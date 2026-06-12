"""LRB v0.2.3b — S3 publication-scale × LLM-grounded × cross-model runner.

Per prereg `docs/research/lrb-v023b-s3-cross-model-preregistration-2026-06-12.md`:
extends v0.2.1 cross-model (S1/S2) gap-table to S3 publication scale
(N=1000 docs / ~5.6k events / 1000 queries) with the same 4-model leg
condition (gemma4:e4b / gemma3:12b / mxtral:8x7b / claude-haiku-4-5).

The v0.2.3 token-mode S3 measurement (PR #825 final) established:
  - R@1 V<N<J pattern preserved 4/4 scale points (S2 → S3 publication)
  - JAMES − Naive gap > +0.10 at every scale point

v0.2.3b extends the cross-scale pattern claim to LLM-grounded scoring
(same RAB H1 deterministic axes; LLM only at the reranker step inside
each SUT adapter). Verdict matrix in prereg §2.

This runner reuses `scripts/research/lrb_run_v021_cross_model.py::run_cell`
and only swaps the fixture path lookup so S3 scenarios resolve correctly.
No new SUT logic; no new scorer logic.

Usage:
  # Token-mode smoke (deterministic; no LLM required) — sanity check
  PYTHONPATH=. python scripts/research/lrb_run_v023b_s3_cross_model.py \\
    --scale smoke --modes token --models token-baseline

  # Single-model LLM-grounded smoke
  PYTHONPATH=. python scripts/research/lrb_run_v023b_s3_cross_model.py \\
    --scale smoke --modes llm-grounded --models gemma4:e4b

  # Publication-scale single-model LLM-grounded
  PYTHONPATH=. python scripts/research/lrb_run_v023b_s3_cross_model.py \\
    --scale publication --modes llm-grounded --models gemma4:e4b

  # Full 4-model LLM-grounded sweep (operator-attended; hours)
  PYTHONPATH=. python scripts/research/lrb_run_v023b_s3_cross_model.py \\
    --scale publication \\
    --modes llm-grounded \\
    --models gemma4:e4b,gemma3:12b,mixtral:8x7b,claude-haiku-4-5
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Reuse v021's run_cell + helpers — only fixture lookup changes.
import scripts.research.lrb_run_v021_cross_model as v021              # noqa: E402

FIXTURE_DIR = ROOT / "eval" / "external" / "_fixtures" / "lrb"
SCALE_TO_FIXTURE = {
    "smoke":       FIXTURE_DIR / "scenario_S3_smoke.json",
    "dev":         FIXTURE_DIR / "scenario_S3_dev.json",
    "publication": FIXTURE_DIR / "scenario_S3_publication.json",
}
OUT_DIR = ROOT / "reports" / "external" / "lrb"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_s3_cell(scale: str, sut_name: str, model: str, mode: str,
                ts: str, out_dir: Path, k: int, ollama_url: str,
                timeout: float) -> Dict[str, Any]:
    """Mirrors `v021.run_cell` but points at the S3 fixture for the
    requested scale."""
    fixture_path = SCALE_TO_FIXTURE[scale]
    if not fixture_path.exists():
        raise FileNotFoundError(
            f"S3 fixture {fixture_path} not found; "
            f"generate first via `python scripts/research/"
            f"build_lrb_scenario_s3.py --scale {scale}`")
    scenario = v021.load_scenario(fixture_path)
    sha = v021.fixture_sha(fixture_path)
    qid_to_cat = {q["query_id"]: q["category"]
                  for q in scenario["queries"]}

    print(f"  cell: scale={scale} sut={sut_name} model={model} mode={mode}")
    factory = v021.SUT_FACTORIES[sut_name]
    run = v021.run_sut_cross_model(
        factory, scenario, sha,
        sut_name=sut_name, mode=mode, model=model,
        ollama_url=ollama_url, timeout=timeout, k=k)
    # S3 has query_time always, so Phase B scorer applies.
    axes = v021.score_run_phase_b(run, k_recall=k)
    rows = [{
        "query_id":      qr.query_id,
        "timestamp":     qr.timestamp,
        "gold":          qr.gold,
        "retrieved":     qr.retrieved,
        "latency_s":     qr.latency_s,
        "context_chars": qr.context_chars,
    } for qr in run.per_query]
    axes["per_category"] = v021.per_category_breakdown(rows, qid_to_cat)

    result = {
        "benchmark":     "lrb",
        "version":       "v0.2.3b",
        "scenario":      f"S3-{scale}",
        "scenario_spec": scenario["spec"],
        "scale_preset":  scale,
        "sut":           sut_name,
        "model":         model,
        "mode":          mode,
        "n_evaluations": len(rows),
        "elapsed_s":     round(run.elapsed_s, 4),
        "fixture_sha":   sha,
        "honest_tier": (
            f"v0.2.3b S3-{scale} cross-model cell; deterministic axes "
            "(RAB H1). NOT publication. Pre-reg: docs/research/"
            "lrb-v023b-s3-cross-model-preregistration-2026-06-12.md"
        ),
        "axes":          axes,
        "started_at":    datetime.now(timezone.utc).isoformat(),
    }

    safe_model = model.replace(":", "-").replace("/", "-")
    cell_label = f"v023b-s3-{scale}-{safe_model}-{mode}"
    result_path = out_dir / f"{cell_label}-{ts}.{sut_name}.result.json"
    import json
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8")
    bench_path = out_dir / f"{cell_label}-{ts}.{sut_name}.bench.jsonl"
    with bench_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ov = result["axes"]["overall"]
    ex = ov["exploratory"]
    print(f"    R@10={ov['R@10']}  temporal_acc={ov['temporal_accuracy']}  "
          f"R@1={ex['R@1']}  elapsed={result['elapsed_s']}s")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LRB v0.2.3b S3 cross-model runner")
    parser.add_argument(
        "--scale", default="smoke",
        choices=list(SCALE_TO_FIXTURE.keys()),
        help=("S3 scale: smoke (CI-safe, 100 docs / ~280 events / 100 q), "
              "dev (300 docs / ~1.2k events / 300 q), publication "
              "(1000 docs / ~5.6k events / 1000 q). Must match a "
              "previously-generated S3 fixture."),
    )
    parser.add_argument("--suts", default="vanilla,naive-supersede,james",
                        help="comma-separated SUT names")
    parser.add_argument(
        "--models", default="token-baseline",
        help=("comma-separated model names; token-baseline is a synonym "
              "for any model in token mode. LLM-grounded mode needs "
              "real model ids (gemma4:e4b / gemma3:12b / mixtral:8x7b "
              "/ claude-haiku-4-5)."),
    )
    parser.add_argument("--modes", default="token",
                        help="comma-separated: token,llm-grounded")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_stamp()

    suts = [s.strip() for s in args.suts.split(",") if s.strip()]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    print("=== LRB v0.2.3b S3 cross-model runner ===")
    print(f"  scale:    {args.scale}")
    print(f"  fixture:  {SCALE_TO_FIXTURE[args.scale]}")
    print(f"  SUTs:     {suts}")
    print(f"  models:   {models}")
    print(f"  modes:    {modes}")
    print(f"  ts:       {ts}")
    print(f"  out:      {args.out_dir}")

    cells: List[Dict[str, Any]] = []
    for mode in modes:
        for model in models:
            # Skip duplicate token cells across models — same as v021.
            if mode == "token" and any(
                    c["model"] == "token-baseline"
                    and c["scale_preset"] == args.scale
                    and c["mode"] == "token"
                    for c in cells):
                continue
            effective_model = ("token-baseline"
                               if mode == "token" else model)
            for sut in suts:
                cell = run_s3_cell(
                    args.scale, sut, effective_model, mode,
                    ts, args.out_dir, args.k,
                    args.ollama_url, args.timeout)
                cells.append(cell)

    # Gap table summary per (model, mode).
    print(f"\n=== SUMMARY (S3-{args.scale}) ===")
    by_key: Dict[tuple, Dict[str, Dict[str, Any]]] = {}
    for c in cells:
        key = (c["model"], c["mode"])
        by_key.setdefault(key, {})[c["sut"]] = c
    for (model, mode), suts_dict in by_key.items():
        print(f"\n  {model} / {mode}:")
        for sut_name in ("vanilla", "naive-supersede", "james"):
            if sut_name not in suts_dict:
                continue
            ov = suts_dict[sut_name]["axes"]["overall"]
            r1 = ov["exploratory"]["R@1"]
            ta = ov["temporal_accuracy"]
            print(f"    {sut_name:<18s}  R@1={r1:.4f}  temp_acc={ta:.4f}")
        if all(sut_name in suts_dict
               for sut_name in ("vanilla", "naive-supersede", "james")):
            v = suts_dict["vanilla"]["axes"]["overall"]["exploratory"]["R@1"]
            n = suts_dict["naive-supersede"]["axes"]["overall"][
                "exploratory"]["R@1"]
            j = suts_dict["james"]["axes"]["overall"]["exploratory"]["R@1"]
            v_n_j = v < n < j
            j_n_gap = j - n
            print(f"    V<N<J: {v_n_j}   J-N gap: {j_n_gap:+.4f}")


if __name__ == "__main__":
    main()
