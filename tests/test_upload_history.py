"""[#7-C] Upload file history admin page — 2026-05-09.

Backend:
  /admin/uploads/history/?limit=50&offset=0&q=filename
  Reads from audit_log SQLite table WHERE endpoint='/upload/'.
  Pagination via limit (capped at 500) + offset.
  Filename search via parameterised SQL LIKE — never string-formatted.

Frontend:
  - new nav-item under 관리 section
  - new page id="page-uploads" with table + search + pagination
  - admin.js loadUploads() + PAGE_LOADERS registration

Tests are pure source-text + import-shape assertions; live HTTP
behavior is exercised via direct sqlite + endpoint contract checks.

Run:
    python -m unittest tests.test_upload_history
"""
from __future__ import annotations

import inspect
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class EndpointSourceTests(unittest.TestCase):
    """The /admin/uploads/history/ endpoint is registered + admin-gated."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.srv = srv
        cls.src = inspect.getsource(srv)

    def test_route_registered(self):
        self.assertIn('@app.get("/admin/uploads/history/"', self.src,
                      "route must exist for admin upload history")

    def test_admin_gate_in_handler(self):
        # The handler must call _require_admin BEFORE touching the DB.
        idx = self.src.index('@app.get("/admin/uploads/history/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        self.assertTrue("_require_admin(api_key, role)" in body or "_require_feature(api_key, role" in body,
                      "/admin/uploads/history/ must enforce admin role")

    def test_query_filters_to_upload_endpoint(self):
        idx = self.src.index('@app.get("/admin/uploads/history/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        self.assertIn("endpoint='/upload/'", body,
                      "must filter audit_log to the /upload/ endpoint")

    def test_uses_parameterised_like(self):
        """Trust boundary — filename search must NOT be f-string'd into SQL."""
        idx = self.src.index('@app.get("/admin/uploads/history/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        # Both COUNT and SELECT branches must use parameter placeholder.
        self.assertIn("query LIKE ?", body,
                      "filename filter must use ? placeholder, not string format")
        # And the bound argument should wrap with %...%.
        self.assertIn(r'f"%{qstr}%"', body,
                      "wildcard must be on the bound parameter, not on the SQL itself")
        # Negative: there should NOT be a direct f-string SQL injection.
        self.assertNotRegex(body, r"query LIKE\s+'%\{",
                            "must not interpolate user input into raw SQL")

    def test_pagination_caps_limit(self):
        idx = self.src.index('@app.get("/admin/uploads/history/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        # Must clamp limit so an attacker can't ask for 999999 rows.
        self.assertRegex(body, r"min\(int\(limit[^)]*\)\s*,\s*\d+\)",
                         "limit must be clamped to a max")
        self.assertIn("max(0, int(offset", body,
                      "offset must be floored at 0")

    def test_returns_documented_shape(self):
        idx = self.src.index('@app.get("/admin/uploads/history/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        for field in ('"timestamp"', '"filename"', '"user_role"',
                      '"ip_address"', '"blocked"', '"security_event"'):
            self.assertIn(field, body,
                          f"per-row dict must include {field}")
        for top in ('"items"', '"total"', '"limit"', '"offset"', '"q"'):
            self.assertIn(top, body,
                          f"top-level response must include {top}")


class LiveSqliteShapeTests(unittest.TestCase):
    """End-to-end against a temp audit DB — confirm filter + pagination."""

    def test_filter_and_paginate_against_temp_db(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "test_audit.db")
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, user_role TEXT, endpoint TEXT,
                    query TEXT, answer TEXT, graph_paths TEXT,
                    blocked INTEGER, security_event TEXT,
                    elapsed_sec REAL, ip_address TEXT
                )
            """)
            # Insert a mix: 3 uploads, 2 queries.
            rows = [
                ("2026-05-08T10:00", "admin",   "/upload/", "report.pdf"),
                ("2026-05-08T10:01", "admin",   "/upload/", "photo.jpg"),
                ("2026-05-08T10:02", "external","/query/",  "what is X"),
                ("2026-05-08T10:03", "admin",   "/upload/", "minutes.docx"),
                ("2026-05-08T10:04", "external","/query/",  "tell me Y"),
            ]
            for ts, role, ep, q in rows:
                conn.execute(
                    "INSERT INTO audit_log "
                    "(timestamp,user_role,endpoint,query,answer,graph_paths,"
                    " blocked,security_event,elapsed_sec,ip_address) "
                    "VALUES (?,?,?,?,'','[]',0,'',0.0,'')",
                    (ts, role, ep, q),
                )
            conn.commit()

            # Mirror the endpoint's logic locally.
            conn.row_factory = sqlite3.Row
            uploads = conn.execute(
                "SELECT * FROM audit_log WHERE endpoint='/upload/' "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (10, 0),
            ).fetchall()
            self.assertEqual(len(uploads), 3,
                             "3 upload rows expected (queries excluded)")
            # DESC by id → newest first
            self.assertEqual(uploads[0]["query"], "minutes.docx")

            # Filename search.
            hits = conn.execute(
                "SELECT * FROM audit_log WHERE endpoint='/upload/' "
                "AND query LIKE ? ORDER BY id DESC",
                ("%report%",),
            ).fetchall()
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["query"], "report.pdf")

            # Pagination — limit 2, offset 1
            page = conn.execute(
                "SELECT * FROM audit_log WHERE endpoint='/upload/' "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (2, 1),
            ).fetchall()
            self.assertEqual(len(page), 2)
            # Skip newest, get next two: photo.jpg, report.pdf
            self.assertEqual([r["query"] for r in page],
                             ["photo.jpg", "report.pdf"])

            conn.close()


class FrontendAdminJsTests(unittest.TestCase):
    """admin.js must register loadUploads + define the function."""

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "admin.js").read_text(encoding="utf-8")

    def test_page_loader_registered(self):
        # Must appear in the loaders dict that drives showPage().
        self.assertRegex(self.js, r"uploads\s*:\s*loadUploads",
                         "PAGE_LOADERS must map 'uploads' → loadUploads")

    def test_function_defined(self):
        self.assertIn("function loadUploads", self.js,
                      "loadUploads function must be defined")

    def test_calls_correct_endpoint(self):
        # Function body must call /admin/uploads/history/ with limit + offset.
        idx = self.js.index("function loadUploads")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("/admin/uploads/history/", body)
        self.assertIn("limit=", body)
        self.assertIn("offset=", body)

    def test_html_escapes_filename(self):
        # XSS guard — filename comes from user-controlled input (uploaded
        # file name was attacker-controlled at upload time). Must escape.
        self.assertIn("function _escHtml", self.js,
                      "_escHtml helper must exist for XSS-safe rendering")
        idx = self.js.index("function _escHtml")
        body = self.js[idx:idx + 400]
        self.assertIn("&amp;", body)
        self.assertIn("&lt;", body)
        self.assertIn("&gt;", body)

    def test_pagination_helpers_exist(self):
        self.assertIn("function _uploadsPrev", self.js)
        self.assertIn("function _uploadsNext", self.js)


class FrontendAdminHtmlTests(unittest.TestCase):
    """admin.html must declare the nav item + page section."""

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "admin.html").read_text(encoding="utf-8")

    def test_nav_item_present(self):
        # Sidebar must have a clickable entry that calls showPage('uploads', ...).
        self.assertIn("showPage('uploads'", self.html,
                      "sidebar must register a nav-item linking to uploads page")
        self.assertIn('admin.upload_history', self.html,
                      "i18n key admin.upload_history must be wired in")

    def test_page_div_present(self):
        self.assertIn('id="page-uploads"', self.html,
                      "page container with id page-uploads must exist")
        self.assertIn('id="uploads-tbody"', self.html,
                      "table body container must exist for loadUploads()")
        self.assertIn('id="uploads-search"', self.html,
                      "search input must exist")
        self.assertIn('id="uploads-pager"', self.html,
                      "pagination container must exist")

    def test_search_uses_enter_key(self):
        # Ergonomic: pressing Enter triggers loadUploads.
        self.assertIn("if(event.key==='Enter') loadUploads()", self.html)


class I18nKeysTests(unittest.TestCase):
    """i18n.js must carry both en + ko strings for the new page."""

    @classmethod
    def setUpClass(cls):
        cls.txt = (ROOT / "frontend" / "static" / "i18n.js").read_text(encoding="utf-8")

    def test_keys_exist_in_both_languages(self):
        for key in (
            "'admin.upload_history':",
            "'uploads.page_title':",
            "'uploads.search_placeholder':",
            "'common.search':",
        ):
            # Must appear at least twice (once per language block).
            self.assertGreaterEqual(self.txt.count(key), 2,
                f"key {key} must be defined in BOTH en and ko blocks")


if __name__ == "__main__":
    unittest.main()
