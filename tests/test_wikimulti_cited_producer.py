"""Cycle γ D-2wiki — WikiMultiCitedProducer parser contract tests.

The producer's LLM-touching half is tested by smoke runs; the parser
half (which converts a noisy LLM completion into the validated
``predicted_supporting_facts`` list the scorer reads) must be
contract-pinned without an LLM in the loop.

Pins:
  * Anchor splitting (`SUPPORTING_FACTS:` line in any case / spacing).
  * Citation regex captures `[Title #N]` / `[ Title  #  N ]`.
  * Validation: title-in-context + sent_id-in-range; out-of-range
    drops, hallucinated titles drop, non-int sent_id drops.
  * Deduplication preserves first-occurrence order.
  * `build_cited_prompt` reads loader metadata correctly.
  * Producer bench row shape (`predicted_supporting_facts`,
    `raw_completion`, `mode=closed-corpus-cited`).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _query(*, qid="2wiki-q1", question="Q?", titles=None, sentences=None):
    from eval.external import ExternalQuery
    titles = titles or ["Alice", "Wonderland"]
    sentences = sentences or [["A0.", "A1."], ["W0.", "W1.", "W2."]]
    context_texts = tuple(" ".join(s) for s in sentences)
    return ExternalQuery(
        id=qid,
        benchmark="2wiki",
        question=question,
        context=context_texts,
        gold_answer="",
        metadata={
            "context_titles":    titles,
            "context_sentences": sentences,
            "supporting_facts":  [],
            "type":              "comparison",
            "entity_ids":        "",
            "evidences":         [],
            "evidences_id":      [],
            "answer_id":         "",
            "split":             "dev",
        },
    )


# ──────────────────────────────────────────────────────────────────────


class AnchorSplitTests(unittest.TestCase):
    def test_split_returns_full_text_when_no_anchor(self):
        from eval.external.wikimulti_cited_producer import \
            _split_at_supporting_facts
        ans, sf = _split_at_supporting_facts("Just an answer.")
        self.assertEqual(ans, "Just an answer.")
        self.assertEqual(sf, "")

    def test_split_at_canonical_anchor(self):
        from eval.external.wikimulti_cited_producer import \
            _split_at_supporting_facts
        ans, sf = _split_at_supporting_facts(
            "Final answer.\nSUPPORTING_FACTS: [Alice #0]"
        )
        self.assertEqual(ans, "Final answer.")
        self.assertIn("[Alice #0]", sf)

    def test_split_tolerates_case_and_underscore(self):
        from eval.external.wikimulti_cited_producer import \
            _split_at_supporting_facts
        ans, sf = _split_at_supporting_facts(
            "Answer.\nsupporting facts: [Alice #0]"
        )
        self.assertEqual(ans, "Answer.")
        self.assertIn("[Alice #0]", sf)

    def test_split_returns_empty_on_non_string(self):
        from eval.external.wikimulti_cited_producer import \
            _split_at_supporting_facts
        ans, sf = _split_at_supporting_facts(None)        # type: ignore
        self.assertEqual((ans, sf), ("", ""))


class CitationRegexTests(unittest.TestCase):
    def test_basic_citation(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [Alice #0]",
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [["Alice", 0]])

    def test_multiple_citations(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [Alice #0], [Wonderland #2]",
            context_titles=["Alice", "Wonderland"],
            context_sentences=[["s0"], ["s0", "s1", "s2"]],
        )
        self.assertEqual(sf, [["Alice", 0], ["Wonderland", 2]])

    def test_spaces_inside_brackets(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [ Alice  #  0 ]",
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [["Alice", 0]])

    def test_multi_word_title(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [Lewis Carroll #0]",
            context_titles=["Lewis Carroll"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [["Lewis Carroll", 0]])


class ValidationTests(unittest.TestCase):
    def test_hallucinated_title_dropped(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [Ghost #0], [Alice #0]",
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [["Alice", 0]])

    def test_out_of_range_sent_id_dropped(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [Alice #99], [Alice #0]",
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [["Alice", 0]])

    def test_negative_sent_id_dropped(self):
        # Regex `\d+` rejects '-' so this is effectively no-citation.
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [Alice #-1]",
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [])

    def test_no_anchor_returns_empty_even_with_brackets(self):
        # `[Alice #0]` outside the SUPPORTING_FACTS segment is ignored
        # — citations leaking into the answer text don't pollute the SF
        # axis.
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Some answer [Alice #0] inline.",
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [])

    def test_duplicates_collapse_preserving_first_order(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [Wonderland #1], [Alice #0], "
            "[Wonderland #1]",
            context_titles=["Alice", "Wonderland"],
            context_sentences=[["s0"], ["s0", "s1"]],
        )
        self.assertEqual(sf, [["Wonderland", 1], ["Alice", 0]])

    def test_empty_sentences_for_title_drops_all_sf_for_it(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Ans.\nSUPPORTING_FACTS: [Alice #0]",
            context_titles=["Alice"],
            context_sentences=[[]],
        )
        self.assertEqual(sf, [])


class EmptyInputTests(unittest.TestCase):
    def test_empty_completion(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "",
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [])

    def test_non_string_completion(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            None,                                        # type: ignore
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [])

    def test_anchor_only_no_citations(self):
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts
        sf = parse_supporting_facts(
            "Insufficient Information.\nSUPPORTING_FACTS:",
            context_titles=["Alice"],
            context_sentences=[["s0"]],
        )
        self.assertEqual(sf, [])


class PromptBuilderTests(unittest.TestCase):
    def test_prompt_contains_question(self):
        from eval.external.wikimulti_cited_producer import \
            build_cited_prompt
        q = _query(question="Who founded Wonderland?")
        prompt = build_cited_prompt(q)
        self.assertIn("Who founded Wonderland?", prompt)

    def test_prompt_enumerates_titles_and_zero_indexed_sentences(self):
        from eval.external.wikimulti_cited_producer import \
            build_cited_prompt
        q = _query(
            titles=["Alpha", "Beta"],
            sentences=[["A0.", "A1."], ["B0."]],
        )
        prompt = build_cited_prompt(q)
        self.assertIn("Title: Alpha", prompt)
        self.assertIn("Title: Beta", prompt)
        self.assertIn("#0: A0.", prompt)
        self.assertIn("#1: A1.", prompt)
        self.assertIn("#0: B0.", prompt)

    def test_prompt_advertises_exact_supporting_facts_format(self):
        from eval.external.wikimulti_cited_producer import \
            build_cited_prompt
        q = _query()
        prompt = build_cited_prompt(q)
        self.assertIn("SUPPORTING_FACTS:", prompt)
        # The exact citation format must be in the prompt so small
        # models don't have to guess.
        self.assertIn("[<Title> #<sent_id>]", prompt)

    def test_prompt_handles_missing_metadata_gracefully(self):
        from eval.external.wikimulti_cited_producer import \
            build_cited_prompt
        from eval.external import ExternalQuery
        q = ExternalQuery(
            id="2wiki-q1", benchmark="2wiki", question="Q?",
            context=("ctx",), gold_answer="",
            metadata={},                                  # no titles/sentences
        )
        prompt = build_cited_prompt(q)
        # No crash; prompt still well-formed.
        self.assertIn("Question: Q?", prompt)
        self.assertIn("SUPPORTING_FACTS:", prompt)


class ProducerBenchRowShapeTests(unittest.TestCase):
    """Stubs the GemmaClient so the bench-row shape is exercised
    end-to-end without an LLM."""

    def test_row_carries_predicted_supporting_facts(self):
        from eval.external.wikimulti_cited_producer import \
            WikiMultiCitedProducer

        producer = WikiMultiCitedProducer()
        q = _query(question="Who founded Alice?")
        # Stub the GemmaClient with a callable inside the produce path.
        # Because the producer late-imports core.gemma_client, we
        # monkey-patch on its module object after import.
        import core.gemma_client as gc

        class _StubClient:
            def call_gemma(self, prompt, **_kw):
                # Honor the prompt format the producer published.
                return ("Alice was founded by Carroll.\n"
                        "SUPPORTING_FACTS: [Alice #1]")

        original = gc.GemmaClient
        try:
            gc.GemmaClient = _StubClient
            row = producer.produce(q)
        finally:
            gc.GemmaClient = original

        self.assertEqual(row["id"], q.id)
        self.assertEqual(row["mode"], "closed-corpus-cited")
        self.assertEqual(row["predicted_supporting_facts"],
                         [["Alice", 1]])
        # Answer segment stripped of the SUPPORTING_FACTS line.
        self.assertNotIn("SUPPORTING_FACTS", row["answer"])
        self.assertIn("Alice was founded by Carroll.", row["answer"])
        # raw_completion preserves the full LLM output for audit.
        self.assertIn("SUPPORTING_FACTS:", row["raw_completion"])

    def test_row_handles_no_citations_gracefully(self):
        from eval.external.wikimulti_cited_producer import \
            WikiMultiCitedProducer

        producer = WikiMultiCitedProducer()
        q = _query()
        import core.gemma_client as gc

        class _StubClient:
            def call_gemma(self, prompt, **_kw):
                return "Insufficient Information.\nSUPPORTING_FACTS:"

        original = gc.GemmaClient
        try:
            gc.GemmaClient = _StubClient
            row = producer.produce(q)
        finally:
            gc.GemmaClient = original

        self.assertEqual(row["predicted_supporting_facts"], [])
        self.assertEqual(row["answer"], "Insufficient Information.")


class ScorerEndToEndTests(unittest.TestCase):
    """The producer's output round-trips through `WikiMultiScorer`
    such that `support_fact_f1` is non-zero when citations match gold.
    """

    def test_support_fact_f1_round_trip(self):
        from eval.external.wikimulti_scorer import WikiMultiScorer
        from eval.external.wikimulti_cited_producer import \
            parse_supporting_facts

        q = _query()
        # Force gold supporting_facts so the axis becomes measurable
        # (without modifying loader semantics).
        q.metadata["supporting_facts"] = [["Alice", 0], ["Wonderland", 1]]

        completion = ("Some answer.\n"
                      "SUPPORTING_FACTS: [Alice #0], [Wonderland #1]")
        predicted = parse_supporting_facts(
            completion,
            context_titles=q.metadata["context_titles"],
            context_sentences=q.metadata["context_sentences"],
        )
        bench_row = {
            "id": q.id,
            "answer": "Some answer.",
            "predicted_supporting_facts": predicted,
        }
        scorer = WikiMultiScorer()
        axes = scorer.score([q], [bench_row])
        sf_axis = next(a for a in axes if a.name == "support_fact_f1")
        # Perfect match → support_fact_f1 = 1.0.
        self.assertEqual(sf_axis.score, 1.0)
        self.assertEqual(sf_axis.n_queries, 1)


if __name__ == "__main__":
    unittest.main()
