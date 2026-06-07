"""Cycle γ Phase A.4.2 — MuSiQue scorer contract tests."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _query(
    *,
    qid: str = "musique-ans-1",
    variant: str = "ans",
    gold: str = "Sam Bankman-Fried",
    aliases=None,
    support_idx_set=None,
):
    from eval.external import ExternalQuery
    return ExternalQuery(
        id=qid,
        benchmark=f"musique-{variant}",
        question="Multi-hop Q?",
        context=(),
        gold_answer=gold,
        metadata={
            "answer_aliases":  aliases or [],
            "support_idx_set": support_idx_set or [],
            "variant":         variant,
            "split":           "dev",
        },
    )


def _row(qid: str, answer: str, **kwargs):
    return {"id": qid, "answer": answer, **kwargs}


class NormalisationTests(unittest.TestCase):
    def test_lowercase_and_punctuation_stripped(self):
        from eval.external.musique_scorer import _normalize_answer
        self.assertEqual(_normalize_answer("The Big Apple!"), "big apple")

    def test_articles_dropped(self):
        from eval.external.musique_scorer import _normalize_answer
        self.assertEqual(_normalize_answer("a tree"), "tree")
        self.assertEqual(_normalize_answer("An apple"), "apple")
        self.assertEqual(_normalize_answer("THE quick brown fox"),
                          "quick brown fox")

    def test_whitespace_collapsed(self):
        from eval.external.musique_scorer import _normalize_answer
        self.assertEqual(
            _normalize_answer("  many   spaces  here  "),
            "many spaces here",
        )


class TokenF1Tests(unittest.TestCase):
    def test_identical_strings_f1_is_one(self):
        from eval.external.musique_scorer import _f1
        self.assertEqual(_f1("Sam Bankman-Fried", "Sam Bankman-Fried"), 1.0)

    def test_no_overlap_f1_is_zero(self):
        from eval.external.musique_scorer import _f1
        self.assertEqual(_f1("Paris", "Berlin"), 0.0)

    def test_partial_overlap_yields_harmonic_mean(self):
        from eval.external.musique_scorer import _f1
        # Articles are dropped by normalisation; pick a non-article
        # third token so the partial overlap is genuine.
        # Prediction has 3 tokens ("big", "juicy", "apple"), gold has 2
        # ("big", "apple"); intersection 2.
        # precision = 2/3, recall = 2/2 = 1 → F1 = 2 * (2/3) / (1 + 2/3) = 0.8
        self.assertAlmostEqual(_f1("big juicy apple", "big apple"),
                                 0.8, places=3)

    def test_both_empty_strings_f1_is_one(self):
        from eval.external.musique_scorer import _f1
        self.assertEqual(_f1("", ""), 1.0)

    def test_one_empty_f1_is_zero(self):
        from eval.external.musique_scorer import _f1
        self.assertEqual(_f1("Paris", ""), 0.0)
        self.assertEqual(_f1("", "Paris"), 0.0)


class ExactMatchTests(unittest.TestCase):
    def test_em_after_normalisation(self):
        from eval.external.musique_scorer import _exact_match
        self.assertEqual(_exact_match("The Big Apple!", "big apple"), 1)
        self.assertEqual(_exact_match("Paris.", "Paris"), 1)
        self.assertEqual(_exact_match("Paris", "Berlin"), 0)


class AliasMaxTests(unittest.TestCase):
    def test_max_em_picks_alias_when_gold_misses(self):
        from eval.external.musique_scorer import _max_em
        # Gold mismatches, alias matches → EM = 1.
        self.assertEqual(
            _max_em("Washington DC", "Washington, D.C.",
                     ["Washington DC", "Washington"]),
            1,
        )

    def test_max_f1_picks_best_alias(self):
        from eval.external.musique_scorer import _max_f1
        # Alias "Washington" yields a single-token match.
        f1 = _max_f1("Washington", "Washington, D.C.",
                      ["Washington DC", "Washington"])
        self.assertEqual(f1, 1.0)


class ScorerAxesTests(unittest.TestCase):
    def test_em_and_f1_with_one_hit(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer(variant="ans")
        queries = [
            _query(qid="m1", gold="Paris"),
            _query(qid="m2", gold="Tokyo"),
        ]
        rows = [
            _row("m1", "The capital is Paris."),  # F1 partial, EM 0
            _row("m2", "Tokyo"),                  # EM + F1 1.0
        ]
        axes = {a.name: a for a in s.score(queries, rows)}
        # m1: pred tokens = "the capital is paris" → "capital is paris"
        # gold tokens = "paris" → overlap=1
        # precision = 1/3, recall = 1/1 → F1 = 0.5
        # m2: F1 = 1
        self.assertAlmostEqual(axes["f1"].score, (0.5 + 1.0) / 2,
                                 places=3)
        # EM: m1 = 0, m2 = 1 → 0.5
        self.assertEqual(axes["em"].score, 0.5)

    def test_missing_bench_row_counts_as_miss(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer(variant="ans")
        queries = [
            _query(qid="m1", gold="Paris"),
            _query(qid="m2", gold="Tokyo"),
        ]
        rows = [_row("m1", "Paris")]   # no row for m2
        axes = {a.name: a for a in s.score(queries, rows)}
        # 1 hit / 2 queries
        self.assertEqual(axes["em"].score, 0.5)

    def test_alias_max_lifts_em_and_f1(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer(variant="ans")
        queries = [
            _query(qid="m1", gold="Washington, D.C.",
                   aliases=["Washington DC", "Washington"]),
        ]
        # Model says just "Washington" — alias matches exactly.
        rows = [_row("m1", "Washington")]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["em"].score, 1.0)
        self.assertEqual(axes["f1"].score, 1.0)


class SupportIdxAxisTests(unittest.TestCase):
    def test_support_axis_skipped_when_no_predicted_field(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer()
        queries = [_query(qid="m1", gold="X",
                            support_idx_set=[0, 2])]
        # Bench row carries no predicted_support_idx field.
        axes = {a.name: a for a in
                s.score(queries, [_row("m1", "X")])}
        ax = axes["support_idx_recall"]
        self.assertEqual(ax.score, 0.0)
        self.assertEqual(ax.n_queries, 0)
        self.assertIn("not measured", ax.notes)

    def test_perfect_support_recall(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer()
        queries = [_query(qid="m1", gold="X",
                            support_idx_set=[0, 2])]
        rows = [_row("m1", "X", predicted_support_idx=[0, 2])]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["support_idx_recall"].score, 1.0)
        self.assertEqual(axes["support_idx_recall"].n_queries, 1)

    def test_partial_support_recall(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer()
        queries = [_query(qid="m1", gold="X",
                            support_idx_set=[0, 2, 4])]
        rows = [_row("m1", "X", predicted_support_idx=[0, 4])]
        axes = {a.name: a for a in s.score(queries, rows)}
        # 2 of 3 gold supports recovered.
        self.assertAlmostEqual(
            axes["support_idx_recall"].score, 2 / 3, places=3,
        )

    def test_accepts_string_ints_in_predicted_list(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer()
        queries = [_query(qid="m1", gold="X",
                            support_idx_set=[0, 2])]
        # Some upstream serialisers emit string ints — accept those.
        rows = [_row("m1", "X", predicted_support_idx=["0", "2"])]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["support_idx_recall"].score, 1.0)


class ConstructorAndValidationTests(unittest.TestCase):
    def test_default_variant_is_ans(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer()
        self.assertEqual(s.variant, "ans")
        self.assertEqual(s.benchmark_id, "musique-ans")

    def test_rejects_unknown_variant(self):
        from eval.external.musique_scorer import MuSiQueScorer
        with self.assertRaises(ValueError):
            MuSiQueScorer(variant="bogus")

    def test_validate_queries_catches_mismatch(self):
        from eval.external.musique_scorer import MuSiQueScorer
        s = MuSiQueScorer(variant="ans")
        with self.assertRaises(ValueError):
            s.score([_query(qid="x", variant="full")], [])


if __name__ == "__main__":
    unittest.main()
