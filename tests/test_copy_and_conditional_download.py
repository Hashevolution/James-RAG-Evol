"""Conversation copy + conditional download UX (item #4, 2026-05-08).

User feedback: "대화내용은 복사가 가능한 버튼을 대화창 아래 만들고,
파일 다운로드의 경우는 보고서 양식으로 파일로 만들었때 버튼이
뜨게끔 로직과 ui 개선".

Changes:

1. Conversation full-copy button — between messages and input area.
   Reads localStorage HISTORY_KEY, formats turns as
   "[사용자] ...\\n[자메스] ...\\n\\n", clipboard.writeText.

2. Per-message export buttons (.md/.docx/.txt) shown ONLY when
   the user's prior question contained a 'report-export' keyword.
   Default chat answers have only feedback (👍/👎/📋 copy).
   Keyword regex: 보고서|레포트|문서로|문서 로 만들|파일로 만들|
                  파일 로 저장|다운로드|export|report (file|format)?

3. Per-message single-answer copy button (📋 복사).

Run:
  python -m unittest tests.test_copy_and_conditional_download
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "index.html"
JS   = ROOT / "frontend" / "static" / "chat.js"


class FullCopyButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.js   = JS.read_text(encoding="utf-8")

    def test_html_has_full_copy_button(self):
        # [§5 migration] copyConversation() → data-action.
        self.assertIn('data-action="copy-conversation"', self.html,
                      "전체 대화 복사 버튼 missing")
        self.assertIn("대화 전체 복사", self.html,
                      "user-visible label '대화 전체 복사' missing")

    def test_js_copy_conversation_function(self):
        self.assertIn("async function copyConversation()", self.js)
        self.assertIn("HISTORY_KEY", self.js)
        # Both modern + fallback clipboard paths.
        self.assertIn("navigator.clipboard", self.js)
        self.assertIn("execCommand('copy')", self.js,
                      "fallback execCommand path required for non-HTTPS / "
                      "older mobile browsers")

    def test_js_copy_conversation_serializes_role_and_text(self):
        idx = self.js.index("async function copyConversation()")
        body = self.js[idx:idx + 1500]
        # The serialization marks user vs james.
        self.assertIn("[사용자]", body)
        self.assertIn("[자메스]", body)


class PerMessageCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_copy_answer_text_function(self):
        self.assertIn("async function copyAnswerText(btn)", self.js,
                      "per-message copy function missing")

    def test_per_message_copy_button_in_msg(self):
        # The copy button is rendered in appendJamesMsg.
        idx = self.js.index("function appendJamesMsg")
        # Bound to next top-level function to capture entire body.
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 8000
        body = self.js[idx:end]
        # [§5 migration] copyAnswerText(this) → data-action; delegate
        # passes the element to the underlying function.
        self.assertIn('data-action="copy-answer-text"', body,
                      "appendJamesMsg must include a per-answer copy button")
        self.assertIn("📋 복사", body)


class ConditionalExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_pending_report_request_flag_exists(self):
        self.assertIn("pendingReportRequest", self.js,
                      "module-scope pendingReportRequest flag missing")

    def test_keyword_regex_present(self):
        self.assertIn("REPORT_REQUEST_KEYWORDS", self.js,
                      "report-request keyword regex constant missing")
        # Must include '보고서' and 'report'.
        idx = self.js.index("REPORT_REQUEST_KEYWORDS")
        body = self.js[idx:idx + 300]
        self.assertIn("보고서", body)
        self.assertIn("report", body)

    def test_send_message_sets_flag(self):
        idx = self.js.index("async function sendMessage()")
        body = self.js[idx:idx + 1500]
        self.assertIn("pendingReportRequest = REPORT_REQUEST_KEYWORDS.test(text)",
                      body,
                      "sendMessage must set pendingReportRequest based on regex")

    def test_append_james_consumes_flag(self):
        # Use next-function bound so future additions to appendJamesMsg
        # (e.g. #A6-2 web-used badge) don't push the export logic past
        # an arbitrary char limit.
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 12000
        body = self.js[idx:end]
        self.assertIn("showExportBtns", body,
                      "appendJamesMsg must check showExportBtns variable")
        self.assertIn("pendingReportRequest = false", body,
                      "appendJamesMsg must consume (clear) the flag after read")
        # When showExportBtns is false, the export buttons must be empty string.
        self.assertIn("showExportBtns ?", body,
                      "ternary branch must conditionally render export buttons")

    def test_report_keywords_match_expected_phrases(self):
        # Behavioral parity check via regex extraction — the JS pattern
        # must accept all the user-reported phrasings.
        idx = self.js.index("REPORT_REQUEST_KEYWORDS =")
        # Find the regex literal after `=` until the trailing `;`.
        end = self.js.index(";", idx)
        snippet = self.js[idx:end]
        # Convert /pattern/i to a Python re by extracting between slashes.
        m = re.search(r"/(.+)/i", snippet, re.DOTALL)
        self.assertIsNotNone(m, "could not locate regex literal in JS")
        py_pat = re.compile(m.group(1), re.IGNORECASE)
        for phrase in (
            "보고서로 만들어줘",
            "이걸 레포트로 정리해",
            "이 답변 파일로 만들어",
            "다운로드 해줘",
            "make this a report",
            "export this",
        ):
            self.assertTrue(py_pat.search(phrase),
                            f"keyword regex did not match {phrase!r}")
        for non_phrase in (
            "안녕하세요",
            "팔란티어에 대해 알려줘",
            "What is RAG",
        ):
            self.assertIsNone(py_pat.search(non_phrase),
                              f"keyword regex incorrectly matched {non_phrase!r}")


if __name__ == "__main__":
    unittest.main()
