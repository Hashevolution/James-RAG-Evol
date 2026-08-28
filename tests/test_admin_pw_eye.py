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
        # [§5 PR-D] inline onclick="toggleAdminPwVisibility()" replaced
        # by data-action="toggle-admin-pw-visibility".
        self.assertIn('id="admin-login-pw-toggle"', self.html,
            "admin login pw toggle button missing")
        self.assertIn('data-action="toggle-admin-pw-visibility"', self.html,
            "toggle button must wire to toggle-admin-pw-visibility "
            "(routed through the click delegate)")

    def test_default_label_present(self):
        """The toggle must carry a visible label before any click.

        [2026-08-26] Was asserting the 👁️ emoji. The control moved to
        Korean text labels (표시 / 숨김) in admin.js, but the markup was
        left with an empty button body — so the button rendered blank
        until first clicked, and only the aria-label identified it. This
        test caught a real gap, so the fix is in admin.html and the
        assertion follows the new labelling rather than the old glyph.
        """
        m = re.search(
            r'id="admin-login-pw-toggle"[^>]*>(.*?)</button>',
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m, "couldn't locate toggle button content")
        label = m.group(1).strip()
        self.assertTrue(label, "toggle button must not render empty")
        self.assertEqual(label, "표시",
            "initial label is 표시 — the field starts masked, so the "
            "button offers to reveal it")

    def test_password_field_padding_for_button(self):
        # Padding-right ≥ 32px so the eye button doesn't overlap text.
        # [2026-08-26] The inline style moved into a generated utility
        # class when inline styles were extracted; the declaration is
        # unchanged, so follow it into the stylesheet.
        # Attribute order is not guaranteed (the markup has class before
        # id), and `admin-login-pw` is a prefix of `admin-login-pw-toggle`
        # — so match the whole tag and require the exact id.
        tag = re.search(r'<input[^>]*id="admin-login-pw"[^>]*>', self.html)
        self.assertIsNotNone(tag, "password input not found")
        m = re.search(r'class="([^"]+)"', tag.group(0))
        self.assertIsNotNone(m, "password input must carry its class")
        util = [c for c in m.group(1).split() if c.startswith("u-")]
        self.assertTrue(util, "expected an extracted utility class")
        css = (ROOT / "frontend" / "static" / "tokens.css").read_text(
            encoding="utf-8")
        rule = re.search(r"\.%s\{([^}]*)\}" % re.escape(util[0]), css)
        self.assertIsNotNone(rule,
            f"utility class {util[0]} referenced but never declared")
        # The padding shorthand is `10px 40px 10px 14px` — right side 40px.
        self.assertIn("10px 40px 10px 14px", rule.group(1),
            "padding-right must accommodate the toggle button (40px)")


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
        # [2026-08-26] Labels are Korean text now, not emoji.
        self.assertIn("'숨김'", body,
            "label must flip to 숨김 when the password is revealed")
        self.assertIn("'표시'", body,
            "label must flip back to 표시 when it is masked again")


if __name__ == "__main__":
    unittest.main()
