"""Cognitive Phase 3 PR-9b — wiring tests.

PR-9a (test_episodic_memory.py) covers the store as a black box.
This file covers the *wiring*: that the cognitive stages
(planner / reflect / verify / synth via trace_synth_call) actually
call `record_event()`, that cross-turn read in `engine_memory` injects
prior reasoning into the system_prompt, and that the admin endpoint
respects session isolation.

Strategy:
  * Replace the singleton EpisodicMemory with one backed by a temp
    DB so writes are observable without touching production state.
  * Bind a session ContextVar before exercising the stage under
    test, then read back rows from the temp DB.
  * Mock the LLM backend so tests stay hermetic and CPU-cheap.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.memory.episodic import (  # noqa: E402
    EpisodicMemory,
    _clear_singleton_for_tests,
)
import core.memory.episodic as _episodic_mod  # noqa: E402
from core.observability import (  # noqa: E402
    set_session_context,
    current_session,
)


def _fresh_episodic_singleton() -> EpisodicMemory:
    """Replace the module-level singleton with one backed by a temp
    DB. Returns the new instance so tests can read rows back.
    """
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    em = EpisodicMemory(db_path=f.name)
    _clear_singleton_for_tests()
    _episodic_mod._SINGLETON = em
    return em


class WiringFromStagesTests(unittest.TestCase):
    """Each cognitive stage should write one episodic row when called
    inside a bound session context.
    """

    def setUp(self):
        self.em = _fresh_episodic_singleton()
        set_session_context("s_test", "s_test:1")
        # Force-enable opt-in modules so their _emit paths actually run.
        self._saved_planner = os.environ.pop("JAMES_ENABLE_PLANNER", None)
        os.environ["JAMES_ENABLE_PLANNER"] = "1"

    def tearDown(self):
        _clear_singleton_for_tests()
        set_session_context("", "")
        if self._saved_planner is None:
            os.environ.pop("JAMES_ENABLE_PLANNER", None)
        else:
            os.environ["JAMES_ENABLE_PLANNER"] = self._saved_planner

    def test_planner_records_after_successful_plan(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.return_value = MagicMock(
            text='{"subtasks": ["a", "b", "c"], "rationale": "ok"}',
            error="",
        )
        with patch("core.reasoning.backends.get_backend",
                   return_value=fake):
            Planner().plan(
                "비트코인 ETF 가 미국 시장에 미친 영향을 분석해줘",
            )
        events = self.em.recent_events("s_test", limit=50)
        plan_events = [e for e in events if e.stage == "plan"]
        self.assertEqual(len(plan_events), 1,
            "planner should write exactly one episodic row per plan call")
        self.assertIn("subtasks", plan_events[0].summary.lower() + " "
                      + str(plan_events[0].extras))

    def test_synth_records_via_trace_synth_call(self):
        from core.reasoning import trace_helpers
        fake_backend = MagicMock()
        fake_backend.complete.return_value = MagicMock(
            text="answer body",
            error="",
            backend_id="ollama_local",
            latency_ms=50,
        )
        with patch("core.reasoning.trace_helpers.get_backend",
                   return_value=fake_backend), \
             patch("core.reasoning.trace_helpers.resolve_backend_for_stage",
                   return_value="ollama_local"):
            trace_helpers.trace_synth_call(
                "what is RAG?",
                applied_rule="reasoning.synth.rag",
                stage="synth",
            )
        events = self.em.recent_events("s_test", limit=50)
        synth_events = [e for e in events if e.stage == "synth"]
        self.assertEqual(len(synth_events), 1,
            "trace_synth_call should mirror to episodic exactly once")
        self.assertEqual(synth_events[0].summary, "answer body")


class CrossTurnReadTests(unittest.TestCase):
    """build_memory_context should inject prior turns' episodic
    summaries into the system_prompt — except on the first turn of
    a new session (hist_ctx == "" gate).
    """

    def setUp(self):
        self.em = _fresh_episodic_singleton()
        # Pre-populate two prior turns in this session.
        for turn_idx, summary in [(1, "계획 3단계"),
                                   (2, "verify 통과")]:
            self.em.record(
                session_id="s_cross",
                turn_id=f"s_cross:{turn_idx}",
                stage=("plan" if turn_idx == 1 else "verify"),
                summary=summary,
            )

    def tearDown(self):
        _clear_singleton_for_tests()

    def test_cross_turn_read_injects_prior_events_when_hist_ctx_present(self):
        # Stub the MemoryStore / character / persona machinery so we
        # isolate the episodic block under test.
        from core.reasoning import engine_memory
        engine = MagicMock()

        ms_inst = MagicMock()
        ms_inst.get_system_prompt.return_value = ""
        ms_inst.get_context.return_value = ""
        ms_inst.get_history_context.return_value = "prior turn content"
        ms_inst.get_long_term_context.return_value = ""

        with patch("core.memory.MemoryStore", return_value=ms_inst), \
             patch("core.character_profile.CharacterProfile") as cp, \
             patch("core.memory.is_persona_command", return_value=False):
            cp.return_value.get_prompt_modifiers.return_value = ""
            _, system_prompt, hist_ctx = engine_memory.build_memory_context(
                engine, "follow-up question",
                "admin", {"session_id": "s_cross"},
            )
        self.assertNotEqual(hist_ctx, "",
            "fixture should leave hist_ctx populated")
        self.assertIn("이전 추론 흔적", system_prompt,
            "cross-turn episodic block should be prepended")
        self.assertIn("계획 3단계", system_prompt)
        self.assertIn("verify 통과", system_prompt)

    def test_cross_turn_read_skips_on_new_session_first_turn(self):
        # hist_ctx == "" → fresh session → no episodic context, even
        # though prior session-id rows might exist (PR-O4 N-3 isolation).
        from core.reasoning import engine_memory
        engine = MagicMock()
        ms_inst = MagicMock()
        ms_inst.get_system_prompt.return_value = ""
        ms_inst.get_context.return_value = ""
        ms_inst.get_history_context.return_value = ""
        ms_inst.get_long_term_context.return_value = ""

        with patch("core.memory.MemoryStore", return_value=ms_inst), \
             patch("core.character_profile.CharacterProfile") as cp, \
             patch("core.memory.is_persona_command", return_value=False):
            cp.return_value.get_prompt_modifiers.return_value = ""
            _, system_prompt, hist_ctx = engine_memory.build_memory_context(
                engine, "first message",
                "admin", {"session_id": "s_cross"},
            )
        self.assertEqual(hist_ctx, "")
        self.assertNotIn("이전 추론 흔적", system_prompt,
            "first turn must not see prior episodic context")


class SessionIsolationTests(unittest.TestCase):
    """SQL WHERE session_id = ? gate is checked at the store level by
    test_episodic_memory.py. This test verifies the wiring layer
    respects the same boundary — events from session A don't surface
    when build_memory_context runs under session B.
    """

    def setUp(self):
        self.em = _fresh_episodic_singleton()
        # Session A: a turn happened, has plan events.
        self.em.record(
            session_id="s_A", turn_id="s_A:1",
            stage="plan", summary="should NOT leak to session B",
        )

    def tearDown(self):
        _clear_singleton_for_tests()

    def test_cross_session_episodic_does_not_leak(self):
        from core.reasoning import engine_memory
        engine = MagicMock()
        ms_inst = MagicMock()
        ms_inst.get_system_prompt.return_value = ""
        ms_inst.get_context.return_value = ""
        ms_inst.get_history_context.return_value = "B's own history"
        ms_inst.get_long_term_context.return_value = ""

        with patch("core.memory.MemoryStore", return_value=ms_inst), \
             patch("core.character_profile.CharacterProfile") as cp, \
             patch("core.memory.is_persona_command", return_value=False):
            cp.return_value.get_prompt_modifiers.return_value = ""
            _, system_prompt, _ = engine_memory.build_memory_context(
                engine, "B's question",
                "admin", {"session_id": "s_B"},
            )
        self.assertNotIn("should NOT leak", system_prompt,
            "session A's events must never surface under session B")


class OptOutGateTests(unittest.TestCase):
    """JAMES_EPISODIC_CONTEXT=0 disables cross-turn injection without
    affecting the record path. Useful when an operator wants to
    measure baseline cost.
    """

    def setUp(self):
        self.em = _fresh_episodic_singleton()
        self.em.record(
            session_id="s_off", turn_id="s_off:1",
            stage="plan", summary="should be hidden when disabled",
        )
        self._saved = os.environ.get("JAMES_EPISODIC_CONTEXT")
        os.environ["JAMES_EPISODIC_CONTEXT"] = "0"

    def tearDown(self):
        _clear_singleton_for_tests()
        if self._saved is None:
            os.environ.pop("JAMES_EPISODIC_CONTEXT", None)
        else:
            os.environ["JAMES_EPISODIC_CONTEXT"] = self._saved

    def test_opt_out_suppresses_injection(self):
        from core.reasoning import engine_memory
        engine = MagicMock()
        ms_inst = MagicMock()
        ms_inst.get_system_prompt.return_value = ""
        ms_inst.get_context.return_value = ""
        ms_inst.get_history_context.return_value = "prior turn"
        ms_inst.get_long_term_context.return_value = ""

        with patch("core.memory.MemoryStore", return_value=ms_inst), \
             patch("core.character_profile.CharacterProfile") as cp, \
             patch("core.memory.is_persona_command", return_value=False):
            cp.return_value.get_prompt_modifiers.return_value = ""
            _, system_prompt, _ = engine_memory.build_memory_context(
                engine, "follow-up",
                "admin", {"session_id": "s_off"},
            )
        self.assertNotIn("이전 추론 흔적", system_prompt,
            "opt-out env must suppress the episodic block")


class ContextVarBindingTests(unittest.TestCase):
    """engine.query() binds (session_id, turn_id) before any stage
    runs. record_event() returns None when called outside a bound
    context — keeping unit tests and background jobs from polluting
    the store with session_id="" rows.
    """

    def setUp(self):
        self.em = _fresh_episodic_singleton()
        # Explicitly clear context so we start uninstrumented.
        set_session_context("", "")

    def tearDown(self):
        _clear_singleton_for_tests()

    def test_record_event_noop_without_session_context(self):
        from core.memory.episodic import record_event
        out = record_event(stage="plan", summary="orphan write")
        self.assertIsNone(out,
            "record_event must skip when no session is bound")
        events = self.em.recent_events("anything", limit=10)
        self.assertEqual(events, [],
            "no row should land in the store")

    def test_record_event_writes_when_session_bound(self):
        from core.memory.episodic import record_event
        set_session_context("s_bound", "s_bound:1")
        try:
            ev_id = record_event(
                stage="reflect",
                summary="bound write",
                extras={"k": "v"},
            )
            self.assertIsNotNone(ev_id,
                "record_event should return event_id when session bound")
            events = self.em.recent_events("s_bound", limit=10)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].stage, "reflect")
            self.assertEqual(events[0].summary, "bound write")
            self.assertEqual(events[0].extras.get("k"), "v")
        finally:
            set_session_context("", "")


if __name__ == "__main__":
    unittest.main()
