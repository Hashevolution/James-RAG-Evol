"""DFS + scoring constants for the graph engine.

Extracted from the legacy single-file ``core/graph_engine.py`` during
the v0.6 oversize-module split (CLAUDE.md rule #5). Values are
byte-identical to the pre-split file; only the location moved.
"""
from __future__ import annotations

import os


CONFIDENCE_THRESHOLD = 0.6
MAX_DEPTH            = 4
DFS_SCORE_THRESHOLD  = 0.05
DEPTH_DECAY          = 0.7

# Relation mutation_types that mean the edge is NOT part of the current
# graph state (deactivated by the cascade / T1 expiration / T7 supersede).
_DEAD_MUTATION_TYPES = ("invalidated", "superseded", "expired")


def relation_is_live(rel: dict) -> bool:
    """v0.6.1 — current-state live traversal must honor lifecycle status.

    Measurement (cascade_consistency_probe, PR #1020) showed live graph
    traversal filtered relations by confidence ONLY, so cascade-/T1-/T7-
    deactivated edges leaked into the LLM context (status was honored only
    in the reconstruct_*_at time-travel path). This predicate restores
    consistency: an edge is live unless ``status.active is False`` or its
    ``mutation_type`` is invalidated/superseded/expired.

    Kill-switch ``JAMES_DISABLE_STATUS_FILTER=1`` → legacy (leaky)
    behavior, for A/B measurement. Untagged legacy edges (no status /
    mutation_type) are treated as live.
    """
    if os.environ.get("JAMES_DISABLE_STATUS_FILTER") == "1":
        return True
    if not isinstance(rel, dict):
        return False
    if (rel.get("status") or {}).get("active") is False:
        return False
    if rel.get("mutation_type") in _DEAD_MUTATION_TYPES:
        return False
    return True


__all__ = [
    "CONFIDENCE_THRESHOLD",
    "MAX_DEPTH",
    "DFS_SCORE_THRESHOLD",
    "DEPTH_DECAY",
    "relation_is_live",
]
