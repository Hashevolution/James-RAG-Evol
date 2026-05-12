"""[P2 unified UX, 2026-05-10] Interactive radar + correlation ripple UI.

User feedback (2026-05-10):
> "성향 그래프쪽으로 이동시켜서 사용자가 직관적으로 설정할수 있게끔
>  깔끔하게 설정 장치를 통합 대안 제시해라"
> "성향의 종류를 좀더 다양화하고 여러가지 성향의 상관관계가 서로간의
>  늘어나고 줄어드는 정도를 잘 반영하게끔 사용자가 직관적인 알수 있도록"

P2 source-level contracts (HTML/JS/CSS):

  - admin.html
    - SVG radar (#char-radar) replaces the 300x300 canvas
    - Layout container (.char-layout) + side panel (.char-side)
    - Connection panel (#char-connections) for selected-trait influence
    - Fine-tune sliders block (#trait-sliders) labelled "정밀 조정"
    - Drag hint + legend + reset/save buttons preserved

  - admin.js
    - loadCharacter fetches both /admin/character/ and /admin/character/correlations
    - renderInteractiveRadar — SVG generation with pointer events
    - applyTraitChangeLocally — backend ripple math mirrored client-side
      so the UI predicts what the server will save (no flicker on POST)
    - Korean trait names (label_ko) shown when present
    - escapeHtml on every user-data interpolation
    - data-attr + addEventListener (PR #157 pattern) — never inline onclick
      with raw-id interpolation

  - admin.css (inline in admin.html)
    - SVG vertex / edge classes
    - ripple keyframes (pos green / neg red)
    - touch-action: none on .char-radar (mobile drag doesn't scroll page)

Run:
    python -m unittest tests.test_character_interactive_radar
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "admin.html"
CSS  = ROOT / "frontend" / "static" / "admin.css"
JS = ROOT / "frontend" / "static" / "admin.js"
I18N = ROOT / "frontend" / "static" / "i18n.js"


def _combined_admin() -> str:
    """[v0.2.x #8] admin styles moved out of admin.html into
    admin.css. CSS-contract tests below combine the two so the
    assertions don't care which file holds the rules."""
    return (HTML.read_text(encoding="utf-8")
            + "\n"
            + CSS.read_text(encoding="utf-8"))


# ─── 1. HTML structure ─────────────────────────────────────────────
class HtmlStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_svg_radar_present(self):
        self.assertIn('id="char-radar"', self.html,
            "P2 must replace canvas with SVG #char-radar")
        self.assertIn('class="char-radar"', self.html)

    def test_old_canvas_removed(self):
        self.assertNotIn('id="radar-chart"', self.html,
            "old canvas radar must be replaced — leftover canvas would "
            "render alongside SVG and confuse users")

    def test_layout_two_column(self):
        # .char-layout flex container with .char-radar-wrap + .char-side
        self.assertIn('class="char-layout"', self.html)
        self.assertIn('class="char-radar-wrap"', self.html)
        self.assertIn('class="char-side"', self.html)

    def test_connections_panel_present(self):
        # The "selected trait → influences these others" panel.
        self.assertIn('id="char-connections"', self.html)

    def test_fine_tune_sliders_block_present(self):
        # Sliders are kept as a secondary precise input — must still
        # have the #trait-sliders container that admin.js renders into.
        self.assertIn('id="trait-sliders"', self.html)
        # And labelled differently from before — '정밀 조정' / 'Fine Tune'.
        self.assertIn('char.fine_tune', self.html)

    def test_legend_rows_present(self):
        for key in ("char.legend_pos", "char.legend_neg", "char.legend_pair"):
            self.assertIn(key, self.html,
                f"legend i18n key {key} must be present in HTML")

    def test_buttons_preserved(self):
        # [§5 PR-D] inline onclick="saveCharacter()" / "resetCharacter()"
        # replaced by data-action variants routed through the click
        # delegate.
        self.assertIn('data-action="save-character"', self.html)
        self.assertIn('data-action="reset-character"', self.html)


# ─── 2. CSS — radar visuals + ripple animations ───────────────────
class CssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # CSS rules live in admin.css (extracted from admin.html in
        # the v0.2.x #8 cleanup); HTML still carries the data-attrs
        # the rules key off. Combining the two keeps every existing
        # assertion source-agnostic.
        cls.html = _combined_admin()

    def test_touch_action_none_for_mobile_drag(self):
        # Without touch-action: none, dragging the radar on mobile
        # scrolls the page — same trap as the graph.html drag.
        self.assertRegex(
            self.html, r"\.char-radar[^{]*\{[^}]*touch-action\s*:\s*none",
            re.DOTALL,
        )

    def test_vertex_class_styled(self):
        self.assertIn(".radar-vertex", self.html)
        # Cursor must indicate drag-ability.
        self.assertRegex(
            self.html, r"\.radar-vertex[^{]*\{[^}]*cursor\s*:\s*grab",
            re.DOTALL,
        )

    def test_correlation_edges_color_coded(self):
        # Positive = green, negative = red.
        self.assertRegex(self.html, r"\.corr-edge\.pos[^{]*\{[^}]*stroke\s*:\s*#22c55e", re.DOTALL)
        self.assertRegex(self.html, r"\.corr-edge\.neg[^{]*\{[^}]*stroke\s*:\s*#ef4444", re.DOTALL)

    def test_ripple_keyframes_defined(self):
        self.assertIn("@keyframes char-ripple-pos", self.html)
        self.assertIn("@keyframes char-ripple-neg", self.html)


# ─── 3. JS — load + render contract ───────────────────────────────
class JsLoadRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_loadCharacter_fetches_correlations(self):
        # P2 must call /admin/character/correlations alongside /admin/character/.
        idx = self.js.index("async function loadCharacter")
        body = self.js[idx:idx + 1500]
        self.assertIn("/admin/character/", body)
        self.assertIn("/admin/character/correlations", body,
            "loadCharacter must fetch the correlation graph for "
            "frontend visualization")

    def test_loadCharacter_uses_promise_all(self):
        # Two API calls in parallel — saves a roundtrip on slow links.
        idx = self.js.index("async function loadCharacter")
        body = self.js[idx:idx + 1500]
        self.assertIn("Promise.all", body,
            "loadCharacter must fan-out to /admin/character/ and "
            "/admin/character/correlations in parallel")

    def test_render_function_defined(self):
        self.assertIn("function renderInteractiveRadar", self.js)

    def test_render_uses_svg_polygon_polyline(self):
        # Source check: SVG primitives should be in the renderer.
        idx = self.js.index("function renderInteractiveRadar")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        # We use polygon for grid + polyline-style data area + circle vertices.
        self.assertIn("polygon", body)
        self.assertIn("circle", body,
            "vertex rendering must emit <circle> elements")

    def test_correlations_drawn_as_paths(self):
        # P2 must render the correlation edges (not just sliders).
        idx = self.js.index("function renderInteractiveRadar")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("corr-edge", body,
            "correlation edges must render with the .corr-edge class")
        self.assertIn("_correlations.forEach", body,
            "must iterate over the loaded correlations array")


# ─── 4. JS — drag (pointer events) ────────────────────────────────
class JsDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_pointer_event_handlers_defined(self):
        for fn in ("onVertexPointerDown", "onVertexPointerMove", "onVertexPointerUp"):
            self.assertIn(f"function {fn}", self.js,
                f"P2 must define {fn} for SVG drag")

    def test_pointer_capture_used(self):
        # setPointerCapture is what makes the drag continue even when
        # the pointer leaves the vertex circle.
        self.assertIn("setPointerCapture", self.js,
            "drag must use setPointerCapture so the drag continues "
            "outside the vertex's hit area")

    def test_uses_data_attr_pattern_for_vertex_id(self):
        # PR #157 pattern: data-trait-id + addEventListener, not inline
        # onclick with raw-id interpolation.
        idx = self.js.index("function renderInteractiveRadar")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("data-trait-id", body,
            "vertices must carry data-trait-id (PR #157 pattern)")
        self.assertNotRegex(
            body, r"onclick=\"[^\"]*'\s*\+\s*tr",
            "must not interpolate raw trait id into inline onclick — "
            "that's the bug we fixed in PR #157",
        )

    def test_vertex_pointerdown_wired_via_addEventListener(self):
        idx = self.js.index("function renderInteractiveRadar")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("addEventListener('pointerdown'", body,
            "pointer events must be wired via addEventListener — "
            "consistent with the rest of the codebase's safe pattern")

    def test_screen_to_viewbox_transform(self):
        # SVG viewBox is 600x600 but rendered at any pixel size — drag
        # math must convert screen coords through getScreenCTM().
        self.assertIn("getScreenCTM", self.js,
            "drag must convert screen pixels to viewBox coordinates "
            "via getScreenCTM().inverse() — otherwise the drag math is "
            "wrong on resized viewports")


# ─── 5. JS — local ripple mirrors backend ─────────────────────────
class JsLocalRippleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_apply_change_function_defined(self):
        self.assertIn("function applyTraitChangeLocally", self.js)

    def test_applies_opponent_flip(self):
        idx = self.js.index("function applyTraitChangeLocally")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        # Group A~D opponent must flip to (1 - newValue) — same as backend.
        self.assertIn("_OPPONENTS", body)
        self.assertRegex(
            body, r"\(\s*1\s*-\s*newValue\s*\)",
            msg="opponent value must be (1 - newValue) — matches backend "
                "_OPPONENTS flip",
        )

    def test_applies_correlation_ripple(self):
        idx = self.js.index("function applyTraitChangeLocally")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        # Same formula as backend: delta * weight * damping.
        self.assertIn("_correlations.forEach", body)
        self.assertIn("_ripple_damping", body,
            "client ripple must use the damping factor returned by the "
            "backend so the visual matches the saved value")
        self.assertRegex(
            body, r"delta\s*\*\s*corr\.weight\s*\*\s*_ripple_damping",
            msg="ripple formula must mirror backend: delta × weight × damping",
        )

    def test_skip_set_prevents_double_write(self):
        idx = self.js.index("function applyTraitChangeLocally")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("skip", body,
            "must skip the source + opponent when iterating ripples — "
            "otherwise the opponent flip is double-written by a "
            "correlation edge")

    def test_animateRippleFor_function(self):
        self.assertIn("function animateRippleFor", self.js)

    def test_ripple_animation_chooses_pos_or_neg(self):
        idx = self.js.index("function animateRippleFor")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("ripple-pos", body)
        self.assertIn("ripple-neg", body)
        # Must force reflow before re-adding class — otherwise repeated
        # ripples on the same vertex never re-trigger CSS animation.
        self.assertIn("getBoundingClientRect", body,
            "must force reflow (e.g. getBoundingClientRect) so the CSS "
            "animation re-fires when ripple lands on the same vertex")


# ─── 6. JS — sliders use safe pattern + bidirectional sync ─────────
class JsSliderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_renderTraitSliders_uses_data_attr(self):
        idx = self.js.index("function renderTraitSliders")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("data-slider-id", body,
            "P2 sliders must use data-slider-id, not inline oninput "
            "with interpolated id (PR #157 pattern)")
        self.assertNotIn("oninput=\"onTraitChange", body,
            "old inline oninput pattern must be removed")

    def test_renderTraitSliders_groups_F(self):
        # P1 added Group F — slider header must support it.
        idx = self.js.index("function renderTraitSliders")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("char.group_f", body,
            "renderTraitSliders must label Group F (P1 new traits)")

    def test_uses_label_ko_when_present(self):
        # Korean labels have priority — fallback to English label.
        idx = self.js.index("function renderTraitSliders")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("label_ko", body,
            "must show Korean labels when available (this is a "
            "Korean-first product per CLAUDE.md)")

    def test_resetCharacter_includes_new_traits(self):
        idx = self.js.index("function resetCharacter")
        self.js.index("\n", idx + 1)
        # Reset block has all defaults inline; expand to the closing brace.
        end = self.js.index("\n}", idx)
        body = self.js[idx:end]
        for tid in ("conciseness", "directness", "optimism",
                    "risk_tolerance", "patience"):
            self.assertIn(tid, body,
                f"resetCharacter must include default for new trait {tid!r}")

    def test_sync_function_defined(self):
        # syncSlidersToTraits keeps slider DOM in sync after radar drag.
        self.assertIn("function syncSlidersToTraits", self.js)


# ─── 7. JS — XSS escape on all interpolation ──────────────────────
class JsXssEscapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_render_radar_escapes_labels(self):
        idx = self.js.index("function renderInteractiveRadar")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        # Trait labels + icons go to innerHTML — escape them.
        self.assertGreaterEqual(body.count("escapeHtml"), 3,
            "renderInteractiveRadar must escape trait id, icon, and "
            "label text (multiple interpolation sites)")

    def test_connections_panel_escapes(self):
        idx = self.js.index("function renderConnectionsPanel")
        nxt = self.js.index("\nfunction ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("escapeHtml", body,
            "connection rows interpolate trait names — must escape")


# ─── 8. i18n — both locales have the new keys ─────────────────────
class I18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.i18n = I18N.read_text(encoding="utf-8")

    def test_both_locales_have_new_keys(self):
        new_keys = [
            "char.intro", "char.drag_hint", "char.legend",
            "char.legend_pos", "char.legend_neg", "char.legend_pair",
            "char.connections", "char.connections_empty",
            "char.fine_tune", "char.note_pair", "char.note_corr",
            "char.save_ok", "char.save_warn",
            "char.group_a", "char.group_b", "char.group_c",
            "char.group_d", "char.group_e", "char.group_f",
        ]
        for key in new_keys:
            occurrences = self.i18n.count(f"'{key}'")
            self.assertGreaterEqual(occurrences, 2,
                f"i18n key {key!r} must be defined in both EN and KO locales "
                f"(found {occurrences} occurrences)")


if __name__ == "__main__":
    unittest.main()
