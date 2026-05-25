"""Session-scoped event store — Cognitive Phase 3 PR-9a.

The session tier of the ``docs/ARCHITECTURE.md §5.7.6`` scope hierarchy.
Holds the intra-turn reasoning trail (plan / reflect / verify / synth /
…) in a form the *next* turn in the same session can read online.

This module ships infrastructure only — no call sites in the cognitive
middleware reach ``EpisodicMemory.record`` yet. PR-9b adds the wiring.
The split mirrors the L0 / L1 pattern the backends track used
(PR #283 ships infra; PR #284 wires the call sites).

Two invariants from §5.7.6:

1. **Writes never escape upward.** Every read filters on
   ``WHERE session_id = ?`` at the SQL layer. The store exposes no
   "list all sessions" read on the user-facing path — that's an
   admin-only API in PR-9b.
2. **Session end clears.** A new ``session_id`` is a clean episodic
   slate; ``clear_session`` removes exactly that session's rows.
   ``prune_older_than`` is the retention sweep (default 7 days, matches
   ``JAMES_TRACE_RETENTION_DAYS`` from Axis 3 PR #84).

Design doc: ``docs/design/v0.3-episodic-memory.md``.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ─── Stage taxonomy ────────────────────────────────────────────────
# Validated at record() time so a typo at the wiring site (PR-9b)
# fails loudly during dev rather than silently bypassing readers.
# Mirrors the cognitive middleware stages in
# docs/ARCHITECTURE.md §5.7.2.
KNOWN_STAGES = frozenset({
    "retrieve",
    "plan",
    "reflect",
    "verify",
    "synth",
    "tool_call",
    "error",
})


# ─── Summary truncation ────────────────────────────────────────────
# Matches the audit_log's truncate_summary cap (240 chars). Long
# reasoning summaries fall outside the episodic working set — the
# forensic record in audit_log carries the full text.
MAX_SUMMARY_CHARS = 240


# ─── Default DB location ───────────────────────────────────────────
# Separate file from james_data.db (workspace-scoped) and
# james_audit.db (forensic, retained). Episodic prunes; mixing
# retention policies in one file forces the wrong invariant to win.
try:
    from config import BASE_DIR
    DEFAULT_EPISODIC_DB = os.path.join(BASE_DIR, "james_episodic.db")
except ImportError:
    DEFAULT_EPISODIC_DB = "./james_episodic.db"


@dataclass(frozen=True)
class EpisodicEvent:
    """One reasoning event recorded inside a session.

    Field shape matches docs/design/v0.3-episodic-memory.md §"Schema".
    The frozen=True attribute pins the contract — consumers don't
    mutate events after read; if reflection needs to revise a verdict
    it appends a new event rather than editing the old one (mirrors
    the append-only discipline of audit_log).
    """

    event_id: str
    session_id: str
    turn_id: str
    ts: float
    stage: str
    summary: str
    score: float = 0.0
    extras: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""


def _new_event_id() -> str:
    """Sortable + globally-unique id. ULID-shaped (timestamp-prefix +
    randomness) without pulling in an external dependency:

      ``{millis:013d}-{hex16}``

    The 13-digit zero-padded millisecond timestamp keeps the string
    sortable through the year 2286, matching ULID's design horizon.
    The 16-char random hex (64 bits) is enough collision-resistance
    for the per-session event volume the design anticipates
    (~20 events × ~10 turns × ~thousands of sessions ≈ 10^5 events
    per workspace, well within 2^64).
    """
    return f"{int(time.time() * 1000):013d}-{secrets.token_hex(8)}"


def _truncate(s: str) -> str:
    """Cap summary at MAX_SUMMARY_CHARS. Non-strings coerced via str()
    so a misuse at the call site doesn't crash the writer.
    """
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    if len(s) <= MAX_SUMMARY_CHARS:
        return s
    return s[:MAX_SUMMARY_CHARS]


class EpisodicMemory:
    """One instance per process. Scoped reads/writes happen via
    ``session_id`` arguments rather than per-session instances — same
    pattern as ``MemoryStore`` in store.py, and the session_id stays
    the only namespace key so a future v0.4 multi-process topology
    remains forward-compatible.

    Initialization is idempotent: re-running on an existing DB
    creates no schema drift, opens the existing file.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or DEFAULT_EPISODIC_DB
        Path(os.path.dirname(self._db_path) or ".").mkdir(
            parents=True, exist_ok=True
        )
        self._init_schema()

    # ─── lifecycle ──────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        # WAL keeps concurrent reads safe with one writer — the v0.3
        # single-process default. Multi-process topology (v0.4) needs
        # a different store; the schema/API stay forward-compatible
        # because session_id is the only namespace key.
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            # Some filesystems (network mounts) refuse WAL; the rest
            # of the store still works under rollback-journal mode,
            # so this is best-effort.
            pass
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodic_events (
                    event_id    TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    turn_id     TEXT NOT NULL,
                    ts          REAL NOT NULL,
                    stage       TEXT NOT NULL,
                    summary     TEXT,
                    score       REAL DEFAULT 0.0,
                    extras_json TEXT,
                    trace_id    TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS ix_episodic_session_ts
                    ON episodic_events(session_id, ts DESC);
                CREATE INDEX IF NOT EXISTS ix_episodic_turn
                    ON episodic_events(session_id, turn_id);
                CREATE INDEX IF NOT EXISTS ix_episodic_trace
                    ON episodic_events(trace_id);
                """
            )

    # ─── write ──────────────────────────────────────────────────

    def record(
        self,
        *,
        session_id: str,
        turn_id: str,
        stage: str,
        summary: str,
        score: float = 0.0,
        extras: Optional[Dict[str, Any]] = None,
        trace_id: str = "",
    ) -> str:
        """Append one event. Returns the assigned ``event_id``.

        Validates ``stage`` against KNOWN_STAGES (typo → ValueError).
        Truncates ``summary`` to MAX_SUMMARY_CHARS. Non-string
        ``summary`` is coerced rather than rejected so a misused
        wiring point doesn't crash the writer.
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be a non-empty str")
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("turn_id must be a non-empty str")
        if stage not in KNOWN_STAGES:
            raise ValueError(
                f"unknown stage {stage!r}; "
                f"known stages: {sorted(KNOWN_STAGES)}"
            )

        event_id = _new_event_id()
        truncated = _truncate(summary)
        extras_json = json.dumps(extras or {}, ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO episodic_events "
                "(event_id, session_id, turn_id, ts, stage, summary, "
                "score, extras_json, trace_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    session_id,
                    turn_id,
                    time.time(),
                    stage,
                    truncated,
                    float(score),
                    extras_json,
                    trace_id or "",
                ),
            )
        return event_id

    # ─── read ───────────────────────────────────────────────────

    def _row_to_event(self, row: sqlite3.Row) -> EpisodicEvent:
        try:
            extras = json.loads(row["extras_json"]) if row["extras_json"] else {}
        except (json.JSONDecodeError, TypeError):
            # A malformed extras_json row shouldn't take the reader
            # down — the rest of the event is still useful for
            # debugging. Surface as empty dict; the dev-time path
            # has already passed JSON validation via json.dumps.
            extras = {}
        return EpisodicEvent(
            event_id=row["event_id"],
            session_id=row["session_id"],
            turn_id=row["turn_id"],
            ts=float(row["ts"]),
            stage=row["stage"],
            summary=row["summary"] or "",
            score=float(row["score"] or 0.0),
            extras=extras,
            trace_id=row["trace_id"] or "",
        )

    def events_for_turn(
        self,
        session_id: str,
        turn_id: str,
    ) -> List[EpisodicEvent]:
        """Every event in one turn, sorted chronologically by event_id
        (the ULID-shaped id sorts by ts millis as a side-effect).
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM episodic_events "
                "WHERE session_id = ? AND turn_id = ? "
                "ORDER BY event_id ASC",
                (session_id, turn_id),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def recent_events(
        self,
        session_id: str,
        *,
        limit: int = 20,
        stages: Tuple[str, ...] = (),
    ) -> List[EpisodicEvent]:
        """The last ``limit`` events in this session, optionally
        filtered by stage. Default 20 ≈ 5 turns of reasoning. Returned
        in chronological order (oldest first) so the next-turn cognitive
        consumer sees the trail in the order it happened.
        """
        if limit <= 0:
            return []

        sql = (
            "SELECT * FROM ("
            "SELECT * FROM episodic_events WHERE session_id = ? "
        )
        params: List[Any] = [session_id]
        if stages:
            placeholders = ",".join("?" for _ in stages)
            sql += f"AND stage IN ({placeholders}) "
            params.extend(stages)
        # Pull the most recent N rows in reverse-chrono via the index,
        # then flip to chronological in the outer SELECT.
        sql += (
            "ORDER BY ts DESC LIMIT ?"
            ") ORDER BY ts ASC"
        )
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_by_trace_id(
        self,
        session_id: str,
        trace_id: str,
    ) -> List[EpisodicEvent]:
        """Look up every event written under one trace_id within this
        session. Cross-session lookup deliberately disallowed — the
        admin debugging endpoint in PR-9b crosses sessions through a
        separate API that the PolicyEngine gates.
        """
        if not trace_id:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM episodic_events "
                "WHERE session_id = ? AND trace_id = ? "
                "ORDER BY event_id ASC",
                (session_id, trace_id),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    # ─── lifecycle ──────────────────────────────────────────────

    def clear_session(self, session_id: str) -> int:
        """Delete every row for this session. Returns rows removed.
        Called when the frontend cycles a session via ``newSession()``
        (chat.js, PR #302) and as part of the retention sweep.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM episodic_events WHERE session_id = ?",
                (session_id,),
            )
            return cur.rowcount

    def prune_older_than(self, *, max_age_days: int) -> int:
        """Retention sweep. Default at the call site is 7 days,
        matching ``JAMES_TRACE_RETENTION_DAYS`` (Axis 3 PR #84).
        Returns rows removed.
        """
        if max_age_days <= 0:
            raise ValueError("max_age_days must be > 0")
        threshold = time.time() - (max_age_days * 86400)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM episodic_events WHERE ts < ?",
                (threshold,),
            )
            return cur.rowcount


