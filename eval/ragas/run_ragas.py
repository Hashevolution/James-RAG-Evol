"""RAGAS evaluation harness for JAMES (Issue #46, Axis 2-B).

Phase-1 scope: ship a working harness shell, NOT a baseline. The harness
is wired to local infra (Ollama as judge LLM, sentence-transformers for
embeddings) so the first run on a clean laptop produces real numbers
without OpenAI/HF/Cohere tokens. The first committed baseline lands in
a follow-up PR after a representative-hardware run.

Why this PR doesn't commit baseline numbers:
  - The "first run after merge becomes the v0.2 baseline" line in #46
    is intentional: the baseline must be reproducible on the user's
    Windows + Ollama + 16 GB box. Pre-committing a number from this
    development machine would lie about reproducibility.

Components (all local, no third-party API tokens required):
  - Judge LLM: Ollama via its OpenAI-compatible endpoint
    (http://127.0.0.1:11434/v1). Uses config.GEMMA_MODEL by default;
    operator can point at deepseek/qwen via env JAMES_LLM_MODEL.
  - Embeddings: project's existing models/miniLM
    (paraphrase-multilingual-MiniLM-L12-v2). Same model as ChromaDB
    so retrieval-side and eval-side share semantic space.
  - Fixture: eval/ragas/fixture_v0.2.json — 3 hand-crafted public-
    knowledge rows. Pre-baked retrieved_contexts so we don't need a
    live JAMES /query/ to exercise the harness. Phase 2 swaps this
    for live retrieval once #45 lands a bench.py runner.

Output: reports/ragas_<timestamp>.json (gitignored). Summary table
        printed to stdout.

Usage:
    python eval/ragas/run_ragas.py
    python eval/ragas/run_ragas.py --fixture eval/ragas/fixture_v0.2.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default=str(ROOT / "eval" / "ragas" / "fixture_v0.2.json"))
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
