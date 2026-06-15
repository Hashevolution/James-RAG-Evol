"""v0.6.1 — core/llm_settings.py + routes/llm_settings.py tests.

Covers the DB-first / env-fallback / default resolution chain, the
schema validation, and the admin endpoint surface (partial write +
clear + 400/403).

Run:
  python -m unittest tests.test_v06_llm_settings
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _isolate_settings_db():
    """Point the module's DB at a fresh temp path + clear test-side
    state so each test starts with a known empty DB."""
    import core.llm_settings as L
    L._DB_PATH = tempfile.mktemp(prefix="james_ls_t_", suffix=".db")
    return L


def _scrub_env():
    for env in (
        "JAMES_LLM_MODEL", "JAMES_CODING_MODEL", "JAMES_VISION_MODEL",
        "JAMES_AUTO_ROUTER", "JAMES_AUTO_STYLE", "JAMES_BACKEND_TIER",
        "JAMES_BACKEND_SYNTH", "JAMES_AGENT_BACKEND",
        "JAMES_AGENT_OLLAMA_MODEL", "JAMES_AGENT_ANTHROPIC_MODEL",
    ):
        os.environ.pop(env, None)


class ResolutionChainTests(unittest.TestCase):
    def setUp(self):
        _scrub_env()
        self.L = _isolate_settings_db()

    def test_default_when_no_db_no_env(self):
        self.assertEqual(self.L.get("default_model"), "gemma4:e4b")
        self.assertTrue(self.L.get_bool("auto_router"))

    def test_env_takes_over_when_db_empty(self):
        os.environ["JAMES_LLM_MODEL"] = "gemma3:4b"
        self.assertEqual(self.L.get("default_model"), "gemma3:4b")

    def test_db_takes_precedence_over_env(self):
        os.environ["JAMES_LLM_MODEL"] = "gemma3:4b"
        self.L.set("default_model", "mxtral:latest", by="admin")
        self.assertEqual(self.L.get("default_model"), "mxtral:latest")

    def test_clear_falls_back_to_env(self):
        os.environ["JAMES_LLM_MODEL"] = "gemma3:4b"
        self.L.set("default_model", "mxtral:latest", by="admin")
        self.L.clear("default_model")
        self.assertEqual(self.L.get("default_model"), "gemma3:4b")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        _scrub_env()
        self.L = _isolate_settings_db()

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            self.L.set("nonsense", "x", by="a")

    def test_bad_bool_rejected(self):
        with self.assertRaises(ValueError):
            self.L.set("auto_router", "maybe", by="a")

    def test_bad_enum_rejected(self):
        with self.assertRaises(ValueError):
            self.L.set("agent_backend", "azure", by="a")

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):
            self.L.set("default_model", "x" * 300, by="a")

    def test_nul_byte_rejected(self):
        with self.assertRaises(ValueError):
            self.L.set("default_model", "x\x00y", by="a")


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        _scrub_env()
        self.L = _isolate_settings_db()

    def test_snapshot_shape(self):
        snap = self.L.as_dict()
        for k in ("settings", "db", "env", "defaults", "schema"):
            self.assertIn(k, snap)
        keys = [s["key"] for s in snap["schema"]]
        self.assertIn("default_model", keys)
        self.assertIn("agent_backend", keys)
        self.assertEqual(len(snap["schema"]), 10)


# ── HTTP endpoint ────────────────────────────────────────────────

def _make_client(role="admin"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.llm_settings as r
    from routes._helpers import get_role_from_request

    app = FastAPI()
    app.include_router(r.router)
    app.dependency_overrides[get_role_from_request] = lambda: role
    r._bearer_username = lambda request: "admin"
    r._require_admin = lambda api_key, role: None if role == "admin" else (
        _ for _ in ()
    ).throw(__import__("fastapi").HTTPException(status_code=403,
                                                  detail="admin only"))
    return TestClient(app), r


class EndpointTests(unittest.TestCase):
    def setUp(self):
        _scrub_env()
        self.L = _isolate_settings_db()

    def test_get_returns_snapshot(self):
        client, _ = _make_client()
        resp = client.get("/admin/llm-settings/?api_key=x")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("settings", body)
        self.assertIn("schema", body)

    def test_get_forbidden_for_non_admin(self):
        client, _ = _make_client(role="user")
        resp = client.get("/admin/llm-settings/?api_key=x")
        self.assertEqual(resp.status_code, 403)

    def test_post_partial_update(self):
        client, _ = _make_client()
        resp = client.post("/admin/llm-settings/", json={
            "api_key": "x",
            "settings": {"default_model": "mxtral:latest",
                         "auto_router": "0"},
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["written"]["default_model"], "mxtral:latest")
        self.assertEqual(body["written"]["auto_router"], "0")
        self.assertFalse(body["errors"])

    def test_post_clear_falls_back_to_env(self):
        client, _ = _make_client()
        # write then clear
        client.post("/admin/llm-settings/", json={
            "api_key": "x", "settings": {"default_model": "mxtral:latest"},
        })
        resp = client.post("/admin/llm-settings/", json={
            "api_key": "x", "settings": {}, "clear": ["default_model"],
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("default_model", resp.json()["cleared"])

    def test_post_all_errors_returns_400(self):
        client, _ = _make_client()
        resp = client.post("/admin/llm-settings/", json={
            "api_key": "x",
            "settings": {"auto_router": "maybe", "agent_backend": "azure"},
        })
        self.assertEqual(resp.status_code, 400)


class ServerRegistrationTests(unittest.TestCase):
    def test_routes_wired(self):
        import server_llmwiki
        paths = {getattr(r, "path", None) for r in server_llmwiki.app.routes}
        self.assertIn("/admin/llm-settings/", paths)


class Risk1_UseDBToggleTests(unittest.TestCase):
    """Risk #1 mitigation (2026-06-15): JAMES_SETTINGS_USE_DB=0 makes
    env source-of-truth so measurement runs cannot be silently
    shadowed by an operator's admin Settings change."""

    def setUp(self):
        _scrub_env()
        self.L = _isolate_settings_db()

    def tearDown(self):
        os.environ.pop("JAMES_SETTINGS_USE_DB", None)

    def test_toggle_default_is_db_first(self):
        os.environ["JAMES_LLM_MODEL"] = "gemma3:4b"
        self.L.set("default_model", "mxtral:latest", by="admin")
        self.assertEqual(self.L.get("default_model"), "mxtral:latest")

    def test_toggle_zero_skips_db(self):
        os.environ["JAMES_LLM_MODEL"] = "gemma3:4b"
        self.L.set("default_model", "mxtral:latest", by="admin")
        os.environ["JAMES_SETTINGS_USE_DB"] = "0"
        self.assertEqual(self.L.get("default_model"), "gemma3:4b")

    def test_toggle_accepts_false_and_friends(self):
        os.environ["JAMES_LLM_MODEL"] = "gemma3:4b"
        self.L.set("default_model", "mxtral:latest", by="admin")
        for val in ("false", "no", "off", "disabled", "0", "FALSE"):
            os.environ["JAMES_SETTINGS_USE_DB"] = val
            self.assertEqual(self.L.get("default_model"), "gemma3:4b", val)

    def test_toggle_unset_or_truthy_keeps_db(self):
        os.environ["JAMES_LLM_MODEL"] = "gemma3:4b"
        self.L.set("default_model", "mxtral:latest", by="admin")
        for val in ("", "1", "true", "yes"):
            if val:
                os.environ["JAMES_SETTINGS_USE_DB"] = val
            else:
                os.environ.pop("JAMES_SETTINGS_USE_DB", None)
            self.assertEqual(self.L.get("default_model"), "mxtral:latest", val)


if __name__ == "__main__":
    unittest.main()
