"""Python file (.py) export support (item #A4-B, 2026-05-08).

User feedback: "대화에서 파일로 제시하라고 할때 워드 파일,
파이썬 코딩 파일 등 제시할수 있는 성능이 되는지 확인".

Existing /export/ supports md / txt / docx (PR #93). This adds .py
so users can save coding-mode answers directly as runnable Python.

Strategy:
  - When the answer has fenced ```python``` (or ```py```/```) blocks,
    the .py output is just the concatenated code. User gets clean
    runnable Python without manually scraping the prose.
  - When no fenced blocks exist, prose is escaped as `#`-prefixed
    comments. The file imports cleanly (no syntax error) and acts
    as a self-describing reference.
  - Export header always includes the timestamp + source so the
    file is self-describing.

Frontend:
  - .py button auto-appears when answer contains ```...``` regardless
    of the report-request flag. Coding answers always offer it.
  - When the user said "파일로/보고서로", the full set (.md/.docx/.txt)
    plus .py shows up.

Run:
  python -m unittest tests.test_py_export
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class PyExporterTests(unittest.TestCase):
    """tools/export/document_exporter.py — _export_py + integration."""

    @classmethod
    def setUpClass(cls):
        from tools.export import document_exporter as dx
        cls.dx = dx

    def test_py_in_supported_formats(self):
        self.assertIn("py", self.dx.SUPPORTED_FORMATS,
                      "py must be a recognised export format")

    def test_py_mime_and_extension(self):
        self.assertEqual(self.dx._MIME_BY_FORMAT["py"],
                         "text/x-python; charset=utf-8")
        self.assertEqual(self.dx._EXT_BY_FORMAT["py"], ".py")

    def test_export_py_extracts_python_blocks(self):
        content = (
            "여기 함수입니다.\n\n"
            "```python\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n\n"
            "그리고 사용 예:\n"
            "```py\n"
            "print(add(1, 2))\n"
            "```\n"
        )
        result = self.dx.export_document(content, format="py")
        self.assertEqual(result.actual_format, "py")
        self.assertEqual(result.fallback_reason, "")
        self.assertTrue(result.filename.endswith(".py"))
        body = result.data.decode("utf-8")
        self.assertIn("def add(a, b):", body)
        self.assertIn("print(add(1, 2))", body)
        # The prose ("여기 함수입니다") should NOT leak into the .py body.
        self.assertNotIn("여기 함수입니다", body,
            "non-fenced prose should not appear when code blocks exist")

    def test_export_py_unspecified_lang_block_treated_as_code(self):
        # ``` ... ``` (no language) — operator-friendly: many LLMs omit
        # the lang tag. We accept these blocks too.
        content = (
            "분석:\n\n"
            "```\n"
            "import sys\n"
            "print(sys.version)\n"
            "```\n"
        )
        result = self.dx.export_document(content, format="py")
        body = result.data.decode("utf-8")
        self.assertIn("import sys", body)
        self.assertIn("print(sys.version)", body)

    def test_export_py_no_code_falls_back_to_comments(self):
        # Pure-prose answer → escape every line as `# comment` so the
        # file imports cleanly and reads as documentation.
        content = "이것은 코드가 없는 답변입니다.\n\n2번째 문단."
        result = self.dx.export_document(content, format="py")
        self.assertEqual(result.actual_format, "py",
            "no fallback to md when prose-only — comments are valid Python")
        body = result.data.decode("utf-8")
        # Each non-empty line should start with '#'.
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            self.assertTrue(stripped.startswith("#"),
                f"prose line not commented out: {line!r}")
        # Content should still be preserved.
        self.assertIn("코드가 없는 답변", body)

    def test_export_py_header_has_timestamp(self):
        result = self.dx.export_document("```py\nx=1\n```", format="py")
        body = result.data.decode("utf-8")
        # Header line should mention "Exported from JAMES" and have a date.
        self.assertIn("Exported from JAMES", body)
        self.assertRegex(body, r"\d{4}-\d{2}-\d{2}",
            "timestamp must be ISO-style YYYY-MM-DD")

    def test_export_py_long_prose_line_split(self):
        # Lines >200 chars get split so flake8/pylint don't fire on
        # every line of the resulting .py.
        long_line = "긴 문장입니다. " * 30   # ~270+ chars
        content = long_line
        result = self.dx.export_document(content, format="py")
        body = result.data.decode("utf-8")
        for line in body.splitlines():
            self.assertLess(len(line), 200,
                f"line longer than 200 chars: len={len(line)}")


class FrontendPyButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_py_button_in_appendJamesMsg(self):
        # The button literal must reference 'py' format with code-block
        # detection.
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 8000
        body = self.js[idx:end]
        self.assertIn("exportAnswer(this, 'py')", body,
                      ".py export button missing")
        self.assertIn("hasCodeBlock", body,
                      "must detect code blocks before showing .py button")
        self.assertIn("```", body,
                      "must check for fenced code blocks in answer")

    def test_py_button_shown_independently_of_report_keyword(self):
        # The user shouldn't have to type "파이썬 파일로" to get .py — if
        # the answer has code blocks, we offer it.
        idx = self.js.index("const pyExportBtn")
        body = self.js[idx:idx + 600]
        self.assertIn("hasCodeBlock", body,
                      "py button gated on hasCodeBlock, not pendingReportRequest")


if __name__ == "__main__":
    unittest.main()
