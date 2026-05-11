"""W4-Q2-a — feature gate wiring on existing admin endpoints.

The catalog from Q1 is no longer just metadata: 17 endpoints now
consult ``PolicyEngine.can_use_feature`` through the new
``_require_feature`` helper. This test proves the override path
ACTUALLY changes who can call which endpoint — without it, Q1 was
purely cosmetic.

Two demonstrations using ``/admin/users`` as the witness endpoint:
  1. admin JWT → 200 (default_allowed includes admin)
  2. manager JWT → 403 by default
  3. override admin.users allowed for manager → manager JWT now → 200
  4. clear override → manager JWT → 403 again

The same wiring covers 17 endpoints; testing one is enough to prove
the helper + Q1 module + Q2 wiring all line up.
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
    "test-secret-for-q2a-wiring-32chars-min",
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


class FeatureGateRewireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")
        from core import auth as auth_mod
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        _seed_schema(self.db)
        self._saved_path = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.db

    def tearDown(self):
        from core import auth as auth_mod
        auth_mod._DB_PATH = self._saved_path
        Path(self.db).unlink(missing_ok=True)

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _hdr(self, role: str):
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token(f'test-{role}', role)}"}

    # ── default matrix ────────────────────────────────────────────
    def test_admin_passes_admin_users_by_default(self):
        r = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key},
            headers=self._hdr("admin"),
        )
        self.assertEqual(r.status_code, 200, r.text)

    def test_manager_blocked_from_admin_users_by_default(self):
        r = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key},
            headers=self._hdr("manager"),
        )
        self.assertEqual(r.status_code, 403)

    # ── override path ─────────────────────────────────────────────
    def test_override_grants_manager_access(self):
        from core.feature_registry import set_override
        set_override("admin.users", "manager", True, updated_by="test")
        r = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key},
            headers=self._hdr("manager"),
        )
        self.assertEqual(r.status_code, 200, r.text)

    def test_clear_override_restores_default_deny(self):
        from core.feature_registry import set_override, clear_override
        set_override("admin.users", "manager", True)
        # Confirm it actually let manager in first.
        r1 = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key},
            headers=self._hdr("manager"),
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        clear_override("admin.users", "manager")
        # Now back to default-deny.
        r2 = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key},
            headers=self._hdr("manager"),
        )
        self.assertEqual(r2.status_code, 403)

    def test_override_to_false_revokes_admin(self):
        # Inverse direction: an admin override flagged False should
        # lock the admin out. This is the operator's escape hatch
        # for "we need to disable a feature mid-flight without a
        # deploy" scenarios.
        from core.feature_registry import set_override
        set_override("admin.users", "admin", False)
        r = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key},
            headers=self._hdr("admin"),
        )
        self.assertEqual(r.status_code, 403)

    # ── different features stay independent ───────────────────────
    def test_override_on_one_feature_does_not_leak_to_another(self):
        from core.feature_registry import set_override
        # Grant manager access to admin.users only.
        set_override("admin.users", "manager", True)
        # admin.audit_log still defaults to admin-only — manager blocked.
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key},
            headers=self._hdr("manager"),
        )
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
