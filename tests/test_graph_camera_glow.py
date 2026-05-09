"""[PR camera-glow, 2026-05-09] Graph camera centering + soft glow.

User feedback:
> "선택된 노드 연결된 노드 목록 창에서 특정 노드를 클릭하면 선택한
>  노드로 화면이 이동해야한다. 검색창에서 선택한 노드로도 이동하도록
>  개선."
> "선택된 노드와 연결된 선을 따라 이동하는 불빛은 노드와 선 모양을
>  감싸는 형식으로 자연스럽게 반짝이는 방식으로 구현"

Two improvements:

  1. Camera centering — onNodeClick already moved the camera but the
     animation was subtle (distance=240, 700ms). Tightened to
     distance=110 (closer view) + 1200ms (longer animation) so the
     screen-travel-to-node is clearly visible when the click came
     from the search drawer or neighbor panel.

  2. Wrap-around glow — replaces the hard square sprite with a soft
     radial-gradient texture for both:
       (a) traveling pulse sprites (size 14 vs old 8 — softer/larger)
       (b) NEW node halos for active path nodes — sine-pulsing
           Sprite around each lit node, 1.8s breathing period

  Together: the path doesn't just have a moving dot, the active nodes
  themselves "wrap" with a soft glow that breathes.

Run:
    python -m unittest tests.test_graph_camera_glow
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


# ─── Item 1 — Camera centering ──────────────────────────────────
class CameraCenteringTests(unittest.TestCase):
    """onNodeClick must move camera with closer + longer animation."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def _click_body(self) -> str:
        idx = self.js.index("function onNodeClick")
        # Bound at next comment-block divider
        nxt = self.js.index("// ─", idx + 100)
        return self.js[idx:nxt]

    def test_distance_tightened(self):
        body = self._click_body()
        # Old code had `distance = 240`; new code should be closer
        # (≤ 200) so the camera move is visible.
        m = re.search(r"distance\s*=\s*(\d+)", body)
        self.assertIsNotNone(m, "distance literal must be present")
        d = int(m.group(1))
        self.assertLessEqual(d, 200,
            f"camera distance {d} too far — should be ≤200 so move "
            "is visibly impactful when triggered from search/neighbor")
        self.assertGreater(d, 50,
            "but not too close — node should still be in viewable distance")

    def test_animation_duration_longer(self):
        body = self._click_body()
        # cameraPosition(..., node, <duration>) — find the duration arg.
        m = re.search(r"cameraPosition\([\s\S]+?node,\s*(\d+)", body)
        self.assertIsNotNone(m, "cameraPosition with duration arg expected")
        ms = int(m.group(1))
        self.assertGreaterEqual(ms, 1000,
            f"camera animation {ms}ms too short — should be ≥1000ms so "
            "the screen-travel motion is clearly visible")

    def test_explore_still_called_after_camera(self):
        body = self._click_body()
        # The order matters: camera move FIRST (so user sees screen
        # travel), then exploreFromNode (which lights up neighbors).
        cam_idx = body.index("cameraPosition")
        explore_idx = body.index("exploreFromNode")
        self.assertLess(cam_idx, explore_idx,
            "cameraPosition must be called BEFORE exploreFromNode so "
            "the visual order matches user mental model: travel → light up")


