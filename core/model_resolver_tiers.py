"""Local complexity-tier ladder — split out of ``model_resolver.py``.

Extracted (CLAUDE.md rule #5, 2026-06-21) so ``core/model_resolver.py``
stays under the 20 KB cap. Behaviour is byte-identical to the in-place
block; only the home module changed. Depends one-way on
``core.model_resolver`` (which does NOT import this module → no cycle).

# ─── v18.7 Phase 3a — local complexity-tier ladder ─────────────────
# Operator decision 2026-06-16 (Option B): D5 should escalate among
# LOCAL ollama model sizes by query complexity (4b → 12b → 27b)
# rather than routing local↔cloud. The existing BackendCapability
# tier vocabulary (small ≤4B / medium 12-27B / large 70B+ or cloud)
# does NOT give three local rungs — a 12 GB GPU has no local "large"
# (70B+). So the local ladder is its own mapping, separate from the
# backend-tier system: it picks an ollama TAG for a given complexity
# rung, and a future Phase 3b wire feeds that tag to ollama_local.
#
# Rungs (NOT the same as BackendCapability tiers — these are local
# model-size rungs):
#   "light"    → gemma3:4b   — narrow scope / CAP_SUBSTITUTION / cheap
#   "standard" → gemma3:12b  — chat measurement leader (Phase 2b)
#   "deep"     → gemma3:27b  — broad scope / CAP_HEAVY / verify stage
#
# Honest framing: this ladder is DEFINED but NOT YET CONSUMED by the
# pipeline. gemma3:12b is the only rung with a paired measurement
# (Phase 2b chat); gemma3:4b lost that measurement and gemma3:27b was
# not measured. Phase 3b runs a complexity-paired measurement
# (narrow vs broad query × {4b, 12b, 27b}) BEFORE any escalation is
# wired into D5 — the α-7 caveat (no activation without measurement)
# is binding here.
"""
from __future__ import annotations

import os
from typing import List

from core.model_resolver import (
    ResolvedModel,
    installed_models,
    resolve_for_mode,
)


LOCAL_TIER_LADDER: dict = {
    "light":    "gemma3:4b",
    "standard": "gemma3:12b",
    "deep":     "gemma3:27b",
}

# Order from cheapest to most capable — used for graceful downgrade
# when the requested rung's model isn't installed.
_LADDER_ORDER = ["light", "standard", "deep"]


def _local_tier_tag(rung: str) -> str:
    """Tag for a local complexity rung, honoring env override.

    Env key: JAMES_LOCAL_TIER_<RUNG> (e.g. JAMES_LOCAL_TIER_DEEP).
    Unknown rung falls back to the 'standard' rung tag.
    """
    env_key = f"JAMES_LOCAL_TIER_{rung.upper()}"
    raw = os.environ.get(env_key, "").strip()
    if raw:
        return raw
    return LOCAL_TIER_LADDER.get(rung, LOCAL_TIER_LADDER["standard"])


def resolve_local_tier(rung: str = "standard") -> ResolvedModel:
    """Resolve an installed ollama tag for a local complexity rung.

    Picks the rung's mapped tag if installed; otherwise downgrades
    along _LADDER_ORDER (deep → standard → light) to the nearest
    installed rung, then falls through to resolve_for_mode("chat")
    as a last resort so this never returns an empty tag when ANY
    model is installed.

    Never raises. Phase 3a: callers are introspection / probe only —
    the pipeline does NOT call this yet (Phase 3b wires it after the
    complexity-paired measurement).
    """
    inst = installed_models()
    chain: List[str] = []

    # Requested rung first.
    want = _local_tier_tag(rung)
    chain.append(want)
    if want in inst:
        return ResolvedModel(want, "local_tier", chain, "")

    # Downgrade along the ladder from the requested rung downward, then
    # any remaining rung, to find the nearest installed model.
    try:
        start = _LADDER_ORDER.index(rung)
    except ValueError:
        start = _LADDER_ORDER.index("standard")
    candidates = _LADDER_ORDER[start::-1] + _LADDER_ORDER[start + 1:]
    for r in candidates:
        tag = _local_tier_tag(r)
        if tag in chain:
            continue
        chain.append(tag)
        if tag in inst:
            return ResolvedModel(
                tag, "local_tier_downgrade", chain,
                f"requested rung '{rung}' tag '{want}' not installed; "
                f"using '{tag}' (rung '{r}')",
            )

    # Last resort — reuse the chat resolver (preference list + any).
    fallback = resolve_for_mode("chat", requested="")
    chain.extend(t for t in fallback.fallback_chain if t not in chain)
    return ResolvedModel(
        fallback.tag,
        "local_tier_fallback_chat" if fallback.tag else "none",
        chain,
        fallback.warning or (
            f"no local-tier model installed for rung '{rung}'"
        ),
    )


__all__ = ["LOCAL_TIER_LADDER", "resolve_local_tier"]
