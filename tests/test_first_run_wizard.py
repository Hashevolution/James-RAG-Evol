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
        # [§5 PR-D] inline onclick="firstRunDismiss()" replaced by
        # data-action="first-run-dismiss" routed through the click delegate.
        self.assertIn('data-action="first-run-dismiss"', self.html)

    def test_refresh_button_calls_firstRunCheck(self):
        # [§5 PR-D] inline onclick="firstRunCheck()" replaced by
        # data-action="first-run-check".
        self.assertIn('data-action="first-run-check"', self.html)


class FrontendJsTests(unittest.TestCase):
    """admin.js must define the wizard functions + wire them to login flow.

    Post-#372 (UI-IA Phase 2): the install endpoint POST + the
    /admin/llm/install-progress poller were extracted into the shared
    `LlmInstall.start(...)` controller in `llm-install.js`. admin.js
    keeps the wizard-specific orchestration (firstRunCheck / Show /
    Install / Dismiss / Row) and delegates the HTTP machinery via
    callbacks. The split is asserted on both files.
    """

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "admin.js").read_text(encoding="utf-8")
        cls.install_js = (
            ROOT / "frontend" / "static" / "llm-install.js"
        ).read_text(encoding="utf-8")

    def test_required_functions_defined(self):
        # _firstRunPollProgress moved into LlmInstall.start tick (no
        # longer a function in admin.js). The remaining wizard
        # functions stay in admin.js.
        for fn in ("firstRunCheck", "firstRunShow", "firstRunInstall",
                   "firstRunDismiss", "_firstRunRow"):
            self.assertIn(f"function {fn}", self.js,
                f"function '{fn}' must be defined")

    def test_check_uses_resolution_endpoint(self):
        idx = self.js.index("async function firstRunCheck")
        self.js.index("\n", self.js.index("}", idx + 200))
        body = self.js[idx:idx + 1500]
        self.assertIn("/admin/llm/resolution", body,
            "firstRunCheck must call /admin/llm/resolution")

    def test_show_uses_recommend_endpoint(self):
        idx = self.js.index("async function firstRunShow")
        body = self.js[idx:idx + 2500]
        self.assertIn("/admin/llm/recommend", body)

    def test_install_uses_install_endpoint(self):
        # admin.js's firstRunInstall now delegates to LlmInstall.start
        # which owns the POST to /llm/install/. Assert the delegation
        # in admin.js and the actual endpoint hit in llm-install.js.
        idx = self.js.index("async function firstRunInstall")
        body = self.js[idx:idx + 1500]
        self.assertIn("LlmInstall.start", body,
            "firstRunInstall must delegate to LlmInstall.start")
        self.assertIn("/llm/install/", self.install_js,
            "llm-install.js must POST to /llm/install/")

    def test_install_polls_progress(self):
        # Polling machinery moved to LlmInstall.start tick. Assert
        # admin.js wires onProgress + the poll endpoint + done check
        # both live in llm-install.js.
        idx = self.js.index("async function firstRunInstall")
        body = self.js[idx:idx + 1500]
        self.assertIn("onProgress", body,
            "firstRunInstall must wire an onProgress callback")
        self.assertIn("/admin/llm/install-progress", self.install_js,
            "llm-install.js must hit the progress endpoint")
        self.assertIn("p.done", self.install_js,
            "llm-install.js must check 'done' flag from progress endpoint")

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
