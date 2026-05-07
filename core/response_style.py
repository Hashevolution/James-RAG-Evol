"""Response-style presets — controls answer length, structure, and tone
across all LLM call sites in the reasoning pipeline.

Why this module exists
----------------------
Pre-this-PR every LLM call hard-coded `max_tokens=2000` and the
`_generate_answer` system prompt forced a two-section structure
(📚 자료 기반 + 💡 추론). End-result: every answer was long and
verbose, even for trivial chat. Operators reported "답변이 너무 길고
복잡" (issue raised in 2026-05-08 user-feedback session).

Three presets, one resolver
---------------------------

`brief`     max_tokens=600,  no forced section split — direct answer.
`standard`  max_tokens=1200, two sections but compact (DEFAULT).
`detailed`  max_tokens=2000, full two-section with extensive reasoning
            (preserves pre-this-PR behavior as opt-in).

Resolution order (highest precedence first):
  1. explicit `style=` kwarg from caller
  2. `JAMES_RESPONSE_STYLE` env var
  3. fallback to `standard`

Why a separate module rather than inlining
- Three call sites need it: `engine._generate_answer`, `modes.handle_chat`,
  `pipeline.run_retrieval_pipeline` web fallback. A shared resolver keeps
  the precedence rule in one place — adding a fourth call site doesn't
  duplicate the env-var read.
- The structural rule (📚/💡 prompt block) lives next to the token cap
  it's paired with, so changing one without the other isn't possible.

This is mother-platform behavior. No domain-specific style logic lives
here — domain packs may eventually override via Axis 3 / v0.3 plugin
contract, but that's out of scope for v0.2.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


# Public preset names — use these strings everywhere, not literals.
BRIEF = "brief"
STANDARD = "standard"
DETAILED = "detailed"

VALID_STYLES = (BRIEF, STANDARD, DETAILED)


@dataclass(frozen=True)
class StylePreset:
    """Resolved style — what each call site needs to issue an LLM call.

    `name`: preset id for logging / response echo.
    `max_tokens`: hard cap passed to call_gemma.
    `force_two_sections`: when True, the 📚/💡 structural rule is
        added to the prompt; when False, the model gets a single-shot
        prompt with no structural template.
    `rule_text_ko` / `rule_text_en`: the literal rule block injected
        into the prompt when `force_two_sections=True`.
    """
    name:               str
    max_tokens:         int
    force_two_sections: bool
    rule_text_ko:       str
    rule_text_en:       str


# Concrete presets — keep them grouped here so a reviewer changing one
# notices the others. The two-section rules differ by language; the
# brief rule is intentionally empty (no template at all).
_PRESETS: dict[str, StylePreset] = {
    BRIEF: StylePreset(
        name=BRIEF,
        max_tokens=600,
        force_two_sections=False,
        rule_text_ko="간결하게 핵심만 한 문단으로 답변하세요.\n",
        rule_text_en="Answer concisely in one short paragraph.\n",
    ),
    STANDARD: StylePreset(
        name=STANDARD,
        max_tokens=1200,
        force_two_sections=True,
        rule_text_ko=(
            "답변 구조 (간결하게):\n"
            "📚 자료 기반: 내부 자료 사실만. 없으면 '관련 자료 없음'\n"
            "💡 추론: 자료를 연결한 짧은 분석 (3-4문장)\n"
        ),
        rule_text_en=(
            "Answer structure (concise):\n"
            "📚 Data-based: facts from internal data only, or 'No relevant data'\n"
            "💡 Reasoning: short analysis tying data together (3-4 sentences)\n"
        ),
    ),
    DETAILED: StylePreset(
        name=DETAILED,
        max_tokens=2000,
        force_two_sections=True,
        rule_text_ko=(
            "답변 구조:\n"
            "📚 자료 기반: (내부 자료 사실만. 없으면 '관련 자료 없음')\n"
            "💡 추론: (자료와 지식을 연결한 자유 분석)\n"
            "규칙: 두 섹션 모두 작성. 자료 기반은 확인된 사실만.\n"
        ),
        rule_text_en=(
            "Answer structure:\n"
            "📚 Data-based: (facts from internal data only, or 'No relevant data')\n"
            "💡 Reasoning: (free analysis using data + knowledge)\n"
            "Rules: Both sections required. Data-based = confirmed facts only.\n"
        ),
    ),
}


def resolve_style(explicit: str = "") -> StylePreset:
    """Resolve the active style preset for an LLM call.

    Args:
      explicit: caller-provided style id (from API request kwarg).
                Empty string / None / unknown values fall through to
                the env var, then the default.

    Resolution order: explicit kwarg → JAMES_RESPONSE_STYLE env →
    `standard` default. Unknown values at any layer fall through to
    the next layer rather than raising — this matches the rest of the
    reasoning pipeline's defensive defaults (a typo in a config never
    crashes a live request).
    """
    candidate = (explicit or "").strip().lower()
    if candidate in _PRESETS:
        return _PRESETS[candidate]
    env = (os.getenv("JAMES_RESPONSE_STYLE", "") or "").strip().lower()
    if env in _PRESETS:
        return _PRESETS[env]
    return _PRESETS[STANDARD]
