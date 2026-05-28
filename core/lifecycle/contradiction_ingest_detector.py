"""v0.4.1 PR-T2.D-1 — contradiction detector for ingestion-path wiring.

Identifies pairs of ``(existing_rel, new_rel)`` that should be routed
through ``dispatch_contradiction`` (PR-T2.C, already in v0.4.0) instead
of being silently appended by
``_merge_relations_into_existing_entity`` in ``core/wiki_generator/_merge.py``.

Trigger policy is **B** (적극 — per v0.4.1 entry memo §2 + this session's
additional LOCK): any ``(head, predicate)`` match qualifies as a
contradiction candidate; the deterministic classifier decides
A_invalidate / B_supersede / ignore from there. Caller's ingestion
code only needs to identify "which existing relations are contradiction
candidates" — the classifier handles "how to apply".

Two patterns this detector recognizes:

  P1 — ``different_tail``: existing_rel has same predicate as new_rel
       but different target. Canonical case: CEO change. Same
       ``(head, predicate=CEO_OF)`` but target Dario vs target NewName.

  P2 — ``divergent_validity``: existing_rel has same ``(target, predicate)``
       as new_rel but the existing edge carries v0.4 lifecycle metadata
       (``validity`` / ``status`` / ``mutation_type``) that the new
       observation may close or contradict. E.g., new observation
       has explicit ``valid_until`` that closes the existing edge's
       open validity.

Out of scope (T2.D-1):

- Calling ``dispatch_contradiction``. T2.D-2 wires this detector's
  output into ``_merge.py``.
- Updating existing entities. The detector is a pure read.
- Schema validation. ``core/relations_schema.py`` owns that.
- The actual A/B/ignore decision. ``contradiction_arbiter.classify_contradiction``
  owns that, called by ``dispatch_contradiction``.

Pure function. No I/O, no clock side-effects.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

# Literal pattern labels — kept as plain str for v0.4.1 to avoid
# importing typing.Literal across all Python versions; promote to
# Literal["different_tail", "divergent_validity"] in a follow-up
# if/when we drop Python 3.10 support.
ContradictionPattern = str


def _default_predicate_normalizer(label: str) -> str:
    """Falls back to ``core.ontology.normalize_relation`` when
    available, identity otherwise. Mirrors the fallback pattern in
    ``core/wiki_generator/_merge.py`` so both sites compare predicates
    the same way."""
    try:
        from core.ontology import normalize_relation as _norm  # type: ignore
        return _norm(label) or label
    except Exception:
        return label


def _extract_predicate(rel: Dict[str, Any]) -> Optional[str]:
    """The classifier matches on ``(head, predicate, tail)``. For
    contradiction detection we use the relation ``type`` (preferred)
    or ``label`` (fallback) as the predicate identifier. Returns
    ``None`` for malformed input."""
    if not isinstance(rel, dict):
        return None
    t = rel.get("type")
    if isinstance(t, str) and t:
        return t
    label = rel.get("label")
    if isinstance(label, str) and label:
        return label
    return None


def _extract_target(rel: Dict[str, Any]) -> Optional[str]:
    if not isinstance(rel, dict):
        return None
    target = rel.get("target")
    if isinstance(target, str) and target:
        return target
    return None


def _has_v04_lifecycle(rel: Dict[str, Any]) -> bool:
    """True if the relation carries any v0.4 lifecycle metadata
    (``validity`` / ``status`` / ``mutation_type``).

    Pattern P2 only fires when this is True. Edges without any v0.4
    metadata are pre-v0.4 legacy — they're too schema-poor for the
    classifier to make a meaningful A/B/ignore call, so the
    sources-append path stays the right default for them.
    """
    if not isinstance(rel, dict):
        return False
    if rel.get("validity"):
        return True
    if rel.get("status"):
        return True
    if rel.get("mutation_type"):
        return True
    return False


def find_contradiction_candidates(
    new_rel: Dict[str, Any],
    existing_rels: List[Dict[str, Any]],
    *,
    predicate_normalizer: Callable[[str], str] = _default_predicate_normalizer,
) -> List[Tuple[Dict[str, Any], ContradictionPattern]]:
    """For a ``new_rel`` being ingested onto an entity, find existing
    relations on the SAME entity that may contradict it.

    Returns a list of ``(existing_rel, pattern)`` pairs ordered by
    discovery in ``existing_rels``. Empty list = no candidate (safe
    to merge as today).

    The head entity is implicit — both ``new_rel`` and ``existing_rels``
    are by construction relations of the SAME entity (the one
    ``_merge.py`` is merging into).

    Args:
        new_rel: the new relation about to be added (ingestion shape:
            at least ``target`` and ``type`` or ``label``).
        existing_rels: the entity's existing relations (loaded from
            its frontmatter).
        predicate_normalizer: optional callable to normalize predicate
            labels for comparison. Default falls back to
            ``core.ontology.normalize_relation`` with identity fallback.
    """
    new_target = _extract_target(new_rel)
    new_pred_raw = _extract_predicate(new_rel)
    if not new_pred_raw:
        return []
    new_pred = predicate_normalizer(new_pred_raw)

    candidates: List[Tuple[Dict[str, Any], ContradictionPattern]] = []
    for er in existing_rels:
        if not isinstance(er, dict):
            continue
        er_pred_raw = _extract_predicate(er)
        if not er_pred_raw:
            continue
        er_pred = predicate_normalizer(er_pred_raw)
        if er_pred != new_pred:
            continue
        er_target = _extract_target(er)

        # P1: same predicate, different target.
        if er_target and new_target and er_target != new_target:
            candidates.append((er, "different_tail"))
            continue

        # P2: same predicate + same target. Only flag when existing
        # has v0.4 lifecycle metadata; without it, the existing edge
        # is too schema-poor for the classifier to make a meaningful
        # A/B/ignore call and the sources-append path is the right
        # default.
        if er_target == new_target and _has_v04_lifecycle(er):
            candidates.append((er, "divergent_validity"))
            continue

    return candidates


def to_classifier_edge_shape(
    rel: Dict[str, Any],
    *,
    ingest_doc_id: Optional[str] = None,
    ingest_ts: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert an ingestion-shape relation to the classifier's
    expected ``old_edge`` / ``new_fact`` shape.

    The classifier (``contradiction_arbiter.classify_contradiction``)
    looks for:

      - ``validity.from`` / ``validity.to``
      - ``sources[].weight``
      - ``valid_from`` (top-level OR ``validity.from`` for new_fact)
      - ``timestamp`` / ``ts``

    Ingestion-shape relations have:

      - ``target`` / ``type`` / ``label``
      - ``sources``: ``List[{doc_id, ts, weight, role}]``
      - ``confidence`` (optional, top-level)

    The two shapes overlap on ``sources``. ``validity`` may or may
    not exist on the ingestion-shape rel (depends on whether the
    LLM extractor produced it). If ``sources`` is missing and
    ``ingest_doc_id`` is provided, a single-source view is
    synthesized so the classifier rule 2 (confidence comparison)
    can fire on a degenerate-but-still-typed shape.

    Malformed input (non-dict) returns an empty dict.
    """
    if not isinstance(rel, dict):
        return {}
    out = dict(rel)
    if "sources" not in out and ingest_doc_id is not None:
        weight = rel.get("confidence")
        if not isinstance(weight, (int, float)):
            weight = None
        out["sources"] = [{
            "doc_id": ingest_doc_id,
            "ts": ingest_ts,
            "weight": weight,
            "role": "ingest",
        }]
    return out


__all__ = [
    "ContradictionPattern",
    "find_contradiction_candidates",
    "to_classifier_edge_shape",
]
