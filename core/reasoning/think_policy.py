"""Per-stage `think` policy for gemma4:e4b (A2, feeds from A3).

§16.5 of `reports/research-runs/v3prime-cross-family-final-2026-05-29.md`
identified that gemma4:e4b silently spends ~85% of `num_predict` on a
hidden default-on "Thinking Process:" reasoning trace; A3 then measured
the *quality* impact of `think=false` on hard fixtures per cognitive
stage (`reports/research-runs/v3prime-a3-think-quality-boundary-*.md`).

A3 verdict (n=5/cell, deterministic graders, hard fixtures):
- planner        — think=OFF safe (Δquality=+0.04, reclaim ~770 tok)
- reflect        — think=OFF safe (Δquality=0,    reclaim ~690 tok)
- verify         — think=OFF safe (Δquality=0,    reclaim ~900 tok)
- synthesis      — think=OFF wins (Δquality=-0.60 with thinking,
                                   conflict-detection 100% vs 40%)
- query_rewriter — think=OFF safe (Δquality=0,    reclaim ~580 tok)

This module centralises the per-stage policy so a future revisit (LLM-
judge v2, new stages, new thinking-capable models) edits one file. The
policy is *opt-in*: the env flag `JAMES_GEMMA4_E4B_THINK_OFF=1` activates
it. Default is OFF for backward compatibility — operators verify on
their own data before flipping.

Model gating: the policy only applies to thinking-capable checkpoints
(currently the `gemma4:e4b` family — the only Ollama panel model that
declares the `thinking` capability in §16.2). For non-thinking models the
call site emits no `think` field, so the request body stays byte-
identical to pre-A2 behaviour even with the flag ON.
"""
from __future__ import annotations

import os
from typing import Optional

# A3-verified safe stages (think=OFF either matches or beats think=ON
# on hard fixtures, with budget reclaim). Keep the names in sync with
# the `stage=` strings passed to `complete_with_retry` / `trace_synth_call`.
_SAFE_STAGES: frozenset[str] = frozenset({
    "planner",
    "reflect",
    "verify",
    "synth",             # engine_synth.generate_rag_answer → trace_synth_call
    "query_rewriter",    # core/retrieval/query_rewriter.py (stage tag)
})

# Thinking-capable model checkpoints. §16.2: only gemma4:e4b in the
# v3prime cross-family panel declares the `thinking` capability via
# `ollama show`. Non-thinking checkpoints would reject the field (or
# ignore it); the call site uses this list to decide whether to emit
# the field at all. New checkpoints are added explicitly — false
# positives here cause silent HTTP 400s on non-thinking backends.
_THINKING_CAPABLE_PREFIXES: tuple[str, ...] = (
    "gemma4:e4b",
)

_ENV_FLAG = "JAMES_GEMMA4_E4B_THINK_OFF"


def _flag_active() -> bool:
    """Operator gate. Default OFF for backward compatibility."""
    val = os.environ.get(_ENV_FLAG, "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def is_thinking_capable(model: str) -> bool:
    """Whether ``model`` is a checkpoint that emits a hidden thinking
    trace by default (§16.2). Used by `core/gemma_client.py` to decide
    whether to emit the `think` field in the Ollama request body — a
    non-thinking model would reject (HTTP 400) or ignore it.
    """
    if not model:
        return False
    return any(model.startswith(p) for p in _THINKING_CAPABLE_PREFIXES)


def think_for_stage(stage: str) -> Optional[bool]:
    """A3-derived per-stage think policy. Returns:

    - ``False`` when the flag is ON and the stage is on the A3 safe-list
      → caller should request the thinking trace off.
    - ``None`` otherwise (flag OFF, or unknown stage) → caller does not
      override; backend uses its default (think=on for gemma4:e4b).

    The model gating (is_thinking_capable) is applied downstream in
    `GemmaClient.call_gemma` so this function can be called without
    knowing the target model — keeps the per-stage call sites uncluttered.
    """
    if not _flag_active():
        return None
    if stage in _SAFE_STAGES:
        return False
    return None


__all__ = [
    "_SAFE_STAGES",                # exposed for tests / audits
    "_THINKING_CAPABLE_PREFIXES",  # exposed for tests / audits
    "is_thinking_capable",
    "think_for_stage",
]
