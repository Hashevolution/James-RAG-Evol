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
    "- 사과 문구나 '재작성했습니다' 같은 메타-텍스트 없이 답변만.\n\n"
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
    "- Output only the revised answer — no apologies or meta-text like "
    "\"here is the revised version\".\n\n"
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
        critique_max_tokens: int = DEFAULT_CRITIQUE_MAX_TOKENS,
        revise_max_tokens: int = DEFAULT_REVISE_MAX_TOKENS,
    ) -> None:
        self._backend_id = backend_id
        self._critique_timeout = critique_timeout
        self._revise_timeout = revise_timeout
        self._critique_max_tokens = critique_max_tokens
        self._revise_max_tokens = revise_max_tokens

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

        # D5.C.2.c — flag-gated backend resolution. Reflect is not
        # D1-wired (uses fixed critique/revise caps), so
        # `budget_signal=None` here. Flag-off → `self._backend_id`
        # (byte-identical). Flag-on → router policy with budget=None
        # → rule 4 → legacy. Reflect is not grounding-critical
        # (only `verify` is) so the escalation does not fire. Single
        # backend serves both critique + revise calls below.
        try:
            from core.reasoning.backends import get_backend
            from core.reasoning.router import emit_route_event, resolve_backend

            # Critique prompt template is enough for routing — the
            # actual prompts (critique then revise) hit the same backend.
            router_prompt = crit_tmpl
            backend_id = resolve_backend(
                "reflect",
                router_prompt,
                budget_signal=None,
                fallback_backend_id=self._backend_id,
            )
            backend = get_backend(backend_id)
        except Exception:
            return draft

        emit_route_event(
            "reflect",
            router_prompt,
            backend_id,
            budget_signal=None,
            reason="fallback",
        )

        # ── critique pass ────────────────────────────────────
        critique_prompt = crit_tmpl.format(query=query, draft=draft)
        critique_text, critique_err = self._call(
            backend,
            critique_prompt,
            timeout=self._critique_timeout,
            max_tokens=self._critique_max_tokens,
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
            max_tokens=self._revise_max_tokens,
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

        return revised_text

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
        t0 = time.time()
        try:
            result = backend.complete(
                prompt, max_tokens=max_tokens, timeout=timeout
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
