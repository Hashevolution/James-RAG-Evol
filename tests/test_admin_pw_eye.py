"""Admin login password 👁️ toggle (item #A8-3, 2026-05-09).

User feedback: "패쓰워드 란에도 보이고 가리는 기능 눈 모양 토글 설치".
PR #117 added it to the chat page login modal. This PR brings parity
to the admin login modal.

Run:
  python -m unittest tests.test_admin_pw_eye
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "admin.html"
JS   = ROOT / "frontend" / "static" / "admin.js"


class HtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_toggle_button_present(self):
        self.assertIn('id="admin-login-pw-toggle"', self.html,
            "admin login pw toggle button missing")
        self.assertIn('toggleAdminPwVisibility()', self.html,
            "toggle button must wire to toggleAdminPwVisibility()")

    def test_default_emoji(self):
        m = re.search(
            r'id="admin-login-pw-toggle"[^>]*>(.*?)</button>',
            self.html,
        )
        self.assertIsNotNone(m, "couldn't locate toggle button content")
        self.assertIn("👁️", m.group(1),
            "default emoji should be 👁️ (visible)")

    def test_password_field_padding_for_button(self):
        # Padding-right ≥ 32px so the eye button doesn't overlap text.
        m = re.search(
            r'id="admin-login-pw"[^>]*style="([^"]+)"',
            self.html,
        )
        self.assertIsNotNone(m)
        style = m.group(1)
        # The padding shorthand is `10px 40px 10px 14px` — right side 40px.
        self.assertIn("10px 40px 10px 14px", style,
            "padding-right must accommodate the eye button (40px)")


class JsHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_toggle_function_exists(self):
        self.assertIn("function toggleAdminPwVisibility", self.js,
            "missing toggleAdminPwVisibility helper")

    def test_toggle_swaps_both_directions(self):
        idx = self.js.index("function toggleAdminPwVisibility")
        body = self.js[idx:idx + 600]
        self.assertIn("input.type = 'text'", body,
            "must reveal: type='password' → type='text'")
        self.assertIn("input.type = 'password'", body,
            "must hide: type='text' → type='password'")
        self.assertIn("'🙈'", body,
            "emoji must flip when revealed")


if __name__ == "__main__":
    unittest.main()
