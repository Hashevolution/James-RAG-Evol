"""Brain-neural icon + improved gradient shimmer (item #1-A, 2026-05-08).

User feedback: "챗의 답변 추론 과정 ui를 뇌신경이 반짝이는 로봇 모양
아이콘을 쓰고, 첨부된 글자도 그라데이션하게 반짝이게 수정".

Changes:
  - SVG brain-pulse icon: rounded-square robot head + antenna + 3
    neuron nodes that blink with different phases + pulse glow.
    Replaces the static spinner-dot in the thinking placeholder.
  - Multi-stop rainbow gradient on .thinking-label: stage-color →
    white → accent → white → stage-color (was: stage-color → white →
    stage-color, less eye-catching).
  - drop-shadow glow on the label text for a "sparkling" feel.

Run:
  python -m unittest tests.test_brain_icon_shimmer
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS_PATH  = ROOT / "frontend" / "static" / "chat.js"
CSS_PATH = ROOT / "frontend" / "static" / "mobile.css"


class BrainPulseSvgTests(unittest.TestCase):
    """The brainPulseSvg() helper renders an SVG with the expected
    structural elements (outline, links, 3 neurons)."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS_PATH.read_text(encoding="utf-8")

    def test_helper_exists(self):
        self.assertIn("function brainPulseSvg", self.js,
                      "brainPulseSvg helper must exist")

    def test_used_in_appendTyping(self):
        idx = self.js.index("function appendTyping")
        body = self.js[idx:idx + 1500]
        self.assertIn("brainPulseSvg(", body,
                      "appendTyping must call brainPulseSvg for the placeholder icon")

    def test_svg_contains_outline_and_neurons(self):
        # The function returns a string with the SVG markup. Pull it
        # out and check element counts.
        idx = self.js.index("function brainPulseSvg")
        end = self.js.index("function appendTyping", idx)
        body = self.js[idx:end]
        self.assertIn("<svg", body)
        self.assertIn('class="brain-outline"', body,
                      "must include the head/antenna outline")
        # Three neuron nodes with distinct phase classes.
        self.assertIn('class="neuron neuron-1"', body)
        self.assertIn('class="neuron neuron-2"', body)
        self.assertIn('class="neuron neuron-3"', body)
        # Connecting lines between neurons.
        self.assertIn('class="neuron-link"', body,
                      "neuron-link path missing — visual cue connecting nodes")

    def test_active_class_toggle(self):
        idx = self.js.index("function brainPulseSvg")
        end = self.js.index("function appendTyping", idx)
        body = self.js[idx:end]
        self.assertIn("brain-pulse-active", body,
            "active flag must add brain-pulse-active class for animation")

    def test_aria_hidden_for_screen_readers(self):
        # Decorative — don't pollute screen reader output.
        idx = self.js.index("function brainPulseSvg")
        end = self.js.index("function appendTyping", idx)
        body = self.js[idx:end]
        self.assertIn('aria-hidden="true"', body,
                      "decorative SVG should be aria-hidden")


class ShimmerCssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = CSS_PATH.read_text(encoding="utf-8")

    def test_brain_pulse_class_present(self):
        self.assertIn(".brain-pulse {", self.css,
                      "missing .brain-pulse base class")
        self.assertIn(".brain-pulse-active", self.css,
                      "missing active-state CSS")

    def test_three_neuron_blink_keyframes(self):
        # Three different phase keyframes so neurons don't blink in
        # lockstep — gives the "neural firing" feel.
        for kf in ("james-neuron-blink-1",
                   "james-neuron-blink-2",
                   "james-neuron-blink-3"):
            self.assertIn(f"@keyframes {kf}", self.css,
                          f"missing keyframe {kf}")

    def test_neuron_pulse_keyframe_uses_drop_shadow(self):
        # The pulse should glow — look for drop-shadow inside the
        # james-neuron-pulse keyframe block.
        m = re.search(r"@keyframes\s+james-neuron-pulse\s*\{([^}]*\}[^@]*)\}",
                      self.css, re.DOTALL)
        self.assertIsNotNone(m,
            "james-neuron-pulse keyframe missing")
        self.assertIn("drop-shadow", m.group(0),
            "neuron pulse must use drop-shadow for glow effect")

    def test_thinking_label_uses_multistop_gradient(self):
        # Locate .thinking-label rule. Must have ≥4 colour stops in the
        # gradient (stage-color, white, accent, white, stage-color).
        m = re.search(r"\.thinking-label\s*\{([^}]+)\}", self.css)
        self.assertIsNotNone(m, ".thinking-label rule missing")
        body = m.group(1)
        # linear-gradient(...) — count comma-separated stops inside.
        grad = re.search(r"linear-gradient\(([^;]+)\);", body, re.DOTALL)
        self.assertIsNotNone(grad, "must use a linear-gradient")
        stops = grad.group(1).split(",")
        self.assertGreaterEqual(len(stops), 6,
            f"shimmer gradient must have ≥6 segments incl direction "
            f"and 5 colour stops (got {len(stops)})")

    def test_thinking_label_has_glow(self):
        m = re.search(r"\.thinking-label\s*\{([^}]+)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("drop-shadow", m.group(1),
            "label needs a glow filter for sparkling effect")


class IntegrationTests(unittest.TestCase):
    """The placeholder line composition uses the new helper + label
    classes so styling cascades correctly."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS_PATH.read_text(encoding="utf-8")

    def test_placeholder_uses_thinking_label_class(self):
        # Without thinking-label class, the gradient CSS doesn't apply.
        idx = self.js.index("function appendTyping")
        body = self.js[idx:idx + 1500]
        # Find the placeholder div.
        m = re.search(r"thinking-placeholder.+?</div>", body, re.DOTALL)
        self.assertIsNotNone(m)
        ph_html = m.group(0)
        self.assertIn("thinking-label", ph_html,
            "placeholder text must carry .thinking-label so gradient applies")

    def test_placeholder_no_longer_uses_static_dot(self):
        # The old .thinking-spinner-dot was a CSS pulse on a single dot —
        # replaced by brain-pulse. Verify it's gone from the placeholder.
        idx = self.js.index("function appendTyping")
        body = self.js[idx:idx + 1500]
        m = re.search(r"thinking-placeholder.+?</div>", body, re.DOTALL)
        ph_html = m.group(0)
        self.assertNotIn("thinking-spinner-dot", ph_html,
            "old static dot should be replaced by brainPulseSvg")


if __name__ == "__main__":
    unittest.main()
