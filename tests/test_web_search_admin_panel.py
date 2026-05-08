"""Web search admin config — role permission + threshold (item #A6-1).

User feedback (2026-05-08):
  (a) admin 외 user role도 웹 검색 허용 가능 — 어드민 페이지에서 role별
      설정 가능 여부 조정.
  (b) TAVILY_API_KEY 미설정 시 어드민에 토스트 경고.
  (d) low_relevance threshold 0.30 — 어떻게 조정하면 좋을지 admin 가능.

Backend:
  - core/web_search_config.py — JSON-backed config with VALID_ROLES,
    load(), save(), is_role_allowed(), get_threshold(), validate_update().
  - /admin/web-search-config/ GET + POST endpoints (admin-gated).
  - core/reasoning/pipeline.py reads is_role_allowed + get_threshold
    instead of hardcoded 'admin' + 0.30.

Frontend:
  - admin.html settings page — Web Search section with role
    checkboxes + threshold slider + engine status display.
  - admin.js loadWebSearchConfig + saveWebSearchConfig.
  - When TAVILY_API_KEY missing + DDG active, toast warning fires
    once on admin page settings load.

Run:
  python -m unittest tests.test_web_search_admin_panel
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class WebSearchConfigModuleTests(unittest.TestCase):
    """core/web_search_config.py — JSON-backed settings."""

    def setUp(self):
        # Each test gets a temp config file so we don't touch the
        # real one in the working dir.
        self.tmpdir = tempfile.mkdtemp()
        self.cfg_path = os.path.join(self.tmpdir, "web_search_config.json")
        # Patch _CONFIG_PATH for the test.
        from core import web_search_config as wsc
        self.wsc = wsc
        self._orig_path = wsc._CONFIG_PATH
        wsc._CONFIG_PATH = self.cfg_path

    def tearDown(self):
        self.wsc._CONFIG_PATH = self._orig_path
        if os.path.exists(self.cfg_path):
            os.unlink(self.cfg_path)
        os.rmdir(self.tmpdir)

    def test_defaults_when_no_file(self):
        cfg = self.wsc.load()
        self.assertEqual(cfg["allowed_roles"], ["admin"])
        self.assertEqual(cfg["threshold"], 0.30)

    def test_save_then_load_roundtrip(self):
        self.wsc.save(["admin", "manager"], 0.45)
        cfg = self.wsc.load()
        self.assertEqual(cfg["allowed_roles"], ["admin", "manager"])
        self.assertAlmostEqual(cfg["threshold"], 0.45)

    def test_corrupt_file_falls_back_to_defaults(self):
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            f.write("not json {")
        cfg = self.wsc.load()
        self.assertEqual(cfg["allowed_roles"], ["admin"])
        self.assertEqual(cfg["threshold"], 0.30)

    def test_unknown_roles_filtered_out_on_load(self):
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump({"allowed_roles": ["admin", "wizard"]}, f)
        cfg = self.wsc.load()
        self.assertEqual(cfg["allowed_roles"], ["admin"],
            "unknown roles must be silently filtered, valid kept")

    def test_empty_allowed_roles_after_filter_uses_default(self):
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump({"allowed_roles": ["wizard"]}, f)
        cfg = self.wsc.load()
        # After filtering, list is empty → restore default.
        self.assertEqual(cfg["allowed_roles"], ["admin"],
            "empty list after filter must restore default (don't lock everyone out)")

    def test_threshold_out_of_range_rejected_on_load(self):
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump({"threshold": 5.0}, f)
        cfg = self.wsc.load()
        self.assertEqual(cfg["threshold"], 0.30,
            "out-of-range threshold must fall back to default")

    def test_is_role_allowed(self):
        self.wsc.save(["admin", "manager"], 0.30)
        self.assertTrue(self.wsc.is_role_allowed("admin"))
        self.assertTrue(self.wsc.is_role_allowed("manager"))
        self.assertFalse(self.wsc.is_role_allowed("employee"))
        self.assertFalse(self.wsc.is_role_allowed(""))

    def test_get_threshold(self):
        self.wsc.save(["admin"], 0.42)
        self.assertAlmostEqual(self.wsc.get_threshold(), 0.42)

    def test_validate_update_rejects_unknown_role(self):
        _, _, err = self.wsc.validate_update(["admin", "wizard"], 0.30)
        self.assertIn("unknown role", err)

    def test_validate_update_rejects_empty_list(self):
        _, _, err = self.wsc.validate_update([], 0.30)
        self.assertIn("cannot be empty", err)

    def test_validate_update_rejects_out_of_range(self):
        _, _, err = self.wsc.validate_update(["admin"], 1.5)
        self.assertIn("[0.0, 1.0]", err)

    def test_validate_update_accepts_valid(self):
        roles, t, err = self.wsc.validate_update(
            ["admin", "manager"], 0.4
        )
        self.assertEqual(err, "")
        self.assertEqual(roles, ["admin", "manager"])
        self.assertAlmostEqual(t, 0.4)


class PipelineUsesConfigTests(unittest.TestCase):
    """pipeline.py must read from core.web_search_config, not hardcode."""

    @classmethod
    def setUpClass(cls):
        from core.reasoning import pipeline
        cls.src = inspect.getsource(pipeline)

    def test_imports_config_helpers(self):
        self.assertIn("from core.web_search_config import", self.src,
            "pipeline.py must import is_role_allowed + get_threshold")
        self.assertIn("get_threshold", self.src)
        self.assertIn("is_role_allowed", self.src)

    def test_threshold_constant_replaced(self):
        # The hardcoded literal `unified_score < 0.30` should be gone
        # — replaced by `unified_score < get_threshold()`.
        self.assertNotIn("unified_score < 0.30", self.src,
            "hardcoded 0.30 threshold must be replaced by get_threshold()")
        self.assertIn("unified_score < get_threshold()", self.src,
            "must call get_threshold() in low_relevance check")

    def test_role_check_uses_helper(self):
        # `if user_role == "admin"` → `if is_role_allowed(user_role)`.
        self.assertIn("is_role_allowed(user_role)", self.src,
            "role gate must call is_role_allowed, not hardcode admin")
        # Make sure the previous hardcoded check is no longer in the
        # web-search branch (it could still appear elsewhere).
        # Locate the web search block and check inside.
        m = re.search(
            r"is_role_allowed\(user_role\).+?print\(f\"\[WEB\]",
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m,
            "is_role_allowed must gate the WEB log path")


class AdminEndpointTests(unittest.TestCase):
    """server_llmwiki.py — /admin/web-search-config/ GET + POST."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_get_endpoint_registered(self):
        self.assertIn('@app.get("/admin/web-search-config/"', self.src,
            "GET /admin/web-search-config/ must be registered")

    def test_post_endpoint_registered(self):
        self.assertIn('@app.post("/admin/web-search-config/"', self.src,
            "POST /admin/web-search-config/ must be registered")

    def test_post_admin_gated(self):
        # Find POST handler body, must require admin.
        m = re.search(
            r'@app\.post\("/admin/web-search-config/".+?'
            r'@app\.|\Z',
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn("_require_admin", body,
            "POST must call _require_admin")

    def test_post_validates_via_helper(self):
        m = re.search(
            r'@app\.post\("/admin/web-search-config/".+?'
            r'@app\.|\Z',
            self.src, re.DOTALL,
        )
        body = m.group(0)
        self.assertIn("validate_update", body,
            "POST must call validate_update for input checks")
        self.assertIn("status_code=400", body,
            "validation error must produce 400")


class FrontendAdminPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "admin.html").read_text(encoding="utf-8")
        cls.js   = (ROOT / "frontend" / "static" / "admin.js").read_text(encoding="utf-8")

    def test_html_section_present(self):
        self.assertIn("Web Search", self.html,
            "admin.html settings page must contain Web Search section")
        self.assertIn('id="ws-threshold"', self.html,
            "threshold slider missing")
        self.assertIn('class="ws-role-cb"', self.html,
            "role checkboxes missing")
        self.assertIn('id="web-search-status-display"', self.html,
            "engine status display target missing")

    def test_load_function_exists(self):
        self.assertIn("async function loadWebSearchConfig", self.js)
        self.assertIn("'/admin/web-search-config/'", self.js,
            "loadWebSearchConfig must hit /admin/web-search-config/")

    def test_save_function_exists(self):
        self.assertIn("async function saveWebSearchConfig", self.js)
        idx = self.js.index("async function saveWebSearchConfig")
        body = self.js[idx:idx + 1500]
        self.assertIn(".ws-role-cb", body,
            "save must read role checkbox state")
        self.assertIn("threshold", body)

    def test_loadSettings_chains_web_config(self):
        # When admin enters settings page, both core settings + web
        # search config should load.
        idx = self.js.index("async function loadSettings")
        body = self.js[idx:idx + 4500]
        self.assertIn("loadWebSearchConfig", body,
            "loadSettings must also trigger loadWebSearchConfig")

    def test_tavily_missing_toast_warning(self):
        # When tavily_key=false + active=duckduckgo, frontend shows
        # a toast warning. We just check the conditional + toast
        # call exist.
        idx = self.js.index("async function loadWebSearchConfig")
        body = self.js[idx:idx + 2500]
        self.assertIn("tavily_key", body,
            "must inspect engine_status.tavily_key")
        self.assertIn("TAVILY_API_KEY", body,
            "warning copy must mention the env var name")
        self.assertIn("toast", body,
            "must call toast() helper for the warning")


if __name__ == "__main__":
    unittest.main()
