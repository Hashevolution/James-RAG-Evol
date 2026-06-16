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
        """Public reasoning entry point.

        Wraps the implementation in a ``try/finally`` so every return
        path — including ``_blocked_result`` and exception unwinds —
        releases the turn's working-memory scratch (PR-10b). The
        previous body lives in ``_query_impl``; this method is a
        thin wrapper so the cleanup invariant is impossible to skip.
        """
        try:
            return self._query_impl(
                user_query, user_role, source_type, session_id,
                response_style, mode_override, selected_model,
                **kwargs,
            )
        finally:
            # PR-10b — release the turn's scratch and clear the
            # session ContextVar so the next request in this
            # thread starts uninstrumented. Both wrapped in try
            # so a teardown failure cannot eclipse a real exception
            # bubbling up from the impl.
            try:
                from core.observability import (
                    get_session_context,
                    set_session_context,
                )
                _sid, _tid = get_session_context()
                if _sid and _tid:
                    try:
                        from core.memory.working import get_working_memory
                        get_working_memory().clear_turn(_sid, _tid)
                    except Exception:
                        pass
                set_session_context("", "")
            except Exception:
                pass

    def _query_impl(
        self,
        user_query:  str,
        user_role:   str        = None,
        source_type: Optional[str] = "prod",
        session_id:  str        = "default",
        response_style: str     = "",
        mode_override:  str     = "",
        selected_model: str     = "",
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

        # ── STEP 0.3: AnswerStyleClassifier auto-mount (cycle β #2) ──
        # response_style 미명시 시 query intent 정량 인식 → 양식
        # auto-mount. 단답 query → "terse" (TERSE_PRESET 4 layer collapse
        # + rule_text v2 strict + pipeline_synth P-1 자동 발동). 분석/
        # 보고서 query → "natural" (production default 그대로).
        #
        # 사용자가 explicit response_style ("terse" / "natural" / etc)
        # 넘기면 본 step 우회 — UX override 보존.
        #
        # advanced 스택 (planner/reflect/verify) 의 env-gate 와는 별도
        # axis. production Default = advanced ON 그대로 유지. 본 step
        # 은 양식 layer 만 다룬다.
        #
        # 분류 자체 비활성화: env JAMES_AUTO_STYLE=0 (classifier 내부
        # gate). 분류 실패 (예외) 시 response_style 빈 채로 진행 =
        # NATURAL_PRESET resolve = 기존 동작 byte-identical.
        if not (response_style or "").strip():
            try:
                from core.answer_style_classifier import classify_answer_style
                _auto_style, _method = classify_answer_style(safe_query)
                response_style = _auto_style
                print(f"[STYLE] auto-mount '{safe_query[:30]}' → "
                      f"{_auto_style} ({_method})")
            except Exception as e:
                # 분류 실패는 non-fatal — response_style 빈 채로 진행
                self._log("auto_style_classify", e, user_role)

        # ── Session ContextVar — Cognitive Phase 3 PR-9b ────
        # Bind (session_id, turn_id) to the current async/threading
        # context so cognitive stages (planner / reflect / verify /
        # synth) can attribute their episodic events without taking
        # session_id as a signature parameter. turn_id is millisecond-
        # precision timestamp scoped under session_id — sortable per
        # session, unique within a single-process turn.
        try:
            from core.observability import set_session_context
            _turn_id = f"{session_id}:{int(time.time() * 1000)}"
            set_session_context(session_id, _turn_id)
        except Exception as e:
            # ContextVar set failing is non-fatal — episodic stays a
            # no-op for this turn rather than crashing the query.
            self._log("session_context", e, user_role)

        # ── Memory context + 대화 히스토리 주입 (delegated) ───
        # The MemoryStore / character / persona-command / language-
        # detection logic moved to core/reasoning/engine_memory.py for
        # the rule #5 module-size split. The helper mutates ``kwargs``
        # in place (persona-language commands write
        # ``kwargs["session_language"]``).
        from core.reasoning.engine_memory import build_memory_context
        memory_context, system_prompt, hist_ctx = build_memory_context(
            self, safe_query, user_role, kwargs, response_style=response_style,
        )

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

        # ── v18.7 Phase 2c/3c — measured-preference mode routing ──
        # When the user did NOT pick a model, these modes auto-route
        # through the measured preference list instead of the global
        # config.GEMMA_MODEL default. requested="" makes
        # resolve_for_mode use the preference-list top (not
        # GEMMA_MODEL), so these are the modes that actually consume
        # the Phase-1 plumbing.
        #   • chat (Phase 2b, v18.7-phase2b-chat QDC): gemma3:12b
        #     (0.917) > gemma4:e4b (0.833) > gemma3:4b (0.750) on the
        #     Korean chat fixture.
        #   • retrieval (Phase 3b, v18.7-phase3b-tier-ladder QDC):
        #     gold-grounded 27b(1.0) > 12b(0.889) > 4b(0.852) >
        #     gemma4:e4b(0.815). The default GEMMA_MODEL (gemma4:e4b)
        #     is WEAKEST on evidence-rich retrieval; preference top is
        #     gemma3:12b (best value; 27b is more accurate but 2.3x
        #     slower + verbose, so not the default).
        # Kill-switch: JAMES_DISABLE_MODE_AWARE_ROUTING=1 reverts both
        # to GEMMA_MODEL. meta/wiki_edit/vision/self_evolve stay on the
        # legacy path (not yet measurement-validated per mode).
        if mode in ("chat", "retrieval") and not picked_model:
            import os
            if not os.environ.get("JAMES_DISABLE_MODE_AWARE_ROUTING"):
                from core.model_resolver import resolve_for_mode
                _rm = resolve_for_mode(mode, requested="")
                if _rm.tag:
                    picked_model = _rm.tag
                    print(f"[MODEL] mode={mode} auto-routed → '{_rm.tag}' "
                          f"(source={_rm.source}; measured pref)")
                    if _rm.warning:
                        print(f"[MODEL] {_rm.warning}")

        # ── Mode dispatch (#29 phase 2: extracted to core/reasoning/modes.py) ──
        if mode == "chat":
            return handle_chat(self, safe_query, system_prompt, memory_context, user_role, t_start, response_style=response_style, selected_model=picked_model, hist_ctx=hist_ctx)
        if mode == "meta":
            return handle_meta(self, safe_query, system_prompt, user_role, t_start)
        if mode == "wiki_edit":
            return handle_wiki_edit(self, safe_query, system_prompt, user_role, t_start, selected_model=picked_model)
        if mode == "self_evolve":
            return handle_self_evolve(self, safe_query, system_prompt, user_role, t_start, selected_model=picked_model)
        if mode == "coding":
            return handle_coding(self, safe_query, system_prompt, user_role, t_start, selected_model=picked_model)

        # ── PR-O5 (cycle 12) — internal RAG feature gate ──────────
        # external (= guest / 비로그인) 는 일상 챗만 허용. internal
        # RAG (vector + graph) 차단 시 handle_chat 으로 우회 →
        # LLM 의 일반 지식 + system_prompt + memory_context 만으로
        # 답변. admin 이 권한 매트릭스에서 query.internal_rag 를
        # external 에 override 하면 정상적인 retrieval 경로 통과.
        try:
            from core.policy_engine import default_engine as _policy_engine
            _rag_dec = _policy_engine.can_use_feature(user_role, "query.internal_rag")
            if not _rag_dec.allowed:
                print(f"[POLICY] {user_role} blocked from internal_rag "
                      f"({_rag_dec.reason}) → chat-only fallback")
                return handle_chat(
                    self, safe_query, system_prompt, memory_context, user_role, t_start,
                    response_style=response_style, selected_model=picked_model,
                    hist_ctx=hist_ctx,
                )
        except Exception as e:
            self._log("internal_rag_gate", e, user_role)

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


    # ─── LLM 답변 생성 (delegated to engine_synth) ─────────
    # The canonical RAG synthesis (prompt assembly + trace_synth_call
    # wrap + error normalisation) moved to core/reasoning/engine_synth.py
    # for the rule #5 module-size split. External callers
    # (pipeline_synth.py, reflect.py, verify.py) keep their existing
    # ``engine._LLM_ERROR_PREFIXES`` / ``engine._generate_answer(...)``
    # access shape; the class members below are thin re-exports /
    # delegators so a future contract change has one place to edit.

    # Tuple re-export — immutable, so a single shared reference is safe.
    from core.reasoning.engine_synth import (
        LLM_ERROR_PREFIXES as _LLM_ERROR_PREFIXES,
        NO_INFO_PATTERNS as _NO_INFO_PATTERNS,
    )

    @classmethod
    def _normalize_no_info(cls, answer: str) -> str:
        from core.reasoning.engine_synth import normalize_no_info
        return normalize_no_info(answer)

    @staticmethod
    def _classify_query(query: str) -> str:
        from core.reasoning.engine_synth import classify_query
        return classify_query(query)

    def _generate_answer(self, question: str, context: str,
                          system_prompt: str = "",
                          response_style: str = "",
                          selected_model: str = "") -> str:
        """Thin delegator → ``engine_synth.generate_rag_answer``.

        Existing call sites in pipeline_synth.py keep their
        ``engine._generate_answer(...)`` shape; this method just
        forwards to the free function so the implementation can live
        in a smaller, more focused module.
        """
        from core.reasoning.engine_synth import generate_rag_answer
        return generate_rag_answer(
            self, question, context, system_prompt,
            response_style=response_style,
            selected_model=selected_model,
        )

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
