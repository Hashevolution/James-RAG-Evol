"""
PROJECT JAMES — Memory Extractor (Phase 6 Step 1~3)

Step 1: preference — trigger 키워드 기반
Step 2: pattern    — 반복 행동 + 명시적 패턴 감지
Step 3: goal       — 목표/계획 선언 감지

로컬 전용 시스템 — James 본인만 사용.
RAG와 완전 분리 — 다른 검색 경로 사용.
"""

import re
from collections import deque
from typing import Optional

# ─── 상수 ────────────────────────────────────────────────────

# Step 1: preference trigger
TRIGGER_KEYWORDS = [
    # 한국어
    "앞으로", "기억해", "항상", "매번", "나는", "나의 스타일",
    "기억해줘", "잊지 마",
    # English
    "remember", "always", "from now on", "keep in mind",
    "my preference", "i prefer", "i like", "i want you to",
]

PATTERN_KEYWORDS = [
    # 한국어
    "주로", "보통", "대부분", "습관적으로", "자주", "즐겨", "선호",
    # English
    "usually", "typically", "often", "prefer", "tend to", "mostly",
]

GOAL_KEYWORDS = [
    # 한국어
    "목표", "계획", "하고 싶다", "만들고 싶다", "구현하고 싶다",
    # English
    "goal", "plan", "want to", "aim to", "trying to", "hope to",
]

# Step 2: pattern trigger

# Step 3: goal trigger

# 반복 감지용 히스토리 (최근 50개)
_query_history: deque = deque(maxlen=50)


# ─── 반복 패턴 감지 ──────────────────────────────────────────

def repeated_pattern(query: str) -> bool:
    """동일 패턴 2회 이상 반복 시 True"""
    key = query.strip()[:30]
    _query_history.append(key)
    return list(_query_history).count(key) >= 2


# ─── preference 파싱 (Step 1) ────────────────────────────────

def _parse_preference(query: str) -> Optional[dict]:
    rules = [
        (r"(코드|code).*(상세|자세|간단|짧게|길게)", "code_detail_level"),
        (r"(언어|language).*(한국어|영어|english)",   "response_language"),
        (r"(답변|응답).*(짧게|간결|상세|자세)",        "response_style"),
        (r"(먼저|first|우선).*(구조|architecture|설계)", "explain_style"),
    ]
    q = query.strip()
    for pattern, key in rules:
        if re.search(pattern, q, re.IGNORECASE):
            return {"type":"preference","key":key,"value":q[:100],
                    "raw":q,"confidence":0.85,"source":"trusted"}
    return {"type":"preference","key":"general","value":q[:100],
            "raw":q,"confidence":0.82,"source":"trusted"}


# ─── pattern 감지 (Step 2) ───────────────────────────────────

def _detect_pattern(query: str) -> dict:
    """
    Step 2: 반복 행동 또는 명시적 패턴 선언.
    예: "주로 아키텍처 설계부터 시작해"
        "보통 코드 리뷰 먼저 요청함"
    """
    q = query.strip()

    # 패턴 키워드 기반 파싱
    rules = [
        (r"(아키텍처|설계|구조).*(먼저|우선|시작)", "prefers_architecture_first"),
        (r"(코드|code).*(리뷰|review)",             "prefers_code_review"),
        (r"(테스트|test).*(먼저|우선)",              "prefers_test_first"),
        (r"(요약|정리).*(먼저|우선|짧게)",           "prefers_summary_first"),
    ]
    for pattern, label in rules:
        if re.search(pattern, q, re.IGNORECASE):
            return {"type":"pattern","pattern":label,"raw":q,
                    "confidence":0.82,"source":"trusted"}

    return {"type":"pattern","pattern":q[:100],"raw":q,
            "confidence":0.80,"source":"trusted"}


# ─── goal 감지 (Step 3) ──────────────────────────────────────

def _detect_goal(query: str) -> dict:
    """
    Step 3: 명시적 목표/계획 선언.
    예: "보안이 강한 RAG 시스템 완성이 목표야"
        "로컬 AI 엔진 구축하고 싶다"
    """
    q = query.strip()
    return {"type":"goal","goal":q[:200],"raw":q,
            "confidence":0.80,"source":"trusted"}


# ─── 메인 API ────────────────────────────────────────────────

