"""Prompt templates + per-stage timeout/cap constants for the
reflection loop.

Extracted from the legacy single-file ``core/reasoning/reflect.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). The
template contents are byte-identical to the pre-split file; only the
location moved.

External callers (research scripts + tests) import these directly:

    from core.reasoning.reflect import (
        CRITIQUE_PROMPT_EN, REVISE_PROMPT_EN, REVISE_PROMPT_KO,
        REVISE_PROMPT_V2_EN, REVISE_PROMPT_V2_KO,
    )

The re-export façade in ``core.reasoning.reflect.__init__`` preserves
that import shape so the split is a no-op for callers.
"""
from __future__ import annotations

from core.reasoning.evidence_budget import (
    DEFAULT_EVIDENCE_CHARS,
    EVIDENCE_CHARS_ENV,
    resolve_evidence_chars,
)


# [JAMES_REASONING_BACKEND wiring 2026-05-18] resolved at import time.
from core.reasoning.backends import get_default_backend_id as _get_default_backend
DEFAULT_BACKEND_ID = _get_default_backend()
# Critique + revise timeouts — kept tight so reflection doesn't blow
# past the 30s timing target in core/reasoning/engine.py.
DEFAULT_CRITIQUE_TIMEOUT_S = 30.0
DEFAULT_REVISE_TIMEOUT_S = 45.0
# gemma4:e4b consumes ~500 hidden reasoning tokens before the first
# visible output on short structured prompts; cap below that floor
# → deterministic empty response (model burns the budget without
# surfacing any byte). Revise stage already sits above the floor.
DEFAULT_CRITIQUE_MAX_TOKENS = 4096
DEFAULT_REVISE_MAX_TOKENS = 1024
# Reject runaway revised answers that ballooned far past the draft —
# usually a sign the LLM added boilerplate apologies rather than fixing
# substance. 2.5× draft length is a generous bound.
MAX_REVISE_RATIO = 2.5


# ─── Critique evidence budget (2026-09-26) ───────────────────────
#
# Why this is tied to the SYNTH variable and not a number of its own.
#
# The 2026-09-24 cognitive-stages contrast traced a defect: critique was
# formatted with {query} and {draft} only, so it judged facts against
# the model's own training data. A fact newer than the model — the
# normal case for an internal knowledge base — read as a hallucination
# and revise deleted it (report §4.1, arm A Q14: a correct, grounded
# "GPT-6 announced 2026-04-15" became "no information has been made
# public").
#
# The fix hands critique the evidence. That creates a second trap: the
# draft is written from `JAMES_SYNTH_CONTEXT_CHARS` (default 8000)
# characters of context (core/reasoning/engine_synth.py:107). Give the
# critique LESS than synth had and a fact supported only by the unseen
# tail reads as unsupported — the same defect, one layer down. So the
# budget is read from the same variable rather than re-declared, and
# the two cannot drift apart. Truncation, when it happens, is stated
# inside the prompt (see `build_critique_prompt`) rather than left as a
# silent absence.
#
# Related: the 1000-char synth cap that caused over-abstention
# (memory `feedback_synth_context_1000_truncation_rootcause`) is the
# same failure shape — a prompt that cannot see its evidence.
# 2026-09-27 — moved to core/reasoning/evidence_budget.py when verify's
# fact check turned out to have the same defect (context[:2000] against
# synth's 8000). Two stages reading one number, not two copies of it.
DEFAULT_CRITIQUE_CONTEXT_CHARS = DEFAULT_EVIDENCE_CHARS
_CONTEXT_CHARS_ENV = EVIDENCE_CHARS_ENV


def resolve_critique_context_chars() -> int:
    """Evidence characters the critique may see. See the block above."""
    return resolve_evidence_chars()


_TRUNCATED_KO = (
    "\n\n[...자료가 길어 이후 부분은 생략됨. 생략된 부분에 근거가 있을 수 "
    "있으므로, 여기 보이지 않는다는 이유만으로 '자료 미근거' 라고 하지 마라.]"
)
_TRUNCATED_EN = (
    "\n\n[...evidence truncated here. Support may exist in the omitted "
    "part, so do NOT call a claim unsupported merely because you cannot "
    "see it above.]"
)


def build_critique_prompt(query: str, draft: str, context: str = "",
                          *, is_ko: bool = False) -> str:
    """The critique prompt for this call.

    With evidence, facts are judged against the evidence. **Without
    evidence the factual dimension is withdrawn entirely** — a reviewer
    that cannot see what the answer was based on is not in a position
    to call any fact wrong, and letting it try is what broke Q14.
    """
    if not (context or "").strip():
        tmpl = CRITIQUE_PROMPT_KO if is_ko else CRITIQUE_PROMPT_EN
        return tmpl.format(query=query, draft=draft)

    limit = resolve_critique_context_chars()
    shown = context[:limit]
    if len(context) > limit:
        shown += _TRUNCATED_KO if is_ko else _TRUNCATED_EN
    tmpl = (CRITIQUE_PROMPT_GROUNDED_KO if is_ko
            else CRITIQUE_PROMPT_GROUNDED_EN)
    return tmpl.format(query=query, draft=draft, context=shown)


