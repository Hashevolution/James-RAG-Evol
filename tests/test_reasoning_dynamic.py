"""Reasoning UI dynamic improvements (item #A8-1, 2026-05-09).

User feedback: "추론중 표시 글자 그라데이션 애니메이션을 조금도 빠르게
움직이도록 설정하고 '추론 시작중' 외에 다른 멘트로 전환되는 등
다이내믹하게 개선".

CSS:
  - james-shimmer animation 2.4s → 1.2s (gradient sweep speed)
  - neuron-blink + neuron-pulse 1.4s → 0.9s (faster firing)

JS:
  - THINKING_PLACEHOLDER_PHRASES — 8 phrases that rotate every 1.6s
    until the first real stage event arrives. Stops cleanly when
    apply() removes the placeholder.

Run:
  python -m unittest tests.test_reasoning_dynamic
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS  = ROOT / "frontend" / "static" / "chat.js"
CSS = ROOT / "frontend" / "static" / "mobile.css"


class ShimmerSpeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = CSS.read_text(encoding="utf-8")

    def test_shimmer_animation_faster(self):
        # All james-shimmer animation declarations must be ≤ 1.5s.
        for m in re.finditer(r"animation:\s*james-shimmer\s+([\d.]+)s", self.css):
            duration = float(m.group(1))
            self.assertLessEqual(duration, 1.5,
                f"james-shimmer animation duration {duration}s — must be ≤1.5s "
                f"for the 'dynamic' feel user requested")

    def test_neuron_blink_faster(self):
        # Each .brain-pulse-active .neuron-N rule must use ≤ 1.0s.
        for m in re.finditer(
            r"\.brain-pulse-active\s+\.neuron-\d.+?(\d+\.?\d*)s",
            self.css, re.DOTALL,
        ):
            duration = float(m.group(1))
            self.assertLessEqual(duration, 1.0,
                f"neuron-N animation {duration}s — must be ≤1.0s")


class PlaceholderRotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_phrases_array_exists(self):
        self.assertIn("THINKING_PLACEHOLDER_PHRASES", self.js,
            "must declare a phrase rotation array")

    def test_at_least_5_phrases(self):
        m = re.search(
            r"const\s+THINKING_PLACEHOLDER_PHRASES\s*=\s*\[(.+?)\];",
            self.js, re.DOTALL,
        )
        self.assertIsNotNone(m, "couldn't locate phrases array literal")
        # Count single-quoted strings inside.
        phrases = re.findall(r"'([^']+)'", m.group(1))
        self.assertGreaterEqual(len(phrases), 5,
            f"expected ≥5 phrases, got {len(phrases)}")
        # First phrase must still be the original "추론 시작 중" so
        # there's no jarring change for users who saw the prior copy.
        self.assertEqual(phrases[0], "추론 시작 중",
            "first phrase should remain '추론 시작 중' for continuity")

    def test_rotation_interval_set_in_appendTyping(self):
        idx = self.js.index("function appendTyping")
        body = self.js[idx:idx + 2500]
        self.assertIn("setInterval", body,
            "appendTyping must use setInterval to rotate phrases")
        # Interval should be 1-2s — fast enough to feel alive but not
        # vertigo-inducing.
        m = re.search(r"setInterval\(\(?\)\s*=>\s*\{[\s\S]+?\}\s*,\s*(\d+)\s*\)",
                      body)
        self.assertIsNotNone(m, "couldn't extract interval delay")
        delay = int(m.group(1))
        self.assertGreaterEqual(delay, 800)
        self.assertLessEqual(delay, 2500)

    def test_rotation_clears_when_placeholder_removed(self):
        # When the first stage event arrives we remove the placeholder.
        # The rotation timer must also clear or it'd leak intervals
        # forever (and try to .textContent on a detached node).
        idx = self.js.index("첫 진짜 이벤트 도착 시 placeholder 제거")
        body = self.js[idx:idx + 800]
        self.assertIn("clearInterval(rotateTimer)", body,
            "must clearInterval when placeholder is removed")

    def test_placeholder_text_class_present(self):
        # The rotation logic targets .thinking-placeholder-text — ensure
        # the placeholder span actually carries that class.
        idx = self.js.index("function appendTyping")
        body = self.js[idx:idx + 2500]
        self.assertIn("thinking-placeholder-text", body,
            "placeholder span must have a stable selector class for the "
            "rotation timer to find it")


if __name__ == "__main__":
    unittest.main()
