"""PROJECT JAMES — AnswerStyleClassifier (cycle β #2, 2026-06-06)

답변 양식 자동 선택기 — Mother-platform 6 원칙의 원칙 6
("JAMES 가 단답 query 자동 파악 → 단답 specific 자동 장착 = Default
인정") 의 구현 layer.

What & Why
----------
사용자가 ``response_style`` 을 명시하지 않으면, query 의 intent 를
정량 인식해서 적절한 양식을 auto-mount:

  - 단답형 query (Who/What/When/Yes-No/짧은 entity 질의 등)
    → ``response_style="terse"`` auto-set → TERSE_PRESET 4 layer
      collapse (character / persona / sources_header / rule_text)
      + pipeline_synth P-1 (planner directive skip) + rule_text v2
      strict 가 자동 발동

  - 분석/보고서 query
    → ``response_style="natural"`` (production default 유지)
      → NATURAL_PRESET 의 보고서 양식 + ## sections 분기 그대로

advanced 스택 (planner / reflect / verify) 의 env-gate 와는 별도
axis — production Default 는 advanced ON 그대로 유지. 본 classifier
는 양식 layer 만 다룬다.

Design — IntentClassifier hybrid 패턴 미러
------------------------------------------
``core/intent_classifier.py`` 의 검증된 ``classify_fast`` (regex 70%) +
``classify_llm`` (LLM fallback 30%) hybrid 구조 그대로 사용. 검증된
패턴 = step7 14/14 = 100% 정확도 (`feedback_intent_classifier_audit_clean`).

API
---
- ``classify(query) -> (style, method)`` — 메인 entry
  - ``style`` = ``"terse"`` or ``"natural"``
  - ``method`` = ``"fast"`` / ``"llm"`` / ``"default"``
- ``classify_fast(query) -> Optional[str]`` — regex only
- ``classify_llm(query) -> str`` — LLM fallback
- ``classify_answer_style(query)`` — module-level convenience wrapper

사용자 explicit override
------------------------
호출 site 에서 사용자가 ``response_style="terse"`` 등 명시 시 본
classifier 를 우회 (wiring 위치 책임). 본 모듈 자체는 분류만 한다 —
override 결정은 caller 에게.
"""
from __future__ import annotations

import os
import re
import time
from typing import Optional, Tuple


