"""v0.4.1 PR-T2.D-1 contradiction detector contract tests.

Pins the detector's behavior so T2.D-2 (the wiring PR) and any
future caller can rely on the (existing_rel, pattern) shape.

Run:
  python -m unittest tests.test_t2d1_contradiction_detector
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lifecycle.contradiction_ingest_detector import (  # noqa: E402
    find_contradiction_candidates,
    to_classifier_edge_shape,
)


# ---------------------------------------------------------------------------
# find_contradiction_candidates
# ---------------------------------------------------------------------------

class FindContradictionCandidatesTests(unittest.TestCase):
    """Pattern P1 (different_tail) + Pattern P2 (divergent_validity)
    + the degenerate cases."""

    def test_empty_existing_returns_empty(self):
        result = find_contradiction_candidates(
            {"target": "X", "type": "CEO_OF"},
            [],
        )
        self.assertEqual(result, [])

    def test_no_predicate_returns_empty(self):
        """new_rel without predicate (no type or label) can't
        identify a contradiction edge."""
        result = find_contradiction_candidates(
            {"target": "X"},
            [{"target": "X", "type": "CEO_OF"}],
        )
        self.assertEqual(result, [])

    def test_non_dict_new_rel_returns_empty(self):
        result = find_contradiction_candidates(
            "not a dict",  # type: ignore[arg-type]
            [{"target": "X", "type": "CEO_OF"}],
        )
        self.assertEqual(result, [])

    def test_different_predicate_no_match(self):
        """Same target but different predicate = unrelated edges,
        not a contradiction. Uses identity normalizer so the
        production ontology mapping (which collapses many specific
        labels to ``RELATED_TO``) doesn't accidentally match them."""
        new = {"target": "X", "type": "CEO_OF"}
        existing = [{"target": "X", "type": "BASED_IN"}]
        result = find_contradiction_candidates(
            new, existing, predicate_normalizer=lambda x: x,
        )
        self.assertEqual(result, [])

    def test_p1_different_tail_canonical_ceo_change(self):
        """Canonical CEO-change scenario: same predicate, different
        target. THIS is the case the v0.4.1 entry memo §1 calls out."""
        new = {"target": "NewName", "type": "CEO_OF"}
        existing = [{"target": "Dario", "type": "CEO_OF"}]
        result = find_contradiction_candidates(new, existing)
        self.assertEqual(len(result), 1)
        rel, pattern = result[0]
        self.assertEqual(rel["target"], "Dario")
        self.assertEqual(pattern, "different_tail")

    def test_p2_same_pair_with_validity(self):
        """Same (target, predicate) + existing has v0.4 validity →
        divergent_validity candidate. New observation may close
        existing edge's open window."""
        new = {"target": "X", "type": "CEO_OF"}
        existing = [{
            "target": "X", "type": "CEO_OF",
            "validity": {"from": "2026-01-01", "to": None},
        }]
        result = find_contradiction_candidates(new, existing)
        self.assertEqual(len(result), 1)
        _, pattern = result[0]
        self.assertEqual(pattern, "divergent_validity")

    def test_p2_same_pair_with_status(self):
        new = {"target": "X", "type": "CEO_OF"}
        existing = [{
            "target": "X", "type": "CEO_OF",
            "status": {"active": True},
        }]
        result = find_contradiction_candidates(new, existing)
        self.assertEqual(len(result), 1)
        _, pattern = result[0]
        self.assertEqual(pattern, "divergent_validity")

    def test_p2_same_pair_with_mutation_type(self):
        new = {"target": "X", "type": "CEO_OF"}
        existing = [{
            "target": "X", "type": "CEO_OF",
            "mutation_type": "active",
        }]
        result = find_contradiction_candidates(new, existing)
        self.assertEqual(len(result), 1)
        _, pattern = result[0]
        self.assertEqual(pattern, "divergent_validity")

    def test_p2_same_pair_no_lifecycle_skipped(self):
        """Legacy edge without v0.4 metadata = safe to merge sources
        as today (the conservative-within-B variant — pre-v0.4 edges
        don't go through the classifier)."""
        new = {"target": "X", "type": "CEO_OF"}
        existing = [{"target": "X", "type": "CEO_OF"}]
        result = find_contradiction_candidates(new, existing)
        self.assertEqual(result, [])

    def test_label_used_when_type_missing(self):
        """Ingestion-shape relations sometimes have `label` instead
        of `type` (Korean labels from LLM extraction). The detector
        falls back to label."""
        new = {"target": "X", "label": "CEO_OF"}
        existing = [{"target": "Y", "label": "CEO_OF"}]
        result = find_contradiction_candidates(new, existing)
        self.assertEqual(len(result), 1)
        _, pattern = result[0]
        self.assertEqual(pattern, "different_tail")

    def test_multiple_candidates_returned_in_order(self):
        """The detector reports all candidates; the caller decides
        which to dispatch first. Uses identity normalizer so the
        production ontology mapping (which collapses many labels to
        ``RELATED_TO``) doesn't interfere with the test setup."""
        new = {"target": "NewName", "type": "CEO_OF"}
        existing = [
            {"target": "Dario", "type": "CEO_OF"},  # P1
            {
                "target": "NewName", "type": "CEO_OF",
                "validity": {"from": "2026-01-01"},
            },  # P2
            {"target": "Z", "type": "BASED_IN"},  # unrelated predicate
        ]
        result = find_contradiction_candidates(
            new, existing, predicate_normalizer=lambda x: x,
        )
        self.assertEqual(len(result), 2)
        patterns = [p for _, p in result]
        # Discovery order in existing_rels is preserved.
        self.assertEqual(patterns, ["different_tail", "divergent_validity"])

    def test_malformed_existing_rels_skipped_safely(self):
        new = {"target": "X", "type": "CEO_OF"}
        existing = [
            None,  # type: ignore[list-item]
            "not a dict",  # type: ignore[list-item]
            {},
            {"target": "Y", "type": "CEO_OF"},
        ]
        result = find_contradiction_candidates(new, existing)
        self.assertEqual(len(result), 1)

    def test_custom_normalizer_used(self):
        """If callers pass a custom predicate_normalizer (e.g. for
        non-default ontology mapping), it's applied to BOTH sides."""
        def norm(label: str) -> str:
            return "CEO" if label in ("CEO_OF", "leads") else label
        new = {"target": "X", "type": "CEO_OF"}
        existing = [{"target": "Y", "type": "leads"}]
        result = find_contradiction_candidates(
            new, existing, predicate_normalizer=norm,
        )
        self.assertEqual(len(result), 1)
        _, pattern = result[0]
        self.assertEqual(pattern, "different_tail")


