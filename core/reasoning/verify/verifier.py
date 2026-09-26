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
from core.reasoning.verify.security_flags import _build_security_flags
from core.reasoning.verify.prompts import (
    ANNOTATE_THRESHOLD,
    DEFAULT_BACKEND_ID,
    DEFAULT_FACT_CHECK_MAX_TOKENS,
    DEFAULT_FACT_CHECK_TIMEOUT_S,
    FACT_CHECK_PROMPT_EN,
    FACT_CHECK_PROMPT_KO,
    MIN_ANSWER_LEN_FOR_VERIFY,
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
        if not answer or len(answer.strip()) < MIN_ANSWER_LEN_FOR_VERIFY:
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
        recommendation = self._decide(sec_flags, is_grounded, unsupported)
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
        prompt = tmpl.format(
            query=query[:300],
            answer=answer[:2000],
            context=context[:2000],
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
    ) -> str:
        # Highest severity wins.
        if any(f.startswith("security.injection_echo") for f in sec_flags):
            return "block"
        if not is_grounded and len(unsupported) >= ANNOTATE_THRESHOLD:
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

