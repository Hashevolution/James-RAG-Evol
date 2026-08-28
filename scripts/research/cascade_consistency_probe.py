"""Cascade reasoning-consistency probe (deterministic, no LLM/server).

Question (from the 2026-06-22 measurement check): does the entity-edit
cascade (and the broader T1/T7 lifecycle) actually keep LIVE graph
reasoning consistent? The cascade sets a dropped relation's
``status.active=False`` — but does live traversal HONOR that, or keep
traversing it?

This probe calls the REAL live-context builder
(``GraphEngine.build_graph_context_str`` — the function that hands graph
relations to the LLM) on fixture entities that mix active edges with
lifecycle-deactivated edges (invalidated / superseded / expired), all
above CONFIDENCE_THRESHOLD so the existing confidence filter can't mask
the question. It then models the candidate fix (a status-aware filter)
by pre-filtering the entity's relations, and measures both arms:

  - leakage   = a should-NOT-appear (deactivated) target that still
                appears in the context  → the inconsistency.
  - retention = a should-appear (active) target that appears
                (Path-Recall analog) → the fix must not drop these.

Paired arms:
  CURRENT  — relations passed as-is (today's behavior).
  FILTERED — relations pre-filtered by status (the proposed fix).

Run: python scripts/research/cascade_consistency_probe.py
Exit 0 always (a measurement, not a gate). Writes a JSON report next to
the fixture under reports/research-runs/.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "eval" / "cascade_consistency_fixture.json"


def _is_active(rel: dict) -> bool:
    """The candidate status-aware predicate the live traversal currently
    lacks: an edge is live only if it is not lifecycle-deactivated."""
    st = rel.get("status") or {}
    if st.get("active") is False:
        return False
    if rel.get("mutation_type") in ("invalidated", "superseded", "expired"):
        return False
    return True


def _context_for(eng, entity: dict) -> str:
    # exercise the REAL live-context builder (confidence-only filter today)
    return eng.build_graph_context_str([entity], [], 0.0)


def _present(targets, ctx: str):
    return {t: (t in ctx) for t in targets}


def main(out_path: "Path | None" = None) -> int:
    """Run the probe and write the JSON report.

    ``out_path`` defaults to the committed report under
    ``reports/research-runs/``. Tests pass a temporary path: the report
    is a tracked file, so running the probe against the default dirtied
    the working tree on every test run — and the committed copy is a
    record of a past measurement, not something a test should overwrite.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from core.graph_engine.engine import GraphEngine
    # build_graph_context_str only needs get_rel_type (staticmethod) +
    # module helpers — skip __init__ (no WikiGenerator/vector store).
    eng = object.__new__(GraphEngine)

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    scenarios = data["scenarios"]

    rows = []
    cur_leaks = cur_drops = filt_leaks = filt_drops = 0
    tot_bad = tot_good = 0
    cur_consistent = filt_consistent = 0

    for sc in scenarios:
        ent = sc["entity"]
        good = sc.get("should_appear", [])
        bad = sc.get("should_not_appear", [])
        tot_good += len(good)
        tot_bad += len(bad)

        # CURRENT arm — relations as-is.
        cur_ctx = _context_for(eng, ent)
        cur_bad = _present(bad, cur_ctx)
        cur_good = _present(good, cur_ctx)

        # FILTERED arm — status-aware pre-filter (the proposed fix).
        filt_ent = dict(ent)
        filt_ent["relations"] = [r for r in ent.get("relations", []) if _is_active(r)]
        filt_ctx = _context_for(eng, filt_ent)
        filt_bad = _present(bad, filt_ctx)
        filt_good = _present(good, filt_ctx)

        c_leak = sum(1 for v in cur_bad.values() if v)
        c_drop = sum(1 for v in cur_good.values() if not v)
        f_leak = sum(1 for v in filt_bad.values() if v)
        f_drop = sum(1 for v in filt_good.values() if not v)
        cur_leaks += c_leak; cur_drops += c_drop
        filt_leaks += f_leak; filt_drops += f_drop
        if c_leak == 0 and c_drop == 0:
            cur_consistent += 1
        if f_leak == 0 and f_drop == 0:
            filt_consistent += 1

        rows.append({
            "scenario": sc["name"],
            "current":  {"leaked": [k for k, v in cur_bad.items() if v],
                         "dropped_active": [k for k, v in cur_good.items() if not v]},
            "filtered": {"leaked": [k for k, v in filt_bad.items() if v],
                         "dropped_active": [k for k, v in filt_good.items() if not v]},
        })

    n = len(scenarios)
    report = {
        "fixture": str(FIXTURE.relative_to(ROOT)),
        "scenarios": n,
        "metrics": {
            "current": {
                "invalidated_leakage": cur_leaks,
                "active_dropped": cur_drops,
                "consistent_scenarios": f"{cur_consistent}/{n}",
                "active_retention": round((tot_good - cur_drops) / tot_good, 3) if tot_good else None,
            },
            "filtered_fix": {
                "invalidated_leakage": filt_leaks,
                "active_dropped": filt_drops,
                "consistent_scenarios": f"{filt_consistent}/{n}",
                "active_retention": round((tot_good - filt_drops) / tot_good, 3) if tot_good else None,
            },
        },
        "rows": rows,
        "verdict": (
            "CURRENT live traversal LEAKS lifecycle-deactivated relations "
            "(status ignored); the status-aware filter removes the leak with "
            "full active-relation retention."
            if cur_leaks > 0 and filt_leaks == 0 and filt_drops == 0
            else "see metrics"
        ),
    }

    if out_path is None:
        out_path = ROOT / "reports" / "research-runs" / "cascade-consistency-probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[cascade-probe] scenarios={n}  fixture={report['fixture']}")
    print(f"  CURRENT  : invalidated_leakage={cur_leaks}  active_dropped={cur_drops}  "
          f"consistent={cur_consistent}/{n}  active_retention="
          f"{report['metrics']['current']['active_retention']}")
    print(f"  FILTERED : invalidated_leakage={filt_leaks}  active_dropped={filt_drops}  "
          f"consistent={filt_consistent}/{n}  active_retention="
          f"{report['metrics']['filtered_fix']['active_retention']}")
    for r in rows:
        if r["current"]["leaked"] or r["current"]["dropped_active"]:
            print(f"    · {r['scenario']}: CURRENT leaked={r['current']['leaked']} "
                  f"dropped={r['current']['dropped_active']}")
    print(f"  verdict: {report['verdict']}")
    try:
        shown = out_path.relative_to(ROOT)
    except ValueError:
        shown = out_path          # out_path may sit outside the repo (tests)
    print(f"  report → {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
