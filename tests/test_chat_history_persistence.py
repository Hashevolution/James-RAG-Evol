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
        idx = self.src.index("async function clearHistory")
        # Look at the 800 chars after the function signature.
        body = self.src[idx:idx + 800]
        self.assertIn(
            "localStorage.removeItem('james_session')",
            body,
            "clearHistory must clear james_session from localStorage "
            "so the next reload mints a fresh session",
        )


if __name__ == "__main__":
    unittest.main()
