"""Frontend §5 — inline event handlers → ``data-action`` + delegation.

CSP-friendly migration (HANDOVER_WEB_UI.md §4 priority 5).

Every page-level HTML file in ``frontend/`` must be free of inline
``onclick=``, ``onchange=``, ``onkeydown=``, ``onkeyup=``,
``onsubmit=``, ``oninput=``, ``onfocus=``, ``onblur=`` handler
attributes. The matching JS file installs a single document-level
delegated handler that routes by ``data-action`` (clicks) and by
``e.target.id`` + ``e.key`` (keyboard shortcuts).

This contract is rolled out **page by page**. Each PR flips one
page's assertions on. Pages still using inline handlers stay on the
known-bad list (``_LEGACY_INLINE_PAGES``) and graduate as their PR
lands.

Run:
    python -m unittest tests.test_frontend_event_delegation
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STATIC = FRONTEND / "static"

# Inline handler attributes the migration removes. Mirrors the
# common DOM event-attribute surface; if a new one appears in HTML,
# add it here so the contract catches it.
_INLINE_ATTR_RE = re.compile(
    r"\son(?:click|change|submit|input|keydown|keyup|keypress"
    r"|focus|blur|paste|drag(?:start|enter|over|leave|end)?|drop"
    r"|mouseover|mouseout|mouseenter|mouseleave"
    r"|mousedown|mouseup)\s*=",
    re.IGNORECASE,
)

# Pages already migrated to delegation. Each PR adds a name here.
_MIGRATED_PAGES = {
    "graph.html",
    "workspace.html",
    "index.html",
}

# Pages still using inline handlers. Will shrink to empty by PR-D.
_LEGACY_INLINE_PAGES = {
    "admin.html",
}


class NoInlineHandlersTests(unittest.TestCase):
    """Migrated pages must have zero inline event-handler attributes."""

    def test_migrated_pages_have_no_inline_handlers(self):
        for name in sorted(_MIGRATED_PAGES):
            with self.subTest(page=name):
                src = (FRONTEND / name).read_text(encoding="utf-8")
                hits = _INLINE_ATTR_RE.findall(src)
                self.assertEqual(
                    hits, [],
                    name + " still has inline handler attributes: "
                    + ", ".join(sorted(set(h.strip() for h in hits))),
                )

    def test_legacy_pages_still_known(self):
        # Guardrail: if a legacy page silently becomes clean, promote
        # it to _MIGRATED_PAGES so the contract starts protecting it.
        for name in sorted(_LEGACY_INLINE_PAGES):
            with self.subTest(page=name):
                src = (FRONTEND / name).read_text(encoding="utf-8")
                self.assertRegex(
                    src, _INLINE_ATTR_RE,
                    name + " is now free of inline handlers — please "
                    "move it from _LEGACY_INLINE_PAGES to "
                    "_MIGRATED_PAGES in this test.",
                )


class GraphPageDelegationTests(unittest.TestCase):
    """PR-A — graph.html now routes via data-action; graph.js installs
    a single document click delegate plus a keydown delegate for
    Enter (login submit) and Escape (search drawer close)."""

    @classmethod
    def setUpClass(cls):
        cls.html = (FRONTEND / "graph.html").read_text(encoding="utf-8")
        cls.js   = (STATIC / "graph.js").read_text(encoding="utf-8")

    def test_html_uses_data_action_for_lang_toggle(self):
        self.assertRegex(
            self.html,
            r'data-lang-toggle\s+data-action="toggle-lang"',
            "language toggle button must carry data-action=toggle-lang",
        )

    def test_html_uses_data_action_for_drawer_toggle(self):
        self.assertIn(
            'data-action="toggle-search-drawer"', self.html,
            "search drawer toggle must carry data-action=toggle-search-drawer",
        )

    def test_html_uses_data_action_for_login_button(self):
        self.assertIn(
            'data-action="do-login"', self.html,
            "login button must carry data-action=do-login",
        )

    def test_html_drops_inline_login_submit_keys(self):
        # The two login modal inputs used to fire doLogin() on Enter
        # via inline onkeydown. After §5 migration they're plain
        # <input>s — the JS keydown delegate watches them by id.
        self.assertNotRegex(
            self.html,
            r'id="login-(pw|apikey)"[^>]*onkeydown',
            "login inputs must not carry inline onkeydown",
        )

    def test_js_installs_click_delegation(self):
        # Single document-level click listener, switch by data-action.
        self.assertRegex(
            self.js,
            r"document\.addEventListener\(\s*['\"]click['\"]",
            "graph.js must install a document-level click delegate",
        )
        self.assertIn("data-action", self.js,
            "graph.js must read data-action in its delegate")

    def test_js_installs_keydown_delegation(self):
        self.assertRegex(
            self.js,
            r"document\.addEventListener\(\s*['\"]keydown['\"]",
            "graph.js must install a document-level keydown delegate",
        )
        # Enter on login fields and Escape on tsd-search must be routed.
        self.assertIn("login-pw", self.js)
        self.assertIn("login-apikey", self.js)
        self.assertIn("tsd-search", self.js)


class WorkspacePageDelegationTests(unittest.TestCase):
    """PR-B — workspace.html and workspace.js route every click via
    ``data-action``; static inputs are bound by id at DOMContentLoaded.

    workspace.js dynamically renders <tr> rows and job-action buttons
    through innerHTML; those templates must also emit ``data-action``
    rather than inline ``onclick``."""

    @classmethod
    def setUpClass(cls):
        cls.html = (FRONTEND / "workspace.html").read_text(encoding="utf-8")
        cls.js   = (STATIC / "workspace.js").read_text(encoding="utf-8")

    # ─── HTML ──────────────────────────────────────────────────────
    def test_html_uses_data_action_for_header_buttons(self):
        for action in (
            "toggle-lang", "show-login", "do-logout",
        ):
            with self.subTest(action=action):
                self.assertIn(f'data-action="{action}"', self.html)

    def test_html_uses_data_action_for_tab_nav(self):
        # All three sidebar tabs route through one 'select-tab' action,
        # with the tab name pulled from the existing data-tab attribute.
        self.assertEqual(
            self.html.count('data-action="select-tab"'), 3,
            "all three nav-item tabs must carry data-action=select-tab",
        )
        for tab in ("data", "jobs", "search"):
            self.assertRegex(
                self.html,
                r'data-tab="' + tab + r'"[^>]*data-action="select-tab"',
                f'nav-item[data-tab={tab}] must carry data-action=select-tab',
            )

    def test_html_uses_data_action_for_pager_and_jobs(self):
        for action in (
            "data-page-prev", "data-page-next",
            "run-job", "reload-jobs",
            "close-detail", "close-login", "do-login",
            "open-forgot",
        ):
            with self.subTest(action=action):
                self.assertIn(f'data-action="{action}"', self.html)

    def test_html_drops_inline_login_submit_keys(self):
        # login-pw / login-apikey used to fire doLogin() on Enter via
        # inline onkeydown — now handled by direct addEventListener on
        # those stable ids in _bindStableInputs.
        self.assertNotRegex(
            self.html,
            r'id="login-(pw|apikey)"[^>]*onkeydown',
        )

    def test_html_drops_javascript_href(self):
        # ``href="javascript:openForgot()"`` (CSP-hostile) replaced by
        # ``href="#" data-action="open-forgot"``; the click delegate
        # calls preventDefault before invoking the action.
        self.assertNotIn('href="javascript:', self.html)

    def test_html_forgot_link_carries_data_action(self):
        self.assertRegex(
            self.html,
            r'<a\s+href="#"\s+data-action="open-forgot"',
        )

    # ─── JS ────────────────────────────────────────────────────────
    def test_js_installs_click_delegation(self):
        self.assertRegex(
            self.js,
            r"document\.addEventListener\(\s*['\"]click['\"]",
            "workspace.js must install a document-level click delegate",
        )
        self.assertIn("data-action", self.js)

    def test_js_binds_stable_inputs(self):
        # Helper must exist and DOMContentLoaded must call it. Without
        # this binding the search, status select and login-Enter
        # shortcuts silently stop working.
        self.assertIn("_bindStableInputs", self.js)
        self.assertRegex(
            self.js,
            r"DOMContentLoaded[\s\S]*?_bindStableInputs\(\)",
        )

    def test_js_dynamic_rows_use_data_action(self):
        # The artifact-row <tr> template (reloadData) and job action
        # buttons (reloadJobs) must emit data-action attributes,
        # not inline onclick=.
        self.assertIn('data-action="open-detail"', self.js)
        self.assertIn('data-artifact-id', self.js)
        self.assertIn('data-action="download-job"', self.js)
        self.assertIn('data-action="show-job-error"', self.js)
        self.assertIn('data-job-id', self.js)
        # And the templates must not regress to inline onclick.
        self.assertNotRegex(
            self.js,
            r'<(?:tr|button)[^>]*\sonclick=',
            "no innerHTML template in workspace.js may emit inline onclick",
        )


class ChatPageDelegationTests(unittest.TestCase):
    """PR-C — index.html / chat.js / upload.js route every click via
    ``data-action``; ``oninput`` is split into a separate
    ``data-input-action`` delegate so dynamic upload-row inputs can be
    re-rendered through innerHTML without losing wiring; stable inputs
    (chat textarea, login/forgot/signup modals, mode/model pickers)
    are bound by id at DOMContentLoaded."""

    @classmethod
    def setUpClass(cls):
        cls.html   = (FRONTEND / "index.html").read_text(encoding="utf-8")
        cls.chat   = (STATIC / "chat.js").read_text(encoding="utf-8")
        cls.upload = (STATIC / "upload.js").read_text(encoding="utf-8")

    # ─── HTML — static actions ────────────────────────────────────
    def test_html_uses_data_action_for_header(self):
        for action in (
            "set-source", "toggle-lang", "clear-history",
            "toggle-session-panel", "show-login",
        ):
            with self.subTest(action=action):
                self.assertIn(f'data-action="{action}"', self.html)

    def test_html_uses_data_action_for_sidebar(self):
        for action in (
            "toggle-sidebar", "switch-sidebar-mode",
            "trigger-file-input", "trigger-folder-input",
            "upload-files",
        ):
            with self.subTest(action=action):
                self.assertIn(f'data-action="{action}"', self.html)

    def test_html_uses_data_action_for_chat_actions(self):
        for action in (
            "use-chip", "trigger-model-install", "accept-mode-recommend",
            "copy-conversation", "send-message", "new-session",
        ):
            with self.subTest(action=action):
                self.assertIn(f'data-action="{action}"', self.html)

    def test_html_uses_data_action_for_login_modal(self):
        for action in (
            "toggle-api-key-visibility", "close-login", "do-login",
            "open-forgot-password-modal", "open-signup-modal",
        ):
            with self.subTest(action=action):
                self.assertIn(f'data-action="{action}"', self.html)

    def test_html_drops_javascript_href(self):
        # ``href="javascript:openForgotPasswordModal()"`` and
        # ``href="javascript:openSignupModal()"`` replaced by
        # ``href="#" data-action="open-…-modal"``; click delegate calls
        # preventDefault before invoking the action.
        self.assertNotIn('href="javascript:', self.html)

    # ─── chat.js dynamic templates ────────────────────────────────
    def test_chat_js_dynamic_buttons_use_data_action(self):
        for action in (
            "logout", "approve-wiki-save", "ask-with-force-web",
            "export-answer", "send-feedback", "copy-answer-text",
            "ask-suggestion",
            "switch-session", "rename-session", "delete-session",
        ):
            with self.subTest(action=action):
                self.assertIn(f'data-action="{action}"', self.chat)

    def test_chat_js_export_buttons_carry_format_data(self):
        # The four export buttons share one action and pass the format
        # via ``data-format`` so the delegate only registers one entry.
        for fmt in ("py", "md", "docx", "txt"):
            with self.subTest(format=fmt):
                self.assertRegex(
                    self.chat,
                    r'data-action="export-answer"[^`]*?data-format="' + fmt + r'"',
                )

    def test_chat_js_feedback_buttons_carry_dir_and_signal(self):
        # sendFeedback was called as fn(dirId, signal, btn); migration
        # encodes (dirId, signal) into data attributes so the delegate
        # can rebuild the call.
        for signal in ("explicit_positive", "explicit_negative"):
            with self.subTest(signal=signal):
                self.assertRegex(
                    self.chat,
                    r'data-action="send-feedback"[^`]*?data-signal="' + signal + r'"',
                )
        self.assertIn('data-dir-id="', self.chat,
            "feedback button must carry data-dir-id")

    def test_chat_js_session_rows_carry_sid(self):
        # The three session-panel actions (switch/rename/delete) read
        # the session id from data-sid (HTML-escaped via escHtml) —
        # safer than the prior JS string-injection pattern.
        self.assertRegex(
            self.chat,
            r'data-action="switch-session"\s+data-sid=',
        )
        self.assertRegex(
            self.chat,
            r'data-action="rename-session"\s+data-sid=',
        )
        self.assertRegex(
            self.chat,
            r'data-action="delete-session"\s+data-sid=',
        )

    # ─── upload.js dynamic templates ──────────────────────────────
    def test_upload_js_uses_data_action(self):
        self.assertIn('data-action="chat-attach-click"', self.upload)
        self.assertIn('data-action="remove-or-cancel"', self.upload)
        # And the folder-input per-row oninput moves to a separate
        # input-delegate attribute so the click delegate doesn't see it.
        self.assertIn('data-input-action="update-instruction"', self.upload)

    def test_upload_js_no_inline_handlers(self):
        hits = _INLINE_ATTR_RE.findall(self.upload)
        self.assertEqual(
            hits, [],
            "upload.js innerHTML templates may not emit inline handlers",
        )

    # ─── Delegation infrastructure ────────────────────────────────
    def test_chat_js_installs_click_delegation(self):
        self.assertRegex(
            self.chat,
            r"document\.addEventListener\(\s*['\"]click['\"]",
            "chat.js must install a document-level click delegate",
        )
        self.assertIn("data-action", self.chat)

    def test_chat_js_installs_input_delegation(self):
        # The folder-input oninput in upload.js routes through this
        # separate input delegate so re-rendered rows keep working.
        self.assertRegex(
            self.chat,
            r"document\.addEventListener\(\s*['\"]input['\"]",
            "chat.js must install a document-level input delegate",
        )
        self.assertIn("data-input-action", self.chat)

    def test_chat_js_binds_stable_inputs_on_dom_ready(self):
        self.assertIn("_bindStableInputs", self.chat)
        self.assertRegex(
            self.chat,
            r"DOMContentLoaded[\s\S]{0,80}?_bindStableInputs",
        )

    def test_chat_js_binds_modal_overlay_close(self):
        # The three modal overlay click-outside handlers are bound by
        # id in _bindStableInputs (closeLoginOutside / Forgot / Signup
        # each check e.target === overlay so we forward the event).
        self.assertIn("closeLoginOutside", self.chat)
        self.assertIn("closeForgotPasswordOutside", self.chat)
        self.assertIn("closeSignupOutside", self.chat)


if __name__ == "__main__":
    unittest.main()
