"""Evidence-Scope extractor (LEO proposal — L.A skeleton).

LEO (Younghu) 가 design memo
(`docs/handovers/v0.4-leo-evidence-scope-routing-track.md`, PR #512) 에서
제안한 *measured input-side* routing axis 의 추출기. 추론 루프가 이미
산출한 `loop_state` (`docs`, `graph_context`, `graph_paths`) 만 읽어
`evidence_scope ∈ [0, 1]` 스칼라 + 4-component breakdown 을 만든다.

LLM 호출 0개. 추가 검색 0개. I/O 0개. 외부 의존 0개. 순수 함수.

Phase plan (mirrors D5 lettering):
  • L.0  design memo (PR #512) — landed
  • L.A  **this PR** — extractor + JAMES_SCOPE_ROUTING flag + tests.
         flag default OFF. flag ON/OFF 모두 byte-identical to pre-L.A
         main *because no call site invokes this module yet* — L.C
         배선 전까지 module 은 constructible but 무의미.
  • L.B  D5 `router.select_backend(..., evidence_scope=...)` 인자 추가
  • L.C  `core/reasoning/pipeline.py` Loop 1 종료 직후 측정 + 합성
         backend 재선택 + `reason:route` audit payload 확장
  • L.D  closure — result doc + ROADMAP entry + memory sync

Default-off invariant: ``JAMES_SCOPE_ROUTING`` unset/0 → behavior
identical to pre-L.A main. Mirrors D1's ``JAMES_ADAPTIVE_BUDGET``
(`core.reasoning.budget.adaptive_budget_enabled`) and D5's
``JAMES_AUTO_ROUTER`` (`core.reasoning.router._auto_router_enabled`)
patterns — opt-in routing, never silent escalation.

Mode-gate (LEO open Q #3): `engine._query_impl` dispatches `chat` /
`meta` / `wiki_edit` / `self_evolve` / `coding` modes to `handle_*`
helpers *before* `run_retrieval_pipeline` runs, so evidence_scope only
ever sees the `retrieval` mode call path. No mode gate needed at the
extractor — empty inputs naturally yield scope=0.0 as a safety net.

Vocab anchor — Robin Converse's 2026-05-24 LinkedIn endorsement of
*"parameter count buys reasoning routing precision, not just capacity"*
named the line; D1 budget realized it on the task-weight axis; this
module realizes it on the evidence-scope axis. LEO's contribution is
the *measured* signal complementing the *predicted* one — see the
design memo §"Relationship to D5 (not a fork)" for the framing.
"""

from __future__ import annotations

import math
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Dict, Final, Iterator, Optional, Sequence

# ─── Flag ──────────────────────────────────────────────────────────

_FLAG_ON_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


def scope_routing_enabled() -> bool:
    """Env-flag gate. Default OFF.

    `JAMES_SCOPE_ROUTING=1` (or `true` / `yes` / `on`) activates the
    scope-based routing path *once L.C lands the call-site wiring*.
    Until then, this flag has no behavioral effect — the extractor is
    constructible but no production call site invokes it.

    Mirrors `core.reasoning.router._auto_router_enabled` and
    `core.reasoning.budget.adaptive_budget_enabled`.
    """
    return os.getenv("JAMES_SCOPE_ROUTING", "0").strip().lower() in _FLAG_ON_VALUES


# ─── Constants (mirrored from elsewhere in the codebase) ───────────
#
# Both are intentionally duplicated rather than imported to keep this
# module dependency-free at the call sites that L.C will add. A
# consolidation refactor (single source of truth) is out of scope for
# L.A and would touch `pipeline.py` + `graph_engine.py` simultaneously.

# ChromaDB relevance gate — mirrors `pipeline.py:RELEVANCE_GATE` (local
# constant inside `run_retrieval_pipeline`). Docs scoring below this
# are treated as "ChromaDB returned them but they aren't real evidence".
_RELEVANCE_THRESHOLD: Final[float] = 0.45

# Graph DFS depth ceiling — mirrors `core/graph_engine.py:MAX_DEPTH`.
# Used to normalize observed depth into [0, 1].
_GRAPH_MAX_DEPTH: Final[int] = 4

# Heuristic "wide" reference points for normalizing unbounded counts
# into [0, 1]. Tuned against STEP 7 priors; L.D bench may revisit.
_GRAPH_FANOUT_REFERENCE: Final[float] = 12.0
_GRAPH_PATHS_REFERENCE: Final[float] = 8.0

