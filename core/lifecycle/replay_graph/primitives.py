"""Public primitives: ``reconstruct_graph_at`` + ``view_from_snapshot``
+ ``_validity_contains``.

Extracted from the legacy single-file ``core/lifecycle/replay_graph.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

External callers (routes/admin.py, tests/test_t5_*) import these from
``core.lifecycle.replay_graph`` — the re-export façade in
``__init__.py`` preserves that import shape.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.lifecycle.replay_audit import is_lifecycle_event

from core.lifecycle.replay_graph.db_read import (
    _default_db_path,
    _read_lifecycle_events,
)
from core.lifecycle.replay_graph.handlers import (
    _HANDLERS,
    apply_pack_event,
)
from core.lifecycle.replay_graph.snapshot import GraphSnapshot


# ─── public primitive ──────────────────────────────────────────────


def reconstruct_graph_at(
    t: datetime,
    *,
    audit_log_path: Optional[str] = None,
    include_event_types: Optional[Tuple[str, ...]] = None,
    tenant_id: Optional[str] = None,
) -> GraphSnapshot:
    """Replay every lifecycle event row whose ``timestamp ≤ t`` and
    return the resulting :class:`GraphSnapshot`.

    Args:
        t: UTC-aware ``datetime``. Replay cutoff. Events strictly
            after ``t`` are not folded in.
        audit_log_path: optional path override. Defaults to the
            production audit_log (resolved the same way
            ``emit_lifecycle_event`` resolves it).
        include_event_types: optional tuple restricting which event
            types are considered. Default: every member of
            :data:`LIFECYCLE_EVENT_TYPES`. Mostly useful for
            cross-chain integration in PR-T5.C.
        tenant_id: **v0.5 G1.b** — optional tenant scope. When set,
            only rows whose payload-stamped ``tenant_id`` matches
            this value are folded into the snapshot. ``None``
            (default) preserves byte-identical pre-G1.b behaviour —
            every row is visible regardless of stamp. Rows that do
            NOT carry a ``tenant_id`` field are EXCLUDED when this
            argument is set (the explicit-tenant filter is strict —
            "no tenant stamp" is treated as "not my tenant").

    Returns:
        :class:`GraphSnapshot` — deterministic projection of the
        replayed event stream.

    Pure-function contract (LOCK 4): the only side-channel is the
    audit_log SELECT. The function does not read the wiki, the
    knowledge_tracker, the graph engine, or any other module's
    state — so an audit_log JSON dump alone is enough to reproduce
    the snapshot on any machine.

    Tenant-filter contract (G1.b): the filter is applied AFTER
    JSON parse (not in the SQL WHERE clause) so the determinism
    contract is preserved — a `tenant_id` filter applied to the
    same audit_log + same `t` always yields the same snapshot. The
    SQL pre-filter optimisation is left out intentionally — clarity
    over micro-optimisation, and the post-parse filter pairs
    naturally with G1.a's payload-stamping pattern.
    """
    path = audit_log_path or _default_db_path()
    rows = _read_lifecycle_events(path, t, include_event_types)

    edges: Dict[str, Dict[str, Any]] = {}
    chains: Dict[str, List[str]] = {}
    invalidated: set = set()
    # v0.6 G8.c — mounted-packs projection. Tracked separately from
    # the edge state because pack mount/unmount events do not touch
    # edges/chains. Insertion order is preserved (a pack mounted
    # earlier shows up first in the snapshot tuple).
    mounted_pack_ids: List[str] = []
    n = 0

    for evt, payload_json in rows:
        if not is_lifecycle_event(evt):
            # Defence-in-depth: the SELECT clause already filters
            # by event_type, but a free-text column might carry
            # legacy junk on legacy migrations. Skip silently rather
            # than crash; the audit-only invariant is preserved
            # because the snapshot depends only on rows that *do*
            # validate.
            continue
        if include_event_types and evt not in include_event_types:
            continue
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            # Malformed payload: skip. A future T5.D test will
            # surface a counter so an operator notices, but the
            # snapshot itself must remain deterministic.
            continue
        if not isinstance(payload, dict):
            continue
        # v0.5 G1.b — tenant filter. Applied AFTER parse + dict
        # check so the upstream rows still load with the same
        # determinism, but only matching rows are folded in.
        if tenant_id is not None:
            if payload.get("tenant_id") != tenant_id:
                continue
        # v0.6 G8.c — pack mount/unmount tracking via helper module.
        apply_pack_event(evt, payload, mounted_pack_ids)
        handler = _HANDLERS.get(evt)
        if handler is None:
            continue
        handler(edges, chains, invalidated, payload)
        n += 1

    return GraphSnapshot(
        edges=edges,
        supersede_chains=chains,
        invalidated_ids=frozenset(invalidated),
        replayed_at=t,
        event_count=n,
        # v0.6 G8.c — tuple to freeze the projection (deterministic
        # snapshot field).
        mounted_pack_ids=tuple(mounted_pack_ids),
    )


# ─── PR-T5.C — cross-chain integration helper ──────────────────────


def view_from_snapshot(
    snapshot: GraphSnapshot,
    head_id: str,
    t: datetime,
) -> Optional[Dict[str, Any]]:
    """Single-chain projection of a graph snapshot — the audit-only
    equivalent of :func:`core.lifecycle.supersede_chain.reconstruct_view_at`.

    Walks the supersede chain rooted at ``head_id`` inside ``snapshot``
    (built by :func:`reconstruct_graph_at`) and returns the edge whose
    ``validity`` window contained ``t``, **excluding** edges in
    ``snapshot.invalidated_ids`` (same semantics as
    ``reconstruct_view_at`` — CASCADE invalidations remove the edge
    even when it would otherwise match the interval).

    Args:
        snapshot: the snapshot produced by ``reconstruct_graph_at``.
        head_id: chain root id (same shape as the head dict's id used
            with the live primitive).
        t: UTC-aware ``datetime``.

    Returns:
        The first chain edge (in chain order) whose
        ``validity.from <= t < validity.to`` (``None`` on either bound
        means "open"). ``None`` if no chain edge matches or the head
        is not in the snapshot.

    Cross-chain integration contract (memo §5):
        view_from_snapshot(snapshot, head_id, t) ∈ snapshot.edges.values()
        ∪ {None}

        i.e. when this helper returns an edge, the edge IS in the
        snapshot's edges dict. This pins the live ↔ replay equivalence
        once mutation-site wiring lands (PR-T5.A.b → PR-T5.D I4).

    Why a snapshot-side helper, not a live re-call of
    ``reconstruct_view_at``? The live primitive takes a
    ``lookup: Callable[[str], dict]`` that resolves ids against the
    on-disk wiki. The audit-only invariant (I1) forbids that for
    replay — we must walk the chain using only the snapshot. This
    helper IS the audit-only equivalent.
    """
    if not isinstance(head_id, str) or not head_id:
        return None
    chain_ids = snapshot.supersede_chains.get(head_id)
    if not chain_ids:
        return None

    invalidated = snapshot.invalidated_ids
    match: Optional[Dict[str, Any]] = None

    # Walk in chain order and keep the latest matching edge — mirrors
    # the "iterate forward + return last match" semantics of the live
    # reconstruct_view_at (it walks the supersede order from oldest to
    # newest; the most-recent interval that contains t is the answer).
    for edge_id in chain_ids:
        if edge_id in invalidated:
            continue
        edge = snapshot.edges.get(edge_id)
        if not edge:
            continue
        validity = edge.get("validity") or {}
        if _validity_contains(validity, t):
            match = edge
    return match


def _validity_contains(validity: Dict[str, Any], t: datetime) -> bool:
    """``validity.from <= t < validity.to`` with ``None``-as-open
    semantics. Matches the live ``supersede_chain._validity_contains``
    so the two reconstructions stay byte-equivalent on edge selection.
    """
    from_str = validity.get("from")
    to_str = validity.get("to")
    if from_str is not None:
        try:
            vf = datetime.fromisoformat(str(from_str).replace("Z", "+00:00"))
        except ValueError:
            return False
        if t < vf:
            return False
    if to_str is not None:
        try:
            vt = datetime.fromisoformat(str(to_str).replace("Z", "+00:00"))
        except ValueError:
            return False
        if t >= vt:
            return False
    return True


__all__ = [
    "reconstruct_graph_at",
    "view_from_snapshot",
    "_validity_contains",
]
