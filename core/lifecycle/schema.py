"""v0.4 Sprint 5 — T1 + T7 schema extension validators + defaults.

Sprint 5 first-bundle PR-0 (validator prep, 2026-05-26). Lands the
field vocabulary + validation + safe-default helpers before the
migration script (PR-T1.A) or the supersede operations (PR-T7.A)
reference them.

Pure-validation surface — no clock dependency, no I/O, no
behavioural change for v0.3-shaped data. Existing callers that
import these symbols through ``core.relations_schema`` (the v0.3
canonical location) continue to work; the symbols re-export from
that module unchanged.

Field vocabulary locked at the entry memo §3 + strategic memo §3.3 +
§4.2 + §9.5.2:

- **Source-level (T1)**: ``valid_from`` / ``valid_until``
  (ISO 8601 strings or None).
- **Edge-level (T1+T7)**: ``validity`` (``{from, to}`` dict),
  ``status`` (``{active, superseded_by, superseded_at}`` dict),
  ``mutation_type`` (``"active" | "invalidated" | "superseded" |
  "expired"`` enum).

The validator + defaults split:

- ``validate_source_v04_fields(source)`` — raises ``ValueError`` on
  malformed v0.4 fields. Acceptable shapes documented in the
  function docstring.
- ``apply_v04_source_defaults(source)`` — returns a copy of ``source``
  with v0.4 fields filled at v0.3-equivalent safe defaults. Idempotent.
- ``validate_edge_v04_fields(edge)`` — same contract for edges.
- ``apply_v04_edge_defaults(edge)`` — same contract for edges.

Migration script (PR-T1.A) composes ``apply_v04_*_defaults`` over the
loaded frontmatter to migrate idempotently. Subsequent T7 / T2 PRs
compose ``validate_*_v04_fields`` at write-time to catch malformed
mutations before they hit the wiki.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Final


# ─── Mutation type enum ───────────────────────────────────────────
#
# Per the entry memo §12.3 lock, absence in audit-log rows is
# interpreted as ``"active"`` (matches pre-bundle semantics where no
# mutation-type concept existed). Validator accepts the value list
# below; ``apply_v04_edge_defaults`` fills ``"active"`` when missing.
T1_MUTATION_ACTIVE:      Final[str] = "active"
T1_MUTATION_INVALIDATED: Final[str] = "invalidated"   # CASCADE (Layer 3)
T1_MUTATION_SUPERSEDED:  Final[str] = "superseded"    # EVENT (T7)
T1_MUTATION_EXPIRED:     Final[str] = "expired"       # EVENT (T1)

VALID_MUTATION_TYPES: Final[frozenset[str]] = frozenset({
    T1_MUTATION_ACTIVE,
    T1_MUTATION_INVALIDATED,
    T1_MUTATION_SUPERSEDED,
    T1_MUTATION_EXPIRED,
})


# ─── Field name constants ────────────────────────────────────────
#
# Callers + tests reference the schema vocabulary by symbol rather
# than string-literal duplication.
T1_SOURCE_FIELD_VALID_FROM:  Final[str] = "valid_from"
T1_SOURCE_FIELD_VALID_UNTIL: Final[str] = "valid_until"

T7_EDGE_FIELD_VALIDITY:      Final[str] = "validity"
T7_EDGE_FIELD_STATUS:        Final[str] = "status"
T7_EDGE_FIELD_MUTATION_TYPE: Final[str] = "mutation_type"

# ─── T6 Causality Chain (v0.4.1, 2026-05-28) ─────────────────────
#
# Edge-level ``derived_from`` field tracks the base facts that an
# inferred edge depends on. When a base fact is invalidated by
# CASCADE, derived edges automatically lose their support and become
# invalidation candidates (T6 cascade, separate module).
#
# Per v0.4.1 entry memo Decision 3 LOCK: cycles are rejected at
# schema validation time (a derivation that includes itself in its
# transitive chain is genuine schema confusion).
T6_EDGE_FIELD_DERIVED_FROM: Final[str] = "derived_from"

T6_DERIVATION_TRANSITIVE: Final[str] = "transitive"
T6_DERIVATION_OPERATOR:   Final[str] = "operator"
T6_DERIVATION_INFERRED:   Final[str] = "inferred"

VALID_DERIVATION_TYPES: Final[frozenset[str]] = frozenset({
    T6_DERIVATION_TRANSITIVE,
    T6_DERIVATION_OPERATOR,
    T6_DERIVATION_INFERRED,
})


def _parse_optional_iso(value: Any) -> datetime | None:
    """Return parsed ``datetime`` for an ISO-8601 string, ``None`` for
    ``None``, raise ``ValueError`` on anything else (malformed string,
    wrong type).

    Trailing ``Z`` is accepted via the ``+00:00`` substitution,
    matching ``core.relations_schema.validate_occurred_at`` so the
    two timestamp paths share one parser contract.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"expected ISO 8601 string or None, got {type(value).__name__}"
        )
    if not value:
        raise ValueError(
            "ISO 8601 string must be non-empty (use None instead)"
        )
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"not parseable as ISO 8601: {value!r}") from e


