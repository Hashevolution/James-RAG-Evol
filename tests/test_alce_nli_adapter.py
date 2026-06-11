"""Cycle γ D-alce — ResearchTierNliAdapter contract tests.

Pins:
  * Adapter wraps an HR `NliVerifier` and returns boolean for
    `verify(premise, hypothesis)`.
  * `is_alce_grade` is False (T5-XXL TRUE NLI is the official grade —
    research-tier adapters do NOT claim it).
  * `name` includes the backend HF checkpoint so scorer `notes`
    document the upgrade.
  * Vacuous hypothesis / empty premise edge cases mirror the
    StringContainmentVerifier fallback.
  * `get_alce_adapter` dispatches by canonical HR verifier name.

These tests use a stub backend (no transformers import) so they run
in the dependency-free CI lane.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from eval.external.lrb.nli_verifier import (NliLabel, NliResult, NliVerifier,
                                            RobertaMnliVerifier)


class _StubBackend(NliVerifier):
    """Stub NliVerifier — returns a fixed NliResult per (premise,
    hypothesis) pair without loading any HuggingFace model."""

    model_id = "stub/nli-fixture"

    def __init__(self, label: NliLabel = NliLabel.ENTAILMENT) -> None:
        super().__init__(device="cpu")
        self._fixed_label = label
        self.calls = []  # type: list[tuple[str, str]]

    def verify(self, premise: str, hypothesis: str) -> NliResult:
        self.calls.append((premise, hypothesis))
        scores = {NliLabel.ENTAILMENT: 0.0,
                  NliLabel.NEUTRAL: 0.0,
                  NliLabel.CONTRADICTION: 0.0}
        scores[self._fixed_label] = 1.0
        return NliResult(
            label=self._fixed_label,
            score_entailment=scores[NliLabel.ENTAILMENT],
            score_neutral=scores[NliLabel.NEUTRAL],
            score_contradiction=scores[NliLabel.CONTRADICTION],
        )


# ──────────────────────────────────────────────────────────────────────


class AdapterContractTests(unittest.TestCase):
    """Implements the ALCE NLIVerifier Protocol contract."""

    def test_is_alce_grade_is_false(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        adapter = ResearchTierNliAdapter(_StubBackend())
        # Research-tier explicitly does NOT claim ALCE-official-grade
        # (T5-XXL TRUE NLI Mixture is the only ALCE-grade checkpoint).
        self.assertFalse(adapter.is_alce_grade)

    def test_name_surfaces_backend_checkpoint(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        adapter = ResearchTierNliAdapter(_StubBackend())
        self.assertIn("stub/nli-fixture", adapter.name)
        self.assertIn("research-tier", adapter.name)

    def test_grade_property_default(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        adapter = ResearchTierNliAdapter(_StubBackend())
        self.assertEqual(adapter.grade, "research-tier")

    def test_grade_property_override(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        adapter = ResearchTierNliAdapter(_StubBackend(), grade="experimental")
        self.assertEqual(adapter.grade, "experimental")
        self.assertIn("experimental:", adapter.name)

    def test_backend_property_returns_input(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        backend = _StubBackend()
        adapter = ResearchTierNliAdapter(backend)
        self.assertIs(adapter.backend, backend)


class VerifyBooleanMappingTests(unittest.TestCase):
    """Maps backend NliResult.label → boolean per HR prereg §3.2
    (entailment only; neutral and contradiction both False)."""

    def test_entailment_maps_to_true(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        adapter = ResearchTierNliAdapter(_StubBackend(NliLabel.ENTAILMENT))
        self.assertTrue(adapter.verify("p", "h"))

    def test_neutral_maps_to_false(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        adapter = ResearchTierNliAdapter(_StubBackend(NliLabel.NEUTRAL))
        self.assertFalse(adapter.verify("p", "h"))

    def test_contradiction_maps_to_false(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        adapter = ResearchTierNliAdapter(_StubBackend(NliLabel.CONTRADICTION))
        self.assertFalse(adapter.verify("p", "h"))

    def test_backend_called_with_unstripped_inputs(self):
        # The adapter delegates premise/hypothesis verbatim — the
        # backend gets the raw strings, not adapter-mutated text.
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        backend = _StubBackend()
        adapter = ResearchTierNliAdapter(backend)
        adapter.verify("Premise text.", "Hypothesis text.")
        self.assertEqual(backend.calls,
                         [("Premise text.", "Hypothesis text.")])


class EdgeCaseTests(unittest.TestCase):
    """Vacuous / empty edge cases mirror StringContainmentVerifier
    so the research-tier upgrade does not silently change semantics."""

    def test_non_string_returns_false(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        adapter = ResearchTierNliAdapter(_StubBackend())
        self.assertFalse(adapter.verify(123, "h"))           # type: ignore[arg-type]
        self.assertFalse(adapter.verify("p", None))          # type: ignore[arg-type]

    def test_vacuous_hypothesis_returns_true_without_backend_call(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        backend = _StubBackend(NliLabel.CONTRADICTION)
        adapter = ResearchTierNliAdapter(backend)
        # Vacuous claim has no content to falsify — adapter returns
        # True without invoking the (slow) backend NLI model.
        self.assertTrue(adapter.verify("p", "   "))
        self.assertTrue(adapter.verify("p", ""))
        self.assertEqual(backend.calls, [])

    def test_empty_premise_returns_false_without_backend_call(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        backend = _StubBackend(NliLabel.ENTAILMENT)
        adapter = ResearchTierNliAdapter(backend)
        # Empty premise cannot entail anything.
        self.assertFalse(adapter.verify("", "h"))
        self.assertFalse(adapter.verify("   ", "h"))
        self.assertEqual(backend.calls, [])

    def test_none_backend_raises(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        with self.assertRaises(ValueError):
            ResearchTierNliAdapter(None)             # type: ignore[arg-type]

    def test_invalid_grade_raises(self):
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        with self.assertRaises(ValueError):
            ResearchTierNliAdapter(_StubBackend(), grade="")
        with self.assertRaises(ValueError):
            ResearchTierNliAdapter(_StubBackend(), grade=None)  # type: ignore[arg-type]


class DispatchTests(unittest.TestCase):
    """`get_alce_adapter` resolves canonical HR verifier names."""

    def test_dispatch_roberta_returns_research_tier_wrapping_roberta(self):
        from eval.external.alce_nli_adapter import get_alce_adapter
        adapter = get_alce_adapter("roberta-mnli")
        self.assertIsInstance(adapter.backend, RobertaMnliVerifier)
        self.assertFalse(adapter.is_alce_grade)
        self.assertIn("roberta-large-mnli", adapter.name)

    def test_dispatch_deberta(self):
        from eval.external.alce_nli_adapter import get_alce_adapter
        from eval.external.lrb.nli_verifier import DebertaV3NliVerifier
        adapter = get_alce_adapter("deberta-v3-anli")
        self.assertIsInstance(adapter.backend, DebertaV3NliVerifier)
        self.assertFalse(adapter.is_alce_grade)

    def test_dispatch_aliases(self):
        # Inherits HR's `get_verifier` aliases.
        from eval.external.alce_nli_adapter import get_alce_adapter
        a1 = get_alce_adapter("primary")
        a2 = get_alce_adapter("secondary")
        self.assertIn("roberta-large-mnli", a1.name)
        self.assertIn("DeBERTa-v3-large", a2.name)

    def test_dispatch_unknown_name_raises(self):
        from eval.external.alce_nli_adapter import get_alce_adapter
        with self.assertRaises(ValueError):
            get_alce_adapter("not-a-real-verifier")


class ScorerIntegrationTests(unittest.TestCase):
    """Smoke test: the adapter satisfies the ALCEScorer constructor
    contract and round-trips through one citation cycle."""

    def test_adapter_is_accepted_by_scorer(self):
        from eval.external import ExternalQuery
        from eval.external.alce_nli_adapter import ResearchTierNliAdapter
        from eval.external.alce_scorer import ALCEScorer

        adapter = ResearchTierNliAdapter(_StubBackend(NliLabel.ENTAILMENT))
        scorer = ALCEScorer(variant="asqa", verifier=adapter)
        # The scorer holds the adapter and reports its name in notes.
        self.assertIs(scorer.verifier, adapter)

        q = ExternalQuery(
            id="alce-asqa-1",
            benchmark="alce-asqa",
            question="Q?",
            context=("Premise A about topic.", "Other passage."),
            gold_answer="ignored",
            metadata={"variant": "asqa", "retriever": "test"},
        )
        row = {"id": "alce-asqa-1",
               "answer": "Claim about topic [1]."}

        axes = scorer.score([q], [row])
        # Both citation axes should report with the research-tier name
        # in notes so the result.json documents the upgrade honestly.
        for axis in axes:
            self.assertIn("research-tier", axis.notes)
            self.assertIn("is_alce_grade=False", axis.notes)


if __name__ == "__main__":
    unittest.main()
