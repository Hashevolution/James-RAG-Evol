"""v0.4.1 PR-T2.D-2 + T2.D-2.b — ingestion-path contradiction dispatch.

Wires the v0.4.0 contradiction infrastructure
(``classify_contradiction`` + ``supersede_edge``) into the
``core/wiki_generator/_merge.py`` merge loop. Pre-merge hook: before
new relations are sources-appended, identify contradiction candidates
via PR-T2.D-1's detector, run the classifier, and apply the resulting
label.

T2.D-2.b extends T2.D-2 with proper A_invalidate handling via the
``PendingCascade`` deferred-execution pattern — the dispatcher
records cascade requests but doesn't execute them; the caller
(``_merge.py``) applies them AFTER writing back the entity it had
loaded in memory. This sidesteps the write-after-read race that
T2.D-2 dropped A_invalidate over.

## Trigger policy LOCK — B (적극)

Per v0.4.1 entry memo §2 + this session's added LOCK. Any
``(head, predicate)`` match on the same entity qualifies as a
contradiction candidate; the classifier (already deterministic
v0.4.0 #541) decides A_invalidate / B_supersede / ignore.

## Scope — three labels handled differently

| label | how the dispatcher handles it | rationale |
|---|---|---|
| ``B_supersede`` | call ``supersede_edge`` in-line → ``new_edge`` appended to ``existing_rels``, ``old_edge`` mutated in place. new_rel filtered out. | pure function, no file I/O, race-free |
| ``ignore`` | drop ``new_rel`` from the merge output | the classifier already said "duplicate"; nothing to do |
| ``A_invalidate`` | record a ``PendingCascade`` for the lowest-weight non-manual source on existing_rel + **keep new_rel** so the regular merge loop appends it as a fresh edge. Caller runs the cascade post-write via ``apply_pending_cascades``. | ``cascade_remove_doc_from_sources`` mutates entity files; deferring until AFTER ``_merge.py`` writes prevents the write-after-read race. |

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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from core.cascade._delete import cascade_remove_doc_from_sources
from core.lifecycle.contradiction_arbiter import (
    classify_contradiction,
)
from core.lifecycle.contradiction_ingest_detector import (
    find_contradiction_candidates,
    to_classifier_edge_shape,
)
from core.lifecycle.supersede_chain import supersede_edge


AuditEmit = Callable[[Dict[str, Any]], None]


@dataclass
class PendingCascade:
    """A cascade request captured during dispatch but not yet executed.

    The caller (``_merge.py``) runs ``apply_pending_cascades`` after
    writing back the entity it had loaded in memory, so the cascade's
    file mutations don't race with the merge's pending write.
    """
    bad_doc_id: str
    pattern: str         # "different_tail" | "divergent_validity"
    audit_payload: Dict[str, Any] = field(default_factory=dict)


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
        ``(rels_to_merge, dispatch_log, pending_cascades)``:
          - ``rels_to_merge``: ``new_rels`` with B_supersede/ignore
            cases filtered out. A_invalidate cases stay so the regular
            sources-append path adds the new rel as a fresh edge
            (cascade runs after the write removes the wrong source).
          - ``dispatch_log``: per-decision audit entries
            (``new_rel``, ``existing_rel``, ``pattern``, ``label``,
            ``action``). Useful for tests + ``audit_log`` mirroring.
          - ``pending_cascades``: deferred ``PendingCascade`` requests
            the caller MUST execute (via ``apply_pending_cascades``)
            after writing back its in-memory entity state — otherwise
            A_invalidate decisions are silently dropped.
    """
    emit = audit_emit or _noop_audit
    rels_to_merge: List[Dict[str, Any]] = []
    dispatch_log: List[Dict[str, Any]] = []
    pending_cascades: List[PendingCascade] = []

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
            # T2.D-2.b — collect a PendingCascade for the lowest-weight
            # non-manual source on existing_rel + KEEP new_rel in
            # rels_to_merge. The regular merge loop appends new_rel
            # as a fresh edge; the caller runs the cascade
            # post-write so it doesn't race with the in-memory
            # entity edit.
            bad_doc_id = _pick_cascade_target(existing_rel)
            if bad_doc_id is None:
                # No cascadeable source on existing_rel — keep new_rel
                # and log as no-op. Defensive: an edge with no usable
                # source shouldn't have made it to dispatch, but if
                # it did we don't manufacture an invalid cascade.
                log_entry["action"] = "a_invalidate_no_cascade_target"
                rels_to_merge.append(new_rel)
                emit({
                    "endpoint":      "lifecycle:ingest_contradiction",
                    "role":          "system",
                    "mutation_type": "invalidated_skipped",
                    "pattern":       pattern,
                    "note":          "existing_rel has no cascadeable source",
                })
            else:
                audit_payload = {
                    "endpoint":      "lifecycle:ingest_contradiction",
                    "role":          "system",
                    "mutation_type": "invalidated",
                    "pattern":       pattern,
                    "bad_doc_id":    bad_doc_id,
                    "old_edge_id":   existing_rel.get("id"),
                }
                pending_cascades.append(PendingCascade(
                    bad_doc_id=bad_doc_id,
                    pattern=pattern,
                    audit_payload=audit_payload,
                ))
                rels_to_merge.append(new_rel)
                log_entry["action"] = "a_invalidate_cascade_pending"
                log_entry["bad_doc_id"] = bad_doc_id
                emit(audit_payload)

        else:
            # Defensive — classifier returned a label we don't
            # know. Keep new_rel so we don't silently lose data.
            log_entry["action"] = "kept_unknown_label"
            rels_to_merge.append(new_rel)

        dispatch_log.append(log_entry)

    return rels_to_merge, dispatch_log, pending_cascades