def validate_source_v04_fields(source: dict) -> None:
    """Raise ``ValueError`` if a source dict carries malformed T1 fields.

    Acceptable shapes:
      - missing both ``valid_from`` and ``valid_until``  → v0.3 default
      - either or both fields present as ``None``        → indefinite
      - either or both fields present as ISO 8601 string → bounded

    Order constraint: when both are present, ``valid_from`` must be
    strictly earlier than ``valid_until`` (zero-length / inverted
    windows rejected so the cascade can't get stuck on a source
    that's neither active nor expired).
    """
    if not isinstance(source, dict):
        raise ValueError(
            f"source must be a dict, got {type(source).__name__}"
        )
    vf = _parse_optional_iso(source.get(T1_SOURCE_FIELD_VALID_FROM))
    vu = _parse_optional_iso(source.get(T1_SOURCE_FIELD_VALID_UNTIL))
    if vf is not None and vu is not None and not (vf < vu):
        raise ValueError(
            f"valid_from must be strictly earlier than valid_until — "
            f"got valid_from={source.get(T1_SOURCE_FIELD_VALID_FROM)!r} "
            f"valid_until={source.get(T1_SOURCE_FIELD_VALID_UNTIL)!r}"
        )


def validate_edge_v04_fields(edge: dict) -> None:
    """Raise ``ValueError`` if an edge (relation) dict carries malformed
    T1+T7 fields.

    Acceptable shapes:
      - all three new fields missing → v0.3 default (treated as
        active / no validity window / mutation_type="active")
      - ``validity`` dict with ``from`` / ``to`` (both ISO-8601 strings
        or None). Same strict-earlier constraint as
        ``validate_source_v04_fields`` when both bounds are set.
      - ``status`` dict with ``active`` (bool), ``superseded_by``
        (str ID or None), ``superseded_at`` (ISO 8601 or None).
      - ``mutation_type`` ∈ ``VALID_MUTATION_TYPES``.

    Cross-field consistency (T7 invariant pinned at write-time):
    ``status.active == False`` implies one of three:
      1. ``mutation_type == "superseded"`` with non-empty
         ``status.superseded_by`` AND ``status.superseded_at`` set
      2. ``mutation_type == "invalidated"`` (CASCADE path; no
         supersede link required)
      3. ``mutation_type == "expired"`` (T1 path; no supersede link
         required)

    The cross-field check fires only when both ``status`` and
    ``mutation_type`` are explicitly set — partial v0.4 shapes
    (e.g., ``status`` set, ``mutation_type`` missing) get
    default-applied at ``apply_v04_edge_defaults`` time.
    """
    if not isinstance(edge, dict):
        raise ValueError(
            f"edge must be a dict, got {type(edge).__name__}"
        )

    # ─── T1+T7 validity window ───────────────────────────────────
    validity = edge.get(T7_EDGE_FIELD_VALIDITY)
    if validity is not None:
        if not isinstance(validity, dict):
            raise ValueError(
                f"edge.validity must be a dict, got "
                f"{type(validity).__name__}"
            )
        vf = _parse_optional_iso(validity.get("from"))
        vu = _parse_optional_iso(validity.get("to"))
        if vf is not None and vu is not None and not (vf < vu):
            raise ValueError(
                f"edge.validity.from must be strictly earlier than "
                f"validity.to — got from={validity.get('from')!r} "
                f"to={validity.get('to')!r}"
            )

    # ─── T7 status ───────────────────────────────────────────────
    status = edge.get(T7_EDGE_FIELD_STATUS)
    if status is not None:
        if not isinstance(status, dict):
            raise ValueError(
                f"edge.status must be a dict, got "
                f"{type(status).__name__}"
            )
        active = status.get("active", True)
        if not isinstance(active, bool):
            raise ValueError(
                f"edge.status.active must be bool, got "
                f"{type(active).__name__}"
            )
        sb = status.get("superseded_by")
        if sb is not None and not isinstance(sb, str):
            raise ValueError(
                f"edge.status.superseded_by must be str ID or None, "
                f"got {type(sb).__name__}"
            )
        _parse_optional_iso(status.get("superseded_at"))

    # ─── T1+T7 mutation_type ─────────────────────────────────────
    mt = edge.get(T7_EDGE_FIELD_MUTATION_TYPE)
    if mt is not None and mt not in VALID_MUTATION_TYPES:
        raise ValueError(
            f"edge.mutation_type must be one of "
            f"{sorted(VALID_MUTATION_TYPES)}, got {mt!r}"
        )

    # ─── Cross-field consistency (T7 invariant) ──────────────────
    if isinstance(status, dict) and mt is not None:
        active = status.get("active", True)
        sb = status.get("superseded_by")
        sa = status.get("superseded_at")
        if active is False and mt == T1_MUTATION_SUPERSEDED:
            if not sb or sa is None:
                raise ValueError(
                    "status.active=False with mutation_type='superseded' "
                    "requires non-empty superseded_by AND superseded_at"
                )
        if active is True and mt in (
            T1_MUTATION_INVALIDATED,
            T1_MUTATION_SUPERSEDED,
            T1_MUTATION_EXPIRED,
        ):
            raise ValueError(
                f"status.active=True is incompatible with "
                f"mutation_type={mt!r} — only 'active' is consistent "
                f"with status.active=True"
            )


