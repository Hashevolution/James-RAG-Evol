"""T5.A — Lifecycle event taxonomy + emit helpers (write side).

This module is the write-side infrastructure for v0.4.2 T5's
**audit-only invariant** (``reconstruct_graph_at(t)`` will depend
solely on the audit_log row stream up to ``t`` — design memo §2 +
§4 invariant I1). Every lifecycle mutation that produces a
read-side graph state change must emit one audit_log row with
``event_type`` in :data:`LIFECYCLE_EVENT_TYPES` so the read-side
reconstruction can replay the mutation deterministically.

Design memo: ``docs/design/v0.4.2-t5-replayable-audit-graph.md``.

Decision LOCKs (memo §7):

* LOCK 1 — ``event_payload`` is a JSON string column on ``audit_log``,
  not a separate table. Keeps the migration to ``ALTER TABLE … ADD
  COLUMN`` (idempotent, no row rewrite).
* LOCK 2 — emit is **synchronous in-transaction**: ``emit_lifecycle_event``
  inserts on the calling thread; lifecycle code must call it before
  returning from the mutation site.

API surface
-----------

  * :data:`LIFECYCLE_EVENT_TYPES` — frozen tuple of every valid
    lifecycle event type.
  * :func:`emit_lifecycle_event` — write a lifecycle row to
    ``audit_log``. Never raises; returns ``True`` on insert,
    ``False`` on any failure (matches ``audit_bridge.mirror_to_audit_db``
    contract).
  * :func:`is_lifecycle_event` — boolean predicate for routing
    reads back to lifecycle replay vs reasoning trace replay.

Read-side (``reconstruct_graph_at(t)``) lands in PR-T5.B
(``core/lifecycle/replay_graph.py``).

Wiring (PR-T5.A.b or follow-up): every existing mutation site
listed in :data:`LIFECYCLE_EVENT_TYPES` calls
:func:`emit_lifecycle_event` exactly once per state change. The
release-gating "every mutation → audit row" invariant (memo §11
risk table) pins that contract.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional


# ─── Event-type taxonomy (LOCK with design memo §3) ────────────────
#
# Every lifecycle mutation that the read-side replay must observe to
# reconstruct graph state at an arbitrary ``t`` must use one of these
# event types. The names match the design memo §3 table 1:1.
#
# Adding a new entry here is a public API change: the migration
# script does not need to know the entries (event_type is a free
# TEXT column), but ``reconstruct_graph_at`` (PR-T5.B) dispatches
# on these strings, and every entry must have a corresponding
# decoder there.

# T7 — supersede chain mutations
EVT_SUPERSEDE_EDGE_CREATED  = "lifecycle.supersede.edge_created"
EVT_SUPERSEDE_CHAIN_EXTENDED = "lifecycle.supersede.chain_extended"

# T6 — causality chain cascade
EVT_CASCADE_INVALIDATE = "lifecycle.cascade.invalidate"

# T1 — temporal validity expiration
EVT_T1_EXPIRATION_CASCADE = "lifecycle.t1.expiration_cascade"

# T2 — deterministic contradiction arbitration
EVT_T2_DISPATCH_CONTRADICTION = "lifecycle.t2.dispatch_contradiction"

# T2.D — ingestion-time pre-merge contradiction routing
EVT_T2D_INGEST_DISPATCH = "lifecycle.t2d.ingest_dispatch"

# Migration marker — rows emitted by ``migrate_v042_replay_audit.py``
# when the historic wiki state was snapshot-reverse-derived because
# the original mutation predates audit_log capture. Replay treats
# these as a one-shot bootstrap event.
EVT_BACKFILL_SNAPSHOT = "lifecycle.backfill.snapshot"


LIFECYCLE_EVENT_TYPES: tuple[str, ...] = (
    EVT_SUPERSEDE_EDGE_CREATED,
    EVT_SUPERSEDE_CHAIN_EXTENDED,
    EVT_CASCADE_INVALIDATE,
    EVT_T1_EXPIRATION_CASCADE,
    EVT_T2_DISPATCH_CONTRADICTION,
    EVT_T2D_INGEST_DISPATCH,
    EVT_BACKFILL_SNAPSHOT,
)


_LIFECYCLE_PREFIX = "lifecycle."


def is_lifecycle_event(event_type: Optional[str]) -> bool:
    """True iff ``event_type`` is one of :data:`LIFECYCLE_EVENT_TYPES`.

    The check is exact-equality against the registered set rather
    than a ``startswith("lifecycle.")`` prefix, so a typo in a
    mutation site (``lifecycle.cascadx.invalidate``) does not
    silently slip into the replay stream.
    """
    return isinstance(event_type, str) and event_type in LIFECYCLE_EVENT_TYPES


# ─── DB path resolution (matches audit_bridge) ──────────────────────


def _default_db_path() -> str:
    """Resolve the production audit_log SQLite path.

    Mirrors the resolution order used by ``audit_bridge`` so a
    lifecycle event lands in the same database as the reasoning
    rows — replay reads them back from one place.
    """
    env = (os.environ.get("JAMES_AUDIT_DB") or "").strip()
    if env:
        return env
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "audit.db",
    )


# ─── emit (write side) ─────────────────────────────────────────────


def emit_lifecycle_event(
    event_type: str,
    payload: Dict[str, Any],
    *,
    user_role: str = "system",
    timestamp: Optional[str] = None,
    db_path: Optional[str] = None,
    retention_class: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> bool:
    """Insert one ``audit_log`` row with the given lifecycle
    ``event_type`` + JSON-encoded ``payload``.

    Args:
        event_type: one of :data:`LIFECYCLE_EVENT_TYPES`. Validated.
        payload: any JSON-serializable dict describing the mutation
            (edge ids, ``mutation_type``, validity window, etc.).
            Encoded with ``ensure_ascii=False`` so Korean / mixed
            text round-trips without escape clutter.
        user_role: who triggered the mutation. Defaults to
            ``"system"`` because most lifecycle mutations originate
            from CASCADE / EVENT machinery, not from an HTTP role.
        timestamp: ISO-8601 string. Defaults to ``datetime.now()``.
        db_path: optional override. Production code omits it.
        retention_class: **v0.5 G4** — optional machine-readable
            retention tag. When set, stamped into the row's
            ``event_payload`` JSON under ``retention_class`` so
            ``core.lifecycle.retention.pending_retention_review`` can
            find rows past their window. Must be a value accepted by
            :func:`core.lifecycle.retention.validate_retention_class`
            — malformed values cause the emit to return ``False``
            (safer than silently stamping garbage).

    Returns:
        ``True`` on insert, ``False`` on any failure. **Never raises**
        — matches ``audit_bridge.mirror_to_audit_db`` so a lifecycle
        bug cannot block the cascade or supersede path.

    Notes:
        * The ``audit_log`` schema must have ``event_type`` and
          ``event_payload`` columns (``migrate_v042_replay_audit.py``
          adds them). On a pre-migration DB this function returns
          ``False`` instead of crashing.
        * ``endpoint`` is set to ``event_type`` so existing operator
          audit views (``/admin/audit/list``) surface lifecycle rows
          without a separate filter.
        * **No schema migration** is needed for ``retention_class`` —
          it lives inside the ``event_payload`` JSON column.
    """
    if not is_lifecycle_event(event_type):
        return False
    if not isinstance(payload, dict):
        return False

    # v0.5 G4 — validate + stamp retention_class into the payload.
    if retention_class is not None:
        # Local import to avoid a circular at module-import time
        # (retention.py imports nothing from replay_audit.py — this
        # keeps the dependency one-way, even though replay_audit only
        # consults retention.validate at runtime).
        from core.lifecycle.retention import validate_retention_class
        if not validate_retention_class(retention_class):
            return False
        # Copy to avoid mutating the caller's dict.
        payload = dict(payload)
        payload["retention_class"] = retention_class

    # v0.5 G1.a — resolve + stamp tenant_id into the payload.
    # Resolution order: explicit kwarg → with_tenant_id() override →
    # JAMES_TENANT_ID env. When `is_tenant_isolation_enforced()` is
    # true AND resolution yields no tenant_id, emit fails fast
    # (returns False without inserting) — keeps a multi-tenant
    # deploy from accidentally writing tenant-anonymous rows.
    from core.lifecycle.tenant import (
        current_tenant_id,
        is_tenant_isolation_enforced,
    )
    resolved_tenant = (
        tenant_id if tenant_id is not None else current_tenant_id()
    )
    if is_tenant_isolation_enforced() and not resolved_tenant:
        return False
    if resolved_tenant:
        # Defensive copy if we haven't already (the G4 branch above
        # may already have copied). dict() on a dict is cheap; the
        # invariant is "never mutate the caller's dict in place".
        payload = dict(payload)
        payload["tenant_id"] = resolved_tenant

    ts = timestamp or datetime.now().isoformat()
    try:
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return False

    path = db_path or _default_db_path()
    try:
        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, user_role, endpoint, query, answer, "
                " graph_paths, blocked, security_event, elapsed_sec, "
                " ip_address, event_type, event_payload) "
                "VALUES (?, ?, ?, NULL, NULL, NULL, 0, NULL, NULL, NULL, ?, ?)",
                (ts, user_role, event_type, event_type, payload_json),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False


__all__ = [
    "LIFECYCLE_EVENT_TYPES",
    "EVT_SUPERSEDE_EDGE_CREATED",
    "EVT_SUPERSEDE_CHAIN_EXTENDED",
    "EVT_CASCADE_INVALIDATE",
    "EVT_T1_EXPIRATION_CASCADE",
    "EVT_T2_DISPATCH_CONTRADICTION",
    "EVT_T2D_INGEST_DISPATCH",
    "EVT_BACKFILL_SNAPSHOT",
    "is_lifecycle_event",
    "emit_lifecycle_event",
]
