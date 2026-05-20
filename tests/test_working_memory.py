"""Cognitive Phase 3 PR-10a — turn-scoped working memory unit tests.

Covers the 10-item test plan in
``docs/design/v0.3-working-memory.md`` §"Test plan". The store is
in-process plain-dict, so every test creates a fresh
``WorkingMemory()`` instance to stay hermetic and parallel-safe.

PR-10b adds the wiring tests that exercise the helper inside the
cognitive stages.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.memory.working import (  # noqa: E402
    WorkingMemory,
    get_working_memory,
    working_event,
    _clear_singleton_for_tests,
)
from core.observability import (  # noqa: E402
    set_session_context,
)


# ─── 1. round-trip + isolation ──────────────────────────────────────


class RoundTripTests(unittest.TestCase):

    def test_set_get_round_trip(self):
        """Plan item 1 — what set() wrote, get() returns."""
        wm = WorkingMemory()
        wm.set(session_id="s1", turn_id="t1",
               role="reflect.draft", key="text", value="hello")
        self.assertEqual(
            wm.get(session_id="s1", turn_id="t1",
                   role="reflect.draft", key="text"),
            "hello",
        )

    def test_get_default_on_miss(self):
        """Plan item 2 — missing slot returns default."""
        wm = WorkingMemory()
        # miss at every level: turn / role / key
        self.assertIsNone(wm.get(session_id="s1", turn_id="t1",
                                  role="x", key="y"))
        self.assertEqual(
            wm.get(session_id="s1", turn_id="t1",
                   role="x", key="y", default="fallback"),
            "fallback",
        )

    def test_overwrite_replaces_value(self):
        """A second set() to the same (s, t, role, key) replaces the
        earlier value — not a list append. Stages reflect / verify
        rely on this for "current best draft" semantics.
        """
        wm = WorkingMemory()
        wm.set(session_id="s1", turn_id="t1",
               role="r", key="k", value="v1")
        wm.set(session_id="s1", turn_id="t1",
               role="r", key="k", value="v2")
        self.assertEqual(
            wm.get(session_id="s1", turn_id="t1", role="r", key="k"),
            "v2",
        )


class IsolationTests(unittest.TestCase):
    """The strictest invariant — turn isolation. A turn must never
    see another turn's slots, even from the same session.
    """

    def test_turn_isolation(self):
        """Plan item 3 — same session, different turn → no leak."""
        wm = WorkingMemory()
        wm.set(session_id="s1", turn_id="t1",
               role="r", key="k", value="t1_value")
        # Read under t2 — same session, different turn
        out = wm.get(session_id="s1", turn_id="t2",
                     role="r", key="k", default=None)
        self.assertIsNone(out,
            "turn isolation is the strictest invariant — a stage in "
            "turn t2 must NOT see turn t1's working slots")

    def test_session_isolation(self):
        """Plan item 4 — same turn_id literal under different
        session_id are independent."""
        wm = WorkingMemory()
        wm.set(session_id="sA", turn_id="t1",
               role="r", key="k", value="A_value")
        wm.set(session_id="sB", turn_id="t1",
               role="r", key="k", value="B_value")
        self.assertEqual(
            wm.get(session_id="sA", turn_id="t1", role="r", key="k"),
            "A_value",
        )
        self.assertEqual(
            wm.get(session_id="sB", turn_id="t1", role="r", key="k"),
            "B_value",
        )


# ─── 2. keys() + clear_turn() + prune ───────────────────────────────


class IntrospectionTests(unittest.TestCase):

    def test_keys_lists_only_role_slots(self):
        """Plan item 5 — keys(role) returns the keys this turn wrote
        under that role, not other roles'."""
        wm = WorkingMemory()
        wm.set(session_id="s", turn_id="t",
               role="reflect.draft", key="text", value="x")
        wm.set(session_id="s", turn_id="t",
               role="reflect.draft", key="latency_ms", value=42)
        wm.set(session_id="s", turn_id="t",
               role="verify.claims", key="c1", value="claim 1")
        out = wm.keys(session_id="s", turn_id="t",
                      role="reflect.draft")
        self.assertEqual(set(out), {"text", "latency_ms"})

    def test_keys_returns_empty_when_role_absent(self):
        wm = WorkingMemory()
        self.assertEqual(
            wm.keys(session_id="s", turn_id="t", role="missing"),
            [],
        )


