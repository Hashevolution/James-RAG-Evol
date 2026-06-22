"""Structural lock-test for the visual-regression harness.

The harness itself (scripts/visual_regression.py) needs a running server
+ headless Chromium to actually render pages, so the *live* run is
operator-driven (or CI with a browser). This test pins the harness's
contract so a refactor can't silently break it:

  - the module imports without playwright/chromium present;
  - PAGES covers the canonical routes (so a route rename flags here);
  - the benign report-only CSP console warning stays ignored;
  - a committed baseline exists for every page (the visual reference).

A *live* render+diff smoke runs only when both Chromium is installed AND
``JAMES_VIZ_BASE_URL`` points at a running server — otherwise it skips,
so the normal test run stays green without a browser/server.

Run: ``python -m unittest tests.test_visual_regression_harness``
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class HarnessContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import scripts.visual_regression as viz
        cls.viz = viz

    def test_module_imports_without_browser(self):
        # Module-level code must not require playwright (lazy-imported in
        # run()), so the harness is importable in any environment.
        self.assertTrue(hasattr(self.viz, "PAGES"))
        self.assertTrue(callable(self.viz.main))

    def test_pages_cover_canonical_routes(self):
        paths = {p for _, p in self.viz.PAGES}
        for must in ("/", "/chat", "/admin", "/admin/graph",
                     "/admin/graph#flow", "/admin/graph#rollback",
                     "/workspace"):
            self.assertIn(must, paths,
                          f"visual harness PAGES missing canonical route {must!r}")

    def test_benign_csp_warning_ignored(self):
        self.assertIn("upgrade-insecure-requests",
                      "".join(self.viz.CONSOLE_IGNORE),
                      "the report-only CSP console warning must stay ignored")

    def test_baseline_exists_for_every_page(self):
        base = ROOT / "reports" / "visual" / "baseline"
        if not base.exists():
            self.skipTest("no baseline captured yet "
                          "(run scripts/visual_regression.py --update-baseline)")
        for name, _ in self.viz.PAGES:
            self.assertTrue((base / f"{name}.png").exists(),
                            f"missing visual baseline: {name}.png")


class LiveRenderSmoke(unittest.TestCase):
    """Opt-in: only runs when Chromium is installed AND JAMES_VIZ_BASE_URL
    is set (a running server). Otherwise skipped."""

    def test_live_render_no_console_errors(self):
        import scripts.visual_regression as viz
        if not viz._have_playwright():
            self.skipTest("playwright/chromium not installed")
        base_url = os.environ.get("JAMES_VIZ_BASE_URL")
        if not base_url:
            self.skipTest("set JAMES_VIZ_BASE_URL to a running server to run "
                          "the live render smoke")
        rc = viz.run(base_url, update_baseline=False, threshold=1.0)
        self.assertEqual(rc, 0, "visual harness reported console errors / diffs")


if __name__ == "__main__":
    unittest.main()
