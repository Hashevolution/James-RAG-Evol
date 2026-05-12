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
    r"|focus|blur|mouseover|mouseout|mouseenter|mouseleave"
    r"|mousedown|mouseup)\s*=",
    re.IGNORECASE,
)

# Pages already migrated to delegation. Each PR adds a name here.
_MIGRATED_PAGES = {
    "graph.html",
    "workspace.html",
}

# Pages still using inline handlers. Will shrink to empty by PR-D.
_LEGACY_INLINE_PAGES = {
    "index.html",
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


if __name__ == "__main__":
    unittest.main()
