"""v0.4 Sprint 5 PR-0 — ``core.lifecycle.schema`` contract tests.

Pins the v0.4 T1+T7 schema extension (validators + safe-default
helpers) that the migration script (PR-T1.A), supersede operations
(PR-T7.A), and contradiction arbiter (PR-T2.A) will all reference.

Contract layers covered here:

1. **Field vocabulary constants** — symbol names and enum members
   match the locked design (entry memo §3).
2. **Source validator** (``validate_source_v04_fields``) — accepts
   v0.3 shapes (no new fields) + all valid v0.4 shapes; rejects
   malformed v0.4 fields with explicit ``ValueError``.
3. **Edge validator** (``validate_edge_v04_fields``) — same contract
   for edges plus the cross-field consistency rule (T7 invariant
   pinned at write-time).
4. **Defaults helpers** (``apply_v04_*_defaults``) — idempotent,
   non-mutating, default to v0.3-equivalent semantics.
5. **Re-export** — ``core.relations_schema`` still surfaces every new
   symbol so v0.3 callers see no breakage.
"""
from __future__ import annotations

import pytest

from core.lifecycle.schema import (
    T1_MUTATION_ACTIVE,
    T1_MUTATION_EXPIRED,
    T1_MUTATION_INVALIDATED,
    T1_MUTATION_SUPERSEDED,
    T1_SOURCE_FIELD_VALID_FROM,
    T1_SOURCE_FIELD_VALID_UNTIL,
    T7_EDGE_FIELD_MUTATION_TYPE,
    T7_EDGE_FIELD_STATUS,
    T7_EDGE_FIELD_VALIDITY,
    VALID_MUTATION_TYPES,
    apply_v04_edge_defaults,
    apply_v04_source_defaults,
    validate_edge_v04_fields,
    validate_source_v04_fields,
)


# ─── Field vocabulary ─────────────────────────────────────────────


def test_mutation_type_enum_values():
    """The four enum members locked at the entry memo §12.3 are
    present + distinct."""
    assert T1_MUTATION_ACTIVE == "active"
    assert T1_MUTATION_INVALIDATED == "invalidated"
    assert T1_MUTATION_SUPERSEDED == "superseded"
    assert T1_MUTATION_EXPIRED == "expired"
    assert VALID_MUTATION_TYPES == frozenset({
        "active", "invalidated", "superseded", "expired",
    })


def test_field_name_constants():
    """Field name constants match the locked schema vocabulary so
    callers and tests reference them by symbol, not string-literal."""
    assert T1_SOURCE_FIELD_VALID_FROM == "valid_from"
    assert T1_SOURCE_FIELD_VALID_UNTIL == "valid_until"
    assert T7_EDGE_FIELD_VALIDITY == "validity"
    assert T7_EDGE_FIELD_STATUS == "status"
    assert T7_EDGE_FIELD_MUTATION_TYPE == "mutation_type"


# ─── Source validator — v0.3 shapes accepted ─────────────────────


def test_v03_source_passes_validator():
    """A pre-v0.4 source dict (no new fields) is accepted unchanged —
    pins the backward-compat invariant."""
    src = {"doc_id": "report_Q1.pdf", "weight": 0.7, "role": "extract"}
    validate_source_v04_fields(src)   # must not raise


def test_v03_source_with_extra_unknown_fields_passes():
    """Unknown extra fields don't trip the validator — it only checks
    the v0.4 fields it knows about. Forward-compat with future T3/T4
    additions."""
    src = {
        "doc_id": "report_Q1.pdf",
        "weight": 0.7,
        "role": "extract",
        "future_field_T3_aging": "exp_decay",
    }
    validate_source_v04_fields(src)


# ─── Source validator — v0.4 valid shapes ────────────────────────


@pytest.mark.parametrize("vf,vu", [
    (None, None),                                # both None → indefinite
    ("2026-04-01", None),                        # bounded from only
    (None, "2027-04-01"),                        # bounded until only
    ("2026-04-01", "2027-04-01"),                # both bounded
    ("2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z"),  # ISO 8601 datetime + Z
    ("2026-04-01T12:34:56+09:00",
     "2026-04-02T12:34:56+09:00"),               # offset-aware
])
def test_source_v04_valid_shapes(vf, vu):
    """Every locked-as-valid v0.4 source shape passes."""
    src = {
        "doc_id": "x",
        "weight": 0.5,
        "role": "extract",
        T1_SOURCE_FIELD_VALID_FROM: vf,
        T1_SOURCE_FIELD_VALID_UNTIL: vu,
    }
    validate_source_v04_fields(src)