# ---------------------------------------------------------------------------
# to_classifier_edge_shape
# ---------------------------------------------------------------------------

class ToClassifierEdgeShapeTests(unittest.TestCase):

    def test_passthrough_when_sources_present(self):
        """Existing relations already have sources from prior ingest
        — leave them alone."""
        rel = {
            "target": "X", "type": "CEO_OF",
            "sources": [{"doc_id": "d", "weight": 0.8}],
        }
        r = to_classifier_edge_shape(rel)
        self.assertEqual(r["target"], "X")
        self.assertEqual(r["sources"], [{"doc_id": "d", "weight": 0.8}])

    def test_synthesizes_source_from_ingest_meta(self):
        """New observations may arrive without `sources` populated
        (the LLM extractor sometimes emits flat dicts). Caller
        supplies doc_id + ts to bake a single-source view so the
        classifier rule 2 (confidence comparison) has something to
        chew on."""
        rel = {"target": "X", "type": "CEO_OF", "confidence": 0.9}
        r = to_classifier_edge_shape(
            rel, ingest_doc_id="doc_123", ingest_ts="2026-05-28T00:00:00Z",
        )
        self.assertEqual(len(r["sources"]), 1)
        s = r["sources"][0]
        self.assertEqual(s["doc_id"], "doc_123")
        self.assertEqual(s["ts"], "2026-05-28T00:00:00Z")
        self.assertEqual(s["weight"], 0.9)
        self.assertEqual(s["role"], "ingest")

    def test_synthesizes_source_with_no_confidence(self):
        """If confidence isn't a number, weight stays None — the
        classifier rule 2 handles None gracefully (best_source_weight
        returns None, rule 2 skips)."""
        rel = {"target": "X", "type": "CEO_OF"}
        r = to_classifier_edge_shape(
            rel, ingest_doc_id="doc_123", ingest_ts="2026-05-28T00:00:00Z",
        )
        self.assertEqual(len(r["sources"]), 1)
        self.assertIsNone(r["sources"][0]["weight"])

    def test_does_not_synthesize_without_ingest_doc_id(self):
        """Without ingest_doc_id, leave sources absent — caller
        already knows the rel has no source attribution."""
        rel = {"target": "X", "type": "CEO_OF"}
        r = to_classifier_edge_shape(rel)
        self.assertNotIn("sources", r)

    def test_malformed_input_returns_empty(self):
        self.assertEqual(to_classifier_edge_shape(None), {})  # type: ignore[arg-type]
        self.assertEqual(to_classifier_edge_shape("nope"), {})  # type: ignore[arg-type]

    def test_does_not_mutate_input(self):
        rel = {"target": "X", "type": "CEO_OF", "confidence": 0.9}
        before = dict(rel)
        _ = to_classifier_edge_shape(
            rel, ingest_doc_id="doc_123", ingest_ts="2026-05-28T00:00:00Z",
        )
        self.assertEqual(rel, before)


if __name__ == "__main__":
    unittest.main()
