"""LRB scorer — Phase A axes. Deterministic; no LLM judge anywhere.

The 7 locked Phase A axes (prereg §1.3):

  * R@5 / R@10  — retrieval recall against per-T gold supporting docs.
  * P@5 / P@10  — retrieval precision against per-T gold.
  * Latency      — mean wall-clock retrieval time per query (seconds).
  * Token cost   — mean retrieved-context tokens per query (proxy:
                   chars / 4, the rule of thumb for ASCII tokenisation).
  * Temporal accuracy — fraction of (query, T) evaluations where the
                   top-k retrieved set contains the gold valid-at-T
                   doc set fully (R@k == 1.0 for that evaluation).

All axes are computed both overall and per-category. Per-category
breakdown surfaces where the validity-window discriminator pays off
(shift queries) vs where it's neutral (stable lookups).
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Dict, List


def _recall_at_k(retrieved: List[str], gold: List[str], k: int) -> float:
    """|gold ∩ top_k| / |gold|. Returns 1.0 when gold is empty AND no
    docs retrieved (correct abstention); 0.0 when gold is empty but
    docs retrieved (false positives — stale doc resurfaces)."""
    top = retrieved[:k]
    if not gold:
        return 1.0 if not top else 0.0
    return len(set(gold) & set(top)) / len(gold)


def _precision_at_k(retrieved: List[str], gold: List[str], k: int) -> float:
    """|gold ∩ top_k| / k. When gold is empty, precision is undefined —
    we return 1.0 if no docs retrieved, 0.0 if any (matches recall
    convention above)."""
    top = retrieved[:k]
    if not gold:
        return 1.0 if not top else 0.0
    return len(set(gold) & set(top)) / k


def _temporal_accuracy(retrieved: List[str], gold: List[str],
                       k: int) -> float:
    """1.0 if the top-k retrieved set fully covers the gold set
    (R@k == 1.0), else 0.0. The per-evaluation strict-success rate."""
    return 1.0 if _recall_at_k(retrieved, gold, k) >= 1.0 else 0.0


def score_axes(rows: List[Dict[str, Any]], *,
               k_recall: int = 10) -> Dict[str, Any]:
    """Compute LRB Phase A axes from per-query rows.

    Each row is a dict with keys:
      query_id, timestamp, gold, retrieved, latency_s, context_chars

    Returns a dict with overall axes + per_category and per_timestamp
    breakdowns.
    """
    out: Dict[str, Any] = {}

    # Overall
    r5  = [_recall_at_k(r["retrieved"], r["gold"], 5)  for r in rows]
    r10 = [_recall_at_k(r["retrieved"], r["gold"], 10) for r in rows]
    p5  = [_precision_at_k(r["retrieved"], r["gold"], 5)  for r in rows]
    p10 = [_precision_at_k(r["retrieved"], r["gold"], 10) for r in rows]
    ta  = [_temporal_accuracy(r["retrieved"], r["gold"], k_recall)
           for r in rows]
    lat = [r["latency_s"]     for r in rows]
    ctx = [r["context_chars"] for r in rows]
    token_cost = [c / 4.0 for c in ctx]

    # Exploratory: top-1 axes (NOT part of prereg-locked 7; informs
    # enterprise UX where the first hit is what the user sees).
    r1 = [_recall_at_k(r["retrieved"], r["gold"], 1) for r in rows]
    p1 = [_precision_at_k(r["retrieved"], r["gold"], 1) for r in rows]
    ta_strict = [_temporal_accuracy(r["retrieved"], r["gold"], 1)
                 for r in rows]

    out["overall"] = {
        "R@5":               round(mean(r5),  6),
        "R@10":              round(mean(r10), 6),
        "P@5":               round(mean(p5),  6),
        "P@10":              round(mean(p10), 6),
        "latency_s_mean":    round(mean(lat), 6),
        "token_cost_mean":   round(mean(token_cost), 4),
        "temporal_accuracy": round(mean(ta), 6),
        "n":                 len(rows),
        "exploratory": {
            "R@1":           round(mean(r1), 6),
            "P@1":           round(mean(p1), 6),
            "temporal_accuracy_strict_top1": round(mean(ta_strict), 6),
        },
    }

    # Per timestamp
    by_ts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_ts[r["timestamp"]].append(r)
    out["per_timestamp"] = {}
    for ts in sorted(by_ts):
        ts_rows = by_ts[ts]
        out["per_timestamp"][ts] = {
            "R@5":               round(mean(
                _recall_at_k(r["retrieved"], r["gold"], 5)
                for r in ts_rows), 6),
            "R@10":              round(mean(
                _recall_at_k(r["retrieved"], r["gold"], 10)
                for r in ts_rows), 6),
            "P@5":               round(mean(
                _precision_at_k(r["retrieved"], r["gold"], 5)
                for r in ts_rows), 6),
            "P@10":              round(mean(
                _precision_at_k(r["retrieved"], r["gold"], 10)
                for r in ts_rows), 6),
            "temporal_accuracy": round(mean(
                _temporal_accuracy(r["retrieved"], r["gold"], k_recall)
                for r in ts_rows), 6),
            "latency_s_mean":    round(mean(
                r["latency_s"] for r in ts_rows), 6),
            "token_cost_mean":   round(mean(
                r["context_chars"] / 4.0 for r in ts_rows), 4),
            "n":                 len(ts_rows),
        }

    # Per category (each row needs category — looked up from query_id)
    # Driver does not supply category directly; caller can post-merge.
    return out