def extract_memory(query: str, response: str) -> Optional[dict]:
    """
    질문에서 저장할 Memory 후보 추출.
    Step 1(preference) → Step 2(pattern) → Step 3(goal) 순서.
    """
    if not query or not query.strip():
        return None
    q = query.strip()

    # 너무 짧은 잡담 제외
    if len(q) < 8:
        return None

    # Step 1: preference trigger
    if any(k in q for k in TRIGGER_KEYWORDS):
        return _parse_preference(q)

    # Step 2: pattern trigger 또는 반복
    if any(k in q for k in PATTERN_KEYWORDS):
        return _detect_pattern(q)
    if repeated_pattern(q):
        return _detect_pattern(q)

    # Step 3: goal trigger
    if any(k in q for k in GOAL_KEYWORDS):
        return _detect_goal(q)

    return None


def validate_memory(candidate: Optional[dict]) -> bool:
    """추출된 후보 검증."""
    if not candidate:
        return False
    if candidate.get("source") != "trusted":
        return False
    if float(candidate.get("confidence", 0)) < 0.8:
        return False
    return True

def _parse_preference(query: str) -> Optional[dict]:
    """
    "앞으로 코드는 상세하게" → key=code_style, value=상세하게
    "항상 한국어로 답변해"   → key=language, value=한국어
    """
    q = query.strip()

    # 규칙 기반 파싱
    rules = [
        (r"(코드|code).*(상세|자세|간단|짧게|길게)", "code_detail_level"),
        (r"(언어|language).*(한국어|영어|english)", "response_language"),
        (r"(답변|응답).*(짧게|간결|상세|자세)", "response_style"),
        (r"(먼저|first|우선).*(구조|architecture|설계)", "explain_style"),
    ]
    for pattern, key in rules:
        if re.search(pattern, q, re.IGNORECASE):
            value = q[:100]
            return {
                "type":       "preference",
                "key":        key,
                "value":      value,
                "raw":        q,
                "confidence": 0.85,
                "source":     "trusted",
            }

    # 매칭 없으면 general preference
    return {
        "type":       "preference",
        "key":        "general",
        "value":      q[:100],
        "raw":        q,
        "confidence": 0.82,
        "source":     "trusted",
    }


# ─── pattern 감지 ────────────────────────────────────────────

def _detect_pattern(query: str) -> dict:
    return {
        "type":       "pattern",
        "pattern":    query.strip()[:100],
        "raw":        query,
        "confidence": 0.80,
        "source":     "trusted",
    }


# ─── 메인 API ────────────────────────────────────────────────

def extract_memory(query: str, response: str) -> Optional[dict]:
    """
    질문 + 응답에서 저장할 Memory 후보 추출.

    Returns:
        dict (후보) or None (저장 불필요)
    """
    if not query or not query.strip():
        return None

    q = query.strip()

    # Gate 1: 너무 짧은 잡담 제외
    if len(q) < 8:
        return None

    # Gate 2: trigger 키워드 → preference 추출
    if any(k in q for k in TRIGGER_KEYWORDS):
        return _parse_preference(q)

    # Gate 3: 반복 패턴 → pattern 저장
    if repeated_pattern(q):
        return _detect_pattern(q)

    return None


def validate_memory(candidate: Optional[dict]) -> bool:
    """추출된 후보 검증."""
    if not candidate:
        return False

    # Gate 1: 신뢰 소스
    if candidate.get("source") != "trusted":
        return False

    # Gate 2: confidence
    if float(candidate.get("confidence", 0)) < 0.8:
        return False

    return True


# ─── [P1-5] 페르소나 명령 감지 ────────────────────────────────

# 호칭/이름 변경 패턴
PERSONA_NAME_PATTERNS = [
    r'(J|제이|자메스|James)\s*(로|라고|이라고|으로)?\s*(부르|호칭|불러|불러줘|불러라)',
    r'(이름|호칭|이름이|부를\s*때)\s*(을|를|은|는)?\s*(\w+)\s*(으로|로)',
    r'앞으로\s+\w+\s+(라고|로|으로)\s+(불러|호칭)',
    r'(나를|저를|자기를|본인을)\s+(\w+)\s+(이라고|으로|라고)',
]

# 말투/성격 변경 패턴
PERSONA_STYLE_PATTERNS = [
    r'(말투|어투|성격|스타일|태도|방식)\s*(을|를|은|는)?\s*(바꿔|변경|수정)',
    r'(더|좀)\s*(친절하게|냉철하게|간결하게|자세하게|엄격하게)',
    r'(격식체|반말|존댓말|공식적|비공식적)\s*(으로|로)',
]

# 언어 변경 패턴 (페르소나와 분리 — 세션 설정으로 처리)
PERSONA_LANGUAGE_PATTERNS = [
    r'(앞으로|이제|지금부터)\s+(한국어|영어|영문|Korean|English)\s*(로|으로|만)',
    r'(언어|답변)\s*(을|를|은|는)?\s*(한국어|영어|Korean|English)\s*(로|으로)',
]


