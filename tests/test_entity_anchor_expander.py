"""F9.2 — unit tests for core.retrieval.entity_anchor_expander.

Tests inject a fake ``graph_engine`` so the suite is independent of
the operator's prod wiki. The CI runs against test/ fixtures only.

Coverage:
  * surface index build: frontmatter name + aliases + alias pack
  * substring match: case-insensitive, KO/EN, with particles
  * anchor collection: top_n cap, dedupe, skip-already-in-query
  * graceful no-op: empty / short / unknown query / missing engine
  * lazy index build + invalidate
  * module singleton lifecycle
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.retrieval.entity_anchor_expander import (  # noqa: E402
    DEFAULT_TOP_N,
    MIN_SURFACE_LENGTH,
    EntityAnchorExpander,
    _clear_singleton_for_tests,
    get_entity_anchor_expander,
)


# ─── Fake GraphEngine ────────────────────────────────────────────────


class FakeWikiGenerator:
    """Minimal stand-in. Real WikiGenerator scans the wiki dir at
    init — we skip that and just hold an in-memory frontmatter map."""

    def __init__(self, frontmatters: Dict[str, dict]):
        # entity_id_index is iterated as {eid: Path}. Tests use
        # arbitrary path strings; _read_frontmatter looks up by Path.
        self._frontmatters = frontmatters
        self.entity_id_index: Dict[str, Path] = {
            eid: Path(f"<test:{eid}>") for eid in frontmatters
        }

    def _read_frontmatter(self, filepath: Path) -> Optional[dict]:
        eid = str(filepath).removeprefix("<test:").removesuffix(">")
        return self._frontmatters.get(eid)


class FakeGraphEngine:
    """Implements just the surface used by EntityAnchorExpander:
    ``wiki_generator`` attribute + ``load_entity(eid)`` method."""

    def __init__(self, frontmatters: Dict[str, dict]):
        self.wiki_generator = FakeWikiGenerator(frontmatters)
        self._frontmatters = frontmatters

    def load_entity(self, eid: str) -> dict:
        return self._frontmatters.get(eid, {})


# ─── Fixture builders ────────────────────────────────────────────────


def _dsp_frontmatter() -> dict:
    """The actual q15-cluster entity (mirrors the real
    wiki/entity/prod/person/david_soria_parra.md shape)."""
    return {
        "entity_id":   "e_person_ce96a8e5",
        "entity_type": "person",
        "name":        "David Soria Parra",
        "normalized_name": "david_soria_parra",
        "aliases":     ["David Soria Parra"],
        "relations": [
            {
                "type":       "RELATED_TO",
                "target":     "MCP",
                "target_id":  "e_concept_9b3beb71",
                "confidence": 0.9,
            },
            {
                "type":       "RELATED_TO",
                "target":     "08_MCP_(Model_Context_Protocol)",
                "target_id":  "e_document_328538ac",
                "confidence": 0.7,
            },
        ],
    }


def _palantir_frontmatter() -> dict:
    return {
        "entity_id":   "e_org_palantir",
        "entity_type": "org",
        "name":        "Palantir Technologies (PLTR)",
        "normalized_name": "palantir",
        "aliases":     ["팔란티어", "Palantir", "PLTR"],
        "relations": [
            {"type": "HAS_CEO", "target": "Alex Karp",
             "target_id": "e_person_karp", "confidence": 0.95},
            {"type": "FOUNDED_BY", "target": "Peter Thiel",
             "target_id": "e_person_thiel", "confidence": 0.85},
        ],
    }


def _wiki(*entities: dict) -> Dict[str, dict]:
    return {e["entity_id"]: e for e in entities}


# ─── Surface index tests ─────────────────────────────────────────────


class SurfaceIndexTests(unittest.TestCase):
    def test_name_indexed(self):
        ge = FakeGraphEngine(_wiki(_dsp_frontmatter()))
        ex = EntityAnchorExpander(graph_engine=ge)
        ex._ensure_indexed()
        self.assertIn("David Soria Parra", ex._surface_index)
        self.assertEqual(
            ex._surface_index["David Soria Parra"], "e_person_ce96a8e5",
        )

    def test_aliases_indexed(self):
        ge = FakeGraphEngine(_wiki(_palantir_frontmatter()))
        ex = EntityAnchorExpander(graph_engine=ge)
        ex._ensure_indexed()
        for alias in ["팔란티어", "Palantir", "PLTR"]:
            self.assertIn(alias, ex._surface_index, f"missing alias {alias!r}")
            self.assertEqual(ex._surface_index[alias], "e_org_palantir")

    def test_canonical_name_wins_on_conflict(self):
        """Two entities with overlapping alias — first index entry
        keeps it (frontmatter is authoritative source of truth)."""
        a = {**_dsp_frontmatter(), "entity_id": "eid_a",
             "name": "Shared", "aliases": []}
        b = {**_palantir_frontmatter(), "entity_id": "eid_b",
             "name": "Other", "aliases": ["Shared"]}
        ge = FakeGraphEngine({"eid_a": a, "eid_b": b})
        ex = EntityAnchorExpander(graph_engine=ge)
        ex._ensure_indexed()
        self.assertEqual(ex._surface_index["Shared"], "eid_a",
                         "first-write should win — canonical name beats later alias")

    def test_short_surface_rejected(self):
        """Single-char aliases never enter the index — guards against
        absurd matches like an alias "M" lighting up every query."""
        ent = {**_dsp_frontmatter(), "aliases": ["A", "MCP", "X"]}
        ge = FakeGraphEngine({"e_person_ce96a8e5": ent})
        ex = EntityAnchorExpander(graph_engine=ge)
        ex._ensure_indexed()
        self.assertNotIn("A", ex._surface_index)
        self.assertNotIn("X", ex._surface_index)
        self.assertIn("MCP", ex._surface_index)
        self.assertGreaterEqual(MIN_SURFACE_LENGTH, 2)  # pin the guard value

    def test_empty_wiki_returns_empty_index(self):
        ge = FakeGraphEngine({})
        ex = EntityAnchorExpander(graph_engine=ge)
        ex._ensure_indexed()
        self.assertEqual(ex._surface_index, {})

    def test_malformed_frontmatter_skipped(self):
        """A None / non-dict frontmatter (corrupt file) must not
        break index build."""
        ge = FakeGraphEngine({
            "eid_good": _dsp_frontmatter(),
            "eid_bad":  None,  # type: ignore[dict-item]
        })
        ex = EntityAnchorExpander(graph_engine=ge)
        ex._ensure_indexed()
        self.assertIn("David Soria Parra", ex._surface_index)


# ─── expand() — the q15 case ─────────────────────────────────────────


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.ge = FakeGraphEngine(_wiki(
            _dsp_frontmatter(),
            _palantir_frontmatter(),
        ))
        self.ex = EntityAnchorExpander(graph_engine=self.ge)

    # ── core q15 acceptance ──────────────────────────────────────

    def test_bare_proper_noun_q15_form_gets_mcp_anchor(self):
        """The primary diagnosis case — must return MCP as an anchor."""
        expanded, anchors, hit = self.ex.expand("David Soria Parra가 누구야?")
        self.assertTrue(hit)
        self.assertIn("MCP", anchors)
        self.assertIn("MCP", expanded)
        self.assertIn("(관련:", expanded)

    def test_bare_proper_noun_name_only_form(self):
        expanded, anchors, hit = self.ex.expand("David Soria Parra")
        self.assertTrue(hit)
        self.assertIn("MCP", anchors)

    # ── matching invariants ──────────────────────────────────────

    def test_case_insensitive_match(self):
        expanded, anchors, hit = self.ex.expand("david soria parra")
        self.assertTrue(hit)
        self.assertIn("MCP", anchors)

    def test_korean_alias_match(self):
        expanded, anchors, hit = self.ex.expand("팔란티어의 CEO는?")
        self.assertTrue(hit)
        self.assertIn("Alex Karp", anchors)

    def test_korean_with_particle(self):
        """Substring match must work despite trailing 가/는/을 particles."""
        expanded, anchors, hit = self.ex.expand("팔란티어가 뭐야?")
        self.assertTrue(hit)
        self.assertIn("Alex Karp", anchors)

    def test_unknown_entity_returns_unchanged(self):
        expanded, anchors, hit = self.ex.expand("Foobar Baz는 누구?")
        self.assertFalse(hit)
        self.assertEqual(anchors, [])
        self.assertEqual(expanded, "Foobar Baz는 누구?")

    # ── novelty guard ────────────────────────────────────────────

    def test_anchor_already_in_query_not_re_added(self):
        """When 'MCP' is already in the query, it must NOT appear in
        the anchor list (the user's own words are not anchors)."""
        expanded, anchors, hit = self.ex.expand("MCP 설계자 David Soria Parra")
        self.assertNotIn("MCP", anchors)
        # The other (longer document name) anchor IS novel
        self.assertEqual(hit, len(anchors) > 0)

    def test_all_anchors_already_present_returns_no_hit(self):
        """When every available anchor is already in the query, hit
        is False even though an entity matched."""
        # Construct an entity whose only anchor IS the query's text.
        ent = {
            "entity_id": "e_test",
            "name":      "TestName",
            "aliases":   ["TestName"],
            "relations": [
                {"type": "RELATED_TO", "target": "TestName"},
            ],
        }
        ge = FakeGraphEngine({"e_test": ent})
        ex = EntityAnchorExpander(graph_engine=ge)
        expanded, anchors, hit = ex.expand("TestName 안내")
        self.assertFalse(hit)
        self.assertEqual(anchors, [])
        self.assertEqual(expanded, "TestName 안내")

    # ── top_n cap ────────────────────────────────────────────────

    def test_top_n_caps_anchor_count(self):
        # Build an entity with 5 novel anchors
        ent = {
            "entity_id": "e_lots",
            "name":      "Lots",
            "aliases":   ["Lots"],
            "relations": [
                {"type": "RELATED_TO", "target": f"Anchor{i}"}
                for i in range(5)
            ],
        }
        ge = FakeGraphEngine({"e_lots": ent})
        ex = EntityAnchorExpander(graph_engine=ge)
        _, anchors, hit = ex.expand("Lots 안내", top_n=2)
        self.assertTrue(hit)
        self.assertEqual(len(anchors), 2)
        self.assertEqual(anchors, ["Anchor0", "Anchor1"])

    def test_top_n_default_constant(self):
        self.assertEqual(DEFAULT_TOP_N, 3)

    def test_top_n_zero_disables_cap(self):
        ent = {
            "entity_id": "e_lots",
            "name":      "Lots",
            "aliases":   ["Lots"],
            "relations": [
                {"type": "RELATED_TO", "target": f"Anchor{i}"}
                for i in range(5)
            ],
        }
        ge = FakeGraphEngine({"e_lots": ent})
        ex = EntityAnchorExpander(graph_engine=ge)
        _, anchors, _ = ex.expand("Lots 안내", top_n=0)
        self.assertEqual(len(anchors), 5)

    # ── dedupe ───────────────────────────────────────────────────

    def test_duplicate_anchors_across_entities_dedupe(self):
        """Two entities both pointing to the same anchor → anchor
        appears once in output."""
        a = {
            "entity_id": "eid_a",
            "name":      "EntityA",
            "aliases":   ["EntityA"],
            "relations": [{"type": "RELATED_TO", "target": "Shared"}],
        }
        b = {
            "entity_id": "eid_b",
            "name":      "EntityB",
            "aliases":   ["EntityB"],
            "relations": [{"type": "RELATED_TO", "target": "Shared"}],
        }
        ge = FakeGraphEngine({"eid_a": a, "eid_b": b})
        ex = EntityAnchorExpander(graph_engine=ge)
        _, anchors, _ = ex.expand("EntityA and EntityB 비교")
        self.assertEqual(anchors.count("Shared"), 1)

    # ── return shape on edge cases ───────────────────────────────

    def test_empty_query_no_op(self):
        for val in ["", "   ", "\n\t"]:
            expanded, anchors, hit = self.ex.expand(val)
            self.assertEqual(expanded, val)
            self.assertEqual(anchors, [])
            self.assertFalse(hit)

    def test_non_string_query_no_op(self):
        for val in [None, 123, [], {}]:
            expanded, anchors, hit = self.ex.expand(val)  # type: ignore[arg-type]
            self.assertEqual(anchors, [])
            self.assertFalse(hit)

    def test_relation_with_missing_target_skipped(self):
        ent = {
            "entity_id": "e_test",
            "name":      "TestName",
            "aliases":   ["TestName"],
            "relations": [
                {"type": "RELATED_TO"},                  # no target
                {"type": "RELATED_TO", "target": ""},    # empty target
                {"type": "RELATED_TO", "target": "Good"},
            ],
        }
        ge = FakeGraphEngine({"e_test": ent})
        ex = EntityAnchorExpander(graph_engine=ge)
        _, anchors, hit = ex.expand("TestName 안내")
        self.assertEqual(anchors, ["Good"])
        self.assertTrue(hit)

    def test_non_dict_relation_skipped(self):
        ent = {
            "entity_id": "e_test",
            "name":      "TestName",
            "aliases":   ["TestName"],
            "relations": [
                "not a dict",                            # corrupt entry
                {"type": "RELATED_TO", "target": "Good"},
            ],
        }
        ge = FakeGraphEngine({"e_test": ent})
        ex = EntityAnchorExpander(graph_engine=ge)
        _, anchors, hit = ex.expand("TestName 안내")
        self.assertEqual(anchors, ["Good"])
        self.assertTrue(hit)


# ─── Lazy-index + invalidate ─────────────────────────────────────────


class LifecycleTests(unittest.TestCase):
    def test_index_built_lazily_on_first_expand(self):
        ge = FakeGraphEngine(_wiki(_dsp_frontmatter()))
        ex = EntityAnchorExpander(graph_engine=ge)
        self.assertIsNone(ex._surface_index)
        ex.expand("David Soria Parra")
        self.assertIsNotNone(ex._surface_index)

    def test_invalidate_clears_index(self):
        ge = FakeGraphEngine(_wiki(_dsp_frontmatter()))
        ex = EntityAnchorExpander(graph_engine=ge)
        ex.expand("David Soria Parra")
        self.assertIsNotNone(ex._surface_index)
        ex.invalidate_index()
        self.assertIsNone(ex._surface_index)

    def test_invalidate_picks_up_new_entities(self):
        wiki = _wiki(_dsp_frontmatter())
        ge = FakeGraphEngine(wiki)
        ex = EntityAnchorExpander(graph_engine=ge)
        # First expand — no Palantir
        _, _, hit_before = ex.expand("팔란티어의 CEO?")
        self.assertFalse(hit_before)
        # Operator ingests a new entity. Then invalidates.
        new_eid = "e_org_palantir"
        ge._frontmatters[new_eid] = _palantir_frontmatter()
        ge.wiki_generator.entity_id_index[new_eid] = Path(f"<test:{new_eid}>")
        ge.wiki_generator._frontmatters[new_eid] = _palantir_frontmatter()
        ex.invalidate_index()
        _, anchors, hit_after = ex.expand("팔란티어의 CEO?")
        self.assertTrue(hit_after)
        self.assertIn("Alex Karp", anchors)


# ─── Module-level singleton ──────────────────────────────────────────


class SingletonTests(unittest.TestCase):
    def setUp(self):
        _clear_singleton_for_tests()

    def tearDown(self):
        _clear_singleton_for_tests()

    def test_get_returns_same_instance(self):
        a = get_entity_anchor_expander()
        b = get_entity_anchor_expander()
        self.assertIs(a, b)

    def test_clear_for_tests_resets(self):
        a = get_entity_anchor_expander()
        _clear_singleton_for_tests()
        b = get_entity_anchor_expander()
        self.assertIsNot(a, b)


# ─── Defensive guards (no GraphEngine, missing attrs) ────────────────


class DefensiveGuardsTests(unittest.TestCase):
    def test_graph_engine_without_wiki_generator_returns_empty(self):
        class Broken:
            pass
        ex = EntityAnchorExpander(graph_engine=Broken())
        ex._ensure_indexed()
        self.assertEqual(ex._surface_index, {})

    def test_load_entity_missing_returns_no_op(self):
        class NoLoad:
            wiki_generator = FakeWikiGenerator(_wiki(_dsp_frontmatter()))
        ex = EntityAnchorExpander(graph_engine=NoLoad())
        _, anchors, hit = ex.expand("David Soria Parra")
        # Index built fine; load_entity missing → no anchors collected
        self.assertEqual(anchors, [])
        self.assertFalse(hit)


# ─── Default lazy GraphEngine import path ────────────────────────────


class LazyGraphEngineImportTests(unittest.TestCase):
    """When constructed without ``graph_engine``, the expander must
    import + instantiate GraphEngine on first use (not at construction).
    This is the production code path."""

    def test_default_construction_does_not_import_graph_engine(self):
        ex = EntityAnchorExpander()
        self.assertIsNone(ex._graph_engine)
        self.assertIsNone(ex._surface_index)

    def test_default_construction_imports_graph_engine_on_expand(self):
        ex = EntityAnchorExpander()
        with patch("core.graph_engine.GraphEngine") as mock_ge_cls:
            mock_instance = FakeGraphEngine(_wiki(_dsp_frontmatter()))
            mock_ge_cls.return_value = mock_instance
            ex.expand("David Soria Parra")
            mock_ge_cls.assert_called_once()
        self.assertIs(ex._graph_engine, mock_instance)


if __name__ == "__main__":
    unittest.main()
