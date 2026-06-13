"""Prompt-length config for the Gemma client.

Extracted from the legacy single-file ``core/gemma_client.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

External callers (tests) import these directly:

    from core.gemma_client import _resolve_max_prompt_len

The re-export façade in ``core.gemma_client.__init__`` preserves
that import shape.
"""
from __future__ import annotations

import os


# Prompt-length cap. The historical default is 4000 chars, baked in
# during Phase 4 to keep early-dev runaway prompts bounded. Cycle γ
# Phase B smoke (2026-06-08) revealed the cap silently truncates
# multi-doc evidence prompts (RGB en row had 35k-char context
# truncated to 4k → noise_robustness measured on truncated evidence),
# the same class of bug as
# ``feedback_synth_context_1000_truncation_rootcause``. Make the
# cap configurable via env var so external-bench measurement runs
# can lift it without touching call sites; the default stays at
# 4000 so production behaviour is byte-identical for any caller
# that doesn't set the env var.
_DEFAULT_MAX_PROMPT_LEN = 4000


def _resolve_max_prompt_len() -> int:
    """Read ``JAMES_GEMMA_MAX_PROMPT_CHARS`` from env each call.

    Reading per-call (not at import) lets a measurement script set the
    env var after this module has been imported and still take effect.
    Returns the default on missing / invalid / non-positive values
    rather than raising — silent fallback matches the rest of this
    module's behaviour and keeps an env-var typo from crashing
    production traffic.
    """
    raw = os.environ.get("JAMES_GEMMA_MAX_PROMPT_CHARS")
    if not raw:
        return _DEFAULT_MAX_PROMPT_LEN
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_PROMPT_LEN
    if val <= 0:
        return _DEFAULT_MAX_PROMPT_LEN
    return val


__all__ = [
    "_DEFAULT_MAX_PROMPT_LEN",
    "_resolve_max_prompt_len",
]