class AnswerStyleClassifier:
    """양식 (terse / natural) 자동 분류기.

    Hybrid pipeline:
      1. ``classify_fast`` — regex 패턴 (no LLM)
      2. ``classify_llm`` — fast 미매치 시 LLM 분류
      3. fallback default → ``natural`` (안전 default)
    """

    # ── Fast patterns — 단답형 query 직접 catch ─────────────────────
    # 매치 시 → "terse". 매치 안 됨 → None (LLM fallback).
    #
    # 패턴 구성 근거:
    #   - Wh-fact question: Who/What/When/Where/Which/How many + be/aux
    #     ("Who is the CEO?", "What year was X founded?")
    #   - Yes/No question: 시작에 be/aux 동사 + entity
    #     ("Is Sam Bankman-Fried still in jail?", "Was the report on Oct 7?")
    #   - 단축 entity / 짧은 query: 매우 짧으면 단답 답
    #   - 한국어 단답 패턴: 누가/언제/어디/몇/얼마/어느 + 의문 종결
    #
    # NOT 단답 (early exit → None → LLM 분류 또는 natural default):
    #   - "compare X and Y" / "analyze X" / "evaluate X" / why / how
    #   - "비교/분석/평가/왜/어떻게/원인/방법"
    #   - "report on X" / "summarize X" / "보고서/요약/정리"
    # ── Fast patterns — explicit "give me the full detail" requests ──
    # Match → "detailed" (DETAILED_PRESET: reproduce the source content
    # in full — tables/numbers/items — instead of summarising). Checked
    # BEFORE terse/natural so "상세히 알려줘" / "원문 그대로" wins even if
    # the query also looks short. Operator catch 2026-06-26: an ingested
    # document's detail (a schedule table) was only ever summarised back.
    FAST_DETAILED_PATTERNS = [
        r"상세\s*(히|하게|한|하면|내용|정보|일정|하게요)",
        r"자세\s*(히|하게|한|하게요)",
        r"구체적(으로|인)",
        r"낱낱이|빠짐없이|하나도\s*빠짐없|모든\s*(내용|항목|정보|일정)",
        r"전체\s*(내용|일정|목록|표|텍스트|원문)",
        r"원문|원본|있는\s*그대로|그대로\s*(보여|알려|적어|읽어)",
        r"풀어서\s*(설명|알려|적어|보여)",
        r"\b(in\s+detail|full\s+detail|verbatim|word[\s\-]for[\s\-]word|"
        r"every\s+detail|full\s+text|the\s+(full|complete|entire)\s+"
        r"(list|table|schedule|content|text|details))\b",
    ]

    FAST_TERSE_PATTERNS = [
        # ── EN Wh-fact question (single-line answer expected) ──
        # "Who is the CEO?" / "What is X?" — directly Wh + copula
        r"^\s*(who|what|when|where|which|how many|how much|how old)\s+"
        r"(is|are|was|were|did|does|do|has|have|had)\b",
        # "What year was X founded?" / "Which company acquired Y?" /
        # "How many employees does Google have?" — Wh + intermediate
        # noun + verb. Second verb position is broad (\w+) to catch
        # past-tense action verbs ("acquired" / "founded") and
        # aux+main ("does have") that the copula-only first pattern
        # misses.
        r"^\s*(what|which|whose|how many|how much|how old)\s+\w+\s+\w+",
        # ── EN Yes/No question — starts with copula/auxiliary ──
        r"^\s*(is|are|does|do|did|was|were|has|have|had|can|could|"
        r"should|would|will)\s+\S+",
        # ── EN "Name the/Identify the" 류 ──
        r"^\s*(name|identify|list)\s+the\b",
        # ── KO Wh-fact question — interrogative + verb ending ──
        # "이 사건이 언제 일어났나요?" / "누가 했나?" / "어디 갔어?"
        r"(누가|누구|언제|어디|어느|몇|얼마)\S*\s*(인가|입니까|이야|이지|"
        r"맞|이죠|이에요|예요|일까|일까요|이지요|"
        r"있나|있어|있나요|"
        r"\S*나요|\S*나|\S*어|\S*야|\S*죠|"
        r"\S*었나요|\S*았나요|\S*했나요|\S*했어|\S*했나|\S*됐나)?"
        r"[\?\.\s]*$",
        # ── KO Yes/No question — 끝에 "맞나/그래/입니까/맞아요" ──
        r"(맞|아닌|그래|입니까|예요|이에요|이지요|이지|이야|일까)[\?\.\s]*$",
        # ── KO 짧은 entity 질의: "X는?" / "X 가?" ──
        r"^\S{1,30}(은|는|이|가)\s*[\?]?\s*$",
        # ── EN/KO 매우 짧은 query (단어 ≤ 3) — 단답 답 가까움 ──
        # query 전체가 짧으면 (예: "OpenAI", "FTX trial date") 단답 expected
        # 단 ambiguous 가능 → 아래 negative patterns 가 먼저 false 만들 case
        # 분리 처리 (외부 check 으로)
    ]

    # 단답 아닌 query — 위 FAST_TERSE 매치 후에도 다시 보고 false 라면
    # ``classify_fast`` 가 None 반환 → LLM fallback. 단 명확히 분석 query
    # 이면 LLM 호출 안 하고 직접 natural 반환 (빠른 path).
    FAST_NOT_TERSE_PATTERNS = [
        # ── EN 분석 / 비교 / 보고서 / 설명 요구 ──
        r"\b(compare|contrast|analyze|analyse|evaluate|explain|describe|"
        r"discuss|elaborate|summarize|summarise|breakdown|outline|"
        r"why|how does|how do|how did|what is the (impact|effect|role|"
        r"significance|relationship))\b",
        # "Give me a/an summary/breakdown/overview/report"
        r"\b(give\s+(me\s+)?(a|an)\s+(summary|breakdown|overview|report))\b",
        # ── KO 분석 / 비교 / 보고서 ── 단 "기술" 은 명사 (technology) 와
        # 동사 (기술하라) 충돌이 커서 "기술 해줘" / "기술 하라" 같은 동사
        # 직접 활용형으로 좁힘.
        r"(비교|대조|분석|평가|설명|논의|요약|정리|개요|보고서|"
        r"리뷰|검토|평론|소개)\S*\s*(해|줘|해줘|하라|해라|해\s*달|바라|"
        r"하시오|하세요|드려)",
        # "기술" 은 동사 활용 (기술하라/기술해) 만 catch
        r"(기술해|기술하라|기술해줘|기술하시오)",
        # KO 분석 명사 단독 등장 — 명사 자체가 분석/보고서 시그널
        # ("기술 스택 개요 설명" / "X 분석" / "Y 보고서" — 명사 뒤
        # 활용형 없이도 분석/보고서 query). 단 "기술" 은 위에서 동사
        # 활용 형태만 좁게 catch.
        r"(분석|평가|설명|비교|대조|논의|요약|정리|개요|보고서|"
        r"리뷰|검토|평론|소개)",
        # KO 의문사 — 단답 아닌 reasoning/explanation 요구
        # 결합형 ("어떤 이유" / "어떤 방법" / "어떤 영향" / "무슨 뜻") 은
        # 분석 query 명확. 위치 무관 등장만 보면 충분.
        r"(왜|어떻게|어떤\s*이유|어떤\s*방법|어떤\s*영향|어떤\s*의미|"
        r"어떤\s*관계|무슨\s*뜻)",
    ]

    # LLM fallback 프롬프트
    CLASSIFY_PROMPT = """당신은 답변 양식을 결정하는 AI입니다.
사용자 발화를 보고, 적절한 답변 양식을 선택하세요.

[양식 정의]
- terse:   단답 답이 자연스러운 query
           ("Who is X?", "When did Y happen?", "Is Z true?",
            "X 가 누구?", "Y 일자?", "Z 맞나?")
- natural: 분석 / 비교 / 보고서 / 설명을 요구하는 query
           ("Compare X and Y", "Analyze the impact", "Why...?",
            "X 분석해줘", "Y 와 Z 차이", "원인 설명")

[판단 기준]
- Wh-fact 단답 query → terse
- Yes/No 단답 query → terse
- 짧은 entity 조회 → terse
- 분석 / 비교 / 평가 / 보고서 → natural
- 설명 / 이유 / 방법 → natural
- 불명확 → natural (안전 default)

[사용자 발화]
{query}

[출력 규칙]
반드시 아래 중 하나만 출력 (다른 말 금지):
terse / natural"""

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def _get_llm(self):
        if self._llm is None:
            try:
                from llm.router import RouterWrapper
                self._llm = RouterWrapper("classify")
            except Exception:
                pass
        return self._llm

    def classify_fast(self, query: str) -> Optional[str]:
        """Regex 패턴 즉시 분류.

        Returns:
          - ``"terse"`` if FAST_TERSE 매치 + NOT_TERSE 매치 없음
          - ``"natural"`` if FAST_NOT_TERSE 매치 (분석/비교/보고서 explicit)
          - ``None`` if 둘 다 매치 안 됨 → LLM fallback 권장
        """
        q = query.strip()
        if not q:
            return "natural"

        # DETAILED 패턴 최우선 — "상세히/원문/전체 내용" 명시 요청은
        # 요약이 아니라 원문 재현을 원하는 것.
        for pat in self.FAST_DETAILED_PATTERNS:
            if re.search(pat, q, re.IGNORECASE):
                return "detailed"

        # NOT_TERSE 패턴 먼저 — 분석/비교/보고서 explicit 우선
        for pat in self.FAST_NOT_TERSE_PATTERNS:
            if re.search(pat, q, re.IGNORECASE):
                return "natural"

        # TERSE 패턴
        for pat in self.FAST_TERSE_PATTERNS:
            if re.search(pat, q, re.IGNORECASE):
                return "terse"

        return None   # 둘 다 미매치 — LLM 또는 default

    def classify_llm(self, query: str, timeout: int = 5) -> str:
        """LLM 기반 분류. 실패 시 ``"natural"`` (안전 default).

        Timeout 5s (짧은 분류용). 단답 vs natural 2-class 라
        IntentClassifier 보다 짧은 prompt + 빠른 응답.
        """
        llm = self._get_llm()
        if llm is None:
            return "natural"

        prompt = self.CLASSIFY_PROMPT.format(query=query[:200])

        try:
            t0 = time.time()
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
                return "natural"

            raw_clean = raw.strip().lower().split()[0] if raw.strip() else ""
            raw_clean = re.sub(r"[^a-z]", "", raw_clean)

            if raw_clean in ("terse", "natural"):
                print(f"[STYLE] LLM 분류: '{query[:30]}' → {raw_clean} "
                      f"({elapsed:.2f}s)")
                return raw_clean

            # 모드명이 아니면 단어 추출 시도
            if "terse" in raw.lower():
                return "terse"
            if "natural" in raw.lower():
                return "natural"

            print(f"[STYLE] LLM 분류 실패 (raw: '{raw[:30]}') → natural")
            return "natural"

        except Exception as e:
            print(f"[STYLE] LLM 분류 오류: {e} → natural")
            return "natural"

    def classify(
        self, query: str, *, llm_fallback: bool = True, timeout: int = 5
    ) -> Tuple[str, str]:
        """Hybrid 분류 (main entry).

        Args:
          ``llm_fallback``: ``classify_fast`` 가 None 반환 시 LLM 분류
            호출 여부. False 면 default ``natural`` 즉시 반환.
            measurement / strict 모드 (LLM call 빈도 통제) 에서 비활성.
          ``timeout``: LLM 분류 timeout (sec). default 5.

        Returns:
          ``(style, method)`` — style ∈ ``{"terse", "natural"}``,
          method ∈ ``{"fast", "llm", "default"}``.
        """
        fast = self.classify_fast(query)
        if fast:
            return fast, "fast"

        if llm_fallback:
            llm_result = self.classify_llm(query, timeout=timeout)
            return llm_result, "llm"

        return "natural", "default"


