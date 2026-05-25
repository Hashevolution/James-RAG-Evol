"""Turn-scoped scratch space — Cognitive Phase 3 PR-10a.

In-process working memory for cognitive stages. See
``docs/design/v0.3-working-memory.md`` for the full scope, ARCHITECTURE
§5.7.6 for the memory-scope hierarchy, and the §5.7.2 "Reflection state
— working memory only" invariant.

PR-10a ships the store and ``working_event()`` helper but **no call
sites**. PR-10b wires reflect / verify / planner / synth and hooks
``clear_turn()`` into ``engine.query()``'s finally block.

Two non-negotiable properties pin this module's design:

1. **Turn isolation** — every read filters by ``(session_id, turn_id)``
   at the method boundary. There is no ``keys_all_turns()`` and no
   way for one turn's stage to read another turn's slots, even from
   the same session.
2. **No on-disk persistence** — process restart wipes the store.
   Keeps the "cleared at turn end" invariant safe against operator
   restart races, and avoids conflating with episodic's SQLite
   persistence contract (PR-9a/PR-9b).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple


# ─── Storage layout ────────────────────────────────────────────────
# Outer key:  (session_id, turn_id)  — one bucket per turn.
# Bucket:     {"ts": last_write_unix_ts, "data": {role: {key: value}}}
#
# Nested dict (rather than flat (s, t, role, key) tuple) is chosen so
# clear_turn() is one O(1) pop on the outer dict instead of an O(N)
# prefix scan. The prune sweep runs sequentially through buckets and
# benefits from the same shape (last-write ts at bucket level).

_Bucket = Dict[str, Any]   # {"ts": float, "data": Dict[str, Dict[str, Any]]}


class WorkingMemory:
    """Process-wide turn-scoped scratch store.

    One instance per process; isolation is enforced at the method
    signature (every entry requires ``session_id`` + ``turn_id``).
    Backed by a plain dict and a single ``threading.Lock`` so the
    FastAPI thread-pool worker that runs ``rag_engine.query()`` can
    hand off to other threads (e.g. background trace writers) without
    a race on the bucket.

    The lock is held only across the dict mutation — not across the
    caller's stage logic — so contention stays bounded.
    """

    def __init__(self) -> None:
        self._buckets: Dict[Tuple[str, str], _Bucket] = {}
        self._lock = threading.Lock()

    # ─── write ──────────────────────────────────────────────────

    def set(
        self,
        *,
        session_id: str,
        turn_id:    str,
        role:       str,
        key:        str,
        value:      Any,
    ) -> None:
        """Store ``value`` under the (session, turn, role, key) tuple.

        Empty session_id / turn_id are silently ignored — same
        defensive posture as ``record_event()`` in episodic.py. A
        background job or test that forgot to bind the ContextVar
        stays inert rather than polluting the store with ``""`` keys.
        """
        if not session_id or not turn_id or not role or not key:
            return
        bucket_key = (session_id, turn_id)
        with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = {"ts": time.time(), "data": {}}
                self._buckets[bucket_key] = bucket
            else:
                bucket["ts"] = time.time()
            bucket["data"].setdefault(role, {})[key] = value

    # ─── read ───────────────────────────────────────────────────

    def get(
        self,
        *,
        session_id: str,
        turn_id:    str,
        role:       str,
        key:        str,
        default:    Any = None,
    ) -> Any:
        """Return the stored value, or ``default`` on miss.

        Missing session/turn/role/key all collapse to the same
        "return default" path so the caller does not have to
        distinguish "turn never wrote anything" from "turn wrote
        but not this role" from "role exists but not this key".
        """
        if not session_id or not turn_id or not role or not key:
            return default
        bucket_key = (session_id, turn_id)
        with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                return default
            role_slot = bucket["data"].get(role)
            if role_slot is None:
                return default
            return role_slot.get(key, default)

    def keys(
        self,
        *,
        session_id: str,
        turn_id:    str,
        role:       str,
    ) -> List[str]:
        """List the keys this turn has written under ``role``.

        Stable sort by insertion is NOT guaranteed — Python's dict
        keeps insertion order, but a caller relying on that is
        depending on a CPython implementation detail. Sort
        explicitly at the call site if order matters.
        """
        if not session_id or not turn_id or not role:
            return []
        bucket_key = (session_id, turn_id)
        with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                return []
            role_slot = bucket["data"].get(role)
            if role_slot is None:
                return []
            return list(role_slot.keys())

    # ─── lifecycle ──────────────────────────────────────────────

    def clear_turn(self, session_id: str, turn_id: str) -> int:
        """Drop every slot for ``(session_id, turn_id)``. Returns the
        number of (role, key) pairs removed — useful for trace /
        debug rows in PR-10b's engine.query() finally hookup.
        """
        if not session_id or not turn_id:
            return 0
        bucket_key = (session_id, turn_id)
        with self._lock:
            bucket = self._buckets.pop(bucket_key, None)
        if bucket is None:
            return 0
        return sum(len(s) for s in bucket["data"].values())

    def prune_idle_turns(self, *, max_age_seconds: int) -> int:
        """Sweep buckets whose last write is older than the threshold.

        Defensive against the rare case ``engine.query()``'s finally
        block did not run (OS-level process kill mid-request). The
        default age at the production callsite is 600s (10 min) —
        long enough that a slow LLM turn keeps its scratch, short
        enough that the dict stays small over a multi-day uptime.

        Returns the number of buckets removed (not slot pairs —
        the call is about reclaiming bucket space, not counting
        what was discarded).
        """
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be > 0")
        threshold = time.time() - max_age_seconds
        to_remove: List[Tuple[str, str]] = []
        with self._lock:
            for k, bucket in self._buckets.items():
                if bucket["ts"] < threshold:
                    to_remove.append(k)
            for k in to_remove:
                self._buckets.pop(k, None)
        return len(to_remove)

    # ─── introspection (debugging / tests) ──────────────────────

    def bucket_count(self) -> int:
        """Number of (session_id, turn_id) buckets currently held.
        Test helper / debug surface — not part of the public stage
        API. PR-10b's engine finally hook ignores this.
        """
        with self._lock:
            return len(self._buckets)


# ─── module-level singleton ─────────────────────────────────────────

_SINGLETON: Optional[WorkingMemory] = None
_SINGLETON_LOCK = threading.Lock()


def get_working_memory() -> WorkingMemory:
    """Process-wide singleton. Lazily constructed so importing the
    module does not allocate the dict until a stage actually writes.
    """
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = WorkingMemory()
    return _SINGLETON


def _clear_singleton_for_tests() -> None:
    """Test helper — drop the singleton so each test class starts
    from an empty store. Production code never calls this.
    """
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


# ─── wiring helper ──────────────────────────────────────────────────

def working_event(
    *,
    role:  str,
    key:   str,
    value: Any,
) -> bool:
    """Thin wiring helper for cognitive stages — PR-10b call sites.

    Reads ``(session_id, turn_id)`` from the
    ``core.observability.current_session`` ContextVar set by
    ``engine.query()`` at turn start (PR-9b infrastructure), then
    forwards to ``WorkingMemory.set()``.

    Returns ``True`` on success, ``False`` when called outside a
    tracked turn (silent no-op — same posture as
    ``record_event()`` in episodic.py). PR-10a has no call sites;
    PR-10b wires reflect / verify / planner / synth to it.
    """
    try:
        from core.observability import get_session_context
        session_id, turn_id = get_session_context()
    except Exception:
        return False
    if not session_id or not turn_id:
        return False
    try:
        get_working_memory().set(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            key=key,
            value=value,
        )
        return True
    except Exception:
        # Working memory is best-effort. A write failure must never
        # crash the live answer flow — same silent-skip posture as
        # the episodic helper.
        return False


__all__ = [
    "WorkingMemory",
    "get_working_memory",
    "working_event",
]
