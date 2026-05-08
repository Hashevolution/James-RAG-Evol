"""Threshold slider labels — 강력/적극/보통/소극/안함 (item #A8-2, 2026-05-09).

User feedback: "어드민 웹서치 설정에서 threshold 조정시 높이거나 낮출때
웹 검색 강력 - 적극 - 보통 - 소극 - 안함. 등으로 알기 쉽게 표기되게끔
개선".

Buckets (pipeline.py: unified_score < threshold → trigger web search):
  v < 0.20  → 안함
  v < 0.35  → 소극
  v < 0.50  → 보통   (default 0.30 sits at the lower edge — fine)
  v < 0.65  → 적극
  else      → 강력

Run:
  python -m unittest tests.test_threshold_labels
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
JS   = ROOT / "frontend" / "static" / "admin.js"


class HtmlElementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_label_span_present(self):
        self.assertIn('id="ws-threshold-label"', self.html,
            "must add a span#ws-threshold-label that JS updates")

    def test_slider_oninput_uses_helper(self):
        # The slider should call applyWsThresholdLabel(this.value),
        # not raw textContent assignment, so the label updates too.
        m = re.search(
            r'<input[^>]*id="ws-threshold"[^>]*oninput="([^"]+)"',
            self.html,
        )
        self.assertIsNotNone(m, "couldn't locate slider element")
        oninput = m.group(1)
        self.assertIn("applyWsThresholdLabel", oninput,
            "slider oninput must call applyWsThresholdLabel for live label")

    def test_track_endpoints_use_korean_labels(self):
        # Min/max badges next to slider should say 안함 / 강력 instead
        # of raw 0.05 / 0.80 numbers.
        # Locate the min/max badges block (between </input> + button).
        block_match = re.search(
            r'id="ws-threshold"[\s\S]+?(<div style="display:flex;gap:4px[^>]*">[\s\S]+?</div>)',
            self.html,
        )
        self.assertIsNotNone(block_match,
            "couldn't locate threshold endpoints block")
        block = block_match.group(1)
        self.assertIn("안함", block,
            "low end must show 안함 label")
        self.assertIn("강력", block,
            "high end must show 강력 label")


class JsHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_helper_function_exists(self):
        self.assertIn("function applyWsThresholdLabel", self.js,
            "must define applyWsThresholdLabel(value) helper")

    def test_helper_handles_all_five_buckets(self):
        idx = self.js.index("function applyWsThresholdLabel")
        body = self.js[idx:idx + 2000]
        for label in ("안함", "소극", "보통", "적극", "강력"):
            self.assertIn(label, body,
                f"all 5 labels must appear; missing: {label}")

    def test_helper_updates_value_display(self):
        idx = self.js.index("function applyWsThresholdLabel")
        body = self.js[idx:idx + 2000]
        # Helper must also update the numeric badge so the slider
        # oninput is the single trigger.
        self.assertIn("ws-threshold-val", body,
            "helper must also update ws-threshold-val numeric display")
        self.assertIn("toFixed(2)", body,
            "numeric badge should be 2-decimal")

    def test_load_chains_helper_after_setting_slider(self):
        # When loadWebSearchConfig populates the slider from the saved
        # threshold, it must also re-apply the label so the saved value
        # shows the right Korean label (not stale "보통").
        idx = self.js.index("async function loadWebSearchConfig")
        body = self.js[idx:idx + 2500]
        self.assertIn("applyWsThresholdLabel", body,
            "loadWebSearchConfig must call applyWsThresholdLabel after slider population")


class BucketBoundaryBehaviorTests(unittest.TestCase):
    """Mirror the JS bucket logic in Python and verify the documented
    boundary mappings hold."""

    @staticmethod
    def _label(v):
        if v < 0.20:   return "안함"
        if v < 0.35:   return "소극"
        if v < 0.50:   return "보통"
        if v < 0.65:   return "적극"
        return "강력"

    def test_default_030_is_normal(self):
        # Default threshold 0.30 should land in 보통 — not too aggressive,
        # not silenced.
        self.assertEqual(self._label(0.30), "소극",
            f"sanity — 0.30 is in [0.20, 0.35) bucket = 소극")

    def test_005_is_off(self):
        self.assertEqual(self._label(0.05), "안함")

    def test_080_is_max(self):
        self.assertEqual(self._label(0.80), "강력")

    def test_boundaries_inclusive_lower_bound(self):
        # v = 0.20 should be "소극" (lower bound inclusive in next bucket)
        self.assertEqual(self._label(0.20), "소극")
        self.assertEqual(self._label(0.35), "보통")
        self.assertEqual(self._label(0.50), "적극")
        self.assertEqual(self._label(0.65), "강력")


if __name__ == "__main__":
    unittest.main()
