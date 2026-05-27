"""v0.4 Sprint 5 PR-T2.B — A-path contradiction routing wire.

Wires the deterministic ``classify_contradiction`` decision into
the production CASCADE / EVENT dispatch.

This PR delivers ONLY the **A-path** (cascade routing). The B-path
(supersede chain wiring) lands at PR-T2.C — calling B here raises
``NotImplementedError`` so a premature integration crashes loudly
rather than silently no-op'ing.

Surface
-------

  ``route_a_invalidate(bad_doc_id, entity_root, *, audit_emit=None)``
      Run the existing ``cascade_remove_doc_from_sources`` for the
      wrong source + emit a ``mutation_type=invalidated`` audit
      row. Returns the cascade counts dict + the audit payload.

  ``dispatch_contradiction(old_edge, new_fact, *, now, entity_root,
                           bad_doc_id_for_a=None, audit_emit=None)``
      End-to-end: calls ``classify_contradiction`` → dispatches.
      A → ``route_a_invalidate`` (requires ``bad_doc_id_for_a``).
      B → raises ``NotImplementedError`` (PR-T2.C).
      ignore → returns ``{"action": "ignore"}``.

Design notes
------------

- **A path narrowness.** The routing wire does NOT add new CASCADE
  logic — it calls the existing ``cascade_remove_doc_from_sources``
  unchanged. The PR's surface is two functions + an audit
  side-effect.
- **Bad-source identification stays at the caller.** The router
  takes ``bad_doc_id_for_a`` explicitly rather than guessing which
  source on ``old_edge`` is the wrong one. The caller (the
  ingestion path that detected the contradiction) knows which doc
  was just rejected — passing that doc_id through is one line.
- **mutation_type audit invariant.** The audit row carries
  ``mutation_type="invalidated"`` so the T7 replay primitive
  (``reconstruct_view_at``) filters correctly — CASCADE
  invalidations are gone for replay; the audit row is the only
  trace.
- **Default audit emitter.** When ``audit_emit`` is ``None``, falls
  back to ``core.audit_bridge.mirror_to_audit_db`` (the same
  mirror the reason:* events use). Tests pass an in-memory
  capture function to assert the payload shape without touching
  the SQLite DB.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from core.lifecycle.contradiction_arbiter import (
    classify_contradiction,
)
from core.lifecycle.schema import T1_MUTATION_INVALIDATED


AuditEmit = Callable[[Dict[str, Any]], None]


def _default_audit_emit(payload: Dict[str, Any]) -> None:
    """Mirror to the audit_log SQLite via core.audit_bridge. Never
    raises — audit failure must not block the cascade write path
    (same pattern as ``trace_synth_call``)."""
    try:
        from core.audit_bridge import mirror_to_audit_db
        mirror_to_audit_db(payload)
    except Exception:
        pass


def route_a_invalidate(
    bad_doc_id: str,
    entity_root: Path | str,
    *,
    audit_emit: Optional[AuditEmit] = None,
) -> Dict[str, Any]:
    """A-path: cascade-remove the wrong source + emit audit row.

    Args:
        bad_doc_id: the doc_id of the source identified as wrong
            (by the caller's contradiction-detection logic).
            ``cascade_remove_doc_from_sources`` removes this from
            every edge that references it; manual sources and
            non-matching doc_ids are preserved unchanged (per the
            existing CASCADE contract — see
            ``core/cascade/_delete.py:cascade_remove_doc_from_sources``
            docstring).
        entity_root: wiki entity root (typically ``wiki/entity``
            or the wiki snapshot the cascade should target).
        audit_emit: optional callback for the audit row. Defaults
            to ``core.audit_bridge.mirror_to_audit_db``.

    Returns:
        ``{"action": "invalidate", "bad_doc_id": …, "counts": …,
           "audit_payload": …}``

        ``counts`` is the dict returned by
        ``cascade_remove_doc_from_sources``:
        ``entities_scanned`` / ``entities_touched`` /
        ``relations_recomputed`` / ``relations_dropped``.

        ``audit_payload`` is the dict that was emitted — useful
        for callers that want to chain audit writes (e.g., write a
        compound row for a multi-step ingestion).

    Raises:
        ValueError if ``bad_doc_id`` is empty or
        ``entity_root`` doesn't exist.
    """
    if not bad_doc_id or not isinstance(bad_doc_id, str):
        raise ValueError(f"bad_doc_id must be a non-empty str, got {bad_doc_id!r}")
    root = Path(entity_root)
    if not root.exists():
        raise ValueError(f"entity_root does not exist: {root}")

    # Lazy-import the cascade to avoid pulling Phase-C dependencies
    # at module import time. The router stays import-light.
    from core.cascade import cascade_remove_doc_from_sources

    counts = cascade_remove_doc_from_sources(bad_doc_id, root)

    audit_payload: Dict[str, Any] = {
        "endpoint":      "lifecycle:invalidate",
        "role":          "system",
        "mutation_type": T1_MUTATION_INVALIDATED,
        "bad_doc_id":    bad_doc_id,
        "entities_scanned":     counts.get("entities_scanned", 0),
        "entities_touched":     counts.get("entities_touched", 0),
        "relations_recomputed": counts.get("relations_recomputed", 0),
        "relations_dropped":    counts.get("relations_dropped", 0),
    }
    emitter = audit_emit or _default_audit_emit
    emitter(audit_payload)

    return {
        "action":         "invalidate",
        "bad_doc_id":     bad_doc_id,
        "counts":         counts,
        "audit_payload":  audit_payload,
    }


def dispatch_contradiction(
    old_edge: dict,
    new_fact: dict,
    *,
    now: datetime,
    entity_root: Optional[Path | str] = None,
    bad_doc_id_for_a: Optional[str] = None,
    audit_emit: Optional[AuditEmit] = None,
) -> Dict[str, Any]:
    """Full A/B dispatch in one call. Calls
    ``classify_contradiction`` + routes.

    Args:
        old_edge: existing v0.4-shaped edge.
        new_fact: the contradicting observation (edge or source
            shape — same dual-shape the classifier accepts).
        now: UTC-aware ``datetime``.
        entity_root: required for A-path (cascade target). Optional
            for B / ignore.
        bad_doc_id_for_a: required when ``classify_contradiction``
            returns ``A_invalidate``. Caller's contradiction-detection
            logic supplies this.
        audit_emit: optional audit callback (A-path only — B-path
            audit lands at PR-T2.C).

    Returns:
        For A_invalidate: see ``route_a_invalidate`` return.
        For ignore: ``{"action": "ignore", "label": "ignore"}``.

    Raises:
        ValueError if A_invalidate is selected but required args
        (``entity_root`` / ``bad_doc_id_for_a``) are missing.
        NotImplementedError if classifier returns B_supersede —
        wiring lands at PR-T2.C. Until then the caller must not
        invoke dispatch on cases that would route to B (or accept
        the loud failure as a guard against premature integration).
    """
    label = classify_contradiction(old_edge, new_fact, now=now)

    if label == "ignore":
        return {"action": "ignore", "label": "ignore"}

    if label == "A_invalidate":
        if entity_root is None:
            raise ValueError(
                "A_invalidate dispatch requires entity_root (cascade target)"
            )
        if not bad_doc_id_for_a:
            raise ValueError(
                "A_invalidate dispatch requires bad_doc_id_for_a — caller's "
                "contradiction-detection logic identifies which source on "
                "old_edge is the wrong one"
            )
        return route_a_invalidate(
            bad_doc_id_for_a, entity_root, audit_emit=audit_emit,
        )

    if label == "B_supersede":
        raise NotImplementedError(
            "B_supersede dispatch lands at PR-T2.C — until then, callers "
            "must filter out B-path contradictions before invoking "
            "dispatch_contradiction. (See PR-T7.A supersede_edge for the "
            "primitive the T2.C wire will call.)"
        )

    # Defensive — classifier returned a label we don't know about.
    # Reachable only if classify_contradiction is extended without a
    # matching dispatch arm here.
    raise RuntimeError(f"unknown contradiction label: {label!r}")


__all__ = [
    "AuditEmit",
    "route_a_invalidate",
    "dispatch_contradiction",
]
