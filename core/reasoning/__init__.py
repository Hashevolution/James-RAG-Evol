"""Reasoning subsystem: query orchestration + Limited Loop (#29 Phase 1).

Phase 1 of the reasoning split is purely structural: `core/reasoning_engine.py`
moved to `core/reasoning/engine.py`. Subsequent phases (PR #29 Phase 2 / 3)
will extract the in-method dispatch (`query()` body) into `modes.py` and the
loop body into `pipeline.py`. This package exists so those follow-ups land
in a stable namespace.

Public API mirrors what call sites currently import from `core.reasoning_engine`.
Module-level constants not imported elsewhere (CONFIDENCE_TH, TIMING_TARGET_SEC,
SYSTEM_LOG_PATH) remain accessible only via deep imports from `engine`.
"""

from core.reasoning.engine import ReasoningEngine, MAX_LOOP, LOOP_TIMEOUT

__all__ = ["ReasoningEngine", "MAX_LOOP", "LOOP_TIMEOUT"]
