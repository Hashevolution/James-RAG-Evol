"""Track C answer-F1 scorer — SQuAD-style EM/F1 + per-bench aggregation.

Shared deterministic scorer for the three Track C benches (TimeQA,
TempReason, MuSiQue). Re-exports the SQuAD v1.1 normalisation /
exact-match / token-F1 primitives (the same routines MuSiQue's
official evaluator uses, mirrored in
``eval/external/musique_scorer.py``).

Per Track C C0 §3.1:
  * Token F1 (SQuAD-norm)
  * Exact Match (EM, SQuAD-norm)

Per-bench extension:
  * TimeQA: answer must be in valid time window (official scoring)
  * MuSiQue: support-fact recall already in musique_scorer
  * TempReason: standard EM/F1
"""
from __future__ import annotations

import re
import string
from statistics import mean
from typing import Any, Dict, Iterable, List


# ─── SQuAD v1.1 normalization (matches musique_scorer byte-for-byte) ──


_ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def _normalize_answer(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.lower()
    s = _ARTICLES.sub(" ", s)
    s = "".join(ch for ch in s if ch not in string.punctuation)
    s = _WHITESPACE.sub(" ", s).strip()
    return s


def _tokens(s: str) -> List[str]:
    n = _normalize_answer(s)
    return n.split() if n else []


def exact_match(prediction: str, gold: str) -> int:
    return int(_normalize_answer(prediction) == _normalize_answer(gold))


def token_f1(prediction: str, gold: str) -> float:
    p = _tokens(prediction)
    g = _tokens(gold)
    if not p and not g:
        return 1.0
    if not p or not g:
        return 0.0
    common = set(p) & set(g)
    if not common:
        return 0.0
    # Standard SQuAD F1 uses multiset counts
    from collections import Counter
    p_cnt = Counter(p)
    g_cnt = Counter(g)
    tp = sum((p_cnt & g_cnt).values())
    if tp == 0:
        return 0.0
    precision = tp / len(p)
    recall = tp / len(g)
    return 2 * precision * recall / (precision + recall)


def max_em(prediction: str, candidates: Iterable[str]) -> int:
    cands = list(candidates) or [""]
    return max(exact_match(prediction, c) for c in cands)


def max_f1(prediction: str, candidates: Iterable[str]) -> float:
    cands = list(candidates) or [""]
    return max(token_f1(prediction, c) for c in cands)


# ─── Aggregation ──────────────────────────────────────────────────────


def score_answer_f1(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate EM + F1 over a list of per-query rows.

    Each row dict needs:
      * ``prediction``: str (generated answer)
      * ``gold``: str (primary gold answer)
      * ``answer_aliases``: list[str] (optional)

    Returns:
      ``{"EM": float, "F1": float, "n": int, "n_empty_pred": int}``
    """
    if not rows:
        return {"EM": 0.0, "F1": 0.0, "n": 0, "n_empty_pred": 0}
    em_scores: List[float] = []
    f1_scores: List[float] = []
    empty = 0
    for r in rows:
        pred = (r.get("prediction") or "").strip()
        if not pred:
            empty += 1
        gold = r.get("gold") or ""
        aliases = r.get("answer_aliases") or []
        cands = [gold] + list(aliases)
        em_scores.append(max_em(pred, cands))
        f1_scores.append(max_f1(pred, cands))
    return {
        "EM": round(mean(em_scores), 6),
        "F1": round(mean(f1_scores), 6),
        "n":  len(rows),
        "n_empty_pred": empty,
    }


__all__ = [
    "_normalize_answer", "exact_match", "token_f1",
    "max_em", "max_f1", "score_answer_f1",
]
