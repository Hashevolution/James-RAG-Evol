"""v0.5 G7 — etag optimistic-concurrency tests.

Covers:

  * `compute_edge_etag` — determinism, field-sensitivity (which mutations
    DO change the etag and which DON'T), validation.
  * `assign_edge_etag` — populates the field, idempotent on unchanged
    edges, force-refresh semantic.
  * `check_edge_etag` — raises on mismatch, no-stored-etag treated as
    mismatch.
  * `EtagMismatchError` — fields populated, descriptive message.
  * `supersede_edge` integration — opt-in via `expected_old_etag`,
    raises before mutation on mismatch, succeeds on match, default
    behaviour (`expected_old_etag=None`) byte-identical to pre-G7
    except for the newly-assigned etag field on both edges.
  * Schema regression — `validate_edge_v04_fields` accepts edges with
    and without etag; rejects empty-string or non-str etag.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.lifecycle.etag import (
    EtagMismatchError,
    assign_edge_etag,
    check_edge_etag,
    compute_edge_etag,
)
from core.lifecycle.schema import (
    T7_EDGE_FIELD_ETAG,
    validate_edge_v04_fields,
)
from core.lifecycle.supersede_chain import supersede_edge


def _fresh_edge() -> dict:
    """Build a minimal v0.4-shaped edge for testing."""
    return {
        "id": "e_edge_aaaaaaaaaa",
        "type": "RELATED_TO",
        "validity": {
            "from": "2026-01-01T00:00:00+00:00",
            "to": None,
        },
        "status": {
            "active": True,
            "superseded_by": None,
            "superseded_at": None,
        },
        "mutation_type": "active",
        "sources": [
            {"doc_id": "doc_x", "weight": 0.9, "role": "primary",
             "ts": "2026-01-01T00:00:00+00:00",
             "valid_from": None, "valid_until": None},
        ],
        "confidence": 0.9,
    }


def _fresh_new_fact() -> dict:
    """Build a v0.4 'new fact' shape for supersede tests."""
    return {
        "type": "RELATED_TO",
        "validity": {"from": None, "to": None},
        "status": {"active": True, "superseded_by": None,
                   "superseded_at": None},
        "mutation_type": "active",
        "sources": [
            {"doc_id": "doc_y", "weight": 0.95, "role": "primary",
             "ts": "2026-06-01T00:00:00+00:00",
             "valid_from": None, "valid_until": None},
        ],
        "confidence": 0.95,
    }


class ComputeEdgeEtagTests(unittest.TestCase):
    def test_deterministic(self):
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        self.assertEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_changes_with_validity_to(self):
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        e2["validity"]["to"] = "2026-12-31T00:00:00+00:00"
        self.assertNotEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_changes_with_status_active(self):
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        e2["status"]["active"] = False
        self.assertNotEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_changes_with_superseded_by(self):
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        e2["status"]["superseded_by"] = "e_edge_xxxxxxxxxx"
        self.assertNotEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_changes_with_sources_doc_id(self):
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        e2["sources"][0]["doc_id"] = "doc_different"
        self.assertNotEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_changes_with_sources_weight(self):
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        e2["sources"][0]["weight"] = 0.5
        self.assertNotEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_invariant_to_confidence(self):
        # confidence is derived; not part of identity → etag unchanged.
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        e2["confidence"] = 0.1
        self.assertEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_invariant_to_label(self):
        # label is display-side; not part of identity → etag unchanged.
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        e2["label"] = "display name"
        self.assertEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_invariant_to_unknown_fields(self):
        # Future caller-added fields don't poison the etag.
        e1 = _fresh_edge()
        e2 = _fresh_edge()
        e2["some_future_field"] = "anything"
        self.assertEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_invariant_to_etag_self_reference(self):
        # The etag must NOT include itself in the hash (would
        # self-reference and prevent stable comparison).
        e1 = _fresh_edge()
        before = compute_edge_etag(e1)
        e1[T7_EDGE_FIELD_ETAG] = "tampered_value"
        after = compute_edge_etag(e1)
        self.assertEqual(before, after)

    def test_validity_none_vs_empty_dict_equivalent(self):
        # 'no temporal window known' has one canonical representation.
        e1 = _fresh_edge()
        e1["validity"] = None
        e2 = _fresh_edge()
        e2["validity"] = {}
        self.assertEqual(compute_edge_etag(e1), compute_edge_etag(e2))

    def test_returns_12_hex(self):
        etag = compute_edge_etag(_fresh_edge())
        self.assertEqual(len(etag), 12)
        # All hex chars
        int(etag, 16)

    def test_rejects_non_dict(self):
        with self.assertRaises(ValueError):
            compute_edge_etag("not an edge")  # type: ignore[arg-type]


class AssignEdgeEtagTests(unittest.TestCase):
    def test_populates_field(self):
        e = _fresh_edge()
        self.assertNotIn(T7_EDGE_FIELD_ETAG, e)
        value = assign_edge_etag(e)
        self.assertEqual(e[T7_EDGE_FIELD_ETAG], value)

    def test_value_matches_compute(self):
        e = _fresh_edge()
        expected = compute_edge_etag(e)
        actual = assign_edge_etag(e)
        self.assertEqual(actual, expected)

    def test_idempotent_on_unchanged_edge(self):
        e = _fresh_edge()
        v1 = assign_edge_etag(e)
        v2 = assign_edge_etag(e)
        self.assertEqual(v1, v2)

    def test_force_refresh_after_mutation(self):
        e = _fresh_edge()
        assign_edge_etag(e)
        e["status"]["active"] = False
        # New compute would differ; assign refreshes the stored value.
        new_value = assign_edge_etag(e)
        self.assertEqual(e[T7_EDGE_FIELD_ETAG], new_value)


class CheckEdgeEtagTests(unittest.TestCase):
    def test_match_returns_none(self):
        e = _fresh_edge()
        value = assign_edge_etag(e)
        self.assertIsNone(check_edge_etag(e, value))

    def test_mismatch_raises(self):
        e = _fresh_edge()
        assign_edge_etag(e)
        with self.assertRaises(EtagMismatchError):
            check_edge_etag(e, "wrong_value")

    def test_no_stored_etag_treated_as_mismatch(self):
        # An edge that never went through the etag layer raises on
        # check — the caller must call `assign_edge_etag` first.
        e = _fresh_edge()
        with self.assertRaises(EtagMismatchError) as ctx:
            check_edge_etag(e, "anything")
        self.assertEqual(ctx.exception.actual, "<absent>")

    def test_error_carries_expected_and_actual(self):
        e = _fresh_edge()
        assign_edge_etag(e)
        with self.assertRaises(EtagMismatchError) as ctx:
            check_edge_etag(e, "expected_value")
        self.assertEqual(ctx.exception.expected, "expected_value")
        self.assertEqual(ctx.exception.actual, e[T7_EDGE_FIELD_ETAG])
        self.assertIn("e_edge_aaaaaaaaaa", str(ctx.exception))


class SupersedeEdgeEtagIntegrationTests(unittest.TestCase):
    def test_default_no_expected_etag_works_as_before(self):
        old = _fresh_edge()
        new_fact = _fresh_new_fact()
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        new_edge, returned_old = supersede_edge(old, new_fact, ts)
        # Pre-G7 behaviour preserved + etag now populated on both.
        self.assertEqual(returned_old["status"]["active"], False)
        self.assertEqual(returned_old["mutation_type"], "superseded")
        self.assertIn(T7_EDGE_FIELD_ETAG, new_edge)
        self.assertIn(T7_EDGE_FIELD_ETAG, returned_old)

    def test_matching_expected_etag_succeeds(self):
        old = _fresh_edge()
        # Caller computes etag BEFORE mutation.
        assign_edge_etag(old)
        snapshot = old[T7_EDGE_FIELD_ETAG]
        new_fact = _fresh_new_fact()
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        # Match → supersede proceeds.
        new_edge, returned_old = supersede_edge(
            old, new_fact, ts, expected_old_etag=snapshot,
        )
        # Etag was refreshed on both edges post-mutation.
        self.assertNotEqual(returned_old[T7_EDGE_FIELD_ETAG], snapshot)
        self.assertIn(T7_EDGE_FIELD_ETAG, new_edge)

    def test_mismatched_expected_etag_raises_before_mutation(self):
        old = _fresh_edge()
        assign_edge_etag(old)
        # Snapshot the pre-mutation status to verify rollback semantics.
        pre_status_active = old["status"]["active"]
        pre_mutation_type = old["mutation_type"]
        new_fact = _fresh_new_fact()
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        with self.assertRaises(EtagMismatchError):
            supersede_edge(
                old, new_fact, ts, expected_old_etag="stale_etag",
            )
        # Old edge must be untouched.
        self.assertEqual(old["status"]["active"], pre_status_active)
        self.assertEqual(old["mutation_type"], pre_mutation_type)

    def test_concurrent_supersede_race_simulation(self):
        """Two writers read the same edge; only the first supersede
        succeeds. The second sees an etag mismatch and refuses."""
        old = _fresh_edge()
        assign_edge_etag(old)
        snapshot_a = old[T7_EDGE_FIELD_ETAG]
        snapshot_b = old[T7_EDGE_FIELD_ETAG]  # Same snapshot both readers

        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)

        # Writer A wins.
        supersede_edge(old, _fresh_new_fact(), ts,
                       expected_old_etag=snapshot_a)
        # Old now has a new etag.
        self.assertNotEqual(old[T7_EDGE_FIELD_ETAG], snapshot_a)

        # Writer B retries with the stale snapshot → loses cleanly.
        with self.assertRaises(EtagMismatchError):
            supersede_edge(old, _fresh_new_fact(), ts,
                           expected_old_etag=snapshot_b)

    def test_post_supersede_etag_is_valid_per_schema(self):
        old = _fresh_edge()
        new_fact = _fresh_new_fact()
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        new_edge, returned_old = supersede_edge(old, new_fact, ts)
        # Both edges must validate (etag included).
        validate_edge_v04_fields(new_edge)
        validate_edge_v04_fields(returned_old)


class SchemaValidationTests(unittest.TestCase):
    def test_edge_without_etag_validates(self):
        e = _fresh_edge()
        # Sanity: pre-G7 v0.4 shape still valid.
        validate_edge_v04_fields(e)

    def test_edge_with_str_etag_validates(self):
        e = _fresh_edge()
        e[T7_EDGE_FIELD_ETAG] = "abc123def456"
        validate_edge_v04_fields(e)

    def test_edge_with_empty_etag_rejected(self):
        e = _fresh_edge()
        e[T7_EDGE_FIELD_ETAG] = ""
        with self.assertRaises(ValueError):
            validate_edge_v04_fields(e)

    def test_edge_with_non_str_etag_rejected(self):
        e = _fresh_edge()
        e[T7_EDGE_FIELD_ETAG] = 123
        with self.assertRaises(ValueError):
            validate_edge_v04_fields(e)


if __name__ == "__main__":
    unittest.main()
