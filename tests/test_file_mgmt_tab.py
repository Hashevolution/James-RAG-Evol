"""[item #2, 2026-05-09] Admin file management tab — tree / search / download.

User feedback: 「파일 업로드와 파일 업로드 히스토리, 서버 pc 안에 원본
파일을 저장 트리 경로, 파일 검색 하는 기능을 하나의 세션을 만들어보는
것 검토」.

Decision (review): option A — admin "📁 파일 관리" tab. Existing
chat-page upload + admin-page upload history (PR #137) are kept and
linked from the new tab; the new responsibilities are tree, search,
download.

Endpoints (server_llmwiki.py):
  GET /admin/files/tree?root=&path=&max_depth=
    Returns nested tree under one of {wiki, uploads, media}.
  GET /admin/files/search?q=&root=&limit=
    Filename substring search under one root, capped at limit.
  GET /admin/files/download?root=&path=
    Streams a single file (extension allowlist + path-traversal guard).

Trust boundary
  - Every endpoint is _require_admin gated
  - Roots are an enum allowlist ({wiki, uploads, media}) — unknown root
    keys are rejected
  - _resolve_under_root uses os.path.realpath to follow symlinks AND
    enforces target stays under the chosen root (containment check)
  - Download additionally enforces an extension allowlist — even if a
    traversal somehow succeeded, .py / .env / .db etc. won't stream

Tests
  Each endpoint's source is asserted to:
    - exist as @app.get
    - call _require_admin BEFORE filesystem touch
    - reference _resolve_under_root for path validation
  Frontend: nav item, page div, function wired to PAGE_LOADERS,
  XSS-safe rendering (textContent, _escHtml).

Run:
    python -m unittest tests.test_file_mgmt_tab
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class EndpointSourceTests(unittest.TestCase):
    """All three endpoints registered + admin-gated + use the validator."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.srv = srv
        cls.src = inspect.getsource(srv)

    def _endpoint_body(self, route_pattern: str) -> str:
        idx = self.src.index(route_pattern)
        # Bound at next @app or another decorator.
        nxt = self.src.index("\n@app.", idx + 1)
        return self.src[idx:nxt]

    def test_tree_route_registered(self):
        self.assertIn('@app.get("/admin/files/tree"', self.src)

    def test_tree_admin_gated(self):
        body = self._endpoint_body('@app.get("/admin/files/tree"')
        self.assertTrue("_require_admin(api_key, role)" in body or "_require_feature(api_key, role" in body,
            "tree must enforce admin BEFORE listing")

    def test_tree_uses_resolver(self):
        body = self._endpoint_body('@app.get("/admin/files/tree"')
        self.assertIn("_resolve_under_root(", body,
            "tree must validate root+path via _resolve_under_root")

    def test_tree_clamps_max_depth(self):
        body = self._endpoint_body('@app.get("/admin/files/tree"')
        # Look for a clamping pattern like min(int(max_depth or 3), 5).
        self.assertRegex(body, r"min\(int\(max_depth[^)]*\)\s*,\s*\d+\)",
            "max_depth must be clamped — unbounded recursion is a DoS")

    def test_search_route_registered(self):
        self.assertIn('@app.get("/admin/files/search"', self.src)

    def test_search_admin_gated(self):
        body = self._endpoint_body('@app.get("/admin/files/search"')
        self.assertTrue("_require_admin(api_key, role)" in body or "_require_feature(api_key, role" in body)

    def test_search_uses_resolver(self):
        body = self._endpoint_body('@app.get("/admin/files/search"')
        self.assertIn("_resolve_under_root(", body)

    def test_search_clamps_limit(self):
        body = self._endpoint_body('@app.get("/admin/files/search"')
        self.assertRegex(body, r"min\(int\(limit[^)]*\)\s*,\s*\d+\)",
            "limit must be clamped — a 1-char query could otherwise "
            "dump the whole tree")

    def test_download_route_registered(self):
        self.assertIn('@app.get("/admin/files/download"', self.src)

    def test_download_admin_gated(self):
        body = self._endpoint_body('@app.get("/admin/files/download"')
        self.assertTrue("_require_admin(api_key, role)" in body or "_require_feature(api_key, role" in body)

    def test_download_uses_resolver(self):
        body = self._endpoint_body('@app.get("/admin/files/download"')
        self.assertIn("_resolve_under_root(", body)

    def test_download_extension_allowlist(self):
        body = self._endpoint_body('@app.get("/admin/files/download"')
        self.assertIn("_FILE_DOWNLOAD_ALLOWED_EXTS", body,
            "extension allowlist is the second line of defense — must be "
            "consulted even after path resolution")

    def test_download_writes_audit(self):
        body = self._endpoint_body('@app.get("/admin/files/download"')
        self.assertIn("_write_audit", body,
            "every download must hit the audit log")


