"""[Axis 6 user feedback, 2026-05-12] Conversation continuity (Item 1).

Real user feedback from the v0.2.x → v0.3 second-user adoption track:

  > 위와 관련 또는 단어를 생략하더라도 바로 앞선 대화의 맥락이 이어져야
  > 하는데, 완전히 다른 딴소리를 할 경우가 생김.
  > 대화가 연속될때는 안녕하세요. 자메스입니다.는 생략해.
  > 대화의 연속성 부분을 총체적으로 개선해야한다.

Root causes traced in PR-A scoping (handover §3 P0):

  - core/memory/store.py:save_turn       — content truncated at
                                            500 chars on write
  - core/memory/store.py:get_history_context — per-turn slice
                                            truncated at 200 chars
                                            on read
  - core/reasoning/engine.py             — limit=3 short-term turns
  - core/reasoning/modes.py:handle_chat  — no instruction tells the
                                            LLM to skip greetings or
                                            resolve anaphora on
                                            continued conversations

This PR widens the truncation caps, bumps the turn limit, and
prepends a Korean / English "continuity directive" to the LLM
prompt whenever ``memory_context`` is non-empty. Tests below pin
the behaviour without requiring a live server.

CLAUDE.md rule #2 note: STEP 7 bench is a stateless single-shot
suite that doesn't carry session_id between queries, so the
continuity directive never fires for STEP 7 — the bench surface
is structurally untouched by this PR. Operator should still run
``scripts/bench.py --suite=step7 --check`` locally before merge
to confirm byte-identical behaviour on cold-start queries.
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


# ─── Memory store truncation widths ──────────────────────────────
class StoreTruncationTests(unittest.TestCase):
    """The save_turn write-cap and get_history_context read-slice
    are now wide enough to carry a typical 1-3 paragraph reply
    without losing tail text. Asserted on source so the test
    doesn't depend on an actual SQLite round-trip (covered
    separately by integration tests that hit the live store)."""

    @classmethod
    def setUpClass(cls):
        from core.memory import store as _store
        cls.src = inspect.getsource(_store)

    def test_save_turn_uses_2000_char_cap(self):
        # Scope the assertion to the save_turn body — other helpers
        # in store.py legitimately use [:500] for unrelated columns
        # (preference value, pattern body, goal text).
        save_idx = self.src.index("def save_turn(")
        next_def = self.src.index("\n    def ", save_idx + 1)
        body = self.src[save_idx:next_def]
        self.assertIn("question[:2000]", body,
            "save_turn must cap user content at 2000 chars")
        self.assertIn("answer[:2000]", body,
            "save_turn must cap assistant content at 2000 chars")
        self.assertNotIn("[:500]", body,
            "the old 500-char cap must be gone from save_turn "
            "— anaphora was losing its referent when long replies "
            "were chopped")

    def test_get_history_context_uses_800_char_slice(self):
        # Scope to the function body — [:200] survives elsewhere
        # (e.g., get_long_term_context summarises at [:150] / [:80]).
        idx = self.src.index("def get_history_context(")
        next_def = self.src.index("\n    def ", idx + 1)
        body = self.src[idx:next_def]
        self.assertIn("[:800]", body,
            "get_history_context must slice each turn at 800 chars")
        self.assertNotIn("[:200]", body,
            "the old 200-char per-turn slice must be gone")


# ─── Engine — short-term window limit ───────────────────────────
class EngineHistoryLimitTests(unittest.TestCase):

    def test_history_limit_is_five(self):
        from core.reasoning import engine as _engine
        src = inspect.getsource(_engine)
        # The call site we widened.
        self.assertIn("get_history_context(session_id, limit=5)", src,
            "engine must pull 5 prior turns (was 3) — multi-turn "
            "threads were dropping the earliest exchange")
        self.assertNotIn("get_history_context(session_id, limit=3)", src,
            "the old 3-turn limit must be gone")


# ─── Continuity directive on the chat handler ───────────────────
class ContinuityDirectiveTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from core.reasoning import modes as _modes
        cls.modes = _modes
        cls.src = inspect.getsource(_modes)

    def test_directives_declared_at_module_level(self):
        # Constants at the top of the file so a future caller (e.g.,
        # handle_meta, handle_coding) can re-use them without
        # re-declaring.
        self.assertTrue(hasattr(self.modes, "CONTINUITY_DIRECTIVE_KO"),
            "modes.py must export a Korean continuity directive")
        self.assertTrue(hasattr(self.modes, "CONTINUITY_DIRECTIVE_EN"),
            "modes.py must export an English continuity directive")

    def test_directives_say_skip_greeting(self):
        # The verbatim "안녕하세요" / "자메스입니다" trigger phrases
        # are mentioned by the user feedback — make sure they're
        # what the directive tells the model to suppress, not some
        # generic "be friendly" hint.
        self.assertIn("안녕하세요",
            self.modes.CONTINUITY_DIRECTIVE_KO,
            "KO directive must explicitly name the greeting it "
            "suppresses so the model can pattern-match")
        self.assertIn("자메스입니다",
            self.modes.CONTINUITY_DIRECTIVE_KO,
            "KO directive must explicitly name the self-introduction "
            "phrase the user reported")
        self.assertRegex(
            self.modes.CONTINUITY_DIRECTIVE_EN,
            r"[Hh]ello|greeting",
            "EN directive must mention greetings to skip")

    def test_directives_mention_anaphora_resolution(self):
        # Both directives must instruct the model to resolve
        # back-references against the most recent turn.
        for token in ("이것", "그것", "위"):
            with self.subTest(token=token):
                self.assertIn(token,
                    self.modes.CONTINUITY_DIRECTIVE_KO,
                    f"KO directive must name the anaphora token "
                    f"{token!r} the user typically uses")
        self.assertRegex(
            self.modes.CONTINUITY_DIRECTIVE_EN,
            r"this|that|above|anaphora",
            "EN directive must name English anaphora patterns")

    def test_handle_chat_gates_directive_on_current_session_history(self):
        # [N-3 2026-05-13] The directive used to gate on
        # ``memory_context`` (long_ctx ∪ hist_ctx ∪ prefs) — but a
        # brand-new session with prior-session summaries in long_ctx
        # would still fire the rule and (a) suppress the greeting and
        # (b) push the LLM to resolve "위/이것/그것" against other
        # sessions' content. The gate now lives on ``hist_ctx`` — the
        # *current* session's prior turns — so only an actual
        # continuation activates the rule. New session → no directive
        # → "안녕하세요" greeting returns + no cross-session leakage.
        chat_idx = self.src.index("def handle_chat(")
        body = self.src[chat_idx:chat_idx + 4000]
        self.assertIn("if hist_ctx:", body,
            "handle_chat must gate the directive on hist_ctx — the "
            "current session's prior turns — not on memory_context, "
            "which blends in cross-session summaries and prefs")
        self.assertIn("CONTINUITY_DIRECTIVE_KO", body,
            "handle_chat must consume the KO directive constant")
        self.assertIn("CONTINUITY_DIRECTIVE_EN", body,
            "handle_chat must consume the EN directive constant")

    def test_handle_chat_accepts_hist_ctx_kwarg(self):
        # The new signature must accept hist_ctx as a keyword arg with
        # an empty-string default, so callers that haven't been
        # updated yet (and stateless test queries) continue to behave
        # like first-turn cold starts.
        sig = inspect.signature(self.modes.handle_chat)
        self.assertIn("hist_ctx", sig.parameters,
            "handle_chat must accept hist_ctx so the engine can pass "
            "the current-session history separately from memory_context")
        self.assertEqual(
            sig.parameters["hist_ctx"].default, "",
            "hist_ctx must default to '' — cold-start callers and "
            "stateless STEP 7 queries should not trigger the directive")

    def test_directive_not_injected_when_only_longterm_memory_exists(self):
        """[N-3 regression] On a brand-new session, ``hist_ctx`` is
        empty but ``memory_context`` can still carry long-term session
        summaries or stored prefs. Before this fix the directive
        fired anyway, suppressing 'safety net' greetings and pushing
        the LLM to resolve anaphora against other sessions' content.
        This test captures the prompt that handle_chat actually
        constructs and asserts the directive is absent in that case.
        """
        from types import SimpleNamespace
        from core.reasoning import modes as _modes

        captured = {}
        def _fake_gemma(prompt, **_kw):
            captured["prompt"] = prompt
            return "안녕하세요. 자메스입니다. 무엇을 도와드릴까요?"

        fake_engine = SimpleNamespace(
            llm = SimpleNamespace(call_gemma=_fake_gemma),
            _log = lambda *a, **kw: None,
            _LLM_ERROR_PREFIXES = ("[Gemma",),
            _elapsed = lambda *a, **kw: None,
        )

        # New session: long-term summary in memory_context but no
        # current-session turns. Greeting should be allowed; the
        # continuity directive must NOT appear in the prompt.
        long_only_memory = "[장기 기억] 사용자는 이전 세션에서 RAG 에 대해 질문했음."
        _modes.handle_chat(
            engine         = fake_engine,
            safe_query     = "안녕",
            system_prompt  = "",
            memory_context = long_only_memory,
            user_role      = "external",
            t_start        = 0.0,
            hist_ctx       = "",  # ← new session — no current history
        )
        self.assertIn("prompt", captured, "handle_chat must call the LLM")
        prompt = captured["prompt"]
        self.assertNotIn(
            _modes.CONTINUITY_DIRECTIVE_KO, prompt,
            "Continuity directive must NOT fire when the only memory "
            "is cross-session — new session greetings would otherwise "
            "be suppressed (N-3)",
        )
        self.assertNotIn(
            _modes.CONTINUITY_DIRECTIVE_EN, prompt,
            "Continuity directive (EN) must also stay out in this case",
        )
        # The memory_context itself can still be included as
        # background, but without the "this is a continuation" framing.
        self.assertIn(long_only_memory, prompt,
            "Long-term memory may still appear in the prompt as "
            "background — it just must not be framed as a continuation")

    def test_directive_injected_when_current_session_history_exists(self):
        """[N-3 regression] When the user *is* mid-conversation —
        hist_ctx non-empty — the directive must still fire so the
        PR #249 anaphora-resolution / greeting-suppression behaviour
        survives. This is the path the original PR #249 was designed
        for and must keep working."""
        from types import SimpleNamespace
        from core.reasoning import modes as _modes

        captured = {}
        def _fake_gemma(prompt, **_kw):
            captured["prompt"] = prompt
            return "(continuation reply)"

        fake_engine = SimpleNamespace(
            llm = SimpleNamespace(call_gemma=_fake_gemma),
            _log = lambda *a, **kw: None,
            _LLM_ERROR_PREFIXES = ("[Gemma",),
            _elapsed = lambda *a, **kw: None,
        )

        live_history = "[이전 대화] user: RAG 알려줘\nassistant: RAG 는 ..."
        _modes.handle_chat(
            engine         = fake_engine,
            safe_query     = "위 내용 더 자세히",
            system_prompt  = "",
            memory_context = live_history,
            user_role      = "external",
            t_start        = 0.0,
            hist_ctx       = live_history,
        )
        prompt = captured.get("prompt", "")
        self.assertIn(
            _modes.CONTINUITY_DIRECTIVE_KO, prompt,
            "Continuity directive must fire when current-session "
            "history exists — that is the original PR #249 path",
        )

    def test_engine_threads_hist_ctx_to_handle_chat(self):
        # The engine builds hist_ctx separately from memory_context
        # and must forward it to handle_chat by name so the gate
        # above can see "current session has prior turns" exactly.
        from core.reasoning import engine as _engine
        src = inspect.getsource(_engine)
        self.assertIn("hist_ctx=hist_ctx", src,
            "engine.query must forward hist_ctx to handle_chat by "
            "keyword so the new-session greeting path is restored")
        # hist_ctx must be initialised before the memory try/except
        # — otherwise a memory store error leaves it undefined when
        # the dispatch tries to forward it.
        hist_init_idx = src.find('hist_ctx = ""')
        try_idx       = src.find("from core.memory import MemoryStore")
        self.assertGreater(hist_init_idx, 0,
            "engine must initialise hist_ctx = '' before the memory "
            "try block so a memory error still yields a cold-start "
            "greeting instead of a NameError")
        self.assertLess(hist_init_idx, try_idx,
            "hist_ctx init must precede the memory try block")

    def test_directive_uses_korean_or_english_per_query(self):
        # The is_ko flag is computed at the top of handle_chat for
        # the rule_txt selection; the directive selection MUST use
        # the same flag to stay consistent.
        chat_idx = self.src.index("def handle_chat(")
        body = self.src[chat_idx:chat_idx + 4000]
        self.assertRegex(
            body,
            r"CONTINUITY_DIRECTIVE_KO\s+if\s+is_ko\s+else\s+CONTINUITY_DIRECTIVE_EN",
            "directive selection must mirror the rule_txt is_ko check",
        )


# ─── Smoke against an actual SQLite round-trip ──────────────────
class StoreRoundTripTests(unittest.TestCase):
    """The truncation caps only matter if a real write+read cycle
    preserves them. This goes through the real MemoryStore against
    a temp DB so an outright SQLite or column-type regression
    would fail here."""

    def test_long_content_round_trips_below_2000(self):
        # Patch _DB_PATH to a temp file so we don't write to the
        # operator's actual james_memory.db.
        import tempfile
        from core.memory import store as _store
        prev = _store.DB_PATH
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp = f.name
        try:
            _store.DB_PATH = tmp
            _store.init_db()
            ms = _store.MemoryStore()
            long_q = "Q. " + ("가" * 1500)   # ~1503 chars, under 2000
            long_a = "A. " + ("나" * 1500)
            ok = ms.save_turn(
                "test_session", long_q, long_a, mode="chat",
            )
            self.assertTrue(ok)

            turns = ms.get_recent_turns("test_session", limit=5)
            # save_turn stores user + assistant rows; both round-trip.
            self.assertEqual(len(turns), 2)
            kinds = {t["role"] for t in turns}
            self.assertEqual(kinds, {"user", "assistant"})
            # Full content (≤ 2000 chars) survived intact.
            for t in turns:
                self.assertGreater(len(t["content"]), 1400,
                    f"role={t['role']} truncated — got "
                    f"{len(t['content'])} chars; cap should be 2000")
        finally:
            _store.DB_PATH = prev
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def test_get_history_context_returns_wide_slice(self):
        import tempfile
        from core.memory import store as _store
        prev = _store.DB_PATH
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp = f.name
        try:
            _store.DB_PATH = tmp
            _store.init_db()
            ms = _store.MemoryStore()
            # 1000-char answer; the OLD 200-char slice would have
            # cut this to ~200 chars in get_history_context.
            answer = "결론은 " + ("매우 중요한 핵심 내용 " * 60)
            ms.save_turn("s1", "위에서 말한 것 자세히 알려줘", answer)
            ctx = ms.get_history_context("s1", limit=5)
            # Should carry well over 200 chars now.
            self.assertGreater(
                len(ctx), 500,
                "get_history_context must yield > 500 chars on a "
                "1000-char answer; old 200-char per-turn slice "
                "would chop it to ~250",
            )
            # Header marker preserved so the model knows it's history.
            self.assertIn("[이전 대화]", ctx)
        finally:
            _store.DB_PATH = prev
            try:
                os.unlink(tmp)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
