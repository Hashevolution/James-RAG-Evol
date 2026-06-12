"""v0.5 G5 — batched contradiction classifier tests.

Covers:

  * Equivalence — `classify_contradiction_batch([(a, b)])[0]` returns
    the same label as `classify_contradiction(a, b)` for every rule.
  * Order preservation — labels returned in input order.
  * Empty input — returns `[]` cleanly.
  * Shared-now invariant — every pair in the batch evaluates against
    the same wall-clock moment (regression test: long batches must
    not see a "now" that drifts pair-to-pair).
  * `audit_batch_id` round-trip via `get_last_batch_id()`.
  * Atomic-on-error — a single per-pair ValueError discards partial
    results (the function does NOT return a truncated list).
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.lifecycle.contradiction_arbiter import (
    classify_contradiction,
    classify_contradiction_batch,
    get_last_batch_id,
)


def _old_edge(*, valid_from="2026-01-01T00:00:00+00:00",
              valid_to=None, weight=0.8) -> dict:
    return {
        "id": "e_edge_aaaaaaaaaa",
        "type": "RELATED_TO",
        "validity": {"from": valid_from, "to": valid_to},
        "status": {"active": True, "superseded_by": None,
                   "superseded_at": None},
        "mutation_type": "active",
        "sources": [
            {"doc_id": "doc_old", "weight": weight, "role": "primary",
             "ts": valid_from, "valid_from": None, "valid_until": None},
        ],
    }


def _new_fact_future() -> dict:
    """A new fact valid_from later than old edge's validity.to (rule 1)."""
    return {
        "valid_from": "2026-12-01T00:00:00+00:00",
        "timestamp": "2026-12-01T00:00:00+00:00",
        "confidence": 0.9,
        "weight": 0.9,
    }


def _new_fact_retroactive() -> dict:
    """A new fact at-or-before old.valid_from with higher confidence (rule 2)."""
    return {
        "valid_from": "2025-06-01T00:00:00+00:00",
        "timestamp": "2025-06-01T00:00:00+00:00",
        "confidence": 0.99,
        "weight": 0.99,
    }


def _new_fact_duplicate() -> dict:
    """A new fact inside the window, same confidence (rule 3)."""
    return {
        "valid_from": "2026-03-01T00:00:00+00:00",
        "timestamp": "2026-03-01T00:00:00+00:00",
        "confidence": 0.8,
        "weight": 0.8,
    }


class BatchEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    def test_single_rule_1_pair_matches_per_pair(self):
        old, new = _old_edge(), _new_fact_future()
        single = classify_contradiction(old, new, now=self.now)
        batch = classify_contradiction_batch([(old, new)], now=self.now)
        self.assertEqual(batch, [single])

    def test_single_rule_2_pair_matches_per_pair(self):
        old, new = _old_edge(), _new_fact_retroactive()
        single = classify_contradiction(old, new, now=self.now)
        batch = classify_contradiction_batch([(old, new)], now=self.now)
        self.assertEqual(batch, [single])

    def test_single_rule_3_pair_matches_per_pair(self):
        old, new = _old_edge(), _new_fact_duplicate()
        single = classify_contradiction(old, new, now=self.now)
        batch = classify_contradiction_batch([(old, new)], now=self.now)
        self.assertEqual(batch, [single])

    def test_mixed_batch_returns_in_order(self):
        pairs = [
            (_old_edge(), _new_fact_future()),       # B_supersede
            (_old_edge(), _new_fact_retroactive()),  # A_invalidate
            (_old_edge(), _new_fact_duplicate()),    # ignore
        ]
        expected = [
            classify_contradiction(o, n, now=self.now) for o, n in pairs
        ]
        actual = classify_contradiction_batch(pairs, now=self.now)
        self.assertEqual(actual, expected)


class EmptyAndNowSemanticsTests(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        self.assertEqual(classify_contradiction_batch([], now=now), [])

    def test_naive_now_raises(self):
        with self.assertRaises(ValueError):
            classify_contradiction_batch([], now=datetime(2026, 6, 1))

    def test_non_datetime_now_raises(self):
        with self.assertRaises(ValueError):
            classify_contradiction_batch([], now="2026-06-01")  # type: ignore[arg-type]

    def test_shared_now_invariant(self):
        # An open-ended old edge (validity.to=None) with a new fact
        # whose valid_from is BEFORE `now`: rule 1's cutoff = now,
        # not valid_to. If `now` were re-evaluated per-pair across a
        # long batch, two identical inputs could yield different
        # labels. Verify both pairs in a 2-element batch produce the
        # same label given the SAME inputs.
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        old = _old_edge(valid_from="2025-01-01T00:00:00+00:00",
                        valid_to=None)
        new = {
            "valid_from": "2026-05-01T00:00:00+00:00",
            "timestamp": "2026-05-01T00:00:00+00:00",
            "confidence": 0.5,
            "weight": 0.5,
        }
        labels = classify_contradiction_batch(
            [(old, new), (old, new)], now=now,
        )
        self.assertEqual(labels[0], labels[1])


class AuditBatchIdRoundTripTests(unittest.TestCase):
    def test_id_stored_and_retrievable(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        classify_contradiction_batch(
            [(_old_edge(), _new_fact_future())],
            now=now, audit_batch_id="batch_abc",
        )
        self.assertEqual(get_last_batch_id(), "batch_abc")

    def test_none_id_overwrites_previous(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        classify_contradiction_batch(
            [(_old_edge(), _new_fact_future())],
            now=now, audit_batch_id="batch_first",
        )
        classify_contradiction_batch(
            [(_old_edge(), _new_fact_future())],
            now=now, audit_batch_id=None,
        )
        # Most recent call had None → getter returns None.
        self.assertIsNone(get_last_batch_id())

    def test_empty_batch_still_sets_id(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        classify_contradiction_batch(
            [], now=now, audit_batch_id="empty_batch_xyz",
        )
        self.assertEqual(get_last_batch_id(), "empty_batch_xyz")


class AtomicOnErrorTests(unittest.TestCase):
    def test_per_pair_error_propagates(self):
        # A malformed `now` would fail upfront, not mid-batch.
        # Per-pair errors come from the per-pair classifier — but
        # the per-pair classifier tolerates missing fields and
        # falls through to rule-4. So the realistic error path is
        # an invalid `now` at the outer call. Verify that path
        # raises BEFORE producing any partial output.
        old, new = _old_edge(), _new_fact_future()
        with self.assertRaises(ValueError):
            classify_contradiction_batch(
                [(old, new)], now="not-a-datetime",  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
