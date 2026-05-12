"""Next-action suggestion chips (item #1-B / #A1, 2026-05-08).

User feedback round 1: "답변 대화창에 자메스가 다음 제안하는 방식은 사용자가
클릭 선택하면 자동으로 질문될수 있도록 설정".
User feedback round 2: "선택지가 일단 제시되면 클릭 가능하도록 개선" —
LLM이 (1)/1)/1./① 등 다양한 포맷으로 답해서 chip이 간헐적으로 안 나옴.

PR #110 (round 1) extracted "(N) text" only. This file's tests cover
the multi-format expansion (#A1): SUGGESTION_PATTERNS array tries
strict → right-paren → period-numbered → circled-digit, takes the
first format that yields ≥2 suggestions.

Coverage:
  - SUGGESTION_PATTERNS array with 4 regex literals.
  - "(1) X (2) Y (3) Z"   strict — original format
  - "1) X 2) Y 3) Z"      right-paren only
  - "1. X\\n2. Y\\n3. Z"  numbered-list format
  - "① X ② Y ③ Z"          circled-digit format
  - Min 2 suggestions per pattern; otherwise fall through to next.
  - Length bounds: each suggestion 4-200 chars.
  - Tail-only matching — body-middle "(1) 첫째" not mistaken.
  - askSuggestion(idx, btn) reads data-suggestion (URI-decoded),
    fills input, calls sendMessage with a small delay.
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


def _extract_patterns(js_src: str):
    """Pull each regex literal out of the SUGGESTION_PATTERNS array.

    The JS source declares:
        const SUGGESTION_PATTERNS = [
          /pattern1/g,
          /pattern2/g,
          ...
        ];

    We grab the array body and re-extract each `/.../g` literal.
    """
    arr = re.search(
        r"const\s+SUGGESTION_PATTERNS\s*=\s*\[(.+?)\];",
        js_src,
        re.DOTALL,
    )
    assert arr, "SUGGESTION_PATTERNS array literal not found"
    body = arr.group(1)
    pats = re.findall(r"/(.+?)/g", body)
    return [re.compile(p) for p in pats]


class SuggestionExtractionTests(unittest.TestCase):
    """Behavioral parity: each regex in SUGGESTION_PATTERNS must match
    the documented inputs/outputs. We mirror the JS extraction in Python."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        cls.py_pats = _extract_patterns(cls.js)
        # Sanity — we expect 4 patterns currently.
        assert len(cls.py_pats) >= 4, \
            f"expected ≥4 patterns in SUGGESTION_PATTERNS, got {len(cls.py_pats)}"

    def _extract(self, text):
        # Simulate the JS function's tail-restriction (last 600 chars)
        # plus the multi-pattern fallback.
        tail = text[-600:] if len(text) > 600 else text
        for py_pat in self.py_pats:
            out = []
            for m in py_pat.finditer(tail):
                t = m.group(2).strip().rstrip(".。")
                if 4 <= len(t) <= 200:
                    if not any(o["text"] == t for o in out):
                        out.append({"n": len(out) + 1, "text": t})
                if len(out) >= 5:
                    break
            if len(out) >= 2:
                return out
        return []

    # ── pattern 1: "(1) X (2) Y (3) Z" ──
    def test_inline_paren_three_options_parsed(self):
        text = "답변 본문... 다음 중 어떤 걸 원하시나요? (1) BlackRock 자세히 (2) 비트코인 ETF 출시 시점 (3) 다른 회사들"
        s = self._extract(text)
        self.assertEqual(len(s), 3)
        self.assertEqual(s[0]["text"], "BlackRock 자세히")
        self.assertIn("ETF", s[1]["text"])

    def test_multiline_paren_options_parsed(self):
        text = "답변... (1) 첫번째 옵션\n(2) 두번째 옵션\n(3) 세번째 옵션"
        s = self._extract(text)
        self.assertEqual(len(s), 3)

    # ── pattern 2: "1) X 2) Y 3) Z" right-paren only (LLM 자주 출력) ──
    def test_right_paren_only_format(self):
        text = "본문 답변. 더 알아볼 항목: 1) BlackRock 추가 분석 2) 비트코인 ETF 시기 3) 경쟁사 비교"
        s = self._extract(text)
        self.assertGreaterEqual(len(s), 2,
            "1) X 2) Y format must yield ≥2 chips")
        self.assertIn("BlackRock", s[0]["text"])

    # ── pattern 3: "1. X\n2. Y\n3. Z" 다행 번호 목록 ──
    def test_period_numbered_list_format(self):
        text = (
            "본문 답변.\n\n"
            "다음 제안:\n"
            "1. BlackRock 추가 정보 확인\n"
            "2. 비트코인 ETF 출시 시기\n"
            "3. 경쟁사 비교 분석\n"
        )
        s = self._extract(text)
        self.assertGreaterEqual(len(s), 2,
            "numbered-list format (1.\\n2.\\n3.) must yield chips")

    # ── pattern 4: "① X ② Y ③ Z" 원문자 ──
    def test_circled_digit_format(self):
        text = "본문... 추가 질문: ① BlackRock 자세히 ② 비트코인 ETF 시점 ③ 경쟁사 비교"
        s = self._extract(text)
        self.assertGreaterEqual(len(s), 2,
            "circled-digit format must yield chips")

    # ── 거짓-매칭 방지 ──
    def test_min_two_suggestions(self):
        # Single "(1) something" should NOT be rendered as chip.
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
        long_text = "(1) " + ("a" * 250) + " (2) bbbb (3) cccc"
        s = self._extract(long_text)
        # 250-char (1) rejected; (2) and (3) accepted.
        self.assertEqual(len(s), 2)
        for item in s:
            self.assertLessEqual(len(item["text"]), 200)


class JsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_extract_function_exists(self):
        self.assertIn("function extractNextActionSuggestions", self.js)

    def test_patterns_array_declared(self):
        # The new structure — multi-pattern fallback.
        self.assertIn("SUGGESTION_PATTERNS", self.js,
            "must export SUGGESTION_PATTERNS array for multi-format fallback")
        # ≥4 regex literals inside the array.
        arr = re.search(
            r"const\s+SUGGESTION_PATTERNS\s*=\s*\[(.+?)\];",
            self.js, re.DOTALL,
        )
        self.assertIsNotNone(arr)
        n_patterns = len(re.findall(r"/.+?/g", arr.group(1)))
        self.assertGreaterEqual(n_patterns, 4,
            f"expected ≥4 fallback patterns, got {n_patterns}")

    def test_function_iterates_patterns(self):
        idx = self.js.index("function extractNextActionSuggestions")
        body = self.js[idx:idx + 1500]
        # Must loop through patterns and return early on first ≥2 hit.
        self.assertIn("for (const re of SUGGESTION_PATTERNS", body,
            "must iterate patterns")
        self.assertIn("re.lastIndex = 0", body,
            "must reset lastIndex (regex with /g flag is stateful)")
        self.assertIn(">= 2", body,
            "must require ≥2 to accept a pattern's result")

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
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 8000
        body = self.js[idx:end]
        self.assertIn("next-action-chip", body,
                      "chip class missing from rendered HTML")
        # [§5 migration] inline onclick → data-action; delegate parses
        # data-index and forwards (index, button) to askSuggestion.
        self.assertIn('data-action="ask-suggestion"', body,
                      "chip must carry data-action=ask-suggestion")
        self.assertIn("data-index=", body,
                      "chip must carry data-index for delegate to forward")
        self.assertIn("data-suggestion=", body,
                      "chip must carry data-suggestion attribute")

    def test_tail_only_matching(self):
        self.assertIn("slice(-600)", self.js,
                      "extraction must restrict to answer tail (600 chars)")


if __name__ == "__main__":
    unittest.main()
