"""Cycle γ Phase A.4.4 — ALCE scorer contract tests.

Pins:
  * NLIVerifier protocol — StringContainmentVerifier is the default
    fallback (NOT ALCE-grade; honest-framing note must surface this).
  * Custom verifier callable is honoured.
  * Citation extraction regex matches ``[1]`` / ``[1, 2]`` / etc.
  * Citation precision = correct-citations / total-citations.
  * Citation recall = sentences-with-at-least-one-supporting-cite /
    sentences-with-citations.
  * Variant + verifier constructor validation.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _query(*, qid="alce-asqa-1", variant="asqa",
            docs=("doc 0 content", "doc 1 content")):
    from eval.external import ExternalQuery
    return ExternalQuery(
        id=qid,
        benchmark=f"alce-{variant}",
        question="Q?",
        context=tuple(docs),
        gold_answer="ignored for citation axes",
        metadata={"variant": variant, "retriever": "test"},
    )


def _row(qid, answer):
    return {"id": qid, "answer": answer}


class StringContainmentVerifierTests(unittest.TestCase):
    def test_default_threshold_is_half(self):
        from eval.external.alce_scorer import StringContainmentVerifier
        v = StringContainmentVerifier()
        self.assertFalse(v.is_alce_grade)
        self.assertIn("string-containment", v.name)

    def test_full_token_overlap_entails(self):
        from eval.external.alce_scorer import StringContainmentVerifier
        v = StringContainmentVerifier()
        self.assertTrue(v.verify(
            premise="OpenAI was founded by Sam Altman in 2015 with Elon Musk.",
            hypothesis="Sam Altman founded OpenAI."
        ))

    def test_no_overlap_does_not_entail(self):
        from eval.external.alce_scorer import StringContainmentVerifier
        v = StringContainmentVerifier()
        # Disjoint content tokens — the fallback does not filter
        # stopwords, so the disjointness must hold across every
        # token (this is exactly the kind of test that the
        # "NOT ALCE-grade" caveat covers: any shared function-word
        # would lift the overlap above 0.5).
        self.assertFalse(v.verify(
            premise="Mars rover Perseverance.",
            hypothesis="OpenAI Anthropic Mistral.",
        ))

    def test_threshold_is_configurable(self):
        from eval.external.alce_scorer import StringContainmentVerifier
        strict = StringContainmentVerifier(min_overlap=1.0)
        # premise has only one of the two hypothesis tokens →
        # below 1.0 → not entailed
        self.assertFalse(strict.verify("foo", "foo bar"))
        loose = StringContainmentVerifier(min_overlap=0.5)
        self.assertTrue(loose.verify("foo", "foo bar"))

    def test_invalid_threshold_raises(self):
        from eval.external.alce_scorer import StringContainmentVerifier
        with self.assertRaises(ValueError):
            StringContainmentVerifier(min_overlap=0.0)
        with self.assertRaises(ValueError):
            StringContainmentVerifier(min_overlap=1.5)

    def test_vacuous_hypothesis_counts_as_entailed(self):
        from eval.external.alce_scorer import StringContainmentVerifier
        v = StringContainmentVerifier()
        # No content tokens in the hypothesis — defaults to True
        # so that an empty claim does not fail entailment.
        self.assertTrue(v.verify("any premise", "..."))


class CitationExtractionTests(unittest.TestCase):
    def test_single_citation(self):
        from eval.external.alce_scorer import _extract_citations
        self.assertEqual(_extract_citations("Claim [1]."), [[1]])

    def test_comma_list_citation(self):
        from eval.external.alce_scorer import _extract_citations
        self.assertEqual(_extract_citations("Claim [1, 2]."), [[1, 2]])

    def test_multiple_citation_groups(self):
        from eval.external.alce_scorer import _extract_citations
        self.assertEqual(
            _extract_citations("A [1]. B [2, 3]. C [4]."),
            [[1], [2, 3], [4]],
        )

    def test_no_citations_returns_empty(self):
        from eval.external.alce_scorer import _extract_citations
        self.assertEqual(_extract_citations("No citations here."), [])

    def test_zero_or_negative_dropped(self):
        from eval.external.alce_scorer import _extract_citations
        # 0 is not a valid ALCE index (1-based) → dropped.
        self.assertEqual(_extract_citations("Claim [0, 1]."), [[1]])


class SentenceSplitTests(unittest.TestCase):
    def test_basic_split(self):
        from eval.external.alce_scorer import _split_sentences
        out = _split_sentences("First sentence. Second sentence? Third!")
        self.assertEqual(len(out), 3)


class ScorerConstructorTests(unittest.TestCase):
    def test_default_variant_is_asqa(self):
        from eval.external.alce_scorer import ALCEScorer
        s = ALCEScorer()
        self.assertEqual(s.variant, "asqa")
        self.assertEqual(s.benchmark_id, "alce-asqa")

    def test_default_verifier_is_string_containment(self):
        from eval.external.alce_scorer import (
            ALCEScorer, StringContainmentVerifier,
        )
        s = ALCEScorer()
        self.assertIsInstance(s.verifier, StringContainmentVerifier)
        self.assertFalse(s.verifier.is_alce_grade)

    def test_rejects_unknown_variant(self):
        from eval.external.alce_scorer import ALCEScorer
        with self.assertRaises(ValueError):
            ALCEScorer(variant="bogus")

    def test_custom_verifier_honoured(self):
        from eval.external.alce_scorer import ALCEScorer

        class FakeNLI:
            name = "fake-nli"
            is_alce_grade = True

            def verify(self, premise, hypothesis):
                return "yes-entail" in premise

        s = ALCEScorer(verifier=FakeNLI())
        self.assertTrue(s.verifier.is_alce_grade)
        # Smoke run: doc 0 has the magic token → entails everything.
        q = _query(qid="alce-asqa-1",
                    docs=("yes-entail doc 0", "doc 1"))
        rows = [_row("alce-asqa-1", "Claim [1]. Other [2].")]
        axes = {a.name: a for a in s.score([q], rows)}
        # 1 of 2 cites entail (cite 1 → doc 0 yes; cite 2 → doc 1 no).
        self.assertAlmostEqual(
            axes["citation_precision"].score, 0.5, places=3,
        )


class CitationAxesTests(unittest.TestCase):
    def test_perfect_entailment_yields_one(self):
        """One sentence with a cite to a doc that obviously contains
        the claim."""
        from eval.external.alce_scorer import ALCEScorer
        s = ALCEScorer()
        q = _query(
            qid="alce-asqa-q1",
            docs=("OpenAI was founded by Sam Altman in 2015 with Elon Musk.",
                  "Distractor: Mars rover updates."),
        )
        rows = [_row(
            "alce-asqa-q1",
            "Sam Altman founded OpenAI [1].",
        )]
        axes = {a.name: a for a in s.score([q], rows)}
        self.assertEqual(axes["citation_precision"].score, 1.0)
        self.assertEqual(axes["citation_recall"].score, 1.0)

    def test_wrong_citation_drops_precision(self):
        from eval.external.alce_scorer import ALCEScorer
        s = ALCEScorer()
        q = _query(
            qid="alce-asqa-q1",
            docs=("OpenAI was founded by Sam Altman in 2015 with Elon Musk.",
                  "Mars rover updates with no Altman."),
        )
        # Cite [2] is irrelevant.
        rows = [_row("alce-asqa-q1",
                     "Sam Altman founded OpenAI [2].")]
        axes = {a.name: a for a in s.score([q], rows)}
        self.assertEqual(axes["citation_precision"].score, 0.0)
        self.assertEqual(axes["citation_recall"].score, 0.0)

    def test_out_of_range_citation_counts_as_unsupported(self):
        from eval.external.alce_scorer import ALCEScorer
        s = ALCEScorer()
        q = _query(qid="alce-asqa-q1",
                    docs=("Premise text.",))
        # Citation [5] is out of range — must NOT crash and must
        # count as an unsupported citation (precision denominator).
        rows = [_row("alce-asqa-q1", "Claim [5].")]
        axes = {a.name: a for a in s.score([q], rows)}
        self.assertEqual(axes["citation_precision"].score, 0.0)

    def test_uncited_sentence_excluded_from_recall(self):
        """Sentences without citations are NOT counted in the
        recall denominator (ALCE official: only cited sentences
        are scored)."""
        from eval.external.alce_scorer import ALCEScorer
        s = ALCEScorer()
        q = _query(qid="alce-asqa-q1",
                    docs=("OpenAI was founded by Sam Altman.",))
        # 2 sentences total: only 1 cites.
        rows = [_row(
            "alce-asqa-q1",
            "Sam Altman founded OpenAI [1]. This is an aside.",
        )]
        axes = {a.name: a for a in s.score([q], rows)}
        # 1 supported / 1 with-citation → 1.0
        self.assertEqual(axes["citation_recall"].score, 1.0)
        # Recall axis n_queries reports row count, not sentence count.
        self.assertEqual(axes["citation_recall"].n_queries, 1)

    def test_no_citations_anywhere_yields_not_measured(self):
        from eval.external.alce_scorer import ALCEScorer
        s = ALCEScorer()
        q = _query(qid="alce-asqa-q1",
                    docs=("Premise.",))
        rows = [_row("alce-asqa-q1", "Answer with no citations.")]
        axes = {a.name: a for a in s.score([q], rows)}
        self.assertEqual(axes["citation_precision"].n_queries, 0)
        self.assertEqual(axes["citation_recall"].n_queries, 0)
        self.assertIn("not measured", axes["citation_precision"].notes)

    def test_multi_index_group_each_counted(self):
        from eval.external.alce_scorer import ALCEScorer
        s = ALCEScorer()
        q = _query(
            qid="alce-asqa-q1",
            docs=("OpenAI founder Sam Altman.",  # supports
                  "Unrelated doc about Mars."),  # does not
        )
        # ``[1, 2]`` cites both docs → 2 individual cite-checks,
        # one supports, one does not → precision 1/2.
        rows = [_row(
            "alce-asqa-q1",
            "Sam Altman founded OpenAI [1, 2].",
        )]
        axes = {a.name: a for a in s.score([q], rows)}
        self.assertAlmostEqual(
            axes["citation_precision"].score, 0.5, places=3,
        )
        # Recall: AT LEAST ONE cite entails → sentence supported → 1.0.
        self.assertEqual(axes["citation_recall"].score, 1.0)


class HonestFramingNotesTests(unittest.TestCase):
    def test_default_verifier_notes_flags_not_alce_grade(self):
        from eval.external.alce_scorer import ALCEScorer
        s = ALCEScorer()
        q = _query(qid="alce-asqa-q1",
                    docs=("OpenAI founder Sam Altman.",))
        rows = [_row("alce-asqa-q1", "Sam Altman founded OpenAI [1].")]
        axes = {a.name: a for a in s.score([q], rows)}
        # The notes field on every emitted axis must call out the
        # fallback so the cycle γ report cannot accidentally publish
        # the score as ALCE-grade.
        self.assertIn("NOT ALCE-grade",
                       axes["citation_precision"].notes)
        self.assertIn("NOT ALCE-grade",
                       axes["citation_recall"].notes)


class ValidationTests(unittest.TestCase):
    def test_validate_queries_catches_mismatch(self):
        from eval.external.alce_scorer import ALCEScorer
        from eval.external import ExternalQuery
        s = ALCEScorer(variant="asqa")
        bad = [ExternalQuery(
            id="x", benchmark="alce-qampari",   # mismatch
            question="?", context=(), gold_answer="a",
        )]
        with self.assertRaises(ValueError):
            s.score(bad, [])


if __name__ == "__main__":
    unittest.main()
