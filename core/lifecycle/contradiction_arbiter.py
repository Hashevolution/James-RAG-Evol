"""v0.4 Sprint 5 PR-T2.A — A/B contradiction classifier.

Single deterministic function that decides how to route a contradicting
observation against an existing edge:

  - **A_invalidate** — the new fact corrects a wrong source. Layer 3
    CASCADE removes the wrong source; downstream confidence
    recomputes; the edge itself may survive on the surviving sources.
  - **B_supersede** — the world genuinely changed. T7 supersede
    creates a new edge, preserves the old one for replay, links via
    ``status.superseded_by``. No CASCADE.
  - **ignore** — duplicate / equivalent observation. Keep the
    existing edge, log an audit row for the duplicate event.

LLM-free by design. The classifier is the **Mem0 differentiator**
(Mem0's memory layer routes via an LLM-judge; JAMES routes via
this deterministic rule tree). Pure function — no I/O, no clock
side-effects (``now`` is an explicit argument).

Decision rules (in order; first match wins):

  1. **B_supersede** — ``new_fact.valid_from`` is strictly later
     than ``old_edge.validity.to`` (or ``now`` when ``validity.to``
     is open). The world moved on; the old edge is historical, the
     new one is the current truth.

  2. **A_invalidate** — ``new_fact`` carries a higher-confidence
     source AND its ``timestamp`` is at-or-before
     ``old_edge.validity.from``. A retroactive correction —
     the old edge was wrong even in its own time window.

  3. **ignore** — keys match, ``new_fact.timestamp`` falls inside
     ``old_edge.validity`` window, no confidence delta. Duplicate
     observation, not a contradiction.

  4. **B_supersede** (default) — edge cases (missing timestamps,
     missing confidence). Safer than CASCADE (history preserved,
     trivial rollback); easier to undo than a destructive op.

The rules deliberately do NOT check the (subject, predicate) keys
match — that's the caller's responsibility (the caller already
identified ``old_edge`` as the edge the new observation contradicts).
The classifier only decides **how** to apply the contradiction
once the caller has identified **which** edge it belongs to.

What this module is NOT
-----------------------

- **Not a routing wire.** The CASCADE / supersede call sites land
  at PR-T2.B / PR-T2.C respectively. This module returns a literal
  label; the caller dispatches.
- **Not a confidence calculator.** Uses
  ``core.relations_schema.compute_confidence_from_sources`` to
  compare; doesn't reimplement.
- **Not a validity reasoner.** Edge cases (missing ``validity.to``,
  ``valid_from``) collapse to the rule-4 default; doesn't try to
  infer windows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from core.lifecycle.schema import (
    T7_EDGE_FIELD_VALIDITY,
)


# Literal return type — the three labels the downstream callers
# (PR-T2.B/C wiring) dispatch on.
ContradictionClass = Literal["A_invalidate", "B_supersede", "ignore"]


def _parse_iso(value: Any) -> Optional[datetime]:
    """Lenient ISO 8601 parse. ``None`` for malformed / missing /
    non-string. Mirrors the cascade module's parser semantics so
    the same input shapes flow through both."""
    if value is None or not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _new_fact_valid_from(new_fact: dict) -> Optional[datetime]:
    """Extract ``new_fact.valid_from`` — the moment the new fact
    becomes true. Caller-shaped: may live at the top level or
    under a ``validity`` sub-dict (matches both v0.4 edge and
    source schemas)."""
    if not isinstance(new_fact, dict):
        return None
    direct = _parse_iso(new_fact.get("valid_from"))
    if direct is not None:
        return direct
    validity = new_fact.get("validity")
    if isinstance(validity, dict):
        return _parse_iso(validity.get("from"))
    return None


def _new_fact_timestamp(new_fact: dict) -> Optional[datetime]:
    """Extract ``new_fact.timestamp`` — when the new observation
    was recorded. Falls back to ``ts`` (source-shape) for callers
    that pass a single-source dict."""
    if not isinstance(new_fact, dict):
        return None
    ts = _parse_iso(new_fact.get("timestamp"))
    if ts is not None:
        return ts
    return _parse_iso(new_fact.get("ts"))


def _old_edge_validity_to(old_edge: dict) -> Optional[datetime]:
    """Extract ``old_edge.validity.to`` (the upper bound of the
    edge's truth window). ``None`` = open (still considered true
    at ``now`` for rule purposes)."""
    if not isinstance(old_edge, dict):
        return None
    validity = old_edge.get(T7_EDGE_FIELD_VALIDITY)
    if not isinstance(validity, dict):
        return None
    return _parse_iso(validity.get("to"))


def _old_edge_validity_from(old_edge: dict) -> Optional[datetime]:
    if not isinstance(old_edge, dict):
        return None
    validity = old_edge.get(T7_EDGE_FIELD_VALIDITY)
    if not isinstance(validity, dict):
        return None
    return _parse_iso(validity.get("from"))


def _best_source_confidence(edge: dict) -> Optional[float]:
    """Highest ``weight`` across the edge's sources (Mem0-style
    point estimate, not the noisy-OR aggregate). Rule 2 wants the
    single best evidence weight to compare against the new fact's.
    Returns None when no source has a numeric weight."""
    if not isinstance(edge, dict):
        return None
    sources = edge.get("sources")
    if not isinstance(sources, list):
        return None
    best: Optional[float] = None
    for s in sources:
        if not isinstance(s, dict):
            continue
        w = s.get("weight")
        if not isinstance(w, (int, float)):
            continue
        wf = float(w)
        if best is None or wf > best:
            best = wf
    return best


def _new_fact_confidence(new_fact: dict) -> Optional[float]:
    """Single-source view of the new fact's confidence. The caller
    typically passes the new observation as either an edge-shape
    (look at ``sources[0].weight``) or a source-shape (top-level
    ``weight`` / ``confidence``).
    """
    if not isinstance(new_fact, dict):
        return None
    # source-shape top-level
    w = new_fact.get("weight")
    if isinstance(w, (int, float)):
        return float(w)
    c = new_fact.get("confidence")
    if isinstance(c, (int, float)):
        return float(c)
    # edge-shape: first source
    sources = new_fact.get("sources")
    if isinstance(sources, list) and sources:
        first = sources[0]
        if isinstance(first, dict):
            fw = first.get("weight")
            if isinstance(fw, (int, float)):
                return float(fw)
    return None


# ─── Decision function ────────────────────────────────────────────


def classify_contradiction(
    old_edge: dict,
    new_fact: dict,
    *,
    now: datetime,
) -> ContradictionClass:
    """Decide A_invalidate / B_supersede / ignore.

    Args:
        old_edge: existing edge that the new observation contradicts.
            Must be a v0.4-shaped dict (run
            ``apply_v04_edge_defaults`` first if you loaded a raw
            v0.3 edge — though missing fields are tolerated and
            fall through to the rule-4 default).
        new_fact: the contradicting observation. Caller-shaped —
            may be a full edge dict or a single-source dict. The
            classifier reads ``valid_from``, ``timestamp`` / ``ts``,
            ``weight`` / ``confidence`` defensively.
        now: UTC-aware current time. Used when ``old_edge.validity.to``
            is open (None) — rule 1 compares against ``now`` in that
            case.

    Returns:
        ``"A_invalidate"`` / ``"B_supersede"`` / ``"ignore"`` —
        downstream callers (PR-T2.B/C) dispatch on this.

    Raises:
        ValueError if ``now`` is not a timezone-aware datetime.
        Missing / malformed fields on ``old_edge`` or ``new_fact``
        are NOT errors — they trigger the rule-4 default
        (B_supersede).
    """
    if not isinstance(now, datetime):
        raise ValueError(f"now must be datetime, got {type(now).__name__}")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (UTC recommended)")

    # ─── Rule 1 — world changed (supersede) ────────────────────────
    new_vf = _new_fact_valid_from(new_fact)
    old_vt = _old_edge_validity_to(old_edge)
    if new_vf is not None:
        cutoff = old_vt if old_vt is not None else now
        if new_vf > cutoff:
            return "B_supersede"

    # ─── Rule 2 — retroactive correction (invalidate) ──────────────
    old_vf = _old_edge_validity_from(old_edge)
    new_ts = _new_fact_timestamp(new_fact)
    new_conf = _new_fact_confidence(new_fact)
    old_conf = _best_source_confidence(old_edge)
    if (
        new_conf is not None
        and old_conf is not None
        and new_conf > old_conf
        and new_ts is not None
        and old_vf is not None
        and new_ts <= old_vf
    ):
        return "A_invalidate"

    # ─── Rule 3 — duplicate (ignore) ───────────────────────────────
    # Inside old edge's validity window + no confidence delta.
    if (
        new_ts is not None
        and old_vf is not None
        and new_ts >= old_vf
        and (old_vt is None or new_ts < old_vt)
    ):
        # Inside the window. Now check confidence equivalence —
        # treat None == None as "equivalent" so the rule fires when
        # neither side carries weight info.
        if new_conf == old_conf:
            return "ignore"

    # ─── Rule 4 — default safer-than-CASCADE ───────────────────────
    return "B_supersede"


__all__ = [
    "ContradictionClass",
    "classify_contradiction",
]
