"""Audit-log SQLite read helpers — the only side-channel for the
:func:`reconstruct_graph_at` primitive.

Extracted from the legacy single-file ``core/lifecycle/replay_graph.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

LOCK 4 (memo §7): these are the ONLY reads the snapshot depends on.
No wiki, no graph engine, no module-level cache — an audit_log JSON
dump alone is enough to reproduce the snapshot on any machine.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple


def _default_db_path() -> str:
    """Mirrors :func:`core.lifecycle.replay_audit._default_db_path`
    so reads and writes hit the same SQLite file."""
    env = (os.environ.get("JAMES_AUDIT_DB") or "").strip()
    if env:
        return env
    # core/lifecycle/replay_graph/db_read.py → repo root is 4 dirnames up.
    return os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            )
        ),
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


__all__ = ["_default_db_path", "_read_lifecycle_events"]
