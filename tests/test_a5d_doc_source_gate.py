"""[#A5-D opt 2] Document → entity hop must respect target's sources field.

Background
----------
The Palantir → 비트코인 spurious path:

    Palantir → PLTR_03(doc) → Morgan Stanley → MSBT → 비트코인

The load-bearing weak link is hop 2 — `PLTR_03(doc) → Morgan Stanley`.
PLTR_03 mentions Morgan Stanley but is NOT a source document for
Morgan Stanley (Morgan Stanley's `sources:` only lists
`09_MorganStanley_MSBT출시.txt`). Old DFS treated all of a doc's
outbound RELATED_TO edges as equivalent and freely traversed them,
turning incidental mentions into reasoning hops.

This gate restricts document → entity outbound traversal to entities
whose `sources:` list contains this document. The rule does NOT apply
to entity → entity hops, so the 78% inferred-0.7 graph backbone that
broke option 1's bench is untouched here.

Run:
    python -m unittest tests.test_a5d_doc_source_gate
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class GateUnitTests(unittest.TestCase):
    """Direct tests on the _doc_outgoing_hop_valid helper."""

    def setUp(self):
        from core import graph_engine as ge
        self.fn = ge._doc_outgoing_hop_valid

    def test_non_doc_source_passes_unconditionally(self):
        # The whole point of the surgical fix — entity → entity edges
        # are NOT subject to this gate (option 1's mistake).
        source = {"entity_type": "org", "name": "Morgan Stanley"}
        target = {"entity_type": "concept", "name": "MSBT"}
        self.assertTrue(self.fn(source, target),
            "non-document source must always pass — gate only governs "
            "document → entity outbound edges")

    def test_concept_to_concept_passes(self):
        source = {"entity_type": "concept", "name": "MSBT"}
        target = {"entity_type": "concept", "name": "비트코인"}
        self.assertTrue(self.fn(source, target))

    def test_doc_to_primary_entity_passes(self):
        # The legitimate pattern: doc D, entity E with D in E.sources.
        source = {
            "entity_type": "document",
            "name": "PLTR_01_Q1_2026_실적분석",
        }
        target = {
            "entity_type": "org",
            "name": "Palantir Technologies (PLTR)",
            "sources": ["PLTR_01_Q1_2026_실적분석.pdf"],
        }
        self.assertTrue(self.fn(source, target),
            "doc → its primary entity must pass — this is the "
            "legitimate doc-to-subject hop")

    def test_doc_to_tangentially_mentioned_entity_blocked(self):
        # The exact case that produced the spurious Palantir → 비트코인
        # path: PLTR_03 doc mentions Morgan Stanley but is not a Morgan
        # Stanley source.
        source = {
            "entity_type": "document",
            "name": "PLTR_03_밸류에이션_리스크_분석",
        }
        target = {
            "entity_type": "org",
            "name": "Morgan Stanley",
            # Morgan Stanley's actual sources field — PLTR_03 is NOT here.
            "sources": ["09_MorganStanley_MSBT출시.txt"],
        }
        self.assertFalse(self.fn(source, target),
            "doc → tangentially-mentioned entity MUST be blocked — "
            "this is the load-bearing fix for the Palantir → 비트코인 "
            "spurious path")

    def test_doc_name_substring_match_in_source_filename(self):
        # Source filenames carry an extension (.pdf, .txt) but document
        # entity names are stems. Match by substring.
        source = {
            "entity_type": "document",
            "name": "01_ETF_단일일최강유입_5월1일",
        }
        target = {
            "entity_type": "concept",
            "name": "비트코인",
            "sources": [
                "01_ETF_단일일최강유입_5월1일.txt",
                "05_Strategy매입중단_Q1실적임박.txt",
            ],
        }
        self.assertTrue(self.fn(source, target),
            "stem-in-filename match must succeed — sources list carries "
            "extension, doc.name is the stem")

    def test_doc_with_empty_sources_target_blocked(self):
        # Defense — entity created without a sources field shouldn't
        # collect inbound from arbitrary docs.
        source = {"entity_type": "document", "name": "some_doc"}
        target = {"entity_type": "org", "name": "FOO", "sources": []}
        self.assertFalse(self.fn(source, target))

    def test_doc_target_with_none_sources_passes_permissively(self):
        # Malformed entity (no sources field at all) — gate is permissive
        # so other validation layers can handle. This is the "missing
        # field is not a security failure" stance — sensitive_layer +
        # ontology strict still apply.
        source = {"entity_type": "document", "name": "some_doc"}
        target = {"entity_type": "org", "name": "FOO"}   # no sources key
        self.assertFalse(self.fn(source, target),
            "missing sources field on target → no whitelist match → "
            "should still be blocked (permissive only when source is "
            "non-doc or input itself is malformed)")

    def test_missing_source_entity_passes(self):
        self.assertTrue(self.fn(None, {"entity_type": "org", "name": "X"}))
        self.assertTrue(self.fn({}, {"entity_type": "org", "name": "X"}))

    def test_doc_with_no_name_passes(self):
        # Without a doc name to match, can't apply the rule. Other gates
        # should catch this case.
        source = {"entity_type": "document", "name": ""}
        target = {"entity_type": "org", "name": "X", "sources": []}
        self.assertTrue(self.fn(source, target))

    def test_target_with_malformed_sources_passes(self):
        source = {"entity_type": "document", "name": "doc"}
        target = {"entity_type": "org", "name": "X", "sources": "string-not-list"}
        self.assertTrue(self.fn(source, target),
            "malformed sources field → defer to other gates")


class PalantirBitcoinPathRegressionTests(unittest.TestCase):
    """End-to-end check: the documented spurious path is broken."""

    def setUp(self):
        from core import graph_engine as ge
        self.fn = ge._doc_outgoing_hop_valid

    def test_load_bearing_hop_pltr03_to_morgan_stanley_blocked(self):
        # Real frontmatter from wiki/entity/prod/document/
        # pltr_03_밸류에이션_리스크_분석.md and
        # wiki/entity/prod/org/morgan_stanley.md.
        pltr_03 = {
            "entity_type": "document",
            "name": "PLTR_03_밸류에이션_리스크_분석",
            "sources": ["PLTR_03_밸류에이션_리스크_분석.pdf"],
        }
        morgan_stanley = {
            "entity_type": "org",
            "name": "Morgan Stanley",
            "sources": ["09_MorganStanley_MSBT출시.txt"],   # PLTR_03 NOT here
        }
        self.assertFalse(self.fn(pltr_03, morgan_stanley),
            "the bridge hop in the Palantir → 비트코인 spurious path "
            "MUST be cut by the new gate — this is why we landed here")

    def test_msbt_to_bitcoin_still_passes(self):
        # Ensure we don't break the rest of the graph: MSBT (concept) →
        # 비트코인 (concept) is non-doc-source, gate passes.
        msbt = {"entity_type": "concept", "name": "MSBT"}
        btc  = {"entity_type": "concept", "name": "비트코인"}
        self.assertTrue(self.fn(msbt, btc),
            "concept → concept is unaffected — only doc → entity is gated")

    def test_blackrock_doc_to_bitcoin_passes_when_doc_is_source(self):
        # Reverse direction sanity: docs that are PRIMARY sources of
        # 비트코인 (e.g. 01_ETF_단일일최강유입_5월1일) should reach it.
        doc = {
            "entity_type": "document",
            "name": "01_ETF_단일일최강유입_5월1일",
        }
        btc = {
            "entity_type": "concept",
            "name": "비트코인",
            "sources": [
                "01_ETF_단일일최강유입_5월1일.txt",
                "05_Strategy매입중단_Q1실적임박.txt",
            ],
        }
        self.assertTrue(self.fn(doc, btc),
            "legitimate doc-as-primary-source hops must remain — only "
            "tangential mentions are blocked")


class IntegrationWithExpandDynamicTests(unittest.TestCase):
    """Verify the gate is plumbed into expand_dynamic's DFS body."""

    def test_dfs_calls_doc_gate(self):
        import inspect
        from core import graph_engine as ge
        src = inspect.getsource(ge.GraphEngine.expand_dynamic)
        self.assertIn("_doc_outgoing_hop_valid", src,
            "expand_dynamic must call _doc_outgoing_hop_valid as part "
            "of its per-rel filter chain")
        # Helper exists and is at module level (free function).
        self.assertTrue(callable(ge._doc_outgoing_hop_valid))


if __name__ == "__main__":
    unittest.main()
