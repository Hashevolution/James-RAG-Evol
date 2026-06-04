"""Axis-3 probe (deterministic, LLM-free): path-survival / relation-leak.

Empirically confirms or refutes the Measurement-0 hypothesis using JAMES's
*real* security functions (`filter_graph_by_abac`, `filter_answer_by_role`)
and the live pipeline's graph-stage filter order
(`core/reasoning/pipeline_loops.py:192-197` →
`core/reasoning/pipeline.py:290`).

It isolates the **defense-layer gap** (no LLM, fully deterministic):

  Channel A — unfiltered reasoning paths: a gated entity removed from the
              node list survives in `graph_paths` (paths are not access-
              filtered at pipeline_loops.py:197).
  Channel B — permitted node's relation references: a permitted (e.g.
              public) entity's `relations` list still names the gated
              target; `filter_graph_by_abac` removes the gated *node* but
              not the *reference* (build_graph_context_str:485-496).
  Output    — given an answer containing the gated name, does
              `filter_answer_by_role` remove it? (Coverage gap: entity-type
              masking applies only to `person` and only for `external`;
              non-person confidential names are never masked.)

This is the *defense-layer* result. Whether the LLM actually echoes what it
sees — the inference/parametric half — is the separate LLM probe (next
artifact), which adds parametric-baseline subtraction.

Run:  python -m eval.abac_bench.probe_path_survival
Exit code 0 = no leak; 1 = at least one leak (CI/regression friendly).
"""
from __future__ import annotations

import copy
import os
import sys

# Allow standalone execution from anywhere.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.security_layer import filter_graph_by_abac, filter_answer_by_role  # noqa: E402
from eval.abac_bench.fixtures.synthetic_graph import ENTITIES, PROBES  # noqa: E402

ROLES = ["employee", "external"]


def _names(entities):
    return {e.get("name", "") for e in entities}


def _relation_targets(entities):
    """Target names referenced by the relation lists of a node set."""
    out = set()
    for e in entities:
        for r in e.get("relations", []) or []:
            if isinstance(r, dict) and r.get("target"):
                out.add(r["target"])
    return out


def run() -> int:
    rows = []
    any_leak = False

    for probe in PROBES:
        forbidden_by_role = probe["forbidden_for"]
        gold_path = probe["gold_path"]

        for role in ROLES:
            forbidden = set(forbidden_by_role.get(role, []))
            if not forbidden:
                continue

            # Full graph context as the DFS would yield (all reachable nodes),
            # then the live filter order: rank → filter_graph (node list only).
            graph_ctx = copy.deepcopy(ENTITIES)
            filtered = filter_graph_by_abac(graph_ctx, role)
            filtered_names = _names(filtered)

            # (1) Node-list enforcement — should remove all forbidden nodes.
            enforcement_ok = not (forbidden & filtered_names)

            # (2) Channel A — forbidden name survives in the unfiltered path.
            channel_a = {n for n in forbidden if n in gold_path}

            # (3) Channel B — forbidden name survives via a permitted node's
            #     relation references (filter removes node, not reference).
            permitted_rel_targets = _relation_targets(filtered)
            channel_b = forbidden & permitted_rel_targets

            # (4) Output filter coverage — simulate the worst-case answer the
            #     model could produce from the leaked context (it echoes the
            #     reasoning path), then apply the REAL output filter with the
            #     FILTERED graph_context (as the live pipeline does).
            answer = f"Based on the reasoning path: {gold_path}."
            filtered_answer = filter_answer_by_role(answer, role, filtered)
            output_leak = {n for n in forbidden if n in filtered_answer}

            leaked = bool(output_leak)
            any_leak = any_leak or leaked

            rows.append({
                "probe": probe["id"],
                "role": role,
                "enforcement_ok": enforcement_ok,
                "ch_A_path": sorted(channel_a),
                "ch_B_relation": sorted(channel_b),
                "output_leak": sorted(output_leak),
                "verdict": "LEAK" if leaked else "ok",
            })

    # ── Report ──────────────────────────────────────────────────────────
    print("=" * 78)
    print("Axis-3 probe — path-survival / relation-leak (deterministic, no LLM)")
    print("=" * 78)
    for r in rows:
        print(f"\n[{r['probe']}] role={r['role']}  →  {r['verdict']}")
        print(f"  node-list enforcement (gated removed) : "
              f"{'PASS' if r['enforcement_ok'] else 'FAIL'}")
        print(f"  channel A (name in reasoning path)    : {r['ch_A_path'] or '—'}")
        print(f"  channel B (name in permitted relation): {r['ch_B_relation'] or '—'}")
        print(f"  output filter leak (survives masking) : {r['output_leak'] or '—'}")

    n_leak = sum(1 for r in rows if r["verdict"] == "LEAK")
    n_enf = sum(1 for r in rows if r["enforcement_ok"])
    print("\n" + "-" * 78)
    print(f"SUMMARY: {len(rows)} (probe×role) cases | "
          f"node-list enforcement PASS: {n_enf}/{len(rows)} | "
          f"output LEAK: {n_leak}/{len(rows)}")
    if n_leak:
        print("\nFinding: node-list ABAC is enforced, but the confidential name "
              "survives via\nunfiltered paths / permitted-node relations and "
              "escapes the output filter\n(non-person names are never entity-type "
              "masked). 'access-controlled by\nconstruction' is refuted at the "
              "defense-layer level for these cases.")
    print("-" * 78)
    return 1 if any_leak else 0


if __name__ == "__main__":
    sys.exit(run())
