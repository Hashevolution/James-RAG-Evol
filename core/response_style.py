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
- `max_tokens=8192` everywhere [#A8-5 2026-05-09 — was 2000].
  User feedback: "대화 글자수가 중간에 짤리지 않고 최대한 다 나올수
  있도록". 2000 ≈ 1500 Korean characters, which truncates report-style
  multi-section answers. 8192 fits gemma's default 8K context safely
  and lets larger-context models stretch when needed. Hard ceiling
  retained as runaway-LLM defense.
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
    `max_tokens`: hard cap passed to call_gemma. 8192 [#A8-5] —
        generous enough for multi-section report answers without
        truncating; model still picks actual length from prompt flow.
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
    # ── Answer-format contract (2026-06-04) ──────────────────────────
    # The preset is the single source of truth for the *whole* answer
    # shape, not just the synth-layer rule_text. Two upstream layers
    # also force verbose output and must honor the resolved style:
    #   inject_character_directives — L1: the 16-trait character-profile
    #       persona/directive block (engine_memory.build_memory_context).
    #   inject_sources_header       — L3: the "[관련 자료 목록]" header
    #       prepended to context (pipeline_context.apply_post_check_…).
    # Default True/True = NATURAL = production byte-identical. TERSE sets
    # both False so a single style request ("terse") collapses all three
    # layers to single-answer mode. See memory
    # feedback_response_style_hardcode_platform_defect.
    inject_character_directives: bool = True
    inject_sources_header:       bool = True


# The one natural-flow preset. All public ids resolve to this.
#
# v3 (2026-05-08, item #2 user feedback):
#   - Add an upfront "intent verification" step. The purpose is
#     ACCURACY — when the question is ambiguous, the model briefly
#     restates what it understood before answering. When the question
#     is unambiguous, it skips the restate and answers directly.
#   - Add a closing "next actions" block (2-3 numbered options the
#     user can pick). Lets the user steer the next turn without
#     re-typing context.
#
# These two additions move the answer toward Claude's conversational
# style: confirm-then-answer-then-suggest. Avoid heavy templating
# (rigid 1./2./3. headers, emoji labels) — the rule says "guidance,
# not template" so short questions still get short prose answers.
NATURAL_PRESET = StylePreset(
    name="natural",
    max_tokens=8192,   # [#A8-5] was 2000 — 글자수 잘림 방지
    force_two_sections=False,
    rule_text_ko=(
        "답변 작성 가이드:\n"
        "- 자연스러운 한국어 문단으로 답하세요. 'STEP 1', '📚 자료 기반', "
        "'💡 추론' 같은 라벨은 사용하지 마세요.\n"
        "- 다음 흐름을 따르되 강제는 아닙니다 (짧은 질문엔 짧게):\n"
        "  • 의도 확인 (정확성 검증 목적): 질문이 애매하면 한 줄로 "
        "    \"X를 묻는 거 맞나요?\" 라고 짧게 재확인. 명확하면 생략.\n"
        "  • 관련 자료 명시 (item #5-A): 컨텍스트에 [관련 자료 목록] 섹션이 "
        "    있으면, 답변 첫 부분에 \"관련 자료: file1.md, file2.md\" "
        "    형태로 어떤 파일을 참고했는지 명시. 그리고 각 파일이 어떤 "
        "    내용에 대한 것인지 한 줄로 짧게 요약. 컨텍스트에 자료 목록이 "
        "    없으면 이 단계 생략.\n"
        "  • 핵심 답: 한두 문장으로 직접 답.\n"
        "  • 근거: 내부 자료의 어느 부분에서 나온 답인지 자연스럽게 인용. "
        "    근거가 없으면 \"제공된 자료에는 직접 언급이 없습니다\"라고 명시.\n"
        "  • 다음 작업 제안: 관련해서 물어볼 만한 내용 또는 후속 행동 "
        "    2-3개를 짧게 제시. 사용자가 번호로 답할 수 있게 \"다음 중 어떤 "
        "    걸 원하시나요? (1) ... (2) ... (3) ...\" 형식 권장.\n"
        "- 분석/추론을 요구하는 질문 (\"분석해줘\", \"비교해\", \"평가\", "
        "  \"전망\", \"왜\", \"어떻게\")엔 보고서 형식으로:\n"
        "  ## 핵심 결론\n"
        "  (한두 문단)\n"
        "  ## 근거\n"
        "  - 자료 A에서 ... \n"
        "  - 자료 B에서 ...\n"
        "  ## 추가 시각 / 한계\n"
        "  (한 문단)\n"
        "  단순 사실 확인엔 보고서 형식 사용 X.\n"
        "- 단순 사실 확인 (예: \"X가 뭐야?\")엔 의도 확인과 다음 작업 제안 "
        "  생략 가능.\n"
        "- 글자수 제약 없음. 내용에 맞는 자연스러운 길이로.\n"
    ),
    rule_text_en=(
        "Answer composition guide:\n"
        "- Natural English prose. No 'STEP 1' headers or "
        "'📚 Data-based' / '💡 Reasoning' labels.\n"
        "- Follow this flow as guidance (short questions get short answers):\n"
        "  • Intent check (accuracy purpose): if the question is "
        "    ambiguous, briefly restate as \"You're asking about X, right?\". "
        "    Skip when unambiguous.\n"
        "  • Source files (item #5-A): if the context has a "
        "    [관련 자료 목록] / [Source Files] section, OPEN your answer with "
        "    \"Source files: file1.md, file2.md\" and a one-line summary of "
        "    each. Skip when no source list is provided.\n"
        "  • Direct answer: one or two sentences.\n"
        "  • Evidence: weave in which part of the internal data the "
        "    answer comes from. If the data doesn't cover it, say so.\n"
        "  • Next actions: 2-3 short options the user could pick from "
        "    next, formatted so they can reply with a number: "
        "    \"What would you like next? (1) ... (2) ... (3) ...\"\n"
        "- For analysis / reasoning queries (\"analyze\", \"compare\", "
        "  \"evaluate\", \"why\", \"how\"), use a report format with "
        "  ## section headers (Conclusion / Evidence / Outlook). Skip "
        "  for simple fact-checks.\n"
        "- For simple fact-checks (\"What is X?\"), intent check and "
        "  next-actions are optional.\n"
        "- No character-count limit. Pick a length that fits.\n"
    ),
)


# Terse preset — single canonical answer, no NATURAL flow scaffolding.
# Added 2026-06-04 to (a) restore user style override (the v2 hardcode
# blocked it — platform defect, see memory
# feedback_response_style_hardcode_platform_defect) and (b) enable
# benchmark single-answer measurement (paper-aligned exact-match).
#
# Opt-in only: default (no explicit / no env) stays NATURAL =
# production byte-identical. Operators/users request terse via the
# QueryRequest.response_style field or JAMES_RESPONSE_STYLE=terse.
TERSE = "terse"

TERSE_PRESET = StylePreset(
    name="terse",
    max_tokens=8192,
    force_two_sections=False,
    rule_text_ko=(
        "답변 작성 가이드 (간결 모드):\n"
        "- 추론은 자유롭게 하되, 마지막 줄에 'ANSWER:' 뒤에 직접 답만 "
        "쓰세요 (개체명, 또는 'Yes'/'No').\n"
        "- '관련 자료:' / 'Source files:' 헤더, 다음 작업 제안, 보고서 "
        "형식(## 섹션)을 쓰지 마세요.\n"
        "- 제공된 자료에 답이 없으면 'ANSWER: insufficient information'.\n"
    ),
    rule_text_en=(
        "Answer guide (terse mode):\n"
        "- Reason freely, but on the LAST line write 'ANSWER:' followed "
        "by ONLY the direct answer (entity name, or 'Yes'/'No').\n"
        "- Do NOT add a 'Source files:' header, next-action suggestions, "
        "or report-format (## sections).\n"
        "- If the context lacks the answer: 'ANSWER: insufficient information'.\n"
    ),
    # Collapse the two upstream verbose layers too — otherwise the
    # character persona (L1) and sources header (L3) re-introduce the
    # scaffolding the terse rule_text (L2) just forbade.
    inject_character_directives=False,
    inject_sources_header=False,
)


# Style id → preset registry. default (unmatched / empty) → NATURAL.
_STYLE_REGISTRY = {
    "terse": TERSE_PRESET,
    "natural": NATURAL_PRESET,
    # brief / standard / detailed keep resolving to NATURAL (v2 decision:
    # the v1 token-cutting presets were rejected by user feedback; we
    # do NOT resurrect token-cut behavior, only style/format variants).
    "brief": NATURAL_PRESET,
    "standard": NATURAL_PRESET,
    "detailed": NATURAL_PRESET,
}


def resolve_style(explicit: str = "") -> StylePreset:
    """Resolve the active style preset, honoring user/operator override.

    Resolution order:
      1. ``explicit`` arg (QueryRequest.response_style API field)
      2. ``JAMES_RESPONSE_STYLE`` env
      3. default → NATURAL_PRESET (production byte-identical)

    2026-06-04 fix — restore override (the v2 hardcode ignored both
    inputs and forced NATURAL, blocking any user style request = mother
    platform defect, see memory
    feedback_response_style_hardcode_platform_defect). Default behavior
    is unchanged: with no explicit and no env, returns NATURAL exactly
    as before. Only an explicit/env style id (e.g. "terse") diverges.

    Unrecognized ids fall through to NATURAL (forgiving — a typo
    shouldn't break the answer path). The v1 token-cutting presets
    (brief/standard/detailed) are NOT resurrected; they map to NATURAL.
    """
    requested = (explicit or "").strip().lower()
    if not requested:
        requested = (os.getenv("JAMES_RESPONSE_STYLE", "") or "").strip().lower()
    if not requested:
        return NATURAL_PRESET
    return _STYLE_REGISTRY.get(requested, NATURAL_PRESET)