# ─── Item 2 — Soft glow texture ─────────────────────────────────
class GlowTextureTests(unittest.TestCase):
    """Radial gradient texture helper."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_get_glow_texture_function(self):
        self.assertIn("function getGlowTexture", self.js)

    def test_hex_to_rgba_helper(self):
        # We need to produce rgba colors with varying alpha for the
        # gradient stops — supporting #abc + #aabbcc shorthand.
        self.assertIn("function _hexToRgba", self.js)

    def test_uses_radial_gradient(self):
        idx = self.js.index("function getGlowTexture")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("createRadialGradient", body,
            "must use createRadialGradient for the soft falloff")
        # Multiple color stops (bright core → soft falloff)
        self.assertGreaterEqual(body.count("addColorStop"), 3,
            "gradient should have ≥3 stops for a smooth falloff curve")

    def test_texture_cached(self):
        # Cache map so we don't re-create the canvas on every spawnPulse.
        self.assertIn("_glowTexCache", self.js)
        idx = self.js.index("function getGlowTexture")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn(".has(", body)
        self.assertIn(".set(", body)


class SpawnPulseUsesGlowTests(unittest.TestCase):
    """spawnPulse must use the glow texture for soft sprites."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_uses_glow_texture(self):
        idx = self.js.index("function spawnPulse")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("getGlowTexture", body,
            "spawnPulse must use the radial gradient texture for the "
            "soft 'comet' look the user described")

    def test_sprite_scale_increased(self):
        # Was 8x8 — bumped to ≥12 for softer "fluid light" look.
        idx = self.js.index("function spawnPulse")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        m = re.search(r"sprite\.scale\.set\((\d+)", body)
        self.assertIsNotNone(m)
        scale = int(m.group(1))
        self.assertGreaterEqual(scale, 12,
            f"sprite scale {scale} too small — should be ≥12 for the "
            "softer/larger wrap-around look")


# ─── Item 2 — Node halos ────────────────────────────────────────
class NodeHaloTests(unittest.TestCase):
    """nodeHalos Map + refresh + per-frame tick."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_node_halos_state(self):
        self.assertRegex(self.js, r"nodeHalos\s*=\s*new Map\(\)",
            "nodeHalos must be a Map (nodeId → Sprite)")

    def test_refresh_function_defined(self):
        self.assertIn("function refreshNodeHalos", self.js)

    def test_tick_function_defined(self):
        self.assertIn("function tickNodeHalos", self.js)

    def test_tick_uses_sine_pulse(self):
        idx = self.js.index("function tickNodeHalos")
        nxt = self.js.index("\n  ", idx + 100)
        body = self.js[idx:idx + 1500]
        self.assertIn("Math.sin", body,
            "halo must pulse via sine for organic breathing feel")
        self.assertIn(".scale.set", body,
            "halo must animate scale (size pulse)")
        self.assertIn(".material.opacity", body,
            "halo must animate opacity (brightness pulse)")

    def test_tick_called_in_pulse_tick(self):
        idx = self.js.index("function pulseTick")
        body = self.js[idx:idx + 2000]
        self.assertIn("tickNodeHalos", body,
            "tickNodeHalos must run every frame from pulseTick")

    def test_refresh_called_from_activate_path(self):
        # When a path activates, halos should appear on the path nodes.
        idx = self.js.index("function activatePath")
        body = self.js[idx:idx + 3500]
        self.assertIn("refreshNodeHalos", body,
            "activatePath must refresh halos to show on path nodes")

    def test_refresh_called_from_explore(self):
        idx = self.js.index("function exploreFromNode")
        body = self.js[idx:idx + 2500]
        self.assertIn("refreshNodeHalos", body,
            "exploreFromNode must refresh halos for center + neighbors")

    def test_refresh_called_from_clear(self):
        # Closing the path must dispose halos so they don't linger.
        idx = self.js.index("function clearActivePath")
        body = self.js[idx:idx + 600]
        self.assertIn("refreshNodeHalos", body,
            "clearActivePath must trigger halo cleanup (dispose)")

    def test_halo_disposed_on_inactive(self):
        # refreshNodeHalos must dispose Sprite + texture on removal
        # to avoid GPU memory leaks across many path switches.
        idx = self.js.index("function refreshNodeHalos")
        nxt = self.js.index("\n  // ", idx + 100)
        body = self.js[idx:nxt]
        self.assertIn("disposeSprite", body,
            "halos for inactive nodes must be disposed (existing helper)")


if __name__ == "__main__":
    unittest.main()
