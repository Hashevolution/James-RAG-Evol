"""
PROJECT JAMES - Retrieval Engine (Phase 4.5)
[REFACTOR] graph_rag_engine.py 분리 — Vector + BM25 책임 전담

책임:
  - Hybrid Search (Vector 0.6 + BM25 0.2 + keyword 0.1 + name 0.1)
  - ABAC 기반 문서 필터
  - Entity 추출 (LLM + rule-based fallback)
  - source_type 필터 [P4.5-2]
  - Context 결합 (doc + graph)

호출 관계:
  reasoning_engine.py → RetrievalEngine
"""

import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

from core.vector_store import VectorStore
from core.gemma_client import GemmaClient
from core.security_layer import log_system_event
from core.policy_engine import default_engine as _policy
from utils.tokenizer import tokenize

SYSTEM_LOG_PATH = "james_system_log.jsonl"


class RetrievalEngine:
    """
    Vector + BM25 하이브리드 검색 + Entity 추출 전담.
    reasoning_engine.py의 loop 각 단계에서 호출된다.
    """

    def __init__(self):
        from llm.router import RouterWrapper
        self.vector_store = VectorStore()
        self.llm          = RouterWrapper("extract")

    # ─── 로그 ───────────────────────────────────────────────

    @staticmethod
    def _log(step: str, error: Exception):
        entry = {
            "time":   datetime.now().isoformat(),
            "level":  "ERROR",
            "step":   f"retrieval_engine.{step}",
            "detail": str(error)[:300],
        }
        try:
            with open(SYSTEM_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ─── BM25 정규화 ─────────────────────────────────────────

    @staticmethod
    def _normalize_bm25(scores: list) -> list:
        import numpy as np
        if isinstance(scores, np.ndarray):
            scores = scores.tolist()
        if not scores:
            return []
        scores = [float(s) for s in scores]
        mn, mx = min(scores), max(scores)
        return [(s - mn) / (mx - mn) for s in scores] if mx - mn > 0 else [0.0] * len(scores)

    # ─── Hybrid Search ───────────────────────────────────────

    def hybrid_search(
        self,
        question: str,
        top_k: int = 8,
        user_role: str = "external",
        source_type: Optional[str] = None,  # [P4.5-2] 'prod' / 'test' / None
    ) -> List[Dict]:
        """
        Vector(0.6) + BM25(0.2) + keyword(0.1) + name(0.1) 하이브리드 검색.

        [P4.5-2] source_type 필터: 'prod'이면 프로덕션 데이터만 검색.
        ABAC 필터: user_role 기준 민감도 체크.
        """
        try:
            vec_results = self.vector_store.search(question, top_k=top_k)
        except Exception as e:
            self._log("vector_search", e)
            return []

        if not vec_results:
            return []

        # [P4.5-2] source_type 필터
        if source_type:
            vec_results = [
                r for r in vec_results
                if r.get("metadata", {}).get("source_type", "prod") == source_type
            ]

        # ABAC 필터 — #44 phase 2-A: routed through PolicyEngine.can_retrieve
        # so future policy changes touch one file (core/policy_engine.py) instead
        # of every retrieval call site. PolicyEngine.can_retrieve currently
        # delegates to security_layer.check_access bit-for-bit (#50).
        vec_results = [
            r for r in vec_results
            if _policy.can_retrieve(user_role, r.get("metadata", {"sensitivity": "internal"})).allowed
        ]

        if not vec_results:
            return []

        for r in vec_results:
            r["vector_score"] = float(r.get("score", 0))

        # BM25
        try:
            tq    = tokenize(question)
            bm25  = BM25Okapi([tokenize(r["text"]) for r in vec_results])
            bm_sc = self._normalize_bm25(bm25.get_scores(tq))
        except Exception as e:
            self._log("bm25", e)
            bm_sc = [0.0] * len(vec_results)

        # keyword score
        qw     = set(tokenize(question))
        kw_raw = [len(qw & set(tokenize(r["text"]))) for r in vec_results]
        max_kw = max(kw_raw) if kw_raw else 1
        kw_sc  = [k / max_kw if max_kw > 0 else 0.0 for k in kw_raw]

        # name score
        names  = [w for w in tokenize(question) if 2 <= len(w) <= 4]
        nm_raw = []
        for r in vec_results:
            dw = set(tokenize(r["text"]))
            nm_raw.append(sum(1 if n in dw else 0.5 if n in r["text"] else 0 for n in names))
        max_nm = max(nm_raw) if nm_raw else 1
        nm_sc  = [n / max_nm if max_nm > 0 else 0.0 for n in nm_raw]

        # 통합 점수
        merged = []
        for i, r in enumerate(vec_results):
            v  = r["vector_score"]
            b  = float(bm_sc[i]) if i < len(bm_sc) else 0.0
            k  = float(kw_sc[i])
            n  = float(nm_sc[i])
            merged.append({
                **r,
                "score":         0.6 * v + 0.2 * b + 0.1 * k + 0.1 * n,
                "vector_score":  v,
                "bm25_score":    b,
                "keyword_score": k,
                "name_score":    n,
            })

        return sorted(merged, key=lambda x: x["score"], reverse=True)

    # ─── Entity 추출 ─────────────────────────────────────────

    def extract_entities(
        self,
        query: str,
        docs: List[str],
        timeout: int = 30,
    ) -> List[Dict]:
        """LLM JSON 추출 + rule-based fallback"""
        prompt   = self._build_entity_prompt(query, docs)
        from llm.router import call_router
        response = call_router(
            prompt, task_type="extract", use_cache=True, timeout=timeout,
        )

        print(f"[DEBUG] entity raw: {response[:200] if response else '(empty)'}")

        try:
            entities = self._safe_json_load(response)
        except Exception as e:
            self._log("entity_parse", e)
            entities = []

        if not entities:
            entities = self._rule_based_fallback(query)

        return entities if isinstance(entities, list) else []

    def _build_entity_prompt(self, query: str, docs: List[str]) -> str:
        safe_docs  = [self._sanitize(d, 300) for d in docs[:3]]
        safe_query = self._sanitize(query, 500)
        return (
            "You are an entity extraction system.\n"
            "Output ONLY valid JSON array. No explanation.\n\n"
            'Format: [{"name": "entity_name", "type": "person|org|concept|document"}]\n\n'
            f"Question:\n{safe_query}\n\n"
            f"Context:\n{chr(10).join(safe_docs)}\n\n"
            "JSON:"
        )

    @staticmethod
    def _safe_json_load(text: str) -> Any:
        if not isinstance(text, str):
            return []
        text = text.strip()
        text = re.sub(r'[^a-zA-Z0-9가-힣\[\]{},:"_\-\.\n\t ]', "", text)
        if not text.startswith("["):
            idx = text.find("[")
            if idx < 0:
                return []
            text = text[idx:]
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"\[.*?\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return []

    def _rule_based_fallback(self, query: str) -> List[Dict]:
        stopwords = {"무엇", "무엇을", "어떤", "하는", "공부", "인가", "은", "는", "을", "를"}
        fallback, seen = [], set()
        for word in re.findall(r"[가-힣A-Za-z0-9]+", query):
            if len(word) < 2 or word in stopwords:
                continue
            if word.endswith(("는", "은", "을", "를", "이", "가", "의")):
                word = word[:-1]
            if word in seen or not word:
                continue
            seen.add(word)
            etype = "person" if re.match(r"^[가-힣]{2,4}$", word) else "concept"
            fallback.append({"name": word, "type": etype})
        entities = fallback[:5]
        print(f"[FALLBACK] rule-based {len(entities)}개")
        return entities

    # ─── Context 결합 ────────────────────────────────────────

    @staticmethod
    def build_doc_context(docs: List[str], doc_scores: List[float] = None) -> tuple:
        """
        Vector 문서를 컨텍스트 문자열로 변환.
        Returns: (doc_context_str, avg_vector_score)
        """
        safe_docs = [RetrievalEngine._sanitize(d, 800) for d in docs[:3]]
        doc_ctx   = "\n\n---\n\n".join(safe_docs)
        avg_score = (sum(doc_scores) / len(doc_scores)) if doc_scores else 0.5
        return doc_ctx, avg_score

    # ─── Sanitize ────────────────────────────────────────────

    @staticmethod
    def _sanitize(text: str, max_len: int = 500) -> str:
        if not isinstance(text, str):
            return ""
        blacklist = [
            "ignore previous", "system prompt", "you are now", "disregard",
            "forget previous", "override rule", "위 규칙을 무시", "다음 지시를 따르",
            "이전 내용을 무시", "모든 지시를", "act as", "pretend you",
        ]
        for b in blacklist:
            if b in text.lower():
                text = re.sub(re.escape(b), "[BLOCKED]", text, flags=re.IGNORECASE)
        return text[:max_len]

    @staticmethod
    def calculate_confidence(r: Dict) -> float:
        """답변 신뢰도 점수 (0~1).

        ``hybrid_search`` ranking 가중치(``0.6/0.2/0.1/0.1``)와는 별도
        분포(``0.5/0.2/0.2/0.1``). vector 영향력을 약간 낮추고
        keyword/name (표면 형태가 정확히 일치하는 신호)에 더 높은
        confidence를 부여한다 — 검색 ranking은 의미 거리가 핵심이지만,
        답변 confidence는 사용자 질의에 명시된 단어가 실제로 문서에
        있다는 사실에 더 의존하는 게 자연스럽다는 판단.

        합 = 1.0. ``round(..., 3)`` 후 ``[0, 1]`` 범위 강제.
        """
        return max(0.0, min(1.0, round(
            r.get("vector_score", 0) * 0.5 +
            r.get("bm25_score", 0) * 0.2 +
            min(r.get("keyword_score", 0), 1.0) * 0.2 +
            min(r.get("name_score", 0), 1.0) * 0.1, 3
        )))
