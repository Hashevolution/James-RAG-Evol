"""W4 P3-2 — authentication middleware accepts user API keys.

Verifies that ``jms_...`` keys minted in P3-1 now resolve to the
owning user's role through the request-authentication path, and that
the system API_KEY behaviour is unchanged.

Three coverage angles:
  1. resolve_api_key_principal — the pure helper (no FastAPI).
  2. verify_api_key — accepts system AND user keys, rejects garbage.
  3. End-to-end via TestClient — calling an admin endpoint with only
     a user API key for an admin user must succeed; with only a
     system key it must NOT (system key is intentionally employee).
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
    "test-secret-for-api-key-middleware-32chars",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core import auth as auth_mod  # noqa: E402
from core import api_keys as ak_mod  # noqa: E402


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
        CREATE TABLE IF NOT EXISTS api_keys (
            key_hash      TEXT PRIMARY KEY,
            key_prefix    TEXT NOT NULL,
            username      TEXT NOT NULL,
            label         TEXT,
            created_at    INTEGER NOT NULL,
            last_used_at  INTEGER,
            revoked_at    INTEGER
        )
    """)
    conn.commit()
    conn.close()


def _insert_user(path: str, username: str, role: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, active) "
        "VALUES (?, ?, ?, 1)",
        (username, auth_mod.hash_password("placeholder_pw_42"), role),
    )
    conn.commit()
    conn.close()


def _system_api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


class PrincipalResolutionTests(unittest.TestCase):
    """resolve_api_key_principal — the non-raising helper."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        _seed_schema(self.db)
        self._saved = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.db

    def tearDown(self):
        auth_mod._DB_PATH = self._saved
        Path(self.db).unlink(missing_ok=True)

    def test_user_key_resolves_to_owner_and_role(self):
        import server_llmwiki as srv
        _insert_user(self.db, "alice", role="manager")
        plain, _ = ak_mod.issue_api_key("alice")
        p = srv.resolve_api_key_principal(plain)
        self.assertEqual(p, {"source": "user", "username": "alice",
                             "role": "manager"})

    def test_system_key_resolves_to_employee_not_admin(self):
        """System key intentionally does NOT carry admin authority."""
        import server_llmwiki as srv
        sys_key = _system_api_key()
        if not sys_key:
            self.skipTest("JAMES_API_KEY missing")
        p = srv.resolve_api_key_principal(sys_key)
        self.assertIsNotNone(p)
        self.assertEqual(p["source"], "system")
        self.assertEqual(p["role"], "employee",
                         "system key must not self-elevate to admin")

    def test_unknown_keys_return_none(self):
        import server_llmwiki as srv
        for k in ("", "garbage", "jms_unissued", "Bearer some-jwt"):
            self.assertIsNone(srv.resolve_api_key_principal(k),
                              f"unexpected resolve on {k!r}")


class VerifyApiKeyTests(unittest.TestCase):
    """verify_api_key — raises on miss, returns None on success."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        _seed_schema(self.db)
        self._saved = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.db

    def tearDown(self):
        auth_mod._DB_PATH = self._saved
        Path(self.db).unlink(missing_ok=True)

    def test_user_key_accepted(self):
        import server_llmwiki as srv
        _insert_user(self.db, "alice", role="employee")
        plain, _ = ak_mod.issue_api_key("alice")
        # No exception expected.
        srv.verify_api_key(plain)

    def test_system_key_accepted(self):
        import server_llmwiki as srv
        sys_key = _system_api_key()
        if not sys_key:
            self.skipTest("JAMES_API_KEY missing")
        srv.verify_api_key(sys_key)

    def test_garbage_raises_403(self):
        import server_llmwiki as srv
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            srv.verify_api_key("absolutely-not-a-key")
        self.assertEqual(cm.exception.status_code, 403)

    def test_revoked_user_key_raises_403(self):
        import server_llmwiki as srv
        from fastapi import HTTPException
        _insert_user(self.db, "alice", role="employee")
        plain, prefix = ak_mod.issue_api_key("alice")
        ak_mod.revoke_api_key("alice", prefix)
        with self.assertRaises(HTTPException) as cm:
            srv.verify_api_key(plain)
        self.assertEqual(cm.exception.status_code, 403)


class EndToEndTests(unittest.TestCase):
    """User API key on a real admin route — admin role on the
    owning user must let the request through; an employee user's
    key must NOT pass the admin gate."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        _seed_schema(self.db)
        self._saved = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.db

    def tearDown(self):
        auth_mod._DB_PATH = self._saved
        Path(self.db).unlink(missing_ok=True)

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def test_user_admin_key_passes_admin_gate(self):
        _insert_user(self.db, "alice-admin", role="admin")
        plain, _ = ak_mod.issue_api_key("alice-admin")
        # /admin/users requires admin role AND a valid API key.
        # The user key here provides both at once via P3-2.
        r = self._client().get(
            "/admin/users",
            params={"api_key": plain},
            # No Bearer JWT — only the user API key as both auth and
            # role source.
        )
        self.assertEqual(r.status_code, 200,
                         f"user admin key should pass admin gate; "
                         f"got {r.status_code}: {r.text}")

    def test_user_employee_key_blocked_at_admin_gate(self):
        _insert_user(self.db, "bob-emp", role="employee")
        plain, _ = ak_mod.issue_api_key("bob-emp")
        r = self._client().get(
            "/admin/users",
            params={"api_key": plain},
        )
        # api_key is valid (200 wouldn't 403 on it), but the resolved
        # role is employee → admin gate fires.
        self.assertEqual(r.status_code, 403)

    def test_system_key_alone_blocked_at_admin_gate(self):
        """A bare JAMES_API_KEY must NOT confer admin authority — the
        current behaviour from before P3-2, deliberately preserved."""
        sys_key = _system_api_key()
        if not sys_key:
            self.skipTest("JAMES_API_KEY missing")
        r = self._client().get(
            "/admin/users",
            params={"api_key": sys_key},
        )
        self.assertEqual(r.status_code, 403,
                         "system key without admin JWT must NOT pass")

    def test_x_api_key_header_works_same_as_query(self):
        _insert_user(self.db, "alice-admin", role="admin")
        plain, _ = ak_mod.issue_api_key("alice-admin")
        # X-API-Key header — keeps the credential out of URL logs.
        r = self._client().get(
            "/admin/users",
            params={"api_key": plain},   # still need it for verify_api_key
            headers={"X-API-Key": plain},
        )
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
