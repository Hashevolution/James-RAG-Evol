"""W4 P3-1 — per-user API keys: issue / list / revoke.

Coverage:
  - core.api_keys helpers (issue / verify / revoke / list) — pure
    DB semantics independent of the FastAPI layer.
  - Endpoint contracts — JWT-scoped issue + list + revoke, plaintext-
    once invariant, cross-user revocation blocked.

Out of scope for THIS PR:
  - The authentication middleware does NOT yet accept the issued
    keys as a substitute for a JWT — that wiring is W4 P3-2. Tests
    here verify that the key resolves through verify_api_key() to
    the correct (username, role); the integration into request
    handling is exercised by P3-2's tests.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-api-keys-suite-32chars",
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


def _insert_user(path: str, username: str, role: str = "employee",
                 active: int = 1) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, active) "
        "VALUES (?, ?, ?, ?)",
        (username, auth_mod.hash_password("placeholder_pw_42"),
         role, active),
    )
    conn.commit()
    conn.close()


def _read_key_row(path: str, prefix: str) -> dict | None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT * FROM api_keys WHERE key_prefix = ?", (prefix,)
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


class IssueAndVerifyTests(unittest.TestCase):
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

    def test_issue_returns_jms_prefixed_plaintext_and_prefix(self):
        _insert_user(self.db, "alice")
        pair = ak_mod.issue_api_key("alice", label="ci")
        self.assertIsNotNone(pair)
        plain, prefix = pair
        self.assertTrue(plain.startswith("jms_"))
        self.assertEqual(prefix, plain[:ak_mod.KEY_PREFIX_LEN])
        # Body is long enough to be brute-resistant.
        self.assertGreater(len(plain), 32)

    def test_issue_persists_hash_not_plaintext(self):
        _insert_user(self.db, "alice")
        plain, prefix = ak_mod.issue_api_key("alice")
        row = _read_key_row(self.db, prefix)
        self.assertIsNotNone(row)
        self.assertNotEqual(row["key_hash"], plain,
                            "plaintext token must NOT be stored")
        self.assertEqual(
            row["key_hash"],
            hashlib.sha256(plain.encode("utf-8")).hexdigest(),
            "stored hash must be SHA256(plaintext)",
        )

    def test_issue_rejects_unknown_user(self):
        self.assertIsNone(ak_mod.issue_api_key("ghost"))

    def test_issue_rejects_inactive_user(self):
        _insert_user(self.db, "pending", active=0)
        self.assertIsNone(ak_mod.issue_api_key("pending"))

    def test_verify_returns_username_and_current_role(self):
        _insert_user(self.db, "alice", role="employee")
        plain, _ = ak_mod.issue_api_key("alice")
        out = ak_mod.verify_api_key(plain)
        self.assertEqual(out, {"username": "alice", "role": "employee"})

    def test_verify_reflects_role_changes_on_user_row(self):
        # If admin promotes alice via the users table, the next verify
        # must see the new role — keys do NOT pin a stale role.
        _insert_user(self.db, "alice", role="employee")
        plain, _ = ak_mod.issue_api_key("alice")
        # Promote alice.
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE users SET role = ? WHERE username = ?",
                     ("manager", "alice"))
        conn.commit()
        conn.close()
        out = ak_mod.verify_api_key(plain)
        self.assertEqual(out["role"], "manager")

    def test_verify_rejects_when_owner_inactive(self):
        _insert_user(self.db, "alice")
        plain, _ = ak_mod.issue_api_key("alice")
        auth_mod.deactivate_user("alice")
        self.assertIsNone(ak_mod.verify_api_key(plain))

    def test_verify_rejects_garbage_and_wrong_prefix(self):
        self.assertIsNone(ak_mod.verify_api_key(""))
        self.assertIsNone(ak_mod.verify_api_key("not-a-key"))
        # Right shape, never issued — must miss.
        self.assertIsNone(ak_mod.verify_api_key("jms_unissued_xyz"))

    def test_verify_bumps_last_used_at(self):
        _insert_user(self.db, "alice")
        plain, prefix = ak_mod.issue_api_key("alice")
        before = _read_key_row(self.db, prefix)
        self.assertIsNone(before["last_used_at"])
        ak_mod.verify_api_key(plain)
        after = _read_key_row(self.db, prefix)
        self.assertIsNotNone(after["last_used_at"])


class RevokeTests(unittest.TestCase):
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

    def test_revoke_blocks_subsequent_verify(self):
        _insert_user(self.db, "alice")
        plain, prefix = ak_mod.issue_api_key("alice")
        self.assertTrue(ak_mod.revoke_api_key("alice", prefix))
        self.assertIsNone(ak_mod.verify_api_key(plain))

    def test_revoke_cannot_target_other_users_key(self):
        _insert_user(self.db, "alice")
        _insert_user(self.db, "bob")
        plain, prefix = ak_mod.issue_api_key("alice")
        # Bob tries to revoke alice's key via her prefix — must fail.
        self.assertFalse(ak_mod.revoke_api_key("bob", prefix))
        # Key still verifies.
        self.assertIsNotNone(ak_mod.verify_api_key(plain))

    def test_revoke_idempotent_returns_false_second_time(self):
        _insert_user(self.db, "alice")
        _, prefix = ak_mod.issue_api_key("alice")
        self.assertTrue(ak_mod.revoke_api_key("alice", prefix))
        self.assertFalse(ak_mod.revoke_api_key("alice", prefix),
                         "re-revoking must not silently re-stamp; "
                         "history is informational")

    def test_revoke_unknown_prefix_returns_false(self):
        _insert_user(self.db, "alice")
        self.assertFalse(ak_mod.revoke_api_key("alice", "jms_xxxxxxxx"))


class ListTests(unittest.TestCase):
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

    def test_list_returns_only_owners_keys(self):
        _insert_user(self.db, "alice")
        _insert_user(self.db, "bob")
        ak_mod.issue_api_key("alice", label="alice-key")
        ak_mod.issue_api_key("bob",   label="bob-key")
        keys = ak_mod.list_api_keys("alice")
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]["label"], "alice-key")

    def test_list_excludes_plaintext_includes_prefix_and_label(self):
        _insert_user(self.db, "alice")
        ak_mod.issue_api_key("alice", label="ci")
        row = ak_mod.list_api_keys("alice")[0]
        # No raw "key" or "plaintext" field — prefix is the handle.
        self.assertNotIn("key", row)
        self.assertNotIn("plaintext", row)
        self.assertIn("key_prefix", row)
        self.assertEqual(row["label"], "ci")
        self.assertFalse(row["revoked"])

    def test_list_sort_active_first_then_recent(self):
        _insert_user(self.db, "alice")
        _, p1 = ak_mod.issue_api_key("alice", label="first")
        _, p2 = ak_mod.issue_api_key("alice", label="second")
        ak_mod.revoke_api_key("alice", p1)
        names = [r["label"] for r in ak_mod.list_api_keys("alice")]
        # Active "second" comes before revoked "first".
        self.assertEqual(names[0], "second")
        self.assertEqual(names[1], "first")
        self.assertTrue(ak_mod.list_api_keys("alice")[1]["revoked"])


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        _seed_schema(self.db)
        self._saved = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.db
        _insert_user(self.db, "alice")
        _insert_user(self.db, "bob")

    def tearDown(self):
        auth_mod._DB_PATH = self._saved
        Path(self.db).unlink(missing_ok=True)

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _hdr(self, username: str, role: str = "employee") -> dict:
        return {"Authorization": f"Bearer {auth_mod.create_token(username, role)}"}

    def test_issue_requires_jwt(self):
        r = self._client().post("/api-keys/issue", json={"label": "ci"})
        self.assertEqual(r.status_code, 401)

    def test_issue_returns_plaintext_once_and_prefix(self):
        r = self._client().post("/api-keys/issue",
                                json={"label": "ci"},
                                headers=self._hdr("alice"))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["token"].startswith("jms_"))
        self.assertEqual(body["prefix"], body["token"][:ak_mod.KEY_PREFIX_LEN])
        self.assertEqual(body["label"], "ci")

    def test_list_returns_only_callers_keys(self):
        ak_mod.issue_api_key("alice", label="alice-key")
        ak_mod.issue_api_key("bob",   label="bob-key")
        r = self._client().get("/api-keys/list",
                               headers=self._hdr("alice"))
        self.assertEqual(r.status_code, 200, r.text)
        labels = [k["label"] for k in r.json()["keys"]]
        self.assertEqual(labels, ["alice-key"])

    def test_revoke_happy_path(self):
        _, prefix = ak_mod.issue_api_key("alice", label="ci")
        r = self._client().post("/api-keys/revoke",
                                json={"key_prefix": prefix},
                                headers=self._hdr("alice"))
        self.assertEqual(r.status_code, 200, r.text)
        # Listing shows it as revoked.
        rows = ak_mod.list_api_keys("alice")
        self.assertTrue(rows[0]["revoked"])

    def test_revoke_cross_user_returns_404(self):
        _, prefix = ak_mod.issue_api_key("alice", label="ci")
        # Bob tries to revoke alice's key.
        r = self._client().post("/api-keys/revoke",
                                json={"key_prefix": prefix},
                                headers=self._hdr("bob"))
        self.assertEqual(r.status_code, 404)

    def test_revoke_unknown_prefix_returns_404(self):
        r = self._client().post("/api-keys/revoke",
                                json={"key_prefix": "jms_nonexist"},
                                headers=self._hdr("alice"))
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
