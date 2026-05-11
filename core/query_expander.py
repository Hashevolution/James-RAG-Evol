"""
PROJECT JAMES — Query Expander (was: core/jepa_adapter.py)

역할: keyword 동의어 사전 기반 query 확장. **JEPA(Joint-Embedding
Predictive Architecture, LeCun)와 무관** — 모듈 이름이 학술 용어와
같았지만 실제 구현은 ``_SYNONYM_MAP`` 사전 lookup + 한국어 stopword
필터의 단순 keyword expansion이다. v0.2 정합성 정정에서 리네임
(`core.jepa_adapter` 는 deprecation shim).

절대 제약:
  ❌ reasoning 금지
  ❌ LLM 호출 금지
  ❌ Graph 접근 금지
  ❌ embedding 사용 금지 (이 모듈은 embedding을 만들지도 사용하지도 않는다)
  ✅ token hard limit 필수 (TOKEN_HARD_LIMIT=50)
  ✅ timeout 필수 (TIMEOUT_SEC=3.0)
  ✅ 실패 시 original query 그대로 반환
"""

import re
import time
import json
from datetime import datetime
from typing import Optional   # noqa: F401 — kept for downstream type hints

TOKEN_HARD_LIMIT = 50     # expanded token 최대
TIMEOUT_SEC      = 3.0    # 이 안에 못 끝내면 bypass

# Backward-compatibility aliases (v0.1.x downstream + tests still import these).
# 다음 마이너에서 제거 후보. 신규 코드는 위의 약식 이름 사용.
JEPA_TOKEN_HARD_LIMIT = TOKEN_HARD_LIMIT
JEPA_TIMEOUT_SEC      = TIMEOUT_SEC

SYSTEM_LOG_PATH = "james_system_log.jsonl"

# ─── 동의어 / 확장 사전 (keyword 기반, LLM 없음) ──────────

_SYNONYM_MAP = {
    # 학문
    "경제":    ["경제학", "경제 이론", "경제 분야"],
    "법":      ["법학", "법률", "법 이론"],
    "심리":    ["심리학", "심리 이론"],
    "물리":    ["물리학", "물리 이론"],
    "AI":      ["인공지능", "머신러닝", "딥러닝"],
    "인공지능": ["AI", "머신러닝", "딥러닝"],
    # 조직
    "회사":    ["기업", "조직", "법인"],
    "대학":    ["대학교", "학교", "교육기관"],
    # 관계
    "소속":    ["근무", "재직", "속한"],
    "공부":    ["학습", "연구", "전공"],
    "연구":    ["공부", "탐구", "분석"],
    # 일반
    "누구":    ["어떤 사람", "인물"],
    "무엇":    ["어떤 것", "어떤 분야"],
    "어디":    ["어느 곳", "어느 기관"],
}

_STOPWORDS = {
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과",
    "도", "만", "에서", "로", "으로", "이란", "란", "인가",
    "무엇", "어떤", "하는", "한다", "합니다", "했다", "인지",
}


def _log(step: str, detail: str, level: str = "INFO"):
    try:
        entry = {"time": datetime.now().isoformat(), "level": level,
                 "step": f"query_expand.{step}", "detail": detail[:200]}
        with open(SYSTEM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _tokenize_simple(text: str) -> list:
    """공백 + 한글 단어 분리 (LLM 없이)"""
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", text)
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 2]


def _expand_keywords(tokens: list) -> list:
    """동의어 사전 기반 확장 (LLM 없음)"""
    expanded = list(tokens)
    for token in tokens:
        synonyms = _SYNONYM_MAP.get(token, [])
        for syn in synonyms:
            if syn not in expanded:
                expanded.append(syn)
    return expanded


def _hard_truncate(tokens: list, limit: int = TOKEN_HARD_LIMIT) -> list:
    """token hard limit 강제 적용"""
    return tokens[:limit]


