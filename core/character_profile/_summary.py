"""Character profile — natural-language summary + LLM prompt modifiers.

``_SummaryMixin``: the two heavy read-side methods —
``build_summary`` (16-trait → 3-line Korean prose) and
``get_prompt_modifiers`` (persona block + threshold-based directives
fed into the reasoning engine prompt).

Both are rule-based (no LLM call) so they are deterministic and fast.
``build_summary`` is a staticmethod that takes a values dict; the
admin frontend has a 1:1 mirror in JS. ``get_prompt_modifiers`` walks
the live instance state ``self._values`` plus calls
``self.build_summary``.

Split out of the monolithic ``core/character_profile.py`` in Stage C.3
so the package respects CLAUDE.md rule #5 (< 20 KB per file). The
mixin pattern keeps the external surface unchanged — callers see
``CharacterProfile.build_summary(values)`` and
``profile.get_prompt_modifiers()`` exactly as before.
"""
from __future__ import annotations

from typing import Dict, List

from ._traits import TRAITS


class _SummaryMixin:

    # ─── LLM 프롬프트 주입 ─────────────────────────────────────────
    def get_prompt_modifiers(self) -> str:
        """reasoning_engine 프롬프트에 주입할 성향 지시문.

        구성:
          1. [캐릭터 페르소나] 블록 — build_summary 결과 (P5d, W3b 추가)
          2. [응답 지시] 블록 — trait 임계값 기반 directive

        directive 규칙:
          - 0.7 이상 → 강하게 반영 (해당 trait 관련 directive 추가)
          - 0.3 이하 → 반대 방향 directive 추가
          - W3b: focus/intuitive/independent/collaborative/boldness 5개도
            directive 발화 (이전엔 누락되어 슬라이더 변경이 LLM 응답에
            영향 X 였음 — W1 §1-C 권고)
        """
        p = self._values
        lines: List[str] = []

        # ─── 0.7 이상 ─────────────────────────────────────────────
        if p.get("caution",        0.5) > 0.7:
            lines.append("확실한 정보만 포함하고 불확실한 부분은 명시하라.")
        if p.get("curiosity",      0.5) > 0.7:
            lines.append("관련된 흥미로운 주제도 함께 제시하라.")
        if p.get("analytical",     0.5) > 0.7:
            lines.append("논리적 근거와 데이터를 중심으로 분석하라.")
        if p.get("empathy",        0.5) > 0.7:
            lines.append("사용자의 감정과 맥락을 고려해서 답변하라.")
        if p.get("creativity",     0.5) > 0.7:
            lines.append("창의적이고 다양한 관점에서 접근하라.")
        if p.get("directness",     0.5) > 0.7:
            lines.append("결론을 먼저 말하고 간결하게 핵심만 전달하라.")
        if p.get("security",       0.5) > 0.7:
            lines.append("보안 위험성과 잠재적 취약점을 항상 함께 언급하라.")
        if p.get("conciseness",    0.5) > 0.7:
            lines.append("불필요한 설명을 제거하고 최대한 짧게 답하라.")
        # ─── P1 신규 trait directives ─────────────────────────────
        if p.get("optimism",       0.5) > 0.7:
            lines.append("긍정적 가능성과 기회를 강조해서 제시하라.")
        if p.get("risk_tolerance", 0.5) > 0.7:
            lines.append("리스크 있는 옵션도 검토 가치가 있다면 제안하라.")
        if p.get("patience",       0.5) > 0.7:
            lines.append("단계적이고 차분한 설명으로 답하라.")
        # ─── W3b 추가: 미반영 5 trait directives ───────────────────
        if p.get("focus",          0.5) > 0.7:
            lines.append("핵심 주제에 집중하고 곁가지 설명을 줄여라.")
        if p.get("intuitive",      0.5) > 0.7:
            lines.append("직관적 통찰과 비유로 빠르게 핵심을 전달하라.")
        if p.get("independent",    0.5) > 0.7:
            lines.append("독자적 판단으로 명확한 결론을 단정 제시하라.")
        if p.get("collaborative",  0.5) > 0.7:
            lines.append("사용자와의 합의를 통해 함께 답을 도출하는 톤을 유지하라.")
        if p.get("boldness",       0.5) > 0.7:
            lines.append("불확실해도 가장 가능성 높은 답을 적극적으로 제시하라.")

        # ─── 0.3 이하 (반대 방향) ─────────────────────────────────
        if p.get("caution",        0.5) < 0.3:
            lines.append("다양한 가능성을 열어두고 과감하게 제안하라.")
        if p.get("conciseness",    0.5) < 0.3:
            lines.append("충분한 배경 설명과 맥락을 포함하여 상세히 답하라.")
        if p.get("optimism",       0.5) < 0.3:
            lines.append("리스크와 한계를 명확히 짚고 신중한 톤으로 답하라.")
        if p.get("risk_tolerance", 0.5) < 0.3:
            lines.append("안전한 옵션을 우선 제안하라.")
        if p.get("patience",       0.5) < 0.3:
            lines.append("핵심 결론을 빠르게 전달하라.")
        if p.get("directness",     0.5) < 0.3:
            lines.append("우회적이고 부드러운 표현을 사용하라.")
        # ─── W3b 추가: 미반영 5 trait 의 low-side directives ───────
        if p.get("focus",          0.5) < 0.3:
            lines.append("관련 주제로 자유롭게 확장하고 다양한 측면을 다뤄라.")
        if p.get("intuitive",      0.5) < 0.3:
            lines.append("근거 데이터와 단계적 추론에 기반해 답하라.")
        if p.get("independent",    0.5) < 0.3:
            lines.append("여러 출처와 관점을 종합해서 답하라.")
        if p.get("collaborative",  0.5) < 0.3:
            lines.append("자신의 결론을 우선 명시한 뒤 부연하라.")
        if p.get("boldness",       0.5) < 0.3:
            lines.append("확실한 부분만 단정하고 나머지는 가능성으로 제시하라.")

        directives = " ".join(lines)

        # ─── [W3b/P5d] 캐릭터 페르소나 블록 prepend ────────────────
        # build_summary 의 3-line 자연어 요약을 system prompt 앞에 둔다 —
        # LLM 이 응답 톤/스타일/가치관을 일관되게 유지하도록 identity 정보
        # 부여. 룰 기반이라 빠르고 결정적.
        summary = self.build_summary(p)
        persona_block = (
            "[캐릭터 페르소나] "
            f"{summary['core']}. "
            f"{summary['values']}. "
            f"{summary['style']}."
        )

        if directives:
            return f"{persona_block} [응답 지시] {directives}"
        return persona_block

    # ─── 자연어 요약 (P5c, 2026-05-10) ─────────────────────────────
    # build_summary 는 16 trait 수치를 한국어 3-line 자연어 요약으로
    # 변환한다. 룰 기반(LLM 호출 X) — 결정적이고 빠르며 admin.js 의
    # 동일 함수와 1:1 미러된다.
    #
    # 반환 키:
    #   core   — Group A~D 4 쌍에서 우세한 사이드 모음
    #   values — Group E (security/creativity/empathy) 강·약 설명
    #   style  — Group F (conciseness/directness/optimism/risk/patience)
    #
    # 임계값:
    #   ≥ 0.65 → "강함" (high 라벨 채택)
    #   ≤ 0.35 → "약함" (low 라벨 채택)
    #   pair (A~D) 차이가 0.10 미만이면 "균형" 으로 간주, 핵심에서 생략.
    @staticmethod
    def build_summary(values: Dict[str, float]) -> Dict[str, str]:
        p = values or {}

        # ── 핵심 (Group A~D 우세 사이드) ────────────────────────────
        pair_dominants: List[str] = []
        pairs = [
            ("curiosity",   "focus"),
            ("caution",     "boldness"),
            ("analytical",  "intuitive"),
            ("independent", "collaborative"),
        ]
        for a, b in pairs:
            va, vb = p.get(a, 0.5), p.get(b, 0.5)
            if abs(va - vb) >= 0.10:
                tid = a if va > vb else b
                pair_dominants.append(TRAITS[tid]["label_ko"])

        if pair_dominants:
            core = "·".join(pair_dominants) + "이 두드러진 성격"
        else:
            core = "여러 성향이 균형을 이룬 성격"

        # ── 가치 (Group E) ──────────────────────────────────────────
        e_rules = [
            ("security",   "보안에 매우 민감함",   "보안의식이 약함"),
            ("creativity", "창의성이 풍부함",      "창의성은 보통 이하"),
            ("empathy",    "공감능력이 높음",      "공감 표현이 절제됨"),
        ]
        value_parts: List[str] = []
        for tid, hi, lo in e_rules:
            v = p.get(tid, 0.5)
            if v >= 0.65:
                value_parts.append(hi)
            elif v <= 0.35:
                value_parts.append(lo)
        vals = (", ".join(value_parts)
                if value_parts else "특정 가치 편향이 두드러지지 않음")

        # ── 스타일 (Group F) ────────────────────────────────────────
        f_rules = [
            ("conciseness",    "간결한",          "설명이 풍부한"),
            ("directness",     "직설적인",        "우회적인"),
            ("optimism",       "낙관적인",        "신중한 톤의"),
            ("risk_tolerance", "위험을 감수하는", "안전 우선의"),
            ("patience",       "인내심 있는",     "결론이 빠른"),
        ]
        style_parts: List[str] = []
        for tid, hi, lo in f_rules:
            v = p.get(tid, 0.5)
            if v >= 0.65:
                style_parts.append(hi)
            elif v <= 0.35:
                style_parts.append(lo)
        style = (", ".join(style_parts) + " 표현 스타일"
                 if style_parts else "균형 잡힌 표현 스타일")

        return {"core": core, "values": vals, "style": style}


__all__ = ["_SummaryMixin"]
