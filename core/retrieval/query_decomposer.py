"""Cycle γ D1 — multi-hop query decomposition.

Phase C.2 proved single-shot dense retrieval misses the 2nd hop of
multi-hop questions (the model solves MuSiQue 2-hop given the gold
supporting paragraphs — oracle gold-in-answer 72% — but JAMES R0
retrieval surfaces them only 8% of the time). D1 decomposes a
multi-hop question into ordered sub-questions and feeds each as an
extra retrieval path, so the hop-2 sub-question ("Who is the spouse of
Steve Hillage?") surfaces what the original query ("Who is the spouse
of the Green performer?") cannot.

Pre-registration: docs/research/cycle-gamma-d1-query-decomposition-preregistration-2026-06-10.md

Opt-in only. ``JAMES_ENABLE_QUERY_DECOMP`` unset / not "1" → ``decompose``
returns ``[]`` and the retrieval query set is byte-identical to today.
Default OFF is deliberate (mother-platform principle 3: specialised
behaviour is an option layer; a default flip is gated on a later
multi-axis cost measurement, not on this single benchmark).

Model selection: ``JAMES_DECOMP_MODEL`` → ``JAMES_LLM_MODEL`` →
``gemma4:e4b``. The measurement harness sets ``JAMES_DECOMP_MODEL`` so
the decomposer uses the same model as synth.
"""
from __future__ import annotations

import os
import re
from typing import List


def query_decomp_enabled() -> bool:
    """True iff ``JAMES_ENABLE_QUERY_DECOMP`` == "1". Read per-call so a
    runtime toggle takes effect immediately (mirrors the cognitive
    feature-flag convention)."""
    return os.environ.get("JAMES_ENABLE_QUERY_DECOMP") == "1"


def _decomp_model() -> str:
    return (os.environ.get("JAMES_DECOMP_MODEL")
            or os.environ.get("JAMES_LLM_MODEL")
            or "gemma4:e4b")


_PROMPT = (
    "Break the following question into the minimal ordered sub-questions "
    "needed to answer it step by step. Output one sub-question per line, "
    "no numbering, no explanation. If it is already a single-hop "
    "question, output it unchanged.\n\n"
    "Question: {q}\n"
    "Sub-questions:"
)

# Strip leading list markers the model sometimes emits despite the
# instruction ("1. ", "1) ", "- ", "* ").
_LEADING_MARKER = re.compile(r"^\s*(?:\d+[.)]\s*|[-*]\s*)")


def decompose(
    query: str,
    *,
    model: str | None = None,
    max_sub: int = 4,
    timeout: int = 60,
) -> List[str]:
    """Return ordered sub-questions for ``query``, or ``[]``.

    ``[]`` is returned (no-op, byte-identical retrieval) when:
      - the flag is off,
      - the query is empty,
      - the LLM call fails,
      - the model echoes the question unchanged (single-hop),
      - the output is empty/garbage.

    Never raises — decomposition must not block retrieval.
    """
    if not query_decomp_enabled():
        return []
    q = (query or "").strip()
    if not q:
        return []
    try:
        from core.gemma_client import GemmaClient
        client = GemmaClient()
        out = client.call_gemma(
            _PROMPT.format(q=q),
            model=model or _decomp_model(),
            max_tokens=256,
            think=False,
            use_cache=False,
            timeout=timeout,
        )
    except Exception:
        return []

    subs: List[str] = []
    seen = {q.lower()}
    for line in (out or "").splitlines():
        line = _LEADING_MARKER.sub("", line).strip()
        if not line or len(line) < 6:
            continue
        low = line.lower()
        if low in seen:
            continue
        seen.add(low)
        subs.append(line)
        if len(subs) >= max_sub:
            break
    return subs


__all__ = ["decompose", "query_decomp_enabled"]
