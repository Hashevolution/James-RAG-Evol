"""Recover a missing cell JSON from a bench JSON (or partial bench
reconstruction from trace files when even the bench JSON is missing).

When the matrix runner's post-bench detection fails silently (no
new bench file picked up despite the subprocess completing), the
cell JSON never gets written. This script gives the operator a
manual recovery path:

  Mode A — `from-bench`: a bench JSON exists at `--bench`. Build a
  proper cell JSON wrapping it. Same schema the matrix runner emits.
  Reliable.

  Mode B — `from-traces`: no bench JSON; reconstruct a partial
  bench-shape from per-trace JSONL files in the workspace. Cost
  axes (token via answer_len, latency_ms) recover; quality axes
  cannot (full answer text is not in traces). Output is flagged
  `partial=True` in the cell JSON so downstream readers don't trust
  it as a complete record.

Usage::

    # Mode A — bench JSON exists but cell JSON was never written
    python scripts/qvt_recover_cell_json.py \\
        --row L3 --tier M_M --suite multihop_rag \\
        --mode from-bench \\
        --bench reports/bench_<sha>_multihop_rag_<ts>.json \\
        --out workspaces/hotpot_eval/reports/research-runs/\\
qvt-ablation-cells/qvt-ablation-cell-L3-M_M.json

    # Mode B — no bench JSON, recover cost-axes only from traces
    python scripts/qvt_recover_cell_json.py \\
        --row L3 --tier M_M --suite multihop_rag \\
        --mode from-traces \\
        --trace-dir workspaces/hotpot_eval/reports/trace/2026-05-31 \\
        --first-session 1 --last-session 100 \\
        --out workspaces/hotpot_eval/reports/research-runs/\\
qvt-ablation-cells/qvt-ablation-cell-L3-M_M.json

Mode B output's quality axes are zero/NaN by construction; treat as
"this cell's cost axes are these numbers; quality axes need rerun."
"""

from __future__ import annotations

import argparse
import json
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

_ROW_ENVS: Dict[str, Dict[str, str]] = {
    "L0": {"JAMES_ENABLE_ENTITY_ANCHOR": "0", "JAMES_ENABLE_QUERY_REWRITE": "0",
           "JAMES_AUTO_ROUTER": "0", "JAMES_ADAPTIVE_BUDGET": "0",
           "JAMES_SCOPE_ROUTING": "0"},
    "L1": {"JAMES_ENABLE_ENTITY_ANCHOR": "1", "JAMES_ENABLE_QUERY_REWRITE": "1",
           "JAMES_AUTO_ROUTER": "0", "JAMES_ADAPTIVE_BUDGET": "0",
           "JAMES_SCOPE_ROUTING": "0"},
    "L2": {"JAMES_ENABLE_ENTITY_ANCHOR": "1", "JAMES_ENABLE_QUERY_REWRITE": "1",
           "JAMES_AUTO_ROUTER": "1", "JAMES_ADAPTIVE_BUDGET": "0",
           "JAMES_SCOPE_ROUTING": "0"},
    "L3": {"JAMES_ENABLE_ENTITY_ANCHOR": "1", "JAMES_ENABLE_QUERY_REWRITE": "1",
           "JAMES_AUTO_ROUTER": "0", "JAMES_ADAPTIVE_BUDGET": "1",
           "JAMES_SCOPE_ROUTING": "0"},
    "L4": {"JAMES_ENABLE_ENTITY_ANCHOR": "1", "JAMES_ENABLE_QUERY_REWRITE": "1",
           "JAMES_AUTO_ROUTER": "0", "JAMES_ADAPTIVE_BUDGET": "0",
           "JAMES_SCOPE_ROUTING": "1"},
    "L5": {"JAMES_ENABLE_ENTITY_ANCHOR": "1", "JAMES_ENABLE_QUERY_REWRITE": "1",
           "JAMES_AUTO_ROUTER": "1", "JAMES_ADAPTIVE_BUDGET": "1",
           "JAMES_SCOPE_ROUTING": "1"},
}

_TIER_MODELS: Dict[str, str] = {
    "M_S": "gemma3:4b", "M_M": "gemma4:e4b", "M_L": "gemma3:12b",
}


