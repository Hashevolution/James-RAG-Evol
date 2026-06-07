"""Cycle γ Phase A.4.0 — scorer base contract tests.

Pins the abstract-base / score-axis invariants every Phase A.4.1+
scorer will inherit:

  * ``ScoreAxis`` is frozen + carries an honest-framing ``notes``
    field that defaults to empty.
  * ``ExternalScorer`` is genuinely abstract — bare class cannot be
    instantiated, ``benchmark_id`` + ``score`` are required
    overrides.
  * ``index_rows_by_id`` skips non-dict rows + rows without a
    string id without raising.
  * ``validate_queries`` catches benchmark-id mismatch.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ScoreAxisSchemaTests(unittest.TestCase):
    def test_is_frozen(self):
        from eval.external import ScoreAxis
        axis = ScoreAxis(name="em", score=0.5, n_queries=10)
        with self.assertRaises(Exception):
            axis.name = "mutated"   # type: ignore[misc]

    def test_defaults(self):
        from eval.external import ScoreAxis
        axis = ScoreAxis(name="em", score=0.5, n_queries=10)
        # per_query defaults to an empty dict; notes defaults to empty string.
        self.assertEqual(axis.per_query, {})
        self.assertEqual(axis.notes, "")

    def test_per_query_default_not_shared_between_instances(self):
        """Classic mutable-default trap — every instance must get its
        own dict, not a class-level shared singleton."""
        from eval.external import ScoreAxis
        a = ScoreAxis(name="em", score=0.0, n_queries=0)
        b = ScoreAxis(name="f1", score=0.0, n_queries=0)
        self.assertIsNot(a.per_query, b.per_query)

    def test_notes_field_records_honest_framing_warning(self):
        from eval.external import ScoreAxis
        axis = ScoreAxis(
            name="citation_precision", score=0.4, n_queries=100,
            notes="string-matching fallback (no NLI backend); "
                  "score is NOT ALCE-grade",
        )
        self.assertIn("not alce-grade", axis.notes.lower())


class ExternalScorerContractTests(unittest.TestCase):
    def test_cannot_instantiate_abstract_base(self):
        from eval.external import ExternalScorer
        with self.assertRaises(TypeError):
            ExternalScorer()   # type: ignore[abstract]

    def test_subclass_missing_score_still_abstract(self):
        from eval.external import ExternalScorer

        class Half(ExternalScorer):
            @property
            def benchmark_id(self) -> str:
                return "x"

        with self.assertRaises(TypeError):
            Half()   # type: ignore[abstract]

    def test_concrete_subclass_instantiable(self):
        from eval.external import ExternalScorer, ScoreAxis

        class Tiny(ExternalScorer):
            @property
            def benchmark_id(self) -> str:
                return "tiny"

            def score(self, queries, bench_rows):
                return [ScoreAxis(name="em", score=1.0, n_queries=1)]

        scorer = Tiny()
        out = scorer.score([], [])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].name, "em")


class IndexRowsByIdTests(unittest.TestCase):
    def _make(self):
        from eval.external import ExternalScorer, ScoreAxis

        class T(ExternalScorer):
            @property
            def benchmark_id(self) -> str:
                return "T"

            def score(self, queries, bench_rows):
                return []
        return T()

    def test_basic_indexing(self):
        scorer = self._make()
        idx = scorer.index_rows_by_id([
            {"id": "a", "answer": "A"},
            {"id": "b", "answer": "B"},
        ])
        self.assertEqual(set(idx), {"a", "b"})
        self.assertEqual(idx["a"]["answer"], "A")

    def test_non_dict_rows_skipped(self):
        scorer = self._make()
        idx = scorer.index_rows_by_id([
            {"id": "a", "answer": "A"},
            "garbage row",
            42,
            {"id": "b", "answer": "B"},
        ])
        self.assertEqual(set(idx), {"a", "b"})

    def test_rows_without_id_skipped(self):
        scorer = self._make()
        idx = scorer.index_rows_by_id([
            {"id": "a"},
            {"answer": "no id here"},
            {"id": "", "answer": "empty id"},
            {"id": 42, "answer": "int id"},   # non-string id skipped
            {"id": "b"},
        ])
        self.assertEqual(set(idx), {"a", "b"})


class ValidateQueriesTests(unittest.TestCase):
    def _make(self, bid="X"):
        from eval.external import ExternalScorer

        class T(ExternalScorer):
            @property
            def benchmark_id(self) -> str:
                return bid

            def score(self, queries, bench_rows):
                return []
        return T()

    def test_matching_benchmark_passes(self):
        from eval.external import ExternalQuery
        scorer = self._make(bid="X")
        ok = [ExternalQuery(id="X-1", benchmark="X", question="?",
                             context=(), gold_answer="a")]
        # Returns None — silent pass.
        self.assertIsNone(scorer.validate_queries(ok))

    def test_mismatched_benchmark_raises(self):
        from eval.external import ExternalQuery
        scorer = self._make(bid="X")
        bad = [ExternalQuery(id="Y-1", benchmark="Y", question="?",
                              context=(), gold_answer="a")]
        with self.assertRaises(ValueError):
            scorer.validate_queries(bad)


if __name__ == "__main__":
    unittest.main()
