"""
PROJECT JAMES — Intent Classifier (Phase 7)

LLM이 사용자 의도를 파악해서 실행 모드를 결정.
키워드 방식의 한계를 극복하고 자연어 완전 이해를 구현.

지원 모드:
  chat        — 일상 대화, 인사, 자기소개
  retrieval   — 지식 검색, 정보 조회
  meta        — 내부 자료 인벤토리 ("어떤 자료가 있어?", "wiki 목록")
  coding      — 코드 작성, 버그 수정, 프로그래밍
  wiki_edit   — 지식 수정, 삭제, 추가 (admin 전용)
  agent       — 자동화, 반복 작업, 멀티스텝 실행 (확장 예정)
  self_evolve — 자메스 자체 개선, 기능 추가 (확장 예정)
  app_dev     — 앱/UI 개발, 서비스 설계 (확장 예정)

설계 원칙:
  - 빠른 응답 (타임아웃 10초, 짧은 프롬프트)
  - fallback: LLM 실패 시 키워드 방식으로 복귀
  - 보안: 권한 없는 모드는 강제 차단
"""

import re
import time
from typing import Optional, Tuple

# Fast-path regex tables (rule-#5 split → core/intent_fast_patterns.py).
from core.intent_fast_patterns import FAST_PATTERNS

# ─── 모드 정의 ───────────────────────────────────────────────

# 현재 활성화된 모드
ACTIVE_MODES = {
    "chat",
    "retrieval",
    "meta",          # 내부 wiki 인벤토리 질의 — "어떤 자료가 있어?" 류
    "coding",
    "wiki_edit",
    "self_evolve",   # [P7] 자기 인식/진화 활성화
    "vision",        # [v18.7] 이미지→텍스트 (handle_vision); image_path
                     # 첨부 또는 명시 override 로만 진입 (텍스트 라우터 X).
}

# 미래 확장 예정 모드 (현재는 fallback 처리)
FUTURE_MODES = {
    "agent",
    "app_dev",
}

# role별 허용 모드
ROLE_ALLOWED = {
    "admin":    ACTIVE_MODES | FUTURE_MODES,
    "manager":  {"chat", "retrieval", "meta", "coding", "vision"},
    "employee": {"chat", "retrieval", "meta", "coding", "vision"},
    # external sees meta too — listing entity *names* leaks no
    # ABAC-protected content (the read still goes through retrieval +
    # role filter). The list itself is the kind of inventory question
    # a new external user typically asks first.
    "external": {"chat", "retrieval", "meta"},
}


# ─── LLM 의도 분류기 ─────────────────────────────────────────

