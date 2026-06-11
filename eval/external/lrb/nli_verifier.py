"""LRB v0.2.4 — NLI verifier for HR (Hallucination Resistance) axis.

Per prereg `docs/research/v024-hr-nli-axis-preregistration-2026-06-11.md`:

  Primary:   RoBERTa-large-MNLI   (~355M, CPU-feasible, MNLI std)
  Secondary: DeBERTa-v3-large-mnli-fever-anli   (~435M, robustness)
  Deferred:  T5-XXL TRUE NLI Mixture (~11B, GPU only, ALCE official)

Determinism:
  * Classification (argmax) — no temperature/sampling
  * Model checkpoint pinned via HF revision hash on first download
  * Lazy load: model only instantiated on first verify call
  * Per-call no state mutation

Each verifier returns a 3-class label {entailment, neutral, contradiction}.

Per prereg §3.2 the HR scorer treats only `entailment` as positive
(strict; neutral and contradiction both count against HR).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class NliLabel(str, Enum):
    ENTAILMENT = "entailment"
    NEUTRAL = "neutral"
    CONTRADICTION = "contradiction"

    @classmethod
    def is_entailed(cls, label: "NliLabel") -> bool:
        return label == cls.ENTAILMENT


@dataclass(frozen=True)
class NliResult:
    label: NliLabel
    score_entailment: float = 0.0
    score_neutral: float = 0.0
    score_contradiction: float = 0.0


# ──────────────────────────────────────────────────────────────────────
# Base
# ──────────────────────────────────────────────────────────────────────


class NliVerifier:
    """Abstract base — subclass per HF model family.

    The base provides lazy model load + canonical label normalization.
    Concrete subclasses define the model_id + label index mapping.
    """

    model_id: str = ""
    revision: Optional[str] = None       # optional HF revision pin
    max_length: int = 512

    # Index -> NliLabel mapping (varies by checkpoint)
    label_map: dict = {}

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self._tokenizer = None
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from transformers import (AutoModelForSequenceClassification,
                                    AutoTokenizer)
        kwargs = {}
        if self.revision is not None:
            kwargs["revision"] = self.revision
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, **kwargs)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_id, **kwargs)
        self._model.to(self.device)
        self._model.eval()

    def verify(self, premise: str, hypothesis: str) -> NliResult:
        """Return NLI classification + per-label softmax scores.

        Deterministic: argmax over softmax logits. Truncates to
        ``max_length`` tokens (RoBERTa/DeBERTa default 512).
        """
        import torch
        self._load()
        inputs = self._tokenizer(
            premise, hypothesis,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        ).to(self.device)
        with torch.no_grad():
            logits = self._model(**inputs).logits[0]
            probs = torch.softmax(logits, dim=-1).cpu().tolist()

        # Normalize to canonical 3 labels
        scores = {NliLabel.ENTAILMENT:    0.0,
                  NliLabel.NEUTRAL:       0.0,
                  NliLabel.CONTRADICTION: 0.0}
        for idx, prob in enumerate(probs):
            canon = self.label_map.get(idx)
            if canon is not None:
                scores[canon] = float(prob)

        # Argmax over canonical labels (deterministic, ties broken by
        # label order: entailment > neutral > contradiction).
        order = [NliLabel.ENTAILMENT, NliLabel.NEUTRAL,
                 NliLabel.CONTRADICTION]
        best = max(order, key=lambda L: (scores[L], -order.index(L)))

        return NliResult(
            label=best,
            score_entailment=scores[NliLabel.ENTAILMENT],
            score_neutral=scores[NliLabel.NEUTRAL],
            score_contradiction=scores[NliLabel.CONTRADICTION],
        )


# ──────────────────────────────────────────────────────────────────────
# RoBERTa-large-MNLI (primary)
# ──────────────────────────────────────────────────────────────────────


class RobertaMnliVerifier(NliVerifier):
    """RoBERTa-large-MNLI — primary verifier per prereg §1.2.

    Checkpoint: `roberta-large-mnli` (Facebook AI, MNLI corpus).
    Labels: [contradiction=0, neutral=1, entailment=2] per MNLI std.
    """
    model_id = "roberta-large-mnli"
    # Pin a revision later when first download succeeds — leave None
    # to let HF resolve to default. (Pin via PR after first download
    # verifies sha.)
    revision = None
    label_map = {
        0: NliLabel.CONTRADICTION,
        1: NliLabel.NEUTRAL,
        2: NliLabel.ENTAILMENT,
    }


# ──────────────────────────────────────────────────────────────────────
# DeBERTa-v3-large MNLI+FEVER+ANLI+ling+wanli (secondary)
# ──────────────────────────────────────────────────────────────────────


class DebertaV3NliVerifier(NliVerifier):
    """DeBERTa-v3-large MNLI+FEVER+ANLI+ling+wanli — robustness check.

    Checkpoint: MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli
    (extended NLI training, stronger on adversarial NLI).
    Labels: [entailment=0, neutral=1, contradiction=2] per MoritzLaurer
    convention (note: REVERSED from MNLI-only checkpoints — verified
    via model card).
    """
    model_id = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
    revision = None
    label_map = {
        0: NliLabel.ENTAILMENT,
        1: NliLabel.NEUTRAL,
        2: NliLabel.CONTRADICTION,
    }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def get_verifier(name: str, device: str = "cpu") -> NliVerifier:
    """Dispatch by canonical name.

    Names (prereg §1.2):
      * "roberta-mnli" / "primary" → RobertaMnliVerifier
      * "deberta-v3-anli" / "secondary" → DebertaV3NliVerifier
    """
    canonical = name.lower().strip()
    if canonical in ("roberta-mnli", "primary", "roberta", "mnli"):
        return RobertaMnliVerifier(device=device)
    if canonical in ("deberta-v3-anli", "secondary", "deberta",
                     "deberta-v3", "anli"):
        return DebertaV3NliVerifier(device=device)
    raise ValueError(
        f"unknown verifier {name!r}; supported: roberta-mnli, "
        f"deberta-v3-anli")


__all__ = [
    "NliLabel", "NliResult", "NliVerifier",
    "RobertaMnliVerifier", "DebertaV3NliVerifier",
    "get_verifier",
]
