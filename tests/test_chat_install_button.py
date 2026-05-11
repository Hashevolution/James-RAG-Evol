"""[item #1, 2026-05-09] Chat secondary picker — explicit install status
+ admin-only install button.

User feedback: "챗 웹페이지에 사용자 대화창에 모델을 선택할수 있는 부분
에서 이미 설치된 모델 표시, 선택 가능하지만 설치 안되있는 경우 설치
하도록 버튼 생성".

Backend already had everything (PR #113 catalog, PR #136 selected_model
wiring, PR #134 live install progress). The gap was UX:
  - dropdown showed ⚠️ for not-installed but NO marker for installed
    (absence-as-signal too subtle)
  - install button was visible to non-admin, who could click it and
    only then learn they couldn't install (toast). Cleaner to hide
    entirely (decision C-1).

Changes
  - Dropdown options: ✓ for installed, ⚠️ 미설치 for not-installed
  - title attr: explicit "설치됨" / "미설치 — 선택 후 옆 버튼으로 설치
    가능 (admin)"
  - updateInstallButton(): early-return when userRole !== 'admin'
  - Login/logout/storage-event: refresh button visibility on role change
  - triggerModelInstall(): keep client-side admin guard as defense-in-
    depth (server has its own gate, but a console-script bypass should
    still hit a toast)

Run:
    python -m unittest tests.test_chat_install_button
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS  = ROOT / "frontend" / "static" / "chat.js"


class DropdownMarkerTests(unittest.TestCase):
    """Dropdown options must show explicit installed/uninstalled markers."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def _refresh_body(self) -> str:
        idx = self.js.index("function refreshModelPicker")
        nxt = self.js.index("\nfunction ", idx + 1)
        return self.js[idx:nxt]

    def test_installed_marker_explicit(self):
        body = self._refresh_body()
        # The conditional must produce a non-empty marker for the
        # installed branch — absence-as-signal was the rejected design.
        self.assertRegex(
            body,
            r"m\.installed\s*\?\s*['\"`]\s*✓",
            "installed branch must produce a ✓ (or similar) marker",
        )

    def test_not_installed_marker_present(self):
        body = self._refresh_body()
        self.assertIn("⚠️ 미설치", body,
            "not-installed branch must say 미설치 explicitly")

    def test_title_attr_describes_status(self):
        body = self._refresh_body()
        self.assertIn("설치됨", body)
        # The not-installed title hints at the install path.
        self.assertRegex(
            body,
            r"미설치.*설치 가능|admin",
            "not-installed title should hint at the install action",
        )


class InstallButtonAdminGateTests(unittest.TestCase):
    """[#1 / C-1] updateInstallButton must hide button for non-admin."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def _update_body(self) -> str:
        idx = self.js.index("function updateInstallButton")
        nxt = self.js.index("\n/* ", idx + 1)
        return self.js[idx:nxt]

    def test_function_early_returns_when_not_admin(self):
        body = self._update_body()
        self.assertIn("userRole !== 'admin'", body,
            "must check role before showing button")
        # Ensure the role check appears BEFORE the show logic — i.e.,
        # a hide+return path exists for non-admin.
        role_chk_idx = body.index("userRole !== 'admin'")
        # There should be a `display = 'none'` and a `return` between
        # the role check and the next significant logic.
        snippet = body[role_chk_idx:role_chk_idx + 200]
        self.assertIn("display = 'none'", snippet)
        self.assertIn("return", snippet)

    def test_login_refreshes_install_button(self):
        # When user logs in (potentially upgrading to admin), the
        # button visibility must re-evaluate.
        idx = self.js.index("✅ ${username} (${userRole}) 로그인 완료")
        # Walk back ~600 chars to find the surrounding login-success block.
        block = self.js[max(0, idx - 600):idx + 200]
        self.assertIn("updateInstallButton", block,
            "login success path must call updateInstallButton")

    def test_logout_refreshes_install_button(self):
        idx = self.js.index("function logout")
        body = self.js[idx:idx + 500]
        self.assertIn("updateInstallButton", body,
            "logout must hide the install button (admin → external)")

    def test_storage_event_refreshes_install_button(self):
        # Cross-tab login state change must reach this tab's button.
        idx = self.js.index("storage", self.js.index("addEventListener"))
        body = self.js[idx - 50:idx + 600]
        self.assertIn("updateInstallButton", body,
            "storage event handler must refresh install button on "
            "cross-tab role change (PR #130 SSO + #1)")


class TriggerInstallDefenseInDepthTests(unittest.TestCase):
    """Even with the button hidden, triggerModelInstall must still
    reject non-admin (defense in depth — console invocation, etc.)."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_trigger_still_checks_role(self):
        idx = self.js.index("async function triggerModelInstall")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("userRole !== 'admin'", body,
            "client-side admin guard kept — server has its own guard "
            "but a script bypass should still get clear feedback")
        self.assertIn("toast", body,
            "non-admin trigger must show toast, not silent failure")


if __name__ == "__main__":
    unittest.main()