def expand(query: str) -> str:
    """
    query expansion only.

    성공: expanded_query 반환
    실패 / timeout / token 초과: original_query 반환

    절대 LLM 호출 없음. keyword 기반 확장만.
    """
    if not query or not query.strip():
        return query

    t_start = time.time()

    try:
        # 1단계: 토크나이징
        tokens = _tokenize_simple(query)
        if not tokens:
            return query

        # timeout 체크
        if time.time() - t_start > TIMEOUT_SEC:
            _log("timeout", f"tokenize 후 timeout | query={query[:50]}", "WARN")
            return query

        # 2단계: 확장
        expanded_tokens = _expand_keywords(tokens)

        # timeout 체크
        if time.time() - t_start > TIMEOUT_SEC:
            _log("timeout", f"expand 후 timeout | query={query[:50]}", "WARN")
            return query

        # 3단계: token hard limit 적용
        truncated = _hard_truncate(expanded_tokens, TOKEN_HARD_LIMIT)
        if len(truncated) < len(expanded_tokens):
            _log("truncated",
                 f"token 초과 {len(expanded_tokens)} → {len(truncated)}", "WARN")

        # 4단계: 원본 query + 확장 키워드 결합
        extra_terms = [t for t in truncated if t not in _tokenize_simple(query)]
        if not extra_terms:
            # 확장 없음 — 그러나 원본 자체가 token limit 초과 시 truncate
            orig_tokens = _tokenize_simple(query)
            if len(orig_tokens) > TOKEN_HARD_LIMIT:
                truncated_orig = orig_tokens[:TOKEN_HARD_LIMIT]
                print(f"[QUERY-EXPAND] 원본 hard truncate: {len(orig_tokens)} → {TOKEN_HARD_LIMIT} tokens")
                return " ".join(truncated_orig)
            return query   # 원본이 limit 이하면 그대로

        expanded_query = query + " " + " ".join(extra_terms[:10])

        # [TOKEN-HARD-LIMIT] 최종 출력 전체 token 수 강제 제한
        final_tokens   = _tokenize_simple(expanded_query)
        if len(final_tokens) > TOKEN_HARD_LIMIT:
            truncated_final = final_tokens[:TOKEN_HARD_LIMIT]
            expanded_query  = " ".join(truncated_final)
            print(f"[QUERY-EXPAND] hard truncate 적용: {len(final_tokens)} → {TOKEN_HARD_LIMIT} tokens")

        elapsed = time.time() - t_start
        _log("expand_ok",
             f"elapsed={elapsed:.3f}s tokens={len(truncated)} extra={len(extra_terms)}")

        print(f"[QUERY-EXPAND] expand: '{query[:40]}' → +{extra_terms[:5]}")
        return expanded_query

    except Exception as e:
        _log("expand_error", str(e), "WARN")
        print(f"[QUERY-EXPAND] ⚠️ 확장 실패 → 원본 사용: {e}")
        return query   # 실패 시 원본 반환


# ─── 자가 테스트 ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Query Expander 자가 테스트 ===\n")

    cases = [
        ("김철수는 경제학을 공부하는가?",    True),
        ("xkzq존재하지않는abc",              False),  # 확장 없음 → 원본
        ("",                                  False),
        ("AI 연구 기관은?",                   True),
    ]

    for query, expect_expanded in cases:
        result = expand(query)
        actually_expanded = result != query and bool(result)
        ok = actually_expanded == expect_expanded or not query
        icon = "✅" if ok else "❌"
        print(f"  {icon} '{query[:30]}' → '{result[:50]}'")
        if actually_expanded:
            extra = result.replace(query, "").strip()
            print(f"       확장어: {extra[:60]}")

    # timeout 테스트 (간접)
    import time as _t
    t = _t.time()
    r = expand("매우 긴 쿼리 " * 100)
    elapsed = _t.time() - t
    print(f"\n  timeout 테스트: elapsed={elapsed:.3f}s (< {TIMEOUT_SEC}s 기대)")
    print(f"  결과: {'✅ bypass 정상' if elapsed < 5 else '❌ 너무 느림'}")
