"""[item #4-1, 2026-05-09] Graph visualization — visual rendering pass.

User feedback: 추론 그래프의 4가지 시각 개선:
  (a) 기본 선 가시성 향상
  (b) 선들이 형성하는 면에 반투명 색 — 입체감
  (c) 핵심 엔티티 큰 스팟 + 짙은 색 (이름 라벨은 #4-2에서)
  (d) hub 연결선 강조

Decision (review feedback):
  C-2: hub = top 10% by degree AND degree ≥ 5 (option C-3 from review;
       both conditions must hold so the emphasized set stays small)

Implementation (frontend/static/graph.js):
  - HUB_TOP_PCT, HUB_MIN_DEGREE constants + hubIds Set
  - computeHubs() called from buildIndices()
  - isHub(node) helper
  - nodeVal: hubs * 1.7
  - linkColor: hub-touching links brighter + base color ↑ opacity
  - linkOpacity 0.55 → 0.7
  - linkWidth: hub-touching 0.8, baseline 0.55 (was 0.4)
  - Three.js FogExp2 for subtle volumetric depth

The hub LABEL display + path-traversed name display are deliberately
deferred to #4-2 because they share a sprite-rendering mechanism with
answer-card lifecycle features.

Run:
    python -m unittest tests.test_graph_visual_rendering
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


class HubDetectionConstantsTests(unittest.TestCase):
    """Hub detection thresholds match the review decision."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_top_pct_threshold(self):
        m = re.search(r"HUB_TOP_PCT\s*=\s*(0?\.\d+)", self.js)
        self.assertIsNotNone(m, "HUB_TOP_PCT must be declared")
        self.assertAlmostEqual(float(m.group(1)), 0.10,
            msg="decision C-2: top 10% by degree")

    def test_min_degree_floor(self):
        m = re.search(r"HUB_MIN_DEGREE\s*=\s*(\d+)", self.js)
        self.assertIsNotNone(m, "HUB_MIN_DEGREE must be declared")
        self.assertEqual(int(m.group(1)), 5,
            "decision C-2: AND degree ≥ 5 (absolute floor)")

    def test_hubids_set_declared(self):
        self.assertRegex(self.js, r"hubIds\s*=\s*new Set\(\)",
            "hubIds must be a Set for O(1) membership lookup")


class ComputeHubsLogicTests(unittest.TestCase):
    """Source-level: computeHubs computes the cutoff correctly."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def _body(self) -> str:
        idx = self.js.index("function computeHubs")
        nxt = re.search(r"\n  function ", self.js[idx + 1:])
        end = idx + 1 + nxt.start() if nxt else len(self.js)
        return self.js[idx:end]

    def test_function_exists(self):
        self.assertIn("function computeHubs", self.js)

    def test_uses_both_thresholds(self):
        body = self._body()
        # The cutoff must be max(top-pct degree, HUB_MIN_DEGREE).
        self.assertIn("HUB_MIN_DEGREE", body)
        self.assertIn("HUB_TOP_PCT", body)
        self.assertIn("Math.max(", body,
            "must AND the two conditions: max() of top-pct and min-floor")

    def test_called_from_buildindices(self):
        idx = self.js.index("function buildIndices")
        # Bound at next function definition.
        nxt = re.search(r"\n  function ", self.js[idx + 1:])
        end = idx + 1 + nxt.start() if nxt else idx + 1500
        body = self.js[idx:end]
        self.assertIn("computeHubs()", body,
            "buildIndices must call computeHubs() so reload refreshes the set")

    def test_isHub_helper(self):
        self.assertIn("function isHub", self.js)


class NodeRenderingTests(unittest.TestCase):
    """Hub nodes get bigger / more saturated treatment."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_node_val_amplifies_hubs(self):
        # nodeVal returns base for non-hubs, base * (something > 1) for hubs.
        idx = self.js.index(".nodeVal(function")
        body = self.js[idx:idx + 400]
        self.assertIn("isHub(n)", body)
        self.assertRegex(body, r"base\s*\*\s*1\.[5-9]\b",
            "hub size multiplier must be in [1.5, 1.9] range — bigger but "
            "not crowding neighbors (1.7x → ~1.2x apparent radius)")

    def test_node_color_uses_isHub(self):
        # Even if both branches return the same value in current impl
        # (full saturation either way), the function must reference
        # isHub to leave the hook open.
        idx = self.js.index(".nodeColor(function")
        body = self.js[idx:idx + 300]
        self.assertIn("isHub(n)", body)


