"""Cycle γ Phase A.4.2 — MuSiQue scorer.

Three axes faithful to Trivedi et al. 2022's official evaluation:

* ``em`` — exact match over SQuAD-style normalisation (lowercase,
  punctuation stripped, English articles dropped, whitespace
  collapsed). Maxed over the gold answer and every entry in
  ``answer_aliases``.

* ``f1`` — token-level precision/recall harmonic mean over the same
  normalisation. Maxed over gold + aliases.

* ``support_idx_recall`` — fraction of the gold ``support_idx_set``
  that the model's predicted support indices recover. Read from the
  bench row's ``support_idx`` or ``predicted_support_idx`` field
  (cycle β #7 left ``sources`` as a list, but a list of *citation
  filenames* rather than paragraph indices — the unified runner
  in Phase A.5 will translate, and until then the bench row must
  carry an explicit support-idx list for the axis to fire). When
  no row carries it, the axis is emitted with ``n_queries=0`` and a
  "not measured" note rather than silently scoring 0.

Honest framing
--------------

The normalisation routine + EM/F1 formulas are a one-to-one mirror
of the standard SQuAD evaluator (``v1.1``) that MuSiQue's
``raw_predictions_to_official_format.py`` calls into. The
``support_idx_recall`` axis is the minimum useful primitive — a
proper precision/recall pair (and the joint EM that MuSiQue's
leaderboard reports) would require the runner to pass *both* the
predicted and gold sets and is a follow-up.
"""
from __future__ import annotations

import re
import string
from typing import Any, Dict, Iterable, List, Optional, Set

from eval.external import ScoreAxis
from eval.external.scorer_base import ExternalScorer
from eval.external.musique_loader import MUSIQUE_VARIANTS


# ─── SQuAD-style normalisation (verbatim from squad_v1 evaluator) ───


_ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def _normalize_answer(s: str) -> str:
    """Lower-case, drop articles, strip punctuation, collapse
    whitespace. Matches SQuAD v1.1's ``normalize_answer`` byte-for-
    byte; MuSiQue calls into the same routine via its conversion
    helper."""
    if not isinstance(s, str):
        return ""
    s = s.lower()
    s = _ARTICLES.sub(" ", s)
    s = "".join(ch for ch in s if ch not in string.punctuation)
    s = _WHITESPACE.sub(" ", s).strip()
    return s


def _tokenize(s: str) -> List[str]:
    """Whitespace tokenize the normalised answer. Empty input → empty
    list (so EM/F1 stay defined on missing answers)."""
    n = _normalize_answer(s)
    return n.split() if n else []


def _exact_match(prediction: str, gold: str) -> int:
    return int(_normalize_answer(prediction) == _normalize_answer(gold))


def _f1(prediction: str, gold: str) -> float:
    """Token-level F1 on the normalised tokens. Empty-set edge case
    matches the SQuAD evaluator: both empty → 1.0; exactly one empty
    → 0.0."""
    p_toks = _tokenize(prediction)
    g_toks = _tokenize(gold)
    if not p_toks and not g_toks:
        return 1.0
    if not p_toks or not g_toks:
        return 0.0
    # Token bag intersection — common multiset behaviour matches SQuAD.
    common: Dict[str, int] = {}
    for t in p_toks:
        common[t] = common.get(t, 0) + 1
    overlap = 0
    g_counts: Dict[str, int] = {}
    for t in g_toks:
        g_counts[t] = g_counts.get(t, 0) + 1
    for t, c in common.items():
        overlap += min(c, g_counts.get(t, 0))
    if overlap == 0:
        return 0.0
    precision = overlap / len(p_toks)
    recall = overlap / len(g_toks)
    return 2 * precision * recall / (precision + recall)


def _max_em(prediction: str, gold: str, aliases: List[str]) -> int:
    candidates = [gold] + [a for a in aliases if isinstance(a, str)]
    return max(_exact_match(prediction, c) for c in candidates) if candidates else 0


def _max_f1(prediction: str, gold: str, aliases: List[str]) -> float:
    candidates = [gold] + [a for a in aliases if isinstance(a, str)]
    return max(_f1(prediction, c) for c in candidates) if candidates else 0.0


# ─── Support-idx helpers ───────────────────────────────────────────


