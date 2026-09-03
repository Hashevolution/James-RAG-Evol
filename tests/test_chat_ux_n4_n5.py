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
        # [2026-08-26] Was asserting the ✨ glyph. The icon was dropped
        # in the emoji-to-SVG sweep but its <span> was left behind
        # empty, so the header rendered a blank 14px box plus the
        # flex gap — the same shape of defect as the admin password
        # toggle. The empty span is removed; what the header must still
        # do is label the cluster, which is asserted above.
        self.assertNotIn('<span style="font-size:14px"></span>', block,
            "an empty decorative span leaves a blank gap in the header")
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


# ─── PR-O2 (2026-05-15) — 자연어 제안 패턴 + threshold ≥1 ───────
class SuggestionPatternsPrO2Tests(unittest.TestCase):
    """사이클 12 PR-O2: SUGGESTION_PATTERNS 에 자연어 invite 3 패턴 추가
    + 단일 매칭 (≥1) 도 chip 화.

    User feedback (2026-05-14):
      > 못 잡는 케이스: 자연어 제안 ("혹시 ~궁금하신가요?"), 1개만 매칭

    NL 패턴 ⑤⑥⑦ 은 매우 구체적 phrasing → false positive 낮음. 기존 ①~④
    numbered list 도 threshold 완화 이득. tail 600자 + length 4-200 +
    중복 제거가 본문 잔재 차단 layer.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")
        # SUGGESTION_PATTERNS 배열 본문만 잘라 옴 — 다른 정규식 정의가
        # 같은 파일에 있으니 윈도우 좁히기.
        m_open = re.search(
            r"const\s+SUGGESTION_PATTERNS\s*=\s*\[", cls.src,
        )
        assert m_open, "SUGGESTION_PATTERNS 배열 정의를 찾을 수 없음"
        body_start = m_open.end()
        m_close = re.search(r"\n\];", cls.src[body_start:])
        assert m_close, "SUGGESTION_PATTERNS 배열의 ']' 닫힘을 찾을 수 없음"
        cls.array_body = cls.src[body_start:body_start + m_close.start()]

    def test_pattern_natural_language_hokshi(self):
        # ⑤ "혹시 X 궁금하신가요?" — anchor 가 한글 '혹시' 로 시작.
        self.assertIn("/(혹시)", self.array_body,
            "자연어 패턴 ⑤ '혹시 X 궁금하신가요?' 누락")

    def test_pattern_natural_language_more_info(self):
        # ⑥ "X에 대해 더 알고 싶으시면" — '더\s*알고\s*싶' 시그니처.
        self.assertRegex(self.array_body, r"더\\s\*알고\\s\*싶",
            "자연어 패턴 ⑥ 'X에 대해 더 알고 싶으시면' 누락")

    def test_pattern_natural_language_related_question(self):
        # ⑦ "관련 질문(으로는)?: X" — '관련' + '질문|문의' + ':'.
        self.assertIn("관련(?:된|해서?)?", self.array_body,
            "자연어 패턴 ⑦ '관련된 질문: X' 누락")
        # '질문|문의' alternation 시그니처 (non-capturing group `(?:...)` 내).
        self.assertIn("질문|문의", self.array_body,
            "자연어 패턴 ⑦ 의 '질문|문의' alternation 누락")

    def test_threshold_lowered_to_one(self):
        # 기존 `out.length >= 2` → `>= 1`.
        self.assertIn("out.length >= 1", self.src,
            "threshold 가 ≥1 로 완화되지 않음")
        # 기존 `>= 2` 게이트가 더 이상 extractNextActionSuggestions 안에
        # 남아 있으면 안 됨 (다른 함수의 `>= 2` 는 무관).
        m_fn = re.search(
            r"function\s+extractNextActionSuggestions\s*\("
            r"[\s\S]+?\n\}\n",
            self.src,
        )
        self.assertIsNotNone(m_fn, "extractNextActionSuggestions 본문을 찾을 수 없음")
        self.assertNotIn("out.length >= 2", m_fn.group(0),
            "extractNextActionSuggestions 안에 옛 ≥2 게이트가 남아있음")

    # [2026-08-19] The three numeric patterns moved off `\d`, which in
    # JavaScript is ASCII-only, onto an explicit class covering ASCII +
    # Arabic-Indic + extended Arabic-Indic digits (Ali Afana's second
    # finding). The signatures are pinned against that class now; the
    # intent of this regression — ①~④ must survive PR-O2's ⑤⑥⑦ — is
    # unchanged.
    DIGIT_CLASS = "[0-9\u0660-\u0669\u06F0-\u06F9]"

    def test_existing_numbered_patterns_intact(self):
        d = self.DIGIT_CLASS
        self.assertIn(r"\((" + d + r")\)", self.array_body,
            "① '(1) X (2) Y' 패턴 누락")
        self.assertIn("(" + d + r")\)\s+", self.array_body,
            "② '1) X 2) Y' 패턴 누락")
        self.assertIn("(" + d + r")\.\s+", self.array_body,
            "③ '1. X 2. Y' 패턴 누락")
        self.assertIn("①②③④⑤⑥⑦⑧⑨", self.array_body,
            "④ '① X ② Y' 원문자 패턴 누락")

    def test_numeric_patterns_are_not_ascii_only(self):
        # The point of the change: a reply enumerated in Arabic-Indic
        # digits must not be invisible to the chip extractor.
        self.assertNotIn(r"\((\d)\)", self.array_body,
            "ASCII-only \\d must not come back for the numeric patterns")
        self.assertIn("\u0660-\u0669", self.array_body,
            "Arabic-Indic digit range missing from SUGGESTION_PATTERNS")

    def test_capture_group_2_convention_maintained(self):
        # 모든 패턴이 group 2 = chip 텍스트 컨벤션을 따라야 함
        # (extractNextActionSuggestions 의 `m[2]` 접근).
        # 핵심 NL 패턴 (혹시 / 더 알고 / 관련 질문) 의 group 2 자리에
        # 길이 상한 capture 시그니처 ([^...]{N,M}) 가 있는지 직접 확인.
        # 정확한 group counting 은 JS regex 파서 없이 어려우므로
        # 시그니처 단위 검사.
        self.assertRegex(
            self.array_body,
            r"혹시[\)\s].*\[\^\?？\\n\]\{6,200\}",
            "⑤ 혹시 패턴의 group 2 capture 시그니처 (길이 6-200) 누락",
        )
        self.assertRegex(
            self.array_body,
            r"\[\^\.\,\(\)\\n\]\{4,200\}\?\)에",
            "⑥ '더 알고' 패턴의 group 2 capture 시그니처 (길이 4-200) 누락",
        )
        self.assertRegex(
            self.array_body,
            r"\[:：\]\)\\s\*\(\[\^\\n\]\{4,200\}\)",
            "⑦ '관련 질문' 패턴의 ':' 뒤 group 2 capture 누락",
        )


class CleanAnswerBodyStripPrO2bTests(unittest.TestCase):
    """[PR-O2b 2026-05-18 user feedback]

    PR-O2 의 cleanAnswer 가 tail 600자 안에서 첫 매칭 이후만 자른다.
    그래서 LLM 답변이 길고 enumeration ((1)/(2)/(3)) 이 본문 앞쪽
    (tail 600자 밖) 에 있고, 다른 follow-up phrase 가 본문 끝쪽
    (tail 안) 에 있으면:

      - tail 안의 phrase 가 chip 으로 emit 됨
      - cutStart 가 tail 안의 첫 매칭 위치 → 그 이후만 strip
      - 본문 앞쪽 enumeration 은 그대로 남음
      - 사용자는 본문 (1)(2)(3) + 하단 chip 1개를 같이 봄 (중복)

    이 PR 은 chip 으로 emit 된 각 텍스트를 본문에서 enumeration prefix
    동반으로 정확 일치 검색해서 그 라인만 추가 제거. 안전성:
      - 정확 일치 substring 만 (sugg.text)
      - enumeration prefix 동반 ((n) / n) / n. / ①②③)
      - 줄 시작/끝 boundary
      - try/catch — regex 빌드 실패 시 base cleanAnswer 유지
    """

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")
        m = re.search(
            r"function\s+extractNextActionSuggestions\s*\("
            r"[\s\S]+?\n\}\n",
            cls.src,
        )
        assert m, "extractNextActionSuggestions 본문을 찾을 수 없음"
        cls.fn_body = m.group(0)

    def test_extra_strip_loop_present(self):
        # chip out[] 을 다시 순회하며 본문에서 제거하는 loop 가 존재.
        self.assertRegex(
            self.fn_body,
            r"for\s*\(\s*const\s+sugg\s+of\s+out\s*\)",
            "PR-O2b strip loop ('for sugg of out') 누락 — 본문 잔재가 "
            "tail cut 한 번으로만 처리되어 enumeration 잔재가 남음",
        )

    def test_regex_escape_helper_inline(self):
        # 매칭 텍스트의 regex meta-char 를 escape 해야 안전. inline
        # replace 로 escape 패턴이 있는지 확인.
        self.assertIn(
            r"[.*+?^${}()|[\]\\]",
            self.fn_body,
            "regex special-char escape 누락 — sugg.text 안의 '?' 같은 "
            "메타 문자가 escape 안 되면 잘못된 RegExp 빌드 → 본문 망가짐",
        )

    def test_enumeration_prefix_required(self):
        # strip 은 enumeration prefix 동반 일치만 — 본문 임의 위치
        # 우연 일치를 자르지 않게.
        self.assertRegex(
            self.fn_body,
            r"\\\(\\\\d\\\)|\\d\[\\\\\.\)\]|①②③",
            "enumeration prefix 조건 ((n)/n)/n./①②③) 누락 — "
            "조건 없는 strip 은 본문 임의 substring 을 자를 위험",
        )

    def test_try_catch_protects_base_clean_answer(self):
        # regex 빌드 실패 시 base cleanAnswer (위 cutStart strip) 가
        # 보존되어야 함. try { ... } catch (_e) { ... } 형태 확인.
        self.assertRegex(
            self.fn_body,
            r"try\s*\{[\s\S]+?\}\s*catch\s*\(\s*_e\s*\)",
            "try/catch 보호 누락 — 잘못된 regex 빌드 시 cleanAnswer "
            "전체가 망가져 답변 본문이 사라질 위험",
        )

    def test_excess_newlines_collapsed_after_strip(self):
        # strip 후 빈 줄 3 개 이상 누적되지 않게 정리하는 step.
        self.assertIn(
            r"\n{3,}",
            self.fn_body,
            "strip 후 newline 정리 step 누락 — 본문에 빈 줄 3 개 이상 "
            "누적되어 UI 가 어색함",
        )


if __name__ == "__main__":
    unittest.main()
