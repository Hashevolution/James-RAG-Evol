"""Cycle γ Phase A.4.1 — RGB scorer contract tests.

Pins the two-axis contract:

  * ``noise_robustness_accuracy`` — substring-match accuracy over
    truth-present rows.
  * ``negative_rejection_f1`` — abstention F1 confusion matrix over
    truth-absent (positive_count == 0) rows.

Builds synthetic ``ExternalQuery`` records + bench rows in tmpdir
directly — no fixture file, no loader needed.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _query(
    *,
    qid: str = "rgb-en-1",
    variant: str = "en",
    question: str = "Who?",
    gold: str = "X",
    positive_count: int = 1,
    negative_count: int = 0,
    answer_aliases=None,
):
    from eval.external import ExternalQuery
    return ExternalQuery(
        id=qid,
        benchmark=f"rgb-{variant}",
        question=question,
        context=(),
        gold_answer=gold,
        metadata={
            "positive_count":  positive_count,
            "negative_count":  negative_count,
            "answer_aliases":  answer_aliases or [],
            "variant":         variant,
            "language":        ("zh" if variant.startswith("zh")
                                else "en"),
        },
    )


def _row(qid: str, answer: str) -> dict:
    return {"id": qid, "answer": answer}


class ConstructorTests(unittest.TestCase):
    def test_default_variant_is_en(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer()
        self.assertEqual(s.variant, "en")
        self.assertEqual(s.benchmark_id, "rgb-en")

    def test_rejects_unknown_variant(self):
        from eval.external.rgb_scorer import RGBScorer
        with self.assertRaises(ValueError):
            RGBScorer(variant="bogus")

    def test_validate_queries_catches_mismatch(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        bad = [_query(qid="x", variant="zh")]
        with self.assertRaises(ValueError):
            s.score(bad, [])


class NoiseRobustnessAxisTests(unittest.TestCase):
    def test_full_hit_yields_one(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid="r1", gold="Paris"),
            _query(qid="r2", gold="Tokyo"),
        ]
        rows = [
            _row("r1", "The answer is Paris."),
            _row("r2", "Tokyo is the capital."),
        ]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["noise_robustness_accuracy"].score, 1.0)
        self.assertEqual(axes["noise_robustness_accuracy"].n_queries, 2)

    def test_partial_hit_yields_fraction(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid="r1", gold="Paris"),
            _query(qid="r2", gold="Tokyo"),
            _query(qid="r3", gold="Berlin"),
        ]
        rows = [
            _row("r1", "Paris"),
            _row("r2", "London"),    # miss
            _row("r3", "Berlin city"),
        ]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertAlmostEqual(
            axes["noise_robustness_accuracy"].score, 2 / 3, places=3,
        )

    def test_alias_match_counts_as_hit(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid="r1", gold="Washington, D.C.",
                   answer_aliases=["Washington DC", "Washington"]),
        ]
        # Model says "Washington" — counts via alias.
        axes = {a.name: a for a in
                s.score(queries, [_row("r1", "Capital is Washington.")])}
        self.assertEqual(axes["noise_robustness_accuracy"].score, 1.0)

    def test_no_truth_present_rows_yields_zero_with_note(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid="r1", positive_count=0, gold=""),
        ]
        axes = {a.name: a for a in
                s.score(queries, [_row("r1", "no idea")])}
        ax = axes["noise_robustness_accuracy"]
        self.assertEqual(ax.score, 0.0)
        self.assertEqual(ax.n_queries, 0)
        self.assertIn("not measured", ax.notes)


class NegativeRejectionAxisTests(unittest.TestCase):
    """Confusion-matrix F1 over abstention behaviour."""

    def test_perfect_abstention_f1_is_one(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid=f"n{i}", positive_count=0, gold="")
            for i in range(3)
        ]
        rows = [
            _row("n0", "I cannot find that information."),
            _row("n1", "Insufficient information available."),
            _row("n2", "I don't know the answer."),
        ]
        axes = {a.name: a for a in s.score(queries, rows)}
        self.assertEqual(axes["negative_rejection_f1"].score, 1.0)
        # Confusion matrix exposed in per_query.
        pq = axes["negative_rejection_f1"].per_query
        self.assertEqual(pq["tp"], 3.0)
        self.assertEqual(pq["fn"], 0.0)

    def test_hallucination_drops_f1(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid="n0", positive_count=0, gold=""),
            _query(qid="n1", positive_count=0, gold=""),
        ]
        rows = [
            _row("n0", "I cannot find that information."),  # TP
            _row("n1", "The answer is Marie Curie."),       # FN
        ]
        axes = {a.name: a for a in s.score(queries, rows)}
        pq = axes["negative_rejection_f1"].per_query
        self.assertEqual(pq["tp"], 1.0)
        self.assertEqual(pq["fn"], 1.0)
        # F1 = TP / (TP + 0.5*(FP+FN)) = 1 / (1 + 0.5) = 0.667
        self.assertAlmostEqual(
            axes["negative_rejection_f1"].score, 1 / 1.5, places=3,
        )

    def test_over_abstention_counts_as_fp(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid="p1", positive_count=1, gold="Paris"),
        ]
        rows = [_row("p1", "I don't know.")]   # FP (truth=present)
        axes = {a.name: a for a in s.score(queries, rows)}
        pq = axes["negative_rejection_f1"].per_query
        self.assertEqual(pq["fp"], 1.0)
        # No absent rows → F1 = 0 / (0 + 0.5*1) = 0
        self.assertEqual(axes["negative_rejection_f1"].score, 0.0)

    def test_missing_row_counted_as_abstention(self):
        """When the runner failed to emit a row for a query, the
        scorer treats the absence as abstention behaviour — TP for
        truth-absent rows, FP for truth-present."""
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid="missing", positive_count=0, gold=""),
        ]
        axes = {a.name: a for a in s.score(queries, [])}
        pq = axes["negative_rejection_f1"].per_query
        self.assertEqual(pq["tp"], 1.0)

    def test_no_absent_rows_yields_zero_with_note(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="en")
        queries = [
            _query(qid="p1", positive_count=1, gold="Paris"),
        ]
        axes = {a.name: a for a in
                s.score(queries, [_row("p1", "Paris")])}
        ax = axes["negative_rejection_f1"]
        self.assertEqual(ax.score, 0.0)
        self.assertEqual(ax.n_queries, 0)
        self.assertIn("not measured", ax.notes)


class ChineseAbstentionTests(unittest.TestCase):
    """zh variant detects Chinese abstention patterns."""

    def test_zh_abstention_recognised(self):
        from eval.external.rgb_scorer import RGBScorer
        s = RGBScorer(variant="zh")
        queries = [_query(qid="z1", variant="zh", positive_count=0,
                            gold="")]
        # 中文 "不知道" pattern.
        axes = {a.name: a for a in
                s.score(queries, [_row("z1", "对不起，我不知道答案。")])}
        self.assertEqual(axes["negative_rejection_f1"].score, 1.0)


class HelperFunctionTests(unittest.TestCase):
    def test_detects_abstention_empty_counts_as_abstain(self):
        from eval.external.rgb_scorer import _detects_abstention
        # Empty / whitespace / None all count — the model said nothing.
        self.assertTrue(_detects_abstention("", language="en"))
        self.assertTrue(_detects_abstention("   ", language="en"))
        self.assertTrue(_detects_abstention(None, language="en"))   # type: ignore[arg-type]

    def test_resolve_model_answer_prefers_answer(self):
        from eval.external.rgb_scorer import _resolve_model_answer
        self.assertEqual(
            _resolve_model_answer({"answer": "A", "output": "B"}),
            "A",
        )

    def test_resolve_model_answer_falls_back_to_output(self):
        from eval.external.rgb_scorer import _resolve_model_answer
        self.assertEqual(
            _resolve_model_answer({"output": "B"}),
            "B",
        )


if __name__ == "__main__":
    unittest.main()
