"""mobile.css coverage — every full-page UI links the shared responsive
overrides stylesheet, and the chat-only sidebar rules stay scoped so
they don't clobber workspace.html's flow-positioned ``nav.sidebar``.

Background: chat (index.html) + admin.html linked mobile.css from day
one; workspace.html shipped without responsive rules other than its
own inline ``@media (max-width: 700px)`` block (sidebar collapse +
detail-panel full-width). That left mobile touch-target sizing,
iOS font-size auto-zoom prevention, safe-area-inset handling and a
few other generic mobile concerns unaddressed on the workspace page.

graph.html intentionally does NOT link mobile.css — it implements its
own page-specific @media block tuned to graph-canvas concerns (top
search drawer, neighbor panel placement). That choice is preserved.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class MobileCssLinkPresentTests(unittest.TestCase):
    """Pages that depend on shared mobile rules link the stylesheet."""

    def _read(self, name: str) -> str:
        return (ROOT / "frontend" / name).read_text(encoding="utf-8")

    def test_chat_links_mobile_css(self):
        self.assertIn('href="/static/mobile.css"', self._read("index.html"),
            "index.html (chat) must link the shared mobile overrides")

    def test_admin_links_mobile_css(self):
        self.assertIn('href="/static/mobile.css"', self._read("admin.html"),
            "admin.html must link the shared mobile overrides")

    def test_workspace_links_mobile_css(self):
        self.assertIn('href="/static/mobile.css"', self._read("workspace.html"),
            "workspace.html must link mobile.css for touch-target + "
            "iOS font-size + safe-area-inset rules")


class ChatSidebarRuleScopedTests(unittest.TestCase):
    """mobile.css's chat sidebar rules use ``aside.sidebar``, not the
    bare ``.sidebar`` selector — so they don't collide with
    workspace.html's ``<nav class="sidebar">``.

    Why this matters: ``<nav class="sidebar">`` in workspace is a
    flow-positioned 200px rail (56px at ≤700px). If mobile.css matched
    it with the chat selector, workspace's sidebar would become
    ``position: fixed`` at 88vw between 701-768px, breaking the page
    layout entirely.
    """

    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / "frontend" / "static" / "mobile.css"
                   ).read_text(encoding="utf-8")

    def test_bare_dot_sidebar_selector_not_used(self):
        # The chat sidebar rule body has these distinctive properties
        # — position:fixed + 88vw width. Confirm no rule with EXACTLY
        # that body is keyed on the bare ``.sidebar`` selector.
        bad = re.search(
            r'(^|\s)\.sidebar\s*\{[^}]*position:\s*fixed[^}]*88vw',
            self.css, re.DOTALL | re.MULTILINE,
        )
        self.assertIsNone(
            bad,
            "mobile.css chat sidebar rule must be scoped to "
            "``aside.sidebar`` — bare ``.sidebar`` would match "
            "workspace.html's <nav class=\"sidebar\">",
        )

    def test_aside_sidebar_selector_present(self):
        self.assertIn("aside.sidebar", self.css,
            "the scoped chat selector should be present in mobile.css")


if __name__ == "__main__":
    unittest.main()
