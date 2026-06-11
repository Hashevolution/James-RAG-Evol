"""PR-11a-1 — event entity schema helpers.

Schema-level guarantees for the upcoming `event` entity type:
  * the 5-element entity-type tuple lists `event` as the 5th element
  * `EVENT_LIKE_ENTITY_TYPES` starts as just `{"event"}` (loader
    extends; tests pin the core baseline)
  * `validate_occurred_at` accepts canonical ISO 8601 strings and
    rejects anything else, with a clear error per failure mode
  * the 5 precision buckets are exactly the documented set

No production wiring yet — this PR is the schema substrate.
PR-11a-2 lifts the wiki_generator literal, PR-11b adds the ingest
emit path, PR-11c the time-bucket filter.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.relations_schema import (  # noqa: E402
    ENTITY_TYPES_CORE,
    EVENT_LIKE_ENTITY_TYPES,
    VALID_OCCURRED_AT_PRECISIONS,
    validate_occurred_at,
)


class EntityTypeVocabularyTests(unittest.TestCase):
    """The truth source for graph-valid entity types. PR-11a-1 shipped
    a 5-element tuple (legacy 4 + `event`); α-8 (2026-06-03,
    `project_alpha_8_phase_a_b_landed`) extended it with 4 more
    horizontal types (date, location, quantity, project) to give the
    extractor enough type slots for evidence-of-absence preservation
    (R1-R5 rules). `wiki_generator.py` was lifted to the constant at
    PR-11a-2, so production and schema agree on whatever the tuple
    holds today."""

    def test_entity_types_core_preserves_legacy_four(self):
        legacy_four = ("person", "concept", "org", "document")
        self.assertEqual(ENTITY_TYPES_CORE[: len(legacy_four)], legacy_four)

    def test_entity_types_core_has_event_immediately_after_legacy_four(self):
        # PR-11a-1 contract: `event` is the 5th element (first non-legacy
        # type). α-8's later additions sit after `event`.
        self.assertEqual(ENTITY_TYPES_CORE[4], "event")

    def test_entity_types_core_matches_alpha8_horizontal_extension(self):
        # α-8 added 4 horizontal (non-vertical) types after event; the
        # ordering matters because evidence-of-absence row emission
        # walks ENTITY_TYPES_CORE in declaration order.
        self.assertEqual(
            ENTITY_TYPES_CORE,
            ("person", "concept", "org", "document",
             "event", "date", "location", "quantity", "project"),
        )

    def test_event_like_entity_types_baseline_is_just_event(self):
        # OntologyPack loader (PR-11e) extends this set at startup.
        # Until then the core baseline is exactly one member.
        self.assertEqual(EVENT_LIKE_ENTITY_TYPES, {"event"})


class OccurredAtPrecisionTests(unittest.TestCase):
    """Five quantization buckets — year, month, day, hour, minute.
    Day is the default (matches the design memo §4.1)."""

    def test_five_known_precisions(self):
        self.assertEqual(
            VALID_OCCURRED_AT_PRECISIONS,
            frozenset({"year", "month", "day", "hour", "minute"}),
        )

    def test_validate_accepts_day_precision_default(self):
        # No raise == OK
        validate_occurred_at("2026-01-10")

    def test_validate_accepts_every_known_precision(self):
        for p in VALID_OCCURRED_AT_PRECISIONS:
            with self.subTest(precision=p):
                validate_occurred_at("2026-01-10T15:32:00Z", precision=p)

    def test_validate_rejects_unknown_precision(self):
        with self.assertRaisesRegex(ValueError, "occurred_at_precision"):
            validate_occurred_at("2026-01-10", precision="quarter")


class OccurredAtFormatTests(unittest.TestCase):
    """ISO 8601 string parsing. Trailing Z accepted, naive datetimes
    accepted, anything that fromisoformat can't read is rejected."""

    def test_accepts_date_only(self):
        validate_occurred_at("2026-01-10")

    def test_accepts_datetime_with_z(self):
        validate_occurred_at("2026-01-10T15:32:00Z")

    def test_accepts_datetime_with_offset(self):
        validate_occurred_at("2026-01-10T15:32:00+09:00")

    def test_accepts_naive_datetime(self):
        validate_occurred_at("2026-01-10T15:32:00")

    def test_rejects_empty(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            validate_occurred_at("")

    def test_rejects_non_string(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            validate_occurred_at(20260110)  # type: ignore[arg-type]

    def test_rejects_garbage(self):
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            validate_occurred_at("yesterday")

    def test_rejects_us_format(self):
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            validate_occurred_at("01/10/2026")

    def test_rejects_quarter_string(self):
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            validate_occurred_at("2026-Q1")


class IdempotenceTests(unittest.TestCase):
    """validate_occurred_at is side-effect-free — repeated calls on
    the same input must not raise on the second call."""

    def test_repeated_validate_no_state_drift(self):
        for _ in range(3):
            validate_occurred_at("2026-01-10")
            validate_occurred_at("2026-01-10T15:32:00Z", precision="minute")


if __name__ == "__main__":
    unittest.main()
