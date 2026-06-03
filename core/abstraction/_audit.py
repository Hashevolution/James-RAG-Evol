"""Egress audit emit — §5.7.13 §"Caller obligations" #2.

Every `build_map → mask_text → (cloud call) → unmask_text` sequence
emits one `reason:egress` row to `audit_bridge`. The row records
*what got masked* (placeholder ids + entity-type histogram), not the
real names (which never leave the local map per §5.7.13 invariant #5)
and not the map itself (replay reconstructs it from the same entity
set).

Failure to audit is treated the same as a failure to mask — the
egress call MUST NOT proceed. This module exposes a single helper;
the caller is responsible for invoking it on the success path.

Module-size discipline: this file holds the audit emit only. Mask /
unmask in `_mask.py`; policy in `_policy.py`.
"""
from __future__ import annotations

import hashlib
from typing import List, Optional

from core.abstraction._mask import AbstractionMap


def _prompt_hash(prompt: str) -> str:
    """8-hex-char sha256 head — matches the prompt-hash convention in
    `core/reasoning/router.py::emit_route_event` so a `reason:egress`
    row can be cross-referenced with the originating `reason:route`
    row via grep."""
    if not prompt:
        return ""
    return hashlib.sha256(prompt.encode("utf-8", errors="ignore")).hexdigest()[:8]


def _type_histogram(amap: AbstractionMap) -> str:
    """Compact `TYPE:n,TYPE:n` summary of masked entities by type. Used
    by the audit row so operators can answer 'how many PERSON / ORG /
    QUANTITY left the machine on this query?' without needing the
    real names (which are not in the row by invariant #5)."""
    hist: dict = {}
    for ph in amap.forward.values():
        # ph shape: "TYPE_n" — split on the last underscore to keep
        # multi-word types intact (none today, but cheap insurance).
        t = ph.rsplit("_", 1)[0]
        hist[t] = hist.get(t, 0) + 1
    return ",".join(f"{t}:{n}" for t, n in sorted(hist.items()))


def emit_egress_event(
    stage: str,
    prompt: str,
    backend_id: str,
    amap: AbstractionMap,
    *,
    flagged: Optional[List[str]] = None,
    reason: str = "egress",
) -> None:
    """Emit one `reason:egress` row to `audit_log` (via `audit_bridge`).

    Schema mapping (mirrors `emit_route_event` in
    `core/reasoning/router.py`):
      • endpoint = "reason:egress"
      • query    = stage name
      • answer   = "backend={id} masked={hist} kept_local={n} passed={n}
                    flagged={list} reason={why} prompt={hash}"

    `flagged` (the hallucinated-placeholder list from `unmask_text`)
    defaults to `None` — call sites without an unmask phase (e.g.
    pre-egress audit) omit it; call sites with one pass the list so
    the row records whether the cloud returned an unmappable token.

    §5.7.13 invariant #5: real entity names never appear in the row.
    Only placeholder ids (`PERSON_1` …) and type histograms. The audit
    surface is what *categories* of entity left the machine, not which
    specific ones — the specific mapping is reconstructible from the
    deterministic build_map(entities, decider) at replay time.

    Never raises — audit failure must not block the production call
    path (mirrors the pattern in `core.audit_bridge.mirror_to_audit_db`
    and `core.reasoning.router.emit_route_event`).
    """
    try:
        from core.audit_bridge import mirror_to_audit_db

        hist = _type_histogram(amap)
        flag_str = ",".join(flagged) if flagged else ""
        ph_hash = _prompt_hash(prompt)

        mirror_to_audit_db({
            "endpoint": "reason:egress",
            "role": "system",
            "query": stage,
            "answer": (
                f"backend={backend_id} masked={hist or '-'} "
                f"kept_local={len(amap.keep_local)} "
                f"passed={len(amap.passed)} "
                f"flagged={flag_str or '-'} "
                f"reason={reason} prompt={ph_hash}"
            ),
        })
    except Exception:
        # Per the module docstring: audit failure must not block the
        # caller. The caller is responsible for treating an egress
        # without an audit row as a §5.7.13 violation at the higher
        # layer (router refuses to proceed if the audit emit raises) —
        # but THIS helper swallows so a transient sqlite hiccup in the
        # audit DB doesn't crash the main pipeline.
        pass


__all__ = ["emit_egress_event"]
