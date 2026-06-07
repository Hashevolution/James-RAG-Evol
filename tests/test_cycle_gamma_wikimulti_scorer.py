"""Cycle γ Phase A.4.3 — 2WikiMultiHopQA scorer contract tests."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _query(
    *,
    qid: str = "2wiki-1",
    gold: str = "Paris",
    aliases=None,
    q_type: str = "comparison",
    supporting_facts=None,
):
    from eval.external import ExternalQuery
    return ExternalQuery(
        id=qid,
        benchmark="2wiki",
        question="?",
        context=(),
        gold_answer=gold,
        metadata={
            "answer_aliases":   aliases or [],
            "type":             q_type,
            "supporting_facts": supporting_facts or [],
            "split":            "dev",
        },
    )


def _row(qid: str, answer: str, **kwargs):
    return {"id": qid, "answer": answer, **kwargs}


class ConstructorAndValidationTests(unittest.TestCase):
    def test_benchmark_id_is_2wiki(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        self.assertEqual(WikiMultiScorer().benchmark_id, "2wiki")

    def test_validate_queries_catches_mismatch(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        with self.assertRaises(ValueError):
            s.score([_query(qid="x")._replace(benchmark="other")
                     if hasattr(_query(qid="x"), "_replace") else
                     None] if False else [
                # ExternalQuery is frozen — build a fresh wrong-benchmark
                # one directly:
                __import__("eval.external", fromlist=["ExternalQuery"])
                .ExternalQuery(id="x", benchmark="other", question="?",
                                context=(), gold_answer="a")
            ], [])


class EmF1AxesTests(unittest.TestCase):
    def test_perfect_hit(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        queries = [_query(qid="w1", gold="Paris"),
                    _query(qid="w2", gold="Tokyo")]
        rows = [_row("w1", "Paris"), _row("w2", "Tokyo")]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["em"].score, 1.0)
        self.assertEqual(axes["f1"].score, 1.0)
        self.assertEqual(axes["em"].n_queries, 2)

    def test_missing_bench_row_counts_as_miss(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        queries = [_query(qid="w1", gold="Paris"),
                    _query(qid="w2", gold="Tokyo")]
        rows = [_row("w1", "Paris")]   # w2 missing
        axes = {a.name: a for a in s.score(queries, rows)}
        # 1 hit / 2 queries
        self.assertEqual(axes["em"].score, 0.5)

    def test_alias_lifts_match(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        queries = [_query(qid="w1", gold="United States",
                            aliases=["USA", "U.S."])]
        rows = [_row("w1", "USA")]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["em"].score, 1.0)

    def test_no_queries_axis_not_measured(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        axes = {a.name: a for a in s.score([], [])}
        self.assertEqual(axes["em"].n_queries, 0)
        self.assertEqual(axes["em"].score, 0.0)
        self.assertIn("not measured", axes["em"].notes)


class PerTypeStratificationTests(unittest.TestCase):
    def test_aggregate_is_mean_of_per_type_means(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        # 2 comparison rows (one hit, one miss) + 1 inference (hit)
        # → comparison mean F1 = 0.5, inference mean F1 = 1.0
        # → aggregate = mean(0.5, 1.0) = 0.75
        queries = [
            _query(qid="c1", gold="Paris", q_type="comparison"),
            _query(qid="c2", gold="Berlin", q_type="comparison"),
            _query(qid="i1", gold="Tokyo", q_type="inference"),
        ]
        rows = [
            _row("c1", "Paris"),
            _row("c2", "London"),
            _row("i1", "Tokyo"),
        ]
        axes = {a.name: a for a in s.score(queries, rows)}
        ax = axes["f1_by_type"]
        self.assertAlmostEqual(ax.score, 0.75, places=3)
        # per_query exposes the per-type means.
        self.assertEqual(ax.per_query["comparison"], 0.5)
        self.assertEqual(ax.per_query["inference"], 1.0)
        # Only types with rows appear in per_query.
        self.assertNotIn("compositional", ax.per_query)
        self.assertNotIn("bridge-comparison", ax.per_query)

    def test_no_type_queries_axis_not_measured(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        # All four types empty → per-type axis not measured.
        queries = [_query(qid="w1", gold="X", q_type="")]
        rows = [_row("w1", "X")]
        axes = {a.name: a for a in s.score(queries, rows)}
        ax = axes["f1_by_type"]
        self.assertEqual(ax.score, 0.0)
        self.assertEqual(ax.n_queries, 0)


class SupportFactAxisTests(unittest.TestCase):
    def test_perfect_support_fact_match(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        sf = [["T0", 0], ["T1", 2]]
        queries = [_query(qid="w1", gold="X", supporting_facts=sf)]
        rows = [_row("w1", "X", predicted_supporting_facts=sf)]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["support_fact_f1"].score, 1.0)

    def test_partial_support_fact_yields_set_f1(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        gold = [["T0", 0], ["T1", 1]]
        pred = [["T0", 0], ["T2", 5]]   # 1 overlap, 1 extra
        queries = [_query(qid="w1", gold="X", supporting_facts=gold)]
        rows = [_row("w1", "X", predicted_supporting_facts=pred)]
        axes = {a.name: a for a in s.score(queries, rows)}
        # precision = 1/2, recall = 1/2 → F1 = 0.5
        self.assertAlmostEqual(axes["support_fact_f1"].score, 0.5,
                                 places=3)

    def test_string_int_sent_id_accepted(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        queries = [_query(qid="w1", gold="X",
                            supporting_facts=[["T0", 0]])]
        # Upstream serialiser emits sent_id as a string.
        rows = [_row("w1", "X",
                      predicted_supporting_facts=[["T0", "0"]])]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["support_fact_f1"].score, 1.0)

    def test_malformed_pair_dropped_silently(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        gold = [["T0", 0], ["T1", 1]]
        # One good, one malformed (missing sent_id), one good.
        pred = [["T0", 0], ["T_bad"], ["T1", 1]]
        queries = [_query(qid="w1", gold="X", supporting_facts=gold)]
        rows = [_row("w1", "X", predicted_supporting_facts=pred)]
        axes = {a.name: a for a in s.score(queries, rows)}
        # Predicted set ends up as {(T0, 0), (T1, 1)} after the
        # malformed pair is dropped → perfect match against gold.
        self.assertEqual(axes["support_fact_f1"].score, 1.0)

    def test_axis_not_measured_when_no_predicted_field(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        queries = [_query(qid="w1", gold="X",
                            supporting_facts=[["T0", 0]])]
        rows = [_row("w1", "X")]   # no predicted_supporting_facts
        axes = {a.name: a for a in s.score(queries, rows)}
        ax = axes["support_fact_f1"]
        self.assertEqual(ax.n_queries, 0)
        self.assertIn("not measured", ax.notes)

    def test_axis_skipped_when_gold_supporting_facts_empty(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = WikiMultiScorer()
        queries = [_query(qid="w1", gold="X", supporting_facts=[])]
        rows = [_row("w1", "X", predicted_supporting_facts=[])]
        axes = {a.name: a for a in s.score(queries, rows)}
        # Gold is empty so the row doesn't contribute; n_queries=0.
        self.assertEqual(axes["support_fact_f1"].n_queries, 0)


class HelperTests(unittest.TestCase):
    def test_set_f1_empty_sets(self):
        from eval.external.wikimulti_scorer import _set_f1
        # Both empty = perfect (degenerate case but SQuAD convention).
        self.assertEqual(_set_f1(set(), set()), 1.0)

    def test_set_f1_one_empty(self):
        from eval.external.wikimulti_scorer import _set_f1
        self.assertEqual(_set_f1({("T", 0)}, set()), 0.0)
        self.assertEqual(_set_f1(set(), {("T", 0)}), 0.0)

    def test_normalize_sf_pair_rejects_malformed(self):
        from eval.external.wikimulti_scorer import _normalize_sf_pair
        self.assertIsNone(_normalize_sf_pair(["only-title"]))
        self.assertIsNone(_normalize_sf_pair([42, 0]))   # title not str
        self.assertIsNone(_normalize_sf_pair("not a pair"))


if __name__ == "__main__":
    unittest.main()
