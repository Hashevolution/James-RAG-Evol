"""Document export — tools/export/document_exporter + /export/ endpoint
(item #4, 2026-05-08 user feedback).

Coverage:
  - export_document for md / txt / docx (success + python-docx
    fallback to md when the dep is missing).
  - export_document for unknown / pdf format (graceful md fallback
    with documented `fallback_reason`).
  - _safe_filename strips path traversal, control chars, caller-
    supplied extension; clamps length; gives a default for empty.
  - Round-trip: md/txt bytes are valid utf-8 and round-trip equal
    to the input (md is passthrough; txt is sanitized but never
    raises on Korean / emoji / long content).
  - Source-level: /export/ endpoint POST exists, accepts the
    documented body fields, sends Content-Disposition.

Run:
  python -m unittest tests.test_document_export
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SafeFilenameTests(unittest.TestCase):
    def test_strips_path_traversal(self):
        from tools.export.document_exporter import _safe_filename
        for raw, expected_substring_check in [
            ("../../etc/passwd",        "passwd"),
            ("..\\..\\system32\\evil",  "evil"),
            ("/absolute/path/file",     "file"),
        ]:
            got = _safe_filename(raw)
            self.assertNotIn("/", got)
            self.assertNotIn("\\", got)
            self.assertNotIn("..", got)

    def test_strips_user_extension(self):
        from tools.export.document_exporter import _safe_filename
        # We own format → caller's `.exe` / `.docx` etc must be removed.
        self.assertNotIn(".exe", _safe_filename("malicious.exe"))
        self.assertNotIn(".docx", _safe_filename("foo.docx"))
        # But internal dots elsewhere are fine.
        self.assertIn("v1", _safe_filename("notes.v1.draft"))

    def test_strips_control_chars(self):
        from tools.export.document_exporter import _safe_filename
        got = _safe_filename("name\x00with\x01nulls\x1f")
        self.assertNotIn("\x00", got)
        self.assertNotIn("\x01", got)
        self.assertNotIn("\x1f", got)

    def test_clamp_length(self):
        from tools.export.document_exporter import _safe_filename
        long_in = "a" * 500
        got = _safe_filename(long_in)
        self.assertLessEqual(len(got), 80)

    def test_default_when_all_bad(self):
        from tools.export.document_exporter import _safe_filename
        got = _safe_filename("///\\\\<<>>")
        self.assertNotEqual(got, "")
        self.assertEqual(got, "james_answer")


class ExportDocumentTests(unittest.TestCase):
    def test_md_passthrough(self):
        from tools.export.document_exporter import export_document
        content = "# Title\n\n- bullet 한글\n\nparagraph 1234"
        r = export_document(content, format="md")
        self.assertEqual(r.actual_format, "md")
        self.assertEqual(r.fallback_reason, "")
        self.assertTrue(r.filename.endswith(".md"))
        self.assertEqual(r.data.decode("utf-8"), content)
        self.assertIn("text/markdown", r.mime)

    def test_txt_strips_markdown_markers(self):
        from tools.export.document_exporter import export_document
        content = "# Header\n\n**bold** and _italic_\n\n- bullet"
        r = export_document(content, format="txt")
        self.assertEqual(r.actual_format, "txt")
        text = r.data.decode("utf-8")
        # Header marker stripped.
        self.assertNotIn("# Header", text)
        self.assertIn("Header", text)
        # **bold** → bold (no asterisks on a sole-bold line).
        # The regex preserves the inner word.
        self.assertIn("bold", text)
        # Bullet "- " → "• "
        self.assertIn("• bullet", text)

    def test_docx_falls_back_to_md_when_unavailable(self):
        # python-docx is NOT in this venv (verified by docstring run
        # earlier). Confirm fallback behavior is documented + clean.
        from tools.export.document_exporter import export_document
        content = "# Title\n\nbody"
        r = export_document(content, format="docx")
        try:
            import docx  # noqa: F401
            python_docx_available = True
        except ImportError:
            python_docx_available = False
        if python_docx_available:
            self.assertEqual(r.actual_format, "docx")
            self.assertGreater(len(r.data), 100,
                               "docx blob must be non-trivial")
        else:
            self.assertEqual(r.actual_format, "md",
                             "docx requested but python-docx missing → md")
            self.assertIn("python-docx", r.fallback_reason)
            self.assertIn("pip install", r.fallback_reason)

    def test_pdf_documented_as_deferred(self):
        from tools.export.document_exporter import export_document, PDF_DEFERRED_NOTE
        r = export_document("anything", format="pdf")
        self.assertEqual(r.actual_format, "md")
        self.assertEqual(r.fallback_reason, PDF_DEFERRED_NOTE)
        self.assertIn("v0.3", r.fallback_reason,
                      "fallback reason must point to the deferral version")

    def test_unknown_format_falls_back_to_md(self):
        from tools.export.document_exporter import export_document
        r = export_document("x", format="xlsx-totally-invalid")
        self.assertEqual(r.actual_format, "md")
        self.assertIn("unsupported format", r.fallback_reason)

    def test_korean_content_roundtrips(self):
        from tools.export.document_exporter import export_document
        content = "# 한글 제목\n\n안녕 자메스. **굵게** _기울임_ `code`"
        for fmt in ("md", "txt"):
            r = export_document(content, format=fmt)
            # Bytes decode as utf-8 — never errors. The exact post-
            # transform text differs per format but must always be
            # well-formed.
            r.data.decode("utf-8")  # raises UnicodeDecodeError on bad output

    def test_default_filename_is_timestamped(self):
        from tools.export.document_exporter import export_document
        r = export_document("x", format="md")
        self.assertTrue(r.filename.startswith("james_answer_"))
        self.assertTrue(r.filename.endswith(".md"))

    def test_caller_filename_sanitized(self):
        from tools.export.document_exporter import export_document
        r = export_document("x", format="md", filename="../../evil.exe")
        self.assertTrue(r.filename.endswith(".md"))
        self.assertNotIn("..", r.filename)
        self.assertNotIn(".exe", r.filename)


class ExportEndpointSourceContractTests(unittest.TestCase):
    """Source-level: /export/ endpoint exists, accepts api_key /
    content / format / filename, sets Content-Disposition with a
    sanitized ASCII fallback + utf-8 RFC 5987 filename* form."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_endpoint_registered(self):
        self.assertIn('@app.post("/export/"', self.src,
                      "/export/ POST endpoint missing")

    def test_endpoint_validates_api_key(self):
        idx = self.src.index('@app.post("/export/"')
        body = self.src[idx:idx + 2500]
        self.assertIn("verify_api_key(api_key)", body,
                      "/export/ must validate api_key")

    def test_endpoint_calls_export_document(self):
        idx = self.src.index('@app.post("/export/"')
        body = self.src[idx:idx + 2500]
        self.assertIn("from tools.export.document_exporter import export_document", body)
        self.assertIn("export_document(content, format=fmt", body)

    def test_content_disposition_has_utf8_form(self):
        idx = self.src.index('@app.post("/export/"')
        body = self.src[idx:idx + 2500]
        self.assertIn('Content-Disposition', body)
        self.assertIn("filename*=UTF-8''", body,
                      "RFC 5987 utf-8 filename form must be present "
                      "so Korean filenames survive the download header")

    def test_size_cap_enforced(self):
        idx = self.src.index('@app.post("/export/"')
        body = self.src[idx:idx + 2500]
        # 1MB cap is a small DoS guard.
        self.assertIn("1_000_000", body,
                      "/export/ must cap content size to avoid memory DoS")
        self.assertIn("status_code=413", body,
                      "oversize content must return HTTP 413")


if __name__ == "__main__":
    unittest.main()