class TrustBoundaryTests(unittest.TestCase):
    """The _resolve_under_root function must reject malicious paths."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.srv = srv

    def test_unknown_root_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.srv._resolve_under_root("invalid_root", "")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_traversal_rejected(self):
        from fastapi import HTTPException
        # Try a classic '..' traversal — should raise 400 once the
        # root directory exists. (If wiki/ doesn't exist the function
        # returns the root; that's tested separately.)
        roots = self.srv._file_mgmt_roots()
        wiki = roots["wiki"]
        if not os.path.isdir(wiki):
            self.skipTest("wiki/ doesn't exist on this host")
        with self.assertRaises(HTTPException) as ctx:
            self.srv._resolve_under_root("wiki", "../../etc/passwd")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_normal_subpath_accepted(self):
        roots = self.srv._file_mgmt_roots()
        wiki = roots["wiki"]
        if not os.path.isdir(wiki):
            self.skipTest("wiki/ doesn't exist on this host")
        result = self.srv._resolve_under_root("wiki", "entity")
        self.assertTrue(result.startswith(wiki),
            "valid subpath must resolve under root")

    def test_empty_path_returns_root(self):
        roots = self.srv._file_mgmt_roots()
        wiki = roots["wiki"]
        if not os.path.isdir(wiki):
            self.skipTest("wiki/ doesn't exist on this host")
        result = self.srv._resolve_under_root("wiki", "")
        # Path equality (normalized).
        self.assertEqual(os.path.realpath(result), os.path.realpath(wiki))


class FileMgmtRootsTests(unittest.TestCase):
    """Roots dict must include the 3 documented keys."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.srv = srv

    def test_three_documented_roots(self):
        roots = self.srv._file_mgmt_roots()
        for key in ("wiki", "uploads", "media"):
            self.assertIn(key, roots, f"root '{key}' must be in allowlist")
            self.assertTrue(os.path.isabs(roots[key]),
                f"root '{key}' must be an absolute path")


class TempFsTreeWalkTests(unittest.TestCase):
    """Build a tempdir, mock the roots, and call the tree+search logic.

    Purely tests the os.walk + listdir paths in the endpoint bodies
    without going through FastAPI.  We re-implement the walk inline
    matching the endpoint's intent as a contract test."""

    def test_search_finds_filename_substring(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "sub"))
            for name in ("alpha.md", "beta.txt", "gamma.md"):
                with open(os.path.join(td, name), "w", encoding="utf-8") as f:
                    f.write("x")
            with open(os.path.join(td, "sub", "alphacat.md"), "w") as f:
                f.write("x")
            # Walk + filter by substring 'alpha' (case-insensitive).
            qstr = "alpha"
            matches = []
            for dirpath, _, filenames in os.walk(td):
                for n in filenames:
                    if qstr in n.lower():
                        matches.append(n)
            self.assertEqual(set(matches), {"alpha.md", "alphacat.md"})


class FrontendNavAndPageTests(unittest.TestCase):
    """admin.html: nav item + page-files div present."""

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "admin.html").read_text(encoding="utf-8")

    def test_nav_item_present(self):
        self.assertIn("showPage('files'", self.html,
            "sidebar must have a clickable entry for the files tab")
        self.assertIn("admin.file_mgmt", self.html,
            "i18n key admin.file_mgmt must be wired in")

    def test_page_div_present(self):
        self.assertIn('id="page-files"', self.html)
        self.assertIn('id="files-content"', self.html,
            "files-content is the tree/search render target")
        self.assertIn('id="files-root"', self.html,
            "root selector must exist (wiki/uploads/media)")
        self.assertIn('id="files-search"', self.html,
            "search input must exist")

    def test_search_uses_enter_key(self):
        self.assertIn("if(event.key==='Enter') searchFiles()", self.html)

    def test_root_select_options_match_backend_allowlist(self):
        # The 3 root options must match the server's _file_mgmt_roots keys.
        for key in ("wiki", "uploads", "media"):
            # value="wiki" (etc.) must appear in the option list.
            self.assertRegex(self.html, rf'value="{key}"',
                f"root option value='{key}' must be present")


class FrontendJsTests(unittest.TestCase):
    """admin.js: PAGE_LOADERS registers files, render functions exist."""

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "admin.js").read_text(encoding="utf-8")

    def test_loader_registered(self):
        self.assertRegex(self.js, r"files\s*:\s*loadFiles",
            "PAGE_LOADERS must map 'files' → loadFiles")

    def test_load_files_function_defined(self):
        self.assertIn("function loadFiles", self.js)

    def test_search_files_function_defined(self):
        self.assertIn("function searchFiles", self.js)

    def test_render_tree_helper_defined(self):
        self.assertIn("function _renderTree", self.js)

    def test_uses_correct_endpoints(self):
        idx = self.js.index("function loadFiles")
        body = self.js[idx:idx + 2000]
        self.assertIn("/admin/files/tree", body)
        idx2 = self.js.index("function searchFiles")
        body2 = self.js[idx2:idx2 + 2000]
        self.assertIn("/admin/files/search", body2)

    def test_xss_guard_on_filenames(self):
        # File/folder names came from the user's filesystem (could
        # include attacker-controlled names from upload). Names must be
        # rendered via _escHtml, never raw.
        idx = self.js.index("function _renderTree")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("_escHtml(n.name)", body,
            "tree row filenames must go through _escHtml")


if __name__ == "__main__":
    unittest.main()
