"""v0.4 Sprint 5 PR-T7.A — T7 supersede chain operations.

Three pure functions for the supersede primitive:

  - ``supersede_edge(old_edge, new_fact, supersede_ts)`` — builds a
    new edge from ``new_fact``, marks the old edge with
    ``status.superseded_by = new_edge.id`` +
    ``status.superseded_at = supersede_ts`` +
    ``status.active = False`` + ``mutation_type = "superseded"``.
    **Does NOT call cascade_remove** — preservation is the whole
    point of T7 (versus Layer 3's destructive CASCADE).
  - ``walk_supersede_chain(edge)`` — follows ``status.superseded_by``
    pointers across the chain. Returns the ordered list with the
    starting edge first and the active head last. Detects cycles
    and raises (cycles are an insertion bug, never representable
    in valid state).
  - ``reconstruct_view_at(head, predicate, t)`` — replay primitive.
    Given the chain head + a node-lookup ``predicate`` (caller
    supplies the id-to-edge map), walks backward through the chain
    and returns the edge whose ``validity`` window contained ``t``.
    Skips edges marked ``mutation_type == "invalidated"`` (CASCADE
    deletions are semantically gone for replay; supersede chain
    members remain visible).

What this module is NOT
-----------------------

- **Not engine-wired.** The production caller (``contradiction_arbiter``
  B-path routing) lands at PR-T2.B / PR-T2.C. Until then, these
  functions are pure-data utilities ready to plug in.
- **Not a graph traversal.** The chain is a linear linked list
  through ``status.superseded_by``. Multi-edge knowledge mutations
  (one fact replacing several) compose via repeated
  ``supersede_edge`` calls at the caller's discretion — no
  fan-in/fan-out semantics here.
- **Not a fact storage layer.** ``new_fact`` is the caller's
  pre-shaped dict (typically the same shape the
  ``contradiction_arbiter`` already produces from a contradicting
  observation). This module composes ``apply_v04_edge_defaults`` on
  top so the new edge has the v0.4 T1+T7 vocabulary populated.

Why a pure module
-----------------

Tests can build chains in-memory without touching disk. Production
callers (PR-T2.C wiring) load entity frontmatter, materialize the
edges as dicts, call ``supersede_edge`` to produce the (new_edge,
mutated_old_edge) pair, and write both back. The orthogonality
keeps the wiki I/O surface out of the chain logic + lets the
contradiction arbiter use the same primitives in a memory-only
arbiter test.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.lifecycle.etag import (
    assign_edge_etag,
    check_edge_etag,
)
from core.lifecycle.schema import (
    T1_MUTATION_INVALIDATED,
    T1_MUTATION_SUPERSEDED,
    T7_EDGE_FIELD_MUTATION_TYPE,
    T7_EDGE_FIELD_STATUS,
    T7_EDGE_FIELD_VALIDITY,
    apply_v04_edge_defaults,
    validate_edge_v04_fields,
)


# Maximum chain length the walker tolerates before declaring cycle.
# Real chains in production should be tiny (a fact mutates rarely).
# A large value provides safety against accidental cycles caused by
# external mutation while still surfacing pathological loops loudly.
_MAX_CHAIN_LENGTH: int = 1024


def _edge_id(edge: dict) -> Optional[str]:
    """Edges in v0.3 wiki schema don't have a canonical ``id`` field —
    they're identified by ``(source_entity_id, target_id, type)``
    composite. PR-T7.A introduces a synthetic ``id`` field on every
    superseded-or-newer edge so the chain can link by reference.

    The id is stored under ``edge["id"]`` (lowercase, top-level) and
    only assigned when a chain operation needs to refer to this edge.
    Legacy edges that have never been superseded simply lack the
    field — that's fine because nothing points at them.
    """
    return edge.get("id") if isinstance(edge, dict) else None


def _ensure_edge_id(edge: dict) -> str:
    """Return the edge's id, assigning a fresh one if missing.

    Uses ``e_edge_<10-hex>`` shape consistent with the entity-id
    convention in ``core.graph_engine`` (``e_<type>_<10-hex>``).
    """
    eid = edge.get("id")
    if eid:
        return str(eid)
    new = f"e_edge_{uuid.uuid4().hex[:10]}"
    edge["id"] = new
    return new


# ─── supersede_edge ────────────────────────────────────────────────


def supersede_edge(
    old_edge: dict,
    new_fact: dict,
    supersede_ts: datetime,
    *,
    expected_old_etag: Optional[str] = None,
) -> tuple[dict, dict]:
    """Create the new edge from ``new_fact`` + mark ``old_edge`` as
    superseded by it.

    Args:
        old_edge: the existing edge being replaced. Must be a v0.4-
            shaped dict (run ``apply_v04_edge_defaults`` first if you
            loaded a raw v0.3 edge). Will be **mutated in place** —
            the caller's reference is updated so the wiki-write path
            picks up the new ``status`` + ``mutation_type``.
        new_fact: the replacing edge body. Same shape as ``old_edge``
            (relation dict from frontmatter). The new edge gets a
            fresh synthetic id + v0.4 defaults applied + validity
            window's ``from`` set to ``supersede_ts`` so the chain's
            temporal ordering is intact for replay.
        supersede_ts: UTC-aware ``datetime`` of the supersede event.
            Written into ``old_edge.status.superseded_at`` AND used
            as the new edge's ``validity.from``.
        expected_old_etag: **optimistic-concurrency token** (v0.5 G7,
            keyword-only). When set, the caller asserts that
            ``old_edge["etag"]`` equals this value at the moment of
            supersede. If the stored etag differs (a concurrent writer
            mutated the edge first), raises :class:`EtagMismatchError`
            BEFORE any mutation — the old edge is untouched and the
            caller can safely retry with the fresh head. Default
            ``None`` preserves byte-identical pre-G7 behaviour.

    Returns:
        ``(new_edge, old_edge)`` — both mutated. ``new_edge`` is a
        fresh dict (built from ``new_fact``), ``old_edge`` is the
        same object passed in. Both carry a freshly-assigned ``etag``
        field reflecting their post-mutation state.

    Raises:
        ValueError if either dict fails ``validate_edge_v04_fields``
        after mutation — defends against the caller passing partial
        v0.4 shapes that would produce an inconsistent chain.
        :class:`EtagMismatchError` if ``expected_old_etag`` is set
        and does not match ``old_edge["etag"]`` — the supersede did
        NOT happen, no fields were mutated.

    What this function does NOT do:
        - **No I/O.** Caller writes both edges back to the wiki.
        - **No cascade_remove.** Old edge's sources stay; only its
          ``status`` flips.
        - **No re-link of downstream chains.** If ``old_edge`` was
          itself already a chain link, the supersede is normal —
          its ``superseded_by`` simply gets overwritten with the
          new edge's id (the chain extends forward).
    """
    if not isinstance(old_edge, dict):
        raise ValueError(f"old_edge must be a dict, got {type(old_edge).__name__}")
    if not isinstance(new_fact, dict):
        raise ValueError(f"new_fact must be a dict, got {type(new_fact).__name__}")
    if not isinstance(supersede_ts, datetime):
        raise ValueError(
            f"supersede_ts must be datetime, got {type(supersede_ts).__name__}"
        )

    # v0.5 G7 — optimistic-concurrency check FIRST (before any mutation).
    # Raises EtagMismatchError on mismatch; old_edge stays untouched.
    if expected_old_etag is not None:
        check_edge_etag(old_edge, expected_old_etag)

    # Build the new edge. apply_v04_edge_defaults is idempotent so the
    # caller may pass either a raw v0.3 dict or a partially-v0.4 dict.
    new_edge: Dict[str, Any] = apply_v04_edge_defaults(new_fact)
    # Always assign a fresh id — the new edge is a distinct entity in
    # the chain even when its body matches an existing edge.
    new_id = f"e_edge_{uuid.uuid4().hex[:10]}"
    new_edge["id"] = new_id
    # Validity window's lower bound = the supersede moment (the new
    # fact was "true from this time forward"). Caller can override
    # later if they have a different valid_from semantic, but the
    # default keeps replay correct.
    validity = dict(new_edge.get(T7_EDGE_FIELD_VALIDITY) or {})
    validity["from"] = supersede_ts.isoformat()
    new_edge[T7_EDGE_FIELD_VALIDITY] = validity

    # Old edge mutations: must be a fully-defaulted v0.4 edge first
    # so the status / mutation_type writes don't lose other fields.
    defaulted_old = apply_v04_edge_defaults(old_edge)
    # Replace the old_edge dict in place by copying the defaulted
    # fields back. (We can't return a new dict for old_edge because
    # the caller likely holds a list reference to it from the wiki
    # frontmatter loader; mutating in place preserves that pointer.)
    for k, v in defaulted_old.items():
        old_edge[k] = v

    status = dict(old_edge.get(T7_EDGE_FIELD_STATUS) or {})
    status["active"] = False
    status["superseded_by"] = new_id
    status["superseded_at"] = supersede_ts.isoformat()
    old_edge[T7_EDGE_FIELD_STATUS] = status
    old_edge[T7_EDGE_FIELD_MUTATION_TYPE] = T1_MUTATION_SUPERSEDED

    # v0.5 G7 — assign fresh etag to BOTH edges so the next caller
    # has an up-to-date concurrency token. Assigned BEFORE validation
    # so the etag field is part of the validated shape.
    assign_edge_etag(new_edge)
    assign_edge_etag(old_edge)

    # Validate both — surface a partial-shape caller bug immediately.
    validate_edge_v04_fields(new_edge)
    validate_edge_v04_fields(old_edge)

    return new_edge, old_edge


# ─── walk_supersede_chain ──────────────────────────────────────────


def walk_supersede_chain(
    edge: dict,
    lookup: Callable[[str], Optional[dict]],
) -> List[dict]:
    """Walk forward through the supersede chain starting at ``edge``.

    Args:
        edge: a chain link (typically a superseded edge — the head of
            the chain returns just ``[edge]``).
        lookup: caller-supplied id-to-edge function. The chain is a
            linked list across the wiki, not held in one place, so
            the walker delegates the materialization to the caller
            (typically an in-memory dict the wiki-loader populated).

    Returns:
        Ordered list ``[edge, next, next_next, …, active_head]``.
        For an edge that has never been superseded, returns ``[edge]``.

    Raises:
        ValueError if a cycle is detected (an already-visited id
        appears again) or the chain exceeds ``_MAX_CHAIN_LENGTH``.
        Either case is a writer-side bug (``supersede_edge`` should
        prevent it; lookup-side corruption is the only path to a
        cycle here).
    """
    if not isinstance(edge, dict):
        raise ValueError(f"edge must be a dict, got {type(edge).__name__}")

    chain: List[dict] = [edge]
    seen: set[str] = set()
    eid = _edge_id(edge)
    if eid:
        seen.add(eid)

    current = edge
    for _ in range(_MAX_CHAIN_LENGTH):
        status = current.get(T7_EDGE_FIELD_STATUS) or {}
        next_id = status.get("superseded_by")
        if not next_id:
            return chain
        if next_id in seen:
            raise ValueError(
                f"supersede chain cycle detected at id={next_id!r}"
            )
        next_edge = lookup(next_id)
        if next_edge is None:
            # Dangling pointer — the chain points past the wiki's
            # known edges. Treat as end-of-chain rather than crash;
            # caller's wiki snapshot may simply lack the next link.
            return chain
        chain.append(next_edge)
        seen.add(next_id)
        current = next_edge

    raise ValueError(
        f"supersede chain exceeded max length {_MAX_CHAIN_LENGTH} — "
        f"likely cycle or pathological mutation"
    )


# ─── reconstruct_view_at ───────────────────────────────────────────


def reconstruct_view_at(
    head: dict,
    lookup: Callable[[str], Optional[dict]],
    t: datetime,
) -> Optional[dict]:
    """Replay primitive — return the edge whose ``validity`` window
    contained ``t``.

    Args:
        head: any link in the chain. The function walks forward
            via ``walk_supersede_chain`` to materialize the whole
            chain, then searches backward for the matching edge.
        lookup: same id-to-edge resolver passed to
            ``walk_supersede_chain``.
        t: UTC-aware ``datetime``.

    Returns:
        The first chain edge (in chain order) whose
        ``validity.from <= t < validity.to`` (where ``None`` on
        either bound means "open"), **excluding** edges with
        ``mutation_type == "invalidated"`` (CASCADE deletes are
        gone for replay even when historically present).

        Returns ``None`` if no chain edge matches.

    Why backward search: when the chain has multiple links, the
    earlier ones cover earlier intervals (by ``supersede_edge``
    contract: new edge's ``validity.from`` = supersede_ts). The
    most-recent edge whose interval contains ``t`` is the correct
    answer; iterating forward + returning the last match achieves
    that.
    """
    chain = walk_supersede_chain(head, lookup)
    match: Optional[dict] = None
    for link in chain:
        mt = link.get(T7_EDGE_FIELD_MUTATION_TYPE)
        if mt == T1_MUTATION_INVALIDATED:
            continue
        validity = link.get(T7_EDGE_FIELD_VALIDITY) or {}
        if _validity_contains(validity, t):
            match = link
    return match


def _validity_contains(validity: dict, t: datetime) -> bool:
    """``validity.from <= t < validity.to`` with ``None``-as-open
    semantics on both bounds. Matches the schema's "indefinite"
    convention.
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
    "supersede_edge",
    "walk_supersede_chain",
    "reconstruct_view_at",
    # Module-private constant exposed for the test that verifies the
    # length cap is enforced before walk_supersede_chain spins forever.
    "_MAX_CHAIN_LENGTH",
    # Convenience for callers that need to mint an id without going
    # through supersede_edge (e.g., seeding a fresh chain head).
    "_ensure_edge_id",
]