# ── 싱글턴 + module-level convenience wrappers ───────────────────────

_classifier: Optional[AnswerStyleClassifier] = None


def get_classifier() -> AnswerStyleClassifier:
    global _classifier
    if _classifier is None:
        _classifier = AnswerStyleClassifier()
    return _classifier


def classify_answer_style(
    query: str, *, llm_fallback: bool = True, timeout: int = 5
) -> Tuple[str, str]:
    """Module-level convenience wrapper. Returns ``(style, method)``.

    Usage at wiring sites::

        from core.answer_style_classifier import classify_answer_style

        if not response_style:
            response_style, _method = classify_answer_style(query)
        # else: user explicit override — skip auto-selection
    """
    # Env opt-out — operator can pin behavior in env without code change.
    # When JAMES_AUTO_STYLE=0 (or "false" / "no"), classify() returns the
    # safe default ("natural", "default") without consulting patterns or
    # LLM. Default ON so production gets auto-mount.
    flag = os.environ.get("JAMES_AUTO_STYLE", "1").strip().lower()
    if flag in ("0", "false", "no"):
        return "natural", "default"
    return get_classifier().classify(
        query, llm_fallback=llm_fallback, timeout=timeout
    )


__all__ = [
    "AnswerStyleClassifier",
    "get_classifier",
    "classify_answer_style",
]
