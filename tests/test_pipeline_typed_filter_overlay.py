"""α-8 Phase B — pipeline_context typed-filter overlay integration tests.

Verifies the overlay at `core/reasoning/pipeline_context.build_unified_context`
behaves correctly under both flag polarities:

- JAMES_DISABLE_TYPED_FILTER unset/0 → typed prefix prepended to graph context
- JAMES_DISABLE_TYPED_FILTER=1     → prefix skipped, byte-identical pre-α-8 path

The integration is byte-additive (original graph_context preserved verbatim);
the typed summary lands BEFORE the existing block as a structural evidence-of-
absence signal.
"""

import os
import unittest
from unittest.mock import patch

from core.reasoning.pipeline_context import build_unified_context


def _make_fake_engine():
    """Minimal engine stand-in that exposes the surface build_unified_context calls."""

    class FakeGraph:
        @staticmethod
        def build_graph_context_str(graph_entities, graph_paths, unified_score=0.0):
            return "\n[GRAPH CONTEXT (unified=0.50)]\n[Entity] Alice (person)"

    class FakeEngine:
        graph = FakeGraph()

        @staticmethod
        def _log(event, exc, user_role):
            pass

        @staticmethod
        def _elapsed(t, label):
            pass

    return FakeEngine()


def _make_loop_state(query="When did Sam Altman join?"):
    return {
        "docs": [{"text": "context", "source": "x.txt"}],
        "graph_context": [
            {"name": "Alice", "entity_type": "person"},
        ],
        "graph_paths": [],
        "doc_context": "[DOC CONTEXT]\nfoo",
        "avg_vec_score": 0.55,
        "expanded_query": query,
    }


class TypedFilterOverlayFlagTests(unittest.TestCase):
    """Polarity check: typed prefix landed iff filter is enabled."""

    def test_filter_disabled_no_prefix(self):
        """JAMES_DISABLE_TYPED_FILTER=1 → typed prefix omitted (byte-identical)."""
        with patch.dict(os.environ, {"JAMES_DISABLE_TYPED_FILTER": "1"}):
            ctx, _ = build_unified_context(
                _make_fake_engine(), _make_loop_state(), user_role="internal"
            )
        self.assertNotIn("[ENTITIES BY TYPE]", ctx)
        # Original graph context block must still be present
        self.assertIn("[GRAPH CONTEXT", ctx)

    def test_filter_enabled_prefix_inserted(self):
        """JAMES_DISABLE_TYPED_FILTER unset → typed prefix prepended."""
        env = os.environ.copy()
        env.pop("JAMES_DISABLE_TYPED_FILTER", None)
        with patch.dict(os.environ, env, clear=True):
            ctx, _ = build_unified_context(
                _make_fake_engine(), _make_loop_state(), user_role="internal"
            )
        self.assertIn("[ENTITIES BY TYPE]", ctx)
        # Original graph context block STILL present (additive)
        self.assertIn("[GRAPH CONTEXT", ctx)

    def test_filter_enabled_temporal_query_emits_date_empty_row(self):
        """Temporal query + no Date entity → '(none found)' row visible."""
        env = os.environ.copy()
        env.pop("JAMES_DISABLE_TYPED_FILTER", None)
        with patch.dict(os.environ, env, clear=True):
            ctx, _ = build_unified_context(
                _make_fake_engine(),
                _make_loop_state(query="When did Alice join?"),
                user_role="internal",
            )
        self.assertIn("[Date]: (none found in graph for this query)", ctx)

    def test_filter_enabled_person_query_includes_person_entities(self):
        """'who' query → person row populated with the entity."""
        env = os.environ.copy()
        env.pop("JAMES_DISABLE_TYPED_FILTER", None)
        with patch.dict(os.environ, env, clear=True):
            ctx, _ = build_unified_context(
                _make_fake_engine(),
                _make_loop_state(query="Who is Alice?"),
                user_role="internal",
            )
        self.assertIn("[Person]: Alice", ctx)


class TypedFilterOverlayOrderTests(unittest.TestCase):
    """Ordering check: typed prefix comes BEFORE the existing graph block."""

    def test_typed_prefix_before_graph_context_block(self):
        env = os.environ.copy()
        env.pop("JAMES_DISABLE_TYPED_FILTER", None)
        with patch.dict(os.environ, env, clear=True):
            ctx, _ = build_unified_context(
                _make_fake_engine(), _make_loop_state(), user_role="internal"
            )
        typed_idx = ctx.index("[ENTITIES BY TYPE]")
        graph_idx = ctx.index("[GRAPH CONTEXT")
        self.assertLess(typed_idx, graph_idx)


if __name__ == "__main__":
    unittest.main()
