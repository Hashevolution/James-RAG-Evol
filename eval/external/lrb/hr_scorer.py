"""LRB v0.2.4 — HR (Hallucination Resistance) scorer.

Per prereg §3:

  For each (query, retrieved_context, answer):
    claims = extract_atomic_claims(answer)
    for claim in claims:
      nli_result = nli_verifier(premise=retrieved_context, hypothesis=claim)
    hr_score = (# entailment claims) / (total claims)
  HR = mean over all queries

Per-claim scoring (strict):
  * entailment    → +1 (claim 정확)
  * neutral       → 0  (NOT positive)
  * contradiction → 0  (claim 잘못)

Empty answer → HR = 1.0 (no claim = no hallucination; abstention 정합).

Context truncation: first 512 tokens (NLI max length); per-cell flag
``context_truncated_count`` reported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Dict, List, Optional

from .claim_extractor import extract_claims
from .nli_verifier import NliLabel, NliResult, NliVerifier


@dataclass
class HrPerQueryResult:
    query_id: str
    answer: str
    claims: List[str]
    nli_results: List[NliResult]
    hr_score: float
    context_truncated: bool


@dataclass
class HrAggregateResult:
    per_query: List[HrPerQueryResult] = field(default_factory=list)
    nli_verifier_id: str = ""
    n_queries: int = 0
    n_claims_total: int = 0
    n_entailed: int = 0
    n_neutral: int = 0
    n_contradicted: int = 0
    n_empty_answers: int = 0
    context_truncated_count: int = 0
    elapsed_s: float = 0.0

    @property
    def hr_mean(self) -> float:
        if not self.per_query:
            return 0.0
        return mean(q.hr_score for q in self.per_query)


def score_hr(
    *,
    queries: List[Dict[str, Any]],
    verifier: NliVerifier,
    llm_augment_model: Optional[str] = None,
    ollama_url: str = "http://localhost:11434",
    timeout: float = 30.0,
) -> HrAggregateResult:
    """Score Hallucination Resistance across a list of queries.

    Each query dict must contain:
      query_id, query, retrieved_context (str), answer (str)
    """
    import time
    start = time.perf_counter()
    out = HrAggregateResult(
        nli_verifier_id=type(verifier).__name__)

    for q in queries:
        ans = (q.get("answer") or "").strip()
        ctx = q.get("retrieved_context") or ""
        if not ans:
            # Empty answer → HR = 1.0 (no claim, no hallucination)
            out.per_query.append(HrPerQueryResult(
                query_id=q["query_id"], answer="", claims=[],
                nli_results=[], hr_score=1.0,
                context_truncated=False))
            out.n_empty_answers += 1
            out.n_queries += 1
            continue

        claims = extract_claims(
            ans,
            llm_augment_model=llm_augment_model,
            ollama_url=ollama_url,
            timeout=timeout,
        )

        # Truncation check (approximate by char-count proxy; NLI
        # tokenizer truncates at 512 tokens which is ~2000 chars for
        # English)
        truncated = len(ctx) > 2000
        if truncated:
            out.context_truncated_count += 1

        nli_results: List[NliResult] = []
        n_entailed_q = 0
        for claim in claims:
            r = verifier.verify(premise=ctx, hypothesis=claim)
            nli_results.append(r)
            if r.label == NliLabel.ENTAILMENT:
                n_entailed_q += 1
                out.n_entailed += 1
            elif r.label == NliLabel.NEUTRAL:
                out.n_neutral += 1
            elif r.label == NliLabel.CONTRADICTION:
                out.n_contradicted += 1
            out.n_claims_total += 1

        hr_q = (n_entailed_q / len(claims)) if claims else 1.0
        out.per_query.append(HrPerQueryResult(
            query_id=q["query_id"], answer=ans, claims=claims,
            nli_results=nli_results, hr_score=hr_q,
            context_truncated=truncated,
        ))
        out.n_queries += 1

    out.elapsed_s = round(time.perf_counter() - start, 4)
    return out


def aggregate_to_axes(result: HrAggregateResult) -> Dict[str, Any]:
    """Convert HrAggregateResult into the result.json `axes` shape used
    by LRB / Track C runners."""
    return {
        "HR_mean": round(result.hr_mean, 6),
        "n_queries": result.n_queries,
        "n_claims_total": result.n_claims_total,
        "n_entailed": result.n_entailed,
        "n_neutral": result.n_neutral,
        "n_contradicted": result.n_contradicted,
        "n_empty_answers": result.n_empty_answers,
        "context_truncated_count": result.context_truncated_count,
        "nli_verifier_id": result.nli_verifier_id,
        "elapsed_s": result.elapsed_s,
    }


__all__ = ["score_hr", "HrPerQueryResult", "HrAggregateResult",
            "aggregate_to_axes"]
