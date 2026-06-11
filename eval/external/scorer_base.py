"""Cycle γ Phase A.4.0 — abstract ``ExternalScorer`` + unified
``ScoreAxis`` dataclass.

Every per-benchmark scorer (RGB / ALCE / MuSiQue / 2Wiki) inherits
:class:`ExternalScorer` and emits one or more :class:`ScoreAxis`
records. The unified runner (Phase A.5) collects these axes into a
single cross-bench table without per-bench branching.

Design philosophy
-----------------

* **One scorer per benchmark**: each scorer implements that
  benchmark's *official* scoring formula (or a documented faithful
  approximation). The scorer reads :class:`eval.external.base.
  ExternalQuery` records side-by-side with the model's bench-output
  rows and emits aggregate scores.

* **Pluggable verifier backends**: the ALCE scorer (A.4.4) needs an
  NLI model to verify citation entailment. The base does NOT pick
  one — it exposes the *interface* and lets each scorer accept a
  callable. The default is a documented string-matching fallback
  (with a clearly-flagged ``score_axis.notes`` warning); operators
  who care about ALCE-grade precision pass a HuggingFace NLI
  callable. This keeps the runtime dependency optional.

* **Honest framing**: every axis carries a ``notes`` field. When a
  scorer falls back to an approximation (e.g. ALCE without NLI), the
  notes record that and the cycle γ report must surface it. The
  self-eval trap rule (memory ``feedback_self_evaluation_trap``)
  applies: a JAMES-internal approximation of an external metric is
  worth less than the metric itself, and we must say so.

API surface
-----------

  * :class:`ScoreAxis` — frozen dataclass with name / score /
    n_queries / per_query / notes.
  * :class:`ExternalScorer` — abstract base. Subclasses override
    ``benchmark_id`` and ``score``.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


# ─── ScoreAxis (frozen) ────────────────────────────────────────────


@dataclass(frozen=True)
class ScoreAxis:
    """One scored axis for one benchmark.

    Attributes:
        name: Stable short identifier (e.g. ``"em"``, ``"f1"``,
            ``"citation_precision"``, ``"negative_rejection_f1"``).
            Used as a column key in the cross-bench table.
        score: Aggregate score over all queries. Range and meaning
            are axis-specific (F1 ∈ [0, 1]; EM ∈ {0, 1} per query
            averaged ∈ [0, 1]; etc.).
        n_queries: How many queries contributed to the aggregate.
            Zero is a legitimate value (no applicable rows in the
            input) and indicates "axis not measured here" rather
            than "score is zero".
        per_query: Optional per-query breakdown. Loaders that need
            sub-aggregates (e.g. MuSiQue F1 by hop count) recompute
            from this field; the runner persists it to the bench
            JSON so downstream analysis is possible.
        notes: Free-text honest-framing field. Approximation
            warnings, missing-backend disclaimers, fixture caveats.
            Empty string means "scored per the official formula
            with no caveats".
    """
    name:       str
    score:      float
    n_queries:  int
    per_query:  Dict[str, float] = field(default_factory=dict)
    notes:      str = ""


# ─── Abstract scorer base ──────────────────────────────────────────


class ExternalScorer(abc.ABC):
    """Abstract base every Phase-A.4.1+ scorer inherits from.

    A scorer subclass is responsible for:

    1. Declaring its :attr:`benchmark_id` so the runner can route
       bench rows to the right scorer.
    2. Implementing :meth:`score` against an iterable of
       :class:`eval.external.base.ExternalQuery` records (fixture)
       and a list of bench rows (model output rows in the JAMES bench
       JSON shape).

    The base does NOT prescribe answer-normalisation, NLI back-ends,
    or aggregation strategies — those are per-benchmark concerns.
    The base only pins the minimum interface every scorer must
    satisfy so the runner stays benchmark-agnostic.
    """

    # ── Subclass contract ──────────────────────────────────────────

    @property
    @abc.abstractmethod
    def benchmark_id(self) -> str:
        """Short benchmark id (e.g. ``"rgb-en"``, ``"alce-asqa"``,
        ``"musique-ans"``, ``"2wiki"``). Must match the
        ``benchmark`` field on the :class:`ExternalQuery` records
        the scorer consumes (runtime check at :meth:`score` enforces
        it)."""

    @abc.abstractmethod
    def score(
        self,
        queries: Iterable["Any"],
        bench_rows: List[Dict[str, Any]],
    ) -> List[ScoreAxis]:
        """Compute every axis the benchmark publishes.

        Args:
            queries: Iterable of :class:`eval.external.base.
                ExternalQuery`. Iterated once.
            bench_rows: List of model-output rows in the JAMES bench
                JSON shape — typically ``[{"id": ..., "answer": ...,
                ...}]``. The runner pairs each query with the row
                whose ``id`` matches ``query.id``.

        Returns:
            A list of :class:`ScoreAxis`. Empty list is legitimate
            (no rows / no applicable axes for this input).
        """

    # ── Shared helpers ─────────────────────────────────────────────

    def index_rows_by_id(
        self,
        bench_rows: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Return ``{row_id: row}`` for fast pairing with queries.

        Rows without an ``id`` field are skipped silently — the
        scorer's per-query loop simply will not find a match for
        the corresponding query, which surfaces as a non-aggregate
        count drop.
        """
        out: Dict[str, Dict[str, Any]] = {}
        for r in bench_rows:
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            if isinstance(rid, str) and rid:
                out[rid] = r
        return out

    def validate_queries(
        self,
        queries: List["Any"],
    ) -> None:
        """Cross-check that every query has the expected
        ``benchmark`` field.

        Subclasses call this from :meth:`score` so a misrouted query
        (e.g. an ALCE row fed to the MuSiQue scorer) surfaces as a
        clean ValueError instead of producing a meaningless score.

        Raises:
            ValueError: when any query's ``benchmark`` does not
                match this scorer's :attr:`benchmark_id`.
        """
        bid = self.benchmark_id
        for q in queries:
            qb = getattr(q, "benchmark", None)
            if qb != bid:
                raise ValueError(
                    f"query benchmark mismatch: scorer is {bid!r} "
                    f"but query has benchmark={qb!r}"
                )


__all__ = [
    "ExternalScorer",
    "ScoreAxis",
]
