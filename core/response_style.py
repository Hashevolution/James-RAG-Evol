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
    # ── Answer-format contract (2026-06-04, extended 2026-06-06) ─────
    # The preset is the single source of truth for the *whole* answer
    # shape, not just the synth-layer rule_text. Three upstream layers
    # also force verbose output and must honor the resolved style:
    #   inject_character_directives — L1: the 16-trait character-profile
    #       persona/directive block (engine_memory.build_memory_context).
    #   inject_persona              — L1b: the MemoryStore persona name
    #       prefix ("당신의 이름은 JAMES입니다.") emitted by
    #       MemoryStore.get_system_prompt(). Added 2026-06-06 (cycle β
    #       Phase A) — Phase A persona-leak diagnostic measured 68-69%
    #       of terse-mode answers leaking "JAMES" / "As JAMES, I have
    #       analyzed" prefixes from this single hardcoded line, the
    #       biggest single contributor to the -0.15/-0.22 single-line
    #       primary-axis loss between the narrow and broad JAMES
    #       vanilla definitions. character_directives blocks the
    #       16-trait block but this line lives on a separate path
    #       (engine_memory.py L63 — store.get_system_prompt() return)
    #       and survived the 2026-06-04 fix. See memory
    #       feedback_engine_memory_persona_name_leak.
    #   inject_sources_header       — L3: the "[관련 자료 목록]" header
    #       prepended to context (pipeline_context.apply_post_check_…).
    # Default True/True/True = NATURAL = production byte-identical.
    # TERSE sets all three False so a single style request ("terse")
    # collapses all four layers to single-answer mode. See memory
    # feedback_response_style_hardcode_platform_defect.
    inject_character_directives: bool = True
    inject_persona:              bool = True
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
        "- ⭐ 최우선 원칙: 답의 길이/톤은 **사용자의 현재 질문**에 맞추세요. "
        "이전 대화가 분석 보고서였더라도, 새 질문이 짧은 인사 (\"안녕\", "
        "\"안녕?\", \"하이\", \"수고\", \"고마워\") 면 한두 문장으로 짧게 "
        "인사로 응대. \"(잠시 멈추고 ~)\" 같은 메타-내레이션, \"결론부터 "
        "말씀드리겠습니다\" 같은 보고서 도입부, ## 헤더, 다음 단계 제안 "
        "전부 생략. 새 질문이 정말 짧은 응대면 답도 짧은 응대.\n"
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
        "- 답변 완결성 (중요): 시작한 섹션 / 문장 / 리스트 항목은 반드시 "
        "  끝까지 마무리하세요. 콜론 ':'·하이픈 '-'·번호 '1.' 등으로 끝나는 "
        "  미완 줄로 답변을 종료하지 마세요. 길어질 것 같으면 미리 핵심을 "
        "  먼저 적고, 그 다음 자연스러운 마무리 문장 (예: \"이상이 핵심입니다.\" "
        "  또는 \"필요하면 더 자세히 풀어드릴 수 있어요.\") 으로 닫으세요.\n"
    ),
    rule_text_en=(
        "Answer composition guide:\n"
        "- ⭐ Top priority: match the **current** user message's "
        "length and tone. If the previous turn was a long analysis "
        "report but the current message is just a greeting (\"hi\", "
        "\"hello\", \"thanks\", \"ok\"), reply with a short greeting. "
        "Drop meta-narration (\"(pausing to think) ...\"), report "
        "openers (\"Let me start with the conclusion\"), ## headers, "
        "and next-step proposals when the current question is a short "
        "social reply. Short message gets a short answer.\n"
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
        "- Answer completeness (important): finish every section, "
        "  sentence, and list item you start. Do NOT end the answer "
        "  on a dangling colon ':', dash '-', or numbered prefix "
        "  '1.'. If the answer would run long, lead with the core "
        "  point, then close with a natural wrap (e.g. \"That's the "
        "  core.\" or \"Happy to expand further if useful.\").\n"
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
    # v4 (2026-06-06 cycle β #2) — answer-first with free-form evidence.
    #
    # v1 (2026-06-04): "Reason freely, end with ANSWER:" license —
    #   PM-19 e4b measured 16% compliance, 84% multi-paragraph synthesis.
    #
    # v2 (cycle β #1.5): "EXACTLY one line" + "MAXIMUM 30 words" +
    #   "no follow-up sentences" — successfully removed synthesis but
    #   over-strict. Banned the natural "answer + brief evidence" UX
    #   shape solely for measurement-side exact-match convenience.
    #
    # v3 (this cycle, intermediate): "First line ANSWER:" + "1-2 short
    #   evidence sentences" + "MAXIMUM 60 words". User caught the
    #   `MAXIMUM 60 words` and `1-2 sentences` quantitative gates as
    #   the *same* measurement-fitting pattern v2 was just rolled back
    #   for: the fixture scorer hits on entity match regardless of
    #   length, so any quantitative cap is enforcement against a
    #   ceiling that never required it.
    #
    # v4 lands the principled shape — keep the *structural* bans that
    # actually prevent the synthesis-shape regression, drop every
    # *quantitative* clamp:
    #   - First line: ANSWER: <answer>           (structural lead)
    #   - Then a brief grounded explanation if it helps   (free-form)
    #   - Avoid multi-paragraph synthesis        (structural ban)
    #   - Avoid ## headers, bullet lists, preamble before ANSWER:
    #     (structural bans)
    #   - No word count cap, no sentence count cap
    #
    # The hypothesis under v4 is that the structural bans alone are
    # what stop the PM-19 84% synthesis-shape regression. If a future
    # measurement shows long synthesis re-emerging, the next dial is
    # structural (e.g. "single short paragraph"), not quantitative —
    # quantitative caps just clip the very answer the rule asks for.
    #
    # Below comment block is retained for v2 historical context only.
    #
    # v2 (cycle β #1.5) — strict single-line via rule_text only.
    # The 2026-06-04 v1 rule_text was a "reason freely, end with ANSWER:"
    # license; the PM-19 e4b answer-shape inspection measured only 16%
    # ANSWER:-line compliance on answerable queries (4/25 each in
    # comparison/temporal/inference) — 84% produced 1500-2800 char
    # multi-paragraph synthesis with ## headers and markdown bullets
    # that the negative-list "Do NOT add ## sections" clause completely
    # failed to suppress. The "Reason freely" clause was the dominant
    # license; explicit `## headers` in the failing samples is direct
    # evidence the negative constraints were ignored. v2 flips to
    # positive format-first: "Output EXACTLY one line: ANSWER: <answer>"
    # plus a quantitative `MAXIMUM 30 words` cap.
    #
    # max_tokens stays at 8192 (NATURAL parity). An initial Phase B
    # draft tightened max_tokens to 150 (~75-90 words) to enforce the
    # 30-word rule at the decoding ceiling, but the PM-19 e4b length
    # distribution showed 10/100 answerable answers in the 200-430 char
    # range follow the legitimate "short reasoning + 'ANSWER:
    # insufficient information'" shape (~60-100 words) and would be
    # truncated mid-conclusion under a 150-token cap, losing the final
    # ANSWER: line itself. The user catch was: rule_text strengthening
    # is a natural dial, max_tokens cap is hard truncation — the second
    # raises the risk of cutting the very answer the rule_text just
    # asked for. We keep the prompt-side instruction strict and trust
    # the model not to overrun by hundreds of words; if measurement
    # later shows long synthesis still leaks past 8192 frequently, we
    # revisit with a value that bounds the *tail*, not the *body*.
    name="terse",
    max_tokens=8192,
    force_two_sections=False,
    rule_text_ko=(
        "답변 형식 (답 먼저, 자료 근거 설명):\n"
        "- 첫 줄에 'ANSWER: <답>' 형식으로 직접 답을 적으세요.\n"
        "- <답> = 개체명 (예: '샘 뱅크먼-프라이드'), 'Yes', 'No', "
        "또는 'insufficient information'\n"
        "- 그 다음 자료에 근거한 짧은 설명을 적으세요 (필요할 때만).\n"
        "- ## 헤더, 불릿 리스트, 다단락 합성, ANSWER 줄 앞 서론은 "
        "쓰지 마세요.\n"
        "- 자료에 답이 없으면 첫 줄 'ANSWER: insufficient information' "
        "만 출력하세요.\n"
    ),
    rule_text_en=(
        "Answer format (answer first, grounded explanation):\n"
        "- First line: 'ANSWER: <answer>' — give the direct answer.\n"
        "- <answer> = entity name (e.g., 'Sam Bankman-Fried'), 'Yes', "
        "'No', or 'insufficient information'\n"
        "- Then a brief grounded explanation from the context, if it "
        "helps.\n"
        "- Avoid ## headers, bullet lists, multi-paragraph synthesis, "
        "and preamble before the ANSWER: line.\n"
        "- If the context lacks the answer: output only the first line "
        "'ANSWER: insufficient information'.\n"
    ),
    # Collapse the three upstream verbose layers too — otherwise the
    # character persona (L1), the MemoryStore persona name (L1b), and
    # the sources header (L3) re-introduce the scaffolding the terse
    # rule_text (L2) just forbade.
    inject_character_directives=False,
    inject_persona=False,
    inject_sources_header=False,
)


