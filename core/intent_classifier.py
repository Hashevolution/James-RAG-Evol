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

# ─── 모드 정의 ───────────────────────────────────────────────

# 현재 활성화된 모드
ACTIVE_MODES = {
    "chat",
    "retrieval",
    "meta",          # 내부 wiki 인벤토리 질의 — "어떤 자료가 있어?" 류
    "coding",
    "wiki_edit",
    "self_evolve",   # [P7] 자기 인식/진화 활성화
}

# 미래 확장 예정 모드 (현재는 fallback 처리)
FUTURE_MODES = {
    "agent",
    "app_dev",
}

# role별 허용 모드
ROLE_ALLOWED = {
    "admin":    ACTIVE_MODES | FUTURE_MODES,
    "manager":  {"chat", "retrieval", "meta", "coding"},
    "employee": {"chat", "retrieval", "meta", "coding"},
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

    # 즉시 분류 가능한 명확 패턴 (LLM 불필요)
    FAST_PATTERNS = {
        "chat": [
            r"^(안녕|hi|hello|hey)\b",
            r"^(고마워|감사|ㅎㅎ|ㅋㅋ)\b",
            r"^.{1,3}$",                          # 3글자 이하
            r"^(remember|please remember|keep in mind|from now on)",
            r"^(i like|i prefer|i want|my name|my style)",
            # [STEP2-A FIX] 언어 변경 명령 → 반드시 chat (wiki_edit 오분류 방지)
            r"(영어|한국어|일본어|중국어|english|korean|japanese|chinese).{0,6}(로|으로|말해|해줘|답해|답변|바꿔|전환)",
            r"(다시|원래|이제).{0,6}(한국어|영어|korean|english)",
            r"^(영어로|한국어로|영어로만|한국어로만)\s*(말해|답해|해줘|해|줘)?$",
        ],
        "coding": [
            r"\b(python|파이썬|javascript|자바스크립트)\b",
            r"\b(def |class |import |traceback)\b",
            r"(코드 작성|코드 수정|버그 찾아|코드 만들어|스크립트)",
        ],
        "self_evolve": [
            r"(네|너|자메스).{0,10}(코드|파일|구조|기능).{0,10}(파악|분석|인식|확인)",
            r"(스스로|자신|자기).{0,10}(분석|개선|진화|파악)",
            r"(폴더|디렉토리).{0,10}(구조|확인|파악)",
            r"\w+\.py.{0,20}(분석|확인|읽어|봐|줘)",
        ],
        "wiki_edit": [
            r"(수정|변경|고쳐|바꿔)(해|봐|줘|라)",
            r"(삭제|지워|제거)(해|봐|줘|라)",
            r"(추가|더해|넣어)(해|봐|줘|라)",
            r"(로|으로)\s*(수정|변경|바꿔|고쳐)",
            r"(잘못|틀렸|틀렸어|잘못됐)",
        ],
        # Meta / inventory queries — "what do you have?", "list everything",
        # "wiki 목록", "내부 자료 보여줘". These previously fell through to
        # `retrieval` and produced hallucinated answers because the wiki
        # file *list* is not in any vector chunk. Now routed to handle_meta
        # which calls tools/wiki/wiki_editor.py::list_entities() directly.
        # Keep narrow — must combine an "inventory verb" with a wiki/data
        # noun, or be one of the canonical phrasings, so we don't hijack
        # legitimate retrieval like "BlackRock 목록 알려줘".
        "meta": [
            r"(wiki|위키|내부\s*자료|보유\s*자료|가지고\s*있는)\s*(목록|리스트|보여)",
            r"(어떤|무슨)\s*(자료|문서|wiki|위키|entity|엔티티).{0,15}(있|가지)",
            r"^(자료|문서|entity|엔티티)\s*(목록|리스트)\s*[?\.!]?$",
            r"(list|show)\s+(all\s+)?(entities|wiki|documents|files)",
            r"^what\s+do\s+you\s+(have|know\s+about)",
        ],
    }

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

    def classify_fast(self, query: str) -> Optional[str]:
        """
        명확한 패턴은 LLM 없이 즉시 분류.
        불명확하면 None 반환 → classify_llm으로 위임.
        """
        q = query.lower().strip()

        for mode, patterns in self.FAST_PATTERNS.items():
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
