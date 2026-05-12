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

    def test_handle_chat_injects_directive_only_when_memory_present(self):
        # Source-level assertion: the directive prepend lives inside
        # an ``if memory_context:`` branch so a first-turn request
        # (empty memory) is unchanged.
        chat_idx = self.src.index("def handle_chat(")
        body = self.src[chat_idx:chat_idx + 4000]
        self.assertIn("if memory_context:", body,
            "handle_chat must gate the directive on memory_context "
            "presence so first-turn replies keep their introductory tone")
        self.assertIn("CONTINUITY_DIRECTIVE_KO", body,
            "handle_chat must consume the KO directive constant")
        self.assertIn("CONTINUITY_DIRECTIVE_EN", body,
            "handle_chat must consume the EN directive constant")

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
