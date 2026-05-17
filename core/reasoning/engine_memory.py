"""Memory context assembly extracted from engine.py (chore split).

CLAUDE.md rule #5 module-size gate: ``core/reasoning/engine.py`` grew
past 23 KB after Phase 0/1/2 wirings + PR-O4 long_ctx gate + PR-O5
internal_rag gate. This module hosts the ~100-line block that ran
inside ``ReasoningEngine.query()`` to build the memory context +
language-aware system prompt.

Behaviour is byte-identical to the original in-method block — pure
refactor; the test suite (test_conversation_continuity in particular)
is the contract.

The block does four things in sequence:

  1. Pull system_prompt + pref_context + hist_ctx from MemoryStore.
     Apply the PR-O4 N-3 gate so long_ctx (cross-session summaries)
     is only included when hist_ctx is non-empty.
  2. Apply the character-profile prompt modifier on top of system_prompt.
  3. Detect persona commands ("내 이름은 X" etc.) and persist them via
     MemoryStore.save_preference — system_prompt is refreshed after.
  4. Detect query language (Korean / English / mixed) and prepend a
     language directive to system_prompt so the LLM responds in the
     right language.

The function mutates the caller's ``kwargs`` dict in place when a
persona-language command is detected (so the new value of
``kwargs["session_language"]`` propagates to subsequent calls in the
same query).
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def build_memory_context(
    engine,
    safe_query: str,
    user_role: str,
    kwargs: Dict[str, Any],
) -> Tuple[str, str, str]:
    """Build the (memory_context, system_prompt, hist_ctx) triple that
    feeds the rest of ReasoningEngine.query().

    Returns:
      memory_context  — concatenation of long_ctx + hist_ctx + pref_context
                        with PR-O4 N-3 gate applied
      system_prompt   — persona text + character modifier + language directive
      hist_ctx        — current-session history (separate so mode
                        handlers can gate the continuity directive on it)
    """
    memory_context = ""
    system_prompt = ""
    # [N-3 2026-05-13] hist_ctx 는 *현재* 세션의 prior turn 만 담는다.
    # 새 세션에서는 빈 문자열 — long_ctx (다른 세션 요약) 나 prefs 가
    # 있더라도 그것만으로 "대화 연속" 으로 취급해서는 안 된다.
    # 모드 핸들러가 continuity directive 발동 여부를 정확히 판단할
    # 수 있도록 try 바깥에서 미리 초기화.
    hist_ctx = ""
    try:
        from core.memory import MemoryStore
        store = MemoryStore()
        system_prompt = store.get_system_prompt()
        pref_context = store.get_context(user_role)

        # [P7-1] 단기: 현재 세션 최근 5턴
        # [Axis 6 user feedback, 2026-05-12] limit 3 → 5. Multi-
        # turn threads ("위 내용 + 추가로 …" 3번 이상) were losing
        # the earliest exchange. 5 keeps roughly the last minute
        # of conversation in context without bloating the prompt.
        session_id = kwargs.get("session_id", "default")
        hist_ctx = store.get_history_context(session_id, limit=5)

        # [P7-4 + PR-O4 2026-05-17] 장기 요약은 *연속* 세션에만 주입.
        # 새 세션의 첫 turn (hist_ctx == "") 에서는 이전 세션의 분석
        # 내용 (long_ctx 의 "[이전 대화 기억]" 블록) 을 제외한다 —
        # persona / preferences 는 system_prompt / pref_context 로
        # 따로 흘러가므로 사용자 정체성은 보존된다.
        # N-3 사용자 차단 회복 (handover §3 사이클 1): PR #257 의
        # continuity-directive 게이트만으로는 부족했음 (long_ctx 자체
        # 가 system prompt 의 배경 정보로 들어가, LLM 이 directive
        # 없이도 prior 분석을 끌어왔음).
        if hist_ctx:
            long_ctx = store.get_long_term_context(
                current_session_id=session_id, limit=2
            )
        else:
            long_ctx = ""

        # 우선순위: 장기기억 → 단기기억 → 선호도
        parts = [p for p in [long_ctx, hist_ctx, pref_context] if p]
        memory_context = "\n\n".join(parts)

        if long_ctx:
            print(f"[LONG_TERM] 장기 기억 주입: {len(long_ctx)}자")
        if hist_ctx:
            print(f"[HISTORY] 단기 기억 주입: {len(hist_ctx)}자")
        if memory_context:
            print(f"[MEMORY] context 주입: {len(memory_context)}자")
        if system_prompt:
            print(f"[PERSONA] {system_prompt[:60]}")
    except Exception as e:
        engine._log("memory_context", e, user_role)

    # ── [P1-10] 성향 캐릭터 modifier → system_prompt 주입 ─
    try:
        from core.character_profile import CharacterProfile
        cp = CharacterProfile()
        modifier = cp.get_prompt_modifiers()
        if modifier and modifier.strip():
            system_prompt = (system_prompt + "\n\n" + modifier).strip()
            print(f"[CHARACTER] 성향 주입: {modifier[:60]}")
    except Exception as e:
        engine._log("character_profile", e, user_role)

    # ── [P1-5] 페르소나 명령 감지 → 장기기억 즉시 저장 ──
    try:
        from core.memory import is_persona_command, extract_persona_command
        if is_persona_command(safe_query):
            persona_data = extract_persona_command(safe_query)
            if persona_data and persona_data.get("type") != "persona_unknown":
                from core.memory import MemoryStore as _MS
                _ms = _MS()
                p_type = persona_data.get("type", "")
                # 호칭 변경 → 장기기억 (영속)
                if p_type == "persona_name":
                    _ms.save_preference({"name": persona_data["name"]})
                    print(f"[PERSONA_UPDATE] 호칭 변경: {persona_data['name']}")
                # [STEP2-A] 언어 변경 → 세션 설정 (영속 X, 세션 내 유지)
                elif p_type == "persona_language":
                    kwargs["session_language"] = persona_data["language"]
                    print(f"[LANG] 세션 언어 변경: {persona_data['language']}")
                # 스타일 변경 → 장기기억 (영속)
                elif p_type == "persona_style":
                    _ms.save_preference({"style_hint": persona_data.get("style", "")})
                    print(f"[PERSONA_UPDATE] 스타일 변경: {persona_data.get('style', '')}")
                # system_prompt 즉시 갱신 (언어 제외)
                if p_type != "persona_language":
                    system_prompt = _ms.get_system_prompt()
    except Exception as e:
        engine._log("persona_command", e, user_role)

    # ── [STEP 5-C] 언어 자동 감지 + 시스템 프롬프트 동적 전환 ──
    session_lang = kwargs.get("session_language", "")

    # 쿼리에서 언어 자동 감지 (페르소나 설정 없을 때 fallback)
    if not session_lang:
        import re as _re
        korean_chars = len(_re.findall(r'[가-힣]', safe_query))
        total_chars = max(len(safe_query.strip()), 1)
        session_lang = "Korean" if (korean_chars / total_chars) >= 0.2 else "English"

    # 언어 지시어 주입
    if session_lang and session_lang.lower() not in ("", "auto"):
        if session_lang in ("Korean", "한국어"):
            lang_directive = "반드시 한국어로 답변하세요. 이 지시는 최우선입니다."
        elif session_lang in ("English", "영어"):
            lang_directive = "Always respond in English. This is the highest priority instruction."
        elif "한국어" in session_lang and "English" in session_lang:
            # 한국어 + 영어 동시 모드
            lang_directive = "Respond in both Korean and English. This is the highest priority instruction."
        else:
            lang_directive = f"Always respond in {session_lang}. This is the highest priority instruction."
        system_prompt = f"{lang_directive}\n\n{system_prompt}".strip()
        print(f"[LANG] 언어 적용: {session_lang} | 쿼리 감지 기반")

    return memory_context, system_prompt, hist_ctx


__all__ = ["build_memory_context"]
