"""W4-Q1 — feature registry + PolicyEngine.can_use_feature + endpoints.

Three layers:
  1. core.feature_registry — pure DB roundtrip.
  2. PolicyEngine.can_use_feature — override > default > fail-closed.
  3. HTTP endpoints — /admin/features/{list,override,reset}.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-feature-registry-suite-32chars",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _seed_schema(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL,
            active        INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_overrides (
            feature_id  TEXT NOT NULL,
            role        TEXT NOT NULL,
            allowed     INTEGER NOT NULL,
            updated_at  INTEGER NOT NULL,
            updated_by  TEXT,
            PRIMARY KEY (feature_id, role)
        )
    """)
    conn.commit()
    conn.close()


def _api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


class _FixtureBase(unittest.TestCase):
    def setUp(self):
        from core import auth as auth_mod
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        _seed_schema(self.db)
        self._saved = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.db

    def tearDown(self):
        from core import auth as auth_mod
        auth_mod._DB_PATH = self._saved
        Path(self.db).unlink(missing_ok=True)


class CatalogTests(unittest.TestCase):
    """Module-import time validation."""

    def test_every_default_role_is_in_allowed_roles(self):
        # Constructor raises on unknown roles; if the module imported
        # without error, every feature is well-formed.
        from core.feature_registry import FEATURES
        from core.auth import ALLOWED_ROLES
        for fid, feat in FEATURES.items():
            self.assertTrue(
                feat.default_allowed.issubset(ALLOWED_ROLES),
                f"{fid} has role not in ALLOWED_ROLES: "
                f"{feat.default_allowed - set(ALLOWED_ROLES)}",
            )

    def test_admin_users_default_is_admin_only(self):
        from core.feature_registry import FEATURES
        self.assertEqual(FEATURES["admin.users"].default_allowed,
                         frozenset({"admin"}))

    def test_query_basic_open_to_everyone(self):
        from core.feature_registry import FEATURES, ALLOWED_ROLES
        self.assertEqual(FEATURES["query.basic"].default_allowed,
                         frozenset(ALLOWED_ROLES))


class StorageTests(_FixtureBase):
    def test_get_override_returns_none_when_empty(self):
        from core.feature_registry import get_override
        self.assertIsNone(get_override("upload.file", "employee"))

    def test_set_then_get_roundtrip(self):
        from core.feature_registry import set_override, get_override
        self.assertTrue(set_override("upload.file", "employee", True,
                                     updated_by="test-admin"))
        self.assertEqual(get_override("upload.file", "employee"), True)

    def test_set_override_upserts(self):
        from core.feature_registry import set_override, get_override
        set_override("upload.file", "employee", True)
        set_override("upload.file", "employee", False)
        self.assertEqual(get_override("upload.file", "employee"), False)

    def test_set_rejects_unknown_feature(self):
        from core.feature_registry import set_override
        self.assertFalse(set_override("nope.such.feature", "admin", True))

    def test_set_rejects_unknown_role(self):
        from core.feature_registry import set_override
        self.assertFalse(set_override("upload.file", "wizard", True))

    def test_clear_override_removes_row(self):
        from core.feature_registry import (
            set_override, clear_override, get_override,
        )
        set_override("upload.file", "employee", True)
        self.assertTrue(clear_override("upload.file", "employee"))
        self.assertIsNone(get_override("upload.file", "employee"))

    def test_clear_returns_false_when_no_row(self):
        from core.feature_registry import clear_override
        self.assertFalse(clear_override("upload.file", "employee"))

    def test_clear_all_overrides_for_feature(self):
        from core.feature_registry import (
            set_override, clear_all_overrides_for, get_override,
        )
        set_override("upload.file", "manager",  True)
        set_override("upload.file", "employee", True)
        set_override("graph.view",  "external", True)
        n = clear_all_overrides_for("upload.file")
        self.assertEqual(n, 2)
        # Other feature untouched.
        self.assertEqual(get_override("graph.view", "external"), True)
        # upload.file rows gone.
        self.assertIsNone(get_override("upload.file", "manager"))


class PolicyEngineCanUseFeatureTests(_FixtureBase):
    def test_default_allow(self):
        from core.policy_engine import default_engine
        d = default_engine.can_use_feature("admin", "admin.users")
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "default.allow")
        self.assertEqual(d.applied_rule, "policy.feature.admin.users")

    def test_default_deny(self):
        from core.policy_engine import default_engine
        d = default_engine.can_use_feature("employee", "admin.users")
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "default.deny")

    def test_override_grants_role_outside_default_set(self):
        from core.policy_engine import default_engine
        from core.feature_registry import set_override
        set_override("upload.file", "employee", True)
        d = default_engine.can_use_feature("employee", "upload.file")
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "override.allow")

    def test_override_revokes_default_grant(self):
        from core.policy_engine import default_engine
        from core.feature_registry import set_override
        set_override("query.basic", "external", False)
        d = default_engine.can_use_feature("external", "query.basic")
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "override.deny")

    def test_unknown_feature_fails_closed(self):
        from core.policy_engine import default_engine
        d = default_engine.can_use_feature("admin", "totally.fake")
        self.assertFalse(d.allowed,
                         "fail-closed on unknown feature_id — typo at a "
                         "call site must not silently authorize")
        self.assertEqual(d.reason, "unknown_feature")