# ─── Critique, WITH evidence (preferred path) ────────────────────

CRITIQUE_PROMPT_GROUNDED_KO = (
    "아래 답변을 비판적으로 검토하라. 검토 목적은 사용자가 받기 전에 "
    "결함을 잡아내는 것이다.\n\n"
    "[원본 질문]\n{query}\n\n"
    "[근거 자료]\n{context}\n\n"
    "[답변 초안]\n{draft}\n\n"
    "사실 판정 규칙 (가장 중요):\n"
    "- 사실의 옳고 틀림은 **오직 위 [근거 자료] 만을 기준으로** 판정하라.\n"
    "- [근거 자료] 가 뒷받침하는 내용은 네가 아는 것과 다르더라도 "
    "**오류가 아니다.** 자료는 네 학습 시점 이후의 최신 정보일 수 있다.\n"
    "- 네 사전지식에 없다는 이유로 '환각' · '사실 오류' 라고 하지 마라. "
    "특히 날짜·수치·제품명이 낯설다는 것은 근거가 되지 않는다.\n"
    "- [근거 자료] 가 뒷받침하지 않는 주장만 '자료 미근거' 로 지적하라.\n"
    "- [근거 자료] 가 **질문이 묻는 대상**에 대해 답하지 않는다면, "
    "'자료에 없음' · '정보 부족' 이라고 한 초안은 **올바른 답이다.** "
    "자료에 같은 종류의 사실이 **다른 대상**에 대해 있다는 이유로 그 초안을 "
    "틀렸다고 하지 마라. (예: 질문은 A 사의 CEO 인데 자료에는 B 사의 CEO 만 "
    "있는 경우 — B 사 CEO 이름을 답으로 만드는 것이 환각이다.)\n\n"
    "다음 3 가지 측면만 점검 (각 1-2 줄):\n"
    "1. 자료 미근거 / 내부 모순 — [근거 자료] 가 뒷받침하지 않는 주장, "
    "또는 답변 안에서 서로 어긋나는 진술\n"
    "2. 누락된 핵심 — 질문에 직접 답하지 않은 부분, 또는 [근거 자료] 가 "
    "**질문의 대상에 대해** 담고 있는데 답변에서 빠진 핵심 정보\n"
    "3. 모호함 — 사용자가 오해할 가능성이 있는 표현\n\n"
    "문제가 없으면 'NO_ISSUES' 한 줄만 출력.\n\n"
    "검토:"
)

CRITIQUE_PROMPT_GROUNDED_EN = (
    "Critically review the draft answer below. The goal is to catch "
    "defects before the user sees it.\n\n"
    "[Original question]\n{query}\n\n"
    "[Evidence]\n{context}\n\n"
    "[Draft answer]\n{draft}\n\n"
    "Rules for judging facts (most important):\n"
    "- Judge whether a fact is right or wrong **against the [Evidence] "
    "above, and nothing else.**\n"
    "- A claim the [Evidence] supports is **NOT an error**, even when it "
    "contradicts what you know. The evidence may be newer than your "
    "training data.\n"
    "- Do NOT call something a 'hallucination' or a 'factual error' "
    "because it is absent from your own knowledge. An unfamiliar date, "
    "figure or product name is not grounds for that claim.\n"
    "- Flag a claim as 'unsupported' only when the [Evidence] does not "
    "support it.\n"
    "- If the [Evidence] does not answer **the subject the question asks "
    "about**, then a draft saying the information is missing is **the "
    "correct answer**. Do NOT mark it wrong because the evidence holds "
    "the same kind of fact about a DIFFERENT subject. (Example: the "
    "question asks for company A's CEO and the evidence names only "
    "company B's CEO — supplying B's CEO would be the hallucination.)\n\n"
    "Check only these 3 dimensions (1-2 lines each):\n"
    "1. Unsupported / Contradiction — claims the [Evidence] does not "
    "support, or statements inconsistent within the answer\n"
    "2. Missing core — parts of the question not answered, or key "
    "information the [Evidence] carries **about the question's subject** "
    "but the answer omits\n"
    "3. Ambiguity — phrasings the user might misread\n\n"
    "If nothing is wrong, output 'NO_ISSUES' on one line.\n\n"
    "Review:"
)


