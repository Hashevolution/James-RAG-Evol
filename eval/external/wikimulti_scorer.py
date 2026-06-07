"""Cycle γ Phase A.4.3 — 2WikiMultiHopQA scorer.

Four axes, faithful to Ho et al. 2020's official evaluation:

* ``em`` / ``f1`` — SQuAD-normalised answer match. Reuses the
  exact helpers the MuSiQue scorer uses (``_normalize_answer`` /
  ``_f1`` / ``_max_em`` / ``_max_f1``) so the two multi-hop
  benchmarks share one normalisation pipeline. The bench's
  ``answer_aliases`` field is empty on 2Wiki — alias lifting is
  still wired in case a future release adds it.

* ``support_fact_f1`` — F1 of the predicted vs gold
  ``[title, sent_id]`` set. 2Wiki's official scorer reports
  precision / recall / F1 over this set; the cycle γ table needs
  one summary number so we expose F1 with the per-row breakdown
  under ``per_query`` (id → sf_f1).

* ``f1_by_type`` — per-question-type token-F1 averages
  (``comparison`` / ``inference`` / ``compositional`` /
  ``bridge-comparison``) recorded as ``per_query``. The aggregate
  ``score`` on this axis is the mean of the per-type means, so a
  table reader sees both the headline and the breakdown.

The supporting-fact axis is only emitted when at least one bench
row carries a ``predicted_supporting_facts`` (or alias) list — the
runner in Phase A.5 will translate JAMES citation outputs into
``[title, sent_id]`` pairs. Until then the axis surfaces with
``n_queries=0`` and a "not measured" note rather than silently
scoring 0.

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
the helpers reused from MuSiQue are SQuAD v1.1 verbatim, not
JAMES-internal inventions. The 4 question types come straight
from the published fixture.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from eval.external import ScoreAxis
from eval.external.scorer_base import ExternalScorer
from eval.external.wikimulti_loader import WIKIMULTI_TYPES
# Private helpers reused — SQuAD v1.1 normalisation is the same
# across multi-hop QA benches. Keeping the helpers in one place
# (musique_scorer) avoids drift; a future refactor may pull them
# into eval/external/_squad_norm.py.
from eval.external.musique_scorer import (
    _f1 as _squad_f1,
    _max_em,
    _max_f1,
    _resolve_model_answer,
)


# ─── Supporting-facts helpers ──────────────────────────────────────


def _normalize_sf_pair(item: Any) -> Optional[Tuple[str, int]]:
    """Coerce a single ``[title, sent_id]`` entry to a hashable
    ``(str, int)`` tuple.

    The fixture emits lists; the runner may also emit tuples. Both
    are accepted. Returns ``None`` on malformed input so the caller
    can silently drop one bad pair without losing the rest.
    """
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        title, sid = item[0], item[1]
        # Accept string ints from upstream serialisers.
        if isinstance(sid, str) and sid.strip().lstrip("-").isdigit():
            sid = int(sid)
        if isinstance(title, str) and isinstance(sid, int):
            return (title, sid)
    return None


def _normalize_sf_list(items: Any) -> Set[Tuple[str, int]]:
    out: Set[Tuple[str, int]] = set()
    if not isinstance(items, list):
        return out
    for it in items:
        norm = _normalize_sf_pair(it)
        if norm is not None:
            out.add(norm)
    return out


def _extract_predicted_supporting_facts(
    row: Dict[str, Any],
) -> Optional[Set[Tuple[str, int]]]:
    """Pull the predicted supporting-facts set out of a bench row.

    Accepted keys (priority):

      * ``predicted_supporting_facts``
      * ``supporting_facts`` (rare — model side rather than gold side)
      * ``predicted_support``

    Returns ``None`` when no key is present, signalling "not measured"
    rather than the empty set (which would otherwise score every row
    as a complete miss).
    """
    for key in ("predicted_supporting_facts",
                "supporting_facts", "predicted_support"):
        if key in row:
            return _normalize_sf_list(row[key])
    return None


def _set_f1(predicted: Set, gold: Set) -> float:
    """Set-level F1. Empty / empty → 1.0; one empty → 0.0; otherwise
    standard harmonic mean of precision and recall."""
    if not predicted and not gold:
        return 1.0
    if not predicted or not gold:
        return 0.0
    tp = len(predicted & gold)
    if tp == 0:
        return 0.0
    precision = tp / len(predicted)
    recall = tp / len(gold)
    return 2 * precision * recall / (precision + recall)


# ─── Scorer ────────────────────────────────────────────────────────


class WikiMultiScorer(ExternalScorer):
    """Single scorer (no variants — 2WikiMultiHopQA is one benchmark
    with one split-per-loader). Constructor takes no required args
    so the runner can ``WikiMultiScorer()`` without dispatch."""

    @property
    def benchmark_id(self) -> str:
        return "2wiki"

    def score(
        self,
        queries: Iterable["Any"],
        bench_rows: List[Dict[str, Any]],
    ) -> List[ScoreAxis]:
        queries = list(queries)
        self.validate_queries(queries)
        idx = self.index_rows_by_id(bench_rows)

        em_total = 0
        f1_total = 0.0
        n_answer = 0

        # Per-question-type accumulators.
        type_f1_sum: Dict[str, float] = {t: 0.0 for t in WIKIMULTI_TYPES}
        type_n:      Dict[str, int]   = {t: 0   for t in WIKIMULTI_TYPES}

        # Support-fact bookkeeping (set-F1 over [title, sent_id] pairs).
        sf_total = 0.0
        n_sf_rows = 0
        sf_per_query: Dict[str, float] = {}

        per_query_f1: Dict[str, float] = {}

        for q in queries:
            row = idx.get(q.id)
            if row is None:
                # Missing bench row → 0 on EM/F1, support skipped.
                em_total += 0
                f1_total += 0.0
                n_answer += 1
                per_query_f1[q.id] = 0.0
                q_type = str(q.metadata.get("type") or "")
                if q_type in type_n:
                    type_n[q_type] += 1
                    # type_f1_sum += 0.0 (no-op)
                continue

            n_answer += 1
            model_text = _resolve_model_answer(row)
            aliases = q.metadata.get("answer_aliases") or []
            gold = q.gold_answer or ""

            em = _max_em(model_text, gold, aliases)
            f1 = _max_f1(model_text, gold, aliases)
            em_total += em
            f1_total += f1
            per_query_f1[q.id] = round(f1, 4)

            q_type = str(q.metadata.get("type") or "")
            if q_type in type_n:
                type_n[q_type] += 1
                type_f1_sum[q_type] += f1

            # Support-fact axis.
            predicted_sf = _extract_predicted_supporting_facts(row)
            if predicted_sf is not None:
                gold_sf = _normalize_sf_list(
                    q.metadata.get("supporting_facts") or []
                )
                if gold_sf:
                    n_sf_rows += 1
                    sf_f1 = _set_f1(predicted_sf, gold_sf)
                    sf_total += sf_f1
                    sf_per_query[q.id] = round(sf_f1, 4)

        axes: List[ScoreAxis] = []

        if n_answer > 0:
            axes.append(ScoreAxis(
                name="em",
                score=round(em_total / n_answer, 4),
                n_queries=n_answer,
                notes="SQuAD v1.1 normalisation (reused from MuSiQue "
                      "scorer); max over gold + answer_aliases.",
            ))
            axes.append(ScoreAxis(
                name="f1",
                score=round(f1_total / n_answer, 4),
                n_queries=n_answer,
                per_query=per_query_f1,
                notes="token-level F1 on SQuAD-normalised tokens; max "
                      "over gold + answer_aliases.",
            ))
        else:
            axes.append(ScoreAxis(
                name="em", score=0.0, n_queries=0,
                notes="no queries in fixture; EM not measured",
            ))
            axes.append(ScoreAxis(
                name="f1", score=0.0, n_queries=0,
                notes="no queries in fixture; F1 not measured",
            ))

        # Per-type axis: aggregate score = mean of the per-type
        # means (so the headline isn't dominated by the largest type),
        # per_query exposes the per-type means as a dict.
        type_means: Dict[str, float] = {}
        contributing_types: List[float] = []
        for t in WIKIMULTI_TYPES:
            n = type_n[t]
            if n > 0:
                mean = type_f1_sum[t] / n
                type_means[t] = round(mean, 4)
                contributing_types.append(mean)
        if contributing_types:
            axes.append(ScoreAxis(
                name="f1_by_type",
                score=round(
                    sum(contributing_types) / len(contributing_types),
                    4,
                ),
                n_queries=sum(type_n[t] for t in WIKIMULTI_TYPES
                                if type_n[t] > 0),
                per_query=type_means,
                notes="mean of per-type F1 means (so the headline isn't "
                      "dominated by the largest type); per_query = "
                      "{type: mean_f1}.",
            ))
        else:
            axes.append(ScoreAxis(
                name="f1_by_type", score=0.0, n_queries=0,
                notes="no queries carried a 'type' metadata field; "
                      "per-type axis not measured",
            ))

        if n_sf_rows > 0:
            axes.append(ScoreAxis(
                name="support_fact_f1",
                score=round(sf_total / n_sf_rows, 4),
                n_queries=n_sf_rows,
                per_query=sf_per_query,
                notes="set-F1 over [title, sent_id] pairs; rows whose "
                      "bench row lacked predicted_supporting_facts are "
                      "skipped.",
            ))
        else:
            axes.append(ScoreAxis(
                name="support_fact_f1",
                score=0.0,
                n_queries=0,
                notes="no bench row carried a predicted_supporting_facts "
                      "list; support-fact axis not measured (the unified "
                      "runner in A.5 will translate JAMES citations into "
                      "[title, sent_id] pairs).",
            ))

        return axes


__all__ = [
    "WikiMultiScorer",
]
