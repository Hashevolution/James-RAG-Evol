"""L1 wiring helper — wrap an LLM call so it emits one TraceStep row.

L0 (PR #283) shipped TraceStep / emit_trace_step / Backend registry as
infrastructure. L1 (this PR) wires the existing 12 ``call_gemma`` sites
in pipeline.py / modes.py / engine.py to emit one ``audit_log`` row each,
without changing what the LLM returns (STEP 7 must stay byte-identical).

The helper exists to keep each call site small:

    raw = trace_synth_call(
        lambda: engine.llm.call_gemma(prompt, timeout=60, max_tokens=400),
        prompt,
        applied_rule="reasoning.synth.chat",
        user_role=user_role,
    )

vs the inline alternative (8 lines per site × 12 sites = 96 LOC of
boilerplate). Same byte-output, plus one audit row per LLM round-trip.

Trace correlation: every emitted step carries the current Axis-3
``trace_id`` (core/observability) under ``extras["trace_id"]`` so the
future replay tool can ``WHERE answer LIKE '%"trace_id": "<id>"%'`` to
gather every reasoning row for one question. Schema fields stay clean —
``parent_step_id`` continues to mean step lineage (populated in Phase 2
when reflection/verification stack steps).
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from core.reasoning.trace_schema import (
    TraceStep,
    compute_inputs_hash,
    emit_trace_step,
    truncate_summary,
)


# Sentinel string used in error rows to mark a RouterWrapper-known
# failure mode (callee returned an error string, not text). Mirrors the
# OllamaLocalBackend convention so consumers see the same shape whether
# they call the backend directly or via this helper.
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
    llm_call: Callable[[], Any],
    prompt: str,
    *,
    applied_rule: str,
    user_role: str = "system",
    stage: str = "synth",
    backend_id: str = "ollama_local",
    parent_step_id: str = "",
    system: str = "",
    extras: Optional[Dict[str, Any]] = None,
) -> str:
    """Call ``llm_call()``, emit one TraceStep, return the raw text.

    Behaviour:
      * Wraps the call in a try/except — exceptions are converted into
        an ``error`` row and re-raised so the caller's existing
        error-handling stays unchanged.
      * On success, classifies RouterWrapper's known error strings
        (`[Gemma 응답 없음]`, etc.) as ``error`` rows even though the
        return type is a string — consumers can filter on ``blocked=1``.
      * Returns the raw text unmodified — no truncation, no rewriting.
        The audit row's ``output_summary`` is a truncated copy; the
        caller's downstream logic sees the full text.

    ``extras`` is merged with the auto-added ``trace_id`` (the latter
    wins on key collision, matching emit_trace_step's "schema field
    cannot be clobbered" invariant from L0).
    """
    t0 = time.time()
    emit_extras: Dict[str, Any] = dict(extras or {})
    trace_id = _current_trace_id()
    if trace_id:
        emit_extras["trace_id"] = trace_id

    try:
        text = llm_call()
    except Exception as e:
        emit_trace_step(
            TraceStep(
                stage=stage,
                backend_id=backend_id,
                parent_step_id=parent_step_id,
                inputs_hash=compute_inputs_hash(prompt, system=system),
                output_summary="",
                applied_rule=applied_rule,
                latency_ms=int((time.time() - t0) * 1000),
                error=f"{type(e).__name__}: {str(e)[:200]}",
            ),
            user_role=user_role,
            extras=emit_extras,
        )
        raise

    text_str = text if isinstance(text, str) else (str(text) if text is not None else "")
    err = ""
    if _is_router_error(text_str):
        err = "backend reported error string"

    emit_trace_step(
        TraceStep(
            stage=stage,
            backend_id=backend_id,
            parent_step_id=parent_step_id,
            inputs_hash=compute_inputs_hash(prompt, system=system),
            output_summary=truncate_summary(text_str),
            applied_rule=applied_rule,
            latency_ms=int((time.time() - t0) * 1000),
            error=err,
        ),
        user_role=user_role,
        extras=emit_extras,
    )
    return text_str


__all__ = ["trace_synth_call"]