def _pick_cascade_target(existing_rel: Dict[str, Any]) -> Optional[str]:
    """Pick the doc_id whose source should be cascaded out of the
    existing edge. Conservative heuristic: lowest-weight non-manual
    source. Returns ``None`` if no eligible source.

    Manual sources are NEVER returned — ``cascade_remove_doc_from_sources``
    preserves them by design (manual role = operator-curated, immune
    from cascade), and picking one as the cascade target would be a
    no-op that hides the actual cascade miss.
    """
    sources = existing_rel.get("sources") if isinstance(existing_rel, dict) else None
    if not isinstance(sources, list) or not sources:
        return None
    eligible: List[Tuple[float, str]] = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        doc_id = s.get("doc_id")
        role = s.get("role")
        if not isinstance(doc_id, str) or not doc_id:
            continue
        if role == "manual":
            continue
        weight = s.get("weight")
        weight_f = float(weight) if isinstance(weight, (int, float)) else 0.0
        eligible.append((weight_f, doc_id))
    if not eligible:
        return None
    eligible.sort(key=lambda x: x[0])
    return eligible[0][1]


def apply_pending_cascades(
    pending_cascades: List[PendingCascade],
    entity_root: Union[Path, str],
    *,
    audit_emit: Optional[AuditEmit] = None,
) -> List[Dict[str, Any]]:
    """Execute the cascade requests captured by
    ``dispatch_contradictions_for_merge`` against the wiki on disk.

    Call AFTER the caller writes back any in-memory entity state.
    Otherwise the cascade can race with the pending write (T2.D-2's
    original bug).

    Args:
        pending_cascades: list from ``dispatch_contradictions_for_merge``.
        entity_root: directory whose ``rglob("*.md")`` is the wiki's
            entity file set (typically ``wiki/entity/prod/`` or
            equivalent). Each cascade removes ``bad_doc_id`` from
            every entity file under this root.
        audit_emit: optional callback for emitting post-cascade
            audit rows (one per cascade), enriched with the
            ``cascade_remove`` counts dict.

    Returns:
        list of per-cascade result dicts, each ``{"bad_doc_id": …,
        "counts": {entities_scanned, entities_touched,
        relations_recomputed, relations_dropped}}``. Empty list
        when no cascades were pending.
    """
    if not pending_cascades:
        return []
    emit = audit_emit or _noop_audit
    root = Path(entity_root)
    results: List[Dict[str, Any]] = []
    for pc in pending_cascades:
        counts = cascade_remove_doc_from_sources(pc.bad_doc_id, root)
        results.append({
            "bad_doc_id": pc.bad_doc_id,
            "counts":     counts,
        })
        payload = dict(pc.audit_payload)
        payload["cascade_counts"] = counts
        payload.setdefault("mutation_type", "invalidated")
        payload["mutation_type"] = "invalidated_applied"
        emit(payload)
    return results


__all__ = [
    "AuditEmit",
    "PendingCascade",
    "apply_pending_cascades",
    "dispatch_contradictions_for_merge",
]
