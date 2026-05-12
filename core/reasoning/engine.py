"""
PROJECT JAMES - Reasoning Engine (Phase 4.5)
[REFACTOR] graph_rag_engine.py 분리 — Loop + Orchestration 전담

책임:
  - 전체 query 파이프라인 오케스트레이션
  - Limited Loop Reasoning (MAX_LOOP=2, TIMEOUT=30s)
  - Loop Role: retrieve(0) → expand(1) → verify(2)
  - LLM 답변 생성 + Hallucination 통제
  - security_layer → loop 전 구간 관통

호출 관계:
  graph_rag_engine.py (thin wrapper) → ReasoningEngine
"""

import json
import time
from datetime import datetime
from typing import Dict, Any, Optional

from core.graph_engine      import GraphEngine
from core.retrieval_engine  import RetrievalEngine
from core.security_layer    import (
    SecurityLayer,
)
from core.reasoning.modes import (
    handle_chat,
    handle_meta,
    handle_wiki_edit,
    handle_self_evolve,
    handle_coding,
)

SYSTEM_LOG_PATH   = "james_system_log.jsonl"
TIMING_TARGET_SEC = 30.0
MAX_LOOP          = 2        # Loop 최대 반복
LOOP_TIMEOUT      = 30.0     # 단일 loop 단계 timeout(s)
CONFIDENCE_TH     = 0.6


