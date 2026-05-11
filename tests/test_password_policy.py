"""W4 P1-B — password + username policy validation.

Covers the pure-function policy validators in ``core.auth`` so the
signup endpoint test can focus on the HTTP shape and not re-verify
every policy edge case.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-policy-suite-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.auth import (  # noqa: E402
    validate_password_policy,
    validate_username,
    PASSWORD_MIN_LEN,
    PASSWORD_MAX_LEN,
    USERNAME_MIN_LEN,
    USERNAME_MAX_LEN,
)


class PasswordPolicyTests(unittest.TestCase):
    def test_accepts_minimum_acceptable(self):
        # 8 chars, letter + digit
        self.assertIsNone(validate_password_policy("abcd1234"))

    def test_accepts_long_within_bcrypt_window(self):
        pw = "a" * 70 + "12"
        self.assertEqual(len(pw), 72)
        self.assertIsNone(validate_password_policy(pw))

    def test_rejects_too_short(self):
        msg = validate_password_policy("abc12")
        self.assertIsNotNone(msg)
        self.assertIn(str(PASSWORD_MIN_LEN), msg)

    def test_rejects_too_long_to_avoid_bcrypt_truncation(self):
        # 73 chars — bcrypt would silently drop the last byte. Reject.
        msg = validate_password_policy("a" * 71 + "12")
        self.assertIsNotNone(msg)
        self.assertIn(str(PASSWORD_MAX_LEN), msg)

    def test_rejects_letters_only(self):
        msg = validate_password_policy("abcdefghij")
        self.assertIsNotNone(msg)
        self.assertIn("숫자", msg)

    def test_rejects_digits_only(self):
        msg = validate_password_policy("12345678")
        self.assertIsNotNone(msg)
        self.assertIn("영문", msg)

    def test_accepts_unicode_letters_with_digit(self):
        # 한글 letters count as alpha via str.isalpha — intentional.
        # The policy is "letter + digit", not "ASCII letter + digit".
        # 6 char Korean + 2 digit = 8, exactly at PASSWORD_MIN_LEN.
        self.assertIsNone(validate_password_policy("한글비밀번호12"))

    def test_rejects_non_string(self):
        self.assertIsNotNone(validate_password_policy(None))         # type: ignore[arg-type]
        self.assertIsNotNone(validate_password_policy(12345678))     # type: ignore[arg-type]


class UsernamePolicyTests(unittest.TestCase):
    def test_accepts_lowercase_alphanumeric(self):
        self.assertIsNone(validate_username("alice"))
        self.assertIsNone(validate_username("user_01"))
        self.assertIsNone(validate_username("a-b-c"))

    def test_rejects_uppercase(self):
        # Case-folding collision with admin is the reason. Reject loudly.
        msg = validate_username("Alice")
        self.assertIsNotNone(msg)

    def test_rejects_korean(self):
        msg = validate_username("앨리스")
        self.assertIsNotNone(msg)

    def test_rejects_space(self):
        msg = validate_username("alice bob")
        self.assertIsNotNone(msg)

    def test_rejects_special_chars(self):
        for bad in ("alice!", "alice.", "alice/", "../etc", "alice@host"):
            self.assertIsNotNone(validate_username(bad),
                                 f"should reject {bad!r}")

    def test_length_bounds(self):
        # Below min
        self.assertIsNotNone(validate_username("ab"))
        # At min
        self.assertIsNone(validate_username("a" * USERNAME_MIN_LEN))
        # At max
        self.assertIsNone(validate_username("a" * USERNAME_MAX_LEN))
        # Above max
        self.assertIsNotNone(validate_username("a" * (USERNAME_MAX_LEN + 1)))


if __name__ == "__main__":
    unittest.main()
