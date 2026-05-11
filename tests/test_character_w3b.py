"""[W3b 2026-05-10, W1 진단 §1-C] character correlation 강화.

W1 진단 결과 4가지 문제 fix:
  1. damping=0.3 → 0.6 (사용자 체감 ripple 강화)
  2. CORRELATIONS 15 → 28+ edges (incoming 보강)
  3. prompt 미반영 5 trait (focus/intuitive/independent/collaborative/
     boldness) directive 추가 — 슬라이더가 LLM 응답에 반영되도록
  4. P5d: build_summary 결과를 [캐릭터 페르소나] 블록으로 prompt prepend

Run:
    python -m unittest tests.test_character_w3b
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.character_profile import (
    CORRELATIONS, CharacterProfile, _RIPPLE_DAMPING,
)


def _fresh() -> CharacterProfile:
    """DB I/O 없는 격리된 프로필 — 테스트 간 상태 격리용."""
    with mock.patch.object(CharacterProfile, "_load", lambda self: None):
        p = CharacterProfile()
    p._save = lambda: None  # type: ignore
    return p


def _force(p: CharacterProfile, **kwargs):
    """직접 dict 쓰기 — set_trait 의 ripple 우회 (단일 trait 격리 테스트용)."""
    for k, v in kwargs.items():
        p._values[k] = v


# ─── 1. Damping 강화 ───────────────────────────────────────────────
class DampingTests(unittest.TestCase):
    def test_damping_increased_to_0_6(self):
        # W1 진단: 0.3 으로는 ripple 변화량 < 0.05 라 사용자 눈에 안 보임.
        # W3b 권고: 0.6 (또는 trait별 가중치). 여기서는 0.6 채택.
        self.assertGreaterEqual(
            _RIPPLE_DAMPING, 0.5,
            f"damping {_RIPPLE_DAMPING} 너무 약함 — 사용자 체감 ripple "
            "≥ 0.05 보장하려면 ≥ 0.5 (W1 §1-C)",
        )

    def test_damping_under_one(self):
        # 1.0 이상은 cascade 폭주 위험 — 0.7 정도가 상한.
        self.assertLess(_RIPPLE_DAMPING, 0.8,
                        "damping 0.8+ 은 짝(1.0) 영향력에 근접 — 별개의 "
                        "독립 trait 가 짝처럼 동작하게 됨")

    def test_visible_ripple_with_new_damping(self):
        # 실제 ripple 이 사용자 눈에 보이는 0.05 이상 변화를 만드는지 확인.
        p = _fresh()
        old_rt = p._values["risk_tolerance"]
        # boldness → risk_tolerance (+0.5). delta=0.5 → nudge=0.5*0.5*0.6=0.15
        p.set_trait("boldness", 0.8)
        nudge = abs(p._values["risk_tolerance"] - old_rt)
        self.assertGreaterEqual(
            nudge, 0.05,
            f"실제 nudge {nudge:.3f} < 0.05 — 사용자가 변화를 체감 못함",
        )


# ─── 2. Edges 확장 + 미반영 trait incoming 보강 ────────────────────
class EdgeExpansionTests(unittest.TestCase):
    def test_total_edges_expanded(self):
        # W1 권고: 15 → 30~40. 이 PR 은 28 edges (점진적 확장).
        self.assertGreaterEqual(
            len(CORRELATIONS), 25,
            f"edges 수 {len(CORRELATIONS)} — W1 §1-C 권고 30+ 달성 "
            "권장 (최소 25 이상은 되어야 sparse 비판 해소)",
        )

    def test_focus_has_incoming(self):
        # P1 미반영 5 trait 의 incoming 확인 — 슬라이더 변화에
        # 자동 따라가도록.
        incoming = [c for c in CORRELATIONS if c[1] == "focus"]
        self.assertGreater(
            len(incoming), 0,
            "focus 가 incoming edge 없음 — 다른 trait 변화에 따라가지 못함",
        )

    def test_intuitive_has_incoming(self):
        incoming = [c for c in CORRELATIONS if c[1] == "intuitive"]
        self.assertGreater(len(incoming), 0)

    def test_independent_has_incoming(self):
        incoming = [c for c in CORRELATIONS if c[1] == "independent"]
        self.assertGreater(len(incoming), 0)

    def test_collaborative_has_incoming(self):
        incoming = [c for c in CORRELATIONS if c[1] == "collaborative"]
        self.assertGreater(len(incoming), 0)

    def test_boldness_has_incoming(self):
        incoming = [c for c in CORRELATIONS if c[1] == "boldness"]
        self.assertGreater(len(incoming), 0)

    def test_no_self_loops(self):
        # 자기 자신을 가리키는 edge 는 의미 없음.
        for src, tgt, w in CORRELATIONS:
            self.assertNotEqual(src, tgt, f"self-loop: {src} → {tgt}")

    def test_weights_in_valid_range(self):
        for src, tgt, w in CORRELATIONS:
            self.assertGreaterEqual(w, -1.0, f"{src}→{tgt} weight 범위 X")
            self.assertLessEqual(w, 1.0, f"{src}→{tgt} weight 범위 X")
            self.assertNotEqual(w, 0.0, f"{src}→{tgt} weight 0 — 의미 없는 edge")


# ─── 3. Prompt directives — 미반영 5 trait 발화 ────────────────────
class MissingTraitDirectivesTests(unittest.TestCase):
    """W1 §1-C: focus/intuitive/independent/collaborative/boldness 가
    이전엔 prompt directive 없었음 → 슬라이더 끝까지 올려도 LLM 응답
    무영향. 이 PR 에서 high/low 양쪽 directive 추가."""

    def _modifier_with(self, **traits) -> str:
        p = _fresh()
        _force(p, **traits)
        return p.get_prompt_modifiers()

    # ── high side (≥ 0.7) ───────────────────────────────────────
    def test_high_focus_emits_directive(self):
        out = self._modifier_with(focus=0.9)
        self.assertIn("핵심 주제에 집중", out)

    def test_high_intuitive_emits_directive(self):
        out = self._modifier_with(intuitive=0.9)
        # "직관" 키워드만 — 한국어 정확한 어휘는 미세조정 가능.
        self.assertIn("직관", out)

    def test_high_independent_emits_directive(self):
        out = self._modifier_with(independent=0.9)
        self.assertIn("독자적", out)

    def test_high_collaborative_emits_directive(self):
        out = self._modifier_with(collaborative=0.9)
        self.assertIn("합의", out)

    def test_high_boldness_emits_directive(self):
        out = self._modifier_with(boldness=0.9)
        self.assertIn("적극", out)

    # ── low side (≤ 0.3) — 슬라이더 양 끝 모두 살아있게 ────────
    def test_low_focus_emits_directive(self):
        out = self._modifier_with(focus=0.1)
        # "확장" 또는 "다양한 측면"
        self.assertTrue("확장" in out or "다양한" in out,
                        f"low focus directive 누락: {out}")

    def test_low_intuitive_emits_directive(self):
        out = self._modifier_with(intuitive=0.1)
        self.assertIn("근거", out)

    def test_low_independent_emits_directive(self):
        out = self._modifier_with(independent=0.1)
        self.assertIn("종합", out)

    def test_low_collaborative_emits_directive(self):
        out = self._modifier_with(collaborative=0.1)
        # "결론을 우선 명시" 또는 비슷한
        self.assertIn("결론", out)

    def test_low_boldness_emits_directive(self):
        out = self._modifier_with(boldness=0.1)
        self.assertIn("가능성", out)


# ─── 4. P5d: 캐릭터 페르소나 블록 prepend ──────────────────────────
class PersonaBlockTests(unittest.TestCase):
    """build_summary 결과가 prompt 앞에 [캐릭터 페르소나] 블록으로 합성."""

    def test_default_includes_persona_block(self):
        p = _fresh()
        out = p.get_prompt_modifiers()
        self.assertIn("[캐릭터 페르소나]", out,
                      "P5d 페르소나 블록 헤더가 없음")

    def test_persona_block_contains_summary_fields(self):
        # 기본값: build_summary 가 "신중함·분석력이 두드러진 성격" 등
        # 반환 → 그 텍스트가 prompt 안에 나타나야.
        p = _fresh()
        out = p.get_prompt_modifiers()
        # 기본 trait 값 (caution=0.7, analytical=0.6) 으로 해당 라벨 출력 기대.
        self.assertIn("신중함", out)
        self.assertIn("분석력", out)

    def test_directive_block_separated_from_persona(self):
        # 둘 다 있을 때 [응답 지시] 헤더로 분리.
        p = _fresh()
        _force(p, caution=0.9)   # high → directive 발화
        out = p.get_prompt_modifiers()
        self.assertIn("[캐릭터 페르소나]", out)
        self.assertIn("[응답 지시]", out)
        # 페르소나가 directive 보다 앞에 와야.
        self.assertLess(
            out.index("[캐릭터 페르소나]"),
            out.index("[응답 지시]"),
        )

    def test_no_directive_no_directive_header(self):
        # 모든 trait 가 중간값(0.5) 이면 directive 0개 → 헤더 미발화.
        p = _fresh()
        for tid in p._values:
            p._values[tid] = 0.5
        out = p.get_prompt_modifiers()
        self.assertIn("[캐릭터 페르소나]", out)
        self.assertNotIn("[응답 지시]", out)


# ─── 5. 통합 — 전체 ripple 시나리오 ─────────────────────────────────
class IntegrationTests(unittest.TestCase):
    def test_focus_responds_to_analytical_change(self):
        # W3b 핵심 효과: analytical → focus (+0.40, damping 0.6)
        # delta=0.5 → nudge = 0.5 * 0.4 * 0.6 = 0.12 (사용자 체감 가능).
        p = _fresh()
        old_focus = p._values["focus"]
        # default: analytical=0.6 → 0.95 면 delta=0.35
        p.set_trait("analytical", 0.95)
        # 짝(intuitive) flip 도 일어남 (analytical 짝). focus 는 ripple 로.
        new_focus = p._values["focus"]
        self.assertGreater(
            new_focus, old_focus,
            "analytical 상승 시 focus 도 상승해야 (W3b incoming edge)",
        )
        # nudge ≥ 0.05 (visible)
        self.assertGreaterEqual(new_focus - old_focus, 0.05)

    def test_high_extreme_yields_persona_plus_directives(self):
        # 극단 caution + analytical 조합 → 페르소나 + directive 양쪽 발화.
        p = _fresh()
        _force(p, caution=0.95, analytical=0.95, security=0.95)
        out = p.get_prompt_modifiers()
        self.assertIn("[캐릭터 페르소나]", out)
        self.assertIn("[응답 지시]", out)
        self.assertIn("확실한 정보만", out)
        self.assertIn("논리적 근거", out)


if __name__ == "__main__":
    unittest.main()
