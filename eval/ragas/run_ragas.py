"""RAGAS evaluation harness for JAMES (Issue #46, Axis 2-B).

Phase-2 (#46): committed baseline + drift detection. `--check` compares
the current run against `eval/ragas/baseline.json` and exits 1 on hard
drift (mirroring `scripts/bench.py` shape).

Components (all local, no third-party API tokens required):
  - Judge LLM: Ollama via its OpenAI-compatible endpoint
    (http://127.0.0.1:11434/v1). Uses config.GEMMA_MODEL by default;
    operator can point at deepseek/qwen via env JAMES_LLM_MODEL.
  - Embeddings: project's existing models/miniLM
    (paraphrase-multilingual-MiniLM-L12-v2). Same model as ChromaDB
    so retrieval-side and eval-side share semantic space.
  - Fixture: eval/ragas/fixture_v0.2.json — 3 hand-crafted public-
    knowledge rows. Pre-baked retrieved_contexts so we don't need a
    live JAMES /query/ to exercise the harness. Phase 3 swaps this
    for live retrieval once a runner reuses the bench.py shape.

Output: reports/ragas_<timestamp>.json (gitignored). Summary table
        printed to stdout.

Usage:
    python eval/ragas/run_ragas.py
        Run the fixture, save report, print summary.

    python eval/ragas/run_ragas.py --check
        Same run, then compare against committed baseline. Exit 1 on
        any hard-locked drift (per-metric absolute drift > tolerance).
        LLM-judge metrics (faithfulness, answer_relevancy) get a wider
        tolerance than embedding-based metrics (context_*).

    python eval/ragas/run_ragas.py --update-baseline
        DESTRUCTIVE: rewrite the committed baseline from this run's
        numbers. Use only for an intentional scope change (model swap,
        fixture refresh) with diff visible in PR review.

    python eval/ragas/run_ragas.py --fixture eval/ragas/fixture_v0.2.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Ensure UTF-8 console (PR #36 helper) — RAGAS prints non-ASCII judge output.
try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


def _build_llm():
    """Wire Ollama's OpenAI-compatible endpoint as the RAGAS judge LLM."""
    from openai import OpenAI
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper
    from config import GEMMA_MODEL

    chat = ChatOpenAI(
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",     # any non-empty string; Ollama ignores it
        model=GEMMA_MODEL,
        temperature=0.0,
        max_completion_tokens=1024,
    )
    return LangchainLLMWrapper(chat)


class _LocalSentenceTransformerEmbeddings:
    """Minimal langchain Embeddings interface backed by SentenceTransformer.

    RAGAS only requires `embed_query` and `embed_documents`. Wiring this
    avoids depending on `langchain-huggingface` (not installed) and reuses
    the same `models/miniLM` that ChromaDB already loads.
    """

    def __init__(self, model_path: Path):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(str(model_path))

    def embed_query(self, text: str) -> List[float]:
        vec = self._model.encode([text], convert_to_numpy=True)[0]
        return vec.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vecs = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vecs]


def _build_embeddings():
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from config import BASE_DIR
    model_path = Path(BASE_DIR) / "models" / "miniLM"
    if not model_path.exists():
        raise RuntimeError(
            f"miniLM model not found at {model_path}. Run a JAMES query once "
            "(server start) to populate the cache, or download "
            "paraphrase-multilingual-MiniLM-L12-v2 manually."
        )
    return LangchainEmbeddingsWrapper(_LocalSentenceTransformerEmbeddings(model_path))


