"""Graph path toggle (item #5-B, 2026-05-08).

User feedback: "그래프 path는 기본적으로 표시 안되나, 사용자가
원할경우 보이는 방식".

Pre-PR every james message rendered all `graph_paths` (often 10-50
entries) as static text under the answer. This created visual noise
on every retrieval answer and pushed feedback buttons + next-action
suggestions out of view on mobile.

Now wrapped in <details> with summary "🕸️ 그래프 경로 N개 보기".
Native HTML element — keyboard / screen-reader accessible, no JS
state to manage. Default closed; click to expand.

Source-level contracts (no JS test runner — assertions scan chat.js):
  - <details> element used (not raw div)
  - <summary> with toggle text including "그래프 경로" and the count
  - Default closed (no `open` attribute on details)
  - graph-paths div still rendered inside the details (so existing
    .graph-paths CSS still styles it)

Run:
  python -m unittest tests.test_graph_path_toggle
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JS = Path(__file__).resolve().parent.parent / "frontend" / "static" / "chat.js"


class GraphPathToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_details_element_used(self):
        # Must be <details> — native disclosure widget. No raw <div>
        # with manual show/hide (more fragile, less accessible).
        self.assertIn("<details", self.js,
                      "graph paths must be wrapped in <details>")
        self.assertIn("<summary", self.js,
                      "<summary> child required for the toggle label")

    def test_summary_label_includes_count_and_emoji(self):
        # User-visible affordance: the toggle should clearly say what
        # it reveals + how many paths there are.
        # Look for the literal Korean label.
        self.assertIn("그래프 경로", self.js,
                      "summary label must include '그래프 경로'")
        # Count interpolation present.
        self.assertIn("${paths.length}", self.js,
                      "summary must show paths.length so user knows the size "
                      "before deciding to expand")

    def test_default_closed_no_open_attr(self):
        # `<details open>` would defeat the purpose — default must
        # be closed. Find the opening details tag.
        m = re.search(r"<details[^>]*?>", self.js)
        self.assertIsNotNone(m, "details tag missing")
        self.assertNotIn(" open", m.group(),
                         "details must NOT have `open` attr — default closed")

    def test_existing_graph_paths_class_preserved(self):
        # Existing CSS .graph-paths styles continue to apply once
        # expanded — must keep the same classname inside <details>.
        self.assertIn('class="graph-paths"', self.js)

    def test_pathsHtml_uses_paths_length_branch(self):
        # The rendering is gated on paths.length > 0 — empty paths
        # arrays should not render the toggle either.
        # Find the paths render block.
        idx = self.js.index("let pathsHtml")
        body = self.js[idx:idx + 1500]
        self.assertIn("paths.length > 0", body,
                      "must guard rendering on non-empty paths array")


class GraphPathChipRenderTests(unittest.TestCase):
    """HANDOVER §3 follow-up — each graph path renders as mint-
    outlined node chips with muted arrow separators instead of a
    plain text run. Existing `<details>` toggle wrapper is
    preserved (see GraphPathToggleTests above)."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        cls.index_html = (Path(__file__).resolve().parent.parent
                          / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_render_helper_splits_on_arrow(self):
        # A renderer helper must split each path string on the
        # arrow glyph and render the segments individually — not
        # just dump the raw `→ A → B → C` text into a div.
        self.assertIn("renderPathRow", self.js,
            "expected a `renderPathRow` helper that turns a path "
            "string into chip markup")
        # The split character must be the actual arrow glyph.
        m = re.search(r"renderPathRow\s*=.*?\}", self.js, re.DOTALL)
        self.assertIsNotNone(m, "renderPathRow body must be findable")
        body = m.group(0)
        self.assertIn("split('→')", body,
            "renderPathRow must split path strings on the '→' glyph")
        # Each node wrapped in .path-node, separators in .path-arrow.
        self.assertIn('class="path-node"', body,
            "each split segment must be wrapped in <span class=\"path-node\">")
        self.assertIn('class="path-arrow"', body,
            "arrow separators must be wrapped in <span class=\"path-arrow\">")
        # Empty / malformed splits must fall back gracefully —
        # the helper checks `nodes.length === 0` and returns ''
        # so a bogus path doesn't render an empty `.path-row`.
        self.assertIn("nodes.length === 0", body,
            "renderPathRow must guard against empty splits")

    def test_chip_css_in_index_html(self):
        # `.path-node` chips must be styled with the mint accent
        # palette so they read as Graph-RAG citations, not generic
        # text. Look inside the `.graph-paths .path-node` rule.
        m = re.search(
            r"\.graph-paths\s+\.path-node\s*\{([^}]+)\}",
            self.index_html,
        )
        self.assertIsNotNone(m,
            "index.html must declare `.graph-paths .path-node` chip styling")
        block = m.group(1)
        self.assertIn("rgba(107,231,208", block,
            "chip must use the mint-cyan accent rgba family")
        self.assertIn("border", block)
        self.assertIn("border-radius", block,
            "chip must have rounded corners")

    def test_arrow_separator_styled_muted(self):
        # The arrow separators sit between chips and should be
        # visually quieter so the chips are the foreground reading.
        m = re.search(
            r"\.graph-paths\s+\.path-arrow\s*\{([^}]+)\}",
            self.index_html,
        )
        self.assertIsNotNone(m,
            "index.html must declare `.graph-paths .path-arrow` separator styling")
        block = m.group(1)
        self.assertIn("var(--muted)", block,
            "arrow separator should use --muted so chips read as the "
            "foreground content")


if __name__ == "__main__":
    unittest.main()
