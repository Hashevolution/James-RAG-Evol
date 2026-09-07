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


# Prompt-length cap. The historical default was 4000 chars, baked in
# during Phase 4 to keep early-dev runaway prompts bounded. Cycle γ
# Phase B smoke (2026-06-08) revealed the cap silently truncates
# multi-doc evidence prompts (RGB en row had 35k-char context
# truncated to 4k → noise_robustness measured on truncated evidence),
# the same class of bug as
# ``feedback_synth_context_1000_truncation_rootcause``.
#
# v0.6.1 design review (2026-07-01): the 4000 default became an
# ACTIVE production defect once ``JAMES_SYNTH_CONTEXT_CHARS`` moved
# to 8000 (engine_synth.py) — the synth stage builds an 8000-char
# evidence block, then this cap chopped the assembled prompt back to
# 4000 chars, silently discarding roughly half the retrieved evidence
# plus the trailing instruction section on every stock install that
# didn't copy `.env.example` (which already sets 16000). The default
# now matches `.env.example` (16000 = evidence 8000 + question +
# instruction headroom). ``JAMES_GEMMA_MAX_PROMPT_CHARS`` still
# overrides in either direction. Consistency with the synth-context
# default is pinned by ``tests/test_gemma_client_prompt_cap.py``.
_DEFAULT_MAX_PROMPT_LEN = 16000


# Ollama keep-alive. Ollama's own default unloads an idle model after
# ~5 minutes; a chat pause longer than that forces a full cold reload
# (tens of seconds on 12B+ models, observed as `done_reason="load"`).
# 30m keeps the model resident across a normal working session while
# still releasing VRAM overnight. Operators can tune / disable via
# ``JAMES_OLLAMA_KEEP_ALIVE`` ("0" / "off" / "none" omits the field →
# Ollama server default applies).
_DEFAULT_KEEP_ALIVE = "30m"


def _resolve_keep_alive() -> str | None:
    """Read ``JAMES_OLLAMA_KEEP_ALIVE`` from env each call.

    Returns the value to place in the Ollama request body, or ``None``
    when the field should be omitted entirely (opt-out). Mirrors
    ``_resolve_max_prompt_len``'s read-per-call semantics so operators
    and measurement scripts can change it without a restart.
    """
    raw = os.environ.get("JAMES_OLLAMA_KEEP_ALIVE")
    if raw is None:
        return _DEFAULT_KEEP_ALIVE
    val = raw.strip()
    if val.lower() in ("", "0", "off", "none", "false"):
        return None
    return val


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
    "_DEFAULT_KEEP_ALIVE",
    "_resolve_keep_alive",
]