# Component weights (heuristic v1). All four kept as module constants
# so L.D STEP 7 tuning or Direction 2 regression output can swap them
# in one place without changing the API.
#
# Rationale (per design memo §"What 'evidence scope' is made of"):
#   _W_EFFECTIVE_K   0.35 — "how many books did we open" is the most
#                            direct measurement of evidence breadth
#   _W_GRAPH_REACH   0.25 — multi-hop traversal = synthesis difficulty
#   _W_DOC_SPREAD    0.20 — distinct sources = composition burden
#   _W_SCORE_ENTROPY 0.20 — flat distribution = no single chunk answers
_W_EFFECTIVE_K: Final[float] = 0.35
_W_GRAPH_REACH: Final[float] = 0.25
_W_DOC_SPREAD: Final[float] = 0.20
_W_SCORE_ENTROPY: Final[float] = 0.20


# ─── Public dataclass ──────────────────────────────────────────────


@dataclass(frozen=True)
class ScopeBreakdown:
    """Audit-friendly decomposition of `evidence_scope`.

    All five fields are in [0, 1]. `scope` is the weighted combination
    of the four components, clamped to [0, 1] to defend against future
    weight changes that don't sum to exactly 1.
    """

    effective_k: float
    score_entropy: float
    graph_reach: float
    doc_spread: float
    scope: float

    def as_audit_payload(self) -> Dict[str, float]:
        """Compact dict for the L.C `reason:route` audit row.

        Schema (5 keys, all rounded to 4 decimals):
          evidence_scope, effective_k, score_entropy, graph_reach,
          doc_spread.
        """
        return {
            "evidence_scope": round(self.scope, 4),
            "effective_k": round(self.effective_k, 4),
            "score_entropy": round(self.score_entropy, 4),
            "graph_reach": round(self.graph_reach, 4),
            "doc_spread": round(self.doc_spread, 4),
        }


# ─── Component extractors (private; tested via compute_scope) ──────


def _effective_k(docs: Sequence[Dict], top_k: int) -> float:
    """Docs with score ≥ relevance threshold, normalized to [0, 1].

    0 docs over threshold → 0.0 (narrow / no real evidence).
    `top_k` docs over threshold → 1.0 (wide).
    """
    if not docs or top_k <= 0:
        return 0.0
    above = sum(
        1 for d in docs if float(d.get("score", 0.0)) >= _RELEVANCE_THRESHOLD
    )
    return min(1.0, above / float(top_k))


def _score_entropy(docs: Sequence[Dict]) -> float:
    """Normalized Shannon entropy of doc score distribution.

    Single sharp peak (one doc dominates) → 0.0 (narrow — one chunk has
    the answer). Flat distribution (many similar scores) → ~1.0 (wide —
    evidence is scattered across documents).

    Empty / single doc → 0.0 (no distribution to measure).
    """
    scores = [max(0.0, float(d.get("score", 0.0))) for d in docs]
    positive = [s for s in scores if s > 0]
    if len(positive) < 2:
        return 0.0
    total = sum(positive)
    probs = [s / total for s in positive]
    h = -sum(p * math.log(p) for p in probs)
    h_max = math.log(len(positive))
    return h / h_max if h_max > 0 else 0.0


def _graph_reach(
    graph_context: Sequence[Dict],
    graph_paths: Sequence,
) -> float:
    """Depth × fan-out × paths, averaged into [0, 1].

    No graph activity → 0.0. Deep DFS (up to MAX_DEPTH=4) with many
    expanded entities and many reasoning paths → ~1.0.
    """
    if not graph_context:
        return 0.0
    max_depth = max(
        (int(g.get("_dfs_depth", 0)) for g in graph_context),
        default=0,
    )
    depth_norm = min(1.0, max_depth / float(_GRAPH_MAX_DEPTH))
    fanout_norm = min(1.0, len(graph_context) / _GRAPH_FANOUT_REFERENCE)
    paths_norm = min(1.0, len(graph_paths) / _GRAPH_PATHS_REFERENCE)
    return (depth_norm + fanout_norm + paths_norm) / 3.0


def _doc_spread(docs: Sequence[Dict]) -> float:
    """Distinct source documents / total docs, in [0, 1].

    All docs from one source → low (cohesive evidence).
    Each doc from a different source → 1.0 (scattered evidence,
    higher composition burden).
    """
    if not docs:
        return 0.0
    sources = set()
    for d in docs:
        s = d.get("source") or d.get("name") or d.get("path") or ""
        if s:
            sources.add(s)
    return min(1.0, len(sources) / float(len(docs)))


