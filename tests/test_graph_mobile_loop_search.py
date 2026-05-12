"""[PR mobile-loop-search, 2026-05-09] Graph viz — three improvements:

User feedback:
> "추론 그래프 웹페이지 관련,,
>  - 폰에서도 좀더 잘보이도록 폰 화면 친화적인 화면 조정
>  - 노드 반짝임과 불빛 이동 애니메이션이 질문이나 다른 노드 선택하기
>    전까지는 계속 될수 있도록 구현
>  - 화면 위쪽에 엔티티 노드 검색 색인창을 열고 닫을수 있게 만들어서,
>    클릭하면 자동으로 이동하는 것 구현"

Three feature blocks:
  1. Mobile responsive — extends @media queries for phone usability
  2. Persistent pulse loop — sprite pulses replay every PULSE_LOOP_MS
     until the next question or node click clears the active set
  3. Top search drawer — collapsible entity search at top edge,
     replaces the side aside on phones (where aside is hidden)

Run:
    python -m unittest tests.test_graph_mobile_loop_search
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS  = ROOT / "frontend" / "static" / "graph.js"
HTML = ROOT / "frontend" / "graph.html"
MOBILE_CSS = ROOT / "frontend" / "static" / "mobile.css"


# ─── Feature 1 — Mobile responsive ───────────────────────────────
class MobileResponsiveTests(unittest.TestCase):
    """@media queries must cover phone (≤768px) and very small (≤480px).

    [mobile-css-extension, 2026-05-12] The graph @media rules used to
    live inline in graph.html at the 720px breakpoint. They moved into
    mobile.css's graph section at the project-standard 768px boundary
    so the four pages share one mobile contract. Tests now read the
    consolidated stylesheet instead of the page."""

    @classmethod
    def setUpClass(cls):
        cls.css = MOBILE_CSS.read_text(encoding="utf-8")

    def test_768_breakpoint_present(self):
        self.assertIn("@media (max-width: 768px)", self.css,
            "tablet+phone breakpoint must exist in mobile.css")

    def test_480_breakpoint_present(self):
        self.assertIn("@media (max-width: 480px)", self.css,
            "tiny-screen breakpoint must adjust further beyond 768px")

    def test_neighbor_panel_responsive(self):
        # Neighbor panel default is left-aligned; on phone it should
        # stretch full-width.
        idx = self.css.index("@media (max-width: 768px)")
        end = self.css.index("@media (max-width: 480px)", idx)
        block = self.css[idx:end]
        self.assertIn(".neighbor-panel", block,
            "neighbor-panel must have phone-specific layout rule")

    # [W2 2026-05-10] query-bar 자체가 graph 페이지에서 제거됐으므로 phone
    # layout 검증도 무관 — 질문 인터페이스는 /chat 페이지에서.

    def test_touch_targets_enlarged(self):
        idx = self.css.index("@media (max-width: 768px)")
        end = self.css.index("@media (max-width: 480px)", idx)
        block = self.css[idx:end]
        # Buttons / clickable rows must be larger for thumb taps.
        # Look for a width/height ≥ 32px or padding ≥ 10px.
        self.assertRegex(block, r"width:\s*32px|min-(?:width|height):\s*[345]\dpx",
            "phone close/toggle buttons must be at least 32px square")


# ─── Feature 2 — Persistent pulse loop ───────────────────────────
class PulseLoopTests(unittest.TestCase):
    """startPulseLoop / stopPulseLoop + integration points."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_loop_state_declared(self):
        self.assertIn("pulseLoopTimer", self.js)
        self.assertIn("pulseLoopEdges", self.js)
        self.assertIn("PULSE_LOOP_MS", self.js)

    def test_start_function_defined(self):
        self.assertIn("function startPulseLoop", self.js)

    def test_stop_function_defined(self):
        self.assertIn("function stopPulseLoop", self.js)

    def test_loop_uses_setInterval(self):
        idx = self.js.index("function startPulseLoop")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("setInterval", body,
            "loop must use setInterval to replay pulses periodically")
        self.assertIn("spawnPulse", body,
            "loop must call spawnPulse on each tick")

    def test_stop_clears_interval(self):
        idx = self.js.index("function stopPulseLoop")
        self.js.index("\n  ", idx + 100)
        body = self.js[idx:idx + 400]
        self.assertIn("clearInterval", body)

    def test_clear_path_stops_loop(self):
        # When the active path is cleared (new question, close panel),
        # the pulse loop must stop too.
        idx = self.js.index("function clearActivePath")
        self.js.index("\n  ", idx + 50)
        body = self.js[idx:idx + 600]
        self.assertIn("stopPulseLoop", body,
            "clearActivePath must also stop the pulse loop so the next "
            "interaction starts from a clean state")

    # [W2 2026-05-10] activatePath 제거 — 질문 답변 path 시각화가 사라졌음.
    # exploreFromNode 가 유일한 path activator → pulse loop 도 거기서만 시작.

    def test_explore_starts_loop(self):
        idx = self.js.index("function exploreFromNode")
        body = self.js[idx:idx + 2500]
        self.assertIn("startPulseLoop", body,
            "exploreFromNode must kick off the pulse loop too "
            "(neighborhood explorer needs the same persistent flow)")


