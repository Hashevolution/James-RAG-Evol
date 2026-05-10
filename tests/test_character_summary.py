"""[P5c, 2026-05-10] Character summary — 자연어 3-line 요약.

build_summary(values) 가 16 trait dict 를 핵심/가치/스타일 3 라인으로
변환하는 룰을 검증한다.

User context:
  P5b (영향력 패널 자연어화) 후속. trait 수치만으로는 "이 캐릭터가
  어떤 성격인지" 한눈에 와닿지 않아 자연어 요약 카드 추가.

규칙:
  ≥ 0.65 → high 라벨 채택
  ≤ 0.35 → low 라벨 채택
  Group A~D pair: 차이 < 0.10 이면 "균형" 으로 간주, core 에서 생략

Run:
    python -m unittest tests.test_character_summary
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.character_profile import TRAITS, CharacterProfile


def _defaults() -> dict:
    return {tid: meta["default"] for tid, meta in TRAITS.items()}


class SummaryShapeTests(unittest.TestCase):
    """반환 객체 모양 검증."""

    def test_returns_three_keys(self):
        out = CharacterProfile.build_summary(_defaults())
        self.assertEqual(set(out.keys()), {"core", "values", "style"})
        for v in out.values():
            self.assertIsInstance(v, str)
            self.assertTrue(v.strip(), "summary 라인은 비어있으면 안 됨")

    def test_empty_dict_uses_defaults(self):
        # 부분 dict (혹은 빈 dict) 로 호출해도 폴백(0.5)으로 동작.
        out = CharacterProfile.build_summary({})
        self.assertEqual(set(out.keys()), {"core", "values", "style"})

    def test_none_input_safe(self):
        # API path 에서 None 이 흘러들어와도 죽지 않음.
        out = CharacterProfile.build_summary(None)  # type: ignore[arg-type]
        self.assertEqual(set(out.keys()), {"core", "values", "style"})


class CoreLineTests(unittest.TestCase):
    """핵심 (Group A~D 우세 사이드)."""

    def test_default_yields_balanced_message(self):
        # 기본값: A=0.5/0.5, B=0.7/0.3, C=0.6/0.4, D=0.5/0.5
        # B(신중함)·C(분석력)만 우세, A·D 는 균형.
        out = CharacterProfile.build_summary(_defaults())
        self.assertIn("신중함", out["core"])
        self.assertIn("분석력", out["core"])
        self.assertNotIn("탐구심", out["core"])
        self.assertNotIn("집중력", out["core"])
        self.assertIn("두드러진", out["core"])

    def test_all_balanced_falls_back(self):
        v = {tid: 0.5 for tid in TRAITS}
        out = CharacterProfile.build_summary(v)
        self.assertIn("균형", out["core"])

    def test_strong_bias_picks_dominant_side(self):
        v = _defaults()
        v["curiosity"], v["focus"] = 0.85, 0.15
        v["boldness"], v["caution"] = 0.80, 0.20
        out = CharacterProfile.build_summary(v)
        self.assertIn("탐구심", out["core"])
        self.assertIn("과감함", out["core"])
        self.assertNotIn("집중력", out["core"])
        self.assertNotIn("신중함", out["core"])

    def test_threshold_diff_below_0_10_is_balanced(self):
        # 0.55 vs 0.45 → diff 0.10, edge case 포함.
        # 0.54 vs 0.46 → diff 0.08, 균형으로 간주되어 core 에서 제외되어야.
        v = _defaults()
        v["independent"], v["collaborative"] = 0.54, 0.46
        out = CharacterProfile.build_summary(v)
        self.assertNotIn("독립성", out["core"])
        self.assertNotIn("협력성", out["core"])


class ValuesLineTests(unittest.TestCase):
    """가치 (Group E: security/creativity/empathy)."""

    def test_default_security_high(self):
        # 기본 security = 0.9 → high
        out = CharacterProfile.build_summary(_defaults())
        self.assertIn("보안", out["values"])

    def test_low_creativity_uses_low_label(self):
        v = _defaults()
        v["creativity"] = 0.20
        out = CharacterProfile.build_summary(v)
        self.assertIn("창의성", out["values"])
        self.assertIn("보통 이하", out["values"])

    def test_neutral_band_omitted(self):
        # 0.5 는 high (≥0.65) 도 low (≤0.35) 도 아님 → 생략.
        v = {tid: 0.5 for tid in TRAITS}
        out = CharacterProfile.build_summary(v)
        # security/creativity/empathy 어느 것도 라벨 없어야 함 → 폴백.
        self.assertIn("두드러지지 않", out["values"])


class StyleLineTests(unittest.TestCase):
    """스타일 (Group F: conciseness/directness/optimism/risk/patience)."""

    def test_default_falls_back(self):
        # 기본값 모두 0.5±0.1 안 → 어떤 스타일 라벨도 안 채택.
        out = CharacterProfile.build_summary(_defaults())
        self.assertIn("균형", out["style"])

    def test_high_conciseness_directness(self):
        v = _defaults()
        v["conciseness"] = 0.80
        v["directness"] = 0.75
        out = CharacterProfile.build_summary(v)
        self.assertIn("간결한", out["style"])
        self.assertIn("직설적인", out["style"])
        self.assertIn("표현 스타일", out["style"])

    def test_low_patience_uses_low_label(self):
        v = _defaults()
        v["patience"] = 0.20
        out = CharacterProfile.build_summary(v)
        self.assertIn("결론이 빠른", out["style"])

    def test_high_and_low_traits_combined(self):
        v = _defaults()
        v["conciseness"] = 0.85   # high → 간결한
        v["optimism"]    = 0.20   # low  → 신중한 톤의
        out = CharacterProfile.build_summary(v)
        self.assertIn("간결한", out["style"])
        self.assertIn("신중한 톤의", out["style"])


class DeterminismTests(unittest.TestCase):
    """동일 입력 → 동일 출력 (LLM 호출 없는 룰 기반 보장)."""

    def test_repeated_calls_match(self):
        v = _defaults()
        a = CharacterProfile.build_summary(v)
        b = CharacterProfile.build_summary(v)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
