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

## v0.6 package split (CLAUDE.md rule #5)

This package was a single ``core/reasoning/reflect.py`` file (29.2
KB, over the 20 KB cap) until the v0.6 oversize-module split. The
public API surface is byte-identical — all existing imports
(``from core.reasoning.reflect import ReflectionLoop`` etc.) keep
working through this façade:

  * :mod:`core.reasoning.reflect.prompts` — CRITIQUE_PROMPT_* /
    REVISE_PROMPT_* / DEFAULT_BACKEND_ID / cap + timeout constants
  * :mod:`core.reasoning.reflect.meta_narration` —
    _META_NARRATIVE_PATTERNS + detector + stripper (v0.4 live verify
    fix #6)
  * :mod:`core.reasoning.reflect.issue_extractor` — critique → tag
    map (Option B redesign, 2026-06-05 §23)
  * :mod:`core.reasoning.reflect.loop` — ReflectionLoop class +
    _enabled / _no_issues helpers
  * this ``__init__.py`` — singleton + re-exports

Tests cover every public AND private symbol re-exported here
(``_clear_singleton_for_tests`` / ``_extract_issue_flag`` /
``_enabled`` / ``_looks_like_meta_narration`` /
``_strip_meta_narration``). Renaming or removing any of them is a
contract break.
"""
from __future__ import annotations

import threading
from typing import Optional

# ─── re-exports — preserves the pre-split import surface ─────────

from core.reasoning.reflect.prompts import (  # noqa: F401
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
from core.reasoning.reflect.meta_narration import (  # noqa: F401
    _META_NARRATIVE_PATTERNS,
    _looks_like_meta_narration,
    _strip_meta_narration,
)
from core.reasoning.reflect.issue_extractor import (  # noqa: F401
    _ISSUE_TYPE_PATTERNS,
    _extract_issue_flag,
)
from core.reasoning.reflect.loop import (  # noqa: F401
    ReflectionLoop,
    _enabled,
    _no_issues,
)


# ─── module-level singleton ────────────────────────────────────────
#
# Lives in the package __init__ rather than in loop.py so the
# get_reflection_loop / _clear_singleton_for_tests pair keeps its
# pre-split import path (`from core.reasoning.reflect import
# get_reflection_loop`). The singleton's behaviour is byte-identical
# to the pre-split version — double-checked lock pattern, lazy
# construction on first call.
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
