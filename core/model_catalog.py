"""Per-mode model catalog + server-side validation (#A2 phase 2, 2026-05-09).

Phase 1 (PR #113) added the secondary model picker UI but the chosen tag
only landed in localStorage — actual /query/ calls still used the mode's
default LLM tag. Phase 2 plumbs the user's choice through to call_gemma.

This module is the single source of truth for:
  - mode → ordered candidate list
  - validating an arbitrary tag against a mode's allowlist (security:
    don't let a client request /query/ with model="rm -rf /")

It deliberately lives in `core/` (not `server_llmwiki.py`) so the
reasoning engine can import it without a circular dependency on the
HTTP layer. `server_llmwiki._model_catalog` now delegates here while
keeping its public name for backward compat with existing tests
(test_model_catalog_per_mode.test_catalog_function_exists).
"""
from __future__ import annotations

from typing import List, Optional, Tuple


def model_catalog() -> dict:
    """Mode → ordered list of (tag, weight) candidates.

    Default-first ordering. Operator's `.env` (JAMES_LLM_MODEL,
    JAMES_CODING_MODEL) is prepended if not already in the list, so a
    custom config still appears as a candidate.
    """
    from config import GEMMA_MODEL, CODING_MODEL
    chat_default = GEMMA_MODEL
    code_default = CODING_MODEL
    chat_cands: List[Tuple[str, str]] = [
        (chat_default, "light"),
        ("gemma3:12b", "medium"),
        ("gemma3:27b", "heavy"),
    ]
    if not any(c[0] == chat_default for c in chat_cands):
        chat_cands.insert(0, (chat_default, "medium"))
    code_cands: List[Tuple[str, str]] = [
        ("qwen2.5-coder:7b", "light"),
        (code_default,       "heavy"),
        ("gemma4:e4b",       "light"),
    ]
    if not any(c[0] == code_default for c in code_cands):
        code_cands.insert(0, (code_default, "heavy"))
    return {
        "chat":         chat_cands,
        "retrieval":    chat_cands,
        "wiki_edit":    chat_cands,
        "self_evolve":  chat_cands,
        "coding":       code_cands,
    }


def is_valid_for_mode(mode: str, tag: str) -> bool:
    """True if `tag` is in the catalog list for `mode`. Unknown mode or
    empty tag returns False (caller falls back to mode default)."""
    if not mode or not tag:
        return False
    cands = model_catalog().get(mode, [])
    return any(t == tag for t, _ in cands)


def resolve_model(mode: str, requested_tag: str) -> Optional[str]:
    """Validate user-requested model against the per-mode allowlist.

    Returns the tag if valid, None otherwise. None means "fall back to
    mode default" — call_gemma() handles `model=None` by using
    config.GEMMA_MODEL, and coding mode's router picks qwen-coder.

    SECURITY: this is the trust boundary between an untrusted client
    request and the actual LLM call. Anything not in the catalog is
    rejected silently (treated as "use default"), not echoed to Ollama.
    """
    if is_valid_for_mode(mode, requested_tag):
        return requested_tag
    return None
