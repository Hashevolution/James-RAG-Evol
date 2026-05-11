"""W4 P2-B — self-service password change (logged-in user).

Coverage:
  - core.auth_reset.change_password — pure DB helper, all four return
    codes ("ok", "invalid_old", "policy:...", "no_user").
  - POST /password/change endpoint — JWT-scoped, status codes 200 /
    400 / 401, and the audit-log invariant that the username comes
    from the JWT `sub` (not the body).
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
    "test-secret-for-password-change-suite-32chars",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core import auth as auth_mod  # noqa: E402
from core import auth_reset as reset_mod  # noqa: E402


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
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token_hash  TEXT PRIMARY KEY,
            username    TEXT NOT NULL,
            created_at  INTEGER NOT NULL,
            expires_at  INTEGER NOT NULL,
            used_at     INTEGER
        )
    """)
    conn.commit()
    conn.close()


def _insert_active(path: str, username: str, password: str,
                   role: str = "employee", active: int = 1) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, active) "
        "VALUES (?, ?, ?, ?)",
        (username, auth_mod.hash_password(password), role, active),
    )
    conn.commit()
    conn.close()


def _verify_login_works(path: str, username: str, password: str) -> bool:
    auth_mod._DB_PATH_saved = auth_mod._DB_PATH
    auth_mod._DB_PATH = path
    try:
        return auth_mod.authenticate(username, password) is not None
    finally:
        auth_mod._DB_PATH = auth_mod._DB_PATH_saved


class ChangePasswordHelperTests(unittest.TestCase):
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

    def test_ok_changes_password_and_old_no_longer_works(self):
        _insert_active(self.db, "alice", "old_pw_42")
        r = reset_mod.change_password("alice", "old_pw_42", "new_pw_99")
        self.assertEqual(r, "ok")
        # Direct authenticate() probe — old fails, new works.
        self.assertIsNone(auth_mod.authenticate("alice", "old_pw_42"))
        self.assertIsNotNone(auth_mod.authenticate("alice", "new_pw_99"))

    def test_invalid_old_password(self):
        _insert_active(self.db, "alice", "old_pw_42")
        r = reset_mod.change_password("alice", "wrong", "new_pw_99")
        self.assertEqual(r, "invalid_old")
        # Original still works.
        self.assertIsNotNone(auth_mod.authenticate("alice", "old_pw_42"))

    def test_policy_rejection_returned_with_message(self):
        _insert_active(self.db, "alice", "old_pw_42")
        # too short
        r = reset_mod.change_password("alice", "old_pw_42", "ab1")
        self.assertTrue(r.startswith("policy:"),
                        f"expected 'policy:...', got {r!r}")
        # Old still works — failed policy must not mutate the row.
        self.assertIsNotNone(auth_mod.authenticate("alice", "old_pw_42"))

    def test_no_user_for_unknown_username(self):
        r = reset_mod.change_password("ghost", "any", "new_pw_99")
        self.assertEqual(r, "no_user")

    def test_no_user_for_inactive_account(self):
        _insert_active(self.db, "pending", "old_pw_42", active=0)
        # Even with the correct old password, an inactive account
        # cannot self-change — they have no business being logged in.
        r = reset_mod.change_password("pending", "old_pw_42", "new_pw_99")
        self.assertEqual(r, "no_user")


class ChangePasswordEndpointTests(unittest.TestCase):
    """HTTP-level: JWT scoping, status codes, body-username defense."""

    @classmethod
    def setUpClass(cls):
        cls._api_key = cls._read_api_key()

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
            self.skipTest("JAMES_API_KEY missing")
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

    def _jwt_for(self, username: str, role: str = "employee") -> str:
        return auth_mod.create_token(username, role)

    def test_ok_returns_200_and_updates_password(self):
        _insert_active(self.db, "alice", "old_pw_42")
        r = self._client().post(
            "/password/change",
            json={"old_password": "old_pw_42", "new_password": "new_pw_99"},
            headers={"Authorization": f"Bearer {self._jwt_for('alice')}"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(auth_mod.authenticate("alice", "new_pw_99"))

    def test_missing_jwt_returns_401(self):
        _insert_active(self.db, "alice", "old_pw_42")
        r = self._client().post(
            "/password/change",
            json={"old_password": "old_pw_42", "new_password": "new_pw_99"},
        )
        self.assertEqual(r.status_code, 401)
        # Row unchanged.
        self.assertIsNotNone(auth_mod.authenticate("alice", "old_pw_42"))

    def test_wrong_old_password_returns_401(self):
        _insert_active(self.db, "alice", "old_pw_42")
        r = self._client().post(
            "/password/change",
            json={"old_password": "wrong", "new_password": "new_pw_99"},
            headers={"Authorization": f"Bearer {self._jwt_for('alice')}"},
        )
        self.assertEqual(r.status_code, 401)

    def test_short_new_password_returns_400(self):
        _insert_active(self.db, "alice", "old_pw_42")
        r = self._client().post(
            "/password/change",
            json={"old_password": "old_pw_42", "new_password": "ab1"},
            headers={"Authorization": f"Bearer {self._jwt_for('alice')}"},
        )
        self.assertEqual(r.status_code, 400)
        # Old still works.
        self.assertIsNotNone(auth_mod.authenticate("alice", "old_pw_42"))

    def test_jwt_scoping_body_username_field_is_ignored(self):
        """The body has no username field by design. A caller cannot
        target another account by adding one — we read from the JWT
        only. This test wedges an extra `username` into the body to
        confirm pydantic-extra-ignore does not accidentally route it.
        """
        _insert_active(self.db, "alice", "old_pw_42")
        _insert_active(self.db, "bob",   "bob_pw_42")
        r = self._client().post(
            "/password/change",
            json={
                "old_password": "old_pw_42",
                "new_password": "new_pw_99",
                "username":     "bob",   # tries to target bob via body
            },
            headers={"Authorization": f"Bearer {self._jwt_for('alice')}"},
        )
        # alice changed, bob untouched.
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(auth_mod.authenticate("alice", "new_pw_99"))
        self.assertIsNotNone(auth_mod.authenticate("bob",   "bob_pw_42"))


if __name__ == "__main__":
    unittest.main()
