"""WCAG AA contrast contract on the dark-UI design tokens.

HANDOVER_WEB_UI.md priority #4 subset 4c. The audit found
``--muted-2`` was #5d616c which gave only ~3.16:1 on --bg (#0a0c11)
— **below the WCAG AA 4.5:1 threshold** for normal-sized body text.
4 small-text use sites (10-12 px) inherited that failure.

This test parses tokens.css, extracts the colour tokens, and computes
the relative-luminance contrast ratio between every text colour and
``--bg``. Each must pass the appropriate WCAG AA threshold (4.5:1 for
normal text, 3:1 for large/decorative).

If a future change darkens ``--muted-2`` (or any text token) below
threshold, this test fails loudly so the regression doesn't ship.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "frontend" / "static" / "tokens.css"


def _srgb_to_linear(c: float) -> float:
    """sRGB component → linear-RGB component, per WCAG 2.x formula."""
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def contrast_ratio(c1: str, c2: str) -> float:
    """WCAG contrast — (L_lighter + 0.05) / (L_darker + 0.05)."""
    l1, l2 = relative_luminance(c1), relative_luminance(c2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def _read_token(name: str) -> str:
    """Pull the value of a top-level token from tokens.css. Returns
    the raw value (typically a hex literal); fails fast if missing."""
    src = TOKENS.read_text(encoding="utf-8")
    m = re.search(rf"{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{6}})", src)
    if not m:
        raise AssertionError(
            f"could not find {name} in tokens.css — token may have been "
            f"renamed or moved out-of-root"
        )
    return m.group(1).lower()


class WcagAaContrastTests(unittest.TestCase):
    """Every text token must satisfy the appropriate AA threshold on --bg.

    Thresholds (WCAG 2.1 SC 1.4.3):
      - Normal text:           ≥ 4.5 : 1
      - Large text (≥ 18pt or  ≥ 3.0 : 1
        14pt bold):
      - UI graphical objects:  ≥ 3.0 : 1
    """

    @classmethod
    def setUpClass(cls):
        cls.bg = _read_token("--bg")

    def _assert_ratio(self, token_name: str, threshold: float,
                      kind: str) -> None:
        color = _read_token(token_name)
        ratio = contrast_ratio(color, self.bg)
        self.assertGreaterEqual(
            ratio, threshold,
            f"{token_name} ({color}) on --bg ({self.bg}) is "
            f"{ratio:.2f}:1 — below WCAG AA {kind} threshold "
            f"({threshold}:1)",
        )

    def test_text_passes_aa_normal(self):
        self._assert_ratio("--text", 4.5, "normal text")

    def test_text_soft_passes_aa_normal(self):
        self._assert_ratio("--text-soft", 4.5, "normal text")

    def test_muted_passes_aa_normal(self):
        # --muted is broadly used for body labels / metadata at
        # 11-13 px — needs the full body-text threshold.
        self._assert_ratio("--muted", 4.5, "normal text")

    def test_muted_2_passes_aa_normal(self):
        # --muted-2 is the borderline secondary muted. Pre-fix value
        # was #5d616c at 3.16:1 — failed AA. Post-fix #787c84 sits
        # at ~4.67:1, just above threshold.
        self._assert_ratio("--muted-2", 4.5, "normal text")

    def test_accent_fg_passes_aa_normal(self):
        # --accent-fg is the foreground colour used on accent-tinted
        # backgrounds AND for prominent body text on --bg in a few
        # places (e.g. modal titles). Verify AA on --bg.
        self._assert_ratio("--accent-fg", 4.5, "normal text")

    def test_brand_2_passes_aa_large(self):
        # --brand-2 (intelligence cyan) is reserved for divider lines
        # / status dots / large badges — large-text/UI threshold
        # applies (3:1).
        self._assert_ratio("--brand-2", 3.0, "large text / UI")


class ContrastCalculatorTests(unittest.TestCase):
    """Spot-check the formula on well-known reference pairs.

    Catches a regression where someone refactors the helpers and
    breaks the underlying calculation."""

    def test_pure_black_on_pure_white_is_21(self):
        # WCAG defines this as the maximum possible — 21:1.
        self.assertAlmostEqual(
            contrast_ratio("#000000", "#ffffff"), 21.0, places=1)

    def test_pure_white_on_pure_black_is_21(self):
        self.assertAlmostEqual(
            contrast_ratio("#ffffff", "#000000"), 21.0, places=1)

    def test_identical_colors_is_1(self):
        self.assertAlmostEqual(
            contrast_ratio("#7c6af7", "#7c6af7"), 1.0, places=1)


if __name__ == "__main__":
    unittest.main()
