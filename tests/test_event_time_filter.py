"""PR-11c — event time-bucket filter.

`core.event_time_filter.filter_entities_by_time_bucket` is the hard
cut applied after retrieval scoring (memo §5.3). These tests pin the
two key rules:

  1. With no bounds set, every entity passes (no filter active).
  2. With either bound set, only events whose occurred_at lies in
     the window pass; non-event entities are dropped.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.event_time_filter import (  # noqa: E402
    entity_within_time_bucket,
    filter_entities_by_time_bucket,
)


# ─── fixtures ──────────────────────────────────────────────────────


def _event(eid: str, occurred_at: str) -> dict:
    return {
        "id":           eid,
        "entity_type":  "event",
        "name":         eid,
        "occurred_at":  occurred_at,
    }


def _concept(eid: str) -> dict:
    return {
        "id":           eid,
        "entity_type":  "concept",
        "name":         eid,
    }


# ─── 1. no-bound passthrough ────────────────────────────────────────


class NoBoundPassthroughTests(unittest.TestCase):
    """Memo §5.3: 'concept nodes (no occurred_at) pass the filter only
    when both occurred_after and occurred_before are absent — a
    time-scoped query implicitly restricts to event nodes.'"""

    def test_no_bounds_keeps_every_entity(self):
        ents = [
            _event("e1", "2026-01-10"),
            _concept("c1"),
            _event("e2", "2026-02-15"),
            _concept("c2"),
        ]
        out = filter_entities_by_time_bucket(ents)
        self.assertEqual([e["id"] for e in out], ["e1", "c1", "e2", "c2"])

    def test_no_bounds_preserves_order(self):
        # Hard cut must not reorder.
        ents = [_event(f"e{i}", "2026-01-10") for i in range(5)]
        out = filter_entities_by_time_bucket(ents)
        self.assertEqual([e["id"] for e in out], [e["id"] for e in ents])


# ─── 2. after / before / both ───────────────────────────────────────


class TimeBoundsTests(unittest.TestCase):

    def test_after_only_drops_earlier_events(self):
        ents = [
            _event("e1", "2026-01-10"),
            _event("e2", "2026-02-15"),
            _event("e3", "2026-03-20"),
        ]
        out = filter_entities_by_time_bucket(
            ents, occurred_after="2026-02-01",
        )
        self.assertEqual([e["id"] for e in out], ["e2", "e3"])

    def test_before_only_drops_later_events(self):
        ents = [
            _event("e1", "2026-01-10"),
            _event("e2", "2026-02-15"),
            _event("e3", "2026-03-20"),
        ]
        out = filter_entities_by_time_bucket(
            ents, occurred_before="2026-02-28",
        )
        self.assertEqual([e["id"] for e in out], ["e1", "e2"])

    def test_both_bounds_filters_to_window(self):
        ents = [
            _event("e1", "2026-01-10"),
            _event("e2", "2026-02-15"),
            _event("e3", "2026-03-20"),
        ]
        out = filter_entities_by_time_bucket(
            ents,
            occurred_after="2026-02-01",
            occurred_before="2026-02-28",
        )
        self.assertEqual([e["id"] for e in out], ["e2"])

    def test_bounds_are_inclusive(self):
        # Exact-match dates pass on both endpoints (closed interval).
        ents = [_event("e1", "2026-02-15")]
        out = filter_entities_by_time_bucket(
            ents,
            occurred_after="2026-02-15",
            occurred_before="2026-02-15",
        )
        self.assertEqual([e["id"] for e in out], ["e1"])

    def test_datetime_with_tz_compares_against_naive_bound(self):
        # Memo §4.1 / module docstring: naive bound and tz-aware
        # entity are coerced to the same naive frame.
        ents = [
            _event("e1", "2026-01-10T15:32:00Z"),
        ]
        out = filter_entities_by_time_bucket(
            ents, occurred_after="2026-01-10",
        )
        self.assertEqual([e["id"] for e in out], ["e1"])


# ─── 3. non-event handling ──────────────────────────────────────────


class NonEventEntityTests(unittest.TestCase):

    def test_concept_dropped_when_any_bound_set(self):
        ents = [
            _concept("c1"),
            _event("e1", "2026-02-15"),
        ]
        out_after = filter_entities_by_time_bucket(
            ents, occurred_after="2026-01-01",
        )
        self.assertEqual([e["id"] for e in out_after], ["e1"])

        out_before = filter_entities_by_time_bucket(
            ents, occurred_before="2026-12-31",
        )
        self.assertEqual([e["id"] for e in out_before], ["e1"])

    def test_event_with_malformed_occurred_at_drops_silently(self):
        # One bad entity must not raise — only drop.
        ents = [
            {"id": "bad", "entity_type": "event",
             "occurred_at": "yesterday"},
            _event("good", "2026-02-15"),
        ]
        out = filter_entities_by_time_bucket(
            ents, occurred_after="2026-01-01",
        )
        self.assertEqual([e["id"] for e in out], ["good"])

    def test_event_missing_occurred_at_drops_when_bound_set(self):
        ents = [
            {"id": "bare", "entity_type": "event"},
            _event("dated", "2026-02-15"),
        ]
        out = filter_entities_by_time_bucket(
            ents, occurred_after="2026-01-01",
        )
        self.assertEqual([e["id"] for e in out], ["dated"])


# ─── 4. bound validation ────────────────────────────────────────────


class BoundValidationTests(unittest.TestCase):
    """Bounds themselves must be parseable. validate_occurred_at
    raises a clear ValueError so a malformed query param doesn't reach
    the per-entity loop (which would silently drop every entity)."""

    def test_garbage_after_bound_raises(self):
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            filter_entities_by_time_bucket(
                [_event("e1", "2026-01-10")],
                occurred_after="last week",
            )

    def test_garbage_before_bound_raises(self):
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            filter_entities_by_time_bucket(
                [_event("e1", "2026-01-10")],
                occurred_before="2026-Q1",
            )


# ─── 5. unit predicate ──────────────────────────────────────────────


class PredicateUnitTests(unittest.TestCase):
    """entity_within_time_bucket is the single-entity primitive that
    callers can use without going through the list-level helper (e.g.
    when streaming a large index)."""

    def test_no_bounds_returns_true(self):
        self.assertTrue(entity_within_time_bucket(_concept("c"), None, None))
        self.assertTrue(entity_within_time_bucket(
            _event("e", "2026-01-10"), None, None,
        ))

    def test_event_passes_when_in_window(self):
        self.assertTrue(entity_within_time_bucket(
            _event("e", "2026-02-15"),
            "2026-02-01", "2026-02-28",
        ))

    def test_event_fails_when_below_lower(self):
        self.assertFalse(entity_within_time_bucket(
            _event("e", "2026-01-15"),
            "2026-02-01", None,
        ))

    def test_event_fails_when_above_upper(self):
        self.assertFalse(entity_within_time_bucket(
            _event("e", "2026-03-15"),
            None, "2026-02-28",
        ))


if __name__ == "__main__":
    unittest.main()
