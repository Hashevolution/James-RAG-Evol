"""v0.6 — core/templating formatter + render tests (PR-2).

The LLM call is stubbed (no live model). Covers:
  * build_format_prompt is pure + carries the no-fabrication instruction
  * format_content wires through call_router and strips/validates output
  * format_content raises on empty/error LLM responses
  * render produces md/txt verbatim + escaped JS-free html
  * prompt-injection: imperative text in inputs stays as data

Run:
  python -m unittest tests.test_v06_templating_formatter_render
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BuildPromptTests(unittest.TestCase):
    def test_prompt_carries_structure_and_no_fabrication_rule(self):
        from core.templating.spec import parse_template
        from core.templating.formatter import build_format_prompt
        spec = parse_template("# Title\n## Sub\n{{author}}\n")
        prompt = build_format_prompt("some raw content", spec)
        self.assertIn("Title", prompt)
        self.assertIn("author", prompt)
        self.assertIn("some raw content", prompt)
        # grounding discipline must be present in the instruction
        self.assertIn("Do not invent", prompt)
        # template provided as data + ignore-instructions guard
        self.assertIn("strictly as data", prompt)

    def test_prompt_is_pure(self):
        from core.templating.spec import parse_template
        from core.templating.formatter import build_format_prompt
        spec = parse_template("# A\n")
        a = build_format_prompt("x", spec)
        b = build_format_prompt("x", spec)
        self.assertEqual(a, b)


class FormatContentTests(unittest.TestCase):
    def _patch_router(self, fn):
        import llm.router as router
        self._orig = router.call_router
        router.call_router = fn
        self.addCleanup(lambda: setattr(router, "call_router", self._orig))

    def test_happy_path(self):
        captured = {}

        def fake(prompt, **kw):
            captured["prompt"] = prompt
            captured["kw"] = kw
            return "  # Title\nformatted body\n  "

        self._patch_router(fake)
        from core.templating.formatter import format_content
        out = format_content("raw stuff", template_raw="# Title\n{{x}}\n")
        self.assertEqual(out, "# Title\nformatted body")
        self.assertEqual(captured["kw"].get("task_type"), "template_format")
        self.assertFalse(captured["kw"].get("use_cache"))

    def test_empty_response_raises(self):
        self._patch_router(lambda prompt, **kw: "   ")
        from core.templating.formatter import format_content
        with self.assertRaises(RuntimeError):
            format_content("raw", template_raw="# T\n")

    def test_error_response_raises(self):
        self._patch_router(lambda prompt, **kw: "Gemma 오류: timeout")
        from core.templating.formatter import format_content
        with self.assertRaises(RuntimeError):
            format_content("raw", template_raw="# T\n")

    def test_empty_raw_content_rejected(self):
        self._patch_router(lambda prompt, **kw: "x")
        from core.templating.formatter import format_content
        with self.assertRaises(ValueError):
            format_content("   ", template_raw="# T\n")


class RenderTests(unittest.TestCase):
    def test_md_txt_verbatim(self):
        from core.templating.render import render
        self.assertEqual(render("hello", "md"), b"hello")
        self.assertEqual(render("hello", "txt"), b"hello")

    def test_html_escaped_and_js_free(self):
        from core.templating.render import render
        out = render("<script>alert(1)</script>", "html").decode("utf-8")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("<!DOCTYPE html>", out)

    def test_bad_format_raises(self):
        from core.templating.render import render, extension_for
        with self.assertRaises(ValueError):
            render("x", "pdf")
        with self.assertRaises(ValueError):
            extension_for("docx")

    def test_extension_for(self):
        from core.templating.render import extension_for
        self.assertEqual(extension_for("md"), ".md")
        self.assertEqual(extension_for("html"), ".html")


if __name__ == "__main__":
    unittest.main()
