"""Direction 1 — TaskBudget contract tests.

Pin the heuristic surface so wiring changes (D1.B/C/D) can't drift
from the V3' measurement-derived cap tiers.
"""

from __future__ import annotations

import pytest

from core.reasoning.budget import (
    CAP_HEAVY,
    CAP_LIGHT,
    CAP_SUBSTITUTION,
    TaskBudget,
    retry_doubled,
)


# ---------------------------------------------------------------------------
# Cap-tier invariants
# ---------------------------------------------------------------------------


def test_cap_tier_ordering():
    """Caps must monotonically increase: substitution < light < heavy."""
    assert CAP_SUBSTITUTION < CAP_LIGHT < CAP_HEAVY


def test_cap_substitution_value():
    """CAP_SUBSTITUTION pinned to 200 — V3'.e substitution arm eval_count=62
    flat, leaves 3x headroom over the observed flatline."""
    assert CAP_SUBSTITUTION == 200


def test_cap_light_value():
    """CAP_LIGHT pinned to 1200 (v2, bumped from 800 on 2026-05-24).

    The v1 value (800) covered V3'.e synthesis arm (eval_count ~400-450)
    and query_rewriter (~377) but truncated reflect (natural-stop ~926)
    and verify (natural-stop ~984) in 19/20 calls each. CAP_LIGHT=1200
    gives ~20% headroom over verify (the highest measured light-tier
    natural-stop) while staying 5x above V3'.e light synth's 235."""
    assert CAP_LIGHT == 1200


def test_cap_heavy_value():
    """CAP_HEAVY pinned to 4096 — PR #399 safe default; V3'.a~d 10/10
    at this cap across all 4 cognitive stages."""
    assert CAP_HEAVY == 4096


# ---------------------------------------------------------------------------
# Substitution-pattern detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "환불 정책 그대로 알려주세요",
        "약관 원문 보여줘",
        "그대로 반환해주세요",
        "Return the exact policy text",
        "verbatim retrieval please",
        "Just copy-paste the clause",
        "Output the section as-is",
    ],
)
def test_substitution_pattern_query_rewriter(prompt: str):
    """Substitution patterns route query_rewriter to CAP_SUBSTITUTION."""
    tb = TaskBudget()
    assert tb.assess("query_rewriter", prompt) == CAP_SUBSTITUTION


@pytest.mark.parametrize(
    "prompt",
    [
        "환불 정책 그대로 알려주세요",
        "verbatim retrieval please",
    ],
)
def test_substitution_pattern_synth(prompt: str):
    """Substitution patterns also route synth to CAP_SUBSTITUTION."""
    tb = TaskBudget()
    assert tb.assess("synth", prompt) == CAP_SUBSTITUTION


@pytest.mark.parametrize(
    "stage",
    ["planner", "reflect", "verify"],
)
def test_substitution_ignored_by_cognitive_stages(stage: str):
    """Cognitive middleware stages always need synthesis; substitution
    patterns in the *user's* prompt do not relieve them from synthesizing.
    A "그대로 알려주세요" query still requires planner decomposition / reflect
    critique / verify fact-check, so these stages skip the substitution
    short-circuit and route through the light/heavy default."""
    tb = TaskBudget()
    # "환불 정책 그대로 알려주세요" has no heavy marker → light cap.
    assert tb.assess(stage, "환불 정책 그대로 알려주세요") == CAP_LIGHT


# ---------------------------------------------------------------------------
# Heavy-synthesis marker detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "한국 RAG 시장을 4단계로 분석해주세요",
        "각 옵션을 비교 평가해주세요",
        "Decompose the problem into subtasks",
        "Solve this step by step",
        "step-by-step explanation please",
        "Compare A and B across three dimensions",
        "쪼개서 풀어주세요",
        "철저히 검토해주세요",
        "구조적으로 분기 후 답변",
        "Multi-step reasoning required",
    ],
)
def test_heavy_marker_routes_to_heavy_cap(prompt: str):
    """Heavy markers escalate to CAP_HEAVY regardless of stage."""
    tb = TaskBudget()
    for stage in ("query_rewriter", "planner", "reflect", "verify", "synth"):
        assert tb.assess(stage, prompt) == CAP_HEAVY, (
            f"Stage {stage} did not escalate on heavy prompt: {prompt!r}"
        )


