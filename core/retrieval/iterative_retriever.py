"""Cycle γ D1b — iterative (self-ask style) retrieval.

D1 (static query decomposition) was INSUFFICIENT: the hop-2
sub-question stayed an anaphora ("Who is the spouse of *that person*?")
because decomposition splits before hop-1 is answered. D1b resolves the
pronoun by answering hop-1 from its own retrieval, then substituting the
answer into hop-2 before the 2nd retrieval round.

```
decompose → [q1, q2, ...]
  for each later hop i:
    retrieve(resolved[i-1]) → docs
    a = extract short answer to resolved[i-1] from docs
    resolved[i] = substitute anaphora in q_i with a   (else fall back to q_i)
return resolved sub-questions  →  caller adds them as extra retrieval paths
```

Pre-registration: docs/research/cycle-gamma-d1b-iterative-retrieval-preregistration-2026-06-10.md

Opt-in only. ``JAMES_ENABLE_ITER_RETRIEVAL`` unset → ``iter_retrieval_enabled``
is False and the caller takes the byte-identical no-op path. Cost is
real (one extract LLM call + one retrieval per later hop) — a default
flip is gated on a multi-axis measurement (quality vs cost), never on
this flag alone.
"""
from __future__ import annotations

import os
import re
from typing import Callable, List, Optional


def iter_retrieval_enabled() -> bool:
    """True iff ``JAMES_ENABLE_ITER_RETRIEVAL`` == "1" (per-call read)."""
    return os.environ.get("JAMES_ENABLE_ITER_RETRIEVAL") == "1"


# Anaphora tokens a static hop-2 sub-question typically carries. Ordered
# longest-first so "that person" matches before "that"/"person".
_ANAPHORA = re.compile(
    r"\b("
    r"that person|that company|that place|that individual|"
    r"that organization|that organisation|that team|that group|"
    r"this person|this company|the person|the company|"
    r"that one|that city|that country|that author|that film|"
    r"they|them|it|this|that"
    r")\b",
    re.IGNORECASE,
)

# Deliberately permissive: the goal is a short bridging entity to feed
# the next hop's retrieval, not a verified final answer. Over-abstention
# (the v1 prompt said "if not contain, UNKNOWN" and the model refused
# even when the entity was present) defeats the whole iterative step, so
# we ask for the best-supported entity and reserve UNKNOWN for genuinely
# irrelevant context. A wrong bridge only adds a noisy retrieval path;
# the original query path still runs, so the downside is bounded.
_EXTRACT_PROMPT = (
    "Read the context and answer the question with the single most "
    "relevant name, entity, place, or short phrase. Answer in as few "
    "words as possible — just the entity, no sentence. Only if the "
    "context mentions nothing relevant at all, output exactly UNKNOWN.\n\n"
    "Context:\n{ctx}\n\n"
    "Question: {q}\n"
    "Answer:"
)


def _extract_answer(
    q: str,
    docs: List[dict],
    *,
    model: str,
    timeout: int = 60,
) -> Optional[str]:
    """Extract a short answer to ``q`` from ``docs``. Returns ``None``
    on empty context / UNKNOWN / failure / over-long output (so the
    caller falls back to the un-substituted sub-question)."""
    ctx = "\n\n".join(
        (d.get("text") or d.get("paragraph_text") or "")
        for d in (docs or [])[:5]
    )
    if not ctx.strip():
        return None
    try:
        from core.gemma_client import GemmaClient
        out = GemmaClient().call_gemma(
            _EXTRACT_PROMPT.format(ctx=ctx, q=q),
            model=model,
            max_tokens=32,
            think=False,
            use_cache=False,
            timeout=timeout,
        )
    except Exception:
        return None
    a = (out or "").strip()
    if a:
        a = a.splitlines()[0].strip().strip('"').strip(".").strip()
    # Reject only a genuine refusal (starts with UNKNOWN) or empty /
    # over-long output (a bridging entity is a few words; a long answer
    # means the model wrote a sentence we can't safely substitute).
    if not a or a.lower().startswith("unknown") or len(a) > 60:
        return None
    return a


def _substitute(q_next: str, answer: str) -> str:
    """Replace the first anaphora token in ``q_next`` with ``answer``;
    if none present, append a disambiguator."""
    if _ANAPHORA.search(q_next):
        return _ANAPHORA.sub(answer, q_next, count=1)
    return f"{q_next} (regarding {answer})"


def iterative_resolve(
    subs: List[str],
    hybrid_search_fn: Callable,
    *,
    model: str,
    user_role: str = "external",
    source_type: Optional[str] = "prod",
    top_k: int = 8,
) -> List[str]:
    """Resolve later-hop anaphora in ``subs`` by answering each earlier
    hop from its own retrieval.

    Returns the resolved sub-question list (same length as ``subs``).
    ``subs[0]`` is returned unchanged; each later hop is either
    substituted (extract succeeded) or left as-is (extract returned
    None — degrades to D1 static behaviour, never worse). Never raises.
    """
    if not subs:
        return []
    resolved: List[str] = [subs[0]]
    for i in range(1, len(subs)):
        prev_q = resolved[i - 1]
        try:
            docs = hybrid_search_fn(
                prev_q, top_k=top_k,
                user_role=user_role, source_type=source_type,
            )
        except Exception:
            docs = []
        a = _extract_answer(prev_q, docs, model=model)
        resolved.append(_substitute(subs[i], a) if a else subs[i])
    return resolved


__all__ = ["iter_retrieval_enabled", "iterative_resolve"]
