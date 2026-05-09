"""[PR explorer, 2026-05-09] Graph node-click neighborhood explorer +
query reasoning overlay.

User feedback (2026-05-09):
> "추론 그래프에서 한개의 엔티티를 클릭하면 이름이 뜨는 동시에 그 스팟이
>  불이 들어오고, 직접 연결된 선과 연결된 엔티티 스팟들로 불빛이 이동하면서
>  흐르는 애니메이션 구현. 그리고 그 스팟들의 이름이 옆에 자연스럽게 목록
>  창으로 뜨고, 그 목록의 스팟 이름을 클릭하면 그 스팟으로 이동하며 다시
>  같은 방식의 로직 구현"
>
> "질문시에 답변을 추론하는 동안 대화챗에서와 같이 추론 애니메이션이 뜨도록
>  하고 엔티티 스팟과 graph path 경로 반짝이게"

Two features in one PR (graph.js + graph.html):

  Feature A — Neighborhood explorer
    onNodeClick now triggers exploreFromNode which:
      1. computes direct neighbors via getNeighbors(node)
      2. lights up center + neighbors via activePathNodes/Edges
         (uses #4-2 path persistence machinery — same Set semantics)
      3. fires staggered sprite pulses outward
      4. opens a side panel with neighbor names + relation labels;
         clicking a name → recursive explore from that neighbor

  Feature B — Query reasoning overlay
    showReasoningOverlay/hideReasoningOverlay called from askQuestion's
    try/finally. Renders an inline brain-pulse widget above the query
    bar with a shimmer "JAMES 추론 중" text. Path sparkle on /query/
    completion was already wired (PR #143 #4-2 activatePath).

Run:
    python -m unittest tests.test_graph_explorer
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


# ─── Feature A — neighborhood explorer ───────────────────────────
class GetNeighborsTests(unittest.TestCase):
    """getNeighbors must walk data.links and return both incoming +
    outgoing edges' counterparts."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_function_defined(self):
        self.assertIn("function getNeighbors", self.js)

    def test_walks_both_directions(self):
        idx = self.js.index("function getNeighbors")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        # Outgoing edge: source==nodeId case
        self.assertIn("sId === nodeId", body)
        # Incoming edge: target==nodeId case
        self.assertIn("tId === nodeId", body)

    def test_dedupes_neighbors(self):
        # An entity can be both source and target of separate edges to
        # the same other entity; we want it listed once.
        idx = self.js.index("function getNeighbors")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("seenIds", body,
            "duplicates must be filtered via seenIds set")


class ExploreFromNodeTests(unittest.TestCase):
    """exploreFromNode wires up activation + pulse + panel."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_function_defined(self):
        self.assertIn("function exploreFromNode", self.js)

    def test_resets_prior_path(self):
        idx = self.js.index("function exploreFromNode")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("clearActivePath", body,
            "must clear prior path lighting when starting new exploration")

    def test_activates_neighbor_set(self):
        idx = self.js.index("function exploreFromNode")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("activePathNodes.add", body)
        self.assertIn("activePathEdges.add", body)
        self.assertIn("refreshLabels", body)

    def test_spawns_pulses_staggered(self):
        idx = self.js.index("function exploreFromNode")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("spawnPulse", body,
            "must call spawnPulse for visual flow")
        self.assertIn("setTimeout", body,
            "pulses must be staggered (setTimeout) so the eye can follow")

    def test_renders_panel(self):
        idx = self.js.index("function exploreFromNode")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("renderNeighborPanel", body)


class NeighborPanelTests(unittest.TestCase):
    """renderNeighborPanel must produce safe HTML + clickable rows."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8")

    def test_panel_div_in_html(self):
        self.assertIn('id="neighbor-panel"', self.html)
        self.assertIn('class="neighbor-panel"', self.html)

    def test_panel_styled(self):
        # Sliding-from-left posture so it doesn't clash with answer-card.
        self.assertIn(".neighbor-panel", self.html)
        self.assertRegex(self.html, r"\.neighbor-panel[^{]*\{[^}]*left:", re.DOTALL)

    def test_render_function_uses_escapehtml(self):
        idx = self.js.index("function renderNeighborPanel")
        nxt = self.js.index("\n  ", idx + 100)   # bound at next top-level
        # Find a stable end: the closing of the function
        end = self.js.index("\n  window.onNeighborClick", idx)
        body = self.js[idx:end]
        # Names + relation labels come from the snapshot — escape them.
        self.assertGreaterEqual(body.count("escapeHtml"), 2,
            "renderNeighborPanel must escape both name and relation")

    def test_neighbor_click_handler_global(self):
        # Inline onclick="onNeighborClick(...)" needs window-level export.
        self.assertIn("window.onNeighborClick", self.js)

    def test_close_panel_handler_global(self):
        self.assertIn("window.closeNeighborPanel", self.js)

    def test_neighbor_click_uses_json_stringify(self):
        # The id is interpolated into an inline onclick string. Even if
        # the system-generated id format is safe, defense-in-depth is
        # JSON.stringify (quoting + escaping).
        idx = self.js.index("function renderNeighborPanel")
        nxt = self.js.index("\n  window.", idx + 100)
        body = self.js[idx:nxt]
        self.assertIn("JSON.stringify", body,
            "id interpolation into inline onclick must use JSON.stringify "
            "for defense-in-depth")


