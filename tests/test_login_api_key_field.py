"""Login modal API key field (item #1-C, 2026-05-08).

User feedback: "로그인 창에 api key를 적을수 있는 칸도 추가". The
old flow used native `prompt('JAMES API Key:')` on first DOMContentLoaded
which is hostile UX on phones (system dialog, can't see the value
afterwards, can't easily change it).

New flow:
  - Login modal has a visible password-type input + 👁️ toggle.
  - Pre-filled from localStorage on showLogin.
  - Saves to localStorage on successful login (only if changed).
  - DOMContentLoaded: when no api_key stored, automatically opens
    the login modal so the user has a clear place to enter it.

Run:
  python -m unittest tests.test_login_api_key_field
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "index.html"
JS   = ROOT / "frontend" / "static" / "chat.js"
I18N = ROOT / "frontend" / "static" / "i18n.js"


class HtmlFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_api_key_input_present(self):
        self.assertIn('id="login-api-key"', self.html,
                      "API key input element missing from login modal")
        # Must be inside the login modal block.
        modal_idx = self.html.index('id="login-modal"')
        # Find the closing </div></div> of modal — search for the
        # trailing </body> instead, which should be near the end.
        # API key input must appear after login-modal opens.
        api_idx = self.html.index('id="login-api-key"')
        self.assertGreater(api_idx, modal_idx,
            "api-key field must be inside login-modal")

    def test_api_key_is_password_type(self):
        # Sensitive — default to hidden. Match the whole <input ...>
        # tag (attributes can come in any order around id="login-api-key").
        m = re.search(r'<input[^>]*id="login-api-key"[^>]*>', self.html, re.DOTALL)
        self.assertIsNotNone(m, "could not locate the <input> tag")
        self.assertIn('type="password"', m.group(0),
            "api key field must default to type='password'")

    def test_visibility_toggle_button_present(self):
        self.assertIn('id="login-api-key-toggle"', self.html,
            "missing 👁️ visibility-toggle button")
        self.assertIn('toggleApiKeyVisibility()', self.html,
            "toggle button must wire to toggleApiKeyVisibility()")

    def test_enter_key_submits_login(self):
        m = re.search(r'id="login-api-key"[^>]*', self.html)
        self.assertIn("if(event.key==='Enter') doLogin()", m.group(0),
            "Enter on api-key field must submit login (parity with pw field)")

    def test_hint_text_present(self):
        # Subtle hint pointing to .env JAMES_API_KEY so users know
        # where the value comes from.
        self.assertIn('data-i18n="auth.api_key_hint"', self.html)


class JsFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_no_native_prompt_on_load(self):
        # Old: prompt('JAMES API Key를 입력하세요:'). New flow uses
        # showLogin() instead.
        self.assertNotIn("prompt('JAMES API Key", self.js,
            "native prompt() should be replaced — bad mobile UX")
        self.assertNotIn("prompt(\"JAMES API Key", self.js,
            "native prompt() should be replaced (double-quoted form)")

    def test_show_login_called_when_no_api_key(self):
        # The chat init listener — find the one that touches james_api_key.
        # There are multiple DOMContentLoaded handlers in this file; locate
        # the one referencing the api-key check explicitly.
        m = re.search(
            r"DOMContentLoaded[^{]*\{[^}]*?james_api_key[^}]*?\}",
            self.js, re.DOTALL,
        )
        self.assertIsNotNone(m,
            "could not find the DOMContentLoaded handler that checks james_api_key")
        body = m.group(0)
        self.assertIn("showLogin", body,
            "must auto-open login modal when api_key missing")

    def test_show_login_prefills_field(self):
        idx = self.js.index("function showLogin")
        body = self.js[idx:idx + 800]
        self.assertIn("login-api-key", body,
            "showLogin must reference the api-key field")
        self.assertIn("getApiKey()", body,
            "must pre-fill from getApiKey() on open")

    def test_toggle_function_swaps_type(self):
        self.assertIn("function toggleApiKeyVisibility", self.js,
            "missing toggleApiKeyVisibility helper")
        idx = self.js.index("function toggleApiKeyVisibility")
        body = self.js[idx:idx + 600]
        self.assertIn("input.type = 'text'", body,
            "must swap to type='text' to reveal")
        self.assertIn("input.type = 'password'", body,
            "must swap back to type='password' to hide")

    def test_do_login_reads_field_value(self):
        idx = self.js.index("async function doLogin")
        m = re.search(r"\nasync function|\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 3000
        body = self.js[idx:end]
        self.assertIn("login-api-key", body,
            "doLogin must read the input field directly (not just localStorage)")
        # Must save new value back to localStorage when changed.
        self.assertIn("localStorage.setItem('james_api_key'", body,
            "doLogin must persist a freshly-entered key")
        # Must validate non-empty before sending.
        self.assertIn("API Key", body,
            "must show error when api key is missing")


class I18nKeysPresentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.i18n = I18N.read_text(encoding="utf-8")

    def test_api_key_label_in_both_languages(self):
        for key in ("'auth.api_key'", "'auth.api_key_hint'"):
            self.assertIn(key, self.i18n,
                f"i18n key {key} missing — UI label won't translate")
        # Both en + ko occurrences (key appears at least twice — once
        # per language block).
        self.assertGreaterEqual(self.i18n.count("'auth.api_key':"), 2,
            "api_key key must exist in both en + ko maps")
        self.assertGreaterEqual(self.i18n.count("'auth.api_key_hint':"), 2,
            "api_key_hint key must exist in both en + ko maps")


if __name__ == "__main__":
    unittest.main()