# ─── Critique, WITHOUT evidence (fallback) ───────────────────────
#
# Reachable for any caller that has no context to pass. The factual
# dimension is deliberately absent: this reviewer cannot see what the
# answer was based on, so a "wrong fact" verdict from here can only be
# a comparison against training data — the Q14 defect. It checks the
# things that ARE visible in the draft alone.

CRITIQUE_PROMPT_KO = (
    "아래 답변을 비판적으로 검토하라. 검토 목적은 사용자가 받기 전에 "
    "결함을 잡아내는 것이다.\n\n"
    "[원본 질문]\n{query}\n\n"
    "[답변 초안]\n{draft}\n\n"
    "판정 제한 (중요): 근거 자료가 주어지지 않았다. 따라서 답변에 담긴 "
    "사실의 진위는 판정할 수 없다. **사실 오류·환각 지적을 하지 마라.** "
    "네 사전지식과 다르다는 이유로 틀렸다고 해서는 안 된다 — 이 답변은 "
    "네 학습 시점 이후의 자료에 근거했을 수 있다.\n\n"
    "다음 3 가지 측면만 점검 (각 1-2 줄):\n"
    "1. 내부 모순 — 답변 안에서 서로 어긋나는 진술 (외부 사실과의 "
    "불일치가 아니라, 답변 내부의 자기모순만)\n"
    "2. 누락된 핵심 — 질문에 직접 답하지 않은 부분\n"
    "3. 모호함 — 사용자가 오해할 가능성이 있는 표현\n\n"
    "문제가 없으면 'NO_ISSUES' 한 줄만 출력.\n\n"
    "검토:"
)

CRITIQUE_PROMPT_EN = (
    "Critically review the draft answer below. The goal is to catch "
    "defects before the user sees it.\n\n"
    "[Original question]\n{query}\n\n"
    "[Draft answer]\n{draft}\n\n"
    "Limit on what you may judge (important): no evidence was provided, "
    "so you cannot establish whether the facts in this answer are true. "
    "**Do NOT raise factual errors or hallucinations.** Do not call "
    "something wrong because it differs from your own knowledge — this "
    "answer may rest on evidence newer than your training data.\n\n"
    "Check only these 3 dimensions (1-2 lines each):\n"
    "1. Contradiction inside the answer — statements inconsistent with "
    "each other (self-contradiction only, NOT disagreement with facts "
    "as you know them)\n"
    "2. Missing core — parts of the question not answered\n"
    "3. Ambiguity — phrasings the user might misread\n\n"
    "If nothing is wrong, output 'NO_ISSUES' on one line.\n\n"
    "Review:"
)


REVISE_PROMPT_KO = (
    "아래 검토를 반영해서 답변을 개정하라.\n\n"
    "[원본 질문]\n{query}\n\n"
    "[답변 초안]\n{draft}\n\n"
    "[검토 결과]\n{critique}\n\n"
    "개정 규칙:\n"
    "- 검토에서 지적된 문제만 수정. 잘 된 부분은 그대로.\n"
    "- 의미를 보존하고 새 사실을 만들지 마라.\n"
    "- **사용자는 검토 과정을 본 적이 없다.** 검토에 대해 코멘트하지 "
    "마라. 변경사항을 설명하지 마라.\n"
    "- 절대 금지: '제시해주신', '지적해주신', '검토 결과', "
    "'이러한 결함', '재작성', '개정된 답변', '[핵심 전략]' "
    "같은 메타-내러티브로 시작하지 마라.\n"
    "- 응답은 사용자의 원본 질문에 바로 답하는 본문이어야 한다 "
    "(원본 질문이 'NVIDIA가 뭐야?' 라면 응답은 'NVIDIA는...' 또는 "
    "비슷한 답변 첫 문장으로 시작).\n\n"
    "개정된 답변:"
)

