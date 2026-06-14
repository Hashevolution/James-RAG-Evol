"""v0.6 — core/templating/ingest.py tests (PR-5).

Covers the three template input modes that converge on a single raw
template-text string: text (verbatim), file (UTF-8 decode + extension
guard), and image (Tesseract OCR). The image path is exercised against
a real temp PNG with the actual OCR call stubbed, so the test stays
offline and does not require a Tesseract binary.

Run:
  python -m unittest tests.test_v06_templating_ingest
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.templating import (
    ingest_document,
    ingest_file,
    ingest_image,
    ingest_text,
)
from core.templating.store import TemplateStoreError

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:  # pragma: no cover - env without Pillow
    _HAS_PIL = False


class IngestTextTests(unittest.TestCase):
    def test_verbatim(self):
        self.assertEqual(ingest_text("# Title\n{{name}}\n"), "# Title\n{{name}}\n")

    def test_empty_rejected(self):
        for bad in ("", "   \n\t"):
            with self.assertRaises(TemplateStoreError):
                ingest_text(bad)


class IngestFileTests(unittest.TestCase):
    def test_md_decoded(self):
        out = ingest_file("# A\nbody\n".encode("utf-8"), "report.md")
        self.assertIn("body", out)

    def test_txt_decoded(self):
        self.assertEqual(ingest_file(b"hello", "notes.txt"), "hello")

    def test_unknown_ext_rejected(self):
        with self.assertRaises(TemplateStoreError):
            ingest_file(b"data", "form.pdf")

    def test_non_utf8_rejected(self):
        with self.assertRaises(TemplateStoreError):
            ingest_file(b"\xff\xfe\x00bad", "x.txt")

    def test_empty_file_rejected(self):
        with self.assertRaises(TemplateStoreError):
            ingest_file(b"   ", "x.txt")

    def test_no_extension_allowed(self):
        # An empty extension shouldn't trip the text-extension guard.
        self.assertEqual(ingest_file(b"plain", ""), "plain")


@unittest.skipUnless(_HAS_PIL, "Pillow required for image-mode tests")
class IngestImageTests(unittest.TestCase):
    def setUp(self):
        fd, self._png = tempfile.mkstemp(suffix=".png", prefix="james_ocr_test_")
        os.close(fd)
        Image.new("RGB", (8, 8), "white").save(self._png)

    def tearDown(self):
        if os.path.exists(self._png):
            os.remove(self._png)

    def test_ocr_success(self):
        with mock.patch("pytesseract.image_to_string",
                        return_value="# Form\n{{name}}\n"):
            out = ingest_image(self._png)
        self.assertIn("Form", out)

    def test_unknown_ext_rejected(self):
        with self.assertRaises(TemplateStoreError):
            ingest_image("/tmp/whatever.pdf")

    def test_empty_ocr_rejected(self):
        with mock.patch("pytesseract.image_to_string", return_value="   \n"):
            with self.assertRaises(TemplateStoreError):
                ingest_image(self._png)


class IngestDocumentTests(unittest.TestCase):
    """v0.6.1 — `ingest_document` (markitdown wrapper).

    The markitdown call is patched so the test stays offline and does
    not require a parser for every office format on the test runner."""

    def test_unknown_ext_rejected(self):
        with self.assertRaises(TemplateStoreError):
            ingest_document("/tmp/no-such.exe")

    def test_known_ext_calls_markitdown(self):
        captured = {}
        fake_result = mock.Mock(text_content="# 회의록\n참석자: 김지원\n")

        class FakeMD:
            def __init__(self):
                pass
            def convert(self, path):
                captured["path"] = path
                return fake_result

        with mock.patch.dict("sys.modules", {"markitdown": mock.Mock(MarkItDown=FakeMD)}):
            out = ingest_document("/tmp/sample.docx")
        self.assertIn("회의록", out)
        self.assertEqual(captured["path"], "/tmp/sample.docx")

    def test_hwp_failure_surfaces_explicit_workaround(self):
        """`.hwp` failures must point at the 한글 → .docx workaround,
        not silently return an empty string."""
        class FakeMD:
            def __init__(self):
                pass
            def convert(self, path):
                raise RuntimeError("unsupported")

        with mock.patch.dict("sys.modules", {"markitdown": mock.Mock(MarkItDown=FakeMD)}):
            with self.assertRaises(TemplateStoreError) as ctx:
                ingest_document("/tmp/sample.hwp")
        self.assertIn(".docx", str(ctx.exception))

    def test_empty_extraction_rejected(self):
        class FakeMD:
            def __init__(self):
                pass
            def convert(self, path):
                return mock.Mock(text_content="")

        with mock.patch.dict("sys.modules", {"markitdown": mock.Mock(MarkItDown=FakeMD)}):
            with self.assertRaises(TemplateStoreError):
                ingest_document("/tmp/empty.pdf")


if __name__ == "__main__":
    unittest.main()
