"""Admin Memory page — session click-to-expand modal (item #3-b).

Source-level contracts:
  - admin.html has the session-turns modal (title / meta / body
    placeholders) and the (.json) close handler.
  - admin.js loadLongTerm passes session_id into openSessionTurns
    when present, marks rows as cursor:pointer only when a session_id
    is available.
  - admin.js loadSessions makes the session_id and turn_count cells
    clickable but leaves the action button alone (no accidental
    summarize&delete on click).
  - admin.js openSessionTurns calls /history/?session_id=&limit=
    and renders turns; XSS-safe via escapeHtml on every operator-
    controlled text field.

Run:
  python -m unittest tests.test_admin_history_expand
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HtmlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parent.parent
                    / "frontend" / "admin.html").read_text(encoding="utf-8")

    def test_modal_present(self):
        self.assertIn('id="session-turns-modal"', self.html,
                      "session-turns modal container missing from admin.html")

    def test_modal_has_title_meta_body_placeholders(self):
        for el in ('id="session-turns-title"',
                   'id="session-turns-meta"',
                   'id="session-turns-body"'):
            self.assertIn(el, self.html,
                          f"modal placeholder {el} missing")

    def test_close_handler_present(self):
        # Backdrop click handler + explicit X button handler both wire
        # to closeSessionTurns.
        self.assertIn('onclick="closeSessionTurns(event)"', self.html,
                      "backdrop click handler missing")
        self.assertIn('onclick="closeSessionTurns()"', self.html,
                      "X button handler missing")

    def test_long_term_table_advertises_clickable_rows(self):
        # The user-visible hint (행 클릭 → 원본 대화 펼침) is what
        # tells operators why rows are clickable. Drift is a UX bug.
        self.assertIn("행 클릭", self.html,
                      "the section title hint must inform operators "
                      "that rows are clickable for expand")


class JsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (Path(__file__).resolve().parent.parent
                  / "frontend" / "static" / "admin.js").read_text(encoding="utf-8")

    def test_open_session_turns_function_exists(self):
        self.assertIn("async function openSessionTurns", self.js,
                      "openSessionTurns function missing")
        # Hits the /history/ endpoint with session_id + limit.
        idx = self.js.index("async function openSessionTurns")
        body = self.js[idx:idx + 2200]
        self.assertIn("/history/?session_id=", body,
                      "must fetch /history/ for the session")
        self.assertIn("limit=", body,
                      "must request a generous limit (200) for full expansion")

    def test_close_session_turns_function_exists(self):
        self.assertIn("function closeSessionTurns", self.js,
                      "closeSessionTurns missing")

    def test_long_term_row_uses_session_id_when_available(self):
        idx = self.js.index("async function loadLongTerm")
        body = self.js[idx:idx + 1500]
        self.assertIn("openSessionTurns(", body,
                      "loadLongTerm rows must wire to openSessionTurns")
        # Conditional: only attach onclick when session_id present.
        self.assertIn("s.session_id", body,
                      "loadLongTerm must read session_id from each summary")

    def test_sessions_action_button_not_overridden(self):
        # Sanity: the summarize&delete button must NOT call
        # openSessionTurns by accident — operators expect distinct
        # behaviors for "expand" vs "delete".
        idx = self.js.index("async function loadSessions")
        body = self.js[idx:idx + 1800]
        self.assertIn("summarizeAndDelete(", body,
                      "summarize&delete button must remain functional")
        # The button itself must not also be wired to expand.
        # Look for the <button ... onclick="summarizeAndDelete..."> region
        # and assert it doesn't contain openSessionTurns inside the button tag.
        m = re.search(
            r'<button[^>]*summarizeAndDelete[^>]*>',
            body,
        )
        self.assertIsNotNone(m, "summarize button regex missing")
        self.assertNotIn("openSessionTurns", m.group(),
                         "the summarize button must not also be wired "
                         "to expand — operators get confused if a single "
                         "click does two things")

    def test_xss_escaping_in_modal_render(self):
        # Operator-controlled text (turn.content, mode) must be
        # escapeHtml'd before being injected into innerHTML.
        idx = self.js.index("async function openSessionTurns")
        body = self.js[idx:idx + 2200]
        # We expect at least 4 escapeHtml() calls in the render block.
        count = body.count("escapeHtml(")
        self.assertGreaterEqual(count, 4,
                                f"openSessionTurns has only {count} escapeHtml "
                                f"calls; operator-controlled text must be "
                                f"escaped to prevent XSS in the admin UI")


if __name__ == "__main__":
    unittest.main()
