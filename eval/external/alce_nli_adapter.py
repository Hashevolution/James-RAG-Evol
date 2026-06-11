"""Cycle γ D-alce — research-tier NLI adapter for ALCE citation scoring.

Wraps the v0.2.4 HR `NliVerifier` family (RoBERTa-MNLI primary, DeBERTa-v3-ANLI
secondary) as the ALCE `NLIVerifier` Protocol expected by
`eval/external/alce_scorer.py::ALCEScorer`. Lets ALCE smoke promote from
"infrastructure-only" string-containment fallback to a research-tier NLI
checkpoint without changing the scorer contract.

**Grade ladder** (per ALCE prereg §1.1 + v0.2.4 HR prereg §1.2):

  ``fallback``       — StringContainmentVerifier (NOT ALCE-grade)
  ``research-tier``  — RoBERTa-MNLI / DeBERTa-v3-ANLI (this adapter)
  ``alce-official``  — T5-XXL TRUE NLI Mixture (GPU-only, deferred)

`is_alce_grade` returns **False** for the research-tier adapter — only the
T5-XXL TRUE NLI Mixture matches ALCE's official-grade designation. The
adapter surfaces its true checkpoint via `name` so the scorer's `notes`
field documents the upgrade honestly.

Determinism: inherited from `NliVerifier` (argmax over softmax, no
sampling, lazy-load model, no per-call state mutation).
"""
from __future__ import annotations

from eval.external.lrb.nli_verifier import NliLabel, NliVerifier, get_verifier


# ──────────────────────────────────────────────────────────────────────
# Adapter
# ──────────────────────────────────────────────────────────────────────


class ResearchTierNliAdapter:
    """Wraps a v0.2.4 HR `NliVerifier` as an ALCE `NLIVerifier`.

    The HR verifier returns a 3-class `NliResult`; ALCE's scorer
    Protocol expects boolean `verify(premise, hypothesis) -> bool`.
    The adapter maps `label == ENTAILMENT` to True (strict, matching
    HR prereg §3.2).
    """

    def __init__(
        self,
        backend: NliVerifier,
        *,
        grade: str = "research-tier",
    ):
        if backend is None:
            raise ValueError("backend NliVerifier must not be None")
        if not isinstance(grade, str) or not grade:
            raise ValueError("grade must be a non-empty string")
        self._backend = backend
        self._grade = grade

    @property
    def name(self) -> str:
        # Reports the actual HF checkpoint so the scorer notes are
        # informative (e.g. "research-tier:roberta-large-mnli").
        return f"{self._grade}:{self._backend.model_id}"

    @property
    def is_alce_grade(self) -> bool:
        # ALCE-official requires T5-XXL TRUE NLI Mixture; the
        # research-tier adapter explicitly does NOT claim this even
        # though it is a strong NLI checkpoint.
        return False

    @property
    def grade(self) -> str:
        return self._grade

    @property
    def backend(self) -> NliVerifier:
        return self._backend

    def verify(self, premise: str, hypothesis: str) -> bool:
        if not isinstance(premise, str) or not isinstance(hypothesis, str):
            return False
        if not hypothesis.strip():
            # Vacuous hypothesis — mirror StringContainmentVerifier
            # behaviour (vacuous claim has nothing to falsify) so the
            # research-tier adapter does not silently flip semantics.
            return True
        if not premise.strip():
            return False
        result = self._backend.verify(premise, hypothesis)
        return NliLabel.is_entailed(result.label)


# ──────────────────────────────────────────────────────────────────────
# Public dispatch
# ──────────────────────────────────────────────────────────────────────


ALCE_ADAPTER_NAMES = ("roberta-mnli", "deberta-v3-anli")


def get_alce_adapter(name: str,
                     device: str = "cpu") -> ResearchTierNliAdapter:
    """Dispatch by canonical HR verifier name.

    Names (aligned with `eval.external.lrb.nli_verifier.get_verifier`):
      * ``"roberta-mnli"`` / ``"primary"`` → RoBERTa-MNLI adapter
      * ``"deberta-v3-anli"`` / ``"secondary"`` → DeBERTa-v3-ANLI adapter

    Raises:
      ValueError when `name` does not match a known HR verifier.
    """
    backend = get_verifier(name, device=device)
    return ResearchTierNliAdapter(backend)


__all__ = [
    "ALCE_ADAPTER_NAMES",
    "ResearchTierNliAdapter",
    "get_alce_adapter",
]
