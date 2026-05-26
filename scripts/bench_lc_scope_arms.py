"""LEO L.D — operator-runnable scope-routing 3-arm bench wrapper.

Runs ``scripts/bench.py --suite=step7`` twice against a live JAMES
server (once with ``JAMES_SCOPE_ROUTING=0``, once with ``=1``), queries
``audit_log`` for ``reason:route`` rows emitted during the flag-ON
window, and aggregates per-query delta + scope distribution into
``reports/research-runs/lc-scope-bench-<timestamp>.json``.

Operator workflow::

    # 1) Start JAMES server in one terminal
    python web_app.py

    # 2) Run the wrapper in another (server stays up)
    python scripts/bench_lc_scope_arms.py

The 4 STEP-7 arms from the LEO L.0 design memo
(``docs/handovers/v0.4-leo-evidence-scope-routing-track.md``
§"STEP 7 bench plan") are observed indirectly via the scope
distribution captured in the audit_log payload:

  - Flag-OFF arm  — byte-identical baseline (bench.py --check
                     against the committed baseline should still pass)
  - Flag-ON narrow (scope ≤ 0.30) — small-tier backend routing
  - Flag-ON wide   (scope ≥ 0.70) — large-tier backend routing
  - Flag-ON halt-prone — Gemma 4 ``done_reason=length`` cases. This
                          script does not query Ollama's native field
                          directly; check the per-stage trace_synth_call
                          rows in audit_log for ``length`` markers.

Acceptance criteria for L.D closure (informational; this script
reports but does not enforce them — that's the result doc's job):

  - Flag-OFF arm latency / graph_paths within bench.py baseline
    tolerance bands (byte-identical invariant)
  - Flag-ON narrow arm: latency delta ≤ baseline (small backend wins)
  - Flag-ON wide arm: latency delta within +30% (large backend
    acceptable for synthesis burden)
  - No grounded=true rate regression on any arm vs D1 v2 closure
    (manual check against the per-query answer_len + downstream
    grounded markers; not part of bench.py's automated check yet)

This script intentionally does NOT toggle other opt-in flags
(``JAMES_AUTO_ROUTER`` / ``JAMES_ADAPTIVE_BUDGET``). Mixing flag
changes would muddy the scope-routing signal.

Cross-stack note: when Robin (V3'.e schema-adopted) or Ali (Track 3
swap_eval) work runs this stack, both arms MUST stay flag-OFF for
apples-to-apples purity — see ``feedback_cross_stack_run_flag_off`` in
memory.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


REPORTS_DIR = ROOT / "reports" / "research-runs"
# audit_log SQLite path — standard JAMES location. Override via
# JAMES_AUDIT_DB env if your deployment puts it elsewhere.
AUDIT_DB = Path(
    os.environ.get("JAMES_AUDIT_DB", str(ROOT / "audit.db"))
)


def _run_arm(arm_name: str, scope_routing: str) -> Optional[Path]:
    """Run one bench arm with the given JAMES_SCOPE_ROUTING value.

    Returns the path to bench.py's output JSON file, or None on
    failure. bench.py writes to ``reports/bench_<sha>_step7_<stamp>.json``;
    we find the most recently created matching file and assume it
    belongs to this run.
    """
    env = os.environ.copy()
    env["JAMES_SCOPE_ROUTING"] = scope_routing

    print(f"\n=== ARM: {arm_name} (JAMES_SCOPE_ROUTING={scope_routing}) ===")
    pre_existing = set((ROOT / "reports").glob("bench_*_step7_*.json"))
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "bench.py"), "--suite=step7"],
            env=env,
            cwd=str(ROOT),
            capture_output=False,
            check=False,
            timeout=1200,
        )
    except subprocess.TimeoutExpired:
        print(f"[{arm_name}] TIMEOUT after 20 min — aborting arm")
        return None
    elapsed = time.time() - t0
    print(
        f"[{arm_name}] bench.py finished in {elapsed:.1f}s "
        f"(exit code {result.returncode})"
    )

    after = set((ROOT / "reports").glob("bench_*_step7_*.json"))
    new = sorted(after - pre_existing)
    if not new:
        print(f"[{arm_name}] no new bench output found under reports/")
        return None
    return new[-1]


def _load_run(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _query_audit_log_scope_rows(after_iso: str) -> List[Dict]:
    """Query audit_log for reason:route rows since ``after_iso``.

    Returns parsed payload dicts (one per emitted route decision).
    Empty list if audit_log not present — operator may have a custom
    deployment; this is best-effort observability, not core path.
    """
    if not AUDIT_DB.exists():
        print(f"[audit] {AUDIT_DB} not found — skipping scope row capture")
        return []
    try:
        import sqlite3
        conn = sqlite3.connect(str(AUDIT_DB))
        cur = conn.cursor()
        cur.execute(
            "SELECT timestamp, query, answer FROM audit_log "
            "WHERE endpoint = 'reason:route' AND timestamp >= ? "
            "ORDER BY timestamp",
            (after_iso,),
        )
        rows: List[Dict] = []
        for ts, stage, answer in cur.fetchall():
            row: Dict = {"timestamp": ts, "stage": stage, "raw": answer}
            for tok in (answer or "").split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    row[k] = v
            rows.append(row)
        conn.close()
        return rows
    except Exception as e:
        print(f"[audit] query failed: {e}")
        return []


def _aggregate(
    off_run: Dict, on_run: Dict, scope_rows: List[Dict],
) -> Dict:
    """Per-query delta + scope distribution summary."""
    off_by_id = {r["id"]: r for r in off_run.get("results", [])}
    on_by_id = {r["id"]: r for r in on_run.get("results", [])}

    deltas: List[Dict] = []
    for qid in sorted(set(off_by_id) | set(on_by_id)):
        off_r = off_by_id.get(qid, {})
        on_r = on_by_id.get(qid, {})
        delta_pct: Optional[float] = None
        if off_r.get("elapsed") and on_r.get("elapsed"):
            delta_pct = round(
                (on_r["elapsed"] - off_r["elapsed"]) / off_r["elapsed"] * 100, 1
            )
        deltas.append({
            "id": qid,
            "text": (off_r.get("text") or on_r.get("text") or "")[:60],
            "category": off_r.get("category") or on_r.get("category"),
            "off_elapsed": off_r.get("elapsed"),
            "on_elapsed": on_r.get("elapsed"),
            "elapsed_delta_pct": delta_pct,
            "off_graph_paths": off_r.get("graph_paths_count"),
            "on_graph_paths": on_r.get("graph_paths_count"),
            "off_answer_len": off_r.get("answer_len"),
            "on_answer_len": on_r.get("answer_len"),
        })

    # Scope distribution from audit_log (flag-ON window only)
    scope_values: List[float] = []
    for row in scope_rows:
        try:
            scope_values.append(float(row.get("evidence_scope", "")))
        except (ValueError, TypeError):
            pass

    scope_summary: Dict = {}
    if scope_values:
        scope_summary = {
            "count": len(scope_values),
            "mean": round(sum(scope_values) / len(scope_values), 4),
            "min": round(min(scope_values), 4),
            "max": round(max(scope_values), 4),
            "narrow_count": sum(1 for v in scope_values if v <= 0.30),
            "mid_count": sum(1 for v in scope_values if 0.30 < v < 0.70),
            "wide_count": sum(1 for v in scope_values if v >= 0.70),
        }

    backend_counts: Dict[str, int] = {}
    for row in scope_rows:
        b = row.get("backend", "")
        if b:
            backend_counts[b] = backend_counts.get(b, 0) + 1

    return {
        "deltas": deltas,
        "scope_summary": scope_summary,
        "backend_counts": backend_counts,
        "scope_rows": scope_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="LEO L.D scope-routing 3-arm bench wrapper.",
    )
    ap.add_argument(
        "--skip-off", action="store_true",
        help=(
            "Skip the flag-OFF baseline arm. Requires --off-path to "
            "supply a prior bench.py output for the OFF comparison."
        ),
    )
    ap.add_argument(
        "--off-path", type=Path, default=None,
        help="Reuse a prior bench.py output JSON for the flag-OFF arm.",
    )
    args = ap.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Arm 1: flag OFF (baseline)
    if args.off_path:
        off_path = args.off_path
        if not off_path.exists():
            print(f"[bench_lc] --off-path {off_path} does not exist")
            return 1
        print(f"=== Re-using flag-OFF result: {off_path}")
    elif args.skip_off:
        print("[bench_lc] --skip-off requires --off-path")
        return 1
    else:
        off_path = _run_arm("flag-OFF baseline", "0")
        if not off_path:
            print("[bench_lc] flag-OFF arm failed — aborting")
            return 1
    off_run = _load_run(off_path)

    # Capture timestamp boundary for audit_log query on flag-ON window
    on_started_iso = datetime.now().isoformat()

    # Arm 2: flag ON
    on_path = _run_arm("flag-ON scope routing", "1")
    if not on_path:
        print("[bench_lc] flag-ON arm failed — aborting")
        return 1
    on_run = _load_run(on_path)

    # Query audit_log for scope rows from the flag-ON window
    scope_rows = _query_audit_log_scope_rows(on_started_iso)
    print(
        f"\n[audit] captured {len(scope_rows)} reason:route rows "
        f"from flag-ON window"
    )

    agg = _aggregate(off_run, on_run, scope_rows)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"lc-scope-bench-{stamp}.json"
    out_path.write_text(
        json.dumps({
            "generated_at": datetime.now().isoformat(),
            "off_run_path": str(off_path.relative_to(ROOT)),
            "on_run_path": str(on_path.relative_to(ROOT)),
            "off_run_total_seconds": off_run.get("total_seconds"),
            "on_run_total_seconds": on_run.get("total_seconds"),
            "aggregate": agg,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[bench_lc] saved: {out_path.relative_to(ROOT)}")

    # Brief operator-facing summary
    if agg["scope_summary"]:
        ss = agg["scope_summary"]
        print(
            f"\n=== Scope distribution (flag-ON, "
            f"{ss['count']} routing decisions) ==="
        )
        print(
            f"  mean={ss['mean']:.3f}  "
            f"min={ss['min']:.3f}  max={ss['max']:.3f}"
        )
        print(f"  narrow (≤0.30): {ss['narrow_count']}")
        print(f"  mid    (0.30 < scope < 0.70): {ss['mid_count']}")
        print(f"  wide   (≥0.70): {ss['wide_count']}")

    if agg["backend_counts"]:
        print("\n=== Backend selection counts (flag-ON) ===")
        for b, c in sorted(agg["backend_counts"].items()):
            print(f"  {b}: {c}")

    print("\n=== Per-query elapsed delta ===")
    for d in agg["deltas"]:
        if d["elapsed_delta_pct"] is not None:
            sign = "+" if d["elapsed_delta_pct"] >= 0 else ""
            print(
                f"  q{d['id']:2}: {d['off_elapsed']:>5.1f}s -> "
                f"{d['on_elapsed']:>5.1f}s  "
                f"({sign}{d['elapsed_delta_pct']:.1f}%)"
            )
        else:
            print(f"  q{d['id']:2}: incomplete result on one or both arms")

    print(
        "\n[bench_lc] L.D closure: paste aggregate into "
        "reports/promo-assets/v3prime-leo-evidence-scope-result.md"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
