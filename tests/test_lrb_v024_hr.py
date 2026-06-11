"""LRB v0.2.4 HR axis tests — claim extractor + scorer + verifier dispatch.

NLI verifier model loading is gated on HuggingFace download. Tests
mock the verifier interface to keep CI fast + deterministic without
network.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pytest

from eval.external.lrb.claim_extractor import (
    MAX_CLAIMS_PER_ANSWER, extract_claims)
from eval.external.lrb.hr_scorer import (
    aggregate_to_axes, score_hr)
from eval.external.lrb.nli_verifier import (
    DebertaV3NliVerifier, NliLabel, NliResult, RobertaMnliVerifier, get_verifier)


# ── Claim extractor: rule-based path ────────────────────────────────


def test_empty_answer_yields_no_claims():
    assert extract_claims("") == []
    assert extract_claims("   ") == []


def test_single_simple_sentence():
    claims = extract_claims("Marcus Chen is the director of the "
                             "Department of Public Works.")
    assert len(claims) == 1
    assert claims[0].startswith("Marcus Chen")


def test_compound_sentence_split_on_and():
    claims = extract_claims(
        "Marcus Chen is the director and Lena Ortiz was his "
        "predecessor.")
    assert len(claims) == 2
    assert any("Marcus Chen" in c for c in claims)
    assert any("Lena Ortiz" in c for c in claims)


def test_compound_split_on_having():
    claims = extract_claims(
        "Marcus Chen is the director of Public Works, having "
        "replaced Lena Ortiz on week 2.")
    assert len(claims) == 2


def test_max_10_claims_cap():
    # Build 15 sentences
    answer = " ".join(f"Claim number {i} is true."
                       for i in range(1, 16))
    claims = extract_claims(answer)
    assert len(claims) == MAX_CLAIMS_PER_ANSWER


def test_dedupes_repeated_claims():
    claims = extract_claims(
        "The sky is blue. The sky is blue. The grass is green.")
    assert len(claims) == 2


def test_drops_too_short_claims():
    claims = extract_claims("Ok. Yes.")
    assert claims == []  # both filtered


def test_terminal_period_added():
    claims = extract_claims("Marcus is director")
    assert claims == ["Marcus is director."]


# ── NLI verifier dispatch (no model load) ───────────────────────────


def test_dispatch_roberta_mnli():
    v = get_verifier("roberta-mnli")
    assert isinstance(v, RobertaMnliVerifier)
    assert v.model_id == "roberta-large-mnli"


def test_dispatch_deberta_v3():
    v = get_verifier("deberta-v3-anli")
    assert isinstance(v, DebertaV3NliVerifier)
    assert "DeBERTa" in v.model_id


def test_dispatch_aliases():
    assert isinstance(get_verifier("primary"), RobertaMnliVerifier)
    assert isinstance(get_verifier("secondary"), DebertaV3NliVerifier)


def test_dispatch_invalid_raises():
    with pytest.raises(ValueError):
        get_verifier("gpt-4")


def test_label_maps_distinct():
    """Verify the two checkpoints have different label index conventions
    (RoBERTa-MNLI: 0=contradiction, DeBERTa-MNLI+FEVER+ANLI:
    0=entailment). The base verifier MUST map to canonical labels per
    its declared label_map.
    """
    r = RobertaMnliVerifier()
    d = DebertaV3NliVerifier()
    assert r.label_map[2] == NliLabel.ENTAILMENT     # RoBERTa: 2=ent
    assert d.label_map[0] == NliLabel.ENTAILMENT     # DeBERTa: 0=ent


# ── HR scorer (with mocked verifier) ────────────────────────────────


@dataclass
class MockVerifier:
    """Always returns a fixed NLI label sequence."""
    seq: List[NliLabel]
    _idx: int = 0

    def verify(self, premise: str, hypothesis: str) -> NliResult:
        label = self.seq[self._idx % len(self.seq)]
        self._idx += 1
        scores = {NliLabel.ENTAILMENT:    0.0,
                  NliLabel.NEUTRAL:       0.0,
                  NliLabel.CONTRADICTION: 0.0}
        scores[label] = 1.0
        return NliResult(
            label=label,
            score_entailment=scores[NliLabel.ENTAILMENT],
            score_neutral=scores[NliLabel.NEUTRAL],
            score_contradiction=scores[NliLabel.CONTRADICTION],
        )


def test_hr_all_entailed_is_1():
    v = MockVerifier(seq=[NliLabel.ENTAILMENT])
    queries = [{
        "query_id": "q1",
        "query": "Who?",
        "retrieved_context": "context",
        "answer": "Marcus is director. He replaced Lena.",
    }]
    r = score_hr(queries=queries, verifier=v)
    assert r.hr_mean == 1.0
    assert r.n_claims_total == 2
    assert r.n_entailed == 2


def test_hr_neutral_counts_as_negative():
    v = MockVerifier(seq=[NliLabel.NEUTRAL])
    queries = [{
        "query_id": "q1",
        "query": "Who?",
        "retrieved_context": "context",
        "answer": "Marcus is director.",
    }]
    r = score_hr(queries=queries, verifier=v)
    assert r.hr_mean == 0.0


def test_hr_contradiction_counts_as_negative():
    v = MockVerifier(seq=[NliLabel.CONTRADICTION])
    queries = [{
        "query_id": "q1",
        "query": "Who?",
        "retrieved_context": "context",
        "answer": "Marcus is director.",
    }]
    r = score_hr(queries=queries, verifier=v)
    assert r.hr_mean == 0.0


def test_hr_mixed_claims():
    v = MockVerifier(seq=[NliLabel.ENTAILMENT, NliLabel.NEUTRAL,
                           NliLabel.CONTRADICTION])
    queries = [{
        "query_id": "q1",
        "query": "Who?",
        "retrieved_context": "context",
        "answer": "Marcus is director. He started today. He is not Lena.",
    }]
    r = score_hr(queries=queries, verifier=v)
    # 3 claims, 1 entailed → HR = 1/3
    assert r.n_claims_total == 3
    assert abs(r.hr_mean - 1.0 / 3.0) < 1e-6


def test_hr_empty_answer_scores_1():
    """Per prereg: empty answer → HR=1.0 (abstention 정합)."""
    v = MockVerifier(seq=[NliLabel.ENTAILMENT])
    queries = [{
        "query_id": "q1",
        "query": "Who?",
        "retrieved_context": "context",
        "answer": "",
    }]
    r = score_hr(queries=queries, verifier=v)
    assert r.hr_mean == 1.0
    assert r.n_empty_answers == 1
    assert r.n_claims_total == 0


def test_hr_aggregate_mean_over_queries():
    v = MockVerifier(seq=[NliLabel.ENTAILMENT, NliLabel.NEUTRAL])
    queries = [
        {"query_id": "q1", "query": "Q", "retrieved_context": "c",
         "answer": "Marcus is director."},      # 1 claim, ent → HR=1
        {"query_id": "q2", "query": "Q", "retrieved_context": "c",
         "answer": "Lena is director."},        # 1 claim, neutral → HR=0
    ]
    r = score_hr(queries=queries, verifier=v)
    assert r.hr_mean == 0.5  # (1.0 + 0.0) / 2


def test_aggregate_to_axes_shape():
    v = MockVerifier(seq=[NliLabel.ENTAILMENT])
    queries = [{"query_id": "q1", "query": "Q",
                 "retrieved_context": "c",
                 "answer": "Marcus is director."}]
    r = score_hr(queries=queries, verifier=v)
    axes = aggregate_to_axes(r)
    assert "HR_mean" in axes
    assert "n_claims_total" in axes
    assert "n_entailed" in axes
    assert "nli_verifier_id" in axes
    assert axes["HR_mean"] == 1.0
    assert axes["nli_verifier_id"] == "MockVerifier"


def test_context_truncation_flag():
    """Long context (>2000 chars) is flagged for truncation."""
    v = MockVerifier(seq=[NliLabel.ENTAILMENT])
    queries = [{
        "query_id": "q1",
        "query": "Q",
        "retrieved_context": "X" * 2500,  # > 2000 chars
        "answer": "Marcus is director.",
    }]
    r = score_hr(queries=queries, verifier=v)
    assert r.context_truncated_count == 1


def test_context_no_truncation_under_threshold():
    v = MockVerifier(seq=[NliLabel.ENTAILMENT])
    queries = [{
        "query_id": "q1",
        "query": "Q",
        "retrieved_context": "short context",
        "answer": "Marcus is director.",
    }]
    r = score_hr(queries=queries, verifier=v)
    assert r.context_truncated_count == 0
