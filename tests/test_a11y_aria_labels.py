"""Icon-only / empty buttons carry accessible names.

HANDOVER_WEB_UI.md priority #4 subset 4b. Icon-only buttons
(glyph characters like ✕ / × / ▲ / ◀ / 🗑) and empty buttons whose
text content is set by JS at runtime (the ``data-lang-toggle``
language switcher) must declare ``aria-label`` so screen-readers
have a stable name regardless of current visual state.

These tests guard against regression — once a button is wired with
aria-label, a future refactor cannot silently strip it.
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


def _button_block_around(html: str, marker: str) -> str:
    """Return the <button ...>...</button> block whose attribute or
    inner text contains ``marker``. Used to assert per-button
    attributes without hard-coding line numbers."""
    # Locate all button blocks (DOTALL because multi-line buttons are
    # common in this codebase).
    for m in re.finditer(r'<button\b[^>]*>([\s\S]*?)</button>', html):
        block = m.group(0)
        if marker in block:
            return block
    return ""


class LangToggleButtonsTests(unittest.TestCase):
    """The ``data-lang-toggle`` button exists on all 4 pages. Its
    visible text is JS-populated, so the static HTML body is empty;
    aria-label is therefore the only stable accessible name."""

    def _block(self, page: str) -> str:
        html = (FRONTEND / page).read_text(encoding="utf-8")
        # data-lang-toggle is unique per page
        m = re.search(
            r'<button[^>]*data-lang-toggle[^>]*>[^<]*</button>',
            html, re.DOTALL,
        )
        return m.group(0) if m else ""

    def _check(self, page: str) -> None:
        block = self._block(page)
        self.assertTrue(block, f"{page}: data-lang-toggle button not found")
        self.assertIn("aria-label=", block,
            f"{page}: lang-toggle must declare aria-label "
            "(its visible text is JS-populated and unreliable for AT)")

    def test_index(self):     self._check("index.html")
    def test_admin(self):     self._check("admin.html")
    def test_workspace(self): self._check("workspace.html")
    def test_graph(self):     self._check("graph.html")


class IconOnlyButtonsTests(unittest.TestCase):
    """Specific high-value icon-only buttons that previously lacked
    an accessible name."""

    def setUp(self):
        self.index = (FRONTEND / "index.html"
                     ).read_text(encoding="utf-8")
        self.admin = (FRONTEND / "admin.html"
                     ).read_text(encoding="utf-8")
        self.workspace = (FRONTEND / "workspace.html"
                         ).read_text(encoding="utf-8")

    def _assert_aria_on_button(self, html: str, locator: str,
                               page: str) -> None:
        """Find a button containing ``locator`` and assert it has
        aria-label. ``locator`` should be a unique substring of the
        button block (e.g. an onclick handler name)."""
        block = _button_block_around(html, locator)
        self.assertTrue(block,
            f"{page}: button matching {locator!r} not found")
        self.assertIn("aria-label=", block,
            f"{page}: button {locator!r} must declare aria-label")

    def test_index_session_open_button(self):
        # The 💬 button in the header opens the session panel
        # (id=session-btn).
        self._assert_aria_on_button(
            self.index, 'id="session-btn"', "index.html")

    # NOTE: the dedicated ✕ "close session panel" button was removed
    # in #372 (UI-IA Phase 2 sidebar consolidation) — the chat session
    # list moved into the sidebar `data-mode="sessions"` rail toggle.
    # The toggle re-uses the same `id="session-btn"` open button (now
    # tested in test_index_session_open_button), so an independent
    # close affordance is no longer rendered. Test deleted with intent.

    def test_index_send_button(self):
        # The ▲ submit button on the chat input.
        # [§5 migration] sendMessage() → data-action="send-message".
        self._assert_aria_on_button(
            self.index, 'data-action="send-message"', "index.html")

    def test_index_model_install_button(self):
        # mode-install-btn — empty button shown only when LLM is missing.
        # [§5 migration] triggerModelInstall() → data-action.
        self._assert_aria_on_button(
            self.index, 'data-action="trigger-model-install"', "index.html")

    def test_index_clear_history_button(self):
        # 🗑 button next to lang toggle.
        # [§5 migration] clearHistory() → data-action="clear-history".
        self._assert_aria_on_button(
            self.index, 'data-action="clear-history"', "index.html")

    def test_index_sidebar_open_button(self):
        # ▶ button shown when sidebar is collapsed (id=sidebar-open-btn).
        self._assert_aria_on_button(
            self.index, 'id="sidebar-open-btn"', "index.html")

    def test_index_sidebar_close_button(self):
        # ◀ button inside the upload sidebar header
        # (class="sidebar-toggle").
        self._assert_aria_on_button(
            self.index, 'class="sidebar-toggle"', "index.html")

    def test_admin_nav_toggle_button(self):
        # ☰ hamburger on admin nav.
        # [§5 PR-D] inline onclick="toggleAdminNav()" replaced by
        # data-action="toggle-admin-nav".
        self._assert_aria_on_button(
            self.admin, 'data-action="toggle-admin-nav"', "admin.html")

    def test_admin_entity_detail_close_button(self):
        # × button inside the entity-detail modal header.
        # [§5 PR-D] now identified by data-action.
        self._assert_aria_on_button(
            self.admin, 'data-action="close-entity-detail"', "admin.html")

    def test_admin_session_turns_close_button(self):
        # [§5 PR-D] now identified by data-action.
        self._assert_aria_on_button(
            self.admin, 'data-action="close-session-turns"', "admin.html")

    def test_workspace_detail_close_button(self):
        # [§5 migration] inline onclick="closeDetail()" replaced by
        # data-action="close-detail" — locator follows.
        self._assert_aria_on_button(
            self.workspace, 'data-action="close-detail"', "workspace.html")


if __name__ == "__main__":
    unittest.main()
