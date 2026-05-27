"""v0.4 live verify fix #6 (2026-05-26) — meta-narration detector tests.

Pins the heuristic + post-process logic added to
`core.reasoning.reflect` so the revise stage never serves the user a
preamble that comments on the critique they never saw.

Background. The 2026-05-26 A3.1 live verify of v0.4.0-alpha.3 captured
a `gemma4:e4b` revision output for a `what is NVIDIA?` query that
opened with:

    제시해주신 검토 결과와 분석은 매우 날카롭고 정확합니다. 초안의
    전문성은 최고 수준이지만, ... 이러한 결함을 완벽하게 보완하여,
    ... [핵심 전략] 1. 톤 조정: ... 2. 구조화: ...

    ***

    🚀 NVIDIA란 무엇인가? ...

The REVISE_PROMPT explicitly forbids this kind of meta-narrative, but
the model occasionally produces it anyway. The fix is two-layer:

  1. Stronger REVISE_PROMPT_KO + EN directives (raises the prior).
  2. Post-process detector that recognises the meta opening + strips
     to the first paragraph separator, falling back to draft when no
     separator is found.

These tests pin layer 2 — the detector + stripper. Layer 1 (prompt
text) is covered by a separate source-grep test below.
"""
from __future__ import annotations

import inspect

import pytest

from core.reasoning.reflect import (
    REVISE_PROMPT_EN,
    REVISE_PROMPT_KO,
    _looks_like_meta_narration,
    _strip_meta_narration,
)


# ─── Detector — _looks_like_meta_narration ────────────────────────


@pytest.mark.parametrize("text", [
    "제시해주신 검토 결과와 분석은 매우 날카롭고 정확합니다.",
    "지적해주신 부분을 모두 반영했습니다.",
    "검토 결과를 반영하여 답변을 다시 작성했습니다.",
    "검토를 반영해서 다음과 같이 개정했습니다.",
    "이러한 결함을 완벽하게 보완하여 답변을 제시합니다.",
    "이러한 문제점을 해결하기 위해 다음과 같이 수정합니다.",
    "개정된 답변 (Revised Answer)",
    "개정 답변 — NVIDIA는 ...",
    "재작성한 답변은 다음과 같습니다.",
    "[핵심 전략] 1. 톤 조정 2. 구조화 ...",
    "Based on the review, here is the revised answer.",
    "Based on your critique, I have updated the draft.",
    "Here is my revised version of the answer.",
    "Here is the revised answer addressing your concerns.",
    "I've revised the answer to fix the issues you noted.",
    "I have rewritten the response per your feedback.",
    "Below is the revised draft.",
    "Thank you for the feedback. Here is the revision.",
    "Thank you for the critique — updated answer follows.",
    "[Core strategy] tone adjustment + structure",
])
def test_detector_flags_known_meta_openings(text):
    assert _looks_like_meta_narration(text), (
        f"detector missed meta-narration opening: {text!r}"
    )


@pytest.mark.parametrize("text", [
    "NVIDIA는 병렬 컴퓨팅 분야의 선도적인 반도체 기업입니다.",
    "NVIDIA is a semiconductor company that pioneered parallel computing.",
    "엔비디아(NVIDIA)는 1993년 미국 캘리포니아주에서 설립되었습니다.",
    "Palantir는 데이터 분석 플랫폼을 제공하는 회사입니다.",
    "경제학이란 자원의 효율적 배분을 연구하는 학문입니다.",
    "Economics studies how societies allocate scarce resources.",
    # Edge — answer that happens to contain "검토" but not as opening
    "이 보고서는 다음 검토를 통해 작성되었습니다: ...",  # 보고서 talks about review process — answer-shaped
    "",
    "   ",
])
def test_detector_skips_normal_answers(text):
    assert not _looks_like_meta_narration(text), (
        f"detector false-positive on normal answer: {text!r}"
    )


# ─── Stripper — _strip_meta_narration ────────────────────────────