def _load_fixture(path: Path) -> List[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("rows") or []
    if not rows:
        raise RuntimeError(f"fixture {path} has no rows")
    # Validate every required field exists (RAGAS will fail cryptically otherwise)
    required = ("user_input", "retrieved_contexts", "response", "reference")
    for i, r in enumerate(rows):
        missing = [k for k in required if k not in r]
        if missing:
            raise RuntimeError(f"fixture row {i}: missing fields {missing}")
    return rows


# RAGAS metrics fall into two families with different reproducibility
# characteristics:
#   - embedding-based (context_precision, context_recall): cosine
#     similarity over deterministic miniLM embeddings → tight band
#   - judge-based (faithfulness, answer_relevancy): rely on the Ollama
#     LLM as a judge → wider band (LLM nondeterminism, parser flakiness)
# Tolerance values are absolute drift in the [0, 1] metric space.
_JUDGE_METRICS    = {"faithfulness", "answer_relevancy"}
_EMBEDDING_METRICS = {"context_precision", "context_recall"}


def _load_baseline() -> Optional[dict]:
    path = ROOT / "eval" / "ragas" / "baseline.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _check_baseline(summary: dict, baseline: dict) -> Tuple[bool, List[str]]:
    """Compare run against committed baseline.

    Hard fails (return False):
      - any metric drifts beyond its per-family tolerance band.
      - any metric absent in current run that baseline expects.

    Soft messages: per-metric drift line for the operator log.
    """
    tol_judge     = baseline.get("tolerance", {}).get("judge_metric_abs",     0.15)
    tol_embedding = baseline.get("tolerance", {}).get("embedding_metric_abs", 0.10)
    bm = baseline.get("metrics", {}) or {}

    msgs:  List[str] = []
    fails: List[str] = []
    for metric_name, band in bm.items():
        cur = summary.get(metric_name)
        if cur is None:
            fails.append(
                f"{metric_name}: missing in current run (baseline expected "
                f"[{band.get('min', '?')}, {band.get('max', '?')}])"
            )
            continue
        tol = tol_judge if metric_name in _JUDGE_METRICS else tol_embedding
        lo = band.get("min", 0.0) - tol
        hi = band.get("max", 1.0) + tol
        if not (lo <= cur <= hi):
            fails.append(
                f"{metric_name}: {cur:.3f} outside band "
                f"[{band.get('min'):.3f}, {band.get('max'):.3f}] ± {tol}"
            )
        else:
            msgs.append(
                f"{metric_name}: {cur:.3f} ∈ "
                f"[{band.get('min'):.3f}, {band.get('max'):.3f}] ± {tol}"
            )

    return (len(fails) == 0), msgs + fails


def _update_baseline(summary: dict, elapsed: float) -> None:
    """Replace baseline metric bands with the current run's values.

    Conservative shift: existing tolerance / fingerprint / description
    fields stay as-is; only the per-metric band endpoints + samples
    counter + elapsed_seconds move. To re-fingerprint on a hardware
    change, edit the file directly in the same PR.
    """
    path = ROOT / "eval" / "ragas" / "baseline.json"
    if not path.exists():
        raise RuntimeError(
            f"no existing baseline at {path} — bootstrap by running once "
            "without --update-baseline, then write the file by hand for "
            "the first commit."
        )
    bl = json.loads(path.read_text(encoding="utf-8"))
    bm = bl.setdefault("metrics", {})
    for metric_name, value in summary.items():
        if value is None:
            continue
        band = bm.setdefault(metric_name, {"min": value, "max": value})
        band["min"] = round(min(band.get("min", value), value), 4)
        band["max"] = round(max(band.get("max", value), value), 4)
    bl["samples"] = bl.get("samples", 0) + 1
    totals = bl.setdefault("totals", {})
    if elapsed:
        totals["elapsed_min"]  = round(min(totals.get("elapsed_min",  elapsed), elapsed), 1)
        totals["elapsed_max"]  = round(max(totals.get("elapsed_max",  elapsed), elapsed), 1)
        totals["elapsed_mean"] = round(
            (totals["elapsed_min"] + totals["elapsed_max"]) / 2, 1
        )
    path.write_text(json.dumps(bl, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default=str(ROOT / "eval" / "ragas" / "fixture_v0.2.json"))
    ap.add_argument(
        "--check", action="store_true",
        help="compare against committed eval/ragas/baseline.json; exit 1 on regression",
    )
    ap.add_argument(
        "--update-baseline", action="store_true",
        help="DESTRUCTIVE: extend baseline bands from this run "
             "(use only on intentional scope-change PRs)",
    )
    args = ap.parse_args()

    fixture_path = Path(args.fixture)
    rows = _load_fixture(fixture_path)
    print(f"[RAGAS] loaded {len(rows)} rows from {fixture_path.name}")

    # Build engines lazily so an import error in optional deps is reported
    # with context rather than a cryptic top-level traceback.
    print("[RAGAS] wiring judge LLM (Ollama via OpenAI-compat endpoint)…")
    llm = _build_llm()
    print("[RAGAS] wiring embeddings (local miniLM)…")
    emb = _build_embeddings()

    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import (
        context_precision, context_recall,
        faithfulness, answer_relevancy,
    )

    dataset = EvaluationDataset.from_list(rows)
    metrics = [context_precision, context_recall, faithfulness, answer_relevancy]
    print(f"[RAGAS] evaluating {len(rows)} rows × {len(metrics)} metrics…")
    t0 = time.time()
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        embeddings=emb,
        show_progress=True,
    )
    elapsed = round(time.time() - t0, 1)

    # `result` is a ragas EvaluationResult. Per-metric aggregate is the
    # mean of its per-row column in result.to_pandas(). Direct
    # `result[metric_name]` returns the per-row list, not a scalar.
    summary: dict = {}
    try:
        df = result.to_pandas()
        metric_names = {m.name for m in metrics}
        for col in df.columns:
            if col in metric_names:
                # Drop NaN before averaging — RAGAS marks rows where the
                # judge LLM failed to produce a parseable verdict as NaN.
                series = df[col].dropna()
                summary[col] = float(series.mean()) if len(series) else None
    except Exception as e:
        print(f"[RAGAS] could not extract summary scores: {e}")

    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ragas_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(
        json.dumps({
            "fixture":         fixture_path.name,
            "rows":            len(rows),
            "elapsed_seconds": elapsed,
            "summary":         summary,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n=== RAGAS summary ({elapsed}s, {len(rows)} rows) ===")
    for k, v in summary.items():
        if v is None:
            print(f"  {k:<22s} (n/a)")
        else:
            print(f"  {k:<22s} {v:.3f}")
    print(f"\nsaved: {out_path.relative_to(ROOT)}")

    # --update-baseline: rewrite committed baseline before any check.
    if args.update_baseline:
        _update_baseline(summary, elapsed)
        print("[RAGAS] baseline file updated from this run")
        return 0

    # --check: compare against committed baseline
    if args.check:
        baseline = _load_baseline()
        if baseline is None:
            print("[RAGAS] no baseline at eval/ragas/baseline.json — cannot check")
            return 1
        ok, msgs = _check_baseline(summary, baseline)
        print()
        for m in msgs:
            print(f"  {m}")
        if ok:
            print("\n[RAGAS] OK — within baseline tolerances")
            return 0
        print(f"\n[RAGAS] FAIL — {sum(1 for m in msgs if 'outside band' in m or 'missing' in m)} regression(s)")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
