"""ReflectionLoop class — the orchestrator that runs critique → revise.

Extracted from the legacy single-file ``core/reasoning/reflect.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

The legacy module docstring (now lives at the package `__init__`):

    Reflection loop — Cognitive Layer Phase 2 PR-5.

    ARCHITECTURE.md §5.7.1: "Reflection Engine — draft → self_critique
    → revised per subtask". Wraps an already-generated answer with a
    critique + revise pass to surface contradictions, missing evidence,
    and policy-relevant errors before the answer reaches the user.

    Posture: opt-in by default. JAMES_ENABLE_REFLECT=1 enables. Each
    invocation costs two extra LLM round-trips (critique + revise),
    roughly doubling the answer-stage latency. Operators choose when
    the quality gain justifies the cost.
"""
from __future__ import annotations

import os
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

from core.reasoning.reflect.prompts import (
    DEFAULT_BACKEND_ID,
    DEFAULT_CRITIQUE_TIMEOUT_S,
    DEFAULT_REVISE_TIMEOUT_S,
    DEFAULT_CRITIQUE_MAX_TOKENS,
    DEFAULT_REVISE_MAX_TOKENS,
    MAX_REVISE_RATIO,
    CRITIQUE_PROMPT_KO,
    CRITIQUE_PROMPT_EN,
    REVISE_PROMPT_KO,
    REVISE_PROMPT_EN,
    REVISE_PROMPT_V2_EN,
    REVISE_PROMPT_V2_KO,
)
from core.reasoning.reflect.meta_narration import _strip_meta_narration
from core.reasoning.reflect.issue_extractor import _extract_issue_flag

# v0.4 Sprint 1 #2 — unified language detection (see core/i18n.py).
# Replaces the legacy ≥ 20% Korean-char threshold with a dominant-
# script comparison that agrees with engine_synth on mixed queries.
from core.i18n import is_korean as _is_korean


def _enabled() -> bool:
    # α-6 S6 sector ablation — `JAMES_DISABLE_COGNITIVE_STAGES=1`
    # forces all cognitive stages OFF regardless of per-stage flags.
    if os.environ.get("JAMES_DISABLE_COGNITIVE_STAGES") == "1":
        return False
    return os.environ.get("JAMES_ENABLE_REFLECT") == "1"


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
        # 2026-06-05 §23 — Option B redesign: when JAMES_REVISE_PROMPT_V2=1
        # the revise call no longer sees the critique text. Critique is
        # compressed to a one-word issue tag and the prompt frames the
        # model as writing a fresh answer (not as revising). This closes
        # the meta-format space at the source — the model cannot speak
        # revision-speak when it never sees a review. Default OFF for
        # production byte-identical. Critique still runs (audit trail
        # preserved); only the revise-side framing changes.
        if os.environ.get("JAMES_REVISE_PROMPT_V2", "0") == "1":
            issue_type = _extract_issue_flag(critique_text)
            rev_v2_tmpl = REVISE_PROMPT_V2_KO if is_ko else REVISE_PROMPT_V2_EN
            revise_prompt = rev_v2_tmpl.format(
                query=query, draft=draft, issue_type=issue_type
            )
        else:
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

        # The revised pass produces the FINAL displayed answer — record its
        # truncation signal so the pipeline's `truncated` flag is accurate.
        if applied_rule.endswith("revised") and not err:
            try:
                from core.reasoning.trace_helpers import set_answer_done_reason
                set_answer_done_reason(getattr(result, "done_reason", "") or "")
            except Exception:
                pass

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


__all__ = [
    "ReflectionLoop",
    "_enabled",
    "_no_issues",
]
