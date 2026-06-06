"""Cycle γ Phase A.0 — abstract ``ExternalBenchFixture`` + unified
``ExternalQuery`` schema.

Every external benchmark loader (RGB, ALCE, MuSiQue, 2WikiMultiHopQA)
implements :class:`ExternalBenchFixture` and emits
:class:`ExternalQuery` records. The unified schema lets one runner
(Phase A.5) drive JAMES across all four benchmarks without per-bench
branching in the answer path — the bench-specific scoring lives in
the per-bench :class:`ExternalScorer` (Phase A.4).

Schema design notes
-------------------

The query record is a frozen dataclass so loaders can cache it
without worrying about downstream mutation. Bench-specific fields
that don't map onto the unified columns are preserved under
``metadata`` verbatim, so the scorer can still see them.

The schema is deliberately small. We do NOT pre-emptively add fields
for "answer aliases" / "support fact ids" / "citation labels" /
"abstention truth" — those land at the per-loader PRs (A.1 - A.3) so
each addition is justified by an actual benchmark requirement. The
abstract base stays tiny; loaders are where the real per-bench shape
lives.

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
each loader pulls the original published fixture rows — no
JAMES-authored prompts, no JAMES-curated subset, no quietly modified
gold labels. The point of cycle γ is external evidence; bending the
fixture invalidates it.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─── Unified query schema (frozen) ─────────────────────────────────


@dataclass(frozen=True)
class ExternalQuery:
    """One question from an external benchmark, in the unified shape
    the cycle γ runner consumes.

    Attributes:
        id: Benchmark-namespaced identifier (e.g. ``"rgb-0001"``,
            ``"alce-asqa-train-42"``). Stable across runs; the per-
            benchmark loader chooses the format so downstream code
            can grep for "rgb-" / "alce-" / "musique-" / "2wiki-".
        benchmark: Short benchmark id — one of ``"rgb"``,
            ``"alce-asqa"``, ``"alce-qampari"``, ``"alce-eli5"``,
            ``"musique"``, ``"2wiki"``. Stable per-loader contract.
        question: The natural-language question text as published in
            the original fixture. NOT rewritten by JAMES.
        context: Supporting passages the benchmark expects the model
            to ground its answer on (Wikipedia paragraphs, news
            articles, …). Empty tuple if the benchmark is
            closed-book.
        gold_answer: The benchmark's primary answer string. For
            yes/no benchmarks (RGB negative rejection) this is
            ``"Yes"`` / ``"No"`` / ``"insufficient"``; for
            entity-extraction benchmarks (MuSiQue / 2Wiki) it's the
            canonical entity name; for citation benchmarks (ALCE)
            it's a long-form answer.
        metadata: Bench-specific fields preserved verbatim from the
            source row. Loaders MUST round-trip the fixture row
            through here so scorers have everything they need
            (alias lists, support-fact ids, abstention truth,
            citation spans, etc.). Treat as opaque dict-of-strings
            for downstream code.
    """
    id:          str
    benchmark:   str
    question:    str
    context:     Tuple[str, ...]
    gold_answer: str
    metadata:    Dict[str, Any] = field(default_factory=dict)

    def to_bench_row(self) -> Dict[str, Any]:
        """Project to the dict shape the JAMES bench JSON uses
        elsewhere — so the existing scoring helpers (``score_paper_
        aligned_accuracy``, ``score_path_coverage``) can still read
        the row alongside the per-bench scorers.

        The cycle γ scorers also use this projection so behaviour
        across benchmarks stays uniform: every scorer reads a dict,
        not a dataclass.
        """
        return {
            "id":         self.id,
            "benchmark":  self.benchmark,
            "question":   self.question,
            "text":       self.question,
            "context":    list(self.context),
            "gold":       self.gold_answer,
            "metadata":   dict(self.metadata),
        }


# ─── Abstract benchmark fixture (per-loader contract) ───────────────


class ExternalBenchFixture(abc.ABC):
    """Abstract base every Phase-A.1+ loader inherits from.

    A loader subclass is responsible for:

    1. Pulling the original published fixture (HuggingFace ``datasets``,
       raw HTTP, or a local cache directory — the loader chooses).
    2. Yielding :class:`ExternalQuery` records via :meth:`iter_queries`.
    3. Reporting its benchmark id via :attr:`benchmark_id` for the
       unified runner's per-bench dispatch.

    The base does NOT prescribe downloading, caching, or batching —
    those are loader-specific concerns. The base only pins the
    minimum interface every loader must satisfy so the runner stays
    benchmark-agnostic.
    """

    # ── Subclass contract ──────────────────────────────────────────

    @property
    @abc.abstractmethod
    def benchmark_id(self) -> str:
        """Short benchmark id (e.g. ``"rgb"``, ``"alce-asqa"``).
        Must match the ``benchmark`` field on the queries this loader
        yields — runtime check at :meth:`iter_queries` enforces it.
        """

    @abc.abstractmethod
    def iter_queries(
        self,
        *,
        split: str = "dev",
        n_samples: Optional[int] = None,
    ) -> "List[ExternalQuery]":
        """Yield the fixture's queries.

        Args:
            split: Benchmark split id (``"train"`` / ``"dev"`` /
                ``"test"``). Each loader decides which splits it
                supports and raises ``ValueError`` for an unknown
                split.
            n_samples: Optional cap. ``None`` returns the whole split
                (useful for full measurement runs); a positive integer
                returns the first ``n_samples`` rows (useful for the
                Phase B smoke + cost-validation runs the design memo
                §6 recommends).
        """

    # ── Shared helpers (loaders inherit these unchanged) ───────────

    def take_sample(
        self,
        queries: "List[ExternalQuery]",
        n_samples: Optional[int],
    ) -> "List[ExternalQuery]":
        """Slice the front of a query list according to ``n_samples``.

        Loaders call this from :meth:`iter_queries` so the
        ``None`` / positive-int semantics stay uniform across
        benchmarks. Centralising it here also means the test for
        n_samples semantics lives in one place (Phase A.0 tests),
        not duplicated per loader.
        """
        if n_samples is None:
            return list(queries)
        if not isinstance(n_samples, int) or n_samples < 0:
            raise ValueError(
                f"n_samples must be None or a non-negative int; got "
                f"{n_samples!r}"
            )
        return list(queries[:n_samples])

    def validate_queries(
        self,
        queries: "List[ExternalQuery]",
    ) -> None:
        """Cross-check the yielded queries against the loader's
        :attr:`benchmark_id` and the unified-schema invariants.

        Loaders SHOULD call this before returning from
        :meth:`iter_queries` — it catches misconfigured fixture rows
        early (loader emits ``"rgb-001"`` but ``benchmark`` field
        says ``"musique"``, etc.).

        Raises:
            ValueError: when a query's ``benchmark`` does not match
                ``self.benchmark_id``, or when an id is empty / a
                duplicate within the batch.
        """
        seen_ids: set = set()
        for q in queries:
            if q.benchmark != self.benchmark_id:
                raise ValueError(
                    f"query {q.id!r} has benchmark={q.benchmark!r} "
                    f"but this loader's benchmark_id is "
                    f"{self.benchmark_id!r}"
                )
            if not q.id:
                raise ValueError("empty query id")
            if q.id in seen_ids:
                raise ValueError(f"duplicate query id: {q.id!r}")
            seen_ids.add(q.id)


__all__ = [
    "ExternalBenchFixture",
    "ExternalQuery",
]
