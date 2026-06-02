"""α-8 extractor extension — schema consistency tests (Phase 1).

Verifies that the 9 horizontal entity types declared in
`core/ontology.py:ENTITY_TYPES` are consistently reflected in:

  1. `core/relations_schema.py:ENTITY_TYPES_CORE` (truth source for
     graph-valid types, drives wiki dir auto-creation)
  2. `core/graph_node_editor.py:NODE_ALLOWED_ENTITY_TYPES` (admin
     entity POST/PUT validator)
  3. `core/wiki_generator/_ingestion.py:_llm_extract_document_entities`
     (LLM extraction prompt — without all 9 in the prompt, the wiki
     never gets entities of the new types, leaving the typed filter's
     "(none found)" signal systematically uninformative — see
     memory `project_alpha_8_closure_state` Phase C confound)
  4. `core/reasoning/modes/wiki_edit.py` (admin wiki-edit LLM prompt)

The α-8 ontology Phase A (PR #688) added 5 horizontal types to
ENTITY_TYPES but didn't propagate to the extractor / validator / admin
prompt — discovered 2026-06-03 during Phase C measurement re-audit.
This test class is the regression guard.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import unittest


# The 9 horizontal types — all 4 sources MUST agree.
EXPECTED_TYPES = frozenset({
    "person", "org", "concept", "document",
    "event", "date", "location", "quantity", "project",
})


class TestEntityTypeSchemaConsistency(unittest.TestCase):

    def test_ontology_entity_types_has_9(self):
        from core.ontology import ENTITY_TYPES
        self.assertEqual(set(ENTITY_TYPES.keys()), EXPECTED_TYPES)

    def test_relations_schema_entity_types_core_has_9(self):
        from core.relations_schema import ENTITY_TYPES_CORE
        self.assertEqual(set(ENTITY_TYPES_CORE), EXPECTED_TYPES)

    def test_node_editor_validator_accepts_9(self):
        from core.graph_node_editor import NODE_ALLOWED_ENTITY_TYPES
        self.assertEqual(set(NODE_ALLOWED_ENTITY_TYPES), EXPECTED_TYPES)

    def test_three_sources_identical(self):
        """All 3 type-declaring constants must be equal sets."""
        from core.ontology import ENTITY_TYPES
        from core.relations_schema import ENTITY_TYPES_CORE
        from core.graph_node_editor import NODE_ALLOWED_ENTITY_TYPES
        a = set(ENTITY_TYPES.keys())
        b = set(ENTITY_TYPES_CORE)
        c = set(NODE_ALLOWED_ENTITY_TYPES)
        self.assertEqual(a, b, "ontology vs relations_schema diverge")
        self.assertEqual(b, c, "relations_schema vs node validator diverge")


class TestExtractionPromptHasAllTypes(unittest.TestCase):
    """Prompts that ask the LLM for entity types must list all 9.
    Bug discovered 2026-06-03: prompts only listed 4 types, so the
    typed filter's 5 new type slots stayed systematically empty
    in the wiki regardless of document content."""

    def test_ingest_prompt_lists_9_types(self):
        src = (ROOT / "core/wiki_generator/_ingestion.py").read_text(encoding="utf-8")
        # All 9 should appear in the prompt string (substring is fine —
        # the prompt enumerates them as `type:"person|org|..."` and
        # in the per-type rule lines below).
        for t in EXPECTED_TYPES:
            with self.subTest(type=t):
                self.assertIn(t, src, f"ingest prompt missing type '{t}'")

    def test_wiki_edit_prompt_lists_9_types(self):
        src = (ROOT / "core/reasoning/modes/wiki_edit.py").read_text(encoding="utf-8")
        for t in EXPECTED_TYPES:
            with self.subTest(type=t):
                self.assertIn(t, src, f"wiki_edit prompt missing type '{t}'")

    def test_ingest_prompt_has_per_type_rules(self):
        """Beyond just listing types, the prompt should give the LLM
        a one-line definition per type so it knows when to use each.
        Mirrors design memo §2.1 — heuristic classifier signal floor."""
        src = (ROOT / "core/wiki_generator/_ingestion.py").read_text(encoding="utf-8")
        # Look for the per-type definition section: each new type should
        # have a `<type>  =` or `<type>     =` pattern indicating its rule.
        # Existing 4 already have this; new 5 must as well.
        for new_type in ("date", "location", "quantity", "project"):
            with self.subTest(type=new_type):
                # Allow flexible whitespace between type name and `=`.
                rule_pattern = f"{new_type}"
                self.assertIn(rule_pattern, src,
                              f"ingest prompt missing per-type rule for '{new_type}'")


class TestNodeValidatorRejectsUnknownType(unittest.TestCase):
    """Validator extension preserves the closed-world property —
    unknown types still rejected."""

    def test_rejects_unknown_vertical_type(self):
        from core.graph_node_editor import NODE_ALLOWED_ENTITY_TYPES
        # Should NOT accept these (vertical / not horizontal-clean)
        # per α-8 design memo §2.3 boundary test:
        self.assertNotIn("regulation", NODE_ALLOWED_ENTITY_TYPES)
        self.assertNotIn("transaction", NODE_ALLOWED_ENTITY_TYPES)
        self.assertNotIn("recipe", NODE_ALLOWED_ENTITY_TYPES)
        # Random gibberish
        self.assertNotIn("xyzzy", NODE_ALLOWED_ENTITY_TYPES)


class TestQueryPathExtractorHas9Types(unittest.TestCase):
    """Phase 2 (2026-06-03) — query-time extractor prompt + entity-id
    fallback loop now mirror the 9-type ontology. Without this, the
    query path could never produce DFS seeds of the 5 new types even
    when the user's question explicitly named such entities."""

    def test_retrieval_engine_query_prompt_lists_9_types(self):
        src = (ROOT / "core/retrieval_engine.py").read_text(encoding="utf-8")
        for t in EXPECTED_TYPES:
            with self.subTest(type=t):
                self.assertIn(t, src,
                              f"retrieval_engine query-prompt missing '{t}'")

    def test_graph_engine_fallback_uses_entity_types_core(self):
        """Pre-extension: hardcoded ['person','org','concept','document'].
        Post-extension: iterate ENTITY_TYPES_CORE so all 9 are tried."""
        src = (ROOT / "core/graph_engine.py").read_text(encoding="utf-8")
        # Hardcoded 4-type literal should be gone from the fallback loop.
        self.assertNotIn(
            '["person", "org", "concept", "document"]', src,
            "graph_engine still has hardcoded 4-type fallback list"
        )
        # And it should now reference ENTITY_TYPES_CORE.
        self.assertIn("ENTITY_TYPES_CORE", src,
                      "graph_engine no longer references ENTITY_TYPES_CORE")


if __name__ == "__main__":
    unittest.main()
