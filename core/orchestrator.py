"""
PROJECT JAMES - Retrieval Orchestrator (Phase 5)

역할: multi-path 수집 후 단순 merge. 그 이상 없음.

절대 제약:
  ❌ reranker 금지
  ❌ 새로운 scoring 로직 금지
  ❌ LLM 호출 금지
  ✅ 단순 merge만 (중복 제거 포함)
  ✅ 기존 hybrid_search 그대로 호출
  ✅ doc_id 기준 단순 중복 제거만
  ✅ 점수 재계산 없음, 순서 변경 없음
"""

import json
import re
from datetime import datetime
from typing import List, Dict, Optional

SYSTEM_LOG_PATH = "james_system_log.jsonl"


def _log(step: str, detail: str):
    entry = {"time": datetime.now().isoformat(), "level": "INFO",
             "step": f"orchestrator.{step}", "detail": detail[:200]}
    try:
        with open(SYSTEM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Phase 2: mirror to SQLite (see core/audit_bridge.py).
    try:
        from core.audit_bridge import mirror_system_event
        mirror_system_event(entry)
    except Exception:
        pass


def _extract_keywords(query: str) -> str:
    """
    쿼리에서 핵심 키워드만 추출 (LLM 없음).
    조사 제거 + 2글자 이상 단어만 유지.
    """
    stopwords = {"은","는","이","가","을","를","의","에","와","과","도","만",
                 "인가","무엇","어떤","하는","한다","합니다","이란","란"}
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", query)
    keywords = [t for t in tokens if len(t) >= 2 and t not in stopwords]
    return " ".join(keywords[:8])   # 최대 8개 키워드


def _make_doc_id(result: Dict) -> str:
    """중복 판단용 ID 생성 (source + 텍스트 앞 50자)"""
    source = result.get("source", "")
    text   = result.get("text", "")[:50]
    return f"{source}::{text}"


def deduplicate(results: List[Dict]) -> List[Dict]:
    """
    doc_id 기준 단순 중복 제거.

    규칙:
    - 동일 doc_id → 첫 번째 것만 유지
    - 점수 재계산 없음
    - 순서 변경 없음
    """
    seen    = set()
    deduped = []
    for r in results:
        did = _make_doc_id(r)
        if did not in seen:
            seen.add(did)
            deduped.append(r)
    return deduped


def retrieve(
    original_query:  str,
    expanded_query:  str,
    hybrid_search_fn,           # 기존 RetrievalEngine.hybrid_search 함수 참조
    user_role:       str  = "external",
    source_type:     Optional[str] = "prod",
    top_k:           int  = 8,
) -> List[Dict]:
    """
    multi-path 수집 → 단순 merge → dedup.

    Path:
      1. original_query  → hybrid_search
      2. expanded_query  → hybrid_search (query_expander 성공 시 다름, 실패 시 동일)
      3. keyword_query   → hybrid_search

    결과 merge: 단순 concat → deduplicate
    ❌ rerank 없음 / ❌ 점수 재계산 없음 / ❌ 순서 변경 없음
    """
    queries = [
        ("original",  original_query),
        ("expanded",  expanded_query),
        ("keyword",   _extract_keywords(original_query)),
    ]

    # expanded == original인 경우 중복 쿼리 제거
    seen_queries, unique_queries = set(), []
    for label, q in queries:
        q_clean = q.strip()
        if q_clean and q_clean not in seen_queries:
            seen_queries.add(q_clean)
            unique_queries.append((label, q_clean))

    all_results: List[Dict] = []

    for label, q in unique_queries:
        try:
            results = hybrid_search_fn(
                q,
                top_k=top_k,
                user_role=user_role,
                source_type=source_type,
            )
            print(f"[ORCH] {label:10s}: '{q[:30]}' → {len(results)}개")
            all_results.extend(results)
        except Exception as e:
            _log("search_error", f"path={label} error={e}")
            print(f"[ORCH] ⚠️ {label} 검색 실패: {e}")

    # 단순 중복 제거만 (점수/순서 변경 없음)
    deduped = deduplicate(all_results)

    _log("retrieve_done",
         f"paths={len(unique_queries)} raw={len(all_results)} deduped={len(deduped)}")
    print(f"[ORCH] merge 완료: raw={len(all_results)} → deduped={len(deduped)}")

    return deduped


# ─── 자가 테스트 ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Orchestrator 자가 테스트 ===\n")

    # mock hybrid_search
    call_count = [0]
    def mock_search(q, top_k=8, user_role="external", source_type="prod"):
        call_count[0] += 1
        return [
            {"text": f"문서A about {q[:10]}", "source": "doc_a.md", "score": 0.9},
            {"text": f"문서B about {q[:10]}", "source": "doc_b.md", "score": 0.8},
            {"text": "공통 문서",              "source": "common.md", "score": 0.7},
        ]

    # 테스트 1: 기본 retrieve
    results = retrieve(
        original_query="경제학이란 무엇인가?",
        expanded_query="경제학이란 무엇인가? 경제 학문 사회과학",
        hybrid_search_fn=mock_search,
    )
    print(f"  ✅ 결과 {len(results)}개 | 호출 횟수={call_count[0]}")
    assert len(results) > 0

    # 테스트 2: dedup — 동일 source 중복 제거
    dups = [
        {"text":"동일 텍스트","source":"a.md","score":0.9},
        {"text":"동일 텍스트","source":"a.md","score":0.9},
        {"text":"다른 텍스트","source":"b.md","score":0.8},
    ]
    deduped = deduplicate(dups)
    ok = len(deduped) == 2
    print(f"  {'✅' if ok else '❌'} dedup: {len(dups)}개 → {len(deduped)}개 (기대: 2)")

    # 테스트 3: expanded == original → 쿼리 중복 제거
    call_count[0] = 0
    retrieve(
        original_query="경제학",
        expanded_query="경제학",   # query_expander 실패 시 동일
        hybrid_search_fn=mock_search,
    )
    # original + keyword만 = 2회 (expanded 중복 제거)
    print(f"  {'✅' if call_count[0] <= 2 else '❌'} 중복 쿼리 제거: {call_count[0]}회 호출 (기대: ≤2)")

    # 테스트 4: 점수/순서 변경 없음 확인
    raw = [{"text":"A","source":"a","score":0.9},{"text":"B","source":"b","score":0.5}]
    d   = deduplicate(raw)
    ok4 = d[0]["score"] == 0.9 and d[1]["score"] == 0.5
    print(f"  {'✅' if ok4 else '❌'} 순서 유지: {[r['score'] for r in d]}")

    print("\n✅ Orchestrator 자가 테스트 완료")
