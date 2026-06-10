"""Cycle γ D3 — multi-hop evidence selection.

The retrieval-arc closure (2026-06-10) found the binding lever is
synth's handling of noisy multi-hop context: the model solves the 2-hop
given clean supporting paragraphs (oracle 72%) but abstains when they
sit among distractors (all-16-docs → 12%). D1/D1b used the
sub-questions as extra *retrieval paths* (wrong layer). D3 uses them to
*select* evidence: take the top docs for each sub-question and pass only
those small, clean winners to synth — bypassing the original-query-
biased wide rerank that misses hop-2.

```
decompose → [original, q1, q2, ...]
  for each q: hybrid_search(q) → keep top-K_sel
  union + dedup the per-subquery winners → small clean context (~4-6 docs)
```

Pre-registration: docs/research/cycle-gamma-d3-evidence-selection-preregistration-2026-06-10.md

Opt-in only. ``JAMES_ENABLE_EVIDENCE_SELECT`` unset → ``evidence_select_enabled``
False and the caller takes the byte-identical normal retrieve+rerank
path. Cost = 1 decompose call + N cheap hybrid_search calls (no per-hop
LLM extract — cheaper than D1b).
"""
from __future__ import annotations

import os
from typing import Callable, List, Optional


def evidence_select_enabled() -> bool:
    """True iff ``JAMES_ENABLE_EVIDENCE_SELECT`` == "1" (per-call read)."""
    return os.environ.get("JAMES_ENABLE_EVIDENCE_SELECT") == "1"


def select_evidence(
    query: str,
    hybrid_search_fn: Callable,
    *,
    model: Optional[str] = None,
    user_role: str = "external",
    source_type: Optional[str] = "prod",
    top_k_search: int = 8,
    k_sel: int = 2,
    max_docs: int = 6,
) -> List[dict]:
    """Build a small clean doc set by taking the top ``k_sel`` docs for
    the original query plus each decomposed sub-question.

    Returns ``[]`` when decomposition yields nothing useful and the
    original query's own top docs are all that's available (the caller
    then falls back to the normal path). Never raises.

    The original query is always the first "sub-question" so a single-
    hop question degrades to "top-k_sel of the original query" — a
    smaller context than R0's rerank-5 but built the same way.
    """
    q = (query or "").strip()
    if not q:
        return []
    try:
        from core.retrieval.query_decomposer import decompose, decomp_model
        subs = decompose(q, force=True, model=model or decomp_model())
    except Exception:
        subs = []

    # Original query first, then sub-questions. If decompose returned
    # nothing, this is just the original query → fall back (return []).
    if not subs:
        return []

    queries = [q] + [s for s in subs if isinstance(s, str) and s.strip()]
    selected: List[dict] = []
    seen = set()
    for sub_q in queries:
        try:
            docs = hybrid_search_fn(
                sub_q, top_k=top_k_search,
                user_role=user_role, source_type=source_type,
            )
        except Exception:
            docs = []
        for d in (docs or [])[:k_sel]:
            src = d.get("source") or d.get("name") or ""
            if src and src in seen:
                continue
            if src:
                seen.add(src)
            selected.append(d)
            if len(selected) >= max_docs:
                return selected
    return selected


__all__ = ["evidence_select_enabled", "select_evidence"]