class ClearTurnTests(unittest.TestCase):

    def test_clear_turn_removes_only_that_turn(self):
        """Plan item 6 — clear_turn drops exactly that turn's slots."""
        wm = WorkingMemory()
        # Populate two turns under the same session
        wm.set(session_id="s", turn_id="t1",
               role="r", key="k1", value="t1k1")
        wm.set(session_id="s", turn_id="t1",
               role="r", key="k2", value="t1k2")
        wm.set(session_id="s", turn_id="t2",
               role="r", key="k1", value="t2k1")

        removed = wm.clear_turn("s", "t1")
        self.assertEqual(removed, 2,
            "clear_turn returns the number of (role, key) pairs removed")

        # t1 gone
        self.assertIsNone(wm.get(session_id="s", turn_id="t1",
                                  role="r", key="k1"))
        # t2 untouched
        self.assertEqual(
            wm.get(session_id="s", turn_id="t2", role="r", key="k1"),
            "t2k1",
        )

    def test_clear_turn_missing_is_noop(self):
        wm = WorkingMemory()
        self.assertEqual(wm.clear_turn("never", "wrote"), 0)


class PruneTests(unittest.TestCase):

    def test_prune_removes_idle_turns_only(self):
        """Plan item 7 — buckets whose last write is older than the
        threshold are removed; recent buckets survive."""
        wm = WorkingMemory()
        # Write to two turns
        wm.set(session_id="s", turn_id="old",
               role="r", key="k", value="x")
        # Manually backdate the "old" bucket's ts
        with wm._lock:
            wm._buckets[("s", "old")]["ts"] = time.time() - 3600
        wm.set(session_id="s", turn_id="fresh",
               role="r", key="k", value="y")

        removed = wm.prune_idle_turns(max_age_seconds=600)
        self.assertEqual(removed, 1)
        # fresh survives
        self.assertEqual(
            wm.get(session_id="s", turn_id="fresh",
                   role="r", key="k"),
            "y",
        )
        # old is gone
        self.assertIsNone(wm.get(session_id="s", turn_id="old",
                                  role="r", key="k"))

    def test_prune_zero_or_negative_raises(self):
        wm = WorkingMemory()
        with self.assertRaises(ValueError):
            wm.prune_idle_turns(max_age_seconds=0)
        with self.assertRaises(ValueError):
            wm.prune_idle_turns(max_age_seconds=-5)


# ─── 3. thread safety (sanity) ──────────────────────────────────────


class ThreadSafetyTests(unittest.TestCase):
    """Sanity-level concurrency check — concurrent writes from two
    threads do not raise and do not lose data. Full stress testing
    is out of scope for v0.3."""

    def test_concurrent_writes_no_data_loss(self):
        wm = WorkingMemory()
        N = 200

        def writer(prefix: str):
            for i in range(N):
                wm.set(session_id="s", turn_id="t",
                       role=prefix, key=f"k{i}", value=i)

        ta = threading.Thread(target=writer, args=("A",))
        tb = threading.Thread(target=writer, args=("B",))
        ta.start(); tb.start()
        ta.join();  tb.join()

        # Each role should have N keys
        self.assertEqual(
            len(wm.keys(session_id="s", turn_id="t", role="A")),
            N,
        )
        self.assertEqual(
            len(wm.keys(session_id="s", turn_id="t", role="B")),
            N,
        )


# ─── 4. working_event() helper ──────────────────────────────────────


class HelperGateTests(unittest.TestCase):
    """working_event() reads (session_id, turn_id) from the
    PR-9b ContextVar. PR-10b wires this into cognitive stages.
    """

    def setUp(self):
        _clear_singleton_for_tests()
        set_session_context("", "")

    def tearDown(self):
        _clear_singleton_for_tests()
        set_session_context("", "")

    def test_helper_noop_when_context_unbound(self):
        """Plan item 9 — outside a tracked turn, the helper returns
        False and writes nothing."""
        ok = working_event(role="r", key="k", value="v")
        self.assertFalse(ok)
        # The singleton was lazily created — confirm no bucket landed
        wm = get_working_memory()
        self.assertEqual(wm.bucket_count(), 0)

    def test_helper_writes_when_context_bound(self):
        """Plan item 10 — under set_session_context, the helper
        writes and the stored slot is retrievable."""
        set_session_context("s_bound", "s_bound:1")
        ok = working_event(role="r", key="k", value="payload")
        self.assertTrue(ok)
        wm = get_working_memory()
        self.assertEqual(
            wm.get(session_id="s_bound", turn_id="s_bound:1",
                   role="r", key="k"),
            "payload",
        )


# ─── 5. singleton ───────────────────────────────────────────────────


class SingletonTests(unittest.TestCase):

    def setUp(self):
        _clear_singleton_for_tests()

    def tearDown(self):
        _clear_singleton_for_tests()

    def test_singleton_is_stable(self):
        a = get_working_memory()
        b = get_working_memory()
        self.assertIs(a, b)


