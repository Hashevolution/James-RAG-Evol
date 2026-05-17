"""Retrieval-side cognitive layer modules (v0.3 Phase 1, 2026-05-17).

ARCHITECTURE.md §5.7.1: this package is the home for query rewriter,
reranker, and adaptive-retrieval primitives that sit between the
existing `core/retrieval_engine.py` (vector + BM25) and the LLM
synthesis step. New modules land here; the v0.2 retrieval engine
stays at `core/retrieval_engine.py`.

Phase 1 PR-1 ships `rerank.py` (cross-encoder reranking).
Future PRs add `query_rewriter.py`, `hybrid.py`, `adaptive.py`.
"""
