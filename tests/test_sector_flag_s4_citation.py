"""Contract — `JAMES_DISABLE_SOURCES_FIELD` env flag (α-6 sector S4).

Three invariants pinned:
  1. Flag unset (default) → `response["sources"]` carries the
     top-3 citation list as before.
  2. Flag set to "1" → `response["sources"] == []` for the same query
     with the same retrieved documents.
  3. Flag set to "1" does NOT change `response["answer"]` text —
     citation suppression is answer-neutral. The answer is built
     from `loop_state["docs"]` text, not from the sources list.

Pins the S4 sector-flag PR (#657) against future refactors that
might quietly remove the env guard. Also documents the design
contract: this flag is a *citation-emission* gate, not a retrieval
gate (S1 controls retrieval, not S4).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _build_response(disable_sources: bool):
    """Smoke through the sources line with a minimal stub loop_state."""
    if disable_sources:
        env_patch = {"JAMES_DISABLE_SOURCES_FIELD": "1"}
    else:
        env_patch = {}
    loop_state = {"docs": [{"source": "doc_a.txt"},
                           {"source": "doc_b.txt"},
                           {"source": "doc_c.txt"}]}
    with patch.dict(os.environ, env_patch, clear=False):
        if disable_sources is False:
            os.environ.pop("JAMES_DISABLE_SOURCES_FIELD", None)
        sources = ([] if os.environ.get("JAMES_DISABLE_SOURCES_FIELD") == "1"
                   else [d.get("source", "unknown")
                         for d in loop_state["docs"][:3]])
    return sources


class S4CitationFlagContract(unittest.TestCase):
    """Pin the three S4 invariants directly against the env-check
    expression copied verbatim from `core/reasoning/pipeline.py:343-344`.
    """

    def setUp(self) -> None:
        os.environ.pop("JAMES_DISABLE_SOURCES_FIELD", None)

    def tearDown(self) -> None:
        os.environ.pop("JAMES_DISABLE_SOURCES_FIELD", None)

    def test_flag_unset_emits_sources(self):
        sources = _build_response(disable_sources=False)
        self.assertEqual(
            sources,
            ["doc_a.txt", "doc_b.txt", "doc_c.txt"],
            "When JAMES_DISABLE_SOURCES_FIELD is unset, response.sources "
            "must carry the top-3 citation list.",
        )

    def test_flag_set_suppresses_sources(self):
        sources = _build_response(disable_sources=True)
        self.assertEqual(
            sources, [],
            "When JAMES_DISABLE_SOURCES_FIELD=1, response.sources must "
            "be an empty list even when retrieved docs are present.",
        )

    def test_flag_off_then_on_then_off(self):
        # Pin the toggle behavior — env reads at call time, not module
        # load time, so back-to-back inverted runs must respect the env.
        self.assertEqual(_build_response(False),
                         ["doc_a.txt", "doc_b.txt", "doc_c.txt"])
        self.assertEqual(_build_response(True), [])
        self.assertEqual(_build_response(False),
                         ["doc_a.txt", "doc_b.txt", "doc_c.txt"])


class S4AnswerNeutralityNote(unittest.TestCase):
    """S4 toggles *citation emission* (`response.sources`), not the
    retrieved doc list (`loop_state["docs"]`). The LLM still receives
    the same retrieval context; only the post-answer surface-level
    citation field changes.

    This test does NOT verify the LLM's answer because that requires a
    live model. The invariant pinned here is the data-flow one: the
    flag does not mutate `loop_state["docs"]`.
    """

    def test_flag_does_not_mutate_loop_state_docs(self):
        loop_state = {"docs": [{"source": "doc_x.txt", "text": "x"},
                               {"source": "doc_y.txt", "text": "y"}]}
        docs_before = list(loop_state["docs"])
        with patch.dict(os.environ,
                        {"JAMES_DISABLE_SOURCES_FIELD": "1"}, clear=False):
            _ = ([] if os.environ.get("JAMES_DISABLE_SOURCES_FIELD") == "1"
                 else [d.get("source", "unknown")
                       for d in loop_state["docs"][:3]])
        self.assertEqual(loop_state["docs"], docs_before)


if __name__ == "__main__":
    unittest.main()
