"""v0.5 B.5.d — tests for the document-subtype intent layer.

Covers:

  * `classify_document_subtype_intent` — keyword routing into the 10
    horizontal DOCUMENT_SUBTYPES, ranking, fallback behaviour.
  * `group_documents_by_subtype` — R1-R5 contract preserved at the
    subtype level (empty slots for query-relevant subtypes, no empty
    extras for non-query subtypes).
  * `format_subtype_context` — explicit `(none found ...)` evidence-of-
    absence phrase + readable display labels.
  * `apply_document_subtype_filter` — end-to-end against the
    `tests/fixtures/v0.5_enterprise_documents.json` corpus.
  * Existing `classify_query_intent` / `apply_typed_filter` regression
    check — adding the subtype layer must NOT change entity-type-level
    behaviour.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from core.graph_typed_filter import (
    apply_document_subtype_filter,
    apply_typed_filter,
    classify_document_subtype_intent,
    classify_query_intent,
    format_subtype_context,
    group_documents_by_subtype,
)
from core.ontology import DOCUMENT_SUBTYPES

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "v0.5_enterprise_documents.json"
)


def _load_documents() -> list:
    with _FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)["documents"]


class ClassifyDocumentSubtypeIntentTests(unittest.TestCase):
    def test_empty_query_returns_empty(self):
        self.assertEqual(classify_document_subtype_intent(""), [])

    def test_no_subtype_keyword_returns_empty(self):
        # Unlike `classify_query_intent` which falls back to ['concept'],
        # the subtype layer is opt-in per-query and returns [].
        self.assertEqual(
            classify_document_subtype_intent("what is the capital of France?"),
            [],
        )

    def test_single_keyword_routes_to_subtype(self):
        self.assertEqual(
            classify_document_subtype_intent("which policy applies?"),
            ["policy"],
        )

    def test_korean_keyword_routes(self):
        self.assertIn("policy",
                      classify_document_subtype_intent("우리 정책이 뭐야?"))

    def test_two_distinct_keywords_outrank_one(self):
        # Policy matches via 2 distinct keywords ('policy' + 'guideline');
        # contract matches via 1 keyword. Policy must rank first.
        # (The classifier counts distinct matched keywords, not repetitions
        # — same behaviour as the entity-type-level classifier.)
        result = classify_document_subtype_intent(
            "is the policy aligned with our guideline and contract?"
        )
        self.assertEqual(result[0], "policy")
        self.assertIn("contract", result)

    def test_meeting_minutes_multiword(self):
        self.assertIn(
            "meeting_minutes",
            classify_document_subtype_intent("show me the meeting minutes"),
        )

    def test_cap_at_10(self):
        # All-keyword query — result still capped at 10.
        big = " ".join(["contract policy procedure memo report",
                        "specification meeting minutes standard form record"])
        self.assertLessEqual(len(classify_document_subtype_intent(big)), 10)

    def test_every_registered_subtype_has_at_least_one_keyword(self):
        # Every subtype in DOCUMENT_SUBTYPES must be matchable via at
        # least one English keyword equal to its name.
        from core.graph_typed_filter import _SUBTYPE_KEYWORDS
        for sub in DOCUMENT_SUBTYPES:
            with self.subTest(subtype=sub):
                self.assertIn(sub, _SUBTYPE_KEYWORDS,
                              f"{sub!r} has no keyword entry")
                self.assertTrue(len(_SUBTYPE_KEYWORDS[sub]) >= 2,
                                f"{sub!r} should have ≥2 keywords")


class GroupDocumentsBySubtypeTests(unittest.TestCase):
    def setUp(self):
        self.docs = [
            {"doc_id": "d1", "subtype": "policy",   "title": "P1"},
            {"doc_id": "d2", "subtype": "policy",   "title": "P2"},
            {"doc_id": "d3", "subtype": "contract", "title": "C1"},
            {"doc_id": "d4", "subtype": "form",     "title": "F1"},
            {"doc_id": "d5",                        "title": "no-subtype"},
        ]

    def test_query_subtype_with_documents_emits_present_row(self):
        groups = group_documents_by_subtype(self.docs, ["policy"])
        names = {g[0]: g for g in groups}
        self.assertIn("policy", names)
        sub, docs, present = names["policy"]
        self.assertEqual(len(docs), 2)
        self.assertTrue(present)

    def test_query_subtype_with_no_documents_emits_empty_row_r1(self):
        # R1: never silently drop a query-relevant subtype.
        groups = group_documents_by_subtype(self.docs, ["report"])
        report_rows = [g for g in groups if g[0] == "report"]
        self.assertEqual(len(report_rows), 1)
        sub, docs, present = report_rows[0]
        self.assertEqual(docs, [])
        self.assertFalse(present)

    def test_query_subtypes_ordered_first_r4(self):
        # R4: intent-rank order honoured.
        groups = group_documents_by_subtype(
            self.docs, ["form", "policy"]
        )
        self.assertEqual(groups[0][0], "form")
        self.assertEqual(groups[1][0], "policy")

    def test_non_query_non_empty_subtypes_emit_as_extras_r3(self):
        # 'contract' and 'form' weren't queried but exist non-empty.
        groups = group_documents_by_subtype(self.docs, ["policy"])
        subtypes_in_out = [g[0] for g in groups]
        self.assertIn("policy", subtypes_in_out)
        self.assertIn("contract", subtypes_in_out)
        self.assertIn("form", subtypes_in_out)

    def test_no_empty_extras_r3_inverse(self):
        # 'report' was NOT queried and has no documents — must not appear.
        groups = group_documents_by_subtype(self.docs, ["policy"])
        names = [g[0] for g in groups]
        self.assertNotIn("report", names)

    def test_documents_without_subtype_silently_skipped(self):
        groups = group_documents_by_subtype(self.docs, ["policy"])
        all_doc_ids = [d.get("doc_id") for _, docs, _ in groups for d in docs]
        self.assertNotIn("d5", all_doc_ids)

    def test_cap_r5(self):
        # 12 query subtypes asked but cap=3 → at most 3 slots out.
        query_subs = list(DOCUMENT_SUBTYPES.keys())[:12]
        groups = group_documents_by_subtype(self.docs, query_subs, cap=3)
        self.assertLessEqual(len(groups), 3)


class FormatSubtypeContextTests(unittest.TestCase):
    def test_renders_present_and_empty_slots(self):
        groups = [
            ("policy", [{"title": "Data retention"}], True),
            ("report", [], False),
        ]
        text = format_subtype_context(groups)
        self.assertIn("[Policy]:", text)
        self.assertIn("[Report]:", text)
        self.assertIn("Data retention", text)
        self.assertIn("(none found", text)

    def test_multiword_subtype_display(self):
        groups = [("meeting_minutes", [{"title": "Q2 review"}], True)]
        text = format_subtype_context(groups)
        self.assertIn("[Meeting Minutes]:", text)

    def test_header_present(self):
        groups = [("policy", [{"title": "X"}], True)]
        text = format_subtype_context(groups)
        self.assertTrue(text.startswith("[DOCUMENTS BY SUBTYPE]"))


class ApplyDocumentSubtypeFilterFixtureTests(unittest.TestCase):
    """End-to-end against the v0.5 enterprise fixture."""

    @classmethod
    def setUpClass(cls):
        cls.docs = _load_documents()

    def test_policy_query_finds_data_retention(self):
        rendered, groups = apply_document_subtype_filter(
            "which policy is in force?", self.docs
        )
        self.assertIn("Data retention policy", rendered)
        policy_rows = [g for g in groups if g[0] == "policy"]
        self.assertEqual(len(policy_rows), 1)
        self.assertTrue(policy_rows[0][2])  # present

    def test_specification_query_finds_both_versions(self):
        rendered, groups = apply_document_subtype_filter(
            "show me the api spec", self.docs
        )
        spec_rows = [g for g in groups if g[0] == "specification"]
        self.assertEqual(len(spec_rows), 1)
        spec_docs = spec_rows[0][1]
        # Fixture has v1 (SUPERSEDED) and v2 (PUBLISHED)
        self.assertEqual(len(spec_docs), 2)

    def test_no_subtype_keyword_returns_empty(self):
        # Generic query without a subtype keyword falls through.
        rendered, groups = apply_document_subtype_filter(
            "what is the capital of France?", self.docs
        )
        self.assertEqual(rendered, "")
        self.assertEqual(groups, [])

    def test_unmatched_subtype_emits_empty_slot_against_fixture(self):
        # Force a query for a subtype the fixture exercises:
        # 'record' exists in fixture (decision log). Verify present row.
        rendered, groups = apply_document_subtype_filter(
            "show me the decision log", self.docs
        )
        self.assertIn("Decision log", rendered)

    def test_empty_subtype_slot_for_missing_kind(self):
        # The fixture has exactly one 'meeting_minutes' doc. Construct a
        # smaller subset that contains no meeting_minutes and query for it.
        no_minutes = [d for d in self.docs if d["subtype"] != "meeting_minutes"]
        rendered, _ = apply_document_subtype_filter(
            "show me the meeting minutes", no_minutes
        )
        self.assertIn("[Meeting Minutes]:", rendered)
        self.assertIn("(none found", rendered)


class RegressionEntityTypeLayerUnchangedTests(unittest.TestCase):
    """Adding the subtype layer must not change entity-type behaviour."""

    def test_classify_query_intent_concept_fallback(self):
        self.assertEqual(classify_query_intent(""), ["concept"])
        self.assertEqual(
            classify_query_intent("what is the capital of France?"),
            ["concept"],
        )

    def test_classify_query_intent_who_routes_to_person(self):
        result = classify_query_intent("who founded this company?")
        self.assertIn("person", result)

    def test_apply_typed_filter_still_works(self):
        entities = [{"entity_type": "person", "name": "Alice"}]
        rendered, groups = apply_typed_filter("who is the author?", entities)
        self.assertIn("[ENTITIES BY TYPE]", rendered)
        self.assertIn("Alice", rendered)


if __name__ == "__main__":
    unittest.main()