# ─── 6. engine.query() finally-block hook (PR-10b) ──────────────────


class EngineQueryFinallyTests(unittest.TestCase):
    """PR-10b — verify that engine.query() releases the turn's
    working-memory scratch and clears the session ContextVar on
    every return path (including exception unwinds inside
    _query_impl).
    """

    def setUp(self):
        _clear_singleton_for_tests()
        set_session_context("", "")

    def tearDown(self):
        _clear_singleton_for_tests()
        set_session_context("", "")

    def _wm(self):
        return get_working_memory()

    def test_query_clears_working_memory_on_normal_return(self):
        """Happy path: a normal return through _query_impl still
        triggers the finally clear. We stub _query_impl so the test
        stays hermetic (no Ollama / retrieval roundtrip).
        """
        from core.reasoning.engine import ReasoningEngine
        engine = ReasoningEngine.__new__(ReasoningEngine)

        captured = {}

        def fake_impl(user_query, user_role=None, source_type="prod",
                      session_id="default", response_style="",
                      mode_override="", selected_model="", **kwargs):
            # While inside the impl, the ContextVar must be bound
            # and a working-memory write must land in the right
            # bucket. The wrapper sets the ContextVar BEFORE
            # delegating — except _query_impl is what sets it in
            # the real engine. Mimic that here.
            from core.observability import set_session_context
            tid = f"{session_id}:1"
            set_session_context(session_id, tid)
            self._wm().set(
                session_id=session_id, turn_id=tid,
                role="reflect.draft", key="text", value="draft v1",
            )
            captured["sid"] = session_id
            captured["tid"] = tid
            return {"answer": "ok", "blocked": False}

        engine._query_impl = fake_impl

        out = engine.query("hello", session_id="s_normal")
        self.assertEqual(out["answer"], "ok")

        # finally must have released the slot
        self.assertIsNone(
            self._wm().get(session_id=captured["sid"],
                            turn_id=captured["tid"],
                            role="reflect.draft", key="text"),
            "working memory must be cleared after query() returns",
        )
        # ContextVar must be released so the next request starts clean
        from core.observability import get_session_context
        sid, tid = get_session_context()
        self.assertEqual((sid, tid), ("", ""),
            "session ContextVar must be cleared in finally")

    def test_query_clears_working_memory_on_exception(self):
        """Critical invariant: if _query_impl raises, the finally
        block still releases the scratch. Otherwise a single
        crashed turn would leak its slots until the prune sweep.
        """
        from core.reasoning.engine import ReasoningEngine
        engine = ReasoningEngine.__new__(ReasoningEngine)

        captured = {}

        def crashing_impl(user_query, user_role=None, source_type="prod",
                          session_id="default", response_style="",
                          mode_override="", selected_model="", **kwargs):
            from core.observability import set_session_context
            tid = f"{session_id}:bang"
            set_session_context(session_id, tid)
            self._wm().set(
                session_id=session_id, turn_id=tid,
                role="verify.claims", key="c1", value="written before crash",
            )
            captured["sid"] = session_id
            captured["tid"] = tid
            raise RuntimeError("synthetic mid-turn failure")

        engine._query_impl = crashing_impl

        with self.assertRaises(RuntimeError):
            engine.query("oops", session_id="s_crash")

        self.assertIsNone(
            self._wm().get(session_id=captured["sid"],
                            turn_id=captured["tid"],
                            role="verify.claims", key="c1"),
            "exception must not skip the finally clear",
        )
        from core.observability import get_session_context
        self.assertEqual(get_session_context(), ("", ""))

    def test_query_clears_when_blocked_early(self):
        """pre_check failures return through _blocked_result without
        the ContextVar ever being bound. The wrapper must still
        clear safely — set_session_context("","") is a no-op
        when nothing was bound.
        """
        from core.reasoning.engine import ReasoningEngine
        engine = ReasoningEngine.__new__(ReasoningEngine)

        def early_return_impl(*args, **kwargs):
            # No set_session_context call → ContextVar stays empty.
            return {"answer": "blocked", "blocked": True}

        engine._query_impl = early_return_impl
        # Pre-bind to verify the wrapper actively clears even what
        # was already there before the call.
        set_session_context("preexisting", "preexisting:0")

        out = engine.query("x", session_id="s_blocked")
        self.assertTrue(out["blocked"])
        from core.observability import get_session_context
        self.assertEqual(get_session_context(), ("", ""),
            "wrapper must clear even when impl never touched the "
            "ContextVar — a stale pre-existing binding must not "
            "leak into the next request")


if __name__ == "__main__":
    unittest.main()