# ─── Feature 3 — Top entity search drawer ────────────────────────
class SearchDrawerHtmlTests(unittest.TestCase):
    """Drawer markup + toggle tab in graph.html."""

    @classmethod
    def setUpClass(cls):
        # [PR-#8b, 2026-05-13] graph.html's inline ``<style>`` was
        # extracted to static/graph.css. ``test_drawer_open_class_styling``
        # checks for the ``.top-search-drawer.tsd-open`` CSS rule,
        # which now lives in the sibling stylesheet — concatenate so
        # the regex still matches.
        css = (ROOT / "frontend" / "static" / "graph.css"
              ).read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8") + "\n" + css

    def test_drawer_div_present(self):
        self.assertIn('id="search-drawer"', self.html)
        self.assertIn('class="top-search-drawer"', self.html)

    def test_toggle_tab_present(self):
        self.assertIn('id="tsd-toggle"', self.html)
        # [§5 migration] inline onclick replaced by data-action +
        # document-level click delegate in graph.js.
        self.assertIn('data-action="toggle-search-drawer"', self.html)

    def test_search_input_present(self):
        self.assertIn('id="tsd-search"', self.html)
        self.assertIn('class="tsd-search"', self.html)

    def test_list_container_present(self):
        self.assertIn('id="tsd-list"', self.html)

    def test_escape_key_closes(self):
        # [§5 migration] ESC-to-close handler moved from inline
        # onkeydown on the input to a document-level keydown delegate
        # in graph.js that routes on (e.target.id, e.key).
        js = (ROOT / "frontend" / "static" / "graph.js").read_text(encoding="utf-8")
        self.assertRegex(
            js,
            r"document\.addEventListener\(\s*['\"]keydown['\"]",
            "graph.js must install a document-level keydown delegate",
        )
        self.assertIn("tsd-search", js,
            "keydown delegate must route ESC on the search input")
        self.assertIn("Escape", js,
            "keydown delegate must recognise the ESC key")

    def test_drawer_open_class_styling(self):
        # CSS rule for .tsd-open must define max-height (slide-in).
        self.assertRegex(
            self.html,
            r"\.top-search-drawer\.tsd-open[^{]*\{[^}]*max-height",
            re.DOTALL,
        )


class SearchDrawerJsTests(unittest.TestCase):
    """toggleSearchDrawer / showSearchDrawer / hideSearchDrawer +
    list rendering + click-to-jump."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_toggle_function_global(self):
        self.assertIn("window.toggleSearchDrawer", self.js,
            "toggle must be window-level for inline onclick")

    def test_hide_function_global(self):
        self.assertIn("window.hideSearchDrawer", self.js)

    def test_render_list_function(self):
        self.assertIn("function _renderSearchList", self.js)

    def test_render_uses_escapehtml(self):
        idx = self.js.index("function _renderSearchList")
        self.js.index("\n  ", idx + 100)
        body = self.js[idx:idx + 2000]
        # Names + types come from the snapshot — XSS-escape both.
        self.assertGreaterEqual(body.count("escapeHtml"), 2,
            "name + type fields must both go through escapeHtml")

    def test_search_row_uses_data_attr_and_listener(self):
        # [PR click-fix, 2026-05-09] earlier versions interpolated
        # JSON.stringify(id) into an inline onclick attribute. JSON's
        # double quotes collided with HTML attribute's double quotes →
        # onclick syntax error → click did nothing. Now we use
        # data-search-id + addEventListener (same pattern as the
        # always-working direct 3D node click).
        idx = self.js.index("function _renderSearchList")
        body = self.js[idx:idx + 2500]
        self.assertIn('data-search-id', body,
            "search row must carry data-search-id, not inline onclick "
            "with interpolated id (HTML-attr quoting bug)")
        self.assertIn("addEventListener('click'", body,
            "click handler must be programmatic — matches direct-3D "
            "click which always worked")
        # Negative regression guard — must not regress to the broken
        # inline-onclick pattern.
        self.assertNotRegex(
            body,
            r"onclick=\"onSearchRowClick\(.*?\+\s*idJs",
            "must not interpolate raw JSON-stringified id into inline "
            "onclick — that's the bug we just fixed",
        )

    def test_click_routes_through_onNodeClick(self):
        # window.onSearchRowClick must call onNodeClick so the
        # exploration animation fires (camera move + neighborhood
        # explorer + pulse loop).
        idx = self.js.index("window.onSearchRowClick")
        body = self.js[idx:idx + 600]
        self.assertIn("onNodeClick", body,
            "search row click must reuse onNodeClick so the same "
            "exploration animation fires")

    def test_empty_query_shows_top_by_degree(self):
        # When the search input is empty, list must show top entities
        # by degree — most useful first.
        idx = self.js.index("function _renderSearchList")
        body = self.js[idx:idx + 1500]
        self.assertIn("degree", body,
            "empty-query path must rank by degree (most-connected first)")

    def test_bootstrap_binds_input(self):
        # The bootstrap function must call _bindSearchDrawerInput so
        # the input's keystrokes update the list.
        idx = self.js.index("function bootstrap")
        body = self.js[idx:idx + 1500]
        self.assertIn("_bindSearchDrawerInput", body)


if __name__ == "__main__":
    unittest.main()
