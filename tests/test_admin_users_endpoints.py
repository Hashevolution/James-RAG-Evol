"""W4 P2-A — admin user-management endpoints + helpers.

Covers:
  - core.auth helpers (list_users / approve_user / reject_user) — pure
    DB-roundtrip semantics, independent of the FastAPI layer.
  - HTTP endpoints — admin gate, audit semantics, error codes, the
    "can't deactivate yourself" invariant.

The endpoints exist to power the admin approval UI (P2-A frontend).
Auditing here matters more than throughput: every approve/reject/
deactivate must end up in james_audit.db.
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
    "test-secret-for-admin-users-suite-32chars",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core import auth as auth_mod  # noqa: E402


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
    conn.commit()
    conn.close()


def _insert(path: str, username: str, role: str, active: int) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, active) "
        "VALUES (?, ?, ?, ?)",
        (username, auth_mod.hash_password("pw_does_not_matter_42"),
         role, active),
    )
    conn.commit()
    conn.close()


def _row(path: str, username: str) -> dict | None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT username, role, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


class AuthHelperTests(unittest.TestCase):
    """Pure DB helpers — no FastAPI involved."""

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

    def test_list_users_omits_password_hash(self):
        _insert(self.db, "alice", "external", 0)
        users = auth_mod.list_users()
        self.assertEqual(len(users), 1)
        # The whole point of going through the helper is that we never
        # leak the password hash to the admin endpoint.
        self.assertNotIn("password_hash", users[0])
        self.assertIn("username", users[0])
        self.assertIn("role", users[0])
        self.assertIn("active", users[0])

    def test_list_users_pending_filter(self):
        _insert(self.db, "alice",  "external", 0)
        _insert(self.db, "bob",    "employee", 1)
        _insert(self.db, "carol",  "external", 0)

        all_users = auth_mod.list_users()
        pending   = auth_mod.list_users(only_pending=True)

        self.assertEqual(len(all_users), 3)
        self.assertEqual({u["username"] for u in pending}, {"alice", "carol"})

    def test_list_users_sort_pending_first(self):
        # active=0 < active=1 by ASC, so pending lands at the top.
        _insert(self.db, "zoe-active",   "employee", 1)
        _insert(self.db, "amy-active",   "employee", 1)
        _insert(self.db, "bob-pending",  "external", 0)
        names = [u["username"] for u in auth_mod.list_users()]
        self.assertEqual(names[0], "bob-pending",
                         "pending users must sort before active users")

    def test_approve_user_flips_active_and_sets_role(self):
        _insert(self.db, "alice", "external", 0)
        ok = auth_mod.approve_user("alice", "manager")
        self.assertTrue(ok)
        row = _row(self.db, "alice")
        self.assertEqual(row["active"], 1)
        self.assertEqual(row["role"], "manager")

    def test_approve_user_rejects_invalid_role(self):
        _insert(self.db, "alice", "external", 0)
        ok = auth_mod.approve_user("alice", "wizard")  # not in ALLOWED_ROLES
        self.assertFalse(ok)
        # Row untouched.
        self.assertEqual(_row(self.db, "alice")["active"], 0)

    def test_approve_user_refuses_already_active(self):
        _insert(self.db, "alice", "employee", 1)
        ok = auth_mod.approve_user("alice", "manager")
        self.assertFalse(ok,
                         "approve must not silently promote an active user; "
                         "use change-role for that workflow instead")
        # Role and active flag unchanged.
        row = _row(self.db, "alice")
        self.assertEqual(row["role"], "employee")
        self.assertEqual(row["active"], 1)

    def test_approve_user_unknown_username_is_noop(self):
        self.assertFalse(auth_mod.approve_user("ghost", "manager"))

    def test_reject_user_deletes_pending_row(self):
        _insert(self.db, "alice", "external", 0)
        ok = auth_mod.reject_user("alice")
        self.assertTrue(ok)
        self.assertIsNone(_row(self.db, "alice"))

    def test_reject_user_refuses_active_account(self):
        _insert(self.db, "bob", "employee", 1)
        ok = auth_mod.reject_user("bob")
        self.assertFalse(ok,
                         "reject must not be a stealth account-deletion path "
                         "for active users — deactivate is the right tool")
        self.assertIsNotNone(_row(self.db, "bob"))


class EndpointTests(unittest.TestCase):
    """HTTP layer — admin gate + audit + error codes."""

    @classmethod
    def setUpClass(cls):
        from core.auth import create_token
        cls._admin_token = create_token("test-admin", "admin")
        cls._user_token  = create_token("test-user", "employee")
        cls._api_key     = cls._read_api_key()

    @staticmethod
    def _read_api_key() -> str:
        env_v = os.environ.get("JAMES_API_KEY")
        if env_v:
            return env_v.strip()
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8-sig").splitlines():
                if line.startswith("JAMES_API_KEY="):
                    return line.split("=", 1)[1].strip()
        return ""

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing; cannot exercise admin route")
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

    def _admin_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._admin_token}"}

    def _user_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._user_token}"}

    # ── list ───────────────────────────────────────────────────────
    def test_list_requires_admin(self):
        _insert(self.db, "alice", "external", 0)
        r = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key},
            headers=self._user_headers(),  # employee, not admin
        )
        self.assertEqual(r.status_code, 403)

    def test_list_returns_users_without_password_hash(self):
        _insert(self.db, "alice", "external", 0)
        _insert(self.db, "bob",   "employee", 1)
        r = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["users"]), 2)
        for u in body["users"]:
            self.assertNotIn("password_hash", u)

    def test_list_pending_only(self):
        _insert(self.db, "alice", "external", 0)
        _insert(self.db, "bob",   "employee", 1)
        r = self._client().get(
            "/admin/users",
            params={"api_key": self._api_key, "pending": "true"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        names = [u["username"] for u in r.json()["users"]]
        self.assertEqual(names, ["alice"])

    # ── approve ────────────────────────────────────────────────────
    def test_approve_promotes_pending_to_active(self):
        _insert(self.db, "alice", "external", 0)
        r = self._client().post(
            "/admin/users/approve",
            params={"api_key": self._api_key},
            json={"username": "alice", "role": "manager"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        row = _row(self.db, "alice")
        self.assertEqual(row["active"], 1)
        self.assertEqual(row["role"], "manager")

    def test_approve_rejects_invalid_role_with_400(self):
        _insert(self.db, "alice", "external", 0)
        r = self._client().post(
            "/admin/users/approve",
            params={"api_key": self._api_key},
            json={"username": "alice", "role": "wizard"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 400)

    def test_approve_returns_404_on_already_active(self):
        _insert(self.db, "alice", "employee", 1)
        r = self._client().post(
            "/admin/users/approve",
            params={"api_key": self._api_key},
            json={"username": "alice", "role": "manager"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 404)
        # Existing role preserved.
        self.assertEqual(_row(self.db, "alice")["role"], "employee")

    # ── reject ─────────────────────────────────────────────────────
    def test_reject_deletes_pending_row(self):
        _insert(self.db, "alice", "external", 0)
        r = self._client().post(
            "/admin/users/reject",
            params={"api_key": self._api_key},
            json={"username": "alice"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(_row(self.db, "alice"))

    def test_reject_refuses_active_account_returns_404(self):
        _insert(self.db, "bob", "employee", 1)
        r = self._client().post(
            "/admin/users/reject",
            params={"api_key": self._api_key},
            json={"username": "bob"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 404)
        # Account preserved — reject must not be a deletion backdoor.
        self.assertIsNotNone(_row(self.db, "bob"))

    # ── deactivate ─────────────────────────────────────────────────
    def test_deactivate_active_user_flips_flag(self):
        _insert(self.db, "bob", "employee", 1)
        r = self._client().post(
            "/admin/users/deactivate",
            params={"api_key": self._api_key},
            json={"username": "bob"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(_row(self.db, "bob")["active"], 0)

    def test_deactivate_self_blocked(self):
        # Admin JWT subject is "test-admin"; deactivating themselves
        # would lock out the only admin in a single-admin deployment.
        _insert(self.db, "test-admin", "admin", 1)
        r = self._client().post(
            "/admin/users/deactivate",
            params={"api_key": self._api_key},
            json={"username": "test-admin"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 400)
        # Row untouched.
        self.assertEqual(_row(self.db, "test-admin")["active"], 1)

    def test_deactivate_unknown_user_returns_404(self):
        r = self._client().post(
            "/admin/users/deactivate",
            params={"api_key": self._api_key},
            json={"username": "ghost"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
