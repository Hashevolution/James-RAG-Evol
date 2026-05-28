"""v0.4.1 PR-T6.C — derivation-aware invalidation cascade.

When a base fact is fully removed (sources=[]), edges whose
``derived_from`` references that base may need to invalidate too.
This module implements the **per-derivation-type semantics**
(Decision 4 LOCK clarification, 2026-05-28):

  - ``derivation: "transitive"`` (chain inference, e.g. A→B→C ⇒ A→C):
    **ANY-trigger**. Loss of any single base breaks the chain →
    invalidate the derived edge.

  - ``derivation: "inferred"`` (LLM-suggested single conclusion):
    **ANY-trigger**. The inference rests on the cited base; if that
    base is gone, the inference is suspect → invalidate.

  - ``derivation: "operator"`` (human-tagged multi-source support):
    **ALL-trigger**. Loss of one base leaves remaining bases as
    alternative support → keep alive. Only when ALL operator bases
    are gone does the edge invalidate.

Mixed-derivation edges (e.g. one transitive + two operator) are
evaluated jointly:

    invalidate := (any transitive/inferred base empty) OR
                  (operator entries exist AND all of them empty)

## What "invalidate" means here

Soft invalidate (matches T7 supersede pattern):
  - ``status.active = False``
  - ``mutation_type = "invalidated"``
  - ``sources`` preserved (the edge survives for T7 replay; CASCADE-
    style drop is a separate concern).

Audit row emitted per invalidation carries ``mutation_type =
"invalidated_by_cascade"`` so the T7 replay primitive can reconstruct
the derivation-cascade history from audit_log alone.

## What this module is NOT

- Not a transitive cascade. The function invalidates the directly-
  derived edges; if those edges are themselves base for further
  derivations, the caller calls ``invalidate_derived_facts`` again
  (or passes the full ``additional_empty_bases`` set up-front).
  Transitive auto-walk is a v0.4.2+ candidate.
- Not a CASCADE replacement. ``cascade_remove_doc_from_sources``
  handles source-level removal; T6.C handles derived-edge-level
  invalidation. They compose: cascade empties a base's sources,
  then ``invalidate_derived_facts(base_id)`` propagates downstream.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

import yaml

from core.lifecycle.schema import (
    T1_MUTATION_INVALIDATED,
    T6_DERIVATION_INFERRED,
    T6_DERIVATION_OPERATOR,
    T6_DERIVATION_TRANSITIVE,
    T6_EDGE_FIELD_DERIVED_FROM,
    T7_EDGE_FIELD_MUTATION_TYPE,
    T7_EDGE_FIELD_STATUS,
)


AuditEmit = Callable[[Dict[str, Any]], None]


# ANY-trigger derivation types (loss of any base → invalidate)
_ANY_TRIGGER_DERIVATIONS: frozenset[str] = frozenset({
    T6_DERIVATION_TRANSITIVE,
    T6_DERIVATION_INFERRED,
})


def _noop_audit(_payload: Dict[str, Any]) -> None:
    return None


def _split_frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---"):
        return None, text
    end = text.find("---", 3)
    if end < 0:
        return None, text
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except Exception:
        return None, text
    body_tail = text[end + 3:]
    return fm, body_tail


def _serialize_frontmatter(fm: dict, body_tail: str) -> str:
    return (
        "---\n"
        + yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                    sort_keys=True)
        + "---"
        + body_tail
    )


def _write_atomic(path: Path, text: str) -> None:
    """tempfile + os.replace — crash mid-write never half-updates."""
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def should_invalidate_edge(
    edge: Dict[str, Any],
    empty_bases: Set[str],
) -> bool:
    """Decision 4 (C-semantics) evaluator.

    Returns True iff the edge's ``derived_from`` evaluates to
    "invalidated" given the set of currently-empty base ids:

      - ANY transitive/inferred entry whose base is in ``empty_bases``
        → invalidate
      - operator entries exist AND ALL of them have bases in
        ``empty_bases`` → invalidate
      - Otherwise → preserve.

    Returns False for edges with empty/missing ``derived_from``
    (nothing to invalidate against).
    """
    if not isinstance(edge, dict):
        return False
    derived_from = edge.get(T6_EDGE_FIELD_DERIVED_FROM)
    if not isinstance(derived_from, list) or not derived_from:
        return False

    operator_entries: List[Dict[str, Any]] = []
    for entry in derived_from:
        if not isinstance(entry, dict):
            continue
        base_id = entry.get("base_fact_id")
        derivation = entry.get("derivation")
        if not isinstance(base_id, str) or not base_id:
            continue
        if derivation in _ANY_TRIGGER_DERIVATIONS:
            if base_id in empty_bases:
                return True
        elif derivation == T6_DERIVATION_OPERATOR:
            operator_entries.append(entry)

    if operator_entries:
        all_operator_empty = all(
            entry.get("base_fact_id") in empty_bases
            for entry in operator_entries
        )
        if all_operator_empty:
            return True

    return False


def _iter_entity_files(entity_root: Path):
    if not entity_root.exists():
        return
    yield from entity_root.rglob("*.md")


def invalidate_derived_facts(
    base_fact_id: str,
    entity_root: Union[Path, str],
    *,
    additional_empty_bases: Optional[Set[str]] = None,
    audit_emit: Optional[AuditEmit] = None,
) -> List[str]:
    """Invalidate edges derived from ``base_fact_id`` (and optionally
    other known-empty bases) per the C-semantics.

    Args:
        base_fact_id: the base fact that just became empty
            (sources=[]). Required.
        entity_root: directory whose ``rglob("*.md")`` is the wiki's
            entity file set (typically ``wiki/entity/prod/``).
        additional_empty_bases: optional extra base ids known to be
            empty in the same operation. Useful for batch cascades:
            the caller assembles the full empty-set up front so the
            operator-derivation ALL-trigger fires correctly even when
            multiple bases vanish simultaneously.
        audit_emit: optional callback. Each invalidation emits one
            row with ``mutation_type="invalidated_by_cascade"`` +
            ``base_fact_id`` + ``derived_edge_id`` + ``entity_path``.

    Returns:
        list of invalidated edge ids (the edges' ``id`` fields).

    Side effects:
        - Mutates entity files on disk: sets ``status.active=False``
          and ``mutation_type="invalidated"`` on each invalidated
          edge. ``sources`` preserved for T7 replay.
        - Writes atomically per file (tempfile + os.replace).
    """
    if not isinstance(base_fact_id, str) or not base_fact_id:
        raise ValueError(
            f"base_fact_id must be non-empty str, got {base_fact_id!r}"
        )
    root = Path(entity_root)
    emit = audit_emit or _noop_audit

    empty_bases: Set[str] = {base_fact_id}
    if additional_empty_bases:
        empty_bases.update(b for b in additional_empty_bases if isinstance(b, str))

    invalidated_ids: List[str] = []

    for path in _iter_entity_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body_tail = _split_frontmatter(text)
        if not isinstance(fm, dict):
            continue
        relations = fm.get("relations") or []
        if not isinstance(relations, list):
            continue

        file_changed = False
        for rel in relations:
            if not isinstance(rel, dict):
                continue
            if not should_invalidate_edge(rel, empty_bases):
                continue

            edge_id = rel.get("id")
            # Mark soft-invalidated (T7-style: keep edge for replay).
            status = rel.get(T7_EDGE_FIELD_STATUS)
            if isinstance(status, dict):
                status["active"] = False
            else:
                rel[T7_EDGE_FIELD_STATUS] = {
                    "active": False,
                    "superseded_by": None,
                    "superseded_at": None,
                }
            rel[T7_EDGE_FIELD_MUTATION_TYPE] = T1_MUTATION_INVALIDATED
            file_changed = True
            if isinstance(edge_id, str) and edge_id:
                invalidated_ids.append(edge_id)
            emit({
                "endpoint":         "lifecycle:t6_cascade",
                "role":             "system",
                "mutation_type":    "invalidated_by_cascade",
                "base_fact_id":     base_fact_id,
                "additional_empty_bases": sorted(
                    b for b in empty_bases if b != base_fact_id
                ),
                "derived_edge_id":  edge_id,
                "entity_path":      str(path.relative_to(root))
                                    if path.is_relative_to(root)
                                    else str(path),
            })

        if file_changed:
            new_text = _serialize_frontmatter(fm, body_tail)
            _write_atomic(path, new_text)

    return invalidated_ids


__all__ = [
    "AuditEmit",
    "invalidate_derived_facts",
    "should_invalidate_edge",
]
