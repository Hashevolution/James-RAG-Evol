"""UI polish — knowledge + security + report intelligence (item #A8-9).

User feedback (2026-05-09): "웹페이지 전체 ui 분위기를 사무적으로
지식과 보안을 갖춘 스마트한 보고서 관리 시스템이라는 점을 잘 나타날수
있게하는 디자인으로 개선".

Goals (subjective; tests assert presence not aesthetics):
  - Slate-tinted palette (cooler greys/blues for enterprise feel)
  - Logo gets a tagline that frames product as knowledge+security+report
  - James answer bubble feels like a "report card" (left accent rail
    + subtle box-shadow elevation)
  - Welcome screen reframes from generic "지식 추론 엔진" to
    "지식·보안·보고서 인텔리전스"
  - Top accent rail (1-2px gradient stripe) for system-header look

Run:
  python -m unittest tests.test_ui_report_polish
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "index.html"


class PaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_brand_2_var_added(self):
        # Secondary brand colour for "intelligence cyan" — used by
        # status badges / dividers.
        self.assertIn("--brand-2:", self.html,
            "must declare --brand-2 secondary brand colour for the polish")
        self.assertIn("--brand-2-soft:", self.html,
            "soft variant for tinted backgrounds")

    def test_shadow_card_var_added(self):
        # Custom elevation token for "report card" surfaces.
        self.assertIn("--shadow-card:", self.html,
            "must declare --shadow-card token for elevation")
        m = re.search(r"--shadow-card:\s*([^;]+);", self.html)
        self.assertIsNotNone(m)
        self.assertIn("rgba(0,0,0", m.group(1),
            "shadow should include a dark rgba layer")

    def test_palette_cooler_tones(self):
        # The base bg should still be near-black but slightly tinted
        # toward navy/slate. Specifically: NOT pure black (#000) and
        # NOT the prior neutral #0c0d10 — should land on something
        # cooler like #0a0c11.
        m = re.search(r"--bg:\s*(#[0-9a-fA-F]{6})", self.html)
        self.assertIsNotNone(m)
        bg = m.group(1).lower()
        self.assertNotEqual(bg, "#000000",
            "pure black is too aggressive — keep slight tint")
        # New value should be different from the prior #0c0d10 baseline.
        self.assertNotEqual(bg, "#0c0d10",
            "palette polish should refresh the bg tint")


class TopAccentRailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_body_before_pseudo_present(self):
        # Subtle "system header" stripe at the top of every page.
        self.assertIn("body::before", self.html,
            "must add ::before stripe on body for system-header look")
        m = re.search(r"body::before\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m)
        block = m.group(1)
        self.assertIn("position: fixed", block,
            "stripe must be fixed-position so it stays during scroll")
        self.assertIn("height", block)
        # Gradient between accent + brand-2.
        self.assertIn("linear-gradient", block,
            "stripe should use a gradient (accent → brand-2)")
        self.assertIn("var(--accent)", block)
        self.assertIn("var(--brand-2)", block)

    def test_stripe_is_thin(self):
        # Should be visually subtle — 1-3px tall, not a thick band.
        m = re.search(r"body::before\s*\{[^}]*height:\s*(\d+)px", self.html)
        self.assertIsNotNone(m, "couldn't extract stripe height")
        height = int(m.group(1))
        self.assertLessEqual(height, 4,
            f"stripe height {height}px too thick — must be ≤ 4px")


class LogoTaglineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_tagline_class_in_html(self):
        self.assertIn('class="tagline"', self.html,
            "must include a tagline span for the logo")

    def test_tagline_copy_mentions_security_and_reporting(self):
        # The tagline frames JAMES as more than chat — knowledge/
        # security/reporting suite.
        m = re.search(r'class="tagline"[^>]*>([^<]+)<', self.html)
        self.assertIsNotNone(m)
        copy = m.group(1)
        # Must mention 보안 (security) and either 지식 (knowledge) or
        # 보고서 (reporting).
        self.assertIn("보안", copy,
            "tagline must mention 보안 (security) for the brand framing")
        self.assertTrue("지식" in copy or "보고서" in copy,
            f"tagline must mention 지식 or 보고서; got {copy!r}")

    def test_logo_mark_uses_brand_2(self):
        # The square mark should blend accent → brand-2 for the
        # "intelligence" feel.
        m = re.search(r"\.logo::before\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m)
        block = m.group(1)
        self.assertIn("var(--brand-2)", block,
            "logo mark gradient should include the new brand-2 stop")


class ReportCardBubbleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_james_bubble_has_left_accent_rail(self):
        # The .msg.james .bubble selector should pick up a left
        # border accent — a thin colour stripe on the left edge that
        # makes the answer feel like a structured report.
        m = re.search(r"\.msg\.james\s+\.bubble\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m, "couldn't locate james bubble rule")
        body = m.group(1)
        self.assertIn("border-left", body,
            "james bubble must have a left accent rail")

    def test_james_bubble_has_elevation(self):
        m = re.search(r"\.msg\.james\s+\.bubble\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("box-shadow", body,
            "james bubble must use box-shadow for elevation")
        self.assertIn("var(--shadow-card)", body,
            "should reference the new --shadow-card token")


class WelcomeReframeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_welcome_subtitle_mentions_security_and_reporting(self):
        # Old copy: "보안 중심 Graph-RAG 지식 추론 엔진".
        # New: 지식 + 보안 + 보고서 angle.
        m = re.search(
            r'<div class="welcome-sub">(.+?)</div>',
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m)
        sub = m.group(1)
        self.assertIn("보안", sub,
            "welcome subtitle must mention 보안")
        self.assertIn("보고서", sub,
            "welcome subtitle must mention 보고서 — the new framing")

    def test_welcome_has_english_descriptor(self):
        # Subtle uppercase English descriptor in mono — feels like an
        # enterprise product UI (e.g., "Knowledge · Security · Reporting").
        m = re.search(
            r'<div class="welcome-sub">(.+?)</div>',
            self.html, re.DOTALL,
        )
        sub = m.group(1)
        self.assertTrue(
            "Knowledge" in sub and "Security" in sub,
            "welcome should include an English descriptor mentioning "
            "Knowledge + Security for enterprise framing")


if __name__ == "__main__":
    unittest.main()
