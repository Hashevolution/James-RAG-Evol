"""Naive supersede-aware RAG SUT for LRB.

Position between Vanilla (knows nothing) and JAMES (validity window
per-event). This SUT understands the SUPERSEDE concept — when a doc is
superseded, the new version replaces the old in the index — but it does
NOT track temporal validity. It cannot answer "what was the policy at
T=6w?" correctly if asked at T=12w (no time travel).

For LRB Phase A/B, this is sufficient because queries are evaluated at
the timestamp the adapter is freshly built up to. So at T=6w, the SUT
state reflects all events through week 6, and SUPERSEDE has correctly
replaced superseded docs.

The expected behaviour vs Vanilla:
  * SUPERSEDE: old doc removed from index, new doc inserted
  * UPDATE: in-place text revision (same as Vanilla)
  * DELETE: doc removed (same as Vanilla)
  * INGEST: insert (same as Vanilla)

The expected behaviour vs JAMES:
  * No validity-window tracking; cannot reconstruct prior-T states
  * Phase A/B doesn't query prior-T because adapter is re-built per T

This SUT is the realistic mid-point: many production RAG systems
implement "supersede = delete-then-insert" at the document store level.
It's the honest comparison for "does JAMES add value beyond just
implementing supersede correctly?"
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


class NaiveSupersedeAdapter:
    """Token-overlap retriever that honours SUPERSEDE = remove-old."""

    def __init__(self) -> None:
        self._docs: Dict[str, Tuple[str, str]] = {}
        self._vecs: Dict[str, Counter] = {}

    def _index(self, doc_id: str, title: str, text: str) -> None:
        haystack = title + " " + text[:400]
        self._docs[doc_id] = (title, text)
        self._vecs[doc_id] = Counter(_tokenize(haystack))

    def _remove(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)
        self._vecs.pop(doc_id, None)

    # ── mutating ops ────────────────────────────────────────────────

    def ingest(self, doc_id: str, title: str, text: str,
               week: int) -> None:
        self._index(doc_id, title, text)

    def update(self, doc_id: str, title: str, text: str,
               week: int) -> None:
        self._index(doc_id, title, text)

    def supersede(self, old_doc_id: str, new_doc_id: str,
                  title: str, text: str, week: int) -> None:
        # The key difference vs Vanilla: remove the old doc when
        # superseded. This is a realistic production-RAG behaviour.
        self._remove(old_doc_id)
        self._index(new_doc_id, title, text)

    def delete(self, doc_id: str, week: int) -> None:
        self._remove(doc_id)

    # ── retrieval (no validity filter — adapter rebuilt per T) ──────

    def _idf(self) -> Dict[str, float]:
        n = len(self._docs)
        df: Counter = Counter()
        for v in self._vecs.values():
            for term in v:
                df[term] += 1
        return {t: math.log(1 + n / (1 + df[t])) for t in df}

    def retrieve_at(self, q: str, k: int, query_time: int,
                    valid_time: int) -> List[str]:
        """Time-travel-aware interface. Naive-supersede ignores
        ``valid_time`` — its state is only the CURRENT (query_time)
        state. Historical queries return the present-day version, which
        is incorrect for non-current valid_time."""
        return self.retrieve(q, k, query_time)

    def retrieve(self, q: str, k: int, t_week: int) -> List[str]:
        idf = self._idf()
        qv = Counter(_tokenize(q))
        if not qv or not self._docs:
            return []
        q_w = {t: cnt * idf.get(t, 0.0) for t, cnt in qv.items()}
        q_norm = math.sqrt(sum(w * w for w in q_w.values())) or 1.0
        scores: List[Tuple[str, float]] = []
        for doc_id, dv in self._vecs.items():
            d_w = {t: cnt * idf.get(t, 0.0) for t, cnt in dv.items()}
            dot = sum(q_w.get(t, 0.0) * d_w.get(t, 0.0)
                      for t in q_w)
            if dot <= 0:
                continue
            d_norm = math.sqrt(sum(w * w for w in d_w.values())) or 1.0
            scores.append((doc_id, dot / (q_norm * d_norm)))
        scores.sort(key=lambda x: (-x[1], x[0]))
        return [d for d, _ in scores[:k]]

    def retrieved_text_length(self, doc_ids: List[str]) -> int:
        return sum(len(self._docs[d][1]) for d in doc_ids
                   if d in self._docs)

    def get_doc(self, doc_id: str):
        """Read-only accessor used by cross-model rerank wrapper."""
        return self._docs.get(doc_id)
