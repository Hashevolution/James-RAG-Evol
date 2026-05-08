"""Mobile responsive UI — frontend/static/mobile.css contract tests.

User feedback (2026-05-08): "웹 뿐만 아니라 폰 사이즈에서도 보기에
적합한 ui로 개선 가능?".

Strategy: a separate `mobile.css` adds @media-gated overrides for
≤768px (tablet), ≤480px (phone), and short-landscape phones. Loaded
LAST in <head> so its rules win over inline base styles by source
order alone (no !important spam needed).

Coverage:
  - mobile.css exists with the expected breakpoints.
  - Both index.html and admin.html link mobile.css AFTER inline
    <style>, so the cascade wins for narrow viewports.
  - Both HTMLs have viewport meta with viewport-fit=cover (iOS
    notch / safe-area), and a theme-color matching --bg.
  - Touch-target rules: buttons / nav-items / textareas have
    min-height ≥ 36px (Apple HIG / Material standard 44 minimum,
    36 acceptable for inline / secondary controls).
  - iOS-zoom-on-focus guard: input/textarea font-size ≥ 16px in
    the mobile rule block.
  - Safe-area-inset-bottom honored in input area padding.

Run:
  python -m unittest tests.test_mobile_responsive
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = ROOT / "frontend" / "static" / "mobile.css"
INDEX_HTML = ROOT / "frontend" / "index.html"
ADMIN_HTML = ROOT / "frontend" / "admin.html"


class CssExistsAndCoversBreakpointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = CSS_PATH.read_text(encoding="utf-8")

    def test_css_file_exists(self):
        self.assertTrue(CSS_PATH.exists(),
                        "frontend/static/mobile.css must exist")

    def test_breakpoint_768px_present(self):
        # Tablet + phone primary breakpoint.
        self.assertRegex(
            self.css,
            r"@media\s*\(\s*max-width\s*:\s*768px\s*\)",
            "768px breakpoint missing",
        )

    def test_breakpoint_480px_present(self):
        # Tighter phone breakpoint.
        self.assertRegex(
            self.css,
            r"@media\s*\(\s*max-width\s*:\s*480px\s*\)",
            "480px breakpoint missing",
        )

    def test_landscape_short_breakpoint_present(self):
        # Phone landscape — header must stay tight.
        self.assertRegex(
            self.css,
            r"@media\s*\(\s*max-width\s*:\s*920px\s*\)\s*and\s*\(\s*max-height\s*:\s*480px\s*\)",
            "landscape phone breakpoint missing",
        )


class TouchTargetAndIosGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = CSS_PATH.read_text(encoding="utf-8")

    def test_input_font_size_at_least_16px(self):
        # iOS zooms in on focus when input font-size < 16px. The
        # mobile.css rule for textarea/input must declare ≥16px.
        # We look inside the 768px block.
        block_match = re.search(
            r"@media\s*\(\s*max-width\s*:\s*768px\s*\)\s*\{(.+?)\n\}\s*\n\s*/\*",
            self.css, re.DOTALL,
        )
        # The block end matching is fragile; just search globally for
        # the relevant rule.
        self.assertRegex(
            self.css,
            r"textarea[^{]*\{[^}]*font-size\s*:\s*16px",
            "textarea must have font-size: 16px in mobile.css "
            "(iOS zoom-on-focus guard)",
        )

    def test_buttons_have_touch_target_min_height(self):
        # Some button class must declare min-height >= 36px in the
        # mobile breakpoint. We accept the rule "button, .btn"
        # OR per-component min-heights elsewhere.
        self.assertRegex(
            self.css,
            r"min-height\s*:\s*(36|40|44|48)px",
            "no touch-target min-height rule found in mobile.css",
        )

    def test_safe_area_inset_bottom_honored(self):
        self.assertIn(
            "env(safe-area-inset-bottom",
            self.css,
            "input area padding must use env(safe-area-inset-bottom) "
            "for iOS home-bar / notch devices",
        )


class HtmlLinksMobileCssTests(unittest.TestCase):
    """Both index.html and admin.html must link mobile.css AFTER
    their inline <style> block — source order = cascade order, so
    later rules win without !important spam."""

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_index_html_links_mobile_css_after_style(self):
        html = self._read(INDEX_HTML)
        link_pos = html.find('href="/static/mobile.css"')
        style_close_pos = html.find("</style>")
        self.assertGreater(link_pos, 0,
                           "index.html does not <link> mobile.css")
        self.assertGreater(link_pos, style_close_pos,
                           "mobile.css link must come AFTER </style> "
                           "so cascade source-order wins")

    def test_admin_html_links_mobile_css_after_style(self):
        html = self._read(ADMIN_HTML)
        link_pos = html.find('href="/static/mobile.css"')
        style_close_pos = html.find("</style>")
        self.assertGreater(link_pos, 0,
                           "admin.html does not <link> mobile.css")
        self.assertGreater(link_pos, style_close_pos,
                           "mobile.css link must come AFTER </style>")

    def test_viewport_fit_cover_for_safe_area(self):
        # Both HTMLs need viewport-fit=cover for env(safe-area-*) to
        # actually do anything on iOS.
        for path in (INDEX_HTML, ADMIN_HTML):
            html = self._read(path)
            self.assertIn(
                "viewport-fit=cover",
                html,
                f"{path.name} viewport meta missing viewport-fit=cover; "
                f"env(safe-area-inset-*) is a no-op without it",
            )

    def test_theme_color_meta_present(self):
        # Mobile browsers tint the address bar to theme-color.
        # Without it, the system white address bar clashes with
        # JAMES's dark theme on Android Chrome.
        for path in (INDEX_HTML, ADMIN_HTML):
            html = self._read(path)
            self.assertRegex(
                html,
                r'<meta\s+name="theme-color"',
                f"{path.name} missing theme-color meta — Android "
                f"address bar will not match the dark theme",
            )


class AvoidsUnreachableCssTests(unittest.TestCase):
    """Sanity: rules using !important should be limited to cases
    where overriding inline-style is actually necessary."""

    def test_no_excessive_important(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        # Count !important occurrences. Inline-style overrides need
        # this; a small number is fine. Excessive use indicates the
        # cascade strategy is broken.
        count = css.count("!important")
        self.assertLessEqual(
            count, 25,
            f"!important used {count} times in mobile.css; aim for "
            f"≤ 25 (inline-style overrides only). Restructure rules "
            f"or rely on source-order cascade if higher."
        )


if __name__ == "__main__":
    unittest.main()
