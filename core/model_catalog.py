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

    [PR plan-2, 2026-05-09] Now builds from `core.llm_catalog.CATALOG`
    (single source of truth). Picker continues to show (tag, weight)
    pairs for backward compat; richer metadata (purpose, vram, size,
    description) is in the central catalog.

    Operator's `.env` defaults (JAMES_LLM_MODEL, JAMES_CODING_MODEL)
    are still prepended if they're not already in the list, so a
    custom config tag still appears as a picker option.

    Mode policy:
      chat / retrieval / wiki_edit / self_evolve  → "chat" purpose
        entries (a small, opinionated chat-priority list to keep the
        secondary picker compact — not all catalog entries appear)
      coding                                       → "coding" purpose
        entries (qwen-coder + deepseek-coder)
    """
    from config import GEMMA_MODEL, CODING_MODEL
    from core.llm_catalog import by_purpose

    # Per-mode picker list. We deliberately curate down to a few
    # candidates so the dropdown stays readable. The full catalog is
    # available via /admin/llm/recommend or core.llm_catalog.by_purpose.
    chat_picker_tags = ["gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:e4b"]
    chat_cands: List[Tuple[str, str]] = []
    for tag in chat_picker_tags:
        for e in by_purpose("chat"):
            if e["tag"] == tag:
                chat_cands.append((e["tag"], e["weight"]))
                break

    # Operator's chat default first if not already in list.
    if GEMMA_MODEL and not any(c[0] == GEMMA_MODEL for c in chat_cands):
        # Look up its weight from central catalog if known, else medium.
        from core.llm_catalog import by_tag
        info = by_tag(GEMMA_MODEL)
        weight = info["weight"] if info else "medium"
        chat_cands.insert(0, (GEMMA_MODEL, weight))

    coding_picker_tags = ["qwen2.5-coder:7b", "qwen2.5-coder:14b",
                          "qwen2.5-coder:32b", "deepseek-coder:6.7b"]
    code_cands: List[Tuple[str, str]] = []
    for tag in coding_picker_tags:
        for e in by_purpose("coding"):
            if e["tag"] == tag:
                code_cands.append((e["tag"], e["weight"]))
                break

    if CODING_MODEL and not any(c[0] == CODING_MODEL for c in code_cands):
        from core.llm_catalog import by_tag
        info = by_tag(CODING_MODEL)
        weight = info["weight"] if info else "heavy"
        code_cands.insert(0, (CODING_MODEL, weight))

    # Append a non-coder light fallback for coding mode (handle_coding
    # falls through to chat-style call_gemma if coder unavailable).
    if not any(c[0] == "gemma4:e4b" for c in code_cands):
        code_cands.append(("gemma4:e4b", "light"))

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
