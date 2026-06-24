"""v0.6.1 UX overhaul — directory browser + agent LLM settings + model
passthrough + session persistence.

No network. Ollama model list is stubbed.

Run:
  python -m unittest tests.test_v06_agent_ux
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_client(role="admin"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.agent_paths as ap
    import routes.agent_sessions as asr
    from routes._helpers import get_role_from_request

    app = FastAPI()
    app.include_router(ap.router)
    app.include_router(asr.router)
    app.dependency_overrides[get_role_from_request] = lambda: role
    ap._bearer_username = lambda request: "admin"
    asr._bearer_username = lambda request: "admin"
    _noop = lambda api_key, role: None
    ap._require_admin = _noop
    asr._require_admin = _noop
    return TestClient(app)


# ── Directory browser ──────────────────────────────────────────────

class BrowseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="james_browse_")
        os.makedirs(os.path.join(self._tmp, "sub_a"))
        os.makedirs(os.path.join(self._tmp, "sub_b"))
        with open(os.path.join(self._tmp, "f.txt"), "w") as f:
            f.write("x")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_roots_listed(self):
        c = _make_client()
        r = c.get("/admin/agent/browse", params={"api_key": "x"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["current"], "")
        self.assertTrue(len(r.json()["entries"]) >= 1)

    def test_subdirs_only_no_files(self):
        c = _make_client()
        r = c.get("/admin/agent/browse", params={"api_key": "x", "path": self._tmp})
        self.assertEqual(r.status_code, 200, r.text)
        names = [e["name"] for e in r.json()["entries"]]
        self.assertIn("sub_a", names)
        self.assertIn("sub_b", names)
        self.assertNotIn("f.txt", names)        # files excluded
        self.assertTrue(r.json()["registerable"])

    def test_critical_root_not_registerable(self):
        c = _make_client()
        crit = "C:\\Windows" if os.name == "nt" else "/etc"
        if not os.path.isdir(crit):
            self.skipTest("critical root not present")
        r = c.get("/admin/agent/browse", params={"api_key": "x", "path": crit})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["registerable"])

    def test_nonexistent_path_404(self):
        c = _make_client()
        bogus = os.path.join(self._tmp, "nope_xyz")
        r = c.get("/admin/agent/browse", params={"api_key": "x", "path": bogus})
        self.assertEqual(r.status_code, 404)


# ── Agent LLM settings ─────────────────────────────────────────────

class LLMSettingsTests(unittest.TestCase):
    def setUp(self):
        # Stub the ollama model list so no network is needed.
        import routes.llm as llm
        self._orig = llm._list_installed_ollama_models
        llm._list_installed_ollama_models = lambda: {"mxtral:latest", "gemma3:12b"}
        os.environ["JAMES_SETTINGS_USE_DB"] = "0"   # env/default, no DB writes
        # Defensive: ensure no leaked agent-backend env from another test
        # class makes ls.get("agent_backend") resolve to non-default.
        self._prev_be = os.environ.pop("JAMES_AGENT_BACKEND", None)

    def tearDown(self):
        import routes.llm as llm
        llm._list_installed_ollama_models = self._orig
        os.environ.pop("JAMES_SETTINGS_USE_DB", None)
        if self._prev_be is not None:
            os.environ["JAMES_AGENT_BACKEND"] = self._prev_be

    def test_get_returns_models_and_defaults(self):
        c = _make_client()
        r = c.get("/admin/agent/llm-settings", params={"api_key": "x"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["backend"], "ollama")
        self.assertIn("mxtral:latest", body["installed_ollama_models"])
        self.assertIn("shell_enabled", body)

    def test_set_invalid_backend_rejected(self):
        c = _make_client()
        r = c.post("/admin/agent/llm-settings",
                   json={"api_key": "x", "backend": "madeup"})
        self.assertEqual(r.status_code, 400)

    def test_set_valid_model_with_db(self):
        # Use a temp DB so the write doesn't touch the real one.
        os.environ.pop("JAMES_SETTINGS_USE_DB", None)
        import core.llm_settings as ls
        tmpdb = tempfile.mkdtemp(prefix="james_ls_")
        orig = ls._DB_PATH
        ls._DB_PATH = os.path.join(tmpdb, "t.db")
        try:
            c = _make_client()
            r = c.post("/admin/agent/llm-settings",
                       json={"api_key": "x", "ollama_model": "gemma3:12b"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(ls.get("agent_ollama_model"), "gemma3:12b")
        finally:
            ls._DB_PATH = orig
            shutil.rmtree(tmpdb, ignore_errors=True)
            os.environ["JAMES_SETTINGS_USE_DB"] = "0"


# ── Model passthrough ──────────────────────────────────────────────

class ModelPassthroughTests(unittest.TestCase):
    def test_ollama_model_override(self):
        from core.agent_tools.backends import get_backend, OllamaBackend
        b = get_backend("ollama", "gemma3:27b")
        self.assertIsInstance(b, OllamaBackend)
        self.assertEqual(b.model, "gemma3:27b")

    def test_empty_model_falls_back(self):
        from core.agent_tools.backends import get_backend
        os.environ["JAMES_SETTINGS_USE_DB"] = "0"
        os.environ.pop("JAMES_AGENT_OLLAMA_MODEL", None)
        try:
            b = get_backend("ollama", "")
            self.assertTrue(b.model)        # non-empty default
        finally:
            os.environ.pop("JAMES_SETTINGS_USE_DB", None)


# ── Session persistence ────────────────────────────────────────────

class SessionTests(unittest.TestCase):
    def setUp(self):
        import core.agent_sessions as asx
        self._tmpdb = tempfile.mkdtemp(prefix="james_sess_")
        self._orig = asx._DB_PATH
        asx._DB_PATH = os.path.join(self._tmpdb, "s.db")

    def tearDown(self):
        import core.agent_sessions as asx
        asx._DB_PATH = self._orig
        shutil.rmtree(self._tmpdb, ignore_errors=True)

    def test_crud_round_trip(self):
        c = _make_client()
        # create
        r = c.post("/admin/agent/sessions", json={"api_key": "x", "title": "T1"})
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.json()["session"]["id"]
        # list
        r = c.get("/admin/agent/sessions", params={"api_key": "x"})
        self.assertEqual(len(r.json()["sessions"]), 1)
        # update with messages
        msgs = [{"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"}]
        r = c.put(f"/admin/agent/sessions/{sid}",
                  json={"api_key": "x", "title": "T2", "messages": msgs})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["session"]["msg_count"], 2)
        # get
        r = c.get(f"/admin/agent/sessions/{sid}", params={"api_key": "x"})
        self.assertEqual(r.json()["session"]["title"], "T2")
        self.assertEqual(len(r.json()["session"]["messages"]), 2)
        # delete
        r = c.delete(f"/admin/agent/sessions/{sid}", params={"api_key": "x"})
        self.assertTrue(r.json()["removed"])
        r = c.get(f"/admin/agent/sessions/{sid}", params={"api_key": "x"})
        self.assertEqual(r.status_code, 404)

    def test_get_missing_404(self):
        c = _make_client()
        r = c.get("/admin/agent/sessions/nope", params={"api_key": "x"})
        self.assertEqual(r.status_code, 404)

    def test_bad_messages_coerced(self):
        import core.agent_sessions as asx
        s = asx.create_session("x")
        out = asx.update_session(s["id"], messages=[
            {"role": "user", "content": "ok"},
            {"role": "user"},                 # missing content → dropped
            "not-a-dict",                     # dropped
            {"content": "no role"},           # dropped
        ])
        self.assertEqual(out["msg_count"], 1)


if __name__ == "__main__":
    unittest.main()
