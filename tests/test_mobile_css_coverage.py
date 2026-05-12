"""mobile.css coverage — every full-page UI links the shared responsive
overrides stylesheet, and the chat-only sidebar rules stay scoped so
they don't clobber workspace.html's flow-positioned ``nav.sidebar``.

Background: chat (index.html) + admin.html linked mobile.css from day
one; workspace.html shipped without responsive rules other than its
own inline ``@media (max-width: 700px)`` block (sidebar collapse +
detail-panel full-width). That left mobile touch-target sizing,
iOS font-size auto-zoom prevention, safe-area-inset handling and a
few other generic mobile concerns unaddressed on the workspace page.

[mobile-css-extension, 2026-05-12] graph.html now also links mobile.css
and its page-specific @media block (top search drawer, neighbor panel
placement, aside hide) was consolidated into mobile.css's graph
section so the four pages share a single 768px / 480px boundary.
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

    def test_graph_links_mobile_css(self):
        self.assertIn('href="/static/mobile.css"', self._read("graph.html"),
            "graph.html must link mobile.css — its mobile @media block "
            "was consolidated into mobile.css's graph section")

    def test_no_full_page_left_unaccounted(self):
        # All four canonical pages must be in the mobile.css contract.
        # Anything new added under frontend/ trips this guard until it's
        # explicitly addressed.
        expected = {"index.html", "admin.html",
                    "workspace.html", "graph.html"}
        top_level = {
            p.name for p in (ROOT / "frontend").glob("*.html")
            if p.is_file()
        }
        unaccounted = top_level - expected
        self.assertEqual(
            unaccounted, set(),
            "new top-level page(s) in frontend/ are missing from the "
            "mobile.css coverage contract: "
            + ", ".join(sorted(unaccounted)),
        )


class WorkspaceRulesConsolidatedTests(unittest.TestCase):
    """The four workspace mobile rules used to live inline in
    workspace.html at the 700px breakpoint. They now live in
    mobile.css's 768px block, scoped so they can't bleed into the
    chat or admin pages."""

    @classmethod
    def setUpClass(cls):
        cls.css  = (ROOT / "frontend" / "static" / "mobile.css"
                    ).read_text(encoding="utf-8")
        cls.html = (ROOT / "frontend" / "workspace.html"
                    ).read_text(encoding="utf-8")

    def test_workspace_html_drops_inline_media(self):
        # ``@media (`` is the real CSS at-rule (a media query always
        # comes with a parenthesised condition). The looser bare
        # ``@media`` substring matched the word in the
        # ``<link rel="stylesheet" href="mobile.css">`` comment that
        # PR-#8b added — tighten the check so the contract still
        # catches real inline @media rules.
        self.assertNotIn("@media (", self.html,
            "workspace.html must no longer carry an inline @media — "
            "all mobile rules belong in mobile.css now")

    def test_nav_sidebar_collapse_rule_present(self):
        # The 56px narrow rail is what mobile workspace looks like.
        self.assertRegex(
            self.css,
            r"nav\.sidebar\s*\{[^}]*width:\s*56px",
            "the workspace narrow-rail rule must be in mobile.css",
        )

    def test_nav_item_label_collapse_is_scoped(self):
        # Workspace hides nav-item labels on mobile; admin keeps them.
        # The selector must therefore be descended from ``nav.sidebar``
        # so admin's ``.nav-item`` isn't matched.
        self.assertRegex(
            self.css,
            r"nav\.sidebar\s+\.nav-item\s+span:not\(\.nav-icon\)",
            "the label-collapse rule must be scoped via nav.sidebar — "
            "an unscoped ``.nav-item span:not(.nav-icon)`` would hide "
            "admin's sidebar labels too",
        )

    def test_detail_panel_full_width_present(self):
        self.assertRegex(
            self.css,
            r"\.detail-panel\s*\{[^}]*width:\s*100vw",
        )


class GraphRulesConsolidatedTests(unittest.TestCase):
    """The graph page's responsive rules used to live inline in
    graph.html at the 720px / 480px breakpoints. They now live in
    mobile.css's 768px / 480px blocks, with the bare ``aside``
    selector scoped via ``.main > aside`` so chat's ``aside.sidebar``
    full-screen drawer rules don't collide."""

    @classmethod
    def setUpClass(cls):
        cls.css  = (ROOT / "frontend" / "static" / "mobile.css"
                    ).read_text(encoding="utf-8")
        cls.html = (ROOT / "frontend" / "graph.html"
                    ).read_text(encoding="utf-8")

    def test_graph_html_drops_inline_media(self):
        # See workspace counterpart — ``@media (`` matches the real
        # CSS at-rule; the bare word now appears in the link comment
        # PR-#8b added next to ``mobile.css``.
        self.assertNotIn("@media (", self.html,
            "graph.html must no longer carry an inline @media — all "
            "mobile rules belong in mobile.css now")

    def test_aside_hide_is_scoped(self):
        # ``.main > aside`` is the scoping that keeps this rule from
        # hiding chat's <aside class="sidebar"> drawer on mobile.
        self.assertRegex(
            self.css,
            r"\.main\s*>\s*aside\s*\{[^}]*display:\s*none",
            "graph's aside-hide must be scoped to .main > aside so it "
            "doesn't match chat's aside.sidebar",
        )

    def test_neighbor_panel_reposition_present(self):
        self.assertRegex(
            self.css,
            r"\.neighbor-panel\s*\{[^}]*top:\s*56px",
        )

    def test_search_drawer_widens_to_viewport(self):
        self.assertRegex(
            self.css,
            r"\.top-search-drawer\s*\{[^}]*width:\s*calc\(100%\s*-\s*16px\)",
        )

    def test_overlay_hint_hidden_on_phone(self):
        self.assertRegex(
            self.css,
            r"\.overlay\.bl\s*\{[^}]*display:\s*none",
            "the bottom-left hint overlay must be hidden on mobile — "
            "it crowds the canvas",
        )

    def test_narrowest_breakpoint_hides_extra_columns(self):
        # The 480px block hides the type column in the search drawer
        # and the relation column in the neighbor panel.
        block_match = re.search(
            r"@media\s*\(max-width:\s*480px\)\s*\{([\s\S]+?)\n\}\s*$",
            cls_css := self.css,
        )
        # Some files end with one more closing brace; fall back to a
        # forgiving match if the strict one missed.
        if block_match is None:
            block_match = re.search(
                r"@media\s*\(max-width:\s*480px\)\s*\{([\s\S]+?)\}\s*(?:/\*|\Z)",
                cls_css,
            )
        self.assertIsNotNone(block_match,
            "couldn't locate the 480px @media block in mobile.css")
        block = block_match.group(1)
        self.assertIn(".tsd-type", block,
            "narrow-phone block must hide .tsd-type")
        self.assertIn(".np-rel", block,
            "narrow-phone block must hide .np-rel")


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