# ─── Public extractor ──────────────────────────────────────────────


def compute_scope(
    docs: Sequence[Dict],
    graph_context: Sequence[Dict],
    graph_paths: Sequence,
    *,
    top_k: int = 8,
) -> ScopeBreakdown:
    """Compute `evidence_scope` from retrieval + graph outputs.

    Args:
        docs: post-rerank doc list. In `core/reasoning/pipeline.py`
            this is `loop_state["docs"]`. Each dict carries at least
            `score` and a source identifier (`source` / `name` / `path`).
        graph_context: DFS-expanded entity dicts. In pipeline.py this
            is `loop_state["graph_context"]`. Each carries `_dfs_depth`.
        graph_paths: reasoning path strings. In pipeline.py this is
            `loop_state["graph_paths"]`.
        top_k: nominal retrieval top_k for `_effective_k` normalization.
            Defaults to 8, matching the orchestrator default.

    Returns:
        `ScopeBreakdown` with 4 component values + the combined scope,
        all in [0, 1].

    Properties:
        - Pure: same inputs → same output, every call. No I/O, no LLM.
        - Empty-safe: any combination of empty inputs returns a
          breakdown with all zeros. This is the natural mode-gate for
          `chat`/`self_evolve` paths that bypass retrieval (LEO open
          Q #3 — no explicit gate needed at the extractor).
        - Bounded: `scope` is clamped to [0, 1] even if weights change.

    Routing intent (L.C):
        Inserted between Loop 1 (graph expand) finish and the
        `generate_answer` call in `pipeline.py`. The router consumes
        `breakdown.scope` to decide the synth backend:
        narrow scope → small / fast backend, wide scope → large
        backend better at multi-document composition.
    """
    ek = _effective_k(docs, top_k=top_k)
    se = _score_entropy(docs)
    gr = _graph_reach(graph_context, graph_paths)
    ds = _doc_spread(docs)
    raw = (
        _W_EFFECTIVE_K * ek
        + _W_SCORE_ENTROPY * se
        + _W_GRAPH_REACH * gr
        + _W_DOC_SPREAD * ds
    )
    scope = max(0.0, min(1.0, raw))
    return ScopeBreakdown(
        effective_k=ek,
        score_entropy=se,
        graph_reach=gr,
        doc_spread=ds,
        scope=scope,
    )


# ─── L.C — ContextVar plumbing ─────────────────────────────────────


_current_scope: ContextVar[Optional[ScopeBreakdown]] = ContextVar(
    "evidence_scope_current", default=None
)


def get_current_scope() -> Optional[ScopeBreakdown]:
    """Read the ScopeBreakdown bound to the current context, if any.

    Returns None when no `scope_context(...)` is active OR when the
    binding inside the active scope_context was None (e.g. flag OFF).
    `trace_helpers.trace_synth_call` reads this to enable scope-based
    backend routing without threading kwargs through every synth-path
    signature.

    Async-safe and thread-safe — `ContextVar` semantics. Each async
    task / thread sees its own bound value.
    """
    return _current_scope.get()


@contextmanager
def scope_context(
    breakdown: Optional[ScopeBreakdown],
) -> Iterator[None]:
    """Bind a ScopeBreakdown to the current async/threading context.

    Used by `core/reasoning/pipeline.py` to expose the post-Loop-1
    scope measurement to any synth-layer LLM call inside the `with`
    block (synth, reflect, verify all flow through trace_helpers).

    Usage::

        breakdown = compute_scope(docs, graph_ctx, graph_paths) \\
            if scope_routing_enabled() else None
        with scope_context(breakdown):
            answer = generate_answer(...)

    Best-effort guarantees:
      - `None` is a valid binding — explicitly signals "no scope this
        turn" rather than leaking a stale prior turn's scope.
      - Cleanup runs even on exception (try/finally on ContextVar
        token reset), so a synth-path raise won't leak the binding
        into the next request handled by the same worker.
    """
    token = _current_scope.set(breakdown)
    try:
        yield
    finally:
        _current_scope.reset(token)


__all__ = [
    "ScopeBreakdown",
    "compute_scope",
    "get_current_scope",
    "scope_context",
    "scope_routing_enabled",
]
