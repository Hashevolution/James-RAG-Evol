"""Cycle γ Phase C.3 — ALCE producer unit tests.

These tests pin the prompt shape and the result-row contract without
calling Ollama. The actual LLM-call path is exercised at smoke time
(operator-run).
"""
import unittest

from eval.external import ExternalQuery
from eval.external.alce_producer import (
    ALCE_INSTRUCTION_DEFAULT,
    ALCEClosedCorpusProducer,
    _format_documents,
)


def _q(question: str, context: tuple) -> ExternalQuery:
    return ExternalQuery(
        id="alce-asqa-test-1",
        benchmark="alce-asqa",
        question=question,
        context=context,
        gold_answer="anything",
        metadata={},
    )


class FormatDocumentsTests(unittest.TestCase):
    """1-based numbering with the 'Document [i]:' prefix mirrors
    ALCE's prompt convention. The scorer's citation indices are also
    1-based, so this is the contract that makes [N] → query.context[N-1]
    line up."""

    def test_single_doc_one_based(self):
        out = _format_documents(["alpha body"])
        self.assertEqual(out, "Document [1]: alpha body")

    def test_three_docs_blank_line_separator(self):
        out = _format_documents(["one", "two", "three"])
        self.assertEqual(
            out,
            "Document [1]: one\n\nDocument [2]: two\n\nDocument [3]: three",
        )

    def test_empty_list_yields_empty_string(self):
        self.assertEqual(_format_documents([]), "")


class PromptShapeTests(unittest.TestCase):
    """The prompt must (a) start with the ALCE instruction verbatim
    and (b) end with 'Answer:' so the model output begins immediately
    after the colon."""

    def setUp(self):
        self.q = _q(
            "Who founded Northbridge Labs?",
            (
                "Northbridge Labs was founded in 2019 by Elena Vasquez.",
                "Aurora is an electrolyte project at Northbridge.",
                "Helios Cells signed an MoU.",
                "Marcus Chen leads the Aurora project.",
                "The lab opened in the Harbor District.",
                "An unrelated passage about cooking.",
            ),
        )

    def test_prompt_starts_with_instruction(self):
        p = ALCEClosedCorpusProducer(n_docs=5)
        prompt = p._prompt(self.q)
        self.assertTrue(prompt.startswith(ALCE_INSTRUCTION_DEFAULT))

    def test_prompt_ends_with_answer_marker(self):
        p = ALCEClosedCorpusProducer(n_docs=5)
        prompt = p._prompt(self.q)
        self.assertTrue(prompt.rstrip().endswith("Answer:"))

    def test_prompt_includes_only_top_n_docs(self):
        # Locked at 5 by the pre-registration; the 6th passage MUST
        # NOT appear in the rendered prompt.
        p = ALCEClosedCorpusProducer(n_docs=5)
        prompt = p._prompt(self.q)
        self.assertIn("Document [1]: Northbridge Labs was founded", prompt)
        self.assertIn("Document [5]: The lab opened in the Harbor District",
                      prompt)
        self.assertNotIn("Document [6]", prompt)
        self.assertNotIn("cooking", prompt)

    def test_prompt_carries_question(self):
        p = ALCEClosedCorpusProducer(n_docs=3)
        prompt = p._prompt(self.q)
        self.assertIn("Question: Who founded Northbridge Labs?", prompt)

    def test_n_docs_must_be_positive(self):
        with self.assertRaises(ValueError):
            ALCEClosedCorpusProducer(n_docs=0)
        with self.assertRaises(ValueError):
            ALCEClosedCorpusProducer(n_docs=-1)


class ProducerNameTests(unittest.TestCase):
    """The runner emits ``producer`` field from this attribute; it must
    be stable so cross-bench tables can group by producer."""

    def test_producer_name_is_alce_closed_corpus(self):
        p = ALCEClosedCorpusProducer()
        self.assertEqual(p.name, "alce-closed-corpus")


if __name__ == "__main__":
    unittest.main()
