"""LRB v0.2.1 cross-model retrieval wrapper.

Per prereg §2:

  3 adapter (Vanilla / Naive / JAMES) 모두 이 layer 위에 build —
  즉 모드 + 모델은 SUT 외부의 cross-cutting concern. SUT 자체 코드는
  변경 0.

This module wraps an existing LRB adapter without modifying its
retrieve_at signature. The wrapper:
  * mode="token"        — pass through to adapter.retrieve_at(q, k, ...)
  * mode="llm-grounded" — call adapter.retrieve_at(q, top_n=20, ...);
                          fetch each candidate's (title, text) via
                          adapter.get_doc(doc_id); rerank with LLM;
                          return top-k.

The wrapper enforces RAB H1 (no LLM judge at scoring time) by being
pure rerank — scoring math stays in the deterministic scorer.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from .llm_rerank import rerank


def retrieve_at_cross_model(adapter,
                            q: str,
                            k: int,
                            query_time: int,
                            valid_time: int,
                            *,
                            mode: str,
                            model: str,
                            rerank_pool: int = 20,
                            ollama_url: str = "http://localhost:11434",
                            timeout: float = 60.0) -> List[str]:
    """Cross-model retrieve wrapper.

    Args:
      adapter:      any LRB SUT adapter exposing
                      retrieve_at(q, k, query_time, valid_time)
                      + get_doc(doc_id) -> (title, text) | None
      q, k, query_time, valid_time: standard LRB retrieve_at signature
      mode:        "token" or "llm-grounded"
      model:       canonical model name (gemma4:e4b / gemma3:12b /
                   mixtral:8x7b / claude-haiku-4-5 / ...)
      rerank_pool: top-N from token-overlap to feed to LLM (default 20
                   per prereg §2)
      ollama_url, timeout: passed to llm_rerank.rerank

    Returns:
      list of top-k doc_ids.
    """
    if mode == "token":
        return adapter.retrieve_at(q, k, query_time, valid_time)

    if mode != "llm-grounded":
        raise ValueError(
            f"mode must be 'token' or 'llm-grounded', got {mode!r}")

    # 1. Token-overlap top-N from the adapter (respects validity for
    #    JAMES, naive supersede for Naive, etc.)
    pool = adapter.retrieve_at(q, rerank_pool, query_time, valid_time)
    if not pool:
        return []

    # 2. Fetch (doc_id, title, text) tuples for each candidate
    candidates: List[Tuple[str, str, str]] = []
    for doc_id in pool:
        rec = adapter.get_doc(doc_id)
        if rec is None:
            continue
        title, text = rec
        candidates.append((doc_id, title, text))

    if not candidates:
        return []

    # 3. LLM rerank
    reranked = rerank(q, candidates, model=model,
                      ollama_url=ollama_url, timeout=timeout)

    # 4. Top-k by rerank order
    return [doc_id for doc_id, _ in reranked[:k]]


__all__ = ["retrieve_at_cross_model"]
