"""DFS + scoring constants for the graph engine.

Extracted from the legacy single-file ``core/graph_engine.py`` during
the v0.6 oversize-module split (CLAUDE.md rule #5). Values are
byte-identical to the pre-split file; only the location moved.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone


CONFIDENCE_THRESHOLD = 0.6
MAX_DEPTH            = 4
DFS_SCORE_THRESHOLD  = 0.05
DEPTH_DECAY          = 0.7

# Relation mutation_types that mean the edge is NOT part of the current
# graph state (deactivated by the cascade / T1 expiration / T7 supersede).
_DEAD_MUTATION_TYPES = ("invalidated", "superseded", "expired")


def _now_utc():
    try:
        from core.lifecycle.clock import now
        return now()
    except Exception:
        return datetime.now(timezone.utc)


def _parse_ts(s):
    """ISO-8601 → tz-aware datetime, or None if empty/unparseable (treated
    as 'no constraint' so a bad timestamp never breaks traversal)."""
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def relation_is_live(rel: dict, *, at=None) -> bool:
    """v0.6.1 — current-state live traversal must honor lifecycle status.

    Measurement (cascade_consistency_probe, PR #1020) showed live graph
    traversal filtered relations by confidence ONLY, so cascade-/T1-/T7-
    deactivated edges leaked into the LLM context (status was honored only
    in the reconstruct_*_at time-travel path). This predicate restores
    consistency. An edge is NOT live if:
      - ``status.active is False``; or
      - ``mutation_type`` ∈ {invalidated, superseded, expired}; or
      - it has a T1 ``validity`` window and the clock is outside it
        (``validity.to < now`` expired, or ``validity.from > now`` not yet
        valid). This catches time-expired edges the batch expiration sweep
        (run_expiration_cascade — NOT per-query) has not yet marked.

    ``at`` overrides the comparison clock (tests / explicit current time).
    Kill-switch ``JAMES_DISABLE_STATUS_FILTER=1`` → legacy (leaky)
    behavior. Untagged legacy edges (no status / mutation_type / validity)
    are live.
    """
    if os.environ.get("JAMES_DISABLE_STATUS_FILTER") == "1":
        return True
    if not isinstance(rel, dict):
        return False
    if (rel.get("status") or {}).get("active") is False:
        return False
    if rel.get("mutation_type") in _DEAD_MUTATION_TYPES:
        return False
    val = rel.get("validity")
    if isinstance(val, dict) and (val.get("to") or val.get("from")):
        cur = at or _now_utc()
        to_ = _parse_ts(val.get("to"))
        frm = _parse_ts(val.get("from"))
        try:
            if to_ is not None and to_ < cur:
                return False
            if frm is not None and frm > cur:
                return False
        except TypeError:
            # naive/aware mismatch — be permissive, never break traversal.
            return True
    return True


__all__ = [
    "CONFIDENCE_THRESHOLD",
    "MAX_DEPTH",
    "DFS_SCORE_THRESHOLD",
    "DEPTH_DECAY",
    "relation_is_live",
]
