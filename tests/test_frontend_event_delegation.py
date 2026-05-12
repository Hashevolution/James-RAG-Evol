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
}

# Pages still using inline handlers. Will shrink to empty by PR-D.
_LEGACY_INLINE_PAGES = {
    "index.html",
    "admin.html",
    "workspace.html",
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


if __name__ == "__main__":
    unittest.main()
