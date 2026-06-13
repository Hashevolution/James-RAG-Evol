"""Per-event-type handlers + the ``_HANDLERS`` dispatch dict.

Extracted from the legacy single-file ``core/lifecycle/replay_graph.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

Each handler takes the *mutable* working state (edges dict, chains
dict, invalidated set) and the event payload, and folds the event in
place. The dispatch loop in :mod:`core.lifecycle.replay_graph.primitives`
calls them in audit_log insertion order — they must be associative +
idempotent under repeat replay (the same audit_log JSON read twice
produces the same snapshot).
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from core.lifecycle.replay_audit import (
    EVT_BACKFILL_SNAPSHOT,
    EVT_CASCADE_INVALIDATE,
    EVT_ONTOLOGY_PACK_MOUNTED,
    EVT_ONTOLOGY_PACK_UNMOUNTED,
    EVT_SUPERSEDE_CHAIN_EXTENDED,
    EVT_SUPERSEDE_EDGE_CREATED,
    EVT_T1_EXPIRATION_CASCADE,
    EVT_T2_DISPATCH_CONTRADICTION,
    EVT_T2D_INGEST_DISPATCH,
    LIFECYCLE_EVENT_TYPES,
)
# v0.6 G8.c — pack mount/unmount handlers + dispatch helper live in
# core/lifecycle/replay_packs.py. The handlers are no-ops (mounted-
# packs tracking happens in the dispatch loop via apply_pack_event),
# but the registry needs an entry for each LIFECYCLE_EVENT_TYPES member.
from core.lifecycle.replay_packs import (
    apply_pack_event,
    handle_ontology_pack_mounted,
    handle_ontology_pack_unmounted,
)


def _h_supersede_edge_created(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, list],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    new_id = payload.get("new_edge_id")
    head_id = payload.get("head_id")
    if not isinstance(new_id, str) or not new_id:
        return
    # Edge dict — payload itself is the canonical projection. We
    # strip the head_id field so the edge view matches what
    # walk_supersede_chain would return on the live graph.
    edge_view = {k: v for k, v in payload.items() if k != "head_id"}
    edges[new_id] = edge_view
    # Chain extension semantics: a new edge attaches under its head.
    # If the head is itself a chain root, append; otherwise create a
    # new chain with the head as root + the new edge after.
    if isinstance(head_id, str) and head_id:
        chain = chains.setdefault(head_id, [head_id])
        if new_id not in chain:
            chain.append(new_id)


def _h_supersede_chain_extended(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, list],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    # chain_extended carries (chain_head, new_link, validity). We
    # treat it as an explicit link append — the new edge may have
    # been created earlier by an edge_created event, or may be
    # introduced here directly (backfill).
    head_id = payload.get("chain_head")
    new_link = payload.get("new_link")
    if not isinstance(head_id, str) or not head_id:
        return
    if not isinstance(new_link, str) or not new_link:
        return
    chain = chains.setdefault(head_id, [head_id])
    if new_link not in chain:
        chain.append(new_link)
    # If the link's edge dict wasn't already projected, register a
    # stub so callers can resolve the id → edge mapping.
    if new_link not in edges:
        edges[new_link] = {
            "id":       new_link,
            "_origin":  "supersede_chain_extended",
            "validity": payload.get("validity", {}),
        }


def _h_cascade_invalidate(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, list],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    # cascade.invalidate carries either {invalidated_edges: [...]} or
    # {edge_id: "..."} depending on call site. Accept both — the
    # mutation_type field is informational only.
    ids = payload.get("invalidated_edges")
    if isinstance(ids, list):
        for ei in ids:
            if isinstance(ei, str) and ei:
                invalidated.add(ei)
                edges.pop(ei, None)
    single = payload.get("edge_id")
    if isinstance(single, str) and single:
        invalidated.add(single)
        edges.pop(single, None)


def _h_t1_expiration_cascade(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, list],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    # T1 expiration removes the edge from the active set just like a
    # T6 cascade invalidate. The validity.to field is informational.
    single = payload.get("edge_id")
    if isinstance(single, str) and single:
        invalidated.add(single)
        edges.pop(single, None)


def _h_t2_dispatch_contradiction(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, list],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    # T2 dispatch resolves a CASCADE-vs-EVENT contradiction. The
    # actual mutation it triggers — invalidate or supersede — is
    # emitted as a separate event by the dispatcher, so this handler
    # is a no-op for the snapshot fold (the downstream event carries
    # the state change). We still accept the row so the audit-only
    # invariant (I1) sees a fully decoded event stream.
    return


def _h_t2d_ingest_dispatch(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, list],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    # T2.D pre-merge dispatch — same rationale as T2: the actual
    # mutation (CASCADE or EVENT) emits its own follow-up event.
    return


def _h_backfill_snapshot(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, list],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    # backfill.snapshot bootstraps the replay state. Operator
    # migrations that cannot re-derive a full event history (older
    # wiki rows) emit one of these so the snapshot starts from a
    # known baseline rather than empty.
    initial_edges = payload.get("edges") or {}
    if isinstance(initial_edges, dict):
        for eid, edge in initial_edges.items():
            if isinstance(eid, str) and isinstance(edge, dict):
                edges[eid] = edge
    initial_chains = payload.get("supersede_chains") or {}
    if isinstance(initial_chains, dict):
        for head_id, chain in initial_chains.items():
            if isinstance(head_id, str) and isinstance(chain, list):
                chains[head_id] = [c for c in chain if isinstance(c, str)]
    initial_invalid = payload.get("invalidated_ids") or []
    if isinstance(initial_invalid, list):
        for eid in initial_invalid:
            if isinstance(eid, str):
                invalidated.add(eid)


_HANDLERS: Dict[str, Callable[..., None]] = {
    EVT_SUPERSEDE_EDGE_CREATED:    _h_supersede_edge_created,
    EVT_SUPERSEDE_CHAIN_EXTENDED:  _h_supersede_chain_extended,
    EVT_CASCADE_INVALIDATE:        _h_cascade_invalidate,
    EVT_T1_EXPIRATION_CASCADE:     _h_t1_expiration_cascade,
    EVT_T2_DISPATCH_CONTRADICTION: _h_t2_dispatch_contradiction,
    EVT_T2D_INGEST_DISPATCH:       _h_t2d_ingest_dispatch,
    EVT_BACKFILL_SNAPSHOT:         _h_backfill_snapshot,
    # v0.6 G8.c — handlers imported from replay_packs (no-ops)
    EVT_ONTOLOGY_PACK_MOUNTED:     handle_ontology_pack_mounted,
    EVT_ONTOLOGY_PACK_UNMOUNTED:   handle_ontology_pack_unmounted,
}


# Sanity: every taxonomy entry has a handler. A missing handler in a
# CI build would be a Decision LOCK 4 (pure function) violation
# because the snapshot would non-deterministically drop events.
assert set(_HANDLERS) == set(LIFECYCLE_EVENT_TYPES), (
    "every LIFECYCLE_EVENT_TYPES entry must have a handler in _HANDLERS"
)


__all__ = [
    "_h_supersede_edge_created",
    "_h_supersede_chain_extended",
    "_h_cascade_invalidate",
    "_h_t1_expiration_cascade",
    "_h_t2_dispatch_contradiction",
    "_h_t2d_ingest_dispatch",
    "_h_backfill_snapshot",
    "handle_ontology_pack_mounted",
    "handle_ontology_pack_unmounted",
    "apply_pack_event",
    "_HANDLERS",
]
