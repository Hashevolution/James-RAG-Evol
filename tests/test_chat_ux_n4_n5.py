"""Chat UX 사이클 5 — suggestion chip header (N-4) + mid-band web chip (N-5).

User feedback (Axis 6 follow-up, 2026-05-13):

  > 챗 페이지에서 대화창에 다음 중 어떤걸 원하시나요 등 2~3가지 제안시,
  > 클릭 선택 버튼 형성이 안되기도 함 (최신 정보로 보완 검색해 볼까요?
  > 떴을때). 클릭할수 있는 제안시 **제안 ** 별 모양을 좀더 가시적으로 개선
  >
  > 부분 추론의 경우에서도 제안에서 웹검색 가능 여부 선택할 수 있게끔
  > 개선, 제안 사항이 클릭버튼 선택 형태로 안나오는 것같은데 확인후 개선

Root cause:
  - "최신 정보로 보완 검색해 볼까요?" 는 `chat.web_chip_high` i18n 라벨
    문자열. 답변 confidence 가 mid-band (0.50 ≤ score < 0.70) 에 들면
    chip 자체가 안 뜸 (사이클 5 이전 설계 = 미band 에서는 chip 없음).
    LLM 이 답변 본문에 같은 문구를 prose 로 적어도 클릭 가능한 형태가
    아니라 사용자는 "버튼이 안 나옴" 으로 인식.
  - 제안 chip 자체는 떴어도 "→ 텍스트" 만 보여 inline prose 와 시각적
    구분이 약함. 사용자가 "버튼이 아니다" 라고 인식.

Fixes:
  - **N-5**: forceWebChip 의 mid-band 변종 추가 (amber #ffb74d, icon 🔍,
    web-supplement-btn class). low (cyan) / mid (amber) / high (mint)
    삼분기 시각 구별.
  - **N-4**: suggestion chip 클러스터 위에 "✨ 제안" 헤더 추가.
    i18n key `chat.suggestions_label` 신설 (ko=제안 / en=Suggestions).
    클릭 가능 신호를 명시.

Run:
  python -m unittest tests.test_chat_ux_n4_n5
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS   = ROOT / "frontend" / "static" / "chat.js"
I18N = ROOT / "frontend" / "static" / "i18n.js"


# ─── N-5 — mid-band web chip variant ───────────────────────────
class MidBandWebChipTests(unittest.TestCase):
    """Partial-inference confidence (0.50 ≤ score < 0.70) must now
    surface a force-web chip. Before N-5 this band rendered nothing."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def test_isMid_flag_present(self):
        # The mid-band predicate must be computed alongside isLow/isHigh.
        self.assertRegex(
            self.src,
            r"const\s+isMid\s*=.*score\s*>=\s*LOW_CONF.*score\s*<\s*HIGH_CONF",
            "isMid predicate must guard the new mid-band branch",
        )

    def test_mid_band_fires_chip(self):
        # The gate must include isMid in addition to isLow/isHigh.
        self.assertIn("isLow || isMid || isHigh", self.src,
            "force-web chip must fire in the mid band too — was the "
            "'no chip' zone before N-5 and that's where users reported "
            "the missing button")

    def test_mid_variant_uses_web_supplement_class(self):
        # The new variant gets its own CSS hook so admin/theme tweaks
        # can style it distinctly from low/high.
        self.assertIn("web-supplement-btn", self.src,
            "mid-band variant must carry a dedicated class")

    def test_mid_variant_uses_web_chip_mid_i18n(self):
        # Don't hard-code the label — go through i18n so ko/en both work.
        self.assertIn("t('chat.web_chip_mid')", self.src,
            "mid-band variant must pull its label from i18n")


class WebChipMidI18nTests(unittest.TestCase):
    """i18n keys for the new mid-band variant exist in both locales."""

    @classmethod
    def setUpClass(cls):
        cls.src = I18N.read_text(encoding="utf-8")

    def test_ko_mid_key_present(self):
        # Korean strings live around line 633; just assert the key is
        # there with a non-empty value.
        m = re.search(r"'chat\.web_chip_mid':\s*'([^']+)'", self.src)
        self.assertIsNotNone(m, "i18n must define chat.web_chip_mid")
        # Both locales declare this key — collect all occurrences.
        all_vals = re.findall(r"'chat\.web_chip_mid':\s*'([^']+)'", self.src)
        self.assertEqual(len(all_vals), 2,
            "chat.web_chip_mid must be defined exactly twice (en + ko)")
        # Verify each non-empty.
        for v in all_vals:
            self.assertTrue(v.strip(),
                "chat.web_chip_mid label must be non-empty in both locales")


# ─── N-4 — suggestion chip cluster header ───────────────────────
class SuggestionClusterHeaderTests(unittest.TestCase):
    """Suggestion chips now sit under a ✨ 제안 header so the cluster
    reads as clickable. Bare chips were getting mistaken for inline
    prose."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def test_cluster_header_emits_when_suggestions_exist(self):
        # The next-actions-header DOM node must appear in the chip
        # rendering branch. Anchor on the rendering site so the test
        # doesn't drift if the styling changes. 2500 chars covers the
        # full conditional render block now that the header was added.
        idx = self.src.index("if (suggestions.length > 0)")
        block = self.src[idx:idx + 2500]
        self.assertIn("next-actions-header", block,
            "the suggestion render block must include a cluster header")
        self.assertIn("✨", block,
            "header must surface the ✨ star icon — user feedback "
            "explicitly asked for 별 모양 visibility")
        self.assertIn("t('chat.suggestions_label')", block,
            "header must pull its label from i18n")

    def test_individual_chip_keeps_arrow_indicator(self):
        # The "→" prefix on each chip is the click affordance; even with
        # the new header, individual chips must keep their arrow.
        idx = self.src.index("if (suggestions.length > 0)")
        block = self.src[idx:idx + 2500]
        self.assertIn("→", block,
            "each suggestion chip must keep its '→' click indicator")
        self.assertIn("data-action=\"ask-suggestion\"", block,
            "chip event hook must be preserved (event delegation handler "
            "in chat.js still listens for ask-suggestion)")


class SuggestionsLabelI18nTests(unittest.TestCase):
    """i18n keys for the new cluster header exist in both locales."""

    @classmethod
    def setUpClass(cls):
        cls.src = I18N.read_text(encoding="utf-8")

    def test_label_defined_twice(self):
        vals = re.findall(r"'chat\.suggestions_label':\s*'([^']+)'", self.src)
        self.assertEqual(len(vals), 2,
            "chat.suggestions_label must exist exactly twice (en + ko)")
        for v in vals:
            self.assertTrue(v.strip())


# ─── Regression — existing low/high variants still wired ────────
class LowHighVariantsStillPresentTests(unittest.TestCase):
    """N-5 must not regress the original two-variant behaviour."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def test_low_variant_intact(self):
        self.assertIn("web-collect-btn", self.src)
        self.assertIn("t('chat.web_chip_low')", self.src)

    def test_high_variant_intact(self):
        self.assertIn("web-refresh-btn", self.src)
        self.assertIn("t('chat.web_chip_high')", self.src)


if __name__ == "__main__":
    unittest.main()
