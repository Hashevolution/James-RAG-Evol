"""Verification engine — Cognitive Layer Phase 2 PR-6.

ARCHITECTURE.md §5.7.1 verifier stage. Two sub-passes:

  1. Security scan — heuristic, fast (~5 ms). Reuses
     INSTRUCTION_INJECTION_PATTERNS + SENSITIVE_PATTERNS from
     core/security_layer.py (single source of truth for ingest +
     post-synth). Flags injection echo, sensitive-data leak (API key
     / password / 주민번호), role-context privilege over-share.
  2. Fact check — optional, LLM-based (JAMES_ENABLE_FACT_CHECK=1).
     Asks the backend whether each claim is supported by context;
     parses a small JSON response. Silent skip on failure.

Recommendations: ``block`` (injection echo → safe refusal),
``annotate`` (≥ 2 unsupported claims → verification note appended),
``accept`` (default).

Opt-in: JAMES_ENABLE_VERIFY=1. Fact-check doubly gated
(JAMES_ENABLE_VERIFY + JAMES_ENABLE_FACT_CHECK) so the cheap
heuristic can run without the LLM call.

CR-E hook: PR-6 verdicts don't write — they modify the answer
string. Future planner / tool router will introduce
verifier-triggered writes via core/change_request.py (CLAUDE.md
rule #3) in Phase 2 PR-7 / PR-8.

Package layout (2026-09-26 rule #5 split — the single file had 472 B of
headroom left under the 20 KB cap):

  * :mod:`core.reasoning.verify.prompts`         — constants, messages, prompts
  * :mod:`core.reasoning.verify.gates`           — env gates
  * :mod:`core.reasoning.verify.security_flags`  — heuristic scan
  * :mod:`core.reasoning.verify.parsing`         — fact-check JSON parsing
  * :mod:`core.reasoning.verify.verifier`        — VerifyResult + Verifier

This façade re-exports the pre-split surface, so
``from core.reasoning.verify import get_verifier`` keeps working.
"""
from __future__ import annotations

import threading
from typing import Optional

# Pre-split `verify.py` exposed the unified detector at module level, and
# tests/test_i18n_language_detection.py imports it from here. Re-exported
# so the split stays a no-op for callers.
from core.i18n import is_korean as _is_korean  # noqa: F401
from core.reasoning.verify.gates import (  # noqa: F401 - re-export contract
    _enabled,
    _fact_check_enabled,
)
from core.reasoning.verify.parsing import (  # noqa: F401 - re-export contract
    _JSON_OBJ_RE,
    _parse_fact_check,
)
from core.reasoning.verify.security_flags import (  # noqa: F401
    _build_security_flags,
)
from core.reasoning.verify.prompts import (  # noqa: F401
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
from core.reasoning.verify.verifier import Verifier, VerifyResult


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
    "ANNOTATE_THRESHOLD",
    "DEFAULT_BACKEND_ID",
    "DEFAULT_FACT_CHECK_MAX_TOKENS",
    "DEFAULT_FACT_CHECK_TIMEOUT_S",
    "FACT_CHECK_PROMPT_EN",
    "FACT_CHECK_PROMPT_KO",
    "MIN_ANSWER_LEN_FOR_VERIFY",
    "Verifier",
    "VerifyResult",
    "get_verifier",
]
