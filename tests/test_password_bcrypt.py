"""W4 P1-A — bcrypt password hashing + transparent legacy migration.

Coverage:
  - ``hash_password`` returns the ``bcrypt$...`` envelope and round-trips
    through ``verify_password``.
  - ``verify_password`` accepts a pre-W4 unsalted SHA256 hex digest (the
    on-disk format every existing account uses).
  - ``verify_password`` rejects malformed input rather than raising.
  - ``authenticate()`` succeeds against a SHA256-seeded row and
    transparently rewrites that row to bcrypt on the way out — so the
    next login uses the strong hash without operator action.

Run:
  python -m unittest tests.test_password_bcrypt
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

# Set JWT secret BEFORE importing core.auth — the module's import-time
# guard rejects a missing/short secret with RuntimeError.
os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-bcrypt-suite-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core import auth as auth_mod  # noqa: E402


def _seed_legacy_row(path: str, username: str, password: str, role: str = "admin") -> None:
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
    conn.execute(
        "INSERT OR REPLACE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, hashlib.sha256(password.encode()).hexdigest(), role),
    )
    conn.commit()
    conn.close()


def _read_hash(path: str, username: str) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()[0]
    finally:
        conn.close()


class HashRoundTripTests(unittest.TestCase):
    def test_bcrypt_envelope_and_verify(self):
        h = auth_mod.hash_password("correct_password_42")
        self.assertTrue(h.startswith("bcrypt$"),
                        f"expected bcrypt$ envelope, got {h[:20]!r}")
        self.assertTrue(auth_mod.verify_password("correct_password_42", h))

    def test_bcrypt_rejects_wrong_password(self):
        h = auth_mod.hash_password("right_one")
        self.assertFalse(auth_mod.verify_password("wrong_one", h))

    def test_bcrypt_unicode_password(self):
        h = auth_mod.hash_password("한글_비밀번호_42")
        self.assertTrue(auth_mod.verify_password("한글_비밀번호_42", h))
        self.assertFalse(auth_mod.verify_password("한글_비밀번호_43", h))

    def test_two_hashes_of_same_password_differ(self):
        # bcrypt salts every call — same password must produce different
        # hashes (otherwise the salt isn't doing its job).
        a = auth_mod.hash_password("same_password")
        b = auth_mod.hash_password("same_password")
        self.assertNotEqual(a, b)
        self.assertTrue(auth_mod.verify_password("same_password", a))
        self.assertTrue(auth_mod.verify_password("same_password", b))


class LegacySha256AcceptanceTests(unittest.TestCase):
    """Existing accounts on disk were stored as raw SHA256 hex. The
    verifier must accept that form so logins don't break the day this
    PR ships — migration happens later, on successful login."""

    def test_verify_accepts_legacy_sha256(self):
        legacy = hashlib.sha256(b"oldpw").hexdigest()
        self.assertTrue(auth_mod.verify_password("oldpw", legacy))

    def test_verify_rejects_wrong_password_against_legacy(self):
        legacy = hashlib.sha256(b"oldpw").hexdigest()
        self.assertFalse(auth_mod.verify_password("not_oldpw", legacy))

    def test_verify_handles_empty_or_garbage_stored(self):
        # Defensive: bad rows must not raise. Authentication path
        # treats this as "deny" — never crash the request.
        self.assertFalse(auth_mod.verify_password("any", ""))
        self.assertFalse(auth_mod.verify_password("any", "not-a-hash"))
        self.assertFalse(auth_mod.verify_password("any", "bcrypt$garbage"))


class TransparentMigrationTests(unittest.TestCase):
    """authenticate() must rewrite legacy rows to bcrypt on first
    successful login, with zero operator action and zero user-visible
    disruption. This is the core W4 P1-A promise."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.path = self._tmp.name
        _seed_legacy_row(self.path, "admin", "oldpw", "admin")
        # Point the module at our temp DB. Restored in tearDown.
        self._saved = auth_mod._DB_PATH
        auth_mod._DB_PATH = self.path

    def tearDown(self):
        auth_mod._DB_PATH = self._saved
        Path(self.path).unlink(missing_ok=True)

    def test_login_with_legacy_password_succeeds(self):
        result = auth_mod.authenticate("admin", "oldpw")
        self.assertIsNotNone(result)
        self.assertEqual(result["role"], "admin")
        self.assertEqual(result["username"], "admin")
        self.assertIn("token", result)

    def test_legacy_row_rewritten_to_bcrypt_on_success(self):
        before = _read_hash(self.path, "admin")
        self.assertEqual(len(before), 64,
                         "test setup must seed a 64-char SHA256 hex digest")

        result = auth_mod.authenticate("admin", "oldpw")
        self.assertIsNotNone(result)

        after = _read_hash(self.path, "admin")
        self.assertTrue(after.startswith("bcrypt$"),
                        f"row should now be bcrypt, got {after[:20]!r}")
        # New password still verifies (we did not change the password,
        # only the stored representation).
        self.assertTrue(auth_mod.verify_password("oldpw", after))

    def test_second_login_does_not_re_rehash(self):
        # First login migrates. Second login should see bcrypt$ and
        # leave the row alone.
        self.assertIsNotNone(auth_mod.authenticate("admin", "oldpw"))
        first = _read_hash(self.path, "admin")
        self.assertIsNotNone(auth_mod.authenticate("admin", "oldpw"))
        second = _read_hash(self.path, "admin")
        # Same bcrypt hash both times — no churn.
        self.assertEqual(first, second,
                         "post-migration logins must NOT re-hash; that "
                         "would invalidate stable equality checks and "
                         "increase needless write load")

    def test_failed_login_does_not_migrate(self):
        before = _read_hash(self.path, "admin")
        self.assertIsNone(auth_mod.authenticate("admin", "wrong_password"))
        after = _read_hash(self.path, "admin")
        self.assertEqual(before, after,
                         "rehash must only happen on a verified login")


if __name__ == "__main__":
    unittest.main()
