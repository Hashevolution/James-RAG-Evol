"""Verification engine — Cognitive Layer Phase 2 PR-6.

ARCHITECTURE.md §5.7.1: "Verification Engine — generator → critic →
fact_checker → security_validator → final_synthesizer". The
generator (synth.py) and critic (reflect.py) already shipped in
PR-5; this PR adds the **fact_checker** + **security_validator**
passes that JAMES advertises as its security-aware reasoning
differentiator (2026-05-14 user briefing).

Two layers run in sequence:

  1. **Security scan** — heuristic, fast (~5 ms). Reuses the existing
     INSTRUCTION_INJECTION_PATTERNS + SENSITIVE_PATTERNS from
     core/security_layer.py so a single source of truth governs both
     ingest-time blocking and post-synth verification. Flags injection
     echo (a low-trust source's instruction leaked into the answer),
     sensitive data leak (API key / password / 주민번호), and (with
     role context) privilege over-share signals.
  2. **Fact check** — optional, LLM-based (separate env gate
     ``JAMES_ENABLE_FACT_CHECK=1``). Asks the backend whether each
     claim in the answer is supported by the retrieved context;
     parses a small JSON response. Skips silently on backend failure.

Recommendation:

  * ``"block"``    — security scan found injection echo (the highest
                     severity signal). Answer is replaced with a safe
                     refusal message; the caller still gets a string.
  * ``"annotate"`` — fact-check found ≥ 2 unsupported claims. The
                     original answer is preserved but appended with a
                     short verification note.
  * ``"accept"``   — everything passed (or only soft signals fired).

Posture: opt-in via JAMES_ENABLE_VERIFY=1. Fact-check is **doubly**
gated (JAMES_ENABLE_VERIFY + JAMES_ENABLE_FACT_CHECK) so an operator
can run cheap heuristic verification without the extra LLM call.

CR-E integration (sustainability note): future work. When the
verifier produces a write-recommending verdict (e.g., "answer reveals
something that should update wiki entity X"), that write will route
through ``core/change_request.py`` per CLAUDE.md rule #3. PR-6 itself
doesn't produce any write-recommending verdicts — its verdicts only
modify the answer string returned to the caller. The CR-E hook lands
with Phase 2 PR-7/PR-8 when planner + tool router introduce
verifier-triggered writes.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from core.reasoning.trace_schema import (
    TraceStep,
    compute_inputs_hash,
    emit_trace_step,
    truncate_summary,
)


# [JAMES_REASONING_BACKEND wiring 2026-05-18] resolved at import time.
from core.reasoning.backends import get_default_backend_id as _get_default_backend
DEFAULT_BACKEND_ID = _get_default_backend()
DEFAULT_FACT_CHECK_TIMEOUT_S = 30.0
# gemma4:e4b consumes ~500 hidden reasoning tokens before the first
# visible output on short structured prompts; cap below that floor
# → deterministic empty response (model burns the budget without
# surfacing any byte).
DEFAULT_FACT_CHECK_MAX_TOKENS = 4096
MIN_ANSWER_LEN_FOR_VERIFY = 30
# An "unsupported claim" count at or above this triggers annotation.
ANNOTATE_THRESHOLD = 2


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


def _enabled() -> bool:
    """Verifier base mode (security_validator heuristic) is **default ON**
    since v0.3.x.

    The base scan is ~5ms of pure-Python pattern matching against the
    final answer — well below the STEP 7 measurement noise floor and
    independent of LLM availability. Keeping it always-on means that
    a vanilla JAMES install gets injection-echo detection from day
    one without an operator having to discover the env flag.

    The legacy opt-in ``JAMES_ENABLE_VERIFY=1`` is still honoured as
    a no-op (truthy → True), so a tightly-coupled .env from earlier
    releases keeps working. The new opt-out is
    ``JAMES_DISABLE_VERIFY=1`` for the rare case an operator wants
    to measure baseline cost or silence the verifier's annotate /
    block recommendations entirely.

    Fact-checking (LLM-driven, +5-15s/query) remains opt-in — see
    :func:`_fact_check_enabled`.
    """
    return os.environ.get("JAMES_DISABLE_VERIFY") != "1"


def _fact_check_enabled() -> bool:
    """Fact-check stays opt-in via ``JAMES_ENABLE_FACT_CHECK=1``.

    The chain ``_enabled() and ...`` means a hard opt-out
    (``JAMES_DISABLE_VERIFY=1``) silences both base scan and
    fact-check in one knob — consistent with operator intent.
    """
    return (
        _enabled()
        and os.environ.get("JAMES_ENABLE_FACT_CHECK") == "1"
    )


# v0.4 Sprint 1 #2 — unified language detection (see core/i18n.py).
from core.i18n import is_korean as _is_korean  # noqa: F401


_BLOCK_MSG_KO = (
    "(보안 검증: 응답에서 신뢰할 수 없는 출처의 지시 흔적이 감지되어 "
    "차단되었습니다. 질문을 다시 표현해 주세요.)"
)
_BLOCK_MSG_EN = (
    "(Security verification: the response contained instruction "
    "echoes from an untrusted source and was blocked. Please "
    "rephrase the question.)"
)


FACT_CHECK_PROMPT_KO = (
    "아래 답변의 핵심 주장들이 제공된 [내부 자료] 에 의해 직접 지지되는지 "
    "검증하라.\n\n"
    "[질문]\n{query}\n\n"
    "[답변]\n{answer}\n\n"
    "[내부 자료]\n{context}\n\n"
    "검증 규칙:\n"
    "- 답변 안의 명시적 주장 (사실 / 수치 / 인용) 만 대상으로 함\n"
    "- 자료가 지지하는 주장은 통과; 자료에 없거나 모순되는 주장만 'unsupported'\n"
    "- 일반 상식 (예: 'AI 는 기술이다') 은 자료에 없어도 통과\n\n"
    "JSON 으로만 응답하라:\n"
    '{{"grounded": true|false, "unsupported": ["짧은 주장 1", "..."]}}'
)

FACT_CHECK_PROMPT_EN = (
    "Verify whether the key claims in the answer are directly "
    "supported by the [Internal Data] below.\n\n"
    "[Question]\n{query}\n\n"
    "[Answer]\n{answer}\n\n"
    "[Internal Data]\n{context}\n\n"
    "Rules:\n"
    "- Only check explicit claims (facts, numbers, citations) inside "
    "the answer\n"
    "- Claims the data supports → pass; only claims that the data "
    "lacks or contradicts go into 'unsupported'\n"
    "- General common knowledge (e.g., 'AI is a technology') passes "
    "even without data support\n\n"
    "Respond with JSON only:\n"
    '{{"grounded": true|false, "unsupported": ["short claim 1", "..."]}}'
)


def _build_security_flags(answer: str, user_role: str) -> List[str]:
    """Heuristic scan. Reuses the existing INSTRUCTION_INJECTION_PATTERNS
    + SENSITIVE_PATTERNS so the verifier and the v0.2 security layer
    agree on what counts as a leak.
    """
    flags: List[str] = []
    if not answer:
        return flags

    try:
        from core.security_layer import (
            INSTRUCTION_INJECTION_PATTERNS,
            SENSITIVE_PATTERNS,
            BLOCKED_KEYWORDS_BY_ROLE,
        )
    except Exception:
        return flags

    # Injection echo — a low-trust source's instruction text bled into
    # the answer despite ingest-time sanitization. This is the highest-
    # severity signal; triggers "block".
    for pattern in INSTRUCTION_INJECTION_PATTERNS:
        try:
            if re.search(pattern, answer, flags=re.IGNORECASE):
                snippet = pattern[:30] + ("…" if len(pattern) > 30 else "")
                flags.append(f"security.injection_echo:{snippet}")
        except re.error:
            continue

    # Sensitive data leak — the output filter still does the redaction;
    # we just flag for audit.
    for pattern, label in SENSITIVE_PATTERNS:
        try:
            if re.search(pattern, answer):
                flags.append(f"security.sensitive_leak:{label}")
        except re.error:
            continue

    # Role-aware blocked keywords — covers the existing role gating
    # for external / employee viewers.
    role_blocked = BLOCKED_KEYWORDS_BY_ROLE.get(user_role, [])
    for kw in role_blocked:
        if kw and kw.lower() in answer.lower():
            flags.append(f"security.role_blocked:{kw}")

    return flags


_JSON_OBJ_RE = re.compile(r'\{[^{}]*"grounded"\s*:\s*(?:true|false)[^{}]*\}', re.DOTALL | re.IGNORECASE)


def _parse_fact_check(llm_text: str):
    """Return ``(grounded: bool, unsupported: List[str])`` or ``None``
    on parse failure (caller treats as "skip, accept").
    """
    if not llm_text:
        return None
    try:
        blob = json.loads(llm_text)
        if isinstance(blob, dict):
            grounded = bool(blob.get("grounded", True))
            unsupported = blob.get("unsupported", []) or []
            if not isinstance(unsupported, list):
                unsupported = []
            unsupported = [str(c)[:120] for c in unsupported if c]
            return (grounded, unsupported)
    except (json.JSONDecodeError, ValueError):
        pass
    # Slower path: regex sniff for the object body
    m = _JSON_OBJ_RE.search(llm_text)
    if m:
        try:
            blob = json.loads(m.group(0))
            grounded = bool(blob.get("grounded", True))
            unsupported = blob.get("unsupported", []) or []
            if isinstance(unsupported, list):
                unsupported = [str(c)[:120] for c in unsupported if c]
            return (grounded, unsupported)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


class Verifier:
    """Stateless wrapper that runs a security scan and (optionally) a
    fact-check pass on a generated answer.
    """

    def __init__(
        self,
        backend_id: str = DEFAULT_BACKEND_ID,
        *,
        fact_check_timeout: float = DEFAULT_FACT_CHECK_TIMEOUT_S,
        fact_check_max_tokens: int = DEFAULT_FACT_CHECK_MAX_TOKENS,
    ) -> None:
        self._backend_id = backend_id
        self._fact_check_timeout = fact_check_timeout
        self._fact_check_max_tokens = fact_check_max_tokens

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
        sec_flags = _build_security_flags(answer, user_role)
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

        # D5.C.2.d — flag-gated backend resolution. Verify is the
        # grounding-critical stage: D5.C.1 policy rule 1 escalates it
        # to `large` tier (preferred), then `medium`, then legacy.
        # This is the stage where a small-tier-only fleet sees
        # routing actually take effect — even with budget_signal=None
        # the verify-stage escalation fires when a larger backend is
        # registered (e.g. JAMES_ENABLE_CLAUDE_BACKEND=1).
        try:
            from core.reasoning.backends import get_backend
            from core.reasoning.router import emit_route_event, resolve_backend

            backend_id = resolve_backend(
                "verify",
                prompt,
                budget_signal=None,
                fallback_backend_id=self._backend_id,
            )
            backend = get_backend(backend_id)
        except Exception:
            return (True, [])

        emit_route_event(
            "verify",
            prompt,
            backend_id,
            budget_signal=None,
            reason="grounding-critical",
        )

        t0 = time.time()
        try:
            result = backend.complete(
                prompt,
                max_tokens=self._fact_check_max_tokens,
                timeout=self._fact_check_timeout,
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


# ─── module-level singleton ────────────────────────────────────────
_SINGLETON: Optional[Verifier] = None
_SINGLETON_LOCK = threading.Lock()


def get_verifier() -> Verifier:
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = Verifier()
    return _SINGLETON


def _clear_singleton_for_tests() -> None:
    """Test helper. Production code never calls this."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


__all__ = [
    "DEFAULT_BACKEND_ID",
    "Verifier",
    "VerifyResult",
    "get_verifier",
]
