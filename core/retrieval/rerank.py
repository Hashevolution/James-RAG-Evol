"""Cross-encoder reranker — Cognitive Layer Phase 1 PR-1.

ARCHITECTURE.md §5.7.1: "Reranker — cross-encoder reordering of
vector-retrieved top-k". Lives between Loop-0 retrieval (orchestrator,
top_k=8) and the existing top-5 truncation in pipeline.py.

Default model: ``cross-encoder/ms-marco-MiniLM-L-6-v2`` (~80 MB, English-
optimized, fast — chosen for the v0.3 local-first profile per the
2026-05-14 user briefing). Operators with Korean-heavy corpora can
swap to ``BAAI/bge-reranker-base`` (~278 MB, multilingual) via the
``JAMES_RERANKER_MODEL`` env var.

Operational knobs:
  JAMES_DISABLE_RERANK=1
      Skip reranking entirely. The pipeline falls back to vector-score
      order (v0.3.0 baseline behavior). Useful for A/B comparison and
      for environments without GPU / sentence-transformers extras.
  JAMES_RERANKER_MODEL=<hf-id>
      Override the default cross-encoder model id.

Failure posture: best-effort. If the model fails to load (no
sentence-transformers, no network for first-time download, GPU OOM),
``rerank()`` logs the failure once and returns the input docs
unchanged. STEP 7 baseline is preserved when reranking is unavailable.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional


DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _disabled() -> bool:
    return os.environ.get("JAMES_DISABLE_RERANK") == "1"


def _model_id() -> str:
    return os.environ.get("JAMES_RERANKER_MODEL", "").strip() or DEFAULT_MODEL


class Reranker:
    """One CrossEncoder instance per process (lazy-loaded).

    Thread-safe lazy init — the first call to ``rerank()`` triggers
    model download (if needed) + GPU/CPU placement; subsequent calls
    reuse the loaded model. Failures during load are sticky for the
    lifetime of the instance so we don't retry on every query.
    """

    def __init__(self, model_id: Optional[str] = None) -> None:
        self._model_id = model_id or _model_id()
        self._model = None             # type: ignore[assignment]
        self._load_failed = False
        self._load_lock = threading.Lock()

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._load_failed:
            return False
        with self._load_lock:
            if self._model is not None:
                return True
            if self._load_failed:
                return False
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self._model_id)
                print(f"[RERANK] model loaded: {self._model_id}")
                return True
            except Exception as e:
                # Sticky failure — don't spam the log on every query.
                self._load_failed = True
                print(f"[RERANK] model load failed ({type(e).__name__}: "
                      f"{str(e)[:120]}) — falling back to vector-score order")
                return False

    def score_pairs(self, query: str, docs: List[Dict[str, Any]]) -> List[float]:
        """Return one cross-encoder score per doc, same order as input.

        Empty doc list → empty list. If the model is unavailable, returns
        the vector scores (caller's existing ranking key) so downstream
        sort is a no-op.
        """
        if not docs:
            return []
        if not self._ensure_loaded():
            return [float(d.get("score", 0.0)) for d in docs]

        pairs = [(query, d.get("text", "") or "") for d in docs]
        try:
            scores = self._model.predict(pairs)   # type: ignore[union-attr]
        except Exception as e:
            print(f"[RERANK] predict failed ({type(e).__name__}: "
                  f"{str(e)[:120]}) — falling back to vector-score order")
            return [float(d.get("score", 0.0)) for d in docs]

        # CrossEncoder returns a numpy array; coerce to plain floats so
        # downstream JSON serialization (audit_log, trace replay) stays
        # straightforward.
        return [float(s) for s in scores]

    def rerank(
        self,
        query: str,
        docs: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Reorder ``docs`` by cross-encoder score (desc), truncate to
        top_k. Adds ``rerank_score`` to each returned dict for audit /
        observability so the operator can see why the new order won.

        Empty input → empty output.
        Disabled / model-load failure / model.predict failure → original
        docs truncated to top_k, **no annotation** (callers can branch
        on ``"rerank_score" in d`` to distinguish a real rerank from a
        fallback).
        """
        if not docs:
            return []
        if _disabled() or not self._ensure_loaded():
            return docs[:top_k]

        # Predict inline so a runtime failure can fall back cleanly
        # without leaving partial annotations. ``score_pairs`` exists
        # as a public API for callers that want raw scores (and accepts
        # the "return vector scores on failure" contract — useful for
        # downstream code that needs *some* score).
        pairs = [(query, d.get("text", "") or "") for d in docs]
        try:
            raw_scores = self._model.predict(pairs)   # type: ignore[union-attr]
        except Exception as e:
            print(f"[RERANK] predict failed ({type(e).__name__}: "
                  f"{str(e)[:120]}) — falling back to vector-score order")
            return docs[:top_k]

        scores = [float(s) for s in raw_scores]
        if len(scores) != len(docs):
            return docs[:top_k]

        # Annotate + sort. Stable sort preserves the input order when
        # cross-encoder ties happen (rare with float scores but possible).
        annotated = [
            {**d, "rerank_score": s, "vector_score": float(d.get("score", 0.0))}
            for d, s in zip(docs, scores)
        ]
        annotated.sort(key=lambda d: d["rerank_score"], reverse=True)
        return annotated[:top_k]


# ─── module-level singleton ────────────────────────────────────────
# Production callers go through get_reranker() so the model loads once
# per process. Tests can either patch the singleton or construct a
# fresh Reranker(model_id=...) for isolation.
_SINGLETON: Optional[Reranker] = None
_SINGLETON_LOCK = threading.Lock()


def get_reranker() -> Reranker:
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = Reranker()
    return _SINGLETON


def _clear_singleton_for_tests() -> None:
    """Test helper. Production code never calls this."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


__all__ = [
    "DEFAULT_MODEL",
    "Reranker",
    "get_reranker",
]
