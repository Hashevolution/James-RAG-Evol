"""Axis-2 probe (deterministic, LLM-free): graph-vs-flat utility differential.

Measures the security-utility cost that is *specific to graph-RAG* using a
reachability proxy for multi-hop answerability — no LLM, no core/ edits, only
the pure `check_access` policy function.

Two answerability models on the same access policy:
  - GRAPH : answerable iff some gold path is fully accessible (every hop node,
            including intermediate "hub" nodes, permitted). Path-dependent.
  - FLAT  : answerable iff all evidence endpoints (`support`) are individually
            accessible. Path-independent (no intermediate dependency).

Reports:
  1. Strictness sweep over JAMES's real roles (external→admin): graph vs flat
     answerable counts → the differential.
  2. Redundancy demonstration (a question with an alternative path).
  3. Betweenness ranking of intermediate nodes.
  4. Targeted (highest-betweenness) vs mean gated-node removal → concentration
     / super-linearity of utility loss, and flat's loss from the same removal.

Caveat: this is an *answerability reachability* proxy, NOT measured answer
quality (that needs the LLM probe). It isolates the structural mechanism.

Run:  python -m eval.abac_bench.probe_differential
"""
from __future__ import annotations

import itertools
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.security_layer import check_access  # noqa: E402  (pure function)
from eval.abac_bench.fixtures.axis2_graph import NODES, QUESTIONS  # noqa: E402

ROLES = ["external", "employee", "manager", "admin"]


def _accessible(role: str, nid: str, blocked: frozenset = frozenset()) -> bool:
    if nid in blocked:
        return False
    return check_access(role, {"sensitivity": NODES[nid]["sensitivity"]})


def graph_answerable(role, q, blocked=frozenset()) -> bool:
    return any(all(_accessible(role, n, blocked) for n in path) for path in q["paths"])


def flat_answerable(role, q, blocked=frozenset()) -> bool:
    return all(_accessible(role, n, blocked) for n in q["support"])


def betweenness() -> dict:
    """Intermediate-node appearances across all gold paths (a betweenness proxy)."""
    counts = {nid: 0 for nid in NODES}
    for q in QUESTIONS:
        for path in q["paths"]:
            for n in path[1:-1]:          # intermediates only
                counts[n] += 1
    return counts


def run() -> int:
    n = len(QUESTIONS)

    # ── 1. Strictness sweep ─────────────────────────────────────────────
    print("=" * 78)
    print("Axis-2 — graph-vs-flat answerability differential (reachability proxy)")
    print("=" * 78)
    print(f"\n{'role':<10} {'graph':>7} {'flat':>7} {'differential (flat-graph)':>28}")
    print("-" * 56)
    for role in ROLES:
        g = sum(graph_answerable(role, q) for q in QUESTIONS)
        f = sum(flat_answerable(role, q) for q in QUESTIONS)
        flag = "  ← graph loses path-gated Qs" if f > g else ""
        print(f"{role:<10} {g:>3}/{n:<3} {f:>3}/{n:<3} {f - g:>20}{flag}")

    # ── 2. Per-question at employee (the headline role) ─────────────────
    print("\nPer-question @ employee (sees public+internal; hub is confidential):")
    for q in QUESTIONS:
        g = graph_answerable("employee", q)
        f = flat_answerable("employee", q)
        tag = ""
        if len(q["paths"]) > 1:
            tag = " [redundant]"
        if f and not g:
            tag += " ⚠️ flat-only (graph path gated)"
        print(f"  {q['id']}: graph={'Y' if g else 'N'} flat={'Y' if f else 'N'}"
              f"  ans={NODES[q['answer']]['name']} ({NODES[q['answer']]['sensitivity']}){tag}")

    # ── 3. Betweenness ranking ──────────────────────────────────────────
    bw = betweenness()
    ranked = sorted(((c, nid) for nid, c in bw.items() if c > 0), reverse=True)
    print("\nIntermediate betweenness (gold-path appearances):")
    for c, nid in ranked:
        print(f"  {NODES[nid]['name']:<14} ({NODES[nid]['sensitivity']:<12}) : {c}")

    # ── 4. Targeted vs mean removal (graph) + flat from same removal ────
    # Candidate set = nodes access control can actually gate (non-public).
    gated_candidates = [nid for nid in NODES if NODES[nid]["sensitivity"] != "public"]
    base_graph = sum(graph_answerable("admin", q) for q in QUESTIONS)  # admin = no clearance gating

    def graph_loss(removed: frozenset) -> int:
        after = sum(graph_answerable("admin", q, removed) for q in QUESTIONS)
        return base_graph - after

    def flat_loss(removed: frozenset) -> int:
        base = sum(flat_answerable("admin", q) for q in QUESTIONS)
        after = sum(flat_answerable("admin", q, removed) for q in QUESTIONS)
        return base - after

    top_nid = ranked[0][1]
    targeted_loss = graph_loss(frozenset([top_nid]))
    per_node = [graph_loss(frozenset([nid])) for nid in gated_candidates]
    mean_loss = sum(per_node) / len(per_node)
    flat_from_hub = flat_loss(frozenset([top_nid]))

    print("\nSingle-node removal (k=1) — graph utility loss concentration:")
    print(f"  targeted (highest-betweenness = {NODES[top_nid]['name']}): "
          f"graph loses {targeted_loss}/{base_graph}")
    print(f"  mean over gated nodes:                         "
          f"graph loses {mean_loss:.2f}/{base_graph}")
    print(f"  same removal, FLAT loss:                       "
          f"flat loses {flat_from_hub}/{base_graph}")
    if targeted_loss > mean_loss and flat_from_hub < targeted_loss:
        ratio = targeted_loss / mean_loss if mean_loss else float("inf")
        print(f"\nFinding: removing one high-betweenness *intermediate* node breaks "
              f"{targeted_loss} graph\nmulti-hop answers ({ratio:.1f}× the mean gated "
              f"node) while flat RAG loses {flat_from_hub} — the\nutility cost of "
              f"access control is concentrated and graph-specific. Redundant\npaths "
              f"(Q6) rescue the question where an alternative bypass exists.")
    print("-" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(run())