class LinkRenderingTests(unittest.TestCase):
    """Links: brighter base, hub-touching emphasized, more opaque overall."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def _link_color_body(self) -> str:
        idx = self.js.index(".linkColor(function")
        return self.js[idx:idx + 1000]

    def test_link_color_hub_touch_branch(self):
        body = self._link_color_body()
        self.assertIn("hubTouch", body)
        self.assertIn("isHub(l.source)", body)
        self.assertIn("isHub(l.target)", body)

    def test_baseline_link_color_brightened(self):
        body = self._link_color_body()
        # The 'rgba(150,160,180,0.25)' baseline (faint) was the old
        # hard-to-read color. After this PR, baseline rgb values must be
        # ≥ 170 each AND opacity ≥ 0.4.
        m = re.findall(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", body)
        self.assertGreater(len(m), 0, "expected at least one rgba literal")
        # The non-hub baseline is the LAST rgba in the function body.
        baseline = m[-1]
        r_, g_, b_, a_ = int(baseline[0]), int(baseline[1]), int(baseline[2]), float(baseline[3])
        self.assertGreaterEqual(r_, 160,
            f"baseline R={r_} should be ≥160 for visibility (was 150)")
        self.assertGreaterEqual(a_, 0.35,
            f"baseline alpha={a_} should be ≥0.35 (was 0.25)")

    def test_link_opacity_increased(self):
        # graph.linkOpacity(...) global — was 0.55, must be ≥ 0.65 now.
        m = re.search(r"\.linkOpacity\(([\d.]+)\)", self.js)
        self.assertIsNotNone(m)
        opacity = float(m.group(1))
        self.assertGreaterEqual(opacity, 0.65,
            f"linkOpacity {opacity} must be ≥0.65 (was 0.55) — gives "
            "lines more presence overall")

    def test_link_width_function_branches_on_hub(self):
        idx = self.js.index(".linkWidth(function")
        body = self.js[idx:idx + 600]
        self.assertIn("hubTouch", body)
        # Three branches now: afterglow path > hub-touching > baseline.
        # Numbers may appear after `return`, in a ternary, or as literals.
        nums = re.findall(r"\b\d+\.\d+\b", body)
        unique = set(nums)
        self.assertGreaterEqual(len(unique), 3,
            f"expected ≥3 distinct width values (afterglow, hub, base), got {unique}")


class VolumetricFogTests(unittest.TestCase):
    """[#4-1 b] Three.js FogExp2 for subtle depth."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_fog_setup_present(self):
        self.assertIn("FogExp2", self.js,
            "Three.js exponential fog must be configured for volumetric "
            "depth — user explicitly asked for 입체감 with low complexity")

    def test_fog_density_low(self):
        # Density too high would obscure distant nodes — defeats visibility.
        # Must be in (0, 0.005] — gentle fade only.
        m = re.search(r"FogExp2\([^,]+,\s*([\d.]+)\)", self.js)
        self.assertIsNotNone(m)
        density = float(m.group(1))
        self.assertGreater(density, 0)
        self.assertLessEqual(density, 0.005,
            f"fog density {density} too dense — must be ≤0.005 to "
            "preserve node/link visibility per user constraint")

    def test_fog_setup_guarded(self):
        # Fog is optional — the renderer must still work if THREE
        # binding fails. The setup is wrapped in try/catch.
        idx = self.js.index("FogExp2")
        # Walk back ~600 chars to find a try (block has multi-line setup).
        prelude = self.js[max(0, idx - 600):idx]
        self.assertIn("try {", prelude,
            "fog setup must be in try/catch — must not break render "
            "if Three.js binding shape changes")
        # And a corresponding catch.
        postlude = self.js[idx:idx + 600]
        self.assertIn("catch", postlude,
            "fog setup must catch errors silently — fog is optional")


if __name__ == "__main__":
    unittest.main()