# ─── module-level singleton + wiring helper (PR-9b) ─────────────────
# Cognitive stages (planner / reflect / verify / synth) share a single
# EpisodicMemory instance so they reuse the same SQLite connection
# pool / schema-init pass. Pattern mirrors `get_planner()` in
# core/reasoning/planner.py.

import threading as _threading

_SINGLETON: Optional[EpisodicMemory] = None
_SINGLETON_LOCK = _threading.Lock()


def get_episodic_memory() -> EpisodicMemory:
    """Process-wide singleton. Lazily constructs on first call so import
    of this module doesn't touch the filesystem until a stage actually
    records something.
    """
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = EpisodicMemory()
    return _SINGLETON


def _clear_singleton_for_tests() -> None:
    """Test helper. Production code never calls this."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


def record_event(
    *,
    stage:    str,
    summary:  str,
    score:    float = 0.0,
    extras:   Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Thin wiring helper for cognitive stages.

    Reads ``(session_id, turn_id)`` from the
    ``core.observability.current_session`` ContextVar set by
    ``engine.query()`` at turn start, plus ``trace_id`` from the
    existing trace ContextVar, then forwards to
    ``EpisodicMemory.record()``.

    Returns the new ``event_id`` on success, ``None`` on any failure
    (no session_id bound, unknown stage, store unavailable). Best-effort
    by design: a stage failing to write episodic must never propagate
    into the reasoning loop or fail the live query.

    Stage typos are caught loudly only when KNOWN_STAGES validation
    fires inside ``record()``; here the exception is swallowed and
    logged as a print to stderr so the operator notices on the trace
    console.
    """
    try:
        from core.observability import get_session_context, get_trace_id
        session_id, turn_id = get_session_context()
        if not session_id or not turn_id:
            return None
        return get_episodic_memory().record(
            session_id=session_id,
            turn_id=turn_id,
            stage=stage,
            summary=summary,
            score=score,
            extras=extras or {},
            trace_id=get_trace_id(),
        )
    except Exception as e:
        # Swallow — episodic is best-effort. Operator sees the gap
        # via missing replay rows, not via crashed queries.
        try:
            import sys
            print(f"[episodic] record_event({stage}) failed: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
        except Exception:
            pass
        return None


__all__ = [
    "EpisodicEvent",
    "EpisodicMemory",
    "KNOWN_STAGES",
    "MAX_SUMMARY_CHARS",
    "DEFAULT_EPISODIC_DB",
    "get_episodic_memory",
    "record_event",
]
