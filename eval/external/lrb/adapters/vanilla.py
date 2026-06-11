"""Vanilla in-memory RAG SUT for LRB Phase A.

Implements an append-only token-overlap retriever. No supersede
understanding; UPDATE re-indexes (overwrites the doc); DELETE removes
the doc; SUPERSEDE keeps BOTH old and new docs in the index (the
classic "quickstart" behaviour). This is the honest floor.

Retrieval = TF-IDF-style token overlap on title + first 400 chars of
text. Deterministic; no embeddings dependency for Phase A smoke (cost
parity with prior-art quickstarts that ship with default settings).
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


class VanillaRagAdapter:
    def __init__(self) -> None:
        # doc_id -> (title, text)
        self._docs: Dict[str, Tuple[str, str]] = {}
        # cached token vectors per doc_id
        self._vecs: Dict[str, Counter] = {}

    def _index(self, doc_id: str, title: str, text: str) -> None:
        haystack = title + " " + text[:400]
        self._docs[doc_id] = (title, text)
        self._vecs[doc_id] = Counter(_tokenize(haystack))

    # ── mutating ops ────────────────────────────────────────────────

    def ingest(self, doc_id: str, title: str, text: str,
               week: int) -> None:
        self._index(doc_id, title, text)

    def update(self, doc_id: str, title: str, text: str,
               week: int) -> None:
        # In-place re-index
        self._index(doc_id, title, text)

    def supersede(self, old_doc_id: str, new_doc_id: str,
                  title: str, text: str, week: int) -> None:
        # Vanilla keeps BOTH old and new (quickstart behaviour).
        self._index(new_doc_id, title, text)

    def delete(self, doc_id: str, week: int) -> None:
        self._docs.pop(doc_id, None)
        self._vecs.pop(doc_id, None)

    # ── retrieval ──────────────────────────────────────────────────

    def _idf(self) -> Dict[str, float]:
        n = len(self._docs)
        df: Counter = Counter()
        for v in self._vecs.values():
            for term in v:
                df[term] += 1
        return {t: math.log(1 + n / (1 + df[t])) for t in df}

    def retrieve_at(self, q: str, k: int, query_time: int,
                    valid_time: int) -> List[str]:
        """Time-travel-aware interface. Vanilla ignores ``valid_time``
        (it has no concept of validity windows) — returns the current
        retrieval. Historical queries are deterministically incorrect
        relative to gold; this is the floor for the time-travel axis."""
        return self.retrieve(q, k, query_time)

    def retrieve(self, q: str, k: int, t_week: int) -> List[str]:
        idf = self._idf()
        qv = Counter(_tokenize(q))
        if not qv or not self._docs:
            return []
        # tf-idf cosine
        scores: List[Tuple[str, float]] = []
        q_w = {t: cnt * idf.get(t, 0.0) for t, cnt in qv.items()}
        q_norm = math.sqrt(sum(w * w for w in q_w.values())) or 1.0
        for doc_id, dv in self._vecs.items():
            d_w = {t: cnt * idf.get(t, 0.0) for t, cnt in dv.items()}
            dot = sum(q_w.get(t, 0.0) * d_w.get(t, 0.0)
                      for t in q_w)
            if dot <= 0:
                continue
            d_norm = math.sqrt(sum(w * w for w in d_w.values())) or 1.0
            scores.append((doc_id, dot / (q_norm * d_norm)))
        # Tie-break by doc_id for determinism
        scores.sort(key=lambda x: (-x[1], x[0]))
        return [d for d, _ in scores[:k]]

    def retrieved_text_length(self, doc_ids: List[str]) -> int:
        return sum(len(self._docs[d][1]) for d in doc_ids
                   if d in self._docs)

    def get_doc(self, doc_id: str):
        """Read-only accessor used by cross-model rerank wrapper. Returns
        ``(title, text)`` or ``None``. Time-validity is *not* enforced
        — the wrapper feeds doc_ids that the adapter already filtered
        through ``retrieve_at``."""
        return self._docs.get(doc_id)
