"""[PR plan-3, 2026-05-09] Admin first-run wizard.

Goal: when an operator opens /admin and Ollama has 0 models installed,
show a hardware-aware install wizard so the operator never has to
guess which `ollama pull <X>` to run.

Components covered:
  Backend
    - server startup banner: friendly console message when ollama is
      empty, pointing to admin wizard
  Frontend
    - admin.html : firstrun-wizard-modal with placeholders for HW
      summary + recommendations + progress
    - admin.js   : firstRunCheck / firstRunShow / firstRunInstall /
      _firstRunPollProgress / firstRunDismiss
    - Trigger    : after admin login success (existing flow), call
      firstRunCheck via setTimeout
    - Dismiss    : sessionStorage so a re-login doesn't re-popup;
      ↻ refresh button always re-checks

Run:
    python -m unittest tests.test_first_run_wizard
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class StartupBannerTests(unittest.TestCase):
    """server_llmwiki on_startup must check resolver + emit a clear
    banner pointing at the admin wizard when no models are installed."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_on_startup_calls_resolution_snapshot(self):
        idx = self.src.index("async def on_startup")
        nxt = self.src.index("\nasync def ", idx + 1)
        body = self.src[idx:nxt]
        self.assertIn("resolution_snapshot", body,
            "on_startup must check Ollama state via resolution_snapshot")

    def test_empty_models_emits_banner(self):
        idx = self.src.index("async def on_startup")
        nxt = self.src.index("\nasync def ", idx + 1)
        body = self.src[idx:nxt]
        # The banner must mention the admin wizard path so operator
        # knows where to go.
        self.assertIn("/admin", body)
        self.assertRegex(body, r"ollama pull",
            "banner must show the install command as a fallback")
        # The 'no models installed' branch is conditional on the
        # `installed` list being empty (Python `if not installed:`).
        self.assertTrue(
            "not installed" in body or "if not snap" in body or "0개" in body,
            "must branch on empty installed list",
        )

    def test_startup_failure_does_not_crash_server(self):
        # Resolver call must be wrapped in try/except so a bad Ollama
        # state never blocks startup.
        idx = self.src.index("resolution_snapshot")
        # Look back ~400 chars for a try.
        prelude = self.src[max(0, idx - 400):idx]
        self.assertIn("try:", prelude)


class FrontendModalTests(unittest.TestCase):
    """admin.html must declare firstrun-wizard-modal + sub-elements."""

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "admin.html").read_text(encoding="utf-8")

    def test_modal_present(self):
        self.assertIn('id="firstrun-wizard-modal"', self.html)

    def test_required_subelements(self):
        for elem_id in ("firstrun-hw-summary",
                         "firstrun-recommendations",
                         "firstrun-progress",
                         "firstrun-progress-text",
                         "firstrun-progress-bar",
                         "firstrun-later-btn"):
            self.assertIn(f'id="{elem_id}"', self.html,
                f"modal must contain element with id={elem_id}")

    def test_dismiss_button_calls_firstRunDismiss(self):
        self.assertIn("onclick=\"firstRunDismiss()\"", self.html)

    def test_refresh_button_calls_firstRunCheck(self):
        self.assertIn("onclick=\"firstRunCheck()\"", self.html)


class FrontendJsTests(unittest.TestCase):
    """admin.js must define the wizard functions + wire them to login flow."""

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "admin.js").read_text(encoding="utf-8")

    def test_required_functions_defined(self):
        for fn in ("firstRunCheck", "firstRunShow", "firstRunInstall",
                   "_firstRunPollProgress", "firstRunDismiss",
                   "_firstRunRow"):
            self.assertIn(f"function {fn}", self.js,
                f"function '{fn}' must be defined")

    def test_check_uses_resolution_endpoint(self):
        idx = self.js.index("async function firstRunCheck")
        nxt = self.js.index("\n", self.js.index("}", idx + 200))
        body = self.js[idx:idx + 1500]
        self.assertIn("/admin/llm/resolution", body,
            "firstRunCheck must call /admin/llm/resolution")

    def test_show_uses_recommend_endpoint(self):
        idx = self.js.index("async function firstRunShow")
        body = self.js[idx:idx + 2500]
        self.assertIn("/admin/llm/recommend", body)

    def test_install_uses_install_endpoint(self):
        idx = self.js.index("async function firstRunInstall")
        body = self.js[idx:idx + 1500]
        self.assertIn("/llm/install/", body)

    def test_install_polls_progress(self):
        idx = self.js.index("async function _firstRunPollProgress")
        body = self.js[idx:idx + 1500]
        self.assertIn("/admin/llm/install-progress", body)
        self.assertIn("p.done", body,
            "must check 'done' flag from progress endpoint")

    def test_dismiss_sets_session_flag(self):
        idx = self.js.index("function firstRunDismiss")
        body = self.js[idx:idx + 400]
        self.assertIn("sessionStorage", body,
            "dismiss must persist via sessionStorage so re-login "
            "doesn't immediately re-popup the wizard")

    def test_check_runs_after_login(self):
        # The login success path (existing — modal hidden + loadDashboard)
        # must trigger firstRunCheck via setTimeout (so dashboard
        # loads first).
        idx = self.js.index("if (modal) modal.style.display = 'none'")
        body = self.js[idx:idx + 500]
        self.assertIn("firstRunCheck", body,
            "login success must trigger firstRunCheck")

    def test_xss_guard_on_model_tag(self):
        # The recommendation rendering must escape the model tag —
        # tags come from server but are rendered into innerHTML.
        idx = self.js.index("function _firstRunRow")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("_escHtml", body,
            "_firstRunRow must use _escHtml for tag/desc fields")


class TriggerSemantics(unittest.TestCase):
    """Wizard must NOT show when models are already installed."""

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "admin.js").read_text(encoding="utf-8")

    def test_check_only_shows_when_empty(self):
        # The function body must branch on installed.length === 0.
        idx = self.js.index("async function firstRunCheck")
        body = self.js[idx:idx + 1500]
        self.assertIn("installed.length === 0", body,
            "wizard must only show when ollama list is empty")
        # And must hide the modal when models exist (recovery case).
        self.assertIn("display = 'none'", body)

    def test_dismiss_respected_when_models_exist(self):
        # If user dismissed AND models exist, no re-popup.
        idx = self.js.index("async function firstRunCheck")
        body = self.js[idx:idx + 1500]
        self.assertIn("james_firstrun_dismissed", body)


if __name__ == "__main__":
    unittest.main()
