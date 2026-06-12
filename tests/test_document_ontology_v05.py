"""v0.5 B.5 — Document ontology + lifecycle contract tests.

Pins:
  * DOCUMENT_SUBTYPES registry has all 10 subtypes; each has parent='document'
    and since='v0.5'.
  * RELATION_TYPES has 4 new document-specific relations + the existing
    SUPERSEDES preserved in T7 layer (not added here).
  * ENTERPRISE_ROLES has 4 roles, each with non-empty perms_over_doc.
  * No vertical-specific entries leak into any v0.5 registry.
  * DocumentLifecycleState enum has 7 values.
  * state_from_t1_t7 + t1_t7_from_state round-trip for every state.
  * Existing ontology contract preserved (entity types, label-to-type
    map, is_valid_relation_triple).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Vertical-specific tokens that MUST NOT appear as a full registry key
# or as a `_`-delimited token within a registry key. If any of these
# strings is an entry key (or a token-component of one), the
# implementation has violated CLAUDE.md rule #1.
#
# We use token-boundary matching (split on '_') rather than substring
# matching so that benign coincidences like 'nda' inside 'standard'
# don't false-positive.
_VERTICAL_TOKENS_FORBIDDEN = (
    "nda", "non_disclosure", "force_majeure", "governing_law",
    "term_sheet", "indemnification",                              # legal
    "recipe", "formulation", "haccp",                             # food
    "10k", "audit_rule", "position_sheet", "mifid",               # finance
    "treatment_protocol", "consent_form", "drug_interaction",     # medical
    "kyc",                                                        # finance/AML — vertical
)


def _entry_contains_vertical_token(entry_name: str) -> str:
    """Returns the offending vertical token if `entry_name` contains
    one as a token (split on '_'), else empty string.

    Token-boundary matching avoids substring false positives like
    'nda' inside 'standard'. Multi-word vertical tokens (e.g.
    'non_disclosure', '10k', 'force_majeure') are checked against
    the full lowercased entry name (with `_`-split tokens joined
    back), so 'non_disclosure_agreement' would match 'non_disclosure'.
    """
    name_lower = entry_name.lower()
    name_tokens = name_lower.split("_")
    for forbidden in _VERTICAL_TOKENS_FORBIDDEN:
        forbidden_tokens = forbidden.split("_")
        if len(forbidden_tokens) == 1:
            # Single-token forbidden: must match an exact entry token
            if forbidden in name_tokens:
                return forbidden
        else:
            # Multi-token forbidden: must appear as consecutive tokens
            joined = "_".join(name_tokens)
            if forbidden in joined.split("__"):
                continue  # paranoia: double-underscores break boundaries
            # Find as substring with surrounding underscores or boundaries
            if (
                joined == forbidden
                or joined.startswith(forbidden + "_")
                or joined.endswith("_" + forbidden)
                or ("_" + forbidden + "_") in joined
            ):
                return forbidden
    return ""


class DocumentSubtypesTests(unittest.TestCase):
    """10 generic enterprise document subtypes (design memo §3.1)."""

    EXPECTED_SUBTYPES = {
        "contract", "policy", "procedure", "memo", "report",
        "specification", "meeting_minutes", "standard", "form", "record",
    }

    def test_all_10_subtypes_present(self):
        from core.ontology import DOCUMENT_SUBTYPES
        self.assertEqual(set(DOCUMENT_SUBTYPES.keys()), self.EXPECTED_SUBTYPES)

    def test_every_subtype_has_parent_document(self):
        from core.ontology import DOCUMENT_SUBTYPES
        for subtype, info in DOCUMENT_SUBTYPES.items():
            self.assertEqual(info.get("parent"), "document",
                             f"{subtype}: parent must be 'document'")

    def test_every_subtype_has_since_v05(self):
        from core.ontology import DOCUMENT_SUBTYPES
        for subtype, info in DOCUMENT_SUBTYPES.items():
            self.assertEqual(info.get("since"), "v0.5",
                             f"{subtype}: since must be 'v0.5'")

    def test_no_vertical_specific_subtypes(self):
        from core.ontology import DOCUMENT_SUBTYPES
        for subtype in DOCUMENT_SUBTYPES:
            offender = _entry_contains_vertical_token(subtype)
            self.assertEqual(offender, "",
                             f"Vertical token {offender!r} found in subtype "
                             f"{subtype!r} — violates rule #1")


class DocumentRelationsTests(unittest.TestCase):
    """4 new document-specific relations + SUPERSEDES preserved in T7."""

    EXPECTED_NEW_RELATIONS = {
        "AUTHORED_BY", "APPROVED_BY", "REFERENCES", "DERIVED_FROM",
    }

    def test_all_4_new_relations_in_registry(self):
        from core.ontology import RELATION_TYPES
        for rel in self.EXPECTED_NEW_RELATIONS:
            self.assertIn(rel, RELATION_TYPES,
                          f"{rel} not in RELATION_TYPES")

    def test_new_relations_have_required_fields(self):
        from core.ontology import RELATION_TYPES
        required = {"label", "inverse", "transitive", "weight",
                    "sensitive", "allowed_head", "allowed_tail"}
        for rel in self.EXPECTED_NEW_RELATIONS:
            info = RELATION_TYPES[rel]
            for field in required:
                self.assertIn(field, info,
                              f"{rel} missing field {field}")

    def test_authored_by_routes_document_to_person(self):
        from core.ontology import RELATION_TYPES
        info = RELATION_TYPES["AUTHORED_BY"]
        self.assertEqual(info["allowed_head"], {"document"})
        self.assertEqual(info["allowed_tail"], {"person"})

    def test_approved_by_is_sensitive(self):
        # Per design memo §3.3: approver identity may be RBAC-restricted
        from core.ontology import RELATION_TYPES
        self.assertTrue(RELATION_TYPES["APPROVED_BY"]["sensitive"])

    def test_references_routes_document_to_document(self):
        from core.ontology import RELATION_TYPES
        info = RELATION_TYPES["REFERENCES"]
        self.assertEqual(info["allowed_head"], {"document"})
        self.assertEqual(info["allowed_tail"], {"document"})

    def test_derived_from_is_transitive(self):
        # Per design memo §3.3: DERIVED_FROM implies content inheritance,
        # transitive (A derives from B derives from C → A derives from C)
        from core.ontology import RELATION_TYPES
        self.assertTrue(RELATION_TYPES["DERIVED_FROM"]["transitive"])

    def test_korean_label_map_includes_new_relations(self):
        from core.ontology import LABEL_TO_TYPE
        self.assertEqual(LABEL_TO_TYPE.get("작성자"), "AUTHORED_BY")
        self.assertEqual(LABEL_TO_TYPE.get("승인자"), "APPROVED_BY")
        self.assertEqual(LABEL_TO_TYPE.get("참조함"), "REFERENCES")
        self.assertEqual(LABEL_TO_TYPE.get("유래"), "DERIVED_FROM")

    def test_document_allowed_relations_include_new(self):
        from core.ontology import ALLOWED_RELATIONS
        doc_rels = ALLOWED_RELATIONS["document"]
        for rel in self.EXPECTED_NEW_RELATIONS:
            self.assertIn(rel, doc_rels,
                          f"document type missing allowed relation {rel}")


class EnterpriseRolesTests(unittest.TestCase):
    """4 generic enterprise roles (design memo §3.4)."""

    EXPECTED_ROLES = {"AUTHOR", "REVIEWER", "APPROVER", "READER"}

    def test_all_4_roles_present(self):
        from core.ontology import ENTERPRISE_ROLES
        self.assertEqual(set(ENTERPRISE_ROLES.keys()), self.EXPECTED_ROLES)

    def test_every_role_has_non_empty_perms(self):
        from core.ontology import ENTERPRISE_ROLES
        for role, info in ENTERPRISE_ROLES.items():
            perms = info.get("perms_over_doc")
            self.assertIsNotNone(perms, f"{role}: perms_over_doc missing")
            self.assertGreater(len(perms), 0,
                               f"{role}: perms_over_doc must be non-empty")

    def test_reader_only_has_read(self):
        from core.ontology import ENTERPRISE_ROLES
        self.assertEqual(ENTERPRISE_ROLES["READER"]["perms_over_doc"],
                         {"read"})

    def test_author_can_edit(self):
        from core.ontology import ENTERPRISE_ROLES
        self.assertIn("edit",
                      ENTERPRISE_ROLES["AUTHOR"]["perms_over_doc"])

    def test_approver_can_approve(self):
        from core.ontology import ENTERPRISE_ROLES
        self.assertIn("approve",
                      ENTERPRISE_ROLES["APPROVER"]["perms_over_doc"])

    def test_reviewer_can_comment(self):
        from core.ontology import ENTERPRISE_ROLES
        self.assertIn("comment",
                      ENTERPRISE_ROLES["REVIEWER"]["perms_over_doc"])


class DocumentLifecycleStateTests(unittest.TestCase):
    """7 lifecycle states + roundtrip with T1+T7 (design memo §3.2)."""

    def test_all_7_states_present(self):
        from core.lifecycle.document_lifecycle import DocumentLifecycleState
        expected = {"draft", "in_review", "approved", "published",
                    "superseded", "archived", "revoked"}
        actual = {s.value for s in DocumentLifecycleState}
        self.assertEqual(actual, expected)

    def test_revoked_takes_precedence(self):
        # Even with everything else set, revoked wins
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       state_from_t1_t7)
        s = state_from_t1_t7(
            revoked=True,
            valid_from="2025-01-01", valid_to="2026-01-01",
            supersede_by="doc-002", approved_at="2024-12-01",
            in_review=True,
        )
        self.assertEqual(s, DocumentLifecycleState.REVOKED)

    def test_supersede_over_published(self):
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       state_from_t1_t7)
        s = state_from_t1_t7(valid_from="2025-01-01",
                             supersede_by="doc-new")
        self.assertEqual(s, DocumentLifecycleState.SUPERSEDED)

    def test_archived_requires_both_valid_from_and_valid_to(self):
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       state_from_t1_t7)
        s = state_from_t1_t7(valid_from="2025-01-01",
                             valid_to="2026-01-01")
        self.assertEqual(s, DocumentLifecycleState.ARCHIVED)

    def test_published_when_only_valid_from(self):
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       state_from_t1_t7)
        s = state_from_t1_t7(valid_from="2025-01-01")
        self.assertEqual(s, DocumentLifecycleState.PUBLISHED)

    def test_approved_when_only_approved_at(self):
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       state_from_t1_t7)
        s = state_from_t1_t7(approved_at="2024-12-01")
        self.assertEqual(s, DocumentLifecycleState.APPROVED)

    def test_in_review_when_flag_set(self):
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       state_from_t1_t7)
        s = state_from_t1_t7(in_review=True)
        self.assertEqual(s, DocumentLifecycleState.IN_REVIEW)

    def test_draft_when_nothing_set(self):
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       state_from_t1_t7)
        self.assertEqual(state_from_t1_t7(),
                         DocumentLifecycleState.DRAFT)

    def test_roundtrip_every_state(self):
        # state_from_t1_t7(**t1_t7_from_state(s)) == s for every s
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       state_from_t1_t7,
                                                       t1_t7_from_state)
        for s in DocumentLifecycleState:
            frontmatter = t1_t7_from_state(s)
            roundtrip = state_from_t1_t7(**frontmatter)
            self.assertEqual(roundtrip, s,
                             f"Round-trip failed for {s}: got {roundtrip}")

    def test_t1_t7_from_state_returns_minimal_set(self):
        # PUBLISHED only needs valid_from; not valid_to, not supersede_by,
        # not approved_at, not in_review (each would push to a different state)
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       t1_t7_from_state)
        frontmatter = t1_t7_from_state(DocumentLifecycleState.PUBLISHED)
        self.assertEqual(set(frontmatter.keys()), {"valid_from"})

    def test_draft_returns_empty_dict(self):
        from core.lifecycle.document_lifecycle import (DocumentLifecycleState,
                                                       t1_t7_from_state)
        self.assertEqual(t1_t7_from_state(DocumentLifecycleState.DRAFT),
                         {})


class ExistingOntologyContractPreservedTests(unittest.TestCase):
    """v0.5 B.5 must be ADDITIVE only. Existing contract preserved."""

    def test_existing_entity_types_unchanged(self):
        from core.ontology import ENTITY_TYPES
        # α-8 baseline: 9 entity types
        expected = {"person", "org", "concept", "document",
                    "event", "date", "location", "quantity", "project"}
        self.assertEqual(set(ENTITY_TYPES.keys()), expected,
                         "B.5 must not change top-level ENTITY_TYPES")

    def test_existing_relations_still_valid(self):
        from core.ontology import RELATION_TYPES
        # Spot-check: STUDIES, RELATED_TO, BELONGS_TO, OCCURRED_AT exist
        for rel in ("STUDIES", "RELATED_TO", "BELONGS_TO", "OCCURRED_AT"):
            self.assertIn(rel, RELATION_TYPES)

    def test_supersedes_not_in_relation_types_belongs_to_t7(self):
        # Per design memo §3.3: SUPERSEDES lives in T7 supersede chain
        # layer, not in RELATION_TYPES. B.5 must not add it here.
        from core.ontology import RELATION_TYPES
        self.assertNotIn("SUPERSEDES", RELATION_TYPES,
                         "SUPERSEDES belongs in T7 layer "
                         "(core/lifecycle/supersede_chain.py), "
                         "not in RELATION_TYPES")


class RuleOneComplianceTests(unittest.TestCase):
    """Every B.5 addition passes the 4-vertical test (no vertical tokens)."""

    def test_no_vertical_tokens_in_document_subtypes(self):
        from core.ontology import DOCUMENT_SUBTYPES
        for subtype in DOCUMENT_SUBTYPES:
            offender = _entry_contains_vertical_token(subtype)
            self.assertEqual(offender, "",
                             f"Vertical token {offender!r} in subtype "
                             f"{subtype!r}")

    def test_no_vertical_tokens_in_new_relations(self):
        new_relations = {"AUTHORED_BY", "APPROVED_BY",
                         "REFERENCES", "DERIVED_FROM"}
        for rel in new_relations:
            offender = _entry_contains_vertical_token(rel)
            self.assertEqual(offender, "",
                             f"Vertical token {offender!r} in relation "
                             f"{rel!r}")

    def test_no_vertical_tokens_in_enterprise_roles(self):
        from core.ontology import ENTERPRISE_ROLES
        for role in ENTERPRISE_ROLES:
            offender = _entry_contains_vertical_token(role)
            self.assertEqual(offender, "",
                             f"Vertical token {offender!r} in role {role!r}")

    def test_helper_catches_legal_specific_pattern(self):
        # Smoke test that the helper would catch a future violation
        self.assertEqual(
            _entry_contains_vertical_token("non_disclosure_agreement"),
            "non_disclosure",
        )
        self.assertEqual(_entry_contains_vertical_token("kyc_form"), "kyc")
        # And does NOT false-positive on legitimate horizontal entries
        self.assertEqual(_entry_contains_vertical_token("standard"), "")
        self.assertEqual(_entry_contains_vertical_token("contract"), "")


if __name__ == "__main__":
    unittest.main()