class ReasoningEngine:
    """
    전체 추론 파이프라인 오케스트레이터.
    security_layer는 loop 진입 전/후 모두 관통.

    Loop 구조:
      Loop 0 — retrieve:  Hybrid Search + 초기 context 확보
      Loop 1 — expand:   Graph DFS + context 보강
      Loop 2 — verify:   추론 경로 검증 + 최종 answer 생성

    MAX_LOOP=2 초과 불가 (Loop Injection 방어)
    """

    def __init__(self, default_role: str = "external"):
        from llm.router import RouterWrapper
        self.graph     = GraphEngine()
        self.retrieval = RetrievalEngine()
        self.llm       = RouterWrapper("general")
        self.security  = SecurityLayer()
        self.default_role = default_role

    # ─── 로그 / 타이밍 ──────────────────────────────────────

    @staticmethod
    def _log(step: str, error: Exception, role: str = "unknown"):
        entry = {
            "time":   datetime.now().isoformat(),
            "level":  "ERROR",
            "step":   f"reasoning_engine.{step}",
            "detail": str(error)[:300],
            "role":   role,
        }
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

    @staticmethod
    def _elapsed(t_start: float, label: str) -> float:
        e = time.time() - t_start
        flag = " ⚠️" if e > 10 else ""
        print(f"[TIMING] {label}: {e:.2f}s{flag}")
        return e

    # ─── 메인 Query ─────────────────────────────────────────

    def query(
        self,
        user_query:  str,
        user_role:   str        = None,
        source_type: Optional[str] = "prod",   # [P4.5-2] 기본 prod
        session_id:  str        = "default",   # [P7-FIX] 메모리 시스템 연동
        response_style: str     = "",          # brief / standard / detailed — see core/response_style.py
        mode_override:  str     = "",          # item #6: 클라이언트가 chat/coding/retrieval 등 명시 → router 우회
        selected_model: str     = "",          # [#A2 phase 2] 사용자가 picker로 고른 LLM tag — 모드 결정 후 catalog 대조
        **kwargs,
    ) -> Dict[str, Any]:
        """
        전체 추론 파이프라인.

        [SECURITY] pre_check → loop → post_check → output_filter 순서로
                   security_layer가 모든 구간 관통.
        [LOOP]     MAX_LOOP=2, 각 단계별 TIMEOUT 적용.
        [P7-FIX]   session_id 추가 — 단기/장기 메모리 정상 작동
        """
        # [P7-FIX] kwargs에 session_id 주입 (내부 메서드들이 참조)
        kwargs["session_id"] = session_id
        if user_role is None:
            user_role = self.default_role

        print(f"\n[REASONING] 질의: {user_query[:80]} (role={user_role}, src={source_type})")
        t_start = time.time()

        # ── STEP 0: pre_check (loop 진입 전 보안) ───────────
        t0 = time.time()
        try:
            sec = self.security.pre_check(user_query, user_role)
            if not sec["allowed"]:
                return self._blocked_result(sec["reason"])
            safe_query = sec["query"]
        except Exception as e:
            self._log("pre_check", e, user_role)
            return self._blocked_result("보안 검사 실패")
        self._elapsed(t0, "STEP0 pre_check")

        # ── Memory context + 대화 히스토리 주입 ─────────────
        memory_context = ""
        system_prompt  = ""
        try:
            from core.memory import MemoryStore
            store         = MemoryStore()
            system_prompt = store.get_system_prompt()
            pref_context  = store.get_context(user_role)

            # [P7-1] 단기: 현재 세션 최근 5턴
            # [Axis 6 user feedback, 2026-05-12] limit 3 → 5. Multi-
            # turn threads ("위 내용 + 추가로 …" 3번 이상) were losing
            # the earliest exchange. 5 keeps roughly the last minute
            # of conversation in context without bloating the prompt.
            session_id = kwargs.get("session_id", "default")
            hist_ctx   = store.get_history_context(session_id, limit=5)

            # [P7-4] 장기: 이전 세션 요약 (최근 2개)
            long_ctx = store.get_long_term_context(
                current_session_id=session_id, limit=2
            )

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
            self._log("memory_context", e, user_role)

        # ── [P1-10] 성향 캐릭터 modifier → system_prompt 주입 ─
        try:
            from core.character_profile import CharacterProfile
            cp       = CharacterProfile()
            modifier = cp.get_prompt_modifiers()
            if modifier and modifier.strip():
                system_prompt = (system_prompt + "\n\n" + modifier).strip()
                print(f"[CHARACTER] 성향 주입: {modifier[:60]}")
        except Exception as e:
            self._log("character_profile", e, user_role)

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
                        _ms.save_preference({"style_hint": persona_data.get("style","")})
                        print(f"[PERSONA_UPDATE] 스타일 변경: {persona_data.get('style','')}")
                    # system_prompt 즉시 갱신 (언어 제외)
                    if p_type != "persona_language":
                        system_prompt = _ms.get_system_prompt()
        except Exception as e:
            self._log("persona_command", e, user_role)

        # ── [STEP 5-C] 언어 자동 감지 + 시스템 프롬프트 동적 전환 ──
        session_lang = kwargs.get("session_language", "")

        # 쿼리에서 언어 자동 감지 (페르소나 설정 없을 때 fallback)
        if not session_lang:
            import re as _re
            korean_chars = len(_re.findall(r'[가-힣]', safe_query))
            total_chars  = max(len(safe_query.strip()), 1)
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
            system_prompt  = f"{lang_directive}\n\n{system_prompt}".strip()
            print(f"[LANG] 언어 적용: {session_lang} | 쿼리 감지 기반")

        # ── Query Router (STEP 0.5a) ─────────────────────────
        # pre_check 통과 후에만 진입. 보안 순서 유지.
        # item #6: mode_override가 있으면 router 건너뛰고 그 모드 사용
        # (클라이언트가 챗 페이지 dropdown으로 명시한 경우). 단,
        # role-allowed 체크는 그대로 적용해서 권한 우회 방지.
        from core.intent_classifier import ROLE_ALLOWED
        VALID_OVERRIDES = {"chat", "retrieval", "meta", "coding",
                           "wiki_edit", "self_evolve"}
        override = (mode_override or "").strip().lower()
        if override and override in VALID_OVERRIDES:
            allowed = ROLE_ALLOWED.get(user_role, {"chat", "retrieval"})
            if override in allowed:
                mode = override
                print(f"[ROUTER] mode={mode} (client override) | query='{safe_query[:40]}'")
            else:
                # 권한 없는 모드 override → router 정상 사용
                print(f"[ROUTER] override {override!r} 권한 없음 (role={user_role}) → 자동 라우팅")
                override = ""

        if not override or override not in VALID_OVERRIDES:
            try:
                from core.query_router import QueryRouter
                mode = QueryRouter().route(safe_query, user_role=user_role)
                print(f"[ROUTER] mode={mode} | query='{safe_query[:40]}'")
            except Exception as e:
                self._log("query_router", e, user_role)
                mode = "retrieval"   # fallback → 기존 Loop

        # ── [Bug fix, 2026-05-09] force_web_search forces retrieval ──
        # The chip click sends force_web_search=True. Only the retrieval
        # pipeline (run_retrieval_pipeline) honors this flag — chat /
        # meta / wiki_edit / etc. silently drop it, which surfaces as:
        # user clicks the "🌐 웹으로 더 조사" chip → server takes the
        # chat path again → memory_context (prior turns including the
        # last inference-only answer) is mixed back into the prompt →
        # new answer looks identical to the previous → user concludes
        # "the search must be based on James's earlier answer".
        #
        # Reality: no web search ran. Force-route to retrieval so the
        # web search actually fires with the original user question.
        if kwargs.get("force_web_search") and mode != "retrieval":
            print(f"[ROUTER] force_web_search=True overrides mode "
                  f"{mode!r} → retrieval (web search needs the "
                  f"retrieval pipeline)")
            mode = "retrieval"

        # ── [#A2 phase 2] selected_model validation ────────────
        # The user's secondary-picker choice arrives untrusted. Reject
        # anything not in the catalog for the resolved mode — silent
        # fallback to mode default, never echo arbitrary tags to Ollama.
        from core.model_catalog import resolve_model
        picked_model = resolve_model(mode, (selected_model or "").strip()) or ""
        if selected_model and not picked_model:
            print(f"[MODEL] '{selected_model}' rejected for mode={mode} → mode default")
        elif picked_model:
            print(f"[MODEL] mode={mode} using user-selected '{picked_model}'")

        # ── Mode dispatch (#29 phase 2: extracted to core/reasoning/modes.py) ──
        if mode == "chat":
            return handle_chat(self, safe_query, system_prompt, memory_context, user_role, t_start, response_style=response_style, selected_model=picked_model)
        if mode == "meta":
            return handle_meta(self, safe_query, system_prompt, user_role, t_start)
        if mode == "wiki_edit":
            return handle_wiki_edit(self, safe_query, system_prompt, user_role, t_start, selected_model=picked_model)
        if mode == "self_evolve":
            return handle_self_evolve(self, safe_query, system_prompt, user_role, t_start, selected_model=picked_model)
        if mode == "coding":
            return handle_coding(self, safe_query, system_prompt, user_role, t_start, selected_model=picked_model)

        # ── Retrieval → core/reasoning/pipeline.py (#29 phase 3) ──
        # Lazy import to avoid circular dependency (pipeline imports
        # MAX_LOOP / LOOP_TIMEOUT / TIMING_TARGET_SEC from this module).
        from core.reasoning.pipeline import run_retrieval_pipeline
        return run_retrieval_pipeline(
            self, safe_query, system_prompt, user_role, source_type, t_start,
            response_style=response_style,
            # [#A8-6] forward the user's "force web search" choice
            force_web_search=kwargs.get("force_web_search", False),
            # [#A2 phase 2] forward validated user-picked LLM
            selected_model=picked_model,
        )


    # ─── LLM 답변 생성 ──────────────────────────────────────

    _LLM_ERROR_PREFIXES = ("[Gemma 응답 없음]", "[Gemma 오류]", "LLM 응답 생성 중 오류")

    _NO_INFO_PATTERNS = [
        "자료에 없음", "자료 없음", "자료에는 없", "자료에서 찾을 수 없",
        "찾을 수 없", "확인되지 않", "확인할 수 없", "언급되지 않",
        "제공되지 않", "제공된 컨텍스트에 없", "정보가 없", "정보 없",
        "어떠한 엔티티", "관련 정보가 없", "해당 정보가 없", "알 수 없", "모르겠",
    ]

    @classmethod
    def _normalize_no_info(cls, answer: str) -> str:
        if not answer or "자료에 없음" in answer:
            return answer
        for pattern in cls._NO_INFO_PATTERNS:
            if pattern.lower() in answer.lower():
                return f"자료에 없음. {answer}"
        return answer

    @staticmethod
    def _classify_query(query: str) -> str:
        q = query.lower()
        if any(k in q for k in ["무엇", "란 무엇", "이란"]):
            return "definition"
        if any(k in q for k in ["예시", "example"]):
            return "example"
        if any(k in q for k in ["아닌", "않"]):
            return "negative_fact" if "무엇" in q else "negative"
        if any(k in q for k in ["인가", "맞"]):
            return "yesno"
        return "general"

    def _generate_answer(self, question: str, context: str,
                          system_prompt: str = "",
                          response_style: str = "",
                          selected_model: str = "") -> str:
        """RAG context + LLM 자유 추론. 한/영 자동 감지.

        `response_style`: kept for API back-compat — v2 always returns
        the NATURAL_PRESET (single natural-flow guide, no rigid
        emoji-section template). See core/response_style.py for the
        v1→v2 redesign rationale.

        `selected_model`: [#A2 phase 2] catalog-validated user pick.
        Empty string → use config.GEMMA_MODEL default.
        """
        from core.response_style import resolve_style
        style = resolve_style(response_style)

        safe_q    = RetrievalEngine._sanitize(question, 300)
        sys_block = f"{system_prompt}\n\n" if system_prompt else ""

        # [P7-I18N] 언어 감지 — 영어 비율로 판단
        en_chars = sum(1 for c in question if c.isascii() and c.isalpha())
        is_en    = en_chars > len(question) * 0.5 and len(question) > 3

        if is_en:
            lbl_data = "📚 Data-based"
            lbl_inf  = "💡 Reasoning"
            no_data  = "No relevant internal data"
            rule_txt = style.rule_text_en
        else:
            lbl_data = "📚 자료 기반"
            lbl_inf  = "💡 추론"
            no_data  = "관련 내부 자료 없음"
            rule_txt = style.rule_text_ko

        if context and len(context.strip()) >= 50:
            if style.force_two_sections:
                prompt = (
                    f"{sys_block}"
                    f"[{'Internal Data' if is_en else '내부 자료'}]\n{context[:1000]}\n\n"
                    f"[{'Question' if is_en else '질문'}]\n{safe_q}\n\n"
                    f"{rule_txt}\n"
                    f"{'Answer' if is_en else '답변'}:\n"
                )
            else:
                # Natural-flow path (v2 default): rule_txt teaches
                # 핵심→근거→대안 prose composition without the rigid
                # 📚/💡 labels. The model picks length from the prompt,
                # not from a token budget.
                prompt = (
                    f"{sys_block}"
                    f"[{'Internal Data' if is_en else '내부 자료'}]\n{context[:1000]}\n\n"
                    f"[{'Question' if is_en else '질문'}]\n{safe_q}\n\n"
                    f"{rule_txt}"
                    f"{'Answer' if is_en else '답변'}:\n"
                )
        else:
            if style.force_two_sections:
                prompt = (
                    f"{sys_block}"
                    f"[{'Question' if is_en else '질문'}]\n{safe_q}\n\n"
                    f"{lbl_data}: {no_data}\n{lbl_inf}:\n"
                )
            else:
                prompt = (
                    f"{sys_block}"
                    f"[{'Question' if is_en else '질문'}]\n{safe_q}\n\n"
                    f"{rule_txt}"
                    f"{'Answer' if is_en else '답변'}:\n"
                )

        try:
            answer = self.llm.call_gemma(
                prompt, timeout=120, use_cache=True,
                max_tokens=style.max_tokens,
                model=selected_model or None,
            )
            if not answer or any(answer.startswith(p) for p in self._LLM_ERROR_PREFIXES):
                return "답변 생성에 실패했습니다."
            return answer
        except Exception as e:
            self._log("generate_answer.llm", e)
            return "LLM 응답 생성 중 오류가 발생했습니다."

    # ─── 헬퍼 ───────────────────────────────────────────────

    @staticmethod
    def _blocked_result(reason: str) -> Dict[str, Any]:
        return {
            "answer":        reason,
            "blocked":       True,
            "graph_paths":   [],
            "graph_used":    0,
            "sources":       [],
            "timing_sec":    0,
            "unified_score": 0.0,
            "loop_count":    0,
        }
