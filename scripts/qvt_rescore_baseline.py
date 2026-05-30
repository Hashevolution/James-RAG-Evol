"""α-5 follow-up — re-score a captured bench JSON against the current oracle.

When the abstention-phrase list or the source-recall scoring logic
changes (PR #618 / #619 / future), the bench JSONs already on disk
become more interesting than the aggregate JSONs that were computed
against the OLD oracle in memory. This script reads a bench JSON +
the matching fixture, runs ``score_five_axis`` (+
``score_five_axis_by_question_type``) against the current oracle,
and writes a fresh baseline JSON with the corrected aggregate.

Cost: ~seconds per bench JSON (no LLM, no server). Compare to a full
re-capture (~107 min on MultiHop-RAG balanced-100).

Usage::

    # Re-score the bench JSON the baseline-capture run wrote earlier:
    python scripts/qvt_rescore_baseline.py \\
        --bench reports/bench_<sha>_<suite>_<ts>.json \\
        --suite multihop_rag \\
        --output workspaces/hotpot_eval/eval/qvt/baseline_<sha>_rescored.json

    # Multi-run baseline: pass each bench JSON via --bench (repeated).
    python scripts/qvt_rescore_baseline.py \\
        --bench reports/bench_a_step7_x.json \\
        --bench reports/bench_a_step7_y.json \\
        --suite step7

    # Auto-resolve fixture path from --suite (step7 → eval/regression,
    # any other → $JAMES_WORKSPACE/eval/<suite>_queries.json):
    JAMES_WORKSPACE=./workspaces/hotpot_eval \\
      python scripts/qvt_rescore_baseline.py \\
        --bench reports/bench_f7762a3_multihop_rag_20260531_063800.json \\
        --suite multihop_rag

The output schema matches ``qvt_capture_baseline.py``'s
``qvt-baseline-v2``. A `rescore_provenance` block is added so it's
obvious the JSON came from a re-score, not a fresh capture, and which
bench JSONs fed it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.qvt.oracle import (  # noqa: E402
    FiveAxisResult,
    score_five_axis,
    score_five_axis_by_question_type,
)


def _resolve_fixture(suite: str) -> Path:
    """Same resolution as scripts/bench.py:_load_suite."""
    canonical = ROOT / "eval" / "regression" / f"{suite}_queries.json"
    if canonical.exists():
        return canonical
    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws_raw:
        ws_path = Path(ws_raw).resolve() / "eval" / f"{suite}_queries.json"
        if ws_path.exists():
            return ws_path
        sys.exit(f"[error] fixture not found:\n  {canonical}\n  {ws_path}")
    sys.exit(f"[error] fixture not found: {canonical}\n"
             "(set JAMES_WORKSPACE to also search a benchmark workspace)")


def _aggregate_runs(runs: List[FiveAxisResult]) -> Dict[str, Any]:
    """Median + noise band per 5-axis. Mirrors qvt_capture_baseline's
    aggregator. Skips the cost axes when not populated (legacy bench
    JSONs predate the `sources` capture; they still have elapsed)."""
    if not runs:
        return {}

    def _stats(values: List[float]) -> Dict[str, float]:
        s = sorted(values)
        return {
            "median": round(s[len(s) // 2], 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "noise_band": round(max(values) - min(values), 4),
        }

    path_means = [r.path_coverage.mean_recall for r in runs]
    graded_means = [r.graded_answer.mean_accuracy for r in runs]
    abstention_f1s = [r.abstention.f1 for r in runs]
    out: Dict[str, Any] = {
        "path_coverage": _stats(path_means),
        "graded_answer": _stats(graded_means),
        "abstention_f1": _stats(abstention_f1s),
        "n_runs": len(runs),
    }
    token_means = [r.token_cost.mean_chars for r in runs
                   if r.token_cost is not None]
    latency_means = [r.latency_cost.mean_s for r in runs
                     if r.latency_cost is not None]
    if token_means:
        out["token_cost"] = _stats(token_means)
    if latency_means:
        out["latency_cost"] = _stats(latency_means)
    return out


def _git_sha() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, check=True,
            timeout=5,
        )
        return out.stdout.strip()[:7]
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", action="append", required=True,
                    metavar="PATH",
                    help="One or more bench JSON paths (repeat the flag "
                         "for paired N>1 runs).")
    ap.add_argument("--suite", required=True,
                    help="Suite name — used to resolve the fixture path.")
    ap.add_argument("--output", default=None,
                    help="Output baseline JSON path. Default: "
                         "<workspace>/eval/qvt/baseline_<sha>_rescored.json "
                         "or eval/qvt/baseline_<sha>_rescored.json")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    fixture_path = _resolve_fixture(args.suite)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    bench_paths = [Path(p) for p in args.bench]
    missing = [p for p in bench_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"[error] bench JSON not found: {p}")
        return 2

    runs: List[FiveAxisResult] = []
    by_type_per_run: List[Dict[str, FiveAxisResult]] = []
    print(f"=== QVT 5-axis re-score ({len(bench_paths)} run(s)) ===")
    print(f"suite:   {args.suite}")
    print(f"fixture: {fixture_path}")
    print(f"oracle:  current main (run `git log --oneline -3` to see what's loaded)")
    for i, bp in enumerate(bench_paths, start=1):
        bench = json.loads(bp.read_text(encoding="utf-8"))
        result = score_five_axis(bench, fixture)
        per_type = score_five_axis_by_question_type(bench, fixture)
        runs.append(result)
        by_type_per_run.append(per_type)
        print(f"\n[run {i}] {bp.name}")
        print(f"  {result.summary()}")

    aggregate = _aggregate_runs(runs)
    aggregate_by_type: Dict[str, Dict[str, Any]] = {}
    if any(by_type_per_run):
        all_qts = set()
        for d in by_type_per_run:
            all_qts.update(d.keys())
        for qt in sorted(all_qts):
            sub = [d[qt] for d in by_type_per_run if qt in d]
            if sub:
                aggregate_by_type[qt] = _aggregate_runs(sub)

    sha = _git_sha() or "unknown"
    # Default output path.
    if args.output:
        out_path = Path(args.output)
    else:
        ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
        if ws_raw:
            out_dir = Path(ws_raw).resolve() / "eval" / "qvt"
        else:
            out_dir = ROOT / "eval" / "qvt"
        out_path = out_dir / f"baseline_{sha}_rescored.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "qvt-baseline-v2",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha,
        "suite": args.suite,
        "fixture_version": fixture.get("version"),
        "fixture_path": str(fixture_path),
        "n_runs": len(runs),
        "aggregate": aggregate,
        "aggregate_by_question_type": aggregate_by_type,
        "rescore_provenance": {
            "is_rescore": True,
            "bench_paths": [str(p) for p in bench_paths],
            "note": (
                "Re-scored from pre-existing bench JSONs against the "
                "current oracle. Use this when an oracle/phrase update "
                "is more impactful than re-running queries against the "
                "live server (~107 min on MultiHop-RAG balanced-100). "
                "See `eval/qvt/oracle.py` git blame for the change in "
                "effect at re-score time."
            ),
        },
    }
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n[done] re-scored baseline written to {out_path}")
    print(f"aggregate: {aggregate}")
    if aggregate_by_type:
        print(f"per-type aggregates: {list(aggregate_by_type.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
