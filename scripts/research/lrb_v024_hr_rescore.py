"""LRB v0.2.4 HR re-score — apply a different NLI verifier to cached answers.

Cross-NLI agreement check (per prereg §1.2 + §1.4 ⭐⭐⭐ requirement):
each per-query (answer, retrieved_context, claims) was cached by the
primary HR smoke run (`lrb_v024_hr_smoke.py` writes bench.jsonl).
This script re-scores those cached claims with a second verifier
without re-running answer generation.

Usage:
  PYTHONPATH=. python scripts/research/lrb_v024_hr_rescore.py \
    --input reports/external/lrb/v024-hr-smoke-*.bench.jsonl \
    --verifier deberta-v3-anli

Output:
  reports/external/lrb/<input basename>.rescore-<verifier>.bench.jsonl
  reports/external/lrb/<input basename>.rescore-<verifier>.result.json
"""
from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from eval.external.lrb.hr_scorer import (
    HrAggregateResult, HrPerQueryResult, aggregate_to_axes)
from eval.external.lrb.nli_verifier import NliLabel, get_verifier

ROOT = Path(__file__).resolve().parent.parent.parent


def rescore_file(input_path: Path, verifier_name: str,
                  out_dir: Path) -> Dict[str, Any]:
    verifier = get_verifier(verifier_name)
    rows = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    import time
    start = time.perf_counter()
    aggregate = HrAggregateResult(
        nli_verifier_id=type(verifier).__name__)
    rescored_rows = []

    for row in rows:
        claims = row.get("claims", [])
        ctx = row.get("retrieved_context", "")
        nli_results_new = []
        n_entailed = 0
        for claim in claims:
            r = verifier.verify(premise=ctx, hypothesis=claim)
            nli_results_new.append(r)
            if r.label == NliLabel.ENTAILMENT:
                n_entailed += 1
                aggregate.n_entailed += 1
            elif r.label == NliLabel.NEUTRAL:
                aggregate.n_neutral += 1
            elif r.label == NliLabel.CONTRADICTION:
                aggregate.n_contradicted += 1
            aggregate.n_claims_total += 1

        hr_q = (n_entailed / len(claims)) if claims else 1.0
        aggregate.per_query.append(HrPerQueryResult(
            query_id=row["query_id"],
            answer=row.get("answer", ""),
            claims=claims,
            nli_results=nli_results_new,
            hr_score=hr_q,
            context_truncated=len(ctx) > 2000,
        ))
        if not row.get("answer", "").strip():
            aggregate.n_empty_answers += 1
        aggregate.n_queries += 1
        if len(ctx) > 2000:
            aggregate.context_truncated_count += 1

        # Persist new NLI per-claim
        new_row = dict(row)
        new_row[f"nli_per_claim_{verifier_name}"] = [
            {"label": r.label.value,
             "ent":   round(r.score_entailment, 4),
             "neu":   round(r.score_neutral, 4),
             "con":   round(r.score_contradiction, 4)}
            for r in nli_results_new
        ]
        new_row[f"hr_score_{verifier_name}"] = hr_q
        rescored_rows.append(new_row)

    aggregate.elapsed_s = round(time.perf_counter() - start, 4)

    # Write outputs
    stem = input_path.stem
    if stem.endswith(".bench"):
        stem = stem[:-len(".bench")]
    rescore_bench = out_dir / f"{stem}.rescore-{verifier_name}.bench.jsonl"
    with rescore_bench.open("w", encoding="utf-8") as f:
        for row in rescored_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    axes = aggregate_to_axes(aggregate)
    rescore_result = out_dir / f"{stem}.rescore-{verifier_name}.result.json"
    rescore_result.write_text(
        json.dumps({
            "benchmark":      "lrb-v024-hr-rescore",
            "source_bench":   str(input_path.name),
            "nli_verifier":   verifier_name,
            "n_queries":      aggregate.n_queries,
            "axes":           axes,
            "honest_tier":    (
                "v0.2.4 HR cross-NLI re-score (cached answers, no "
                "re-generation). Validates cross-verifier agreement "
                "without burning Ollama time."
            ),
            "started_at":     datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8")

    return {
        "input": str(input_path.name),
        "verifier": verifier_name,
        "HR_mean": axes["HR_mean"],
        "n_claims": axes["n_claims_total"],
        "n_entailed": axes["n_entailed"],
        "elapsed_s": axes["elapsed_s"],
        "result_path": str(rescore_result.relative_to(ROOT)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="HR re-score helper")
    parser.add_argument("--input", required=True,
                        help="glob pattern for HR bench.jsonl files")
    parser.add_argument("--verifier", default="deberta-v3-anli")
    parser.add_argument("--out-dir", type=Path,
                        default=ROOT / "reports" / "external" / "lrb")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(Path(p) for p in glob.glob(args.input))
    if not paths:
        print(f"no files match {args.input!r}")
        return

    print(f"\n=== HR re-score ({args.verifier}, {len(paths)} files) ===")
    summary = []
    for p in paths:
        s = rescore_file(p, args.verifier, args.out_dir)
        summary.append(s)
        print(f"  {p.name}")
        print(f"    HR={s['HR_mean']:.4f}  claims={s['n_claims']}  "
              f"entailed={s['n_entailed']}  elapsed={s['elapsed_s']}s")

    print(f"\n=== SUMMARY ===")
    for s in summary:
        print(f"  {s['input']:60s} → HR={s['HR_mean']:.4f}")


if __name__ == "__main__":
    main()
