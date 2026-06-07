"""Cycle γ Phase A.4.1 — RGB scorer.

Two axes (faithful to Chen et al. 2024's official evaluation):

* ``noise_robustness_accuracy`` — over rows with ``positive_count >
  0``, the fraction whose model answer contains the gold answer (or
  any alias) by lowercase substring match. Mirrors RGB's ``label ==
  1`` accuracy under noise.

* ``negative_rejection_f1`` — over rows with ``positive_count ==
  0`` (abstention cases), the F1 of the model's abstention
  behaviour against the ground truth ("abstain"). Mirrors the
  Calibrated Abstention F1 the JAMES bench already computes for
  MultiHop-RAG (``eval.qvt.oracle.score_abstention_f1``), so the
  cycle γ cross-bench table can compare apples to apples.

  Treated as a confusion matrix over abstention behaviour::

      ┌──────────────┬────────────────┬───────────────────────────────┐
      │              │ model abstained│ model produced answer         │
      ├──────────────┼────────────────┼───────────────────────────────┤
      │ truth: absent│ TP             │ FN (hallucination)            │
      │ truth: present│ FP (over-abstain)│ TN                          │
      └──────────────┴────────────────┴───────────────────────────────┘

  ``F1 = TP / (TP + 0.5 (FP + FN))``.

Honest framing
--------------

The two axes are string-based — no NLI, no semantic equivalence.
RGB's reference scoring also leans heavily on string matching
(``label == 1`` when the model output literally contains the gold
substring), so the approximation here is the same primary signal,
not a substitute. The scorer records this in ``ScoreAxis.notes``
when caveats apply (e.g. when no abstention cases exist in the
fixture for the negative_rejection_f1 axis).

Self-eval trap rule: the abstention patterns + matching logic mirror
RGB's ``evalue.py``'s reference detection — they're not JAMES-internal
inventions. The patterns themselves come from the published paper's
prompts ("I cannot find" / "I don't know" / 中文 "无法回答" etc.).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from eval.external import ScoreAxis
from eval.external.scorer_base import ExternalScorer
from eval.external.rgb_loader import RGB_VARIANTS


# ─── Abstention indicators ─────────────────────────────────────────


# English: lowercase patterns. The matching path lowercases the
# model output once, so each token here is a substring check on a
# lowercased string.
_ABSTENTION_EN: Tuple[str, ...] = (
    "i cannot find",
    "i can not find",
    "i can't find",
    "i cannot answer",
    "i can not answer",
    "i can't answer",
    "i cannot determine",
    "i can not determine",
    "i can't determine",
    "i don't know",
    "i do not know",
    "i'm not sure",
    "i am not sure",
    "unable to answer",
    "unable to determine",
    "insufficient information",
    "insufficient context",
    "insufficient evidence",
    "no information available",
    "no relevant information",
    "not enough information",
    "not mentioned",
    "not specified",
    "not provided",
    "no answer",
    "cannot be determined",
    "cannot be answered",
)

# Chinese: simplified patterns for the zh.json / zh_refine.json
# / zh_int.json / zh_fact.json variants. Matching is done on the raw
# (lower-cased — a no-op for Chinese) model output. ``zh`` text in
# the test fixtures stays UTF-8 throughout.
_ABSTENTION_ZH: Tuple[str, ...] = (
    "不知道",
    "无法回答",
    "无法确定",
    "无法判断",
    "没有信息",
    "没有相关",
    "没有提到",
    "信息不足",
    "没有足够信息",
    "无法回应",
    "找不到",
    "未提及",
    "无关",
    "无答案",
)


def _detects_abstention(answer: str, *, language: str) -> bool:
    """True iff ``answer`` matches an abstention indicator for
    ``language``.

    The check is **inclusive** — any matched pattern counts. The
    intent is to credit the model for refusing in a recognisable
    way; a JAMES-internal stricter filter would let the scorer
    artificially raise its own benchmark, which the self-eval trap
    rule explicitly disallows.

    Empty / non-string answers count as abstention (the model
    produced nothing, which on the negative_rejection axis is the
    correct behaviour).
    """
    if not isinstance(answer, str) or not answer.strip():
        return True
    lower = answer.lower()
    patterns = _ABSTENTION_ZH if language == "zh" else _ABSTENTION_EN
    for p in patterns:
        if p in lower:
            return True
    return False


def _answer_contains_gold(
    answer: str,
    gold: str,
    aliases: List[str],
) -> bool:
    """RGB's noise-robustness ``label == 1`` rule: the model output
    literally contains the gold answer (case-insensitive) or any
    alias.
    """
    if not isinstance(answer, str) or not answer:
        return False
    lower_ans = answer.lower()
    if gold and gold.lower() in lower_ans:
        return True
    for a in aliases or []:
        if isinstance(a, str) and a and a.lower() in lower_ans:
            return True
    return False


def _resolve_model_answer(row: Dict[str, Any]) -> str:
    """Bench rows usually carry the model's text under ``answer``
    (the JAMES bench shape) but some external runners use ``output``
    (the ALCE shape). Accept either."""
    for key in ("answer", "output", "prediction"):
        val = row.get(key)
        if isinstance(val, str):
            return val
    return ""


# ─── Scorer ────────────────────────────────────────────────────────


class RGBScorer(ExternalScorer):
    """One scorer per RGB variant (``rgb-en`` / ``rgb-zh`` / each
    refine / int / fact). The variant is fixed at construction so
    the language for abstention detection is unambiguous."""

    def __init__(self, *, variant: str = "en"):
        if variant not in RGB_VARIANTS:
            raise ValueError(
                f"unknown RGB variant: {variant!r}. "
                f"Valid: {RGB_VARIANTS}"
            )
        self._variant = variant

    @property
    def benchmark_id(self) -> str:
        return f"rgb-{self._variant}"

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

        # Noise-robustness bookkeeping.
        nr_total = 0
        nr_hits = 0
        # Negative-rejection bookkeeping (abstention confusion matrix).
        tp = 0  # truth=absent  + model=abstain
        fn = 0  # truth=absent  + model=produced (hallucination)
        fp = 0  # truth=present + model=abstain (over-abstain)
        tn = 0  # truth=present + model=produced (correct attempt)

        for q in queries:
            row = idx.get(q.id)
            if row is None:
                # No matching bench row — counts as the model NOT
                # producing an answer, i.e. abstention. The
                # negative_rejection axis credits it as TP for
                # absent-truth, FP for present-truth. The
                # noise_robustness axis simply skips it.
                model_text = ""
                row_present = False
            else:
                model_text = _resolve_model_answer(row)
                row_present = True

            language = q.metadata.get("language") or (
                "zh" if self._variant.startswith("zh") else "en"
            )
            positive_count = int(q.metadata.get("positive_count", 0))
            truth_absent = (positive_count == 0)
            abstained = _detects_abstention(model_text, language=language)

            if truth_absent:
                if abstained:
                    tp += 1
                else:
                    fn += 1
            else:
                # Noise-robustness measures over the truth=present
                # subset.
                if row_present:
                    nr_total += 1
                    gold = q.gold_answer or ""
                    aliases = q.metadata.get("answer_aliases") or []
                    if _answer_contains_gold(model_text, gold, aliases):
                        nr_hits += 1
                if abstained:
                    fp += 1
                else:
                    tn += 1

        axes: List[ScoreAxis] = []

        # noise_robustness_accuracy
        if nr_total > 0:
            axes.append(ScoreAxis(
                name="noise_robustness_accuracy",
                score=round(nr_hits / nr_total, 4),
                n_queries=nr_total,
                notes="lowercase substring match against gold + aliases "
                      "(RGB official label==1 rule)",
            ))
        else:
            axes.append(ScoreAxis(
                name="noise_robustness_accuracy",
                score=0.0,
                n_queries=0,
                notes="no rows with positive_count > 0 in this fixture "
                      "slice; axis not measured",
            ))

        # negative_rejection_f1. Always emit the confusion matrix under
        # per_query so downstream analysis can spot over-abstention
        # (fp > 0) even on slices that lack absent-truth rows.
        n_absent = tp + fn
        n_present = fp + tn
        confusion = {
            "tp": float(tp),
            "fp": float(fp),
            "fn": float(fn),
            "tn": float(tn),
        }
        if n_absent > 0:
            denom = tp + 0.5 * (fp + fn)
            f1 = (tp / denom) if denom > 0 else 0.0
            axes.append(ScoreAxis(
                name="negative_rejection_f1",
                score=round(f1, 4),
                n_queries=n_absent + n_present,
                per_query=confusion,
                notes="abstention detected by pattern match; F1 mirrors "
                      "JAMES Calibrated Abstention F1 "
                      "(eval.qvt.oracle.score_abstention_f1)",
            ))
        else:
            axes.append(ScoreAxis(
                name="negative_rejection_f1",
                score=0.0,
                n_queries=0,
                per_query=confusion,
                notes="no abstention (positive_count == 0) rows in this "
                      "fixture slice; F1 axis not measured. Confusion "
                      "matrix still recorded so over-abstention (fp > 0) "
                      "stays visible.",
            ))

        return axes


__all__ = [
    "RGBScorer",
]
