"""Reflection loop — Cognitive Layer Phase 2 PR-5.

ARCHITECTURE.md §5.7.1: "Reflection Engine — draft → self_critique →
revised per subtask". Wraps an already-generated answer with a
critique + revise pass to surface contradictions, missing evidence,
and policy-relevant errors before the answer reaches the user.

Posture: opt-in by default. JAMES_ENABLE_REFLECT=1 enables. Each
invocation costs **two extra LLM round-trips** (critique + revise),
roughly doubling the answer-stage latency. Operators choose when the
quality gain justifies the cost.

Routes through the Backend registry (Phase 0 L0) — default
``ollama_local`` matches the rest of v0.3.0's local-first profile. A
future Claude CLI swap is a constructor arg with no other changes:

    ReflectionLoop(backend_id="claude_code_cli").reflect(...)

Two trace rows emitted per successful pass (Phase 0 L1 contract via
emit_trace_step):

    stage="reflect" applied_rule="reasoning.reflect.critique"
    stage="reflect" applied_rule="reasoning.reflect.revised"

Failure rows (critique returned error string / revised failed / etc.)
land with ``error`` non-empty and ``blocked=1``. The caller always gets
SOMETHING back — either the revised text or the original draft.

Wiring (pipeline_synth.py): after generate_answer determines the final
answer, optionally route through reflect() before returning.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional

from core.reasoning.budget import (
    TaskBudget,
    adaptive_budget_enabled,
    complete_with_retry,
)
from core.reasoning.trace_schema import (
    TraceStep,
    compute_inputs_hash,
    emit_trace_step,
    truncate_summary,
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


# v0.4 live verify fix #6 (2026-05-26): meta-narrative detector +
# stripper. Even with the REVISE_PROMPT directives explicitly
# forbidding meta-text, Gemma 4 occasionally opens the revision with
# the model commenting on the critique it just received ("제시해주신
# 검토 결과... 매우 날카롭고 정확합니다... 이러한 결함을 완벽하게
# 보완하여... [핵심 전략]..."). The user never saw the critique,
# so this preamble is pure noise that pushes the actual answer below
# the fold. Live-verified on the 2026-05-26 NVIDIA query.
#
# Strategy:
#   1. If revised_text head matches any meta-narrative pattern AND
#   2. a paragraph-separator line ("***" / "---") exists later, return
#      the body AFTER the separator (that's where the LLM resumed the
#      real answer in observed cases). Else
#   3. Fall back to the draft — safer than serving meta-text.
#
# Patterns are conservative; they target phrases that only appear when
# the model is reflecting on the critique, not in regular answers.
_META_NARRATIVE_PATTERNS = (
    # Korean meta-narrative openings observed in production. `\S*` slot
    # absorbs the connecting particles between the verb roots (검토 +
    # 결과를 + 반영 / 검토 + 를 + 바탕) without anchoring to a specific
    # particle form.
    r'^\s*제시\s*해주신',
    r'^\s*지적\s*해주신',
    r'^\s*검토\s*\S*\s*(반영|바탕|읽고|반영하여)',
    r'^\s*이러한\s+(결함|문제|지적)',
    r'^\s*개정\s*된?\s+(답변|버전)',
    r'^\s*재작성',
    r'^\s*\[?핵심\s+전략\]?',
    # English meta-narrative openings
    r'^\s*Based\s+on\s+(the|your)\s+(review|critique|feedback)',
    r'^\s*Here\s+is\s+(my|the)\s+revised',
    r'^\s*I(\'ve|\s+have)\s+(revised|rewritten|updated)',
    r'^\s*Below\s+is\s+the\s+revised',
    r'^\s*Thank\s+you\s+for\s+the\s+(feedback|review|critique)',
    r'^\s*\[?Core\s+strategy\]?',
)


def _looks_like_meta_narration(text: str) -> bool:
    """Return True when `text` opens with a meta-narrative pattern."""
    import re
    head = text[:300]
    for pat in _META_NARRATIVE_PATTERNS:
        if re.search(pat, head, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def _strip_meta_narration(revised: str) -> str:
    """If `revised` opens with meta-narrative, return the body after
    the first paragraph separator (``***`` / ``---`` / ``===`` on its
    own line). Returns empty string when no separator is found OR the
    extracted body is too short to be a real answer — caller falls
    back to draft on empty.
    """
    if not _looks_like_meta_narration(revised):
        return revised
    import re
    sep_match = re.search(
        r'^\s*([*\-=]{3,})\s*$', revised, re.MULTILINE,
    )
    if not sep_match:
        return ""
    body = revised[sep_match.end():].strip()
    # Sanity floor — body must be substantive, not just a heading.
    if len(body) < 100:
        return ""
    return body


CRITIQUE_PROMPT_KO = (
    "아래 답변을 비판적으로 검토하라. 검토 목적은 사용자가 받기 전에 "
    "결함을 잡아내는 것이다.\n\n"
    "[원본 질문]\n{query}\n\n"
    "[답변 초안]\n{draft}\n\n"
    "다음 3 가지 측면만 점검 (각 1-2 줄):\n"
    "1. 모순/사실 오류 — 답변 안에서 서로 어긋나는 부분이나 명백히 틀린 사실\n"
    "2. 누락된 핵심 — 질문에 직접 답하지 않은 부분 또는 빠진 핵심 정보\n"
    "3. 모호함 — 사용자가 오해할 가능성이 있는 표현\n\n"
    "문제가 없으면 'NO_ISSUES' 한 줄만 출력.\n\n"
    "검토:"
)

CRITIQUE_PROMPT_EN = (
    "Critically review the draft answer below. The goal is to catch "
    "defects before the user sees it.\n\n"
    "[Original question]\n{query}\n\n"
    "[Draft answer]\n{draft}\n\n"
    "Check only these 3 dimensions (1-2 lines each):\n"
    "1. Contradiction / factual error — anything inconsistent within "
    "the answer or clearly wrong\n"
    "2. Missing core — parts of the question not answered, or key "
    "information omitted\n"
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
    "'The critique correctly pointed out', '[Core strategy]'.\n"
    "- The response must directly answer the user's original question "
    "(if the question is 'what is NVIDIA?', the response starts with "
    "'NVIDIA is...' or a similar answer sentence).\n\n"
    "Revised answer:"
)


def _enabled() -> bool:
    return os.environ.get("JAMES_ENABLE_REFLECT") == "1"


# v0.4 Sprint 1 #2 — unified language detection (see core/i18n.py).
# Replaces the legacy ≥ 20% Korean-char threshold with a dominant-
# script comparison that agrees with engine_synth on mixed queries.
from core.i18n import is_korean as _is_korean  # noqa: F401


def _no_issues(critique_text: str) -> bool:
    """Critique signalled the draft is fine — skip revision."""
    if not critique_text:
        return True
    head = critique_text.strip().splitlines()[0] if critique_text.strip() else ""
    return head.strip().upper().startswith("NO_ISSUES")


class ReflectionLoop:
    """Stateless wrapper around a Backend; the Backend itself caches
    the underlying LLM client across calls so successive reflections
    on the same backend share connection state.
    """

    def __init__(
        self,
        backend_id: str = DEFAULT_BACKEND_ID,
        *,
        critique_timeout: float = DEFAULT_CRITIQUE_TIMEOUT_S,
        revise_timeout: float = DEFAULT_REVISE_TIMEOUT_S,
        critique_max_tokens: Optional[int] = None,
        revise_max_tokens: Optional[int] = None,
        budget: Optional[TaskBudget] = None,
    ) -> None:
        """Construct a ReflectionLoop.

        ``critique_max_tokens`` / ``revise_max_tokens`` behaviour
        (D1 wiring, v0.4 Sprint 3 #7b — mirrors planner / query_rewriter):

          • int — fixed cap (per-stage baseline).
          • ``None`` (default) — runtime decision:
              - ``JAMES_ADAPTIVE_BUDGET=1`` → both stages share
                ``TaskBudget.assess("reflect", query)``.
              - flag off → fall back to ``DEFAULT_CRITIQUE_MAX_TOKENS=4096``
                / ``DEFAULT_REVISE_MAX_TOKENS=1024`` — byte-identical
                to pre-#7b behaviour.

        Default-off invariant: ``ReflectionLoop()`` with no kwargs and
        no env opt-in must hit the same caps as before this PR.
        """
        self._backend_id = backend_id
        self._critique_timeout = critique_timeout
        self._revise_timeout = revise_timeout
        self._critique_max_tokens = critique_max_tokens
        self._revise_max_tokens = revise_max_tokens
        self._budget = budget if budget is not None else TaskBudget()

    def reflect(
        self,
        query: str,
        draft: str,
        *,
        user_role: str = "system",
        force: bool = False,
    ) -> str:
        """Run critique → (optional) revise and return the final text.

        Always returns SOMETHING — either the revised answer or the
        original draft. Never raises.

        Skips (returns draft unchanged) when:
          * the env opt-in flag is not set (and ``force`` is False)
          * draft is empty or short (< 30 chars — nothing meaningful
            to critique)
          * backend lookup fails
          * critique returns an error or empty text
          * critique says 'NO_ISSUES' (no revision needed)
          * revise returns an error / empty text
          * revised answer balloons past ``MAX_REVISE_RATIO × draft length``
        """
        if not draft or len(draft.strip()) < 30:
            return draft
        if not force and not _enabled():
            return draft

        is_ko = _is_korean(query) or _is_korean(draft)
        crit_tmpl = CRITIQUE_PROMPT_KO if is_ko else CRITIQUE_PROMPT_EN
        rev_tmpl = REVISE_PROMPT_KO if is_ko else REVISE_PROMPT_EN

        # v0.4 Sprint 3 #7b — D1 cap resolution per sub-stage. Both
        # critique and revise share `assess("reflect", query)` when
        # D1 is active so a heavy task escalates both stages at once
        # (and a light task gives both the same lower cap). assess
        # is fed the user query — not the wrapped CRITIQUE_PROMPT_*
        # / REVISE_PROMPT_* templates which carry heavy markers
        # ("분석" / "review" etc.) as part of the instruction and
        # would otherwise force every reflection call to CAP_HEAVY.
        adaptive_on = adaptive_budget_enabled()
        if adaptive_on and (
            self._critique_max_tokens is None or self._revise_max_tokens is None
        ):
            _adaptive_cap = self._budget.assess("reflect", query)
        else:
            _adaptive_cap = None

        if self._critique_max_tokens is not None:
            crit_cap = self._critique_max_tokens
        elif adaptive_on:
            crit_cap = _adaptive_cap
        else:
            crit_cap = DEFAULT_CRITIQUE_MAX_TOKENS

        if self._revise_max_tokens is not None:
            rev_cap = self._revise_max_tokens
        elif adaptive_on:
            rev_cap = _adaptive_cap
        else:
            rev_cap = DEFAULT_REVISE_MAX_TOKENS

        _budget_for_router = _adaptive_cap if adaptive_on else None

        # D5.C.2.c — flag-gated backend resolution. With D1 active for
        # reflect (when both flags ON) `budget_signal` carries the
        # adaptive cap so router rules 1 / 4 fire on the correct
        # signal. Under D1 flag-off `_budget_for_router` is None →
        # unchanged from pre-#7b. Single backend serves both critique
        # + revise calls below.
        try:
            from core.reasoning.backends import get_backend
            from core.reasoning.router import emit_route_event, resolve_backend

            # Critique prompt template is enough for routing — the
            # actual prompts (critique then revise) hit the same backend.
            router_prompt = crit_tmpl
            backend_id = resolve_backend(
                "reflect",
                router_prompt,
                budget_signal=_budget_for_router,
                fallback_backend_id=self._backend_id,
            )
            backend = get_backend(backend_id)
        except Exception:
            return draft

        emit_route_event(
            "reflect",
            router_prompt,
            backend_id,
            budget_signal=_budget_for_router,
            reason="auto" if _budget_for_router is not None else "fallback",
        )

        # ── critique pass ────────────────────────────────────
        critique_prompt = crit_tmpl.format(query=query, draft=draft)
        critique_text, critique_err = self._call(
            backend,
            critique_prompt,
            timeout=self._critique_timeout,
            max_tokens=crit_cap,
            applied_rule="reasoning.reflect.critique",
            user_role=user_role,
        )
        if critique_err or not critique_text:
            return draft
        if _no_issues(critique_text):
            return draft

        # ── revise pass ──────────────────────────────────────
        revise_prompt = rev_tmpl.format(
            query=query, draft=draft, critique=critique_text
        )
        revised_text, revised_err = self._call(
            backend,
            revise_prompt,
            timeout=self._revise_timeout,
            max_tokens=rev_cap,
            applied_rule="reasoning.reflect.revised",
            user_role=user_role,
        )
        if revised_err or not revised_text:
            return draft

        # Runaway-revision guard — if the revised text balloons past
        # MAX_REVISE_RATIO × draft length, the LLM probably elaborated
        # instead of fixing. Keep the draft.
        if len(revised_text) > len(draft) * MAX_REVISE_RATIO:
            return draft

        # v0.4 live verify fix #6 (2026-05-26): meta-narrative guard.
        # Even with the REVISE_PROMPT directives forbidding meta-text,
        # Gemma 4 occasionally opens the revision with commentary on
        # the critique. `_strip_meta_narration` returns:
        #   - revised_text unchanged if no meta pattern detected
        #   - body after the first paragraph separator if both the
        #     meta pattern AND a separator exist
        #   - empty string when meta pattern matched but no separator
        #     was found → fall back to draft (safer than serving the
        #     meta-narrative as the user-facing answer).
        cleaned = _strip_meta_narration(revised_text)
        if not cleaned:
            return draft
        return cleaned

    def _call(
        self,
        backend,
        prompt: str,
        *,
        timeout: float,
        max_tokens: int,
        applied_rule: str,
        user_role: str,
    ) -> tuple[str, str]:
        """One backend round-trip + one TraceStep emission.

        Returns ``(text, error)``. ``error`` non-empty means the caller
        should fall back. Even on failure, an audit row lands (with
        ``error`` set + ``blocked=1``) so the replay tool sees the
        attempt.
        """
        # v0.4 Sprint 3 #7b — D6 retry wiring. When `max_tokens` is below
        # CAP_HEAVY (D1 active + light task) and the model truncates at
        # the cap, retry once with the doubled cap. No-op at the ceiling
        # — pre-#7b behaviour preserved under flag-off.
        # `stage="reflect"` is the audit-row tag complete_with_retry
        # emits via `reason:retry` (D6 PR #487).
        t0 = time.time()
        try:
            from core.reasoning.think_policy import think_for_stage
            result = complete_with_retry(
                backend,
                prompt,
                cap=max_tokens,
                timeout=timeout,
                stage="reflect",
                think=think_for_stage("reflect"),
            )
        except Exception as e:
            latency_ms = int((time.time() - t0) * 1000)
            err = f"{type(e).__name__}: {str(e)[:200]}"
            self._emit(
                applied_rule=applied_rule,
                prompt=prompt,
                text="",
                latency_ms=latency_ms,
                error=err,
                user_role=user_role,
            )
            return ("", err)

        latency_ms = int((time.time() - t0) * 1000)
        text = getattr(result, "text", "") or ""
        err = getattr(result, "error", "") or ""

        self._emit(
            applied_rule=applied_rule,
            prompt=prompt,
            text=text,
            latency_ms=latency_ms,
            error=err,
            user_role=user_role,
        )
        return (text, err)

    def _emit(
        self,
        *,
        applied_rule: str,
        prompt: str,
        text: str,
        latency_ms: int,
        error: str,
        user_role: str,
    ) -> None:
        extras = {}
        try:
            from core.observability import get_trace_id
            tid = get_trace_id()
            if tid:
                extras["trace_id"] = tid
        except Exception:
            pass
        try:
            emit_trace_step(
                TraceStep(
                    stage="reflect",
                    backend_id=self._backend_id,
                    parent_step_id="",
                    inputs_hash=compute_inputs_hash(prompt),
                    output_summary=truncate_summary(text),
                    applied_rule=applied_rule,
                    latency_ms=latency_ms,
                    error=error,
                ),
                user_role=user_role,
                extras=extras or None,
            )
        except Exception:
            # Reflection trace emission is best-effort — never block the
            # answer flow if audit_log is unavailable.
            pass

        # Cognitive Phase 3 PR-9b — session-scoped episodic mirror.
        try:
            from core.memory.episodic import record_event as _rec
            _rec(
                stage="reflect",
                summary=text,
                extras={"applied_rule": applied_rule,
                        "latency_ms": latency_ms, "error": error},
            )
        except Exception:
            pass


# ─── module-level singleton ────────────────────────────────────────
_SINGLETON: Optional[ReflectionLoop] = None
_SINGLETON_LOCK = threading.Lock()


def get_reflection_loop() -> ReflectionLoop:
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = ReflectionLoop()
    return _SINGLETON


def _clear_singleton_for_tests() -> None:
    """Test helper. Production code never calls this."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


__all__ = [
    "DEFAULT_BACKEND_ID",
    "ReflectionLoop",
    "get_reflection_loop",
]
