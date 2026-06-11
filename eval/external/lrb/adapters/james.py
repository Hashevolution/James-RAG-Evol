"""JAMES audit-native SUT for LRB Phase A.

Same token-overlap retriever as Vanilla — only the **filter** differs:
JAMES applies a validity-window filter at query time. Docs that have
been superseded or deleted before the query timestamp are excluded
from the retrieval set, so token-overlap matches against stale text
do not surface.

This isolates the validity-window axis from any other architectural
difference (no graph, no rerank, no chunking) — the Phase A measurement
is a clean test of whether *just* the validity filter moves the
temporal-accuracy / R@k axes.

Note: JAMES production code has a full 5-layer architecture (Memory
Lifecycle), of which the validity window is one part. The Phase A
adapter exposes ONLY that one part — Phase B will add graph + cascade
to the comparison.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple


_TOK = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]+")
_STOP = {
    "the", "a", "an", "of", "and", "or", "for", "to", "in", "on",
    "at", "by", "with", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "as", "from", "it",
    "its", "into", "than", "then", "but", "not", "no", "so",
}


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOK.findall(text)
            if t.lower() not in _STOP and len(t) >= 2]


class _DocRecord:
    __slots__ = ("doc_id", "title", "text", "vec", "valid_from",
                 "valid_to")

    def __init__(self, doc_id: str, title: str, text: str,
                 valid_from: int, valid_to: int):
        self.doc_id = doc_id
        self.title = title
        self.text = text
        haystack = title + " " + text[:400]
        self.vec = Counter(_tokenize(haystack))
        self.valid_from = valid_from
        self.valid_to = valid_to  # inclusive; INF = 10_000

    def valid_at(self, t: int) -> bool:
        return self.valid_from <= t <= self.valid_to


INF = 10_000


class JamesValidityAdapter:
    """Validity-window-aware in-memory retriever."""

    def __init__(self) -> None:
        # All historical doc versions are retained — the filter
        # selects which ones are valid at query time.
        self._records: Dict[str, _DocRecord] = {}

    # ── mutating ops ────────────────────────────────────────────────

    def ingest(self, doc_id: str, title: str, text: str,
               week: int) -> None:
        self._records[doc_id] = _DocRecord(
            doc_id, title, text, valid_from=week, valid_to=INF)

    def update(self, doc_id: str, title: str, text: str,
               week: int) -> None:
        # UPDATE = in-place text revision; validity window unchanged.
        # We honour the new text immediately (no history kept for
        # UPDATEs in this Phase A scope — LRB v0.2 may extend).
        if doc_id in self._records:
            rec = self._records[doc_id]
            self._records[doc_id] = _DocRecord(
                doc_id, title, text,
                valid_from=rec.valid_from, valid_to=rec.valid_to)
        else:
            # Permissive: treat UPDATE on unknown doc as INGEST
            self.ingest(doc_id, title, text, week)

    def supersede(self, old_doc_id: str, new_doc_id: str,
                  title: str, text: str, week: int) -> None:
        # Mark old doc valid until week-1
        if old_doc_id in self._records:
            old = self._records[old_doc_id]
            old.valid_to = max(week - 1, old.valid_from)
        # Insert new doc valid from week
        self._records[new_doc_id] = _DocRecord(
            new_doc_id, title, text, valid_from=week, valid_to=INF)

    def delete(self, doc_id: str, week: int) -> None:
        if doc_id in self._records:
            rec = self._records[doc_id]
            rec.valid_to = max(week - 1, rec.valid_from - 1)
            # If valid_to < valid_from, the doc is never valid

    # ── retrieval (validity-filtered) ───────────────────────────────

    def _idf_at(self, t_week: int) -> Dict[str, float]:
        live = [r for r in self._records.values() if r.valid_at(t_week)]
        n = len(live)
        df: Counter = Counter()
        for r in live:
            for term in r.vec:
                df[term] += 1
        return {t: math.log(1 + n / (1 + df[t])) for t in df}

    def retrieve_at(self, q: str, k: int, query_time: int,
                    valid_time: int) -> List[str]:
        """Time-travel retrieval — return top-k docs valid at
        ``valid_time``, regardless of ``query_time`` (assuming
        query_time >= valid_time; this method does not undo events).

        This is JAMES's unique contribution vs supersede-aware-only
        RAG: the validity-window per-event lets us reconstruct what
        was true at an earlier T from a later vantage point."""
        return self.retrieve(q, k, valid_time)

    def retrieve(self, q: str, k: int, t_week: int) -> List[str]:
        live = [r for r in self._records.values() if r.valid_at(t_week)]
        if not live:
            return []
        idf = self._idf_at(t_week)
        qv = Counter(_tokenize(q))
        if not qv:
            return []
        q_w = {t: cnt * idf.get(t, 0.0) for t, cnt in qv.items()}
        q_norm = math.sqrt(sum(w * w for w in q_w.values())) or 1.0
        scores: List[Tuple[str, float]] = []
        for r in live:
            d_w = {t: cnt * idf.get(t, 0.0) for t, cnt in r.vec.items()}
            dot = sum(q_w.get(t, 0.0) * d_w.get(t, 0.0)
                      for t in q_w)
            if dot <= 0:
                continue
            d_norm = math.sqrt(sum(w * w for w in d_w.values())) or 1.0
            scores.append((r.doc_id, dot / (q_norm * d_norm)))
        scores.sort(key=lambda x: (-x[1], x[0]))
        return [d for d, _ in scores[:k]]

    def retrieved_text_length(self, doc_ids: List[str]) -> int:
        return sum(len(self._records[d].text) for d in doc_ids
                   if d in self._records)