# Detailed / verbatim preset (2026-06-26) — for explicit "상세히 / 자세히
# / 원문 / 전체 내용" requests. Unlike NATURAL (which condenses into a
# readable answer), this tells the model to REPRODUCE the relevant source
# content in full so an ingested document's tables / numbers / items
# survive instead of collapsing into a one-line summary. It is a
# format/verbosity variant (same 8192 cap + injectors as NATURAL), NOT a
# v1-style token-cut preset.
DETAILED_PRESET = StylePreset(
    name="detailed",
    max_tokens=8192,
    force_two_sections=False,
    rule_text_ko=(
        "답변 작성 가이드 (상세/원문 모드):\n"
        "- 사용자가 **상세한 내용 / 원문 그대로**를 요청했습니다. 내부 "
        "자료의 관련 부분을 **요약하지 말고 빠짐없이 그대로 재현**하세요.\n"
        "- 표가 있으면 **표 형식 그대로, 모든 행**을 옮기세요. 숫자·날짜·"
        "시간·인원·장소·항목·금액을 **하나도 생략하지 말고** 보존.\n"
        "- 압축·일반화·\"등\"으로 뭉뚱그리기 금지. 자료에 있는 구체 항목을 "
        "전부 나열하세요.\n"
        "- 자연스러운 한국어로 구조화하되 ('STEP 1', 📚/💡 라벨 금지) "
        "내용의 완전성을 최우선으로.\n"
        "- 컨텍스트에 [관련 자료 목록]이 있으면 첫 줄에 참고 파일을 명시.\n"
        "- 자료에 없는 내용은 지어내지 말고 \"제공된 자료에는 없습니다\"라고 "
        "명시하세요.\n"
        "- 완결성: 시작한 표·문장·항목은 끝까지 마무리. 미완 줄로 끝내지 "
        "마세요.\n"
    ),
    rule_text_en=(
        "Answer guide (detailed / verbatim mode):\n"
        "- The user asked for the FULL detail / the source as-is. "
        "REPRODUCE the relevant internal-source content in full — do NOT "
        "summarise.\n"
        "- Keep tables as tables (every row). Preserve every number, date, "
        "time, count, place, item, and amount — omit nothing.\n"
        "- No compressing, generalising, or \"etc.\". List every concrete "
        "item present in the source.\n"
        "- Structure as natural prose (no 'STEP 1' or 📚/💡 labels) but "
        "completeness comes first.\n"
        "- If the context has a [Source Files] list, name the files first.\n"
        "- Do not invent content not in the source; say so if it is absent.\n"
        "- Completeness: finish every table, sentence, and item you start.\n"
    ),
)


# Style id → preset registry. default (unmatched / empty) → NATURAL.
_STYLE_REGISTRY = {
    "terse": TERSE_PRESET,
    "natural": NATURAL_PRESET,
    # brief / standard keep resolving to NATURAL (v2 decision: the v1
    # token-cutting presets were rejected by user feedback). "detailed"
    # now resolves to the real DETAILED_PRESET (2026-06-26) — a
    # format/verbosity variant that reproduces source detail, NOT a
    # token-cut preset.
    "brief": NATURAL_PRESET,
    "standard": NATURAL_PRESET,
    "detailed": DETAILED_PRESET,
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