def test_heavy_marker_overrides_nothing_at_substitution_pattern():
    """When both substitution and heavy markers appear in the same prompt,
    the substitution short-circuit wins for serve-stages (query_rewriter,
    synth) because the user is explicitly requesting verbatim output.
    For cognitive stages (planner/reflect/verify), heavy marker applies."""
    tb = TaskBudget()
    mixed = "환불 정책 원문 그대로 알려주세요. 단계별로 분석도 포함."
    # query_rewriter and synth: substitution wins.
    assert tb.assess("query_rewriter", mixed) == CAP_SUBSTITUTION
    assert tb.assess("synth", mixed) == CAP_SUBSTITUTION
    # Cognitive stages: heavy marker applies (they need to synthesize either way).
    assert tb.assess("planner", mixed) == CAP_HEAVY
    assert tb.assess("reflect", mixed) == CAP_HEAVY
    assert tb.assess("verify", mixed) == CAP_HEAVY


# ---------------------------------------------------------------------------
# Default — light synthesis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "RAG가 무엇인가요?",
        "Tell me about ontologies",
        "What is the refund window?",
        "Quick summary of the document please",
    ],
)
def test_default_light_cap(prompt: str):
    """Prompts with neither substitution nor heavy markers default to CAP_LIGHT."""
    tb = TaskBudget()
    for stage in ("query_rewriter", "planner", "reflect", "verify", "synth"):
        assert tb.assess(stage, prompt) == CAP_LIGHT, (
            f"Stage {stage} did not return light cap on prompt: {prompt!r}"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_prompt_defaults_to_light():
    """Empty prompt is the light default — nothing to escalate."""
    tb = TaskBudget()
    assert tb.assess("synth", "") == CAP_LIGHT


def test_context_argument_currently_ignored():
    """Direction 2 (task-weight metric) will use the `context` arg; for
    Direction 1 it's reserved but unused. Pin this so D1 wiring won't
    accidentally depend on context."""
    tb = TaskBudget()
    long_context = "a long retrieval context " * 100
    # Same answer with or without context.
    assert tb.assess("synth", "What is RAG?", context="") == tb.assess(
        "synth", "What is RAG?", context=long_context
    )


def test_assess_is_stateless():
    """Two calls with the same args return the same cap.
    TaskBudget has no internal state."""
    tb = TaskBudget()
    a = tb.assess("query_rewriter", "환불 정책 그대로 알려주세요")
    b = tb.assess("query_rewriter", "환불 정책 그대로 알려주세요")
    assert a == b == CAP_SUBSTITUTION


# ---------------------------------------------------------------------------
# retry_doubled — fallback helper
# ---------------------------------------------------------------------------


def test_retry_doubled_from_substitution():
    """CAP_SUBSTITUTION (200) doubles to 400."""
    assert retry_doubled(CAP_SUBSTITUTION) == 400


def test_retry_doubled_from_light():
    """CAP_LIGHT (1200) doubles to 2400 — below ceiling (CAP_HEAVY=4096)."""
    assert retry_doubled(CAP_LIGHT) == 2400


def test_retry_doubled_caps_at_heavy():
    """Doubling CAP_HEAVY (4096) yields CAP_HEAVY again — ceiling."""
    assert retry_doubled(CAP_HEAVY) == CAP_HEAVY


def test_retry_doubled_respects_max_cap_argument():
    """Caller can lower the ceiling (e.g. for a budget-constrained run)."""
    assert retry_doubled(CAP_LIGHT, max_cap=1000) == 1000
    assert retry_doubled(CAP_SUBSTITUTION, max_cap=300) == 300


def test_retry_doubled_already_above_ceiling_returns_ceiling():
    """A caller passing in a cap above the ceiling gets clamped down."""
    assert retry_doubled(prev_cap=10_000) == CAP_HEAVY


# ---------------------------------------------------------------------------
# Module-export contract — D1.B/C/D wiring depends on these symbols.
# ---------------------------------------------------------------------------


def test_module_exports():
    """Pin the public API surface."""
    from core.reasoning import budget as m
    expected = {
        "CAP_SUBSTITUTION",
        "CAP_LIGHT",
        "CAP_HEAVY",
        "ReasoningStage",
        "TaskBudget",
        "retry_doubled",
    }
    assert set(m.__all__) == expected
