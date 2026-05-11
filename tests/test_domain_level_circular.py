"""Domain level cap removal + circular charts (item #2-B + #2-C, 2026-05-08).

User feedback:
  #2-B: "지식 레벨이 10에서 멈춤 — 무한대로 늘리고 싶다".
  #2-C: "각 분야별로 원형 그래프, 퍼센트 표시".

Backend (core/knowledge_tracker.py):
  - get_domain_levels(): drop the min(10, ...) cap on level. Level
    is now max(1, score/5 + 1) — uncapped, so accumulating users can
    go past 10.
  - New `tier_pct` field — progress within the current 5-point tier
    toward the next level (0-100%). Drives the donut fill arc.

Frontend (admin.js):
  - renderDomains() switches from linear progress bar → SVG donut
    ring with the level number in centre.
  - "/ 10" suffix removed — level is uncapped.
  - tier_pct fills the arc; score + wiki count rendered alongside.

Run:
  python -m unittest tests.test_domain_level_circular
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class LevelCapRemovalTests(unittest.TestCase):
    """Backend cap removal — level can now exceed 10."""

    @classmethod
    def setUpClass(cls):
        from core.knowledge_tracker import KnowledgeTracker
        cls.KT = KnowledgeTracker
        cls.src = inspect.getsource(KnowledgeTracker)

    def test_no_cap_in_get_domain_levels(self):
        # The literal `min(10, ...)` should be gone from level calc.
        m = re.search(r"def get_domain_levels.+?return result",
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(0)
        # level = max(1, ...) is fine; level = max(1, min(10, ...)) is not.
        bad = re.search(r"level\s*=\s*max\(\s*1\s*,\s*min\(\s*10\b", body)
        self.assertIsNone(bad,
            "level cap 10 must be removed — user wants uncapped progression")

    def test_tier_pct_field_present(self):
        m = re.search(r"def get_domain_levels.+?return result",
                      self.src, re.DOTALL)
        body = m.group(0)
        self.assertIn('"tier_pct"', body,
            "must expose tier_pct so donut can render progress within tier")

    def test_high_score_yields_high_level(self):
        # Smoke — accumulating score past the old cap should produce
        # level > 10. Use the public API.
        kt = self.KT()
        # 200 score → tier_floor 200, level = 200/5 + 1 = 41.
        kt._scores["coding"] = 200.0
        levels = kt.get_domain_levels()
        coding = next(d for d in levels if d["domain"] == "coding")
        self.assertGreater(coding["level"], 10,
            f"score 200 should yield level > 10 (got {coding['level']})")

    def test_tier_pct_within_0_100(self):
        kt = self.KT()
        for score in (0, 1.0, 3.5, 5.0, 12.5, 100.0, 999.0):
            kt._scores["coding"] = score
            levels = kt.get_domain_levels()
            coding = next(d for d in levels if d["domain"] == "coding")
            self.assertGreaterEqual(coding["tier_pct"], 0,
                f"tier_pct must be ≥ 0 (got {coding['tier_pct']} at score {score})")
            self.assertLessEqual(coding["tier_pct"], 100,
                f"tier_pct must be ≤ 100 (got {coding['tier_pct']} at score {score})")


class DonutChartFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "admin.js").read_text(encoding="utf-8")

    def test_donut_helper_exists(self):
        self.assertIn("function _domainDonut", self.js,
            "_domainDonut helper must exist for SVG ring rendering")

    def test_donut_uses_circle_with_dasharray(self):
        idx = self.js.index("function _domainDonut")
        end = self.js.index("function renderDomains", idx)
        body = self.js[idx:end]
        self.assertIn("<svg", body, "donut must render SVG")
        self.assertIn("<circle", body, "donut must use <circle> elements")
        self.assertIn("stroke-dasharray", body,
            "progress arc requires stroke-dasharray")
        self.assertIn("transform=\"rotate(-90", body,
            "arc must start from top (rotate -90)")

    def test_donut_includes_level_number(self):
        idx = self.js.index("function _domainDonut")
        end = self.js.index("function renderDomains", idx)
        body = self.js[idx:end]
        self.assertIn("d.level", body,
            "donut must render the level number in centre")
        self.assertIn("<text", body, "must use <text> for level label")

    def test_render_uses_donut(self):
        idx = self.js.index("function renderDomains")
        body = self.js[idx:idx + 2500]
        self.assertIn("_domainDonut(d)", body,
            "renderDomains must call _domainDonut for each domain")

    def test_no_more_slash_10_suffix(self):
        # Level cap removed → "/ 10" suffix should be gone from the
        # domain card render. (Other places — e.g. hardware lv.X — may
        # still have caps, that's separate.)
        idx = self.js.index("function renderDomains")
        body = self.js[idx:idx + 2500]
        self.assertNotIn("/ 10", body,
            "linear-bar version's '/ 10' suffix should be replaced by donut")

    def test_no_linear_progress_bar_in_domain_card(self):
        # The old linear progress bar div should be gone.
        idx = self.js.index("function renderDomains")
        body = self.js[idx:idx + 2500]
        # Old code had `width:${d.pct}%` on a height:8px linear bar.
        self.assertNotIn("height:8px", body,
            "linear bar (height:8px) replaced by donut chart")


if __name__ == "__main__":
    unittest.main()