def _extract_predicted_support(row: Dict[str, Any]) -> Optional[Set[int]]:
    """Pull the model's predicted support-idx set out of a bench row.

    Accepted keys (in priority order):
      * ``predicted_support_idx`` — explicit list of ints
      * ``support_idx``           — same
      * ``predicted_support``     — same

    Returns ``None`` when none of the keys are present, signalling
    "not measured" to the caller. The runner can then emit the axis
    with the appropriate note rather than scoring 0.

    Non-int entries are silently dropped.
    """
    for key in ("predicted_support_idx", "support_idx", "predicted_support"):
        val = row.get(key)
        if isinstance(val, list):
            out: Set[int] = set()
            for v in val:
                if isinstance(v, int):
                    out.add(v)
                elif isinstance(v, str) and v.strip().lstrip("-").isdigit():
                    out.add(int(v))
            return out
    return None


def _resolve_model_answer(row: Dict[str, Any]) -> str:
    for key in ("answer", "output", "prediction"):
        val = row.get(key)
        if isinstance(val, str):
            return val
    return ""


# ─── Scorer ────────────────────────────────────────────────────────


class MuSiQueScorer(ExternalScorer):
    """One scorer per MuSiQue variant (``musique-ans`` or
    ``musique-full``)."""

    def __init__(self, *, variant: str = "ans"):
        if variant not in MUSIQUE_VARIANTS:
            raise ValueError(
                f"unknown MuSiQue variant: {variant!r}. "
                f"Valid: {MUSIQUE_VARIANTS}"
            )
        self._variant = variant

    @property
    def benchmark_id(self) -> str:
        return f"musique-{self._variant}"

    @property
    def variant(self) -> str:
        return self._variant

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

        # Support-fact bookkeeping. Only rows whose bench row actually
        # carries a predicted-support list contribute.
        n_support_rows = 0
        support_recall_total = 0.0

        per_query: Dict[str, float] = {}

        for q in queries:
            row = idx.get(q.id)
            if row is None:
                # No matching bench row — count as a complete miss on
                # EM/F1. Support axis just skips it.
                em_total += 0
                f1_total += 0.0
                n_answer += 1
                per_query[q.id] = 0.0
                continue

            n_answer += 1
            model_text = _resolve_model_answer(row)
            aliases = q.metadata.get("answer_aliases") or []
            gold = q.gold_answer or ""

            em = _max_em(model_text, gold, aliases)
            f1 = _max_f1(model_text, gold, aliases)
            em_total += em
            f1_total += f1
            per_query[q.id] = round(f1, 4)

            # Support axis.
            predicted = _extract_predicted_support(row)
            if predicted is not None:
                gold_support_raw = q.metadata.get("support_idx_set") or []
                gold_support = {int(x) for x in gold_support_raw
                                 if isinstance(x, int)}
                if gold_support:
                    n_support_rows += 1
                    matched = len(predicted & gold_support)
                    support_recall_total += matched / len(gold_support)

        axes: List[ScoreAxis] = []

        if n_answer > 0:
            axes.append(ScoreAxis(
                name="em",
                score=round(em_total / n_answer, 4),
                n_queries=n_answer,
                notes="SQuAD-style normalisation (lowercase + article "
                      "strip + punctuation strip + whitespace collapse); "
                      "max over gold + answer_aliases.",
            ))
            axes.append(ScoreAxis(
                name="f1",
                score=round(f1_total / n_answer, 4),
                n_queries=n_answer,
                per_query=per_query,
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

        if n_support_rows > 0:
            axes.append(ScoreAxis(
                name="support_idx_recall",
                score=round(support_recall_total / n_support_rows, 4),
                n_queries=n_support_rows,
                notes="|predicted ∩ gold| / |gold| over rows whose bench "
                      "row carried predicted_support_idx (or support_idx "
                      "/ predicted_support).",
            ))
        else:
            axes.append(ScoreAxis(
                name="support_idx_recall",
                score=0.0,
                n_queries=0,
                notes="no bench row carried a predicted_support_idx list; "
                      "support-fact axis not measured (the unified runner "
                      "in Phase A.5 will translate JAMES citation "
                      "filenames into paragraph indices).",
            ))

        return axes


__all__ = [
    "MuSiQueScorer",
]