def test_strip_returns_unchanged_when_no_meta():
    """No meta opening → text passes through verbatim."""
    text = (
        "NVIDIA는 병렬 컴퓨팅 분야의 선도적인 반도체 기업입니다. "
        "AI / 자율주행 / 데이터센터 등 현대 첨단 산업의 모든 혁신을 "
        "가능하게 하는 근본적인 엔진 역할을 합니다. CUDA 생태계가 "
        "엔비디아의 진정한 경쟁력입니다."
    )
    assert _strip_meta_narration(text) == text


def test_strip_returns_body_after_separator():
    """Meta opening + ``***`` separator → body returned."""
    body = (
        "🚀 NVIDIA란 무엇인가? (What is NVIDIA?)\n"
        "결론부터 말씀드리자면, 엔비디아는 단순한 반도체 회사를 넘어, "
        "'병렬 컴퓨팅(Parallel Computing)' 이라는 패러다임을 바꾼 핵심 "
        "기술 인프라 기업입니다. 엔비디아의 본질은 '어려운 문제를 "
        "해결하는 컴퓨팅 파워'를 판매하는 것입니다."
    )
    text = (
        "제시해주신 검토 결과와 분석은 매우 날카롭고 정확합니다. "
        "초안의 전문성은 최고 수준이지만, 일반적인 질문에 대한 첫 "
        "응답으로는 정보 과부하라는 결함이 있었습니다.\n\n"
        "[핵심 전략]\n"
        "1. 톤 조정: 과장된 표현을 제거\n"
        "2. 구조화: 정보를 3단계로 분리\n\n"
        "***\n\n"
        f"{body}"
    )
    cleaned = _strip_meta_narration(text)
    assert cleaned, "stripper returned empty when body exists"
    assert cleaned == body, (
        "stripper should return body verbatim after the separator"
    )
    assert "제시해주신" not in cleaned
    assert "[핵심 전략]" not in cleaned


def test_strip_accepts_dash_and_equal_separators():
    """Both ``---`` / ``===`` / ``***`` (3+ chars) count as separators."""
    # Body must clear the 100-char sanity floor in _strip_meta_narration.
    body = (
        "엔비디아는 1993년 설립된 미국 캘리포니아 주의 반도체 기업입니다. "
        "AI / 자율주행 / 데이터센터 등 현대 첨단 산업의 모든 혁신을 "
        "가능하게 하는 근본적인 컴퓨팅 인프라 역할을 합니다."
    )
    assert len(body) >= 100, (
        f"test body too short ({len(body)} chars) — adjust before testing"
    )
    for sep in ("---", "----", "===", "*****"):
        text = (
            "검토 결과를 반영하여 답변을 개정했습니다.\n\n"
            f"{sep}\n\n"
            f"{body}"
        )
        cleaned = _strip_meta_narration(text)
        assert cleaned == body, (
            f"separator {sep!r} not recognised — stripper returned "
            f"{cleaned[:80]!r}"
        )


def test_strip_falls_back_to_empty_when_no_separator():
    """Meta opening but no separator → empty (caller falls to draft)."""
    text = (
        "제시해주신 검토 결과를 모두 반영하여 다음과 같이 개정했습니다. "
        "엔비디아는 반도체 회사입니다." * 3
    )
    cleaned = _strip_meta_narration(text)
    assert cleaned == "", (
        "stripper should return empty so caller falls back to draft "
        "when no paragraph separator is present"
    )


def test_strip_falls_back_when_body_too_short():
    """Separator exists but body is too short → empty (sanity floor)."""
    text = (
        "검토 결과를 반영하여 답변을 다시 작성했습니다.\n\n"
        "***\n\n"
        "NVIDIA는 회사다."  # well under 100 chars
    )
    cleaned = _strip_meta_narration(text)
    assert cleaned == "", (
        "stripper should reject sub-100-char bodies as too thin"
    )


# ─── Source-grep: REVISE_PROMPT directives strengthened ──────────


def test_revise_prompt_ko_forbids_meta_phrases_explicitly():
    """The Korean revise prompt must enumerate forbidden meta openings
    so the model has the prior even before post-process kicks in."""
    src = REVISE_PROMPT_KO
    # The detector's KO patterns target these phrases — the prompt
    # must explicitly forbid the same ones.
    for phrase in ("제시해주신", "검토 결과", "개정된 답변"):
        assert phrase in src, (
            f"REVISE_PROMPT_KO should explicitly forbid {phrase!r} "
            f"so the model is primed before the post-process detector"
        )


