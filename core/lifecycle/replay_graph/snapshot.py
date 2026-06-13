"""``GraphSnapshot`` dataclass + empty-snapshot factory.

Extracted from the legacy single-file ``core/lifecycle/replay_graph.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

External callers (routes/admin.py, tests/test_t5_*) import
``GraphSnapshot`` from ``core.lifecycle.replay_graph`` — the re-export
façade in ``__init__.py`` preserves that import shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Tuple


@dataclass(frozen=True)
class GraphSnapshot:
    """Deterministic projection of the lifecycle event stream up to a
    cutoff time.

    Attributes:
        edges: ``edge_id → edge dict``. Each edge dict carries the
            payload of the event that materialised it (supersede
            ``edge_created`` / backfill ``snapshot``), minus any
            edge_ids that landed in :attr:`invalidated_ids` afterwards.
        supersede_chains: ``head_id → ordered list of edge_ids``,
            including the head. Chains are walked in event order so a
            late ``chain_extended`` cleanly appends.
        invalidated_ids: edge_ids whose **lifecycle.cascade.invalidate**
            (T6) or **lifecycle.t1.expiration_cascade** (T1) event has
            fired with timestamp ≤ ``t``. Invalidated edges are NOT in
            :attr:`edges` — replay omits them just as the live graph
            does (matches ``reconstruct_view_at``'s mutation_type filter).
        replayed_at: the ``t`` cutoff used to compute the snapshot.
        event_count: how many lifecycle event rows contributed
            (≥ 0). 0 on a fresh DB or a pre-mutation-wiring run.
    """
    edges:             Dict[str, Dict[str, Any]]
    supersede_chains:  Dict[str, List[str]]
    invalidated_ids:   FrozenSet[str]
    replayed_at:       datetime
    event_count:       int
    # v0.6 G8.c — ontology pack registry as it was at `replayed_at`.
    # ``pack_id → pack provenance dict`` (carries the pack's
    # capability + since + provenance string at the moment it was
    # mounted; does NOT carry the pack's subtypes / relations /
    # roles because those are content the pack owns + would bloat
    # the snapshot). Empty when no packs are mounted at `t`.
    mounted_pack_ids:  Tuple[str, ...] = ()


def _empty_snapshot(t: datetime) -> GraphSnapshot:
    """Returned when the audit_log has no lifecycle rows
    (e.g. pre-migration DB, pre-wiring production DB).
    """
    return GraphSnapshot(
        edges={}, supersede_chains={}, invalidated_ids=frozenset(),
        replayed_at=t, event_count=0, mounted_pack_ids=(),
    )


__all__ = ["GraphSnapshot", "_empty_snapshot"]