# ─── Source validator — malformed shapes rejected ────────────────


def test_source_not_dict_rejected():
    with pytest.raises(ValueError, match="source must be a dict"):
        validate_source_v04_fields("not a dict")  # type: ignore[arg-type]


def test_source_bad_valid_from_string():
    src = {T1_SOURCE_FIELD_VALID_FROM: "not-a-date"}
    with pytest.raises(ValueError, match="not parseable as ISO 8601"):
        validate_source_v04_fields(src)


def test_source_bad_valid_until_type():
    src = {T1_SOURCE_FIELD_VALID_UNTIL: 12345}
    with pytest.raises(ValueError, match="expected ISO 8601 string"):
        validate_source_v04_fields(src)


def test_source_empty_string_valid_from_rejected():
    src = {T1_SOURCE_FIELD_VALID_FROM: ""}
    with pytest.raises(ValueError, match="must be non-empty"):
        validate_source_v04_fields(src)


def test_source_inverted_window_rejected():
    """``valid_from`` must be strictly earlier than ``valid_until``."""
    src = {
        T1_SOURCE_FIELD_VALID_FROM: "2027-04-01",
        T1_SOURCE_FIELD_VALID_UNTIL: "2026-04-01",
    }
    with pytest.raises(ValueError, match="strictly earlier"):
        validate_source_v04_fields(src)


def test_source_zero_window_rejected():
    """Same instant on both ends is rejected — zero-length windows
    leave the source neither active nor expired."""
    src = {
        T1_SOURCE_FIELD_VALID_FROM: "2026-04-01T00:00:00",
        T1_SOURCE_FIELD_VALID_UNTIL: "2026-04-01T00:00:00",
    }
    with pytest.raises(ValueError, match="strictly earlier"):
        validate_source_v04_fields(src)


# ─── Edge validator — v0.3 shapes accepted ───────────────────────


def test_v03_edge_passes_validator():
    """A pre-v0.4 edge dict (no new fields) is accepted unchanged."""
    edge = {
        "head": "Joby",
        "predicate": "CEO",
        "tail": "Alice",
        "confidence": 0.85,
    }
    validate_edge_v04_fields(edge)


# ─── Edge validator — v0.4 valid shapes ──────────────────────────


def test_edge_v04_full_active_shape():
    """Full v0.4 shape, status active, mutation_type=active."""
    edge = {
        "head": "Joby", "predicate": "CEO", "tail": "Bob",
        T7_EDGE_FIELD_VALIDITY: {"from": "2026-03-15", "to": None},
        T7_EDGE_FIELD_STATUS: {
            "active": True,
            "superseded_by": None,
            "superseded_at": None,
        },
        T7_EDGE_FIELD_MUTATION_TYPE: T1_MUTATION_ACTIVE,
    }
    validate_edge_v04_fields(edge)


def test_edge_v04_superseded_shape():
    """A correctly-shaped superseded edge — active=False + non-empty
    supersede link + superseded_at."""
    edge = {
        "head": "Joby", "predicate": "CEO", "tail": "Alice",
        T7_EDGE_FIELD_VALIDITY: {"from": "2024-01-01", "to": "2026-03-15"},
        T7_EDGE_FIELD_STATUS: {
            "active": False,
            "superseded_by": "edge_bob_ceo_2026",
            "superseded_at": "2026-03-15",
        },
        T7_EDGE_FIELD_MUTATION_TYPE: T1_MUTATION_SUPERSEDED,
    }
    validate_edge_v04_fields(edge)


def test_edge_v04_invalidated_shape():
    """An invalidated edge — active=False + no supersede link."""
    edge = {
        "head": "Joby", "predicate": "CEO", "tail": "WrongAlice",
        T7_EDGE_FIELD_STATUS: {
            "active": False,
            "superseded_by": None,
            "superseded_at": None,
        },
        T7_EDGE_FIELD_MUTATION_TYPE: T1_MUTATION_INVALIDATED,
    }
    validate_edge_v04_fields(edge)


def test_edge_v04_expired_shape():
    """An expired edge — active=False + no supersede link."""
    edge = {
        "head": "report_Q1", "predicate": "MENTIONS", "tail": "Alice",
        T7_EDGE_FIELD_STATUS: {
            "active": False,
            "superseded_by": None,
            "superseded_at": None,
        },
        T7_EDGE_FIELD_MUTATION_TYPE: T1_MUTATION_EXPIRED,
    }
    validate_edge_v04_fields(edge)


# ─── Edge validator — malformed shapes rejected ──────────────────


def test_edge_not_dict_rejected():
    with pytest.raises(ValueError, match="edge must be a dict"):
        validate_edge_v04_fields([])  # type: ignore[arg-type]


