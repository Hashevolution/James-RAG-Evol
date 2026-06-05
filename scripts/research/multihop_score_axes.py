"""Score a multihop_terse_run.py output JSON on all three axes
(primary / graded / abstention F1) in a single command.

Usage:
  JAMES_WORKSPACE=./workspaces/hotpot_eval \
  python scripts/research/multihop_score_axes.py reports/multihop_terse_<model>_<ts>.json

  # Pair compare (Δ vs baseline JSON):
  python scripts/research/multihop_score_axes.py <new>.json --vs <baseline>.json
"""
from __future__ import annotations
import argparse
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from eval.qvt.oracle import (
    score_paper_aligned_accuracy,
    score_graded_answer,
    score_abstention_f1,
)

DEFAULT_FIXTURE = os.path.join(
    ROOT, "workspaces", "hotpot_eval", "eval", "multihop_rag_queries.json"
)


def score(bench_path: str, fixture_path: str) -> dict:
    bench = json.loads(open(bench_path, encoding="utf-8").read())
    fixture = json.loads(open(fixture_path, encoding="utf-8").read())
    primary_axis = score_paper_aligned_accuracy(bench, fixture)
    graded_axis = score_graded_answer(bench, fixture)
    abst_axis = score_abstention_f1(bench, fixture)
    return {
        "primary":  primary_axis.accuracy_primary,
        "strict":   primary_axis.accuracy_strict,
        "graded":   graded_axis.mean_accuracy,
        "abst_f1":  abst_axis.f1,
        "n":        primary_axis.n_queries,
        "n_answerable": primary_axis.n_answerable,
        "n_null":   primary_axis.n_null,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("bench")
    p.add_argument("--vs", dest="baseline", default=None,
                   help="Optional baseline JSON for Δ comparison")
    p.add_argument("--fixture", default=DEFAULT_FIXTURE)
    args = p.parse_args()

    new = score(args.bench, args.fixture)
    print(f"\n=== {os.path.basename(args.bench)} ===")
    print(f"  n             = {new['n']}  ({new['n_answerable']} answerable / "
          f"{new['n_null']} null)")
    print(f"  primary       = {new['primary']:.3f}")
    print(f"  strict        = {new['strict']:.3f}")
    print(f"  graded        = {new['graded']:.3f}")
    print(f"  abst_f1       = {new['abst_f1']:.3f}")

    if args.baseline:
        base = score(args.baseline, args.fixture)
        print(f"\n=== vs {os.path.basename(args.baseline)} ===")
        print(f"  Δ primary     = {new['primary'] - base['primary']:+.3f}")
        print(f"  Δ strict      = {new['strict'] - base['strict']:+.3f}")
        print(f"  Δ graded      = {new['graded'] - base['graded']:+.3f}")
        print(f"  Δ abst_f1     = {new['abst_f1'] - base['abst_f1']:+.3f}")


if __name__ == "__main__":
    main()
