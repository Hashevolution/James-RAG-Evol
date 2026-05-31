"""Contract — `JAMES_DISABLE_GRAPH` env flag (α-6 sector S2).

Three invariants pinned:
  1. Flag unset (default) → `run_loop_1_expand` calls the graph
     traversal stack (engine.graph.* / engine.retrieval.*); the
     normal `entities_extracted / graph_nodes / paths_walked`
     observability fields appear.
  2. Flag set to "1" → early-return: `loop_state["graph_context"]`
     and `loop_state["graph_paths"]` both set to `[]`, no calls to
     the graph engine.
  3. Flag set to "1" + an exception in the would-have-been path
     does NOT raise (we never enter the try-block at all).

Pins the S2 sector-flag PR (#658) against future refactors that
might quietly remove the early-return.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.reasoning.pipeline_loops import run_loop_1_expand  # noqa: E402


def _make_engine(raise_on_extract: bool = False):
    """Stub engine with the minimum surface `run_loop_1_expand` uses."""
    eng = MagicMock()
    if raise_on_extract:
        eng.retrieval.extract_entities.side_effect = RuntimeError("boom")
    else:
        eng.retrieval.extract_entities.return_value = ["E1", "E2"]
    eng.graph.build_entity_map_snapshot.return_value = {}
    eng.graph.match_entities.return_value = ["id1"]
    eng.graph.validate_integrity.return_value = ["id1"]
    eng.graph.expand_dynamic.return_value = (
        [{"node": "n1"}], [{"path": "p1"}]
    )
    eng.graph.rank_nodes.return_value = [{"node": "n1"}]
    eng.graph.verify_reasoning.return_value = [{"path": "p1"}]
    eng.security.filter_graph.return_value = [{"node": "n1"}]
    return eng


class S2GraphFlagContract(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("JAMES_DISABLE_GRAPH", None)

    def tearDown(self) -> None:
        os.environ.pop("JAMES_DISABLE_GRAPH", None)

    def test_flag_unset_calls_graph_stack(self):
        eng = _make_engine()
        state: dict = {"docs": [{"text": "alpha"}]}
        run_loop_1_expand(eng, state, "q", "employee", "prod")
        # Graph engine surfaces were exercised.
        eng.retrieval.extract_entities.assert_called_once()
        eng.graph.expand_dynamic.assert_called_once()
        # State populated.
        self.assertNotEqual(state["graph_paths"], [],
                            "flag-off path should populate graph_paths")

    def test_flag_set_short_circuits(self):
        eng = _make_engine()
        state: dict = {"docs": [{"text": "alpha"}]}
        with patch.dict(os.environ, {"JAMES_DISABLE_GRAPH": "1"}):
            run_loop_1_expand(eng, state, "q", "employee", "prod")
        # No graph engine calls.
        eng.retrieval.extract_entities.assert_not_called()
        eng.graph.expand_dynamic.assert_not_called()
        # State populated with empty lists.
        self.assertEqual(state["graph_context"], [])
        self.assertEqual(state["graph_paths"], [])

    def test_flag_set_swallows_would_have_been_exceptions(self):
        # Even though the engine would raise inside extract_entities,
        # the flag-on path never reaches that branch.
        eng = _make_engine(raise_on_extract=True)
        state: dict = {"docs": [{"text": "alpha"}]}
        with patch.dict(os.environ, {"JAMES_DISABLE_GRAPH": "1"}):
            # Must not raise.
            run_loop_1_expand(eng, state, "q", "employee", "prod")
        eng.retrieval.extract_entities.assert_not_called()


if __name__ == "__main__":
    unittest.main()