def test_edge_validity_not_dict_rejected():
    edge = {T7_EDGE_FIELD_VALIDITY: "2026-04-01"}
    with pytest.raises(ValueError, match="validity must be a dict"):
        validate_edge_v04_fields(edge)


def test_edge_validity_inverted_window_rejected():
    edge = {T7_EDGE_FIELD_VALIDITY: {"from": "2027-01-01", "to": "2026-01-01"}}
    with pytest.raises(ValueError, match="strictly earlier"):
        validate_edge_v04_fields(edge)


def test_edge_status_active_not_bool_rejected():
    edge = {T7_EDGE_FIELD_STATUS: {"active": "yes"}}
    with pytest.raises(ValueError, match="status.active must be bool"):
        validate_edge_v04_fields(edge)


def test_edge_superseded_by_wrong_type_rejected():
    edge = {T7_EDGE_FIELD_STATUS: {"active": True, "superseded_by": 42}}
    with pytest.raises(ValueError, match="superseded_by must be str"):
        validate_edge_v04_fields(edge)


def test_edge_mutation_type_invalid_rejected():
    edge = {T7_EDGE_FIELD_MUTATION_TYPE: "deleted"}
    with pytest.raises(ValueError, match="mutation_type must be one of"):
        validate_edge_v04_fields(edge)


# ─── Edge cross-field consistency (T7 invariants) ────────────────


def test_edge_superseded_requires_supersede_link():
    """``status.active=False`` with ``mutation_type="superseded"``
    requires non-empty ``superseded_by`` AND ``superseded_at``."""
    edge = {
        T7_EDGE_FIELD_STATUS: {
            "active": False,
            "superseded_by": None,
            "superseded_at": None,
        },
        T7_EDGE_FIELD_MUTATION_TYPE: T1_MUTATION_SUPERSEDED,
    }
    with pytest.raises(
        ValueError,
        match="requires non-empty superseded_by AND superseded_at",
    ):
        validate_edge_v04_fields(edge)


def test_edge_superseded_missing_superseded_at_rejected():
    edge = {
        T7_EDGE_FIELD_STATUS: {
            "active": False,
            "superseded_by": "edge_new_id",
            "superseded_at": None,   # missing
        },
        T7_EDGE_FIELD_MUTATION_TYPE: T1_MUTATION_SUPERSEDED,
    }
    with pytest.raises(ValueError, match="requires non-empty"):
        validate_edge_v04_fields(edge)


@pytest.mark.parametrize("mt", [
    T1_MUTATION_INVALIDATED,
    T1_MUTATION_SUPERSEDED,
    T1_MUTATION_EXPIRED,
])
def test_edge_active_true_incompatible_with_non_active_mutation(mt):
    """``status.active=True`` is only consistent with
    ``mutation_type="active"`` — any inactive mutation type with
    active=True is a contradiction."""
    edge = {
        T7_EDGE_FIELD_STATUS: {
            "active": True,
            "superseded_by": "x" if mt == T1_MUTATION_SUPERSEDED else None,
            "superseded_at": "2026-01-01" if mt == T1_MUTATION_SUPERSEDED else None,
        },
        T7_EDGE_FIELD_MUTATION_TYPE: mt,
    }
    with pytest.raises(ValueError, match="incompatible with"):
        validate_edge_v04_fields(edge)


# ─── Source defaults helper ──────────────────────────────────────


def test_source_defaults_fills_missing_fields():
    src = {"doc_id": "x", "weight": 0.5, "role": "extract"}
    out = apply_v04_source_defaults(src)
    assert out[T1_SOURCE_FIELD_VALID_FROM] is None
    assert out[T1_SOURCE_FIELD_VALID_UNTIL] is None
    assert out["doc_id"] == "x"   # v0.3 fields preserved
    assert out["weight"] == 0.5
    assert out["role"] == "extract"


def test_source_defaults_does_not_mutate_input():
    """Caller's dict stays untouched — guarantees safe use inside list
    comprehensions over loaded frontmatter."""
    src = {"doc_id": "x"}
    apply_v04_source_defaults(src)
    assert T1_SOURCE_FIELD_VALID_FROM not in src
    assert T1_SOURCE_FIELD_VALID_UNTIL not in src


def test_source_defaults_idempotent():
    """Applying twice yields the same dict — migration script (PR-T1.A)
    can re-run ``--apply`` safely."""
    src = {"doc_id": "x", "weight": 0.5}
    once = apply_v04_source_defaults(src)
    twice = apply_v04_source_defaults(once)
    assert once == twice


