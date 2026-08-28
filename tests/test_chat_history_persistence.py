"""Chat history persistence — item #3-a (2026-05-08 user feedback).

Source-level contracts on frontend/static/chat.js. We don't have a JS
test runner; this Python test scans the JS source to assert the
three contracts the v3-a fix promises:

  (1) `MAX_STORED` is at least 200 (was 50; user reported the cap
      was hit too quickly when returning to the chat).
  (2) `getSessionId()` reads/writes `localStorage` (not sessionStorage)
      so the session ID survives browser close / phone re-open.
  (3) `restoreHistory()` is actually CALLED on DOMContentLoaded — the
      v0.2.0 bug was that it was defined but never invoked, so the
      restore path was dead.
  (4) `clearHistory()` removes the session id key so a fresh session
      is minted on the next page load.

Run:
  python -m unittest tests.test_chat_history_persistence
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ChatHistoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parent.parent / "frontend" / "static" / "chat.js"
        cls.src = path.read_text(encoding="utf-8")
        cls.normalized = " ".join(cls.src.split())

    def test_max_stored_at_least_200(self):
        # Match `const MAX_STORED  =  200;` allowing whitespace variance.
        # Look for a numeric assignment to MAX_STORED.
        import re
        m = re.search(r"const\s+MAX_STORED\s*=\s*(\d+)", self.src)
        self.assertIsNotNone(m, "MAX_STORED const not found")
        n = int(m.group(1))
        self.assertGreaterEqual(n, 200,
                                f"MAX_STORED={n} too low; user reported "
                                f"50 was hit quickly. v3-a bumped to 200.")

    def test_session_id_persists_in_local_storage(self):
        # The bug we fixed: session_id was in sessionStorage, lost on
        # browser close. v3-a moves it to localStorage.
        # Match 'james_session' as a complete key — sibling keys like
        # 'james_session_lang' (language) must NOT trigger.
        import re
        # Key followed by closing quote + ) or , (read or write usage).
        self.assertTrue(
            re.search(
                r"localStorage\.getItem\(\s*['\"]james_session['\"]\s*\)",
                self.src,
            ),
            "getSessionId must read 'james_session' from localStorage "
            "(was sessionStorage in v0.2.0 — caused orphaned history)",
        )
        self.assertTrue(
            re.search(
                r"localStorage\.setItem\(\s*['\"]james_session['\"]\s*,",
                self.src,
            ),
            "getSessionId must persist 'james_session' to localStorage",
        )
        # And the OLD sessionStorage path for james_session must be gone.
        # Match exact key — 'james_session_lang' (sibling) is fine.
        self.assertFalse(
            re.search(
                r"sessionStorage\.(get|set)Item\(\s*['\"]james_session['\"]",
                self.src,
            ),
            "sessionStorage read/write of 'james_session' must be removed",
        )

    def test_restore_history_is_called_on_dom_content_loaded(self):
        # The v0.2.0 bug was that restoreHistory() was defined but
        # never invoked. The DOMContentLoaded init handler now calls it.
        self.assertIn(
            "restoreHistory()",
            self.src,
            "restoreHistory must be CALLED on DOMContentLoaded — "
            "defining it without invoking it was the v0.2.0 bug",
        )
        # The call must be inside a DOMContentLoaded handler. Look for
        # a window.addEventListener('DOMContentLoaded' window that
        # contains the call.
        idx = self.src.index("restoreHistory()")
        # Find the nearest preceding "DOMContentLoaded" within 800 chars.
        prelude = self.src[max(0, idx - 800):idx]
        self.assertIn("DOMContentLoaded", prelude,
                      "restoreHistory() must be invoked inside a "
                      "DOMContentLoaded handler so existing history "
                      "is shown on page load")

    def test_clear_history_resets_session_id(self):
        # If session_id stays in localStorage even after clearHistory,
        # the user can't actually "start fresh" without manually
        # clearing storage. v3-a removes the session key on clear.
        # [2026-08-26] Was an 800-char window; the confirm copy grew in
        # v0.6.1 v8 and pushed the removeItem call to ~950, so the test
        # reported it missing when it was simply further down.
        from tests._js_source import function_body
        body = function_body(self.src, "clearHistory")
        self.assertIn(
            "localStorage.removeItem('james_session')",
            body,
            "clearHistory must clear james_session from localStorage "
            "so the next reload mints a fresh session",
        )


class SessionIdRefreshAfterMutationTests(unittest.TestCase):
    """[N-3 회귀, 2026-05-18 user feedback]

    PR-O4 #291 added the engine-side `hist_ctx == ""` gate that
    prevents cross-session long_ctx leakage. But the frontend kept
    `SESSION_ID` / `HISTORY_KEY` as `const`s evaluated at module
    load — so newSession() / switchSession() updated localStorage
    but never the in-memory constants. The next POST /query/ sent
    `session_id=<old>`, the backend's hist_ctx was still populated
    from the old session, the N-3 gate didn't fire, and prior-
    session analyses came back in place of greetings.

    These tests pin the fix: const → let + a refreshSessionGlobals()
    helper called wherever localStorage['james_session'] is mutated.
    """

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parent.parent / "frontend" / "static" / "chat.js"
        cls.src = path.read_text(encoding="utf-8")

    def test_session_id_is_let_not_const(self):
        # The bug was that const SESSION_ID couldn't be reassigned
        # when localStorage changed. The fix declares it `let`.
        import re
        # Match the declaration of SESSION_ID.
        # `const SESSION_ID = ...` (old, broken) must NOT appear.
        self.assertFalse(
            re.search(r"\bconst\s+SESSION_ID\b", self.src),
            "SESSION_ID must be declared with `let` so newSession() / "
            "switchSession() can keep it in sync with localStorage. "
            "The previous `const` declaration caused N-3 regression — "
            "in-memory SESSION_ID was frozen at module-load time.",
        )
        self.assertTrue(
            re.search(r"\blet\s+SESSION_ID\b", self.src),
            "SESSION_ID must exist and be declared with `let`.",
        )

    def test_history_key_is_let_not_const(self):
        # HISTORY_KEY depends on SESSION_ID. If SESSION_ID can change
        # at runtime, HISTORY_KEY must follow it or restoreHistory()
        # / saveToLocal() write to the old session's localStorage slot.
        import re
        self.assertFalse(
            re.search(r"\bconst\s+HISTORY_KEY\b", self.src),
            "HISTORY_KEY must be declared with `let` for the same "
            "reason as SESSION_ID — it has to track SESSION_ID across "
            "session mutations or saveToLocal writes orphan history.",
        )
        self.assertTrue(
            re.search(r"\blet\s+HISTORY_KEY\b", self.src),
            "HISTORY_KEY must exist and be declared with `let`.",
        )

    def test_refresh_session_globals_helper_exists(self):
        # A single helper is the right shape — call sites converge
        # on one place that decides "now that localStorage changed,
        # rebind the two in-memory constants".
        self.assertIn(
            "function refreshSessionGlobals(",
            self.src,
            "A refreshSessionGlobals() helper must exist so call "
            "sites (newSession, switchSession, future ones) share "
            "one re-sync path.",
        )
        # The body must reassign BOTH globals — half-fix would still
        # leave restoreHistory() reading the wrong HISTORY_KEY.
        idx = self.src.index("function refreshSessionGlobals(")
        body = self.src[idx:idx + 400]
        self.assertIn("SESSION_ID =", body,
                      "refreshSessionGlobals must reassign SESSION_ID")
        self.assertIn("HISTORY_KEY =", body,
                      "refreshSessionGlobals must reassign HISTORY_KEY")

    def test_new_session_calls_refresh_helper(self):
        # newSession() is the most common path that hits the N-3
        # regression (user clicks "+ 새 채팅"). It MUST call the
        # helper after writing localStorage.
        idx = self.src.index("function newSession(")
        # Scan the function body — bounded by the next top-level
        # `function ` (or end of file).
        next_fn = self.src.find("\nfunction ", idx + 1)
        body = self.src[idx:next_fn if next_fn > 0 else len(self.src)]
        self.assertIn(
            "localStorage.setItem('james_session'",
            body,
            "newSession should still persist the new SID to localStorage",
        )
        self.assertIn(
            "refreshSessionGlobals()",
            body,
            "newSession MUST call refreshSessionGlobals() after the "
            "localStorage.setItem — otherwise SESSION_ID stays at its "
            "old value and the very next /query/ POST sends the wrong "
            "session_id, defeating the PR-O4 #291 N-3 backend gate.",
        )

    def test_switch_session_calls_refresh_helper(self):
        # switchSession() has the same shape — localStorage write,
        # then in-memory constants must be re-synced.
        idx = self.src.index("async function switchSession(")
        next_fn = self.src.find("\nasync function ", idx + 1)
        if next_fn < 0:
            next_fn = self.src.find("\nfunction ", idx + 1)
        body = self.src[idx:next_fn if next_fn > 0 else len(self.src)]
        self.assertIn(
            "localStorage.setItem('james_session'",
            body,
            "switchSession should persist the chosen SID to localStorage",
        )
        self.assertIn(
            "refreshSessionGlobals()",
            body,
            "switchSession MUST call refreshSessionGlobals() — same "
            "reason as newSession. Switching sessions and then sending "
            "a query without re-syncing would route the query to the "
            "OLD session's hist_ctx.",
        )


if __name__ == "__main__":
    unittest.main()