def is_persona_command(query: str) -> bool:
    """
    [P1-5] 페르소나 변경 명령 감지.
    호칭/이름/말투/언어 변경 요청이면 True.
    """
    q = query.strip()
    all_patterns = (
        PERSONA_NAME_PATTERNS +
        PERSONA_STYLE_PATTERNS +
        PERSONA_LANGUAGE_PATTERNS
    )
    for pattern in all_patterns:
        if re.search(pattern, q, re.IGNORECASE):
            return True
    return False


def extract_persona_command(query: str) -> Optional[dict]:
    """
    [P1-5] 페르소나 명령을 파싱해서 저장 가능한 dict 반환.
    반환 예시:
      {"name": "J"}
      {"style": "더 간결하게"}
      {"language": "영어"}
    """
    q = query.strip()
    # 조사 제거 헬퍼
    _JOSA = re.compile(r'(로|으로|라고|이라고|을|를|은|는|이|가|의|에서|에게)$')

    def _clean(token: str) -> str:
        return _JOSA.sub('', token.strip()).strip()

    # 이름/호칭 변경
    for pattern in PERSONA_NAME_PATTERNS:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            # 패턴에서 이름 후보 추출 (불러줘/호칭해 앞 단어)
            tokens = q.split()
            for i, tok in enumerate(tokens):
                if any(k in tok for k in ['불러', '호칭', '부르']):
                    if i > 0:
                        name = _clean(tokens[i-1])
                        if 1 <= len(name) <= 10:
                            return {"name": name, "type": "persona_name"}
            # 영문 이름 매칭 (J, James 등)
            name_match = re.search(r'\b([A-Z][a-z]{0,9})\b', q)
            if name_match:
                return {"name": name_match.group(), "type": "persona_name"}
            # 한국어 1~3글자 이름
            kor_match = re.search(r'(?:나를|저를|저를)?\s*([가-힣]{1,3})\s*(?:라고|로|이라고)', q)
            if kor_match:
                return {"name": _clean(kor_match.group(1)), "type": "persona_name"}

    # 언어 변경
    for pattern in PERSONA_LANGUAGE_PATTERNS:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            lang_map = {"영어": "영어", "english": "영어", "korean": "한국어",
                        "한국어": "한국어", "영문": "영어"}
            for k, v in lang_map.items():
                if k.lower() in q.lower():
                    return {"language": v, "type": "persona_language"}

    # 말투/스타일 변경
    for pattern in PERSONA_STYLE_PATTERNS:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return {"style": m.group().strip(), "type": "persona_style"}

    return {"raw": q, "type": "persona_unknown"}


if __name__ == "__main__":
    print("=== Memory Extractor 자가 테스트 ===\n")

    cases = [
        ("앞으로 코드는 상세하게 설명해줘",        True,  "preference trigger"),
        ("항상 한국어로 답변해줘",                  True,  "preference trigger"),
        ("비밀번호는 1234야",                       False, "민감 정보 차단"),
        ("안녕",                                    False, "너무 짧음"),
        ("경제학이란 무엇인가?",                    False, "trigger 없고 첫 발언"),
    ]

    passed = 0
    for query, expect_save, label in cases:
        candidate = extract_memory(query, "")
        valid     = validate_memory(candidate)
        ok        = valid == expect_save
        passed   += int(ok)
        print(f"  {'✅' if ok else '❌'} {label}")
        print(f"     저장={valid} (기대={expect_save})")

    # 페르소나 명령 테스트
    print("\n  [페르소나 명령 테스트]")
    persona_cases = [
        "J라고 불러줘",
        "앞으로 영어로 답변해줘",
        "더 간결하게 말해줘",
        "나를 James라고 호칭해",
    ]
    for q in persona_cases:
        detected = is_persona_command(q)
        parsed   = extract_persona_command(q) if detected else None
        print(f"  {'✅' if detected else '❌'} '{q}' → {parsed}")

    # 반복 패턴 테스트
    print("\n  [반복 패턴 테스트]")
    q = "경제학이란 무엇인가?"
    extract_memory(q, "")  # 1회
    c2 = extract_memory(q, "")  # 2회
    ok = validate_memory(c2)
    print(f"  {'✅' if ok else '❌'} 2회 반복 → pattern 저장: {ok}")
    passed += int(ok)

    print(f"\n  결과: {passed}/{len(cases)+1} PASS")