def test_revise_prompt_en_forbids_meta_phrases_explicitly():
    src = REVISE_PROMPT_EN
    for phrase in ("Based on", "I have revised", "Here is"):
        assert phrase in src, (
            f"REVISE_PROMPT_EN should explicitly forbid {phrase!r}"
        )


def test_revise_prompts_mention_direct_answer_requirement():
    """Both prompts must make explicit that the response is the
    user-facing answer to the original question, not a critique echo."""
    assert ("원본 질문" in REVISE_PROMPT_KO
            or "사용자" in REVISE_PROMPT_KO)
    assert ("user" in REVISE_PROMPT_EN.lower()
            or "original question" in REVISE_PROMPT_EN.lower())


# ─── Integration smoke — the live-verify fixture ─────────────────


def test_live_verify_nvidia_fixture_stripped_correctly():
    """End-to-end on the actual 2026-05-26 NVIDIA query output:
    meta-narrative preamble + [핵심 전략] block + *** separator +
    real answer body. Stripper must return the body cleanly."""
    fixture = (
        "제시해주신 검토 결과와 분석은 매우 날카롭고 정확합니다. "
        "초안의 전문성은 최고 수준이지만, 일반적인 질문에 대한 첫 "
        "응답으로는 정보 과부하(Information Overload)와 과도한 "
        "마케팅 톤이라는 치명적인 UX 결함이 있었습니다.\n\n"
        "이러한 결함을 완벽하게 보완하여, 전문성은 유지하되, "
        "구조적으로는 간결하고, 비전공자도 이해할 수 있는 비유를 "
        "통해 접근성을 높인 개정본을 제시합니다.\n\n"
        "💡 개정된 답변 (Revised Answer)\n\n"
        "[핵심 전략]\n"
        "1. 톤 조정: 과장된 표현(\"황제\")을 제거하고, 객관적이고 "
        "학술적인 톤으로 변경했습니다.\n"
        "2. 구조화: 정보를 3단계로 명확히 분리하고, 가장 중요한 "
        "개념(CUDA)을 핵심 설명에 녹여 넣었습니다.\n"
        "3. 접근성 강화: CPU와 GPU의 차이를 비유(Analogy)를 사용하여 "
        "설명하여 이해도를 극대화했습니다.\n"
        "4. 정보 과부하 해소: 보안 위험성, 경쟁사 분석 등 깊이 있는 "
        "내용은 별도의 [심층 분석] 섹션으로 분리하여, 사용자가 원하는 "
        "깊이에 따라 선택적으로 읽을 수 있게 했습니다.\n\n"
        "***\n\n"
        "🚀 NVIDIA란 무엇인가? (What is NVIDIA?)\n\n"
        "결론부터 말씀드리자면, 엔비디아는 단순한 반도체 회사를 넘어, "
        "'병렬 컴퓨팅(Parallel Computing)' 이라는 패러다임을 바꾼 핵심 "
        "기술 인프라 기업입니다."
    )
    cleaned = _strip_meta_narration(fixture)
    assert cleaned, "fixture must produce a non-empty body after strip"
    assert cleaned.startswith("🚀 NVIDIA"), (
        "stripper should land exactly on the real answer header — "
        f"got first 80 chars: {cleaned[:80]!r}"
    )
    # Meta phrases must be gone
    for forbidden in ("제시해주신", "검토 결과", "[핵심 전략]",
                      "개정된 답변", "이러한 결함"):
        assert forbidden not in cleaned, (
            f"stripped body still contains forbidden meta phrase: {forbidden!r}"
        )


# ─── Module surface check ────────────────────────────────────────


def test_reflect_exposes_strip_helpers():
    """The two helpers must be importable for downstream callers
    (and for these tests)."""
    from core.reasoning import reflect as m
    src = inspect.getsource(m)
    assert "def _strip_meta_narration" in src
    assert "def _looks_like_meta_narration" in src