class OnNodeClickIntegrationTests(unittest.TestCase):
    """onNodeClick must call exploreFromNode after camera nudge."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_onNodeClick_calls_explore(self):
        idx = self.js.index("function onNodeClick")
        # Find the closing brace of onNodeClick
        nxt = self.js.index("\n  //", idx + 100)   # next top-level comment
        body = self.js[idx:nxt]
        self.assertIn("exploreFromNode(node)", body,
            "onNodeClick must trigger neighborhood exploration")


# ─── Feature B — query reasoning overlay ─────────────────────────
class ReasoningOverlayTests(unittest.TestCase):
    """showReasoningOverlay/hideReasoningOverlay + askQuestion wiring."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8")

    def test_overlay_div_in_html(self):
        self.assertIn('id="query-reasoning-overlay"', self.html)
        self.assertIn('class="query-reasoning-overlay"', self.html)

    def test_overlay_initially_hidden(self):
        # CSS rule must default display:none — JS toggles it.
        self.assertRegex(
            self.html,
            r"\.query-reasoning-overlay[^{]*\{[^}]*display:\s*none",
            re.DOTALL,
        )

    def test_show_function_defined(self):
        self.assertIn("function showReasoningOverlay", self.js)

    def test_hide_function_defined(self):
        self.assertIn("function hideReasoningOverlay", self.js)

    def test_overlay_renders_brain_svg(self):
        idx = self.js.index("function showReasoningOverlay")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        # Brain SVG (path + neurons) — same vibe as chat page brainPulseSvg
        self.assertIn("svg viewBox", body)
        self.assertIn("qr-neuron", body,
            "overlay must contain pulsing neuron circles for the 'thinking' vibe")

    def test_overlay_renders_text_label(self):
        idx = self.js.index("function showReasoningOverlay")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("JAMES 추론 중", body,
            "overlay must show a 'thinking' text label so the user "
            "knows the system is working, not stuck")

    def test_askQuestion_calls_show(self):
        idx = self.js.index("window.askQuestion")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("showReasoningOverlay()", body,
            "askQuestion must show overlay before /query/ POST")

    def test_askQuestion_hides_in_finally(self):
        idx = self.js.index("window.askQuestion")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        # finally block ensures hide even on error path
        self.assertRegex(body, r"finally\s*\{[\s\S]+?hideReasoningOverlay",
            "askQuestion's finally block must hide overlay so it never "
            "stays stuck on error paths")


class CssAnimationTests(unittest.TestCase):
    """The neuron blink + shimmer animations should be defined in CSS."""

    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_neuron_blink_keyframes(self):
        self.assertIn("@keyframes qr-blink", self.html)

    def test_shimmer_keyframes(self):
        self.assertIn("@keyframes qr-shimmer", self.html)

    def test_neurons_have_staggered_delay(self):
        # n2 + n3 should have animation-delay so the three neurons don't
        # blink in unison (matches chat page brain SVG behavior).
        self.assertRegex(
            self.html,
            r"\.qr-neuron\.qr-n2[^{]*\{[^}]*animation-delay",
            re.DOTALL,
        )
        self.assertRegex(
            self.html,
            r"\.qr-neuron\.qr-n3[^{]*\{[^}]*animation-delay",
            re.DOTALL,
        )


if __name__ == "__main__":
    unittest.main()
