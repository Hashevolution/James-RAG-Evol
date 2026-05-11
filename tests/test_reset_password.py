"""tools/admin/reset_password.py — unit tests + auth.py compatibility.

Coverage:
  - The script's hash format is *verifier-compatible* with
    ``core.auth.verify_password`` (W4 P1-A: bcrypt salts every output,
    so byte equality is no longer meaningful — round-trip through the
    verifier is).
  - ``reset_password()`` updates an existing row in a temp DB and the
    new password authenticates through ``core.auth.verify_password``.
  - ``reset_password()`` refuses to create a new user (the silent-mint
    footgun the script's docstring promises to avoid).
  - ``main()`` returns the documented exit codes:
      0 success / 1 generic / 2 no-such-user / 3 cancelled
  - End-to-end: reset password via main() then verify via the same
    path the auth module uses.

Run:
  python -m unittest tests.test_reset_password
"""
from __future__ import annotations

import io
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch as mock_patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _seed_db(path: str) -> None:
    """Build a minimal users table with one known row, matching the
    schema in core.auth._init_db."""
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE users (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL,
            active        INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Pre-existing admin with a known initial hash (sha256("oldpw")).
    import hashlib
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("admin", hashlib.sha256(b"oldpw").hexdigest(), "admin"),
    )
    conn.commit()
    conn.close()


def _row(path: str, username: str) -> dict | None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


class HashCompatibilityTests(unittest.TestCase):
    """The script's hash MUST authenticate through core.auth.verify_password.
    bcrypt salts every output, so we round-trip rather than compare bytes —
    a drift in *format* (prefix, encoding, algorithm) would silently lock
    the user out. Fail loudly on that."""

    def test_script_hash_verifies_via_auth_module(self):
        from tools.admin.reset_password import hash_password
        from core.auth import verify_password
        # 한글 + emoji + symbols + boundary lengths. Empty string is
        # excluded — the script's CLI rejects it (and bcrypt accepts it
        # in principle, but the policy is "non-empty").
        for pw in ("simple", "한글비밀번호", "abc!@#$%^&*()_+", "long" * 17):
            h = hash_password(pw)
            self.assertTrue(h.startswith("bcrypt$"),
                            f"expected bcrypt$ prefix, got {h[:20]!r}")
            self.assertTrue(
                verify_password(pw, h),
                f"reset hash for {pw[:20]!r} did not verify — resetting "
                f"would lock the user out of the real authenticate() path",
            )

    def test_script_hash_rejects_wrong_password(self):
        from tools.admin.reset_password import hash_password
        from core.auth import verify_password
        h = hash_password("right_password_42")
        self.assertFalse(verify_password("wrong_password_42", h))


class ResetPasswordCoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.path = self._tmp.name
        _seed_db(self.path)

    def tearDown(self):
        Path(self.path).unlink(missing_ok=True)

    def test_existing_user_password_updated(self):
        from tools.admin.reset_password import reset_password
        from core.auth import verify_password
        ok = reset_password(self.path, "admin", "new_secret_pw_42")
        self.assertTrue(ok)
        row = _row(self.path, "admin")
        # bcrypt: salt-randomized → can't compare bytes. Verify instead.
        self.assertTrue(row["password_hash"].startswith("bcrypt$"))
        self.assertTrue(
            verify_password("new_secret_pw_42", row["password_hash"]),
            "post-reset hash must verify against the new password",
        )

    def test_nonexistent_user_refused(self):
        from tools.admin.reset_password import reset_password
        # Pre-row count
        before = _row(self.path, "admin")["password_hash"]
        ok = reset_password(self.path, "ghost-user-does-not-exist", "any")
        self.assertFalse(ok, "reset_password must NOT create users")
        # Pre-existing row untouched.
        after = _row(self.path, "admin")["password_hash"]
        self.assertEqual(before, after,
                         "refusing to create must not mutate existing rows")
        # And the ghost row was NOT silently inserted.
        self.assertIsNone(_row(self.path, "ghost-user-does-not-exist"))

    def test_missing_db_file_refused(self):
        from tools.admin.reset_password import reset_password
        ok = reset_password("/nonexistent/path.db", "admin", "any")
        self.assertFalse(ok, "missing DB file must produce a clear no, not a crash")


class MainExitCodeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.path = self._tmp.name
        _seed_db(self.path)

    def tearDown(self):
        Path(self.path).unlink(missing_ok=True)

    def _run_main(self, argv):
        from tools.admin.reset_password import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_exit_0_on_successful_reset(self):
        code, out = self._run_main([
            "--username", "admin",
            "--password", "new_password_42",
            "--db", self.path,
            "--yes",
        ])
        self.assertEqual(code, 0)
        self.assertIn("password updated", out)

    def test_exit_2_when_user_missing(self):
        code, out = self._run_main([
            "--username", "no-such-user",
            "--password", "anything42",
            "--db", self.path,
            "--yes",
        ])
        self.assertEqual(code, 2,
                         "missing user must exit 2 (documented contract)")
        self.assertIn("does not exist", out)

    def test_exit_1_on_short_password(self):
        # Less than 8 chars → reject early.
        code, out = self._run_main([
            "--username", "admin",
            "--password", "short",
            "--db", self.path,
            "--yes",
        ])
        self.assertEqual(code, 1)
        self.assertIn("8 characters", out)

    def test_existing_row_untouched_when_short_password_rejected(self):
        # If the policy reject fires, the row must NOT have been written.
        before = _row(self.path, "admin")["password_hash"]
        self._run_main([
            "--username", "admin",
            "--password", "x",  # too short
            "--db", self.path,
            "--yes",
        ])
        after = _row(self.path, "admin")["password_hash"]
        self.assertEqual(before, after)


class EndToEndAuthCompatTests(unittest.TestCase):
    """After reset_password runs, the new password must work via the
    same hash path that core.auth.authenticate uses."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.path = self._tmp.name
        _seed_db(self.path)

    def tearDown(self):
        Path(self.path).unlink(missing_ok=True)

    def test_reset_then_authenticate_with_new_pw_succeeds(self):
        from tools.admin.reset_password import reset_password
        from core.auth import verify_password

        new_pw = "fresh_password_42"
        self.assertTrue(reset_password(self.path, "admin", new_pw))

        # Mirror what core.auth.authenticate does internally:
        #   verify_password(input, row.password_hash)
        row = _row(self.path, "admin")
        self.assertTrue(
            verify_password(new_pw, row["password_hash"]),
            "post-reset hash must verify against auth.authenticate's "
            "comparison; otherwise the user is still locked out",
        )
        # And the previous (legacy SHA256 of "oldpw") seed no longer
        # passes — proving the row was actually rewritten, not just
        # double-written.
        self.assertFalse(verify_password("oldpw", row["password_hash"]))


if __name__ == "__main__":
    unittest.main()
