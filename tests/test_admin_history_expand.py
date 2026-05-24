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
        # [§5 PR-D] Backdrop close moves to data-overlay-action (fires
        # only when e.target === overlay; replaces the prior
        # onclick="closeSessionTurns(event)" + inner stopPropagation
        # pattern). X button uses data-action="close-session-turns".
        self.assertIn('data-overlay-action="close-session-turns"', self.html,
                      "backdrop click handler missing")
        self.assertIn('data-action="close-session-turns"', self.html,
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
        # [§5 PR-D] The row template now emits
        # data-action="open-session-turns" data-sid=… data-title=…
        # instead of inline onclick="openSessionTurns(…)".
        idx = self.js.index("async function loadLongTerm")
        body = self.js[idx:idx + 1500]
        self.assertIn('data-action="open-session-turns"', body,
                      "loadLongTerm rows must wire to open-session-turns "
                      "via the click delegate")
        self.assertIn('data-sid=', body,
                      "row must carry data-sid for the delegate to read")
        # Conditional: only attach the action when session_id is present.
        self.assertIn("s.session_id", body,
                      "loadLongTerm must read session_id from each summary")

    def test_sessions_action_button_not_overridden(self):
        # Sanity: the summarize&delete button must NOT also fire the
        # expand action by accident — operators expect distinct
        # behaviors for "expand" vs "delete". The row's expand-on-
        # click moved to data-action="open-session-turns" on the
        # session-id and turn-count cells only; the action <button>
        # cell uses data-action="summarize-and-delete".
        idx = self.js.index("async function loadSessions")
        body = self.js[idx:idx + 1800]
        self.assertIn('data-action="summarize-and-delete"', body,
                      "summarize&delete button must remain functional "
                      "via the click delegate")
        # Find the summarize button tag and assert it doesn't also
        # carry the expand action.
        m = re.search(
            r'<button[^>]*data-action="summarize-and-delete"[^>]*>',
            body,
        )
        self.assertIsNotNone(m, "summarize button regex missing")
        self.assertNotIn("open-session-turns", m.group(),
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


class DeleteOnlyPathTests(unittest.TestCase):
    """PR-O8 — operator added a no-LLM delete path next to the existing
    Summarize & Delete button. The LLM-driven path (POST /history/summarize/)
    is a long-running (30-60s) reflect/verify-tier call on gemma4:e4b
    (Direction 1 closure finding, PR #461). Operators frequently mistake
    it for a simple delete and end up waiting. This sub-suite locks
    the new buttons + handlers + i18n surface in place.
    """

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent / "frontend" / "static"
        cls.js   = (root / "admin.js").read_text(encoding="utf-8")
        cls.i18n = (root / "i18n.js").read_text(encoding="utf-8")

    def test_delete_only_button_in_sessions_row(self):
        # The delete-only button must live in the action column of the
        # session list row, alongside (not replacing) the Summarize & Delete
        # button. Operators get to choose which path to take.
        idx = self.js.index("async function loadSessions")
        body = self.js[idx:idx + 1800]
        self.assertIn('data-action="delete-session-only"', body,
                      "delete-only button must be wired via the click delegate")
        self.assertIn('data-action="summarize-and-delete"', body,
                      "summarize-and-delete button must remain — delete-only "
                      "is additive, not a replacement")

    def test_delete_only_handler_registered(self):
        self.assertIn(
            "case 'delete-session-only':",
            self.js,
            "delete-session-only action must have a switch case in the "
            "click delegate",
        )
        self.assertIn(
            "async function deleteSessionOnly(",
            self.js,
            "deleteSessionOnly() function must be defined",
        )

    def test_delete_only_function_does_not_call_summarize(self):
        # Critical: the delete-only path must NOT hit /history/summarize/.
        # If it did, the bug being fixed would silently come back.
        idx = self.js.index("async function deleteSessionOnly(")
        body = self.js[idx:idx + 1200]
        self.assertNotIn("/history/summarize/", body,
                         "deleteSessionOnly must not call the summarize "
                         "endpoint — that was the slow path being separated")
        self.assertIn("/history/?session_id=", body,
                      "deleteSessionOnly must call the DELETE /history/ endpoint")

    def test_delete_only_has_confirm_gate(self):
        idx = self.js.index("async function deleteSessionOnly(")
        body = self.js[idx:idx + 1200]
        self.assertIn("confirm(", body,
                      "deleteSessionOnly must gate the DELETE with a confirm() "
                      "— accidental row clicks should not wipe data")

    def test_summarize_path_has_spinner(self):
        # The summarize path is 30-60s long-running; without a persistent
        # indicator operators think the UI froze. PR-O8 added an
        # explicit spinner toast that lives until the request completes.
        idx = self.js.index("async function summarizeAndDelete(")
        body = self.js[idx:idx + 2000]
        self.assertIn("toastPersistent(", body,
                      "summarizeAndDelete must use the persistent toast "
                      "helper for the long-running LLM call")
        # The spinner must clean up in a finally block so a failed
        # request doesn't leave a stale toast on screen.
        self.assertIn("finally", body,
                      "spinner cleanup must be in a finally block to handle "
                      "the error path too")

    def test_toast_persistent_helper_exists(self):
        self.assertIn(
            "function toastPersistent(",
            self.js,
            "toastPersistent() helper must be defined — it's the persistent "
            "long-running counterpart of toast()",
        )

    def test_summarize_path_has_expectation_gate(self):
        # Before the LLM call fires, surface an explicit confirm that
        # warns about the wait. Operators frequently mistook this for
        # a simple delete; the gate sets correct expectation.
        idx = self.js.index("async function summarizeAndDelete(")
        body = self.js[idx:idx + 2000]
        self.assertIn("confirm(", body,
                      "summarizeAndDelete must gate the LLM call with a "
                      "confirm() that explicitly mentions the wait")
        self.assertIn("mem.confirm_summarize_delete", body,
                      "the confirm text must use the i18n key so KR + EN "
                      "operators both see the wait warning")

    def test_i18n_keys_present_en_and_kr(self):
        # Six new i18n keys across two languages = 12 entries total.
        required = (
            "mem.delete_only",
            "mem.summarize_delete",
            "mem.confirm_delete_only",
            "mem.confirm_summarize_delete",
            "mem.summarizing",
            "mem.deleted_no_summary",
        )
        for k in required:
            # quoted key matches both 'k': value and "k": value forms
            occurrences = self.i18n.count(f"'{k}'") + self.i18n.count(f'"{k}"')
            self.assertGreaterEqual(
                occurrences, 2,
                f"i18n key {k!r} must appear in both EN and KR sections "
                f"(found {occurrences} times)",
            )

    def test_summarize_delete_key_was_previously_undefined(self):
        # Regression guard: the HTML template referenced
        # data-i18n='mem.summarize_delete' but the i18n table never
        # defined it. PR-O8 adds the definition; this test pins it.
        self.assertGreaterEqual(
            self.i18n.count("'mem.summarize_delete'")
            + self.i18n.count('"mem.summarize_delete"'),
            2,
            "mem.summarize_delete must be defined in both EN and KR — "
            "the HTML template referenced it before PR-O8 but the i18n "
            "table didn't carry the key, leaving the button text "
            "untranslated under language switch",
        )


if __name__ == "__main__":
    unittest.main()