def test_source_defaults_preserves_existing_v04_values():
    """If the caller already has v0.4 fields set, the defaults helper
    keeps them — only fills genuinely missing fields."""
    src = {
        "doc_id": "x",
        T1_SOURCE_FIELD_VALID_FROM: "2026-04-01",
        T1_SOURCE_FIELD_VALID_UNTIL: "2027-04-01",
    }
    out = apply_v04_source_defaults(src)
    assert out[T1_SOURCE_FIELD_VALID_FROM] == "2026-04-01"
    assert out[T1_SOURCE_FIELD_VALID_UNTIL] == "2027-04-01"


def test_source_defaults_rejects_non_dict():
    with pytest.raises(ValueError, match="source must be a dict"):
        apply_v04_source_defaults("not a dict")  # type: ignore[arg-type]


# ─── Edge defaults helper ────────────────────────────────────────


def test_edge_defaults_fills_missing_fields():
    edge = {"head": "A", "predicate": "P", "tail": "B"}
    out = apply_v04_edge_defaults(edge)
    assert out[T7_EDGE_FIELD_VALIDITY] == {"from": None, "to": None}
    assert out[T7_EDGE_FIELD_STATUS] == {
        "active": True, "superseded_by": None, "superseded_at": None,
    }
    assert out[T7_EDGE_FIELD_MUTATION_TYPE] == T1_MUTATION_ACTIVE
    # v0.3 fields preserved
    assert out["head"] == "A"
    assert out["predicate"] == "P"
    assert out["tail"] == "B"


def test_edge_defaults_does_not_mutate_input():
    edge = {"head": "A"}
    apply_v04_edge_defaults(edge)
    assert T7_EDGE_FIELD_VALIDITY not in edge
    assert T7_EDGE_FIELD_STATUS not in edge
    assert T7_EDGE_FIELD_MUTATION_TYPE not in edge


def test_edge_defaults_idempotent():
    edge = {"head": "A", "predicate": "P", "tail": "B"}
    once = apply_v04_edge_defaults(edge)
    twice = apply_v04_edge_defaults(once)
    assert once == twice


def test_edge_defaults_after_apply_validates_clean():
    """A defaults-filled edge MUST pass the v0.4 validator. This pins
    that the defaults match the validator's accepted-shape contract."""
    edge = {"head": "A", "predicate": "P", "tail": "B"}
    out = apply_v04_edge_defaults(edge)
    validate_edge_v04_fields(out)   # must not raise


def test_edge_defaults_rejects_non_dict():
    with pytest.raises(ValueError, match="edge must be a dict"):
        apply_v04_edge_defaults(None)  # type: ignore[arg-type]


# ─── Backward-compat re-export through core.relations_schema ─────


def test_relations_schema_reexports_v04_symbols():
    """The new symbols are accessible via the v0.3 canonical
    ``core.relations_schema`` namespace so existing call sites that
    grep the schema vocabulary find everything in one place."""
    from core import relations_schema as rs

    # Constants
    assert rs.T1_MUTATION_ACTIVE == "active"
    assert rs.T1_MUTATION_INVALIDATED == "invalidated"
    assert rs.T1_MUTATION_SUPERSEDED == "superseded"
    assert rs.T1_MUTATION_EXPIRED == "expired"
    assert rs.VALID_MUTATION_TYPES == VALID_MUTATION_TYPES

    # Field name constants
    assert rs.T1_SOURCE_FIELD_VALID_FROM == "valid_from"
    assert rs.T7_EDGE_FIELD_VALIDITY == "validity"

    # Functions
    assert rs.validate_source_v04_fields is validate_source_v04_fields
    assert rs.validate_edge_v04_fields is validate_edge_v04_fields
    assert rs.apply_v04_source_defaults is apply_v04_source_defaults
    assert rs.apply_v04_edge_defaults is apply_v04_edge_defaults


def test_relations_schema_v03_surface_unchanged():
    """v0.3 symbols still present + work — regression pin."""
    from core.relations_schema import (
        VALID_SOURCE_ROLES,
        LEGACY_SOURCE_ROLE,
        compute_confidence_from_sources,
        read_relation_sources,
        validate_occurred_at,
    )
    assert "legacy" in VALID_SOURCE_ROLES
    assert LEGACY_SOURCE_ROLE == "legacy"
    assert compute_confidence_from_sources([]) == 0.0
    assert compute_confidence_from_sources(
        [{"weight": 0.5}]
    ) == 0.5
    assert read_relation_sources({}) == []
    # validate_occurred_at signature unchanged
    validate_occurred_at("2026-01-01", precision="day")