def apply_v04_source_defaults(source: dict) -> dict:
    """Return a copy of ``source`` with v0.4 T1 fields filled at safe
    defaults (``None`` = indefinite validity).

    v0.3-equivalent semantics: the defaults map directly onto the
    "no temporal constraint" reading existing callers already assume.

    Idempotent — applying twice yields the same dict. The migration
    script (PR-T1.A) relies on this to make ``--apply`` re-runnable.

    Returns a new dict; does NOT mutate the caller's argument so the
    function is safe to use inside list comprehensions over loaded
    frontmatter.
    """
    if not isinstance(source, dict):
        raise ValueError(
            f"source must be a dict, got {type(source).__name__}"
        )
    out = dict(source)
    out.setdefault(T1_SOURCE_FIELD_VALID_FROM, None)
    out.setdefault(T1_SOURCE_FIELD_VALID_UNTIL, None)
    return out


def apply_v04_edge_defaults(edge: dict) -> dict:
    """Return a copy of ``edge`` with v0.4 T1+T7 fields filled at safe
    defaults.

    Defaults (match v0.3 semantics for backward compat):
      - ``validity``: ``{"from": None, "to": None}``  (indefinite)
      - ``status``:   ``{"active": True, "superseded_by": None,
                          "superseded_at": None}``
      - ``mutation_type``: ``"active"``

    Idempotent — running on an already-migrated edge yields the same
    dict. The migration script (PR-T1.A) relies on this.

    Returns a new dict; does NOT mutate the caller's argument.
    """
    if not isinstance(edge, dict):
        raise ValueError(
            f"edge must be a dict, got {type(edge).__name__}"
        )
    out = dict(edge)
    out.setdefault(T7_EDGE_FIELD_VALIDITY, {"from": None, "to": None})
    out.setdefault(T7_EDGE_FIELD_STATUS, {
        "active": True,
        "superseded_by": None,
        "superseded_at": None,
    })
    out.setdefault(T7_EDGE_FIELD_MUTATION_TYPE, T1_MUTATION_ACTIVE)
    return out


# ─── T6 derived_from validator + defaults (v0.4.1) ───────────────


