"""Axis-4 probe (deterministic, LLM-free): recovery / graceful degradation.

Defines and measures the recovery axis that VAULT/SNU leave as future work:
when a role's *default* reasoning path is gated but the answer is otherwise
legitimately reachable, can graph re-route through an *alternative permitted*
path?

For a role and question, classify:
  - reachable    : all evidence endpoints (`support`) accessible (answer is
                   legitimately available to this role).
  - primary_gated: the primary path (paths[0]) is NOT fully accessible.
  - candidate    : reachable AND primary_gated (a routing failure, not a
                   legitimate denial — the only place recovery is defined).
  - recovered    : some alternative path (paths[1:]) is fully accessible.

  recovery_rate = recovered / candidate   (per role)

Uses only the pure `check_access` policy function — parallel-safe, no LLM,
no core/ edits.

Run:  python -m eval.abac_bench.probe_recovery
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.security_layer import check_access  # noqa: E402  (pure function)
from eval.abac_bench.fixtures.axis4_recovery import NODES, QUESTIONS  # noqa: E402

ROLES = ["external", "employee", "manager", "admin"]


def _acc(role, nid):
    return check_access(role, {"sensitivity": NODES[nid]["sensitivity"]})


def _path_ok(role, path):
    return all(_acc(role, n) for n in path)


def run() -> int:
    print("=" * 78)
    print("Axis-4 — recovery / graceful degradation (reachability proxy, no LLM)")
    print("=" * 78)
    print(f"\n{'role':<10} {'reachable':>10} {'primary-gated':>14} "
          f"{'candidate':>10} {'recovered':>10} {'recovery_rate':>14}")
    print("-" * 72)

    detail = {}
    for role in ROLES:
        reachable = primary_gated = candidate = recovered = 0
        cand_ids, rec_ids = [], []
        for q in QUESTIONS:
            is_reachable = all(_acc(role, n) for n in q["support"])
            is_primary_gated = not _path_ok(role, q["paths"][0])
            reachable += is_reachable
            primary_gated += is_primary_gated
            if is_reachable and is_primary_gated:
                candidate += 1
                cand_ids.append(q["id"])
                if any(_path_ok(role, p) for p in q["paths"][1:]):
                    recovered += 1
                    rec_ids.append(q["id"])
        rate = f"{recovered/candidate:.0%}" if candidate else "n/a"
        print(f"{role:<10} {reachable:>10} {primary_gated:>14} "
              f"{candidate:>10} {recovered:>10} {rate:>14}")
        detail[role] = (cand_ids, rec_ids)

    # Headline regime: a role that can see answers (internal) but not the hub.
    cand, rec = detail["employee"]
    print(f"\n@ employee (sees internal answers, hub is confidential):")
    print(f"  candidates (answer reachable, default path gated): {cand}")
    print(f"  recovered via alternative permitted path:          {rec}")
    unrec = [c for c in cand if c not in rec]
    print(f"  unrecovered (no alt / alt also gated):             {unrec}")
    if cand:
        print(f"\nFinding: {len(rec)}/{len(cand)} path-gated-but-reachable questions are "
              f"recovered by\nre-routing through an alternative *permitted* path. The "
              f"rest fail not because\nthe answer is forbidden but because no permitted "
              f"route exists — a graph-RAG\ngraceful-degradation gap that flat retrieval "
              f"(path-independent) does not have.")
    print("-" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(run())
