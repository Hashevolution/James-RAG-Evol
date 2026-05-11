"""W4 P1-B — POST /signup/ endpoint contract.

Verifies the HTTP shape and the enumeration-defense property that the
unit tests in ``test_password_policy`` cannot see:

  - Success and duplicate share one response body (200, same message)
    so an anonymous caller cannot probe which usernames exist.
  - Policy violations get a distinct 400 with the rule text.
  - The DB row created by a successful signup has ``active=0`` and
    ``role=external`` — i.e. unable to log in until an admin approves.
  - A duplicate attempt does NOT overwrite the pre-existing row.
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
    "test-secret-for-signup-endpoint-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core import auth as auth_mod  # noqa: E402


def _seed_users_schema(path: str) -> None:
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


def _row(path: str, username: str) -> dict | None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT username, password_hash, role, active "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


_ACCEPTED_MSG = "가입 요청이 접수되었습니다. 관리자 승인 후 사용 가능합니다."


class SignupEndpointTests(unittest.TestCase):
    """Black-box HTTP contract via FastAPI TestClient."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = self._tmp.name
        _seed_users_schema(self.db_path)
        # Point core.auth at our temp DB for the duration of the test.
        self._saved = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.db_path

    def tearDown(self):
        auth_mod._DB_PATH = self._saved
        Path(self.db_path).unlink(missing_ok=True)

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    # ─── success path ───────────────────────────────────────────────
    def test_new_signup_returns_200_with_accepted_message(self):
        client = self._client()
        r = client.post("/signup/", json={
            "username": "alice",
            "password": "alice1234",
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["message"], _ACCEPTED_MSG)

    def test_new_signup_persists_pending_row(self):
        client = self._client()
        r = client.post("/signup/", json={
            "username": "alice",
            "password": "alice1234",
        })
        self.assertEqual(r.status_code, 200)

        row = _row(self.db_path, "alice")
        self.assertIsNotNone(row)
        self.assertEqual(row["role"], "external")
        # active=0 ⇒ login() will return None (verified in test_password_bcrypt).
        self.assertEqual(row["active"], 0)
        # Hash must be bcrypt-format (W4 P1-A invariant).
        self.assertTrue(row["password_hash"].startswith("bcrypt$"))

    # ─── enumeration defense ────────────────────────────────────────
    def test_duplicate_signup_returns_same_200_body_as_success(self):
        client = self._client()
        first = client.post("/signup/", json={
            "username": "alice", "password": "alice1234",
        })
        self.assertEqual(first.status_code, 200)

        second = client.post("/signup/", json={
            "username": "alice", "password": "different_pw_42",
        })
        self.assertEqual(second.status_code, 200)
        # Bodies must be byte-identical so a probing caller cannot
        # distinguish "registered" from "already exists".
        self.assertEqual(first.json(), second.json())

    def test_duplicate_does_not_overwrite_existing_row(self):
        client = self._client()
        client.post("/signup/", json={
            "username": "alice", "password": "alice1234",
        })
        before = _row(self.db_path, "alice")
        self.assertIsNotNone(before)

        # Attempt to take over the account with a new password.
        client.post("/signup/", json={
            "username": "alice", "password": "takeover42attempt",
        })
        after = _row(self.db_path, "alice")
        self.assertEqual(before, after,
                         "duplicate signup must NOT alter the existing row")

    # ─── policy rejection ───────────────────────────────────────────
    def test_short_password_returns_400(self):
        client = self._client()
        r = client.post("/signup/", json={
            "username": "alice", "password": "ab1",
        })
        self.assertEqual(r.status_code, 400)
        body = r.json()
        # FastAPI HTTPException body shape: {"detail": <message>}
        self.assertIn("8", body["detail"])

    def test_password_without_digit_returns_400(self):
        client = self._client()
        r = client.post("/signup/", json={
            "username": "alice", "password": "alphaonly",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("숫자", r.json()["detail"])

    def test_password_without_letter_returns_400(self):
        client = self._client()
        r = client.post("/signup/", json={
            "username": "alice", "password": "12345678",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("영문", r.json()["detail"])

    def test_oversize_password_returns_400(self):
        # 73 chars — past the bcrypt 72-byte window.
        client = self._client()
        r = client.post("/signup/", json={
            "username": "alice", "password": "a" * 71 + "12",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("72", r.json()["detail"])

    def test_uppercase_username_returns_400(self):
        client = self._client()
        r = client.post("/signup/", json={
            "username": "Alice", "password": "alice1234",
        })
        self.assertEqual(r.status_code, 400)

    def test_special_char_username_returns_400(self):
        client = self._client()
        r = client.post("/signup/", json={
            "username": "alice@host", "password": "alice1234",
        })
        self.assertEqual(r.status_code, 400)

    def test_korean_username_returns_400(self):
        client = self._client()
        r = client.post("/signup/", json={
            "username": "앨리스", "password": "alice1234",
        })
        self.assertEqual(r.status_code, 400)

    # ─── side-effect: rejected signup leaves DB clean ──────────────
    def test_policy_violation_does_not_create_row(self):
        client = self._client()
        client.post("/signup/", json={
            "username": "bob", "password": "tooshort",
        })
        self.assertIsNone(_row(self.db_path, "bob"))


class SignupEndsUpInaccessibleTests(unittest.TestCase):
    """A pending account must not be able to log in. This couples
    P1-B to the existing P1-A authenticate() behavior (active=0 ⇒
    None) and would fail loudly if a future refactor removed the
    active-flag check."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = self._tmp.name
        _seed_users_schema(self.db_path)
        self._saved = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.db_path

    def tearDown(self):
        auth_mod._DB_PATH = self._saved
        Path(self.db_path).unlink(missing_ok=True)

    def test_pending_user_cannot_authenticate(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        client = TestClient(srv.app)

        r = client.post("/signup/", json={
            "username": "alice", "password": "alice1234",
        })
        self.assertEqual(r.status_code, 200)

        # Direct authenticate() returns None for an active=0 row.
        self.assertIsNone(auth_mod.authenticate("alice", "alice1234"))

        # The HTTP login route reflects the same — 401, not 200.
        login = client.post("/login/", json={
            "username": "alice", "password": "alice1234", "api_key": "",
        })
        self.assertEqual(login.status_code, 401)


if __name__ == "__main__":
    unittest.main()
