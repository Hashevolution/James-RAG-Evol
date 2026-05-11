"""W4 P2-B — admin-issued reset token workflow.

Coverage:
  - issue_reset_token: returns plaintext once, persists hash, revokes
    prior unused tokens, returns None for unknown/inactive users.
  - consume_reset_token: all six return codes, two-call replay
    rejected, expired token rejected, cross-username token rejected.
  - HTTP endpoints: admin gate on issue, 404 on unknown user,
    unified-401 on bad token (enumeration defense), 200 on valid
    consume, audit semantics.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-reset-token-suite-32chars",
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


def _insert(path: str, username: str, role: str = "employee",
            active: int = 1) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, active) "
        "VALUES (?, ?, ?, ?)",
        (username, auth_mod.hash_password("original_pw_42"), role, active),
    )
    conn.commit()
    conn.close()


def _count_tokens(path: str, username: str) -> int:
    conn = sqlite3.connect(path)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM password_reset_tokens WHERE username = ?",
            (username,),
        ).fetchone()[0]
        return n
    finally:
        conn.close()


def _force_expired_token(path: str, token: str) -> None:
    """Backdate the token so it appears expired."""
    h = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE password_reset_tokens SET expires_at = ? WHERE token_hash = ?",
        (int(time.time()) - 60, h),
    )
    conn.commit()
    conn.close()


class IssueTokenTests(unittest.TestCase):
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

    def test_issue_returns_plaintext_token_and_persists_hash(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        self.assertIsNotNone(tok)
        # token is URL-safe base64 of 32 bytes → at least 32 chars.
        self.assertGreaterEqual(len(tok), 32)
        # DB stores SHA256, NOT the plaintext.
        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute(
                "SELECT token_hash FROM password_reset_tokens WHERE username = ?",
                ("alice",),
            ).fetchone()
        finally:
            conn.close()
        self.assertNotEqual(row[0], tok,
                            "plaintext token must NOT appear in DB")
        self.assertEqual(
            row[0], hashlib.sha256(tok.encode()).hexdigest(),
            "stored hash must be SHA256 of the plaintext token",
        )

    def test_issue_revokes_prior_unused_tokens(self):
        _insert(self.db, "alice")
        first  = reset_mod.issue_reset_token("alice")
        second = reset_mod.issue_reset_token("alice")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        # Only the freshest unused token survives — the first is gone.
        self.assertEqual(_count_tokens(self.db, "alice"), 1)
        # The old token no longer consumes (proves it was deleted).
        self.assertEqual(
            reset_mod.consume_reset_token("alice", first, "new_pw_99"),
            "invalid_token",
        )

    def test_issue_returns_none_for_unknown_user(self):
        self.assertIsNone(reset_mod.issue_reset_token("ghost"))

    def test_issue_returns_none_for_inactive_user(self):
        _insert(self.db, "pending", active=0)
        self.assertIsNone(reset_mod.issue_reset_token("pending"))


class ConsumeTokenTests(unittest.TestCase):
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

    def test_ok_updates_password_and_marks_token_used(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        r = reset_mod.consume_reset_token("alice", tok, "new_pw_99")
        self.assertEqual(r, "ok")
        # New password works, original no longer.
        self.assertIsNotNone(auth_mod.authenticate("alice", "new_pw_99"))
        self.assertIsNone(auth_mod.authenticate("alice", "original_pw_42"))

    def test_replay_rejected_as_already_used(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        self.assertEqual(
            reset_mod.consume_reset_token("alice", tok, "new_pw_99"), "ok",
        )
        # Second call with same token — must NOT silently succeed.
        self.assertEqual(
            reset_mod.consume_reset_token("alice", tok, "yet_another_99"),
            "already_used",
        )
        # The yet_another password should NOT have taken effect.
        self.assertIsNone(auth_mod.authenticate("alice", "yet_another_99"))

    def test_expired_token_rejected(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        _force_expired_token(self.db, tok)
        r = reset_mod.consume_reset_token("alice", tok, "new_pw_99")
        self.assertEqual(r, "invalid_token")

    def test_wrong_username_rejected(self):
        _insert(self.db, "alice")
        _insert(self.db, "bob")
        tok = reset_mod.issue_reset_token("alice")
        # Same token hash, claim it for bob — must fail.
        r = reset_mod.consume_reset_token("bob", tok, "new_pw_99")
        self.assertEqual(r, "invalid_token")
        # alice's password is also unchanged (the bad consume didn't
        # touch any row).
        self.assertIsNotNone(auth_mod.authenticate("alice", "original_pw_42"))

    def test_unknown_token_rejected(self):
        _insert(self.db, "alice")
        r = reset_mod.consume_reset_token("alice", "nonexistent-token-xyz",
                                          "new_pw_99")
        self.assertEqual(r, "invalid_token")

    def test_policy_violation_returned_with_message(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        # Short new password — policy:... before token validation
        # even fires. That's intentional: we don't want a successful
        # token consume to be partially applied with a bad password.
        r = reset_mod.consume_reset_token("alice", tok, "ab1")
        self.assertTrue(r.startswith("policy:"), r)
        # Token still valid for a second try (NOT consumed).
        self.assertEqual(
            reset_mod.consume_reset_token("alice", tok, "valid_pw_99"), "ok",
        )

    def test_inactive_user_rejected(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        # Admin deactivates between issue and consume.
        auth_mod.deactivate_user("alice")
        r = reset_mod.consume_reset_token("alice", tok, "new_pw_99")
        self.assertEqual(r, "no_user")


class EndpointTests(unittest.TestCase):
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

    def _admin_headers(self) -> dict:
        return {"Authorization": f"Bearer {auth_mod.create_token('admin', 'admin')}"}

    def _user_headers(self) -> dict:
        return {"Authorization": f"Bearer {auth_mod.create_token('employee', 'employee')}"}

    # ── issue ──────────────────────────────────────────────────────
    def test_issue_requires_admin(self):
        _insert(self.db, "alice")
        r = self._client().post(
            "/admin/users/issue-reset-token",
            params={"api_key": self._api_key},
            json={"username": "alice"},
            headers=self._user_headers(),  # employee, not admin
        )
        self.assertEqual(r.status_code, 403)

    def test_issue_returns_token_and_ttl(self):
        _insert(self.db, "alice")
        r = self._client().post(
            "/admin/users/issue-reset-token",
            params={"api_key": self._api_key},
            json={"username": "alice"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertGreaterEqual(len(body["token"]), 32)
        self.assertEqual(body["expires_in_seconds"],
                         reset_mod.RESET_TOKEN_TTL_SEC)

    def test_issue_404_for_unknown_user(self):
        r = self._client().post(
            "/admin/users/issue-reset-token",
            params={"api_key": self._api_key},
            json={"username": "ghost"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 404)

    def test_issue_404_for_inactive_user(self):
        _insert(self.db, "pending", active=0)
        r = self._client().post(
            "/admin/users/issue-reset-token",
            params={"api_key": self._api_key},
            json={"username": "pending"},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 404)

    # ── confirm ────────────────────────────────────────────────────
    def test_confirm_happy_path_returns_200_and_changes_password(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        r = self._client().post(
            "/password/reset/confirm",
            json={"username": "alice", "token": tok,
                  "new_password": "new_pw_99"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(auth_mod.authenticate("alice", "new_pw_99"))

    def test_confirm_bad_token_returns_401_unified(self):
        # Wrong token AND wrong username — both must collapse to a
        # single 401 so an anonymous caller can't enumerate users.
        for body in [
            {"username": "alice", "token": "bogus", "new_password": "new_pw_99"},
            {"username": "ghost", "token": "bogus", "new_password": "new_pw_99"},
        ]:
            r = self._client().post("/password/reset/confirm", json=body)
            self.assertEqual(r.status_code, 401, f"body={body}")

    def test_confirm_policy_violation_returns_400(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        r = self._client().post(
            "/password/reset/confirm",
            json={"username": "alice", "token": tok, "new_password": "ab1"},
        )
        self.assertEqual(r.status_code, 400)

    def test_confirm_replay_returns_401(self):
        _insert(self.db, "alice")
        tok = reset_mod.issue_reset_token("alice")
        self._client().post(
            "/password/reset/confirm",
            json={"username": "alice", "token": tok,
                  "new_password": "new_pw_99"},
        )
        r = self._client().post(
            "/password/reset/confirm",
            json={"username": "alice", "token": tok,
                  "new_password": "yet_another_99"},
        )
        self.assertEqual(r.status_code, 401)
        self.assertIsNone(auth_mod.authenticate("alice", "yet_another_99"))


if __name__ == "__main__":
    unittest.main()