class ListEffectiveTests(_FixtureBase):
    def test_shape_with_no_overrides(self):
        from core.feature_registry import list_effective
        rows = list_effective()
        # One row per feature in the catalog.
        self.assertTrue(any(r["id"] == "upload.file" for r in rows))
        upload = next(r for r in rows if r["id"] == "upload.file")
        self.assertIn("admin",   upload["effective"])
        self.assertEqual(upload["effective"]["admin"]["source"], "default")
        self.assertEqual(upload["effective"]["external"]["allowed"], False)

    def test_override_surfaces_with_source_override(self):
        from core.feature_registry import set_override, list_effective
        set_override("upload.file", "external", True)
        rows = list_effective()
        upload = next(r for r in rows if r["id"] == "upload.file")
        self.assertEqual(upload["effective"]["external"]["source"], "override")
        self.assertEqual(upload["effective"]["external"]["allowed"], True)


class EndpointTests(_FixtureBase):
    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")
        super().setUp()

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _admin_hdr(self):
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token('test-admin', 'admin')}"}

    def _employee_hdr(self):
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token('test-emp', 'employee')}"}

    # ── admin gate ──────────────────────────────────────────────
    def test_list_requires_admin(self):
        r = self._client().get(
            "/admin/features/list",
            params={"api_key": self._api_key},
            headers=self._employee_hdr(),
        )
        self.assertEqual(r.status_code, 403)

    def test_override_requires_admin(self):
        r = self._client().post(
            "/admin/features/override",
            params={"api_key": self._api_key},
            json={"feature_id": "upload.file",
                  "role": "manager", "allowed": True},
            headers=self._employee_hdr(),
        )
        self.assertEqual(r.status_code, 403)

    def test_reset_requires_admin(self):
        r = self._client().post(
            "/admin/features/reset",
            params={"api_key": self._api_key},
            json={"feature_id": "upload.file"},
            headers=self._employee_hdr(),
        )
        self.assertEqual(r.status_code, 403)

    # ── list ────────────────────────────────────────────────────
    def test_list_returns_catalog_with_roles(self):
        r = self._client().get(
            "/admin/features/list",
            params={"api_key": self._api_key},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("admin",    body["roles"])
        self.assertIn("manager",  body["roles"])
        self.assertIn("employee", body["roles"])
        self.assertIn("external", body["roles"])
        ids = [f["id"] for f in body["features"]]
        self.assertIn("upload.file", ids)
        self.assertIn("admin.users", ids)

    def test_list_reflects_override_immediately(self):
        from core.feature_registry import set_override
        set_override("upload.file", "external", True)
        r = self._client().get(
            "/admin/features/list",
            params={"api_key": self._api_key},
            headers=self._admin_hdr(),
        )
        body = r.json()
        upload = next(f for f in body["features"] if f["id"] == "upload.file")
        self.assertEqual(upload["effective"]["external"]["source"], "override")
        self.assertEqual(upload["effective"]["external"]["allowed"], True)

    # ── override ────────────────────────────────────────────────
    def test_override_happy_path(self):
        r = self._client().post(
            "/admin/features/override",
            params={"api_key": self._api_key},
            json={"feature_id": "upload.file",
                  "role": "employee", "allowed": True},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        from core.feature_registry import get_override
        self.assertEqual(get_override("upload.file", "employee"), True)

    def test_override_unknown_feature_returns_400(self):
        r = self._client().post(
            "/admin/features/override",
            params={"api_key": self._api_key},
            json={"feature_id": "nope.fake",
                  "role": "employee", "allowed": True},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 400)

    def test_override_unknown_role_returns_400(self):
        r = self._client().post(
            "/admin/features/override",
            params={"api_key": self._api_key},
            json={"feature_id": "upload.file",
                  "role": "wizard", "allowed": True},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 400)

    # ── reset ───────────────────────────────────────────────────
    def test_reset_single_role(self):
        from core.feature_registry import set_override, get_override
        set_override("upload.file", "employee", True)
        r = self._client().post(
            "/admin/features/reset",
            params={"api_key": self._api_key},
            json={"feature_id": "upload.file", "role": "employee"},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["deleted"], 1)
        self.assertIsNone(get_override("upload.file", "employee"))

    def test_reset_entire_feature(self):
        from core.feature_registry import set_override, get_override
        set_override("upload.file", "employee", True)
        set_override("upload.file", "manager",  False)
        r = self._client().post(
            "/admin/features/reset",
            params={"api_key": self._api_key},
            json={"feature_id": "upload.file"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        self.assertEqual(body["deleted"], 2)
        self.assertIsNone(get_override("upload.file", "employee"))
        self.assertIsNone(get_override("upload.file", "manager"))

    def test_reset_returns_zero_when_no_overrides(self):
        r = self._client().post(
            "/admin/features/reset",
            params={"api_key": self._api_key},
            json={"feature_id": "graph.view"},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["deleted"], 0)


if __name__ == "__main__":
    unittest.main()
