"""Response-style — natural-flow answer prompt.

Why this module exists (v2 — 2026-05-08 redesign)
--------------------------------------------------
v1 (PR #72) tried to control answer length via three max_token presets
(brief=600, standard=1200, detailed=2000) plus a rigid 📚/💡 two-section
template. User feedback rejected the approach: cutting tokens makes
answers feel truncated, and the emoji-labelled sections feel mechanical.

What the user wants instead: a Claude-style natural answer flow —
**core answer → supporting evidence → alternative perspective / follow-up
suggestion** — composed as connected prose, with the model picking
the right length for the question.

v2 design
---------
- Single preset (`NATURAL`). The `brief` / `standard` / `detailed` ids
  still resolve to it for backward compat (so existing API consumers
  keep working) but they all behave identically.
- `max_tokens=2000` everywhere — generous, the model picks the actual
  length based on question complexity.
- `force_two_sections=False` — no rigid template. The `rule_text_*`
  block teaches the flow as guidance, not a formatting requirement.
- Rule text instructs prose composition, explicit "do NOT use 📚/💡
  labels", and "short questions get short answers, complex questions
  get the full flow".

The module-level constants (BRIEF / STANDARD / DETAILED / VALID_STYLES)
and `resolve_style()` API are preserved so the call sites in
core/reasoning/engine.py / modes.py / pipeline.py and the
QueryRequest.response_style field continue to work without churn.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


# Public preset names — kept for backward compat with existing call
# sites and the QueryRequest.response_style API field. All three now
# resolve to the same NATURAL preset (length is picked by the model,
# not by the caller).
BRIEF = "brief"
STANDARD = "standard"
DETAILED = "detailed"

VALID_STYLES = (BRIEF, STANDARD, DETAILED)


@dataclass(frozen=True)
class StylePreset:
    """Resolved style — what each call site needs to issue an LLM call.

    `name`: preset id for logging / response echo.
    `max_tokens`: hard cap passed to call_gemma. 2000 is generous; the
        model picks actual length from the prompt's flow guidance, not
        from a token budget.
    `force_two_sections`: legacy field — always False in v2. Kept on
        the dataclass so any caller still reading it gets a sane value.
    `rule_text_ko` / `rule_text_en`: the natural-flow guidance block
        injected into the answer prompt. Teaches the 핵심→근거→대안
        flow as guidance (not a rigid template) and explicitly forbids
        the old 📚/💡 emoji labels.
    """
    name:               str
    max_tokens:         int
    force_two_sections: bool
    rule_text_ko:       str
    rule_text_en:       str


# The one natural-flow preset. All public ids resolve to this.
NATURAL_PRESET = StylePreset(
    name="natural",
    max_tokens=2000,
    force_two_sections=False,
    rule_text_ko=(
        "답변 작성 가이드:\n"
        "- 자연스러운 한국어 문단으로 답하세요. 번호 매기기, 'STEP 1', "
        "'📚 자료 기반', '💡 추론' 같은 라벨은 사용하지 마세요.\n"
        "- 흐름은 다음을 따르되 강제는 아닙니다:\n"
        "  (1) 질문에 대한 핵심 답을 먼저 한 두 문장으로 직접 제시.\n"
        "  (2) 내부 자료에서 근거가 되는 부분을 자연스럽게 이어서 설명. "
        "근거가 없으면 '제공된 자료에는 직접 언급이 없습니다'라고 명시.\n"
        "  (3) 관련 시각, 한계, 또는 후속으로 물어볼 만한 내용을 짧게 덧붙이세요.\n"
        "- 짧은 질문엔 핵심 답만으로 충분합니다. 복잡한 질문일수록 (2)(3)을 채우세요.\n"
        "- 글자수 제약 없음. 내용에 맞는 자연스러운 길이로.\n"
    ),
    rule_text_en=(
        "Answer composition guide:\n"
        "- Write in natural English prose. Do NOT use numbered lists, "
        "'STEP 1' headers, or '📚 Data-based' / '💡 Reasoning' labels.\n"
        "- Follow this flow as guidance (not a rigid template):\n"
        "  (1) Direct answer to the question in one or two sentences first.\n"
        "  (2) Supporting evidence from the internal data, woven into "
        "the prose. If the data does not directly cover the question, "
        "say so explicitly.\n"
        "  (3) Briefly add a related angle, limitation, or a useful "
        "follow-up question.\n"
        "- Short questions deserve short answers. Fill in (2) and (3) "
        "only when the question warrants it.\n"
        "- No character-count limit. Pick a length that fits the content.\n"
    ),
)


def resolve_style(explicit: str = "") -> StylePreset:
    """Resolve the active style preset.

    v2: ignores `explicit` (and the `JAMES_RESPONSE_STYLE` env) — all
    inputs resolve to NATURAL_PRESET. Kept as a function so the call
    sites don't need to change. The signature also documents that
    explicit style ids are accepted (for forward compat if a future
    pack-level override resurrects the preset distinction).

    The env var is still read so an unrecognised value here doesn't
    silently differ from the v1 behavior — but since all values now
    map to NATURAL, the read is informational only.
    """
    # Read but ignore — preserves the v1 API surface for any caller
    # that introspects this function's behavior.
    _ = (explicit or "").strip().lower()
    _ = (os.getenv("JAMES_RESPONSE_STYLE", "") or "").strip().lower()
    return NATURAL_PRESET
