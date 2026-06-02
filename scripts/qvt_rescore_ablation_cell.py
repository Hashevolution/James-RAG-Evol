"""α-5 follow-up — re-score a cell JSON that was written with the wrong
bench output (QQ post-mortem fix for the glob bug landed alongside
this script).

The matrix runner's `_run_single_bench` had a bench-output glob still
hardcoded `step7` (sibling to the #625 subprocess-call fix). When the
matrix ran multihop_rag, the new bench JSON was written under
`reports/bench_*_multihop_rag_*.json` but the runner's post-bench
detection scanned `bench_*_step7_*.json` and picked up an unrelated
stale step7 file. The cell JSON's `runs[*].scores` therefore reflect
the stale file's 12 step7 queries, not the freshly-captured 100
multihop_rag queries.

This script takes a cell JSON written under the buggy code path and
rewrites the runs[*].bench_output + runs[*].scores against the
correct bench JSON (auto-resolved by suite + timestamp proximity, or
provided explicitly). The cell-level `aggregate` is recomputed.

Idempotent — running again with the corrected file is safe; the
rescore_provenance block records what swapped in.

Usage::

    # Auto-find the matching bench JSON for this cell (by suite +
    # cell_end_ts proximity within --tolerance minutes):
    python scripts/qvt_rescore_ablation_cell.py \\
        --cell workspaces/hotpot_eval/reports/research-runs/\\
qvt-ablation-cells/qvt-ablation-cell-L1-M_M.json \\
        --suite multihop_rag

    # Or pass the bench JSON explicitly:
    python scripts/qvt_rescore_ablation_cell.py \\
        --cell <cell.json> \\
        --bench reports/bench_87ed176_multihop_rag_20260531_120746.json

    # Bulk rescore — pass the cell glob:
    python scripts/qvt_rescore_ablation_cell.py \\
        --cell-glob 'workspaces/hotpot_eval/reports/research-runs/\\
qvt-ablation-cells/qvt-ablation-cell-*.json' \\
        --suite multihop_rag

The cell file is overwritten in place after a `.before-rescore.json`
side-copy is created. Side-copy preserves the diagnostic trail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))

from eval.qvt.oracle import (  # noqa: E402
    score_five_axis,
    score_five_axis_by_question_type,
)


BENCH_FILENAME_RE = re.compile(
    r"bench_(?P<sha>[^_]+)_(?P<suite>[a-z_]+?)_"
    r"(?P<ts>\d{8}_\d{6})\.json$"
)


def _resolve_fixture(suite: str) -> Path:
    canonical = ROOT / "eval" / "regression" / f"{suite}_queries.json"
    if canonical.exists():
        return canonical
    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws_raw:
        ws_path = Path(ws_raw).resolve() / "eval" / f"{suite}_queries.json"
        if ws_path.exists():
            return ws_path
    return canonical


def _parse_bench_filename(p: Path) -> Optional[Dict[str, str]]:
    m = BENCH_FILENAME_RE.search(p.name)
    if not m:
        return None
    return m.groupdict()


def _bench_ts(p: Path) -> Optional[datetime]:
    parts = _parse_bench_filename(p)
    if not parts:
        return None
    try:
        return datetime.strptime(parts["ts"], "%Y%m%d_%H%M%S")
    except Exception:
        return None


def _auto_resolve_bench(suite: str, cell_path: Path,
                        tolerance_min: int = 30) -> Optional[Path]:
    """Pick the bench JSON whose mtime is closest to the cell file's
    mtime AND is not newer than the cell. The matrix writes the bench
    file then the cell file; the right pair sits seconds apart with
    bench preceding cell."""
    candidates = list((ROOT / "reports").glob(f"bench_*_{suite}_*.json"))
    if not candidates:
        return None
    cell_mtime = cell_path.stat().st_mtime
    tolerance_s = tolerance_min * 60
    # Prefer bench files written before (or within 60s after) the cell.
    eligible = [
        (cell_mtime - c.stat().st_mtime, c)
        for c in candidates
        if (cell_mtime - c.stat().st_mtime) > -60  # allow 60s clock jitter
    ]
    if not eligible:
        return None
    eligible.sort()
    best_diff, best_path = eligible[0]
    if abs(best_diff) > tolerance_s:
        print(
            f"[warn] closest candidate {best_path.name} is {best_diff:.0f}s "
            f"from cell mtime ({tolerance_s}s tolerance); no match"
        )
        return None
    return best_path


def _rescore_bench(bench_path: Path, fixture: Dict[str, Any]) -> Dict[str, Any]:
    bench_data = json.loads(bench_path.read_text(encoding="utf-8"))
    five = score_five_axis(bench_data, fixture)
    by_qtype = score_five_axis_by_question_type(bench_data, fixture)
    scores = five.to_dict()
    scores["by_question_type"] = {
        qtype: v.to_dict() for qtype, v in by_qtype.items()
    }
    scores["_source_bench"] = str(bench_path.relative_to(ROOT)) \
        if bench_path.is_relative_to(ROOT) else str(bench_path)
    scores["_n_queries"] = len(bench_data.get("results", []))
    return scores


def _stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"median": 0.0, "min": 0.0, "max": 0.0, "noise_band": 0.0}
    return {
        "median": round(statistics.median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "noise_band": round(max(values) - min(values), 4),
    }


def _recompute_aggregate(runs_scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    path_means = [r.get("path_coverage", {}).get("mean_recall", 0.0)
                  for r in runs_scores]
    graded_means = [r.get("graded_answer", {}).get("mean_accuracy", 0.0)
                    for r in runs_scores]
    abstention_f1s = [r.get("abstention", {}).get("f1", 0.0)
                      for r in runs_scores]
    token_means = [r.get("token_cost", {}).get("mean_chars", 0.0)
                   for r in runs_scores]
    latency_means = [r.get("latency_cost", {}).get("mean_s", 0.0)
                     for r in runs_scores]
    return {
        "path_coverage": _stats(path_means),
        "graded_answer": _stats(graded_means),
        "abstention_f1": _stats(abstention_f1s),
        "token_cost": _stats(token_means),
        "latency_cost": _stats(latency_means),
        "n_runs": len(runs_scores),
    }


def _rescore_cell(cell_path: Path, bench_path: Optional[Path],
                  suite: str, dry_run: bool) -> bool:
    cell_data = json.loads(cell_path.read_text(encoding="utf-8"))

    if bench_path is None:
        bench_path = _auto_resolve_bench(suite, cell_path)
        if bench_path is None:
            print(f"[skip] {cell_path.name}: no matching bench JSON found "
                  f"for suite={suite}")
            return False
        print(f"[auto] {cell_path.name} -> {bench_path.relative_to(ROOT)}")
    else:
        print(f"[fixed] {cell_path.name} -> {bench_path.relative_to(ROOT)}")

    fixture_path = _resolve_fixture(suite)
    if not fixture_path.exists():
        print(f"[error] fixture not found at {fixture_path}")
        return False
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    new_scores = _rescore_bench(bench_path, fixture)

    runs = cell_data.get("runs") or []
    old_n = len(runs)
    if not runs:
        runs = [{}]
    # Single-run replacement (T0 smoke is n_runs=1). For multi-run cells
    # we'd need a per-bench mapping — out of scope for the QQ fix; rerun
    # those bigger cells after the running matrix finishes.
    rel_path = (str(bench_path.relative_to(ROOT))
                if bench_path.is_relative_to(ROOT) else str(bench_path))
    runs[0]["bench_output"] = rel_path
    runs[0]["scores"] = new_scores

    cell_data["runs"] = runs
    cell_data["aggregate"] = _recompute_aggregate([r["scores"] for r in runs])
    cell_data.setdefault("rescore_provenance", []).append({
        "rescored_at": datetime.now(timezone.utc).isoformat(),
        "swapped_in_bench": rel_path,
        "old_runs_count": old_n,
        "tool": "scripts/qvt_rescore_ablation_cell.py",
        "reason": "QQ — original cell glob picked stale step7 file",
    })

    if dry_run:
        print(f"[dry-run] would rewrite {cell_path.name}")
        print(f"          path={cell_data['aggregate']['path_coverage']}")
        print(f"          graded={cell_data['aggregate']['graded_answer']}")
        print(f"          abst_f1={cell_data['aggregate']['abstention_f1']}")
        print(f"          token={cell_data['aggregate']['token_cost']}")
        print(f"          latency={cell_data['aggregate']['latency_cost']}")
        return True

    backup = cell_path.with_suffix(".before-rescore.json")
    if not backup.exists():
        shutil.copy2(cell_path, backup)
        print(f"[backup] {backup.name}")
    cell_path.write_text(
        json.dumps(cell_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[wrote] {cell_path.name}")
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--cell", type=Path,
                   help="Single cell JSON to rescore")
    p.add_argument("--cell-glob", type=str,
                   help="Glob of cell JSONs to bulk rescore")
    p.add_argument("--bench", type=Path,
                   help="Explicit bench JSON to score against (skips auto-resolve)")
    p.add_argument("--suite", type=str, default="multihop_rag",
                   help="Suite name (default: multihop_rag)")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview without overwriting")
    args = p.parse_args()

    if not args.cell and not args.cell_glob:
        p.error("--cell or --cell-glob is required")

    cells: List[Path] = []
    if args.cell:
        cells.append(args.cell)
    if args.cell_glob:
        cells.extend(sorted(Path().glob(args.cell_glob)))

    n_ok = 0
    n_skip = 0
    for c in cells:
        if not c.exists():
            print(f"[skip] {c} does not exist")
            n_skip += 1
            continue
        ok = _rescore_cell(c, args.bench, args.suite, args.dry_run)
        if ok:
            n_ok += 1
        else:
            n_skip += 1
    print(f"\nDone. rescored={n_ok} skipped={n_skip}")
    return 0 if n_ok else 1


if __name__ == "__main__":
    sys.exit(main())
