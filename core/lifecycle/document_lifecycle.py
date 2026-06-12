"""v0.5 B.5: Document lifecycle state — interpretive layer over T1+T7.

Per `docs/design/v0.5-enterprise-document-ontology.md` §3.2.

This module is a **pure interpretation layer** over the existing T1
(temporal validity) + T7 (supersede chain) frontmatter. It does NOT
enforce a state machine; T7 supersede chain owns transition truth, and
this module names the truth.

The 7 lifecycle states are:

  DRAFT       — being written; no validity guarantee
  IN_REVIEW   — submitted for review, not yet approved
  APPROVED    — reviewed and signed off, not yet published
  PUBLISHED   — currently in force
  SUPERSEDED  — replaced by a newer version (T7 chain)
  ARCHIVED    — kept for audit but not current
  REVOKED     — formally invalidated (rare; emergency rescind)

Helpers:

  state_from_t1_t7(...) → DocumentLifecycleState
      Interpret T1+T7 frontmatter into a named state. Decision order
      (first match wins): revoked → SUPERSEDED → ARCHIVED → PUBLISHED
      → APPROVED → IN_REVIEW → DRAFT.

  t1_t7_from_state(state) → dict
      Inverse: return canonical T1+T7 frontmatter dict for a state.
      Returns the MINIMAL set of fields that disambiguates this state
      from the others. Callers should fill in real timestamps / doc_ids.

This module touches NO retrieval-side / reasoning-side / graph-engine
code. It only interprets frontmatter.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class DocumentLifecycleState(Enum):
    """The 7 enterprise document lifecycle states (B.5.a §3.2)."""

    DRAFT       = "draft"
    IN_REVIEW   = "in_review"
    APPROVED    = "approved"
    PUBLISHED   = "published"
    SUPERSEDED  = "superseded"
    ARCHIVED    = "archived"
    REVOKED     = "revoked"


def state_from_t1_t7(
    *,
    valid_from: Optional[Any] = None,
    valid_to: Optional[Any] = None,
    supersede_by: Optional[Any] = None,
    approved_at: Optional[Any] = None,
    in_review: bool = False,
    revoked: bool = False,
) -> DocumentLifecycleState:
    """Interpret T1 + T7 frontmatter into a named lifecycle state.

    Decision order (first match wins, per design memo §3.2 state
    machine):

      1. ``revoked`` set         → REVOKED
      2. ``supersede_by`` set    → SUPERSEDED
      3. ``valid_from`` AND ``valid_to`` set → ARCHIVED
      4. ``valid_from`` set (no ``valid_to``, no ``supersede_by``)
         → PUBLISHED
      5. ``approved_at`` set (no ``valid_from``) → APPROVED
      6. ``in_review`` set       → IN_REVIEW
      7. else                    → DRAFT

    All arguments are keyword-only so callers cannot silently swap
    positional ordering. Treats falsy / None / empty strings as
    "field not set". The ``revoked`` and ``in_review`` flags are
    boolean; the timestamp / id fields are treated as set if truthy
    (typically str or datetime).
    """
    if revoked:
        return DocumentLifecycleState.REVOKED
    if supersede_by:
        return DocumentLifecycleState.SUPERSEDED
    if valid_from and valid_to:
        return DocumentLifecycleState.ARCHIVED
    if valid_from:
        return DocumentLifecycleState.PUBLISHED
    if approved_at:
        return DocumentLifecycleState.APPROVED
    if in_review:
        return DocumentLifecycleState.IN_REVIEW
    return DocumentLifecycleState.DRAFT


# Sentinel values for `t1_t7_from_state`. Real callers must fill in
# concrete timestamps / doc_ids; these sentinels just indicate
# "this field needs to be set for this state".
_TS_SENTINEL: str = "<ts>"
_DOC_ID_SENTINEL: str = "<doc_id>"


def t1_t7_from_state(state: DocumentLifecycleState) -> Dict[str, Any]:
    """Return canonical T1+T7 frontmatter dict for a state.

    Inverse of ``state_from_t1_t7``: returns the MINIMAL set of fields
    that disambiguates the given state from the others under the
    decision order documented there.

    Sentinels:
      * ``<ts>``     placeholder for a timestamp the caller must fill
      * ``<doc_id>`` placeholder for the superseding document id

    Callers should overwrite these with concrete values before writing
    the frontmatter to a document. Round-trip property is preserved:
    ``state_from_t1_t7(**t1_t7_from_state(s))`` returns ``s`` for every
    ``s`` in ``DocumentLifecycleState``.
    """
    if state == DocumentLifecycleState.REVOKED:
        return {"revoked": True}
    if state == DocumentLifecycleState.SUPERSEDED:
        return {"supersede_by": _DOC_ID_SENTINEL}
    if state == DocumentLifecycleState.ARCHIVED:
        return {"valid_from": _TS_SENTINEL, "valid_to": _TS_SENTINEL}
    if state == DocumentLifecycleState.PUBLISHED:
        return {"valid_from": _TS_SENTINEL}
    if state == DocumentLifecycleState.APPROVED:
        return {"approved_at": _TS_SENTINEL}
    if state == DocumentLifecycleState.IN_REVIEW:
        return {"in_review": True}
    # DRAFT
    return {}


__all__ = [
    "DocumentLifecycleState",
    "state_from_t1_t7",
    "t1_t7_from_state",
]
