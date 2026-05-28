"""v0.4.1 PR-T2.D-2 — ingestion-path contradiction dispatch.

Wires the v0.4.0 contradiction infrastructure
(``classify_contradiction`` + ``supersede_edge``) into the
``core/wiki_generator/_merge.py`` merge loop. Pre-merge hook: before
new relations are sources-appended, identify contradiction candidates
via PR-T2.D-1's detector, run the classifier, and apply the
no-file-I/O branches in-line.

## Trigger policy LOCK — B (적극)

Per v0.4.1 entry memo §2 + this session's added LOCK. Any
``(head, predicate)`` match on the same entity qualifies as a
contradiction candidate; the classifier (already deterministic
v0.4.0 #541) decides A_invalidate / B_supersede / ignore.

## Scope split — three labels handled differently

| label | how this PR handles it | rationale |
|---|---|---|
| ``B_supersede`` | call ``supersede_edge`` in-line → ``new_edge`` appended to ``existing_rels``, ``old_edge`` mutated in place. new_rel filtered out. | pure function, no file I/O, race-free |
| ``ignore`` | drop ``new_rel`` from the merge output | the classifier already said "duplicate"; nothing to do |
| ``A_invalidate`` | **deferred to T2.D-2.b** — this PR logs only. ``new_rel`` is dropped (cascade would handle the bad source). | ``route_a_invalidate`` calls ``cascade_remove_doc_from_sources`` which mutates entity files while ``_merge.py`` has the same files open in memory → write-after-read race. T2.D-2.b restructures the merge flow to handle this safely. |

## Flag-gated

``JAMES_T2D_INGEST_DISPATCH=1`` enables the dispatch hook. Default
OFF preserves byte-identical legacy behavior. After T2.D-3
acceptance (step7 v6 CEO-change bench), a separate small PR flips
the default ON.

## What this module is NOT

- Not a full ``dispatch_contradiction`` re-implementation. The
  router (``core.lifecycle.contradiction_router``) stays intact;
  this module is the ingestion-specific pre-merge hook that uses
  the same building blocks differently because of the in-memory
  state ownership.
- Not idempotent under repeated ingestion. Calling this twice on
  the same ``(new_rels, existing_rels)`` may double-supersede
  (creating two new edges where one is enough). The
  ``_merge.py`` caller invokes it once per merge.
- Not a CASCADE path. A_invalidate is logged for the audit trail
  but no source removal happens in this PR (T2.D-2.b will).

Pure function (no I/O) for the B + ignore + log paths. A_invalidate
audit row is emitted via the optional ``audit_emit`` callback —
caller can persist to ``audit_log`` if desired, this module does
not import the audit bridge directly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.lifecycle.contradiction_arbiter import (
    classify_contradiction,
)
from core.lifecycle.contradiction_ingest_detector import (
    find_contradiction_candidates,
    to_classifier_edge_shape,
)
from core.lifecycle.supersede_chain import supersede_edge


AuditEmit = Callable[[Dict[str, Any]], None]


def _noop_audit(_payload: Dict[str, Any]) -> None:
    """No-op default — callers that don't pass ``audit_emit`` just
    get the in-memory dispatch results in the returned log without
    any side-channel emission."""
    return None


def _parse_iso(value: Any) -> Optional[datetime]:
    """Lenient ISO 8601 parse mirroring ``contradiction_arbiter._parse_iso``."""
    if value is None or not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def dispatch_contradictions_for_merge(
    new_rels: List[Dict[str, Any]],
    existing_rels: List[Dict[str, Any]],
    *,
    ingest_doc_id: str,
    ingest_ts: str,
    audit_emit: Optional[AuditEmit] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Pre-merge contradiction dispatch.

    For each new_rel in ``new_rels``:
      1. Run PR-T2.D-1's detector against ``existing_rels``.
      2. If candidates exist, take the first one (multi-candidate
         dispatch ordering is T2.D-2.b territory).
      3. Convert both sides to classifier shape, call
         ``classify_contradiction``.
      4. Apply the label:
         - **B_supersede** — call ``supersede_edge``, append the
           new edge to ``existing_rels``, drop new_rel from the
           returned list.
         - **ignore** — drop new_rel.
         - **A_invalidate** — log + drop new_rel (cascade deferred).
      5. If no candidates, pass new_rel through unchanged.

    ``existing_rels`` IS MUTATED IN PLACE — the caller's frontmatter
    list reference picks up the supersede chain links (matches
    ``supersede_edge``'s contract).

    Args:
        new_rels: relations the caller is about to merge (ingestion
            shape: ``target`` + ``type``/``label`` + optional
            ``sources``).
        existing_rels: the entity's current relations (from
            frontmatter). MUTATED for B_supersede paths.
        ingest_doc_id: document being ingested. Used as ``new_fact``
            timestamp / source attribution when the new rel doesn't
            carry its own.
        ingest_ts: ISO 8601 string of ingest moment. Used as
            ``supersede_ts`` for B paths + ``new_fact.timestamp``
            for the classifier.
        audit_emit: optional callback for emitting audit rows
            (``mutation_type=invalidated`` / ``superseded`` /
            ``ignored``). Defaults to no-op.

    Returns:
        ``(rels_to_merge, dispatch_log)``:
          - ``rels_to_merge``: ``new_rels`` with contradicting ones
            filtered out. The caller's regular sources-append path
            handles whatever remains.
          - ``dispatch_log``: per-decision audit entries
            (``new_rel``, ``existing_rel``, ``pattern``, ``label``,
            ``action``). Useful for tests + future ``audit_log`` mirroring.
    """
    emit = audit_emit or _noop_audit
    rels_to_merge: List[Dict[str, Any]] = []
    dispatch_log: List[Dict[str, Any]] = []

    now_dt = _parse_iso(ingest_ts) or datetime.now(timezone.utc)

    for new_rel in new_rels:
        if not isinstance(new_rel, dict):
            continue
        candidates = find_contradiction_candidates(new_rel, existing_rels)
        if not candidates:
            rels_to_merge.append(new_rel)
            continue

        # T2.D-2 scope: dispatch on first candidate only. Multi-candidate
        # ordering (e.g. dispatch on P1 first, then P2) is T2.D-2.b.
        existing_rel, pattern = candidates[0]
        old_shape = to_classifier_edge_shape(existing_rel)
        new_shape = to_classifier_edge_shape(
            new_rel, ingest_doc_id=ingest_doc_id, ingest_ts=ingest_ts,
        )
        label = classify_contradiction(old_shape, new_shape, now=now_dt)

        log_entry: Dict[str, Any] = {
            "new_rel":      new_rel,
            "existing_rel": existing_rel,
            "pattern":      pattern,
            "label":        label,
        }

        if label == "ignore":
            log_entry["action"] = "drop_new_rel_ignored"
            emit({
                "endpoint":      "lifecycle:ingest_contradiction",
                "role":          "system",
                "mutation_type": "ignored",
                "pattern":       pattern,
            })

        elif label == "B_supersede":
            new_edge, _mutated_old = supersede_edge(
                existing_rel, new_rel, now_dt,
            )
            existing_rels.append(new_edge)
            log_entry["action"] = "supersede_applied"
            log_entry["new_edge_id"] = new_edge.get("id")
            log_entry["old_edge_id"] = existing_rel.get("id")
            emit({
                "endpoint":      "lifecycle:ingest_contradiction",
                "role":          "system",
                "mutation_type": "superseded",
                "old_edge_id":   existing_rel.get("id"),
                "new_edge_id":   new_edge.get("id"),
                "superseded_at": now_dt.isoformat(),
            })

        elif label == "A_invalidate":
            # T2.D-2.b territory — cascade_remove is deferred so
            # _merge.py doesn't race with cascade on the same entity
            # file. This PR logs the decision; the new_rel is
            # dropped on the assumption that the deferred cascade
            # would have invalidated the conflicting source.
            log_entry["action"] = "a_invalidate_logged_deferred"
            emit({
                "endpoint":      "lifecycle:ingest_contradiction",
                "role":          "system",
                "mutation_type": "invalidated_deferred",
                "pattern":       pattern,
                "note":          "cascade_remove deferred to T2.D-2.b",
            })

        else:
            # Defensive — classifier returned a label we don't
            # know. Keep new_rel so we don't silently lose data.
            log_entry["action"] = "kept_unknown_label"
            rels_to_merge.append(new_rel)

        dispatch_log.append(log_entry)

    return rels_to_merge, dispatch_log


__all__ = [
    "AuditEmit",
    "dispatch_contradictions_for_merge",
]
