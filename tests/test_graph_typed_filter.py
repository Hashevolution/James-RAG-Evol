"""Unit tests for α-8 Phase A typed filter module (R1-R5 compliance).

Covers:
- Runtime flag polarity (JAMES_DISABLE_TYPED_FILTER disable-on-set)
- Intent classifier keyword detection (EN + KO + fallback)
- group_entities_by_type R1-R5 compliance:
    R1 — query-relevant types always emitted (even when empty)
    R2 — empty slots flagged via present=False
    R3 — query-irrelevant non-empty types also surfaced
    R4 — query types ordered first by intent rank
    R5 — cap enforcement
- format_typed_context rendering format
- apply_typed_filter end-to-end
"""

import os
import unittest
from unittest.mock import patch

from core.graph_typed_filter import (
    apply_typed_filter,
    classify_query_intent,
    format_typed_context,
    group_entities_by_type,
    is_typed_filter_disabled,
)


class TypedFilterFlagTests(unittest.TestCase):
    """JAMES_DISABLE_TYPED_FILTER polarity (R6 — disable-polarity, default OFF)."""

    def test_unset_returns_false(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JAMES_DISABLE_TYPED_FILTER", None)
            self.assertFalse(is_typed_filter_disabled())

    def test_empty_string_returns_false(self):
        with patch.dict(os.environ, {"JAMES_DISABLE_TYPED_FILTER": ""}):
            self.assertFalse(is_typed_filter_disabled())

    def test_zero_returns_false(self):
        with patch.dict(os.environ, {"JAMES_DISABLE_TYPED_FILTER": "0"}):
            self.assertFalse(is_typed_filter_disabled())

    def test_false_string_returns_false(self):
        with patch.dict(os.environ, {"JAMES_DISABLE_TYPED_FILTER": "false"}):
            self.assertFalse(is_typed_filter_disabled())

    def test_one_returns_true(self):
        with patch.dict(os.environ, {"JAMES_DISABLE_TYPED_FILTER": "1"}):
            self.assertTrue(is_typed_filter_disabled())

    def test_truthy_string_returns_true(self):
        with patch.dict(os.environ, {"JAMES_DISABLE_TYPED_FILTER": "true"}):
            self.assertTrue(is_typed_filter_disabled())


class ClassifyQueryIntentTests(unittest.TestCase):
    """Heuristic intent classifier — keyword-based ranked type detection."""

    def test_temporal_query_maps_to_date(self):
        self.assertIn("date", classify_query_intent("When did this happen?"))

    def test_korean_temporal_query_maps_to_date(self):
        self.assertIn("date", classify_query_intent("언제 발표됐나요?"))

    def test_spatial_query_maps_to_location(self):
        self.assertIn("location", classify_query_intent("Where is the meeting?"))

    def test_korean_spatial_query_maps_to_location(self):
        self.assertIn("location", classify_query_intent("어디에 있어?"))

    def test_quantity_query(self):
        self.assertIn("quantity", classify_query_intent("How much does this cost?"))

    def test_person_query(self):
        self.assertIn("person", classify_query_intent("Who is the CEO?"))

    def test_empty_query_returns_concept_fallback(self):
        self.assertEqual(classify_query_intent(""), ["concept"])

    def test_unrecognized_query_returns_concept_fallback(self):
        result = classify_query_intent("zzz xyzzyx blorp")
        self.assertEqual(result, ["concept"])

    def test_multi_keyword_query_ranks_by_count_then_declaration_order(self):
        # "When did the CEO join the company?" matches date(1, "when") +
        # person(1, "ceo"). "company" alone does NOT match org (org wants
        # "which company"/"what company"). Tied at 1; tiebreaker = ENTITY_TYPES
        # declaration order (person 0 < date 5). So person wins.
        result = classify_query_intent("When did the CEO join the company?")
        self.assertEqual(result, ["person", "date"])

    def test_higher_count_wins_over_declaration_order(self):
        # Two date keywords (when + 언제) → date count=2, person count=1 (who).
        # Higher count wins regardless of declaration order.
        result = classify_query_intent("when 언제 who는?")
        self.assertEqual(result[0], "date")

    def test_cap_at_10_types(self):
        # 7 buckets defined; cap=10 means we never lose any
        result = classify_query_intent(
            "Who is where when company project price organization?"
        )
        self.assertLessEqual(len(result), 10)


class GroupEntitiesByTypeTests(unittest.TestCase):
    """R1-R5 compliance for the grouping function."""

    ENTITIES = [
        {"name": "Alice", "entity_type": "person"},
        {"name": "Bob", "entity_type": "person"},
        {"name": "OpenAI", "entity_type": "org"},
        {"name": "AI safety", "entity_type": "concept"},
    ]

    def test_r1_empty_query_relevant_type_emitted_with_empty_list(self):
        """R1: a query-relevant type with no matching entities still gets a row."""
        groups = group_entities_by_type(
            self.ENTITIES, query_types=["date", "event"]
        )
        type_names = [g[0] for g in groups]
        self.assertIn("date", type_names)
        self.assertIn("event", type_names)

    def test_r2_empty_slots_carry_false_present_flag(self):
        """R2: empty slots flagged so renderer can emit the explicit phrase."""
        groups = group_entities_by_type(
            self.ENTITIES, query_types=["date"]
        )
        date_slot = next(g for g in groups if g[0] == "date")
        self.assertEqual(date_slot[1], [])
        self.assertFalse(date_slot[2])

    def test_r3_non_query_types_with_entities_still_surfaced(self):
        """R3: types not in query but present in graph are kept (non-empty only)."""
        groups = group_entities_by_type(
            self.ENTITIES, query_types=["date"]
        )
        type_names = [g[0] for g in groups]
        # 'person' is not query-relevant but has 2 entities -> should appear
        self.assertIn("person", type_names)
        person_slot = next(g for g in groups if g[0] == "person")
        self.assertTrue(person_slot[2])
        self.assertEqual(len(person_slot[1]), 2)

    def test_r3_empty_non_query_types_omitted(self):
        """R3 inverse: types not in query and empty are NOT emitted."""
        groups = group_entities_by_type(
            # only person + org + concept in entities
            self.ENTITIES, query_types=["date"]
        )
        type_names = [g[0] for g in groups]
        # 'quantity', 'location', 'project' all empty + not in query → omitted
        self.assertNotIn("quantity", type_names)
        self.assertNotIn("location", type_names)
        self.assertNotIn("project", type_names)

    def test_r4_query_types_ordered_first(self):
        """R4: query_types appear before non-query types in output order."""
        groups = group_entities_by_type(
            self.ENTITIES, query_types=["date", "event"]
        )
        type_names = [g[0] for g in groups]
        date_idx = type_names.index("date")
        event_idx = type_names.index("event")
        person_idx = type_names.index("person")
        self.assertLess(date_idx, person_idx)
        self.assertLess(event_idx, person_idx)

    def test_r5_cap_limits_slot_count(self):
        """R5: total slots capped at `cap` argument."""
        groups = group_entities_by_type(
            self.ENTITIES,
            query_types=["date", "event", "location", "quantity"],
            cap=2,
        )
        self.assertEqual(len(groups), 2)
        # First two query_types take the slots
        self.assertEqual(groups[0][0], "date")
        self.assertEqual(groups[1][0], "event")

    def test_r5_within_slot_truncation_NEVER_happens(self):
        """R5: entities WITHIN a type slot are never silently truncated."""
        many_persons = [{"name": f"p{i}", "entity_type": "person"} for i in range(20)]
        groups = group_entities_by_type(many_persons, query_types=["person"])
        person_slot = next(g for g in groups if g[0] == "person")
        self.assertEqual(len(person_slot[1]), 20)

    def test_invalid_entity_dict_skipped(self):
        """Non-dict entities silently skipped (defensive)."""
        groups = group_entities_by_type(
            [None, "not a dict", {"name": "ok", "entity_type": "person"}],
            query_types=["person"],
        )
        person_slot = next(g for g in groups if g[0] == "person")
        self.assertEqual(len(person_slot[1]), 1)

    def test_missing_entity_type_defaults_to_concept(self):
        """Entities without entity_type field default to 'concept' bucket."""
        groups = group_entities_by_type(
            [{"name": "untyped"}],
            query_types=["concept"],
        )
        concept_slot = next(g for g in groups if g[0] == "concept")
        self.assertEqual(len(concept_slot[1]), 1)


class FormatTypedContextTests(unittest.TestCase):
    """Renderer format checks — exact shape consumed by the LLM."""

    def test_present_slot_renders_with_entity_names(self):
        groups = [("person", [{"name": "Alice"}, {"name": "Bob"}], True)]
        out = format_typed_context(groups)
        self.assertIn("[Person]: Alice, Bob", out)

    def test_empty_slot_renders_with_none_phrase(self):
        groups = [("date", [], False)]
        out = format_typed_context(groups)
        self.assertIn("[Date]: (none found in graph for this query)", out)

    def test_header_included(self):
        out = format_typed_context([])
        self.assertTrue(out.startswith("[ENTITIES BY TYPE]"))

    def test_type_names_capitalized_in_output(self):
        groups = [("location", [{"name": "Seoul"}], True)]
        out = format_typed_context(groups)
        self.assertIn("[Location]:", out)

    def test_custom_none_phrase_respected(self):
        groups = [("date", [], False)]
        out = format_typed_context(groups, none_phrase="<absent>")
        self.assertIn("[Date]: <absent>", out)


class ApplyTypedFilterTests(unittest.TestCase):
    """End-to-end smoke tests for the convenience wrapper."""

    def test_poison_01_analog_emits_quantity_empty_slot(self):
        """The cross-stack convergence acceptance test case from Phase 4.

        Query asks for a price ('How much') → quantity intent. Graph has
        only a denim_jacket (concept type) — no quantity entity. The
        rendered context MUST tell the LLM that quantity is absent.
        """
        rendered, groups = apply_typed_filter(
            query="How much is the brown leather jacket?",
            entities=[{"name": "denim_jacket_blue", "entity_type": "concept"}],
        )
        self.assertIn(
            "[Quantity]: (none found in graph for this query)", rendered
        )
        self.assertIn("[Concept]: denim_jacket_blue", rendered)

    def test_temporal_null_query_emits_date_empty_slot(self):
        """α-7 null query mechanism: query asks 'when' but graph has no date."""
        rendered, _ = apply_typed_filter(
            query="When did Sridevi join the cast?",
            entities=[{"name": "movie_industry", "entity_type": "concept"}],
        )
        self.assertIn("[Date]: (none found in graph for this query)", rendered)


if __name__ == "__main__":
    unittest.main()