# ─── REVISE_PROMPT v2 (Option B, 2026-06-05 §23) ─────────────────
#
# Why v2 exists. The v1 REVISE_PROMPT_* templates inline the full
# critique text into the prompt the model sees ("[Review]\n{critique}").
# That exposure structurally invites a meta-format response: the model
# reads a review and naturally answers in revision-speak ("Here is my
# revised answer...", "## Revised Answer", "This revision focuses
# on..."). PM-13 (e4b cap=8000 + per-query session, 2026-06-05) showed
# 29/100 answers in this meta mode even with the forbidden-openings
# list + post-process stripper — the meta-format space is open-ended,
# patches are infinite.
#
# v2 closes the meta space at the source: the revise call no longer
# sees the critique text. The critique pass still runs (full audit
# trail preserved in the trace store) and its result is compressed to
# a one-word issue tag (factual_error / missing_core / ambiguity /
# general). The model receives only the draft + query + tag and is
# framed as writing a fresh answer, not as revising. The meta-format
# vocabulary the v1 prompt invites simply has no place to land.
#
# Opt-in via JAMES_REVISE_PROMPT_V2=1 (default OFF = byte-identical to
# v1 path). Promoted to default after PM-16 validation on the same
# fixture that surfaced the meta-mode regression (cap=8000 + per-query
# session). The post-process stripper remains active as a safety net
# under both paths.
REVISE_PROMPT_V2_EN = (
    "Write the best possible answer to the question below. An earlier "
    "attempt had a quality flag (type: {issue_type}) — improve on it.\n\n"
    "[Question]\n{query}\n\n"
    "[Earlier attempt]\n{draft}\n\n"
    "Output rules:\n"
    "- Output ONLY the answer. No preface, no commentary, no description "
    "of what changed.\n"
    "- Start directly with the answer to the question (e.g. for "
    "'what is NVIDIA?' → 'NVIDIA is...'; for a yes/no question → "
    "'Yes,' or 'No,').\n"
    "- Do NOT start with: 'Revised', 'This revision', 'This revised', "
    "'Here is', 'Below is', 'Based on', '## Revised Answer', "
    "'**Revised Answer**', '## Revised Draft', '### Step 1:', "
    "'### 1. Analysis', '### 1. Summary', 'Hello, I am JAMES'.\n"
    "- Preserve facts from the earlier attempt; do not invent new ones.\n\n"
    "Answer:"
)

REVISE_PROMPT_V2_KO = (
    "아래 질문에 가능한 한 가장 좋은 답을 작성하라. 이전 시도에 품질 "
    "플래그가 있었음 (유형: {issue_type}) — 개선해서 답하라.\n\n"
    "[질문]\n{query}\n\n"
    "[이전 시도]\n{draft}\n\n"
    "출력 규칙:\n"
    "- 오직 답변만 출력. 머리말·해설·변경사항 설명 금지.\n"
    "- 사용자의 질문에 바로 답하는 문장으로 시작 (예: 'NVIDIA가 뭐야?' "
    "→ 'NVIDIA는...'; yes/no 질문 → '예,' 또는 '아니오,').\n"
    "- 다음 시작어 금지: '개정', '재작성', '검토 반영', '제시해주신', "
    "'지적해주신', '## 개정된 답변', '## 수정된 답변', '### 1단계:', "
    "'### 1. 분석', '### 1. 요약', '[핵심 전략]'.\n"
    "- 이전 시도의 사실을 보존하고 새 사실을 만들지 마라.\n\n"
    "답변:"
)


REVISE_PROMPT_EN = (
    "Revise the draft to address the review.\n\n"
    "[Original question]\n{query}\n\n"
    "[Draft answer]\n{draft}\n\n"
    "[Review]\n{critique}\n\n"
    "Revision rules:\n"
    "- Fix only the issues the review flagged. Leave good parts as-is.\n"
    "- Preserve meaning; don't invent new facts.\n"
    "- **The user never saw the review.** Do NOT comment on the review. "
    "Do NOT explain what you changed.\n"
    "- Forbidden openings: 'Based on the review', 'I have revised', "
    "'Here is the revised version', 'Thank you for the feedback', "
    "'The critique correctly pointed out', '[Core strategy]', "
    "'## Revised Answer', '**Revised Answer:**', '## Revised Draft', "
    "'This revision focuses on...', 'This revision addresses...', "
    "'This revised answer...', 'Hello, I am JAMES. I will follow the plan'.\n"
    "- Do NOT open with a heading (`## Revised Answer`, `### Step 1:`, "
    "`### 1. Analysis`, `### 1. Summary`) — the user wants the answer "
    "itself, not a report structure.\n\n"
    "Revised answer:"
)


__all__ = [
    "DEFAULT_BACKEND_ID",
    "DEFAULT_CRITIQUE_TIMEOUT_S",
    "DEFAULT_REVISE_TIMEOUT_S",
    "DEFAULT_CRITIQUE_MAX_TOKENS",
    "DEFAULT_REVISE_MAX_TOKENS",
    "MAX_REVISE_RATIO",
    "CRITIQUE_PROMPT_KO",
    "CRITIQUE_PROMPT_EN",
    "CRITIQUE_PROMPT_GROUNDED_KO",
    "CRITIQUE_PROMPT_GROUNDED_EN",
    "DEFAULT_CRITIQUE_CONTEXT_CHARS",
    "resolve_critique_context_chars",
    "build_critique_prompt",
    "REVISE_PROMPT_KO",
    "REVISE_PROMPT_EN",
    "REVISE_PROMPT_V2_EN",
    "REVISE_PROMPT_V2_KO",
]
