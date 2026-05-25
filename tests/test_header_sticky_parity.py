"""v0.4 Sprint 2 #4 — sticky top navigation bar contract.

JAMES has four page surfaces, each with its own ``<header>`` element
+ CSS file. The Sprint 2 #4 spec asked for the header to "persist
across scroll on every page". The right answer differs per page:

  • chat (chat.css) + graph (graph.css)
      body is overflow:hidden + flex column; the page itself never
      scrolls — only inner panels do. ``flex-shrink: 0`` is what
      pins the header at the top; ``position: sticky`` would be a
      no-op (and would conflict with the no-scroll layout).

  • admin (admin.css) + workspace (workspace.css)
      body is min-height:100dvh + flex column; the document DOES
      scroll when content overflows (long admin tables, workspace
      data lists). For those, ``position: sticky; top: 0`` is the
      right primitive — the header stays in view as the user
      scrolls long content.

This test pins the per-page policy so a refactor that homogenises
the headers (e.g. adding ``position: sticky`` to chat.css) doesn't
silently break the no-scroll layout, and dropping sticky from
admin/workspace doesn't silently restore the disappearing-header
bug Sprint 2 #4 fixed.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "frontend" / "static"


def _header_block(css_source: str) -> str:
    """Return the first ``header { … }`` rule body. Looks for the
    bare ``header`` selector (not ``.header`` or ``#header``) to
    avoid catching utility classes."""
    m = re.search(r"(?:^|\s)header\s*\{([^}]+)\}", css_source, re.MULTILINE)
    if not m:
        return ""
    return m.group(1)


class HeaderStickyParityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.styles = {
            name: (STATIC / f"{name}.css").read_text(encoding="utf-8")
            for name in ("admin", "workspace", "chat", "graph")
        }

    def test_admin_header_is_sticky(self):
        block = _header_block(self.styles["admin"])
        self.assertIn("position:", block,
            "admin.css header block should declare position. "
            "Sprint 2 #4 added position: sticky here.")
        self.assertTrue(
            re.search(r"position:\s*sticky", block),
            "admin.css header must be position: sticky (long admin "
            "tables scroll the document; the header must stay).")
        self.assertTrue(
            re.search(r"top:\s*0", block),
            "Sticky needs top:0 to anchor the header to the viewport.")

    def test_workspace_header_is_sticky(self):
        block = _header_block(self.styles["workspace"])
        self.assertTrue(
            re.search(r"position:\s*sticky", block),
            "workspace.css header must be position: sticky to match "
            "admin behaviour — same body layout (min-height + scroll).")
        self.assertTrue(
            re.search(r"top:\s*0", block),
            "Sticky needs top:0 to anchor the header to the viewport.")

    def test_chat_header_is_not_sticky(self):
        """chat.css is intentionally a no-sticky viewport app — body
        is overflow:hidden and the header is pinned via flex-shrink.
        Adding position:sticky here would be redundant at best and
        could interact badly with the inner-flex layout."""
        block = _header_block(self.styles["chat"])
        self.assertNotIn("position: sticky", block,
            "chat.css header should NOT be position:sticky — the "
            "page is overflow:hidden so the document never scrolls "
            "(only inner panels do). flex-shrink: 0 already pins "
            "the header at the top.")
        self.assertTrue(
            re.search(r"flex-shrink:\s*0", block),
            "chat.css header relies on flex-shrink: 0 instead.")

    def test_graph_header_is_not_sticky(self):
        block = _header_block(self.styles["graph"])
        self.assertNotIn("position: sticky", block,
            "graph.css header should NOT be position:sticky — same "
            "rationale as chat.css (overflow:hidden viewport app).")
        self.assertTrue(
            re.search(r"flex-shrink:\s*0", block),
            "graph.css header relies on flex-shrink: 0 instead.")


if __name__ == "__main__":
    unittest.main()
