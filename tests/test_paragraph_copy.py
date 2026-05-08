"""Per-paragraph copy buttons (item #A4-A, 2026-05-08).

User feedback: "대화 내용중 핵심 답변 내용 문단을 복사할수 있게 버튼
별도로 붙이기".

Splits the answer into paragraphs (blank-line separated) and renders
each with its own 📋 copy button. Code blocks are kept intact within
their paragraph (don't split across them). Single-paragraph answers
skip the wrapper to avoid visual noise (the global copy button at
the bottom already covers the case).

JS contract:
  formatAnswerWithParagraphs(text)
    - splits on /\\n\\s*\\n+/
    - extracts ```code``` blocks first, restores after split
    - returns formatAnswer(text) untouched if ≤ 1 paragraph
    - emits <div class="paragraph"> with a .paragraph-copy-btn per part

CSS contract (in index.html):
  - .paragraph relative + margin-bottom
  - .paragraph-copy-btn absolute top-right, opacity 0
  - :hover reveals
  - mobile fallback: low-opacity always

Run:
  python -m unittest tests.test_paragraph_copy
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class JsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_function_exists(self):
        self.assertIn("function formatAnswerWithParagraphs", self.js,
                      "must define formatAnswerWithParagraphs")

    def test_used_by_appendJamesMsg(self):
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 8000
        body = self.js[idx:end]
        self.assertIn("formatAnswerWithParagraphs(answer)", body,
                      "appendJamesMsg should render via the paragraph splitter")
        self.assertNotIn("formatAnswer(answer)", body.replace(
            "formatAnswerWithParagraphs(answer)", ""),
            "must NOT call formatAnswer(answer) directly anymore")

    def test_function_handles_code_blocks(self):
        idx = self.js.index("function formatAnswerWithParagraphs")
        body = self.js[idx:idx + 2000]
        # Code blocks must be preserved across the split (otherwise
        # ```...``` markers would get severed).
        self.assertIn("```", body,
                      "must extract code blocks before splitting")
        self.assertIn("\\x01CB", body,
                      "must use a placeholder marker for code blocks")
        self.assertIn("[\\s\\S]*?", body,
                      "code-block regex must be multi-line (don't anchor on \\n)")

    def test_split_on_blank_lines(self):
        idx = self.js.index("function formatAnswerWithParagraphs")
        body = self.js[idx:idx + 2000]
        # Splitting must use blank-line regex.
        self.assertIn("\\n\\s*\\n", body,
                      "must split paragraphs on blank lines")

    def test_single_paragraph_skips_wrapper(self):
        idx = self.js.index("function formatAnswerWithParagraphs")
        body = self.js[idx:idx + 2000]
        # Edge case — single paragraph answers shouldn't get a per-para
        # copy button (visual noise; global copy button already covers it).
        self.assertIn("parts.length <= 1", body,
                      "must skip paragraph wrapping when <= 1 paragraph")
        self.assertIn("formatAnswer(text)", body,
                      "single-paragraph fallback calls original formatAnswer")

    def test_each_paragraph_has_copy_button(self):
        idx = self.js.index("function formatAnswerWithParagraphs")
        body = self.js[idx:idx + 2500]
        self.assertIn('class="paragraph"', body)
        self.assertIn('class="paragraph-copy-btn"', body)
        self.assertIn('onclick="copyAnswerText(this)"', body,
                      "must reuse copyAnswerText for paragraph copy")
        self.assertIn("encodeURIComponent(restored)", body,
                      "paragraph content must be URI-encoded for data attr")
        self.assertIn("paragraph-content", body,
                      "content wrapper needed for padding-right")


class CssContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_paragraph_styles_present(self):
        # The hover-show button needs CSS to actually hide/reveal —
        # inline styles can't do :hover.
        self.assertIn(".bubble .paragraph", self.html,
                      "missing .paragraph rule for positioning")
        self.assertIn(".paragraph-copy-btn", self.html,
                      "missing .paragraph-copy-btn rule")
        self.assertIn(".bubble .paragraph:hover .paragraph-copy-btn", self.html,
                      "missing :hover rule to reveal button")

    def test_mobile_fallback(self):
        # hover doesn't work on touch — button must be reachable.
        # We accept media query (hover: none) OR an active state fallback.
        has_hover_none = "(hover: none)" in self.html
        self.assertTrue(has_hover_none,
            "mobile fallback rule needed — @media (hover: none) ...")

    def test_button_position_absolute(self):
        # Locate the .paragraph-copy-btn block.
        m = re.search(r"\.paragraph-copy-btn\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("position: absolute", body,
                      "must position absolute (top-right of paragraph)")
        # Initial opacity 0 — invisible until hover.
        self.assertIn("opacity: 0", body)


class ParagraphSplitBehaviorTests(unittest.TestCase):
    """Behavioural simulation of formatAnswerWithParagraphs in Python.

    We extract the splitter logic and apply it in Python re — verifies
    the JS regex handles the documented inputs correctly."""

    def _split(self, text):
        # Mirror JS: extract code blocks → split → restore.
        codeblocks = []
        def _cb_replacer(m):
            codeblocks.append(m.group(0))
            return f"\x01CB{len(codeblocks) - 1}\x01"
        without_code = re.sub(r"```[\s\S]*?```", _cb_replacer, text)
        parts = [p.strip() for p in re.split(r"\n\s*\n+", without_code)]
        parts = [p for p in parts if p]
        for i in range(len(parts)):
            for j, b in enumerate(codeblocks):
                parts[i] = parts[i].replace(f"\x01CB{j}\x01", b)
        return parts

    def test_split_two_paragraphs(self):
        text = "첫 문단입니다.\n\n둘째 문단입니다."
        self.assertEqual(len(self._split(text)), 2)

    def test_three_paragraphs_with_blank_line(self):
        text = "## 결론\n핵심 답입니다.\n\n## 근거\n자료 X에서...\n\n## 추가\n한계는..."
        parts = self._split(text)
        self.assertEqual(len(parts), 3)
        self.assertIn("결론", parts[0])
        self.assertIn("근거", parts[1])

    def test_code_block_preserved_in_paragraph(self):
        text = "설명입니다.\n\n```python\ndef foo():\n    pass\n```\n\n끝."
        parts = self._split(text)
        self.assertEqual(len(parts), 3)
        self.assertIn("```python", parts[1],
                      "code block must stay intact (markers preserved)")
        self.assertIn("def foo", parts[1])

    def test_single_paragraph_returns_one_part(self):
        text = "한 줄짜리 답."
        self.assertEqual(len(self._split(text)), 1)


if __name__ == "__main__":
    unittest.main()