class IntentClassifier:
    """
    LLM 기반 의도 분류기.

    사용 흐름:
      1. classify_fast()  → 명확한 패턴 즉시 분류 (LLM 호출 없음)
      2. classify_llm()   → 불명확한 경우 LLM으로 분류
      3. classify()       → 위 두 단계를 자동으로 선택
    """

    # 즉시 분류 가능한 명확 패턴 (LLM 불필요). 패턴 테이블은 rule-#5
    # 분할로 core/intent_fast_patterns.py 로 이동 — self.FAST_PATTERNS
    # 는 그 모듈 dict 를 가리킨다 (byte-identical).
    FAST_PATTERNS = FAST_PATTERNS

    # LLM 분류 프롬프트
    CLASSIFY_PROMPT = """당신은 사용자 의도를 분류하는 AI입니다.
아래 사용자 발화를 읽고, 가장 적합한 모드를 딱 하나만 선택하세요.

[모드 정의]
- chat:        일상 대화, 인사, 자기소개 질문
- retrieval:   정보 검색, 지식 조회 (특정 주제에 대한 사실)
- meta:        보유한 내부 자료 *목록* 자체에 대한 질의
               ("어떤 자료가 있어?", "wiki 목록 보여줘", "내부 데이터 리스트")
- coding:      코드 작성/수정/분석/버그 수정
- wiki_edit:   지식 수정/추가/삭제 ("틀렸어", "수정해", "삭제해", "추가해", "바꿔", "고쳐")
- self_evolve: 자메스 자신의 코드/구조 분석, 자기 인식, 자기 개선
               ("네 코드 파악해봐", "구조 분석해", "스스로 개선해봐",
                "어떤 파일로 구성됐어", "너 자신을 분석해봐")
- agent:       자동화, 반복 작업, 멀티스텝 실행 (미구현)
- app_dev:     앱/서비스 개발 설계 (미구현)

[판단 기준]
- 보유 자료 인벤토리 질의 → meta (내용 X, 목록 자체 O)
- 수정/변경/삭제/추가 의도 → wiki_edit
- "틀렸어", "잘못됐어", "다시 써", "바꿔", "고쳐" → wiki_edit
- 코드/프로그래밍 관련 → coding
- 자메스 자신(코드, 구조, 파일, 기능)에 대한 분석 → self_evolve
- 특정 주제에 대한 정보 요청 → retrieval
- 대화 → chat

[meta vs retrieval 구분]
- "BlackRock 정보 알려줘" → retrieval (특정 주제)
- "어떤 회사 정보가 있어?" → meta (목록 자체)

[사용자 발화]
{query}

[출력 규칙]
반드시 아래 중 하나만 출력 (다른 말 금지):
chat / retrieval / meta / coding / wiki_edit / self_evolve / agent / app_dev"""

    def __init__(self, llm_client=None):
        self._llm = llm_client   # GemmaClient 인스턴스 (lazy)

    def _get_llm(self):
        if self._llm is None:
            try:
                from llm.router import RouterWrapper
                self._llm = RouterWrapper("classify")
            except Exception:
                pass
        return self._llm

    # ─── Specific-topic guard (item #5, 2026-05-08) ───────────────
    # User reported "팔란티어에 대해 어떤 자료가 있지?" routes to
    # meta (full wiki list) when they actually wanted retrieval
    # (Palantir-specific content). The meta patterns catch any
    # query with "어떤 자료" / "어떤 정보" / "내부 자료" type phrasings.
    # When a specific topic prefix is present (X에 대해 / X 관련 /
    # X의 자료), meta routing is wrong — fall through to retrieval.
    #
    # Generic data nouns (wiki / 자료 / 데이터 / 내부 / entity / etc.)
    # don't count as specific topics — those still route to meta.
    _GENERIC_DATA_NOUNS = {
        "wiki", "위키", "자료", "문서", "데이터", "내부",
        "entity", "엔티티", "knowledge", "정보", "것", "거",
        "내용", "기록", "보유", "저장된", "전체", "모든",
        "data", "info", "files", "documents",
    }

    def _has_specific_topic_prefix(self, q: str) -> bool:
        """True if the query has a specific-topic prefix that should
        override meta routing.

        Patterns recognised:
          - "X에 대해" / "X에 관해" / "X에 관한" / "X에서"
          - "X 관련" / "X관련"
          - "X의 (자료|문서|데이터|정보|내용)" — genitive + data noun
          - Topic noun X must NOT be in _GENERIC_DATA_NOUNS — a
            "wiki에 대해 어떤 자료" still routes to meta.
        """
        m = re.search(
            r"(\S+?)\s*("
            r"에\s*(대해|관해|관한|에서)"           # X에 대해/관해/...
            r"|관련(된)?"                            # X 관련(된)
            r"|의\s+(자료|문서|데이터|정보|내용|기록)"  # X의 자료/정보/...
            r")",
            q,
        )
        if not m:
            return False
        topic = m.group(1).strip().lower()
        # Strip Korean particles attached to the noun.
        topic = re.sub(r"(은|는|이|가|을|를|의|와|과)$", "", topic)
        if not topic:
            return False
        # Generic-data nouns don't count — those queries are still meta.
        return topic not in self._GENERIC_DATA_NOUNS

    def classify_fast(self, query: str) -> Optional[str]:
        """
        명확한 패턴은 LLM 없이 즉시 분류.
        불명확하면 None 반환 → classify_llm으로 위임.

        item #5: meta 패턴은 specific-topic 사전 검사 통과시에만
        매칭. "팔란티어에 대해 어떤 자료" 같은 specific-topic 질의는
        meta가 아닌 retrieval로 보내야 함.
        """
        q = query.lower().strip()
        skip_meta = self._has_specific_topic_prefix(q)

        for mode, patterns in self.FAST_PATTERNS.items():
            if skip_meta and mode == "meta":
                continue   # specific-topic 질의는 meta 우회
            for pat in patterns:
                if re.search(pat, q, re.IGNORECASE):
                    return mode

        return None   # 불명확 → LLM 필요

    def classify_llm(self, query: str, timeout: int = 10) -> str:
        """LLM으로 의도 분류 — 경량 옵션으로 빠르게."""
        llm = self._get_llm()
        if llm is None:
            return "retrieval"

        prompt = self.CLASSIFY_PROMPT.format(query=query[:200])

        try:
            t0  = time.time()
            # [P8-OPT] 분류는 경량 옵션으로 (num_predict=20, ctx=512)
            from llm.router import call_router
            try:
                from config import LLM_OPTIONS_FAST
                raw = call_router(
                    prompt, task_type="classify", timeout=timeout,
                    use_cache=False, options=LLM_OPTIONS_FAST,
                )
            except Exception:
                raw = call_router(
                    prompt, task_type="classify", timeout=timeout, use_cache=False,
                )

            elapsed = time.time() - t0

            if not raw:
                return "retrieval"

            # 응답에서 모드 추출
            raw_clean = raw.strip().lower().split()[0] if raw.strip() else ""
            raw_clean = re.sub(r'[^a-z_]', '', raw_clean)

            all_modes = ACTIVE_MODES | FUTURE_MODES
            if raw_clean in all_modes:
                print(f"[INTENT] LLM 분류: '{query[:30]}' → {raw_clean} ({elapsed:.2f}s)")
                return raw_clean

            # 응답이 모드명이 아닌 경우 — 텍스트에서 모드명 추출
            for mode in all_modes:
                if mode in raw.lower():
                    print(f"[INTENT] LLM 분류(추출): '{query[:30]}' → {mode} ({elapsed:.2f}s)")
                    return mode

            print(f"[INTENT] LLM 분류 실패 (raw: '{raw[:30]}') → retrieval")
            return "retrieval"

        except Exception as e:
            print(f"[INTENT] LLM 분류 오류: {e} → retrieval")
            return "retrieval"

    def classify(self, query: str, user_role: str = "external",
                 timeout: int = 10) -> Tuple[str, str]:
        """
        하이브리드 분류 (메인 함수).

        Returns:
            (mode, method)  — method: "fast" or "llm" or "fallback"
        """
        # 1. 빠른 패턴 분류 (LLM 없음)
        fast_mode = self.classify_fast(query)
        if fast_mode:
            final = self._enforce_role(fast_mode, user_role)
            return final, "fast"

        # 2. LLM 분류
        llm_mode = self.classify_llm(query, timeout=timeout)
        final    = self._enforce_role(llm_mode, user_role)
        return final, "llm"

    def _enforce_role(self, mode: str, user_role: str) -> str:
        """권한 없는 모드 → retrieval로 강제 변환."""
        allowed = ROLE_ALLOWED.get(user_role, {"chat", "retrieval"})

        if mode not in allowed:
            print(f"[INTENT] 권한 차단: {mode} (role={user_role}) → retrieval")
            return "retrieval"

        # 미래 모드는 현재 retrieval로 처리 (추후 활성화)
        if mode in FUTURE_MODES:
            print(f"[INTENT] 미래 모드 {mode} → retrieval (구현 예정)")
            return "retrieval"

        return mode


# ─── 싱글턴 ──────────────────────────────────────────────────

_classifier: Optional[IntentClassifier] = None


def get_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


def classify_intent(query: str, user_role: str = "external",
                    timeout: int = 10) -> Tuple[str, str]:
    """
    외부에서 호출하는 메인 함수.
    Returns: (mode, method)
    """
    return get_classifier().classify(query, user_role, timeout)
