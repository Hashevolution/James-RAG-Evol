"""LLM answer-generation block extracted from pipeline.py.

CLAUDE.md rule #5 module-size gate: pipeline.py grew past 33 KB after
Phase 1 PR-1 (reranker) + PR-2 (query rewriter). This module hosts the
synth block that decides between web fallback, RAG synthesis, and the
no-info retry path — about 200 lines of branching that was the single
biggest chunk in pipeline.py.

Behaviour is byte-identical to the in-place block (this is a pure
refactor; the test suite is the contract). All three Phase 0 L1 trace
wraps on the call_gemma sites are preserved verbatim — the same
audit_log rows land for the same queries.

Returns a small dataclass so the caller can keep the existing
``answer / web_results / pending_save_proposal_id`` outputs.

## v0.6 package split (CLAUDE.md rule #5)

The legacy single-file ``core/reasoning/pipeline_synth.py`` (21.3 KB)
sat over the 20 KB cap after cycle γ Phase D2 added the bilingual
softener helpers. Splitting into a package preserves the public +
private import surface byte-identically — every caller
(``core/reasoning/pipeline.py`` for ``generate_answer`` /
``tests/test_cycle_gamma_phase_d2_softener_bilingual.py`` for the
``_KOREAN_NO_DATA_TRIGGERS`` / ``_ENGLISH_NO_DATA_TRIGGERS`` /
``_abstention_triggers`` / ``_build_retry_prompt`` privates /
``tests/test_planner_terse_skip.py`` for ``generate_answer``) keeps
working through this façade:

  * :mod:`core.reasoning.pipeline_synth.softener` — Korean +
    English no-data triggers + ``_abstention_triggers`` +
    ``_build_retry_prompt``
  * :mod:`core.reasoning.pipeline_synth.result` — ``AnswerBlock``
    dataclass
  * :mod:`core.reasoning.pipeline_synth.generator` —
    ``generate_answer`` orchestrator
  * this ``__init__.py`` — re-exports
"""
from __future__ import annotations

# ─── re-exports — preserves the pre-split import surface ─────────

from core.reasoning.pipeline_synth.result import (  # noqa: F401
    AnswerBlock,
)
from core.reasoning.pipeline_synth.softener import (  # noqa: F401
    _KOREAN_NO_DATA_TRIGGERS,
    _ENGLISH_NO_DATA_TRIGGERS,
    _abstention_triggers,
    _build_retry_prompt,
)
from core.reasoning.pipeline_synth.generator import (  # noqa: F401
    generate_answer,
)


__all__ = ["AnswerBlock", "generate_answer"]
