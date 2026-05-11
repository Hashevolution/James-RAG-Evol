"""Modal accessibility — HANDOVER_WEB_UI.md priority #4 (subset 4a).

Every modal in the four full-page UIs must:

  1. Declare ``role="dialog"`` + ``aria-modal="true"``.
  2. Reference an ``aria-labelledby`` whose target ID exists in the
     same document (screen-readers announce the modal title).
  3. Live in a page that links ``a11y-modal.js`` — the JS helper
     wires the dialog with Tab focus-trap + Escape close + focus
     restoration to the previously-focused element.

These tests do NOT exercise the JS itself (DOM behaviour). They
verify that the static HTML + asset wiring are in place so a future
refactor cannot silently strip the dialog semantics.
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

# Expected modal IDs per page, hand-curated from the modal inventory
# done while writing the a11y pass. If a new modal is added, add it
# here so the assertion that "every visible modal is dialog-roled"
# stays meaningful.
EXPECTED_MODALS = {
    "index.html": [
        "login-modal",
        "forgot-password-modal",
        "signup-modal",
    ],
    "admin.html": [
        "entity-detail-modal",
        "session-turns-modal",
        "admin-login-modal",
        "signup-modal",
        "forgot-password-modal",
        "api-key-display-modal",
        "reset-token-display-modal",
        "firstrun-wizard-modal",
    ],
    "workspace.html": [
        "login-modal",
    ],
    "graph.html": [
        "login-modal",
    ],
}


class ModalDialogAttributesTests(unittest.TestCase):
    """Every modal carries role/aria-modal/aria-labelledby."""

    def _read(self, name: str) -> str:
        return (FRONTEND / name).read_text(encoding="utf-8")

    def _modal_block(self, html: str, modal_id: str) -> str:
        # Find the opening tag of the modal and return roughly the
        # next 600 chars — enough to cover its attribute list and
        # the title element that aria-labelledby should reference.
        m = re.search(
            r'<div[^>]*\bid="' + re.escape(modal_id) + r'"[^>]*>',
            html,
        )
        if not m:
            return ""
        return html[m.start():m.start() + 600]

    def _check_modal(self, page: str, modal_id: str) -> None:
        html = self._read(page)
        opening = re.search(
            r'<div[^>]*\bid="' + re.escape(modal_id) + r'"[^>]*>',
            html,
        )
        self.assertIsNotNone(opening,
            f"{page}: modal #{modal_id} not found")
        tag = opening.group(0)
        self.assertIn('role="dialog"', tag,
            f"{page}#{modal_id}: missing role=\"dialog\"")
        self.assertIn('aria-modal="true"', tag,
            f"{page}#{modal_id}: missing aria-modal=\"true\"")
        m = re.search(r'aria-labelledby="([^"]+)"', tag)
        self.assertIsNotNone(m,
            f"{page}#{modal_id}: missing aria-labelledby")
        target_id = m.group(1)
        # The target element must exist on the page so screen-readers
        # can resolve the label.
        self.assertIn(
            f'id="{target_id}"', html,
            f"{page}#{modal_id}: aria-labelledby='{target_id}' "
            "has no matching element",
        )

    def test_index_modals(self):
        for mid in EXPECTED_MODALS["index.html"]:
            self._check_modal("index.html", mid)

    def test_admin_modals(self):
        for mid in EXPECTED_MODALS["admin.html"]:
            self._check_modal("admin.html", mid)

    def test_workspace_modals(self):
        for mid in EXPECTED_MODALS["workspace.html"]:
            self._check_modal("workspace.html", mid)

    def test_graph_modals(self):
        for mid in EXPECTED_MODALS["graph.html"]:
            self._check_modal("graph.html", mid)


class A11yModalScriptLinkedTests(unittest.TestCase):
    """Every page that has at least one modal also links the helper."""

    def _read(self, name: str) -> str:
        return (FRONTEND / name).read_text(encoding="utf-8")

    def test_helper_script_file_exists(self):
        path = FRONTEND / "static" / "a11y-modal.js"
        self.assertTrue(path.exists(),
            "frontend/static/a11y-modal.js must exist")
        # Cheap sanity check on the script's contract.
        src = path.read_text(encoding="utf-8")
        self.assertIn("role=\"dialog\"", src,
            "helper must query for role=dialog modals")
        self.assertIn("Escape", src,
            "helper must handle the Escape key")
        self.assertIn("Tab", src,
            "helper must implement Tab focus trap")

    def _has_link(self, page: str) -> bool:
        # Accept either src or href phrasing.
        html = self._read(page)
        return ('src="/static/a11y-modal.js"' in html
                or "src='/static/a11y-modal.js'" in html)

    def test_index_links_helper(self):
        self.assertTrue(self._has_link("index.html"),
            "index.html must link a11y-modal.js")

    def test_admin_links_helper(self):
        self.assertTrue(self._has_link("admin.html"),
            "admin.html must link a11y-modal.js")

    def test_workspace_links_helper(self):
        self.assertTrue(self._has_link("workspace.html"),
            "workspace.html must link a11y-modal.js")

    def test_graph_links_helper(self):
        self.assertTrue(self._has_link("graph.html"),
            "graph.html must link a11y-modal.js")


if __name__ == "__main__":
    unittest.main()
