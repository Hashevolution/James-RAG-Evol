"""T5.B — read-side ``reconstruct_graph_at(t)`` primitive.

This module is the read-side counterpart of
:mod:`core.lifecycle.replay_audit` (T5.A). It folds the lifecycle
event stream from ``audit_log`` into a deterministic
:class:`GraphSnapshot` for any cutoff time ``t``. Together the two
modules realise the v0.4.2 T5 audit-only invariant (design memo §2 +
§4 I1)::

    ∀ t. reconstruct_graph_at(t) =
        replay of every lifecycle event row whose timestamp ≤ t.

Decision LOCKs (memo §7):

* LOCK 4 — ``reconstruct_graph_at`` is a **pure function**: no DB
  write, no module-level cache mutation, no global state read
  beyond the audit_log SELECT. Determinism is the whole point —
  the same ``(t, audit_log_path)`` pair always produces the same
  snapshot.
* LOCK 5 — the audit-only invariant (I1) is pinned by a contract
  test that monkeypatches the DB read and asserts every byte the
  snapshot depends on came through it (PR-T5.D).

Why pure event-log fold (not DB scan)
-------------------------------------
The whole point of T5 is that an operator can ship the audit_log
to a third party — no wiki snapshot, no graph dump — and the third
party can reproduce the graph state at any past ``t``. That is
"replay invariant" in the corpus-retrieval analysis (PR #712 §6).
If reconstruction touches the wiki on disk, the invariant collapses.

Out of scope for this PR
------------------------
* Mutation-site wiring (T1/T2/T2.D/T6/T7 → ``emit_lifecycle_event``).
  Lands in T5.A.b or T5.B follow-up. Until wiring happens the
  production audit_log has no lifecycle rows, so live integration
  tests stay synthetic (this module's tests INSERT events directly).
* Live-graph equality invariant (I4) against the on-disk wiki.
  PR-T5.D pins it once mutation wiring is in.
* Cross-chain consistency vs :func:`reconstruct_view_at`. PR-T5.C.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from core.lifecycle.replay_audit import (
    EVT_BACKFILL_SNAPSHOT,
    EVT_CASCADE_INVALIDATE,
    EVT_SUPERSEDE_CHAIN_EXTENDED,
    EVT_SUPERSEDE_EDGE_CREATED,
    EVT_T1_EXPIRATION_CASCADE,
    EVT_T2_DISPATCH_CONTRADICTION,
    EVT_T2D_INGEST_DISPATCH,
    LIFECYCLE_EVENT_TYPES,
    is_lifecycle_event,
)


# ─── snapshot dataclass (design memo §4) ───────────────────────────


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


# Empty snapshot — returned when the audit_log has no lifecycle rows
# (e.g. pre-migration DB, pre-wiring production DB).
def _empty_snapshot(t: datetime) -> GraphSnapshot:
    return GraphSnapshot(
        edges={}, supersede_chains={}, invalidated_ids=frozenset(),
        replayed_at=t, event_count=0,
    )


# ─── per-event-type handlers (private) ─────────────────────────────
#
# Each handler takes the *mutable* working state (edges dict,
# chains dict, invalidated set) and the event payload, and folds the
# event in place. The dispatch loop calls them in audit_log
# insertion order — they must be associative + idempotent under
# repeat replay (the same audit_log JSON read twice produces the
# same snapshot).


def _h_supersede_edge_created(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, List[str]],
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
    chains: Dict[str, List[str]],
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
    chains: Dict[str, List[str]],
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
    chains: Dict[str, List[str]],
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
    chains: Dict[str, List[str]],
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
    chains: Dict[str, List[str]],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    # T2.D pre-merge dispatch — same rationale as T2: the actual
    # mutation (CASCADE or EVENT) emits its own follow-up event.
    return


def _h_backfill_snapshot(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, List[str]],
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
}


# Sanity: every taxonomy entry has a handler. A missing handler in a
# CI build would be a Decision LOCK 4 (pure function) violation
# because the snapshot would non-deterministically drop events.
assert set(_HANDLERS) == set(LIFECYCLE_EVENT_TYPES), (
    "every LIFECYCLE_EVENT_TYPES entry must have a handler in _HANDLERS"
)


# ─── DB read (the only side-channel for the snapshot) ──────────────


def _default_db_path() -> str:
    """Mirrors :func:`core.lifecycle.replay_audit._default_db_path`
    so reads and writes hit the same SQLite file."""
    env = (os.environ.get("JAMES_AUDIT_DB") or "").strip()
    if env:
        return env
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "audit.db",
    )


def _read_lifecycle_events(
    db_path: str,
    t: datetime,
    include: Optional[Tuple[str, ...]],
) -> List[Tuple[str, str]]:
    """SELECT lifecycle rows with timestamp ≤ t, ordered by insertion.

    Returns a list of ``(event_type, event_payload_json)``. Sorted by
    ``id`` (the audit_log primary key) so events ingested at the same
    timestamp string still replay in append order.

    Notes:
        * Pre-migration DBs (no ``event_type`` column) → empty list.
          The function reads ``PRAGMA table_info`` first and returns
          early — this is the same defensive pattern
          ``emit_lifecycle_event`` uses on the write side.
        * The function never raises. On any sqlite error it returns
          an empty list; the snapshot becomes the empty snapshot,
          which is the safe degenerate case.
    """
    try:
        conn = sqlite3.connect(db_path)
    except Exception:
        return []
    try:
        # Detect a pre-migration schema and bail.
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(audit_log)"
        ).fetchall()}
        if "event_type" not in cols or "event_payload" not in cols:
            return []
        cutoff = t.isoformat()
        if include:
            placeholders = ",".join("?" * len(include))
            rows = conn.execute(
                f"SELECT event_type, event_payload "
                f"FROM audit_log "
                f"WHERE event_type IN ({placeholders}) "
                f"AND timestamp <= ? "
                f"ORDER BY id ASC",
                (*include, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT event_type, event_payload "
                "FROM audit_log "
                "WHERE event_type IS NOT NULL "
                "AND timestamp <= ? "
                "ORDER BY id ASC",
                (cutoff,),
            ).fetchall()
        return [(et, ep or "") for et, ep in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ─── public primitive ──────────────────────────────────────────────


def reconstruct_graph_at(
    t: datetime,
    *,
    audit_log_path: Optional[str] = None,
    include_event_types: Optional[Tuple[str, ...]] = None,
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

    Returns:
        :class:`GraphSnapshot` — deterministic projection of the
        replayed event stream.

    Pure-function contract (LOCK 4): the only side-channel is the
    audit_log SELECT. The function does not read the wiki, the
    knowledge_tracker, the graph engine, or any other module's
    state — so an audit_log JSON dump alone is enough to reproduce
    the snapshot on any machine.
    """
    path = audit_log_path or _default_db_path()
    rows = _read_lifecycle_events(path, t, include_event_types)

    edges: Dict[str, Dict[str, Any]] = {}
    chains: Dict[str, List[str]] = {}
    invalidated: set = set()
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
    )


__all__ = [
    "GraphSnapshot",
    "reconstruct_graph_at",
]
