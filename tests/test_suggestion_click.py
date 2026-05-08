"""Next-action suggestion chips (item #1-B, 2026-05-08).

User feedback: "답변 대화창에 자메스가 다음 제안하는 방식은 사용자가
클릭 선택하면 자동으로 질문될수 있도록 설정".

PR #89's natural-flow rule already produces "다음 중 어떤 걸
원하시나요? (1) ... (2) ... (3) ..." at the end of complex
answers. This PR makes those numbered options interactive:
parses them out of the answer text, renders as clickable chips,
clicks fill the input and auto-send.

Coverage:
  - extractNextActionSuggestions(text) parses "(1) X (2) Y (3) Z"
    inline and "(1) X\\n(2) Y\\n(3) Z" multi-line.
  - Tail-only matching — body-middle "(1) 첫째" is not mistaken for
    a suggestion.
  - Min 2 suggestions required — single "(1)" rejected.
  - Length bounds: each suggestion 4-200 chars.
  - askSuggestion(idx, btn) reads data-suggestion (URI-decoded),
    fills input, calls sendMessage with a small delay (UX —
    user can intercept).
  - chip rendering inside appendJamesMsg with onclick wired.

Run:
  python -m unittest tests.test_suggestion_click
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JS = Path(__file__).resolve().parent.parent / "frontend" / "static" / "chat.js"


class SuggestionExtractionTests(unittest.TestCase):
    """Behavioral parity: regex pattern in JS must match the
    documented inputs/outputs. We mirror the JS regex in Python re."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        # Extract the regex literal from JS source.
        # Pattern: const re = /...../g;
        m = re.search(r"const\s+re\s*=\s*/(.+?)/g\s*;", cls.js)
        assert m, "could not locate suggestion regex literal"
        cls.py_pat = re.compile(m.group(1))

    def _extract(self, text):
        # Simulate the JS function's tail-restriction (last 600 chars).
        tail = text[-600:] if len(text) > 600 else text
        out = []
        for m in self.py_pat.finditer(tail):
            t = m.group(2).strip().rstrip(".。")
            if 4 <= len(t) <= 200:
                out.append({"n": int(m.group(1)), "text": t})
            if len(out) >= 5:
                break
        return out if len(out) >= 2 else []

    def test_inline_three_options_parsed(self):
        text = "답변 본문... 다음 중 어떤 걸 원하시나요? (1) BlackRock 자세히 (2) 비트코인 ETF 출시 시점 (3) 다른 회사들"
        s = self._extract(text)
        self.assertEqual(len(s), 3)
        self.assertEqual(s[0]["text"], "BlackRock 자세히")
        self.assertIn("ETF", s[1]["text"])

    def test_multiline_options_parsed(self):
        text = "답변... (1) 첫번째 옵션\n(2) 두번째 옵션\n(3) 세번째 옵션"
        s = self._extract(text)
        self.assertEqual(len(s), 3)

    def test_min_two_suggestions(self):
        # Single "(1) something" should NOT be rendered as a chip
        # — could be body content, not a next-action list.
        text = "답변 본문 (1) 첫째로 X를 한다. 본문 계속..."
        s = self._extract(text)
        self.assertEqual(s, [],
                         "single (1) must not be promoted to suggestions")

    def test_short_suggestion_rejected(self):
        # 4-char min — "(1) X (2) Y" is too short to be useful.
        text = "(1) X (2) Y (3) Z"
        s = self._extract(text)
        self.assertEqual(s, [],
                         "very-short single-token suggestions rejected")

    def test_long_suggestion_truncated(self):
        # 200-char max — anything past that is body text being misread.
        long_text = "(1) " + ("a" * 250) + " (2) bbbb (3) cccc"
        s = self._extract(long_text)
        # The 250-char one rejected; (2)/(3) accepted but len < 2 filter
        # keeps them paired. Behavior: at most we get 2 items if both
        # pass — here (1) excluded, so we have (2) + (3).
        self.assertEqual(len(s), 2)
        for item in s:
            self.assertLessEqual(len(item["text"]), 200)


class JsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_extract_function_exists(self):
        self.assertIn("function extractNextActionSuggestions", self.js)

    def test_ask_suggestion_function(self):
        self.assertIn("function askSuggestion", self.js)
        idx = self.js.index("function askSuggestion")
        body = self.js[idx:idx + 1500]
        self.assertIn("dataset.suggestion", body,
                      "askSuggestion must read data-suggestion attribute")
        self.assertIn("decodeURIComponent", body,
                      "data-suggestion is URI-encoded; must decode")
        self.assertIn("sendMessage()", body,
                      "askSuggestion must trigger send")
        self.assertIn("setTimeout", body,
                      "small delay before send so user can intercept")

    def test_chip_rendered_in_message(self):
        # appendJamesMsg builds suggestionsHtml with chips.
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 8000
        body = self.js[idx:end]
        self.assertIn("next-action-chip", body,
                      "chip class missing from rendered HTML")
        self.assertIn('onclick="askSuggestion(', body,
                      "chip must be wired to askSuggestion")
        self.assertIn("data-suggestion=", body,
                      "chip must carry data-suggestion attribute")

    def test_tail_only_matching(self):
        # Function should only look at the tail of the answer to
        # avoid matching body-mid "(1) 첫째" content.
        self.assertIn("slice(-600)", self.js,
                      "extraction must restrict to answer tail (600 chars)")


if __name__ == "__main__":
    unittest.main()
