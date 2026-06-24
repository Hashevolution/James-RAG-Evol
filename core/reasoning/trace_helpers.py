"""L1 wiring helper — call one backend, emit one TraceStep row.

L0 (PR #283) shipped TraceStep / emit_trace_step / Backend registry as
infrastructure. L1 (PR-A of Track 1, this file) routes every synth call
site through the registered backend instead of calling
``engine.llm.call_gemma`` directly. The wiring stays byte-identical when
the default backend (``ollama_local``) runs — that backend wraps
``RouterWrapper.call_gemma`` with the same kwargs.

S5 (Direction α, 2026-06-03): when `JAMES_FORCE_CLOUD=1` AND the
resolved backend is `provider="cloud"`, the synth call is wrapped
through `core.abstraction.run_cloud_egress` — mask→complete→unmask→
audit per §5.7.12 / §5.7.13. The wrap is self-policing: flag-on with a
non-cloud backend logs a warning and proceeds with the normal path
(wrapping local in abstraction would be a confusing no-op). Optional
`entities` kwarg lets call sites that have typed graph entities pipe
them in for actual masking; default `entities=()` makes the wrap a
mask-no-op but exercises the audit + call path end-to-end.

Call shape:

    raw = trace_synth_call(
        prompt,
        applied_rule="reasoning.synth.chat",
        user_role=user_role,
        timeout=60,
        max_tokens=400,
        model=selected_model or None,
    )

Compared to the previous lambda form, this helper:

  * resolves the backend per stage via ``resolve_backend_for_stage`` —
    a ``JAMES_BACKEND_SYNTH=claude_code_cli`` env now retargets the
    whole synth layer to Claude without touching call sites.
  * never imports ``llm.router`` from the middleware layer; the SDK
    barrier (R5 in ``docs/design/v0.3-llm-provider-contract.md``)
    becomes architecturally enforceable.
  * preserves the trace_id correlation, error-string classification,
    and ``output_summary`` truncation from the v0.3.0 helper — no
    audit-log shape change.

Trace correlation: every emitted step carries the current Axis-3
``trace_id`` (core/observability) under ``extras["trace_id"]`` so the
replay tool can ``WHERE answer LIKE '%"trace_id": "<id>"%'`` to
gather every reasoning row for one question. Schema fields stay
clean — ``parent_step_id`` continues to mean step lineage.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.reasoning.backends import (
    CompletionResult,
    get_backend,
    get_backend_capability,
    resolve_backend_for_stage,
)
from core.reasoning.trace_schema import (
    TraceStep,
    compute_inputs_hash,
    emit_trace_step,
    truncate_summary,
)


# v0.6.1 — last answer-stage truncation signal. The backend reports
# ``done_reason="length"`` when the model hit the output-token cap; the
# answer-PRODUCING generations (synth here + reflect.revised) record it so
# the pipeline can surface an accurate `truncated` flag to the UI's
# "continue" banner (replacing the blind client-side heuristic). Reset at
# pipeline start. Single-process local-first app: a module global is
# adequate (not request-isolated under concurrent load — acceptable).
_ANSWER_DONE_REASON = ""


def set_answer_done_reason(reason) -> None:
    global _ANSWER_DONE_REASON
    _ANSWER_DONE_REASON = reason or ""


def get_answer_done_reason() -> str:
    return _ANSWER_DONE_REASON


def reset_answer_done_reason() -> None:
    global _ANSWER_DONE_REASON
    _ANSWER_DONE_REASON = ""


# Sentinel string used in error rows to mark a backend-reported failure
# (the backend returned text matching RouterWrapper's known error strings
# rather than a clean response). Mirrors the OllamaLocalBackend convention
# so consumers see the same shape regardless of which backend ran.
_ROUTER_ERROR_PREFIXES = (
    "[Gemma 응답 없음]",
    "[Gemma 오류]",
    "LLM 응답 생성 중 오류",
)


def _current_trace_id() -> str:
    """Read the Axis-3 trace_id ContextVar without imposing a hard
    dependency on observability — tests / direct callers without an
    HTTP edge get an empty string and the helper still works.
    """
    try:
        from core.observability import get_trace_id
        return get_trace_id() or ""
    except Exception:
        return ""


def _is_router_error(text: Optional[str]) -> bool:
    if not text:
        return True   # empty result counts as a failure to emit text
    return any(text.startswith(p) for p in _ROUTER_ERROR_PREFIXES)


def trace_synth_call(
    prompt: str,
    *,
    applied_rule: str,
    user_role: str = "system",
    stage: str = "synth",
    parent_step_id: str = "",
    system: str = "",
    timeout: float = 60.0,
    max_tokens: int = 1024,
    use_cache: bool = True,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    extras: Optional[Dict[str, Any]] = None,
    entities: Optional[Any] = None,
    **opts: Any,
) -> str:
    """Run one synth call through the registered backend, emit one
    TraceStep row, return the raw text.

    The backend is resolved fresh on every call so that an operator
    flipping ``JAMES_BACKEND_SYNTH`` takes effect without a server
    restart for the synth layer (other stages still resolve at import
    time — see planner.py / reflect.py / verify.py). The cost is one
    dictionary lookup per call, dominated by the LLM round trip.

    Behaviour:
      * Backend failures are surfaced as ``CompletionResult`` with
        ``error`` populated — never as raised exceptions — and emitted
        as an audit row with ``blocked=True`` semantics. The function
        returns the empty string in that case so existing callers
        keep their ``if not answer: …`` fallbacks.
      * If the helper itself can't reach a backend (registry empty
        during early init / import failure), it logs an error row and
        returns ``""`` rather than raising — matches R1.
      * On success, RouterWrapper-style error strings
        (``[Gemma 응답 없음]`` …) are classified as ``error`` rows even
        though they arrive as plain text — preserves the v0.3.0
        signal where the caller checked ``answer.startswith(prefix)``.

    ``extras`` is merged with the auto-added ``trace_id`` (the latter
    wins on key collision, matching emit_trace_step's "schema field
    cannot be clobbered" invariant from L0).
    """
    t0 = time.time()
    emit_extras: Dict[str, Any] = dict(extras or {})
    trace_id = _current_trace_id()
    if trace_id:
        emit_extras["trace_id"] = trace_id

    # Backend resolution: R1 says we don't raise on the user path, so a
    # registry-level failure (no backends registered, unknown stage) is
    # converted to an error row + empty return rather than an exception.
    #
    # D5.C.2.e — flag-gated D5 routing on top of the existing L1
    # `resolve_backend_for_stage` resolution. Under D5 flag OFF the
    # D5 helper returns the L1-resolved backend ID (byte-identical to
    # pre-D5 main). Under D5 flag ON the router policy decides, with
    # the L1 resolution as the `fallback_backend_id`. The audit
    # `reason:route` row lands per call (see emit_route_event).
    #
    # trace_helpers serves multiple stages — synth, verify, reflect,
    # plan, rewrite, etc. The 4 cognitive stage classes
    # (QueryRewriter / Planner / ReflectionLoop / Verifier) route
    # through their own wiring (D5.C.2.a–d); trace_helpers's wiring
    # here covers the synth path and any other stage that goes
    # through `trace_synth_call` rather than the per-class call site.
    try:
        from core.reasoning.evidence_scope import (
            get_current_scope,
            scope_routing_enabled,
        )
        from core.reasoning.router import emit_route_event, resolve_backend

        # LEO L.C — flag-gated scope-based backend routing on top of
        # the existing D5 budget-based routing. With JAMES_SCOPE_ROUTING
        # OFF (default), `scope_breakdown` stays None → resolve_backend
        # receives `evidence_scope=None` → router policy is byte-
        # identical to post-L.B main. With the flag ON, pipeline.py
        # binds the post-Loop-1 ScopeBreakdown via `scope_context(...)`
        # and the router's L.B rule (narrow→small / wide→large) fires.
        scope_breakdown = (
            get_current_scope() if scope_routing_enabled() else None
        )
        scope_val = (
            float(scope_breakdown.scope)
            if scope_breakdown is not None
            else None
        )

        legacy_backend_id = resolve_backend_for_stage(stage)
        backend_id = resolve_backend(
            stage,
            prompt,
            budget_signal=None,
            evidence_scope=scope_val,
            fallback_backend_id=legacy_backend_id,
        )
        backend = get_backend(backend_id)
    except Exception as e:
        emit_trace_step(
            TraceStep(
                stage=stage,
                backend_id="<unresolved>",
                parent_step_id=parent_step_id,
                inputs_hash=compute_inputs_hash(prompt, system=system),
                output_summary="",
                applied_rule=applied_rule,
                latency_ms=int((time.time() - t0) * 1000),
                error=f"backend_resolution: {type(e).__name__}: {str(e)[:200]}",
            ),
            user_role=user_role,
            extras=emit_extras,
        )
        return ""

    # D5.C.2.e + LEO L.C — audit row for the resolved backend. Emitted
    # between resolution and call so the routing decision is logged
    # even if the subsequent backend.complete fails. The scope payload
    # rides along when present so the operator can correlate
    # `evidence_scope=X.XXXX effective_k=… score_entropy=… …` in the
    # reason:route row with the originating /query/ row via prompt hash.
    emit_route_event(
        stage,
        prompt,
        backend_id,
        budget_signal=None,
        reason="scope" if scope_breakdown is not None else "fallback",
        evidence_scope=scope_breakdown,
    )

    # S5 — Direction α cloud routing. When JAMES_FORCE_CLOUD=1 AND the
    # resolved backend is provider="cloud", wrap the egress through
    # `core.abstraction.run_cloud_egress` (§5.7.12 / §5.7.13). Flag OFF
    # → byte-identical to pre-S5 main (no abstraction import, no extra
    # audit row, no runner overhead).
    #
    # Self-policing: flag ON + non-cloud backend → log + fall through.
    # Wrapping a local backend in abstraction would be a no-op (mask
    # never leaves the machine on the local route by construction) and
    # would mislead operators reading the audit log.
    result: Optional[CompletionResult] = None
    try:
        from core.reasoning.router import force_cloud_enabled
        if force_cloud_enabled():
            cap = get_backend_capability(backend_id)
            if cap.provider == "cloud":
                from core.abstraction import (
                    default_decider,
                    run_cloud_egress,
                )
                # Future S7 will pass a query-conditioned decider;
                # default_decider() with empty open-world sets is the
                # safer-egress default (every sensitive entity → MASK).
                result, _flagged = run_cloud_egress(
                    backend=backend,
                    prompt=prompt,
                    entities=list(entities or ()),
                    decider=default_decider(),
                    stage=stage,
                    system=system,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    model=model,
                    use_cache=use_cache,
                    temperature=temperature,
                    **opts,
                )
            else:
                print(
                    f"[FORCE_CLOUD] backend {backend_id!r} is provider="
                    f"{cap.provider!r}, not 'cloud' — JAMES_FORCE_CLOUD=1 "
                    f"falling through to direct backend.complete. "
                    f"Set JAMES_BACKEND_SYNTH to a cloud-tier backend "
                    f"(e.g. claude_code_cli) to enable cloud routing."
                )
    except Exception as e:  # noqa: BLE001
        # The force-cloud wrap is best-effort. Any failure (import,
        # capability lookup, runner-side refusal in a future change)
        # should NOT take down the synth path — log to stderr and fall
        # through to the normal backend.complete so the user query still
        # gets an answer.
        print(f"[FORCE_CLOUD] wrap failed ({type(e).__name__}: {e}) "
              f"— falling through to direct backend.complete")
        result = None

    if result is None:
        result = backend.complete(
            prompt,
            system=system,
            max_tokens=max_tokens,
            timeout=timeout,
            model=model,
            use_cache=use_cache,
            temperature=temperature,
            **opts,
        )

    text_str = result.text if isinstance(result.text, str) else ""
    err = result.error or ""
    if not err and _is_router_error(text_str):
        err = "backend reported error string"

    # Record the truncation signal for this answer-producing generation
    # (synth / web_fallback / retry). reflect.revised overwrites it later
    # if reflection runs; the pipeline reads the final value.
    set_answer_done_reason(getattr(result, "done_reason", "") or "")

    emit_trace_step(
        TraceStep(
            stage=stage,
            backend_id=result.backend_id or backend_id,
            parent_step_id=parent_step_id,
            inputs_hash=compute_inputs_hash(prompt, system=system),
            output_summary=truncate_summary(text_str),
            applied_rule=applied_rule,
            latency_ms=result.latency_ms or int((time.time() - t0) * 1000),
            error=err,
        ),
        user_role=user_role,
        extras=emit_extras,
    )
    # Cognitive Phase 3 PR-9b — every synth call mirrors to the
    # session-scoped episodic store. Best-effort: no session context
    # bound (tests, batch jobs) or store unavailable → silently skipped.
    # Stage maps directly: KNOWN_STAGES already includes "synth".
    try:
        from core.memory.episodic import record_event as _rec
        _rec(
            stage=stage if stage in ("synth", "retrieve", "tool_call",
                                       "plan", "reflect", "verify",
                                       "error") else "synth",
            summary=text_str,
            extras={"applied_rule": applied_rule, "error": err,
                    "backend_id": result.backend_id or backend_id},
        )
    except Exception:
        pass
    # The caller's downstream logic (error-prefix checks, "" fallback)
    # is unchanged — return text whether it's a clean response or one of
    # RouterWrapper's known error strings.
    return text_str


__all__ = ["trace_synth_call"]