def _resolve_fixture(suite: str) -> Path:
    import os
    canonical = ROOT / "eval" / "regression" / f"{suite}_queries.json"
    if canonical.exists():
        return canonical
    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws_raw:
        ws_path = Path(ws_raw).resolve() / "eval" / f"{suite}_queries.json"
        if ws_path.exists():
            return ws_path
    return canonical


def _stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"median": 0.0, "min": 0.0, "max": 0.0, "noise_band": 0.0}
    return {
        "median": round(statistics.median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "noise_band": round(max(values) - min(values), 4),
    }


def _build_aggregate(score: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "path_coverage": _stats([score.get("path_coverage", {}).get("mean_recall", 0.0)]),
        "graded_answer": _stats([score.get("graded_answer", {}).get("mean_accuracy", 0.0)]),
        "abstention_f1": _stats([score.get("abstention", {}).get("f1", 0.0)]),
        "token_cost": _stats([score.get("token_cost", {}).get("mean_chars", 0.0)]),
        "latency_cost": _stats([score.get("latency_cost", {}).get("mean_s", 0.0)]),
        "n_runs": 1,
    }


def recover_from_bench(args) -> Dict[str, Any]:
    bench_path = Path(args.bench)
    if not bench_path.exists():
        print(f"[error] bench JSON not found: {bench_path}")
        sys.exit(2)
    bench_data = json.loads(bench_path.read_text(encoding="utf-8"))
    fixture_path = _resolve_fixture(args.suite)
    if not fixture_path.exists():
        print(f"[error] fixture not found: {fixture_path}")
        sys.exit(2)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    five = score_five_axis(bench_data, fixture)
    by_type = score_five_axis_by_question_type(bench_data, fixture)
    scores = five.to_dict()
    scores["by_question_type"] = {qt: v.to_dict() for qt, v in by_type.items()}
    scores["_source_bench"] = str(bench_path.relative_to(ROOT)) \
        if bench_path.is_relative_to(ROOT) else str(bench_path)
    scores["_n_queries"] = len(bench_data.get("results", []))

    rel_bench = str(bench_path.relative_to(ROOT)) \
        if bench_path.is_relative_to(ROOT) else str(bench_path)
    return {
        "schema": "qvt-ablation-cell-v2",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": bench_data.get("git_sha"),
        "row": args.row,
        "row_label": args.row,
        "tier": args.tier,
        "model": _TIER_MODELS.get(args.tier, args.tier),
        "env": _ROW_ENVS.get(args.row, {}),
        "fixed_env": {},
        "sanity_think_on": False,
        "fixture_version": fixture.get("version"),
        "n_runs": 1,
        "aggregate": _build_aggregate(scores),
        "aggregate_by_question_type": {},
        "runs": [{"bench_output": rel_bench, "scores": scores}],
        "_recovery": {
            "mode": "from-bench",
            "recovered_at": datetime.now(timezone.utc).isoformat(),
            "tool": "scripts/qvt_recover_cell_json.py",
            "reason": "matrix runner post-bench detection failed silently",
        },
    }


def recover_from_traces(args) -> Dict[str, Any]:
    import os
    trace_dir = Path(args.trace_dir)
    if not trace_dir.exists():
        print(f"[error] trace dir not found: {trace_dir}")
        sys.exit(2)
    needed_sessions = {
        f"bench_{args.suite}_{i}"
        for i in range(args.first_session, args.last_session + 1)
    }
    # mtime window to isolate the right cell's traces (each cell's
    # bench subprocess restarts session_id counting at 1; without
    # mtime filtering, traces from earlier cells overwrite the target
    # cell's data via session_id collisions).
    mtime_after = args.mtime_after
    mtime_before = args.mtime_before
    per_session: Dict[str, Dict[str, Any]] = {}
    for jf in trace_dir.glob("*.jsonl"):
        m = os.path.getmtime(jf)
        if mtime_after is not None and m < mtime_after:
            continue
        if mtime_before is not None and m > mtime_before:
            continue
        try:
            session_id: Optional[str] = None
            answer_len = 0
            elapsed_ms = 0
            for line in jf.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if session_id is None:
                    sid = rec.get("session_id")
                    if sid:
                        session_id = sid
                if rec.get("stage") == "complete":
                    elapsed_ms = rec.get("elapsed_ms", 0)
                    answer_len = rec.get("answer_len", 0)
            if session_id and session_id in needed_sessions:
                per_session[session_id] = {
                    "answer_len": answer_len,
                    "elapsed_ms": elapsed_ms,
                }
        except Exception:
            continue
    if not per_session:
        print("[error] no matching session traces found")
        sys.exit(2)
    n = len(per_session)
    answer_chars = [v["answer_len"] for v in per_session.values()]
    elapsed_s = [v["elapsed_ms"] / 1000.0 for v in per_session.values()]
    mean_chars = sum(answer_chars) / n
    mean_s = sum(elapsed_s) / n
    p95_chars = sorted(answer_chars)[int(0.95 * n)] if n > 1 else answer_chars[0]
    p95_s = sorted(elapsed_s)[int(0.95 * n)] if n > 1 else elapsed_s[0]
    partial_scores = {
        "path_coverage": {"mean_recall": None, "_partial": True},
        "graded_answer": {"mean_accuracy": None, "_partial": True},
        "abstention": {"f1": None, "_partial": True},
        "token_cost": {"mean_chars": round(mean_chars, 2),
                       "p95_chars": round(p95_chars, 2), "n_queries": n},
        "latency_cost": {"mean_s": round(mean_s, 2),
                         "p95_s": round(p95_s, 2), "n_queries": n},
        "_partial": True,
        "_recovered_sessions": sorted(per_session.keys()),
    }
    aggregate = {
        "path_coverage": _stats([0]),
        "graded_answer": _stats([0]),
        "abstention_f1": _stats([0]),
        "token_cost": _stats([mean_chars]),
        "latency_cost": _stats([mean_s]),
        "n_runs": 1,
        "_partial": True,
    }
    return {
        "schema": "qvt-ablation-cell-v2-partial",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": None,
        "row": args.row,
        "row_label": args.row,
        "tier": args.tier,
        "model": _TIER_MODELS.get(args.tier, args.tier),
        "env": _ROW_ENVS.get(args.row, {}),
        "fixed_env": {},
        "sanity_think_on": False,
        "fixture_version": None,
        "n_runs": 1,
        "aggregate": aggregate,
        "aggregate_by_question_type": {},
        "runs": [{"bench_output": None, "scores": partial_scores}],
        "_recovery": {
            "mode": "from-traces",
            "recovered_at": datetime.now(timezone.utc).isoformat(),
            "tool": "scripts/qvt_recover_cell_json.py",
            "reason": "bench JSON missing; reconstructed cost-axes only from per-trace JSONL",
            "n_sessions_recovered": n,
            "first_session": args.first_session,
            "last_session": args.last_session,
            "limitations": [
                "quality axes (path/graded/abst_f1) are not in evidence",
                "rerun the cell to obtain quality verdict",
            ],
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--row", required=True, choices=list(_ROW_ENVS.keys()))
    p.add_argument("--tier", required=True, choices=list(_TIER_MODELS.keys()))
    p.add_argument("--suite", required=True)
    p.add_argument("--mode", required=True, choices=["from-bench", "from-traces"])
    p.add_argument("--bench", type=Path, help="bench JSON path (mode from-bench)")
    p.add_argument("--trace-dir", type=Path, help="trace dir (mode from-traces)")
    p.add_argument("--first-session", type=int, default=1)
    p.add_argument("--last-session", type=int, default=100)
    p.add_argument("--mtime-after", type=float, default=None,
                   help="Trace mtime floor (unix timestamp). Use to "
                        "isolate one cell's traces when session_ids "
                        "collide across cells.")
    p.add_argument("--mtime-before", type=float, default=None,
                   help="Trace mtime ceiling (unix timestamp).")
    p.add_argument("--out", type=Path, required=True, help="cell JSON output path")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.mode == "from-bench":
        if not args.bench:
            p.error("--bench required for mode from-bench")
        cell = recover_from_bench(args)
    else:
        if not args.trace_dir:
            p.error("--trace-dir required for mode from-traces")
        cell = recover_from_traces(args)

    if args.dry_run:
        print(json.dumps(cell.get("aggregate", {}), indent=2))
        print(f"[dry-run] would write {args.out}")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(cell, indent=2, ensure_ascii=False, default=str),
                            encoding="utf-8")
        print(f"[wrote] {args.out}")
        print(f"[mode] {args.mode}")
        if args.mode == "from-traces":
            print("[warning] partial recovery — quality axes not in evidence; rerun cell to verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
