"""Contract — `JAMES_DISABLE_RAG_RETRIEVAL` env flag (α-6 sector S1).

Three invariants pinned:
  1. Flag unset (default) → `run_loop_0_retrieve` calls
     `engine.retrieval.hybrid_search` (via orchestrator) and
     populates `loop_state["docs"]` with results.
  2. Flag set to "1" → early-return: docs == [], doc_context == "",
     avg_vec_score == 0.0; no calls to orchestrator / hybrid_search.
  3. Flag set to "1" + an exception in the would-have-been path
     does NOT raise (early-return never enters the try-block).

This is the C_minus cell baseline — pure LLM with no retrieval.
The model must answer from parametric knowledge or refuse.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.reasoning.pipeline_loops import run_loop_0_retrieve  # noqa: E402


def _make_engine(raise_in_search: bool = False):
    eng = MagicMock()
    if raise_in_search:
        eng.retrieval.hybrid_search.side_effect = RuntimeError("boom")
    else:
        eng.retrieval.hybrid_search.return_value = [
            {"text": "doc1 text", "source": "doc1.txt", "score": 0.9},
            {"text": "doc2 text", "source": "doc2.txt", "score": 0.7},
        ]
    eng.retrieval.build_doc_context.return_value = ("ctx", 0.8)
    return eng


class S1RagRetrievalFlagContract(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("JAMES_DISABLE_RAG_RETRIEVAL", None)

    def tearDown(self) -> None:
        os.environ.pop("JAMES_DISABLE_RAG_RETRIEVAL", None)

    def test_flag_unset_calls_retrieval(self):
        eng = _make_engine()
        state: dict = {"expanded_query": "q"}
        with patch("core.orchestrator.retrieve") as mock_orch:
            mock_orch.return_value = [
                {"text": "x", "source": "a.txt", "score": 0.5},
            ]
            run_loop_0_retrieve(eng, state, "q", "employee", "prod")
            mock_orch.assert_called_once()
        # State populated.
        self.assertTrue(len(state["docs"]) >= 1)

    def test_flag_set_short_circuits(self):
        eng = _make_engine()
        state: dict = {"expanded_query": "q"}
        with patch.dict(os.environ, {"JAMES_DISABLE_RAG_RETRIEVAL": "1"}):
            with patch("core.orchestrator.retrieve") as mock_orch:
                run_loop_0_retrieve(eng, state, "q", "employee", "prod")
                mock_orch.assert_not_called()
            eng.retrieval.hybrid_search.assert_not_called()
            eng.retrieval.build_doc_context.assert_not_called()
        self.assertEqual(state["docs"], [])
        self.assertEqual(state["doc_context"], "")
        self.assertEqual(state["avg_vec_score"], 0.0)

    def test_flag_set_swallows_would_have_been_exceptions(self):
        eng = _make_engine(raise_in_search=True)
        state: dict = {"expanded_query": "q"}
        with patch.dict(os.environ, {"JAMES_DISABLE_RAG_RETRIEVAL": "1"}):
            # Must not raise even though hybrid_search would have.
            run_loop_0_retrieve(eng, state, "q", "employee", "prod")
        eng.retrieval.hybrid_search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
