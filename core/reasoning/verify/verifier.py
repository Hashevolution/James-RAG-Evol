"""``VerifyResult`` and the ``Verifier`` stage itself.

Split out of the single-file ``core/reasoning/verify.py`` on 2026-09-26.
The file had reached 20,008 B against CLAUDE.md rule #5's 20 KB cap —
472 B of headroom — so it could not take another line. Same shape as the
v0.6 ``core/reasoning/reflect/`` split; ``__init__`` re-exports the
pre-split surface, so the move is a no-op for callers.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional


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

# v0.4 Sprint 1 #2 — unified language detection (see core/i18n.py).
from core.i18n import is_korean as _is_korean  # noqa: F401

from core.reasoning.verify.gates import _enabled, _fact_check_enabled
from core.reasoning.verify.parsing import _parse_fact_check
from core.reasoning.evidence_budget import resolve_evidence_chars
from core.reasoning.verify.security_flags import _build_security_flags


_TRUNC_KO = (
    "\n\n[...이후 생략됨. 생략된 부분에 근거가 있을 수 있으므로, 여기 "
    "보이지 않는다는 이유만으로 '근거 없음' 으로 판정하지 마라.]"
)
_TRUNC_EN = (
    "\n\n[...truncated here. Support may exist in the omitted part, so "
    "do NOT mark a claim unsupported merely because you cannot see it "
    "above.]"
)


def _with_truncation_notice(text: str, limit: int, is_ko: bool) -> str:
    """Trim to ``limit`` and say so.

    Silent truncation is the trap: an absent tail reads to the model as
    absent support, which is the defect this budget exists to prevent.
    """
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + (_TRUNC_KO if is_ko else _TRUNC_EN)
from core.reasoning.verify.prompts import (
    ANNOTATE_THRESHOLD,
    BARE_CLAIM_ANSWER_CHARS,
    DEFAULT_BACKEND_ID,
    DEFAULT_FACT_CHECK_MAX_TOKENS,
    DEFAULT_FACT_CHECK_TIMEOUT_S,
    FACT_CHECK_PROMPT_EN,
    FACT_CHECK_PROMPT_KO,
    _BLOCK_MSG_EN,
    _BLOCK_MSG_KO,
)



@dataclass
class VerifyResult:
    """Outcome of one verification pass.

    ``recommendation`` drives caller behaviour:
      - ``"accept"``   → use ``final_answer`` (= input answer)
      - ``"annotate"`` → use ``final_answer`` (= input + verification note)
      - ``"block"``    → use ``final_answer`` (= safe refusal message)
    """
    is_grounded: bool = True
    unsupported_claims: List[str] = field(default_factory=list)
    security_flags: List[str] = field(default_factory=list)
    final_answer: str = ""
    recommendation: str = "accept"


class Verifier:
    """Stateless wrapper that runs a security scan and (optionally) a
    fact-check pass on a generated answer.
    """

    def __init__(
        self,
        backend_id: str = DEFAULT_BACKEND_ID,
        *,
        fact_check_timeout: float = DEFAULT_FACT_CHECK_TIMEOUT_S,
        fact_check_max_tokens: Optional[int] = None,
        budget: Optional[TaskBudget] = None,
    ) -> None:
        # D1 wiring (v0.4 Sprint 3 #7c, mirrors planner / reflect):
        # fact_check_max_tokens None → JAMES_ADAPTIVE_BUDGET decides.
        # Flag off → DEFAULT_FACT_CHECK_MAX_TOKENS (pre-#7c shape).
        self._backend_id = backend_id
        self._fact_check_timeout = fact_check_timeout
        self._fact_check_max_tokens = fact_check_max_tokens
        self._budget = budget if budget is not None else TaskBudget()

    def verify(
        self,
        query: str,
        answer: str,
        context: str,
        user_role: str = "system",
        *,
        force: bool = False,
    ) -> VerifyResult:
        """Run security scan + (optional) fact check.

        Always returns a VerifyResult. Never raises. The
        ``final_answer`` field is the string the caller should use
        (modified for ``annotate``/``block``, unchanged for ``accept``).
        """
        # Only an empty answer short-circuits. The old floor here
        # (`len(answer) < MIN_ANSWER_LEN_FOR_VERIFY`) skipped the
        # security scan AND the fact check for exactly the answers that
        # are a single bare claim — see BARE_CLAIM_ANSWER_CHARS.
        if not answer or not answer.strip():
            return VerifyResult(final_answer=answer, recommendation="accept")
        if not force and not _enabled():
            return VerifyResult(final_answer=answer, recommendation="accept")

        # ── security scan (heuristic) ──────────────────────────
        # `context` reaches the scan since 2026-09-27 so an injection
        # pattern is only an echo when the matched span is really in the
        # evidence. Without it, citing a source ("the context is
        # \"<title>\"") read as instruction bleed-through and a correct
        # answer was replaced by the refusal message.
        sec_flags = _build_security_flags(answer, user_role, context)
        self._emit(
            applied_rule="reasoning.verify.security",
            prompt=answer,
            text=";".join(sec_flags) if sec_flags else "no flags",
            latency_ms=0,
            error="" if not sec_flags else "flags_present",
            user_role=user_role,
        )

        # ── fact check (optional, LLM) ─────────────────────────
        is_grounded = True
        unsupported: List[str] = []
        if _fact_check_enabled() and context and len(context.strip()) >= 50:
            is_grounded, unsupported = self._fact_check(
                query, answer, context, user_role
            )

        # ── decide + format ────────────────────────────────────
        recommendation = self._decide(sec_flags, is_grounded, unsupported,
                                      answer)
        final = self._format(
            query, answer, sec_flags, is_grounded, unsupported, recommendation
        )

        self._emit(
            applied_rule="reasoning.verify.final",
            prompt=answer,
            text=f"rec={recommendation} flags={len(sec_flags)} unsupp={len(unsupported)}",
            latency_ms=0,
            error="" if recommendation == "accept" else recommendation,
            user_role=user_role,
        )

        return VerifyResult(
            is_grounded=is_grounded,
            unsupported_claims=unsupported,
            security_flags=sec_flags,
            final_answer=final,
            recommendation=recommendation,
        )

    def _fact_check(
        self,
        query: str,
        answer: str,
        context: str,
        user_role: str,
    ) -> tuple[bool, List[str]]:
        """Returns ``(is_grounded, unsupported_list)``. Any failure
        path returns ``(True, [])`` — fact-check is a "nice to have",
        not a gate.
        """
        is_ko = _is_korean(query) or _is_korean(answer)
        tmpl = FACT_CHECK_PROMPT_KO if is_ko else FACT_CHECK_PROMPT_EN
        # Both windows used to be a hard-coded 2000 while synth wrote
        # the draft from JAMES_SYNTH_CONTEXT_CHARS (default 8000). A
        # claim supported only by evidence past char 2000 was annotated
        # "not directly supported by the source data" for no reason but
        # the window, and a claim past char 2000 of the answer was never
        # checked at all (answer p95 reached 6133 chars on 2026-09-26).
        # Shared budget, so the two cannot drift apart again.
        limit = resolve_evidence_chars()
        prompt = tmpl.format(
            query=query[:300],
            answer=_with_truncation_notice(answer, limit, is_ko),
            context=_with_truncation_notice(context, limit, is_ko),
        )

        # v0.4 Sprint 3 #7c — D1 cap resolution. assess on the query
        # (not the FACT_CHECK_PROMPT template — that carries heavy
        # markers in the instruction text).
        if self._fact_check_max_tokens is not None:
            cap = self._fact_check_max_tokens
            _budget_for_router = None
        elif adaptive_budget_enabled():
            cap = self._budget.assess("verify", query)
            _budget_for_router = cap
        else:
            cap = DEFAULT_FACT_CHECK_MAX_TOKENS
            _budget_for_router = None

        # D5.C.2.d — flag-gated backend resolution. Verify is the
        # grounding-critical stage: D5.C.1 policy rule 1 escalates to
        # large tier when registered. With D1 active (#7c) the
        # budget_signal layers on rules 1 / 4.
        try:
            from core.reasoning.backends import get_backend
            from core.reasoning.router import emit_route_event, resolve_backend

            backend_id = resolve_backend(
                "verify",
                prompt,
                budget_signal=_budget_for_router,
                fallback_backend_id=self._backend_id,
            )
            backend = get_backend(backend_id)
        except Exception:
            return (True, [])

        emit_route_event(
            "verify",
            prompt,
            backend_id,
            budget_signal=_budget_for_router,
            reason="grounding-critical",
        )

        # D6 retry wiring — length truncation → retry once at doubled
        # cap up to CAP_HEAVY. Flag-off no-op (cap already at 4096).
        t0 = time.time()
        try:
            from core.reasoning.think_policy import think_for_stage
            result = complete_with_retry(
                backend,
                prompt,
                cap=cap,
                timeout=self._fact_check_timeout,
                stage="verify",
                think=think_for_stage("verify"),
            )
        except Exception as e:
            latency_ms = int((time.time() - t0) * 1000)
            self._emit(
                applied_rule="reasoning.verify.fact_check",
                prompt=prompt,
                text="",
                latency_ms=latency_ms,
                error=f"{type(e).__name__}: {str(e)[:200]}",
                user_role=user_role,
            )
            return (True, [])

        latency_ms = int((time.time() - t0) * 1000)
        text = getattr(result, "text", "") or ""
        err = getattr(result, "error", "") or ""
        self._emit(
            applied_rule="reasoning.verify.fact_check",
            prompt=prompt,
            text=text,
            latency_ms=latency_ms,
            error=err,
            user_role=user_role,
        )

        if err or not text:
            return (True, [])

        parsed = _parse_fact_check(text)
        if parsed is None:
            return (True, [])
        return parsed

    def _decide(
        self,
        sec_flags: List[str],
        is_grounded: bool,
        unsupported: List[str],
        answer: str = "",
    ) -> str:
        # Highest severity wins.
        if any(f.startswith("security.injection_echo") for f in sec_flags):
            return "block"
        if not is_grounded and unsupported:
            # A bare claim contains one claim. Requiring two before
            # annotating means a short answer that is entirely
            # unsupported ships clean — which is how "Alex Karp" would
            # have passed even once the length gate was removed.
            # An omitted `answer` is "the caller did not say", not "the
            # answer is empty, therefore bare" — fall back to the
            # threshold rather than annotating on one claim.
            stripped = (answer or "").strip()
            bare = bool(stripped) and len(stripped) <= BARE_CLAIM_ANSWER_CHARS
            if bare or len(unsupported) >= ANNOTATE_THRESHOLD:
                return "annotate"
        return "accept"

    def _format(
        self,
        query: str,
        answer: str,
        sec_flags: List[str],
        is_grounded: bool,
        unsupported: List[str],
        recommendation: str,
    ) -> str:
        if recommendation == "block":
            return _BLOCK_MSG_KO if _is_korean(query) else _BLOCK_MSG_EN
        if recommendation == "annotate":
            shown = ", ".join(c[:60] for c in unsupported[:2])
            if _is_korean(query) or _is_korean(answer):
                note = (
                    f"\n\n(검증: 다음 주장이 자료에 직접 지지되지 "
                    f"않음: {shown})"
                )
            else:
                note = (
                    f"\n\n(Verification: the following claims are not "
                    f"directly supported by the source data: {shown})"
                )
            return answer + note
        return answer

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
                    stage="verify",
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
            pass

        # Cognitive Phase 3 PR-9b — session-scoped episodic mirror.
        try:
            from core.memory.episodic import record_event as _rec
            _rec(
                stage="verify",
                summary=text,
                extras={"applied_rule": applied_rule,
                        "latency_ms": latency_ms, "error": error},
            )
        except Exception:
            pass

