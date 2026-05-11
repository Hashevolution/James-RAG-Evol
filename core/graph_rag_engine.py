"""
PROJECT JAMES - Graph-RAG Engine (Phase 4.5 - Thin Wrapper)
[REFACTOR] 책임 분리 완료. 기존 호환용 wrapper만 유지.

내부 구조:
  ReasoningEngine → GraphEngine + RetrievalEngine
  (loop / orchestration / security 전부 reasoning_engine.py 위임)

기존 호환:
  - RAGEngine 클래스명 유지
  - query() / process_query() 시그니처 동일
  - server_llmwiki.py 수정 불필요
"""

import numpy as np
from typing import Dict, Any, Optional, List

from core.reasoning import ReasoningEngine


class RAGEngine:
    """
    Phase 4.5 Thin Wrapper.
    실제 로직은 ReasoningEngine에 위임.
    """

    def __init__(self, default_role: str = "external"):
        self._engine        = ReasoningEngine(default_role=default_role)
        self.vector_store   = self._engine.retrieval.vector_store
        self.wiki_generator = self._engine.graph.wiki_generator
        self.llm            = self._engine.llm
        self.default_role   = default_role

    # ─── 핵심 API ────────────────────────────────────────────

    def query(
        self,
        user_query:  str,
        user_role:   str           = None,
        source_type: Optional[str] = "prod",
        session_id:  str           = "default",   # [P7-FIX]
        **kwargs,
    ) -> Dict[str, Any]:
        return self._engine.query(
            user_query  = user_query,
            user_role   = user_role or self.default_role,
            source_type = source_type,
            session_id  = session_id,
            **kwargs,
        )

    def process_query(self, question: str, user_role: str = None,
                      session_id: str = "default") -> Dict[str, Any]:
        try:
            result = self.query(question, user_role=user_role, session_id=session_id)
            return {
                "answer":      result.get("answer", ""),
                "sources":     result.get("sources", []),
                "blocked":     result.get("blocked", False),
                "graph_paths": result.get("graph_paths", []),
                "timing_sec":  result.get("timing_sec", 0),
            }
        except Exception as e:
            from core.security_layer import log_system_event
            log_system_event("rag_engine.process_query", str(e))
            return {"answer": f"오류: {e}", "sources": [], "blocked": False,
                    "graph_paths": [], "timing_sec": 0}

    # ─── 기존 코드 호환 헬퍼 ────────────────────────────────

    def hybrid_search(self, question: str, top_k: int = 8, **kwargs) -> List[Dict]:
        return self._engine.retrieval.hybrid_search(
            question, top_k=top_k,
            user_role=kwargs.get("user_role", self.default_role),
        )

    def extract_entities(self, query: str, docs: list, timeout: int = 30) -> List[Dict]:
        return self._engine.retrieval.extract_entities(query, docs, timeout=timeout)

    def expand_graph_dynamic(self, entity_ids: list, source_type_filter=None):
        return self._engine.graph.expand_dynamic(entity_ids, source_type_filter=source_type_filter)

    def _verify_reasoning(self, paths: list) -> list:
        return self._engine.graph.verify_reasoning(paths)

    def _rank_graph_nodes(self, graph_context: list) -> list:
        return self._engine.graph.rank_nodes(graph_context)

    def _build_entity_map_snapshot(self) -> dict:
        return self._engine.graph.build_entity_map_snapshot()

    def match_entities(self, entities: list, snapshot=None) -> list:
        return self._engine.graph.match_entities(entities, snapshot)

    def _validate_graph_integrity(self, entity_ids: list) -> list:
        return self._engine.graph.validate_integrity(entity_ids)

    def generate_answer(self, question: str, context: str) -> str:
        return self._engine._generate_answer(question, context)

    def _normalize_no_info_answer(self, answer: str) -> str:
        return self._engine._normalize_no_info(answer)

    def build_context(
        self,
        docs: list,
        graph_entities: list,
        doc_scores: list = None,
        graph_paths: list = None,
    ) -> str:
        doc_ctx, avg = self._engine.retrieval.build_doc_context(docs, doc_scores)
        graph_ctx    = self._engine.graph.build_graph_context_str(
            graph_entities or [], graph_paths or [], unified_score=avg
        )
        return doc_ctx + graph_ctx

    @staticmethod
    def _normalize_bm25(scores: list) -> list:
        if isinstance(scores, np.ndarray):
            scores = scores.tolist()
        if not scores:
            return []
        scores = [float(s) for s in scores]
        mn, mx = min(scores), max(scores)
        return [(s - mn) / (mx - mn) for s in scores] if mx - mn > 0 else [0.0] * len(scores)