def validate_edge_t6_derived_from(
    edge: dict,
    *,
    edges_by_id: dict | None = None,
) -> None:
    """Raise ``ValueError`` if the edge's ``derived_from`` field is
    malformed OR (when ``edges_by_id`` is provided) introduces a
    derivation cycle.

    Acceptable shapes:
      - ``derived_from`` missing → OK (treated as ``[]``, v0.3-equivalent)
      - ``derived_from: []``     → OK (the migration-script default)
      - ``derived_from: [{base_fact_id: str, derivation: str ∈
        VALID_DERIVATION_TYPES}, …]`` → validated entry-by-entry

    Decision 3 LOCK (v0.4.1 entry memo §2): when ``edges_by_id`` is
    provided (mapping ``id`` → ``edge`` for all edges in scope), this
    function walks each ``base_fact_id``'s transitive chain and raises
    ``ValueError`` on cycle (the edge itself appears in its own
    ancestor set). Pass ``edges_by_id=None`` to skip cycle detection
    (single-edge validation without ancestor context).

    Args:
        edge: the edge dict to validate.
        edges_by_id: optional map from edge id to edge dict, used for
            cycle detection. When omitted, only shape is checked.
    """
    if not isinstance(edge, dict):
        raise ValueError(
            f"edge must be a dict, got {type(edge).__name__}"
        )

    derived_from = edge.get(T6_EDGE_FIELD_DERIVED_FROM)
    if derived_from is None:
        return
    if not isinstance(derived_from, list):
        raise ValueError(
            f"edge.derived_from must be a list, got "
            f"{type(derived_from).__name__}"
        )

    for i, entry in enumerate(derived_from):
        if not isinstance(entry, dict):
            raise ValueError(
                f"edge.derived_from[{i}] must be a dict, got "
                f"{type(entry).__name__}"
            )
        base_fact_id = entry.get("base_fact_id")
        if not isinstance(base_fact_id, str) or not base_fact_id:
            raise ValueError(
                f"edge.derived_from[{i}].base_fact_id must be a "
                f"non-empty str, got {base_fact_id!r}"
            )
        derivation = entry.get("derivation")
        if derivation not in VALID_DERIVATION_TYPES:
            raise ValueError(
                f"edge.derived_from[{i}].derivation must be one of "
                f"{sorted(VALID_DERIVATION_TYPES)}, got {derivation!r}"
            )

    # Decision 3 LOCK — cycle rejection. Walk every base_fact_id's
    # transitive chain; if we encounter the edge's own id, raise.
    if edges_by_id is None:
        return
    edge_id = edge.get("id")
    if not isinstance(edge_id, str) or not edge_id:
        # Without a stable id we can't recognize the cycle endpoint.
        # Skip — calling code that wants strict cycle checking sets
        # an id on the edge before validation.
        return
    _walk_for_cycle(edge_id, derived_from, edges_by_id, visited=set())


def _walk_for_cycle(
    target_id: str,
    derivations: list,
    edges_by_id: dict,
    *,
    visited: set,
) -> None:
    """Recursive helper for cycle detection. Walks transitive base
    chains; raises ``ValueError`` if ``target_id`` reappears."""
    for entry in derivations:
        if not isinstance(entry, dict):
            continue
        base_fact_id = entry.get("base_fact_id")
        if not isinstance(base_fact_id, str) or not base_fact_id:
            continue
        if base_fact_id == target_id:
            raise ValueError(
                f"derivation cycle: edge id={target_id!r} appears in "
                f"its own transitive derived_from chain — Decision 3 "
                f"LOCK rejects self-referential derivations"
            )
        if base_fact_id in visited:
            continue
        visited.add(base_fact_id)
        base = edges_by_id.get(base_fact_id)
        if not isinstance(base, dict):
            continue
        base_derivations = base.get(T6_EDGE_FIELD_DERIVED_FROM)
        if isinstance(base_derivations, list):
            _walk_for_cycle(
                target_id, base_derivations, edges_by_id,
                visited=visited,
            )


def apply_t6_edge_defaults(edge: dict) -> dict:
    """Return a copy of ``edge`` with the v0.4.1 ``derived_from``
    field set to ``[]`` when absent. Idempotent — re-running on an
    already-migrated edge yields the same dict.

    The migration script (T6.A's ``scripts/migrate_v041_lifecycle.py``)
    calls this on every edge in every entity file, then writes back
    only when the dict actually changed (byte-stable).
    """
    if not isinstance(edge, dict):
        raise ValueError(
            f"edge must be a dict, got {type(edge).__name__}"
        )
    out = dict(edge)
    out.setdefault(T6_EDGE_FIELD_DERIVED_FROM, [])
    return out


__all__ = [
    # mutation type enum
    "T1_MUTATION_ACTIVE",
    "T1_MUTATION_INVALIDATED",
    "T1_MUTATION_SUPERSEDED",
    "T1_MUTATION_EXPIRED",
    "VALID_MUTATION_TYPES",
    # field name constants
    "T1_SOURCE_FIELD_VALID_FROM",
    "T1_SOURCE_FIELD_VALID_UNTIL",
    "T7_EDGE_FIELD_VALIDITY",
    "T7_EDGE_FIELD_STATUS",
    "T7_EDGE_FIELD_MUTATION_TYPE",
    "T6_EDGE_FIELD_DERIVED_FROM",
    # T6 derivation type enum
    "T6_DERIVATION_TRANSITIVE",
    "T6_DERIVATION_OPERATOR",
    "T6_DERIVATION_INFERRED",
    "VALID_DERIVATION_TYPES",
    # T6 validators + defaults
    "validate_edge_t6_derived_from",
    "apply_t6_edge_defaults",
    # validators
    "validate_source_v04_fields",
    "validate_edge_v04_fields",
    # defaults
    "apply_v04_source_defaults",
    "apply_v04_edge_defaults",
]
