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
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.graph_engine      import GraphEngine
from core.retrieval_engine  import RetrievalEngine
from core.gemma_client      import GemmaClient
from core.security_layer    import (
    SecurityLayer,
    filter_answer_by_role,
    log_system_event,
)
from core.ontology import get_ancestors, get_relation_weight, is_sensitive_relation
from core.reasoning.modes import (
    handle_chat,
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

            # [P7-1] 단기: 현재 세션 최근 3턴
            session_id = kwargs.get("session_id", "default")
            hist_ctx   = store.get_history_context(session_id, limit=3)

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
        try:
            from core.query_router import QueryRouter
            mode = QueryRouter().route(safe_query, user_role=user_role)
            print(f"[ROUTER] mode={mode} | query='{safe_query[:40]}'")
        except Exception as e:
            self._log("query_router", e, user_role)
            mode = "retrieval"   # fallback → 기존 Loop

        # ── Mode dispatch (#29 phase 2: extracted to core/reasoning/modes.py) ──
        if mode == "chat":
            return handle_chat(self, safe_query, system_prompt, memory_context, user_role, t_start)
        if mode == "wiki_edit":
            return handle_wiki_edit(self, safe_query, system_prompt, user_role, t_start)
        if mode == "self_evolve":
            return handle_self_evolve(self, safe_query, system_prompt, user_role, t_start)
        if mode == "coding":
            return handle_coding(self, safe_query, system_prompt, user_role, t_start)

        # ── Retrieval → 기존 Loop 그대로 진행 ────────────────

        # ── STEP 0.5b: query expansion [P5] ──────────────────
        # core/query_expander.py (was core/jepa_adapter.py — 단순 동의어
        # 사전, JEPA 메커니즘과 무관) 현재 비활성화 상태.
        # → Phase 9에서 멀티모달 임베딩 확장 시 재활성화 예정
        # → 현재는 원본 쿼리 그대로 사용 (0ms 오버헤드)
        t_qexp = time.time()
        expanded_query = safe_query   # 확장 없이 원본 사용
        self._elapsed(t_qexp, "STEP0.5 query_expand")

        # ── Loop 상태 초기화 ─────────────────────────────────
        loop_state = {
            "docs":           [],
            "graph_context":  [],
            "graph_paths":    [],
            "doc_context":    "",
            "avg_vec_score":  0.0,
            "expanded_query": expanded_query,   # [P5] Orchestrator로 전달
        }

        # ══════════════════════════════════════════
        # LOOP (retrieve → expand → verify)
        # MAX_LOOP=2 고정 — Loop Injection 방어
        # ══════════════════════════════════════════
        for loop_idx in range(MAX_LOOP + 1):
            t_loop = time.time()
            role   = f"Loop-{loop_idx}"

            # 루프 단계별 timeout 감시
            if time.time() - t_start > LOOP_TIMEOUT * (loop_idx + 1):
                print(f"[LOOP] {role} TIMEOUT → 조기 종료")
                break

            # ── Loop 0: Retrieve (Orchestrator) ──────────────
            if loop_idx == 0:
                print(f"\n[LOOP-{loop_idx}] retrieve (Orchestrator)")
                try:
                    from core.orchestrator import retrieve as orch_retrieve
                    docs = orch_retrieve(
                        original_query  = safe_query,
                        expanded_query  = loop_state["expanded_query"],
                        hybrid_search_fn= self.retrieval.hybrid_search,
                        user_role       = user_role,
                        source_type     = source_type,
                        top_k           = 8,
                    )
                except Exception as e:
                    self._log("loop0_orchestrator", e, user_role)
                    # fallback: 기존 방식
                    docs = self.retrieval.hybrid_search(
                        safe_query, top_k=8,
                        user_role=user_role,
                        source_type=source_type,
                    )
                docs = docs[:5]
                loop_state["docs"] = docs
                doc_ctx, avg_score = self.retrieval.build_doc_context(
                    [d.get("text", "") for d in docs],
                    [d.get("score", 0.5) for d in docs],
                )
                loop_state["doc_context"]   = doc_ctx
                loop_state["avg_vec_score"] = avg_score
                print(f"  docs={len(docs)} avg_score={avg_score:.3f}")

            # ── Loop 1: Expand (Graph DFS) ────────────────
            elif loop_idx == 1:
                print(f"\n[LOOP-{loop_idx}] expand")
                try:
                    entities = self.retrieval.extract_entities(
                        safe_query,
                        [d.get("text", "") for d in loop_state["docs"][:3]],
                        timeout=30,
                    )
                    snapshot   = self.graph.build_entity_map_snapshot()
                    entity_ids = self.graph.match_entities(entities, snapshot)
                    valid_ids  = self.graph.validate_integrity(entity_ids)

                    graph_ctx, graph_paths = self.graph.expand_dynamic(
                        valid_ids, source_type_filter=source_type
                    )
                    graph_ctx   = self.graph.rank_nodes(graph_ctx)
                    graph_ctx   = self.security.filter_graph(graph_ctx, user_role)
                    graph_paths = self.graph.verify_reasoning(graph_paths)

                    loop_state["graph_context"] = graph_ctx
                    loop_state["graph_paths"]   = graph_paths
                    print(f"  entities={len(entities)} graph_nodes={len(graph_ctx)} paths={len(graph_paths)}")
                except Exception as e:
                    self._log("loop1_expand", e, user_role)

            # ── Loop 2: Verify (최종 컨텍스트 결합) ──────
            elif loop_idx == 2:
                print(f"\n[LOOP-{loop_idx}] verify")
                # 추가 ABAC 일관성 검증 (보안 loop 관통)
                try:
                    abac = self.security.abac_consistency_check(
                        user_role,
                        loop_state["docs"],
                        loop_state["graph_context"],
                        "",
                    )
                    if not abac["consistent"]:
                        print(f"  [ABAC] 위반 {len(abac['violations'])}개")
                except Exception as e:
                    self._log("loop2_abac", e, user_role)

                # [P5.5] Tool 실행 — actions 있을 때만 (최소 연결)
                actions = loop_state.get("pending_actions", [])
                if actions:
                    try:
                        from tools.router import execute_tool
                        tool_ctx = {"user_role": user_role, "allow_fs": False, "allow_shell": False}
                        for action in actions[:3]:   # 최대 3개 제한
                            t_result = execute_tool(action, tool_ctx)
                            loop_state.setdefault("tool_results", []).append(t_result)
                        print(f"  tool_results={len(loop_state.get('tool_results',[]))}개")
                    except ImportError:
                        pass   # tools 없으면 skip
                    except Exception as e:
                        self._log("loop2_tool", e, user_role)

            self._elapsed(t_loop, f"LOOP-{loop_idx}")

        # ── 최종 컨텍스트 결합 ───────────────────────────────
        t_ctx = time.time()
        try:
            # ── unified_score v3 ────────────────────────────────
            # 원칙: "내부 자료를 실제로 활용했나?"
            #
            # [핵심 개선]
            # ChromaDB는 항상 결과를 반환하므로 docs 수만으로 판단 불가.
            # avg_vec_score 임계값(0.45) 이상이어야 "실제 관련 자료"로 인정.
            #
            # 가중치:
            #   doc_score   (55%) — 관련 자료 수 (gate 통과 시)
            #   vec_quality (20%) — 유사도 품질   (gate 통과 시)
            #   graph_score (25%) — 그래프 경로   (단독으론 최대 25%)

            docs      = loop_state["docs"]
            graph_ctx = loop_state["graph_context"]
            graph_pth = loop_state["graph_paths"]
            avg_vec   = loop_state["avg_vec_score"]

            RELEVANCE_GATE = 0.45  # 이 미만 = ChromaDB가 억지로 찾은 무관한 자료

            if avg_vec >= RELEVANCE_GATE and len(docs) > 0:
                # 게이트 통과 → 실제 관련 자료 있음
                doc_score   = min(1.0, len(docs) / 3.0)
                vec_quality = min(1.0, (avg_vec - RELEVANCE_GATE) / 0.25)  # 0.45~0.70 → 0~1
            else:
                # 게이트 미통과 → 관련 자료 없음 (docs 수 무시)
                doc_score   = 0.0
                vec_quality = 0.0

            graph_score = min(1.0, len(graph_pth) / 2.0)

            unified_score = (
                0.55 * doc_score    # 관련 자료 있는지 (핵심)
                + 0.20 * vec_quality  # 유사도 품질
                + 0.25 * graph_score  # 그래프 추론 (단독으론 25%까지만)
            )

            graph_ctx_str = self.graph.build_graph_context_str(
                graph_ctx,
                graph_pth,
                unified_score=unified_score,
            )
            final_context = loop_state["doc_context"] + graph_ctx_str
            print(f"[CONTEXT] unified={unified_score:.3f} len={len(final_context)}"
                  f" (gate={'pass' if avg_vec >= RELEVANCE_GATE else 'fail'}"
                  f" vec={avg_vec:.3f} doc={doc_score:.2f} graph={graph_score:.2f})")
        except Exception as e:
            self._log("context_build", e, user_role)
            final_context = loop_state["doc_context"]
        self._elapsed(t_ctx, "context_build")

        # ── Post-check ───────────────────────────────────────
        try:
            sec_post = self.security.post_check(final_context, user_role)
            safe_context = sec_post["context"] if sec_post["allowed"] else ""
        except Exception as e:
            self._log("post_check", e, user_role)
            safe_context = final_context

        # ── LLM 답변 생성 ────────────────────────────────────
        t_llm = time.time()
        try:
            sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""

            # [P7] retrieval 결과 품질에 따라 분기
            low_relevance = (
                not safe_context
                or len(safe_context.strip()) < 50
                or unified_score < 0.30
            )

            if low_relevance:
                # ── [3-E 경로 A] 내부 자료 없음 → 웹 검색 시도 ──
                web_context = ""
                web_results = []
                try:
                    from tools.web.web_searcher import (
                        search_web, format_search_results,
                        record_search, should_promote_to_longterm,
                        save_as_longterm, update_knowledge_level, is_save_command,
                    )
                    if user_role == "admin":  # 보안: admin만 웹 검색
                        print(f"[WEB] 내부 자료 부족 → 웹 검색: {safe_query[:40]}")
                        web_results = search_web(safe_query, max_results=4)
                        if web_results:
                            web_context = format_search_results(web_results)
                            search_count = record_search(safe_query)

                            # 단기 지식 레벨 +2
                            update_knowledge_level(safe_query, is_longterm=False)

                            # 장기 전환 조건 확인
                            if should_promote_to_longterm(safe_query) or is_save_command(safe_query):
                                # 요약 생성 후 wiki entity 저장
                                try:
                                    summary_prompt = (
                                        f"아래 검색 결과를 한국어로 200자 이내 핵심 요약:\n"
                                        f"{web_context[:1000]}\n\n요약:"
                                    )
                                    summary = self.llm.call_gemma(
                                        summary_prompt, timeout=30, use_cache=False, max_tokens=300
                                    )
                                    if summary:
                                        save_as_longterm(safe_query, web_results, summary, user_role)
                                        update_knowledge_level(safe_query, is_longterm=True)
                                        print(f"[WEB→WIKI] 장기 지식 전환 (검색 {search_count}회)")
                                except Exception as we:
                                    print(f"[WEB→WIKI] 요약/저장 실패: {we}")
                            else:
                                print(f"[WEB] 단기 저장 (누적 {search_count}회 / 2회 이상이면 장기 전환)")
                except Exception as we:
                    print(f"[WEB] 검색 모듈 오류: {we}")

                # 웹 검색 결과 있으면 컨텍스트에 포함
                combined_context = (web_context + "\n\n" if web_context else "") + safe_context
                answer_raw = self.llm.call_gemma(
                    f"{sys_prefix}"
                    f"{'[웹 검색 결과 포함]' if web_context else ''}"
                    f"\n질문: {safe_query}\n\n답변:",
                    use_cache=(not web_context), timeout=90, max_tokens=2000,
                ) if not combined_context.strip() else self._generate_answer(
                    safe_query,
                    combined_context,
                    system_prompt
                )
                answer_raw = answer_raw if answer_raw else ""

                if answer_raw and not any(
                    answer_raw.startswith(p) for p in self._LLM_ERROR_PREFIXES
                ):
                    print(f"[ROUTER] retrieval_fallback (score={unified_score:.3f}) → LLM 직접")
                    answer = answer_raw
                else:
                    answer = self._generate_answer(safe_query, safe_context, system_prompt)
            else:
                # 관련 자료 있음 → System Prompt + RAG 컨텍스트 + LLM 답변
                answer = self._generate_answer(safe_query, safe_context, system_prompt)

            # [P7] "자료 없음" 단독 응답(추론 없음)이면 system_prompt 포함 재시도
            _no_data = ("자료에 없음. 관련된", "답변 생성에 실패", "LLM 응답 생성 중 오류")
            if answer and any(answer.startswith(p) for p in _no_data):
                sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
                retry = self.llm.call_gemma(
                    f"{sys_prefix}질문: {safe_query}\n\n"
                    "📚 자료 기반: 관련 내부 자료 없음\n💡 추론:",
                    use_cache=False, timeout=60, max_tokens=2000,
                )
                if retry and not any(retry.startswith(p) for p in self._LLM_ERROR_PREFIXES):
                    print(f"[ROUTER] post_check → 재시도 (persona 포함)")
                    answer = "📚 자료 기반: 관련 내부 자료 없음\n💡 추론: " + retry

        except Exception as e:
            self._log("generate_answer", e, user_role)
            answer = "답변 생성 중 오류가 발생했습니다."
        self._elapsed(t_llm, "LLM_generate")

        # ── Output Filter ────────────────────────────────────
        try:
            wiki_persons = []
            if user_role == "external":
                wiki_persons = [
                    fm.get("name", "")
                    for eid, fp in self.graph.wiki_generator.entity_id_index.items()
                    for fm in [self.graph.wiki_generator._read_frontmatter(__import__("pathlib").Path(fp))]
                    if fm and fm.get("entity_type") == "person" and fm.get("name")
                ]
            answer = filter_answer_by_role(
                answer, user_role,
                loop_state["graph_context"],
                wiki_person_names=wiki_persons,
            )
        except Exception as e:
            self._log("output_filter", e, user_role)

        # ── Memory Loom 조건부 저장 [P5] ─────────────────────
        # Output Filter 이후, 검증된 결과에만 적용
        try:
            from core.memory import store_result
            if loop_state["graph_paths"] and not any(
                answer.startswith(p) for p in ("답변 생성에 실패", "LLM 응답 생성 중 오류")
            ):
                # 신뢰도 계산 (unified_score 기반)
                conf = round(
                    loop_state["avg_vec_score"] * 0.6
                    + min(len(loop_state["graph_context"]) / 5, 1.0) * 0.4, 3
                )
                mem_result = {
                    "answer":          answer[:300],
                    "confidence":      conf,
                    "ontology_valid":  len(loop_state["graph_paths"]) > 0,
                    "graph_paths":     loop_state["graph_paths"][:3],
                    "user_role":       user_role,
                    "query":           safe_query[:100],
                }
                ok, reason = store_result(mem_result)
                print(f"[LOOM] store={'ok' if ok else 'skip'}: {reason[:60]}")
        except Exception as e:
            self._log("memory_loom", e, user_role)

        # ── 타이밍 출력 ──────────────────────────────────────
        total = time.time() - t_start
        flag  = "✅" if total <= TIMING_TARGET_SEC else "⚠️ 초과"
        print(f"\n[TIMING] 총: {total:.2f}s / {TIMING_TARGET_SEC:.0f}s → {flag}")
        stats = self.llm.get_cache_stats()
        print(f"[CACHE]  {stats['hit_rate_%']} hits={stats['hits']} misses={stats['misses']}")

        return {
            "answer":        answer,
            "graph_paths":   loop_state["graph_paths"],
            "graph_used":    len(loop_state["graph_context"]),
            "sources":       [d.get("source", "unknown") for d in loop_state["docs"][:3]],
            "blocked":       False,
            "timing_sec":    round(total, 2),
            "unified_score": round(unified_score if "unified_score" in dir() else 0.0, 3),
            "loop_count":    min(MAX_LOOP + 1, 3),
        }

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
                          system_prompt: str = "") -> str:
        """RAG context + LLM 자유 추론. 한/영 자동 감지."""
        safe_q    = RetrievalEngine._sanitize(question, 300)
        sys_block = f"{system_prompt}\n\n" if system_prompt else ""

        # [P7-I18N] 언어 감지 — 영어 비율로 판단
        import re as _re
        en_chars = sum(1 for c in question if c.isascii() and c.isalpha())
        is_en    = en_chars > len(question) * 0.5 and len(question) > 3

        if is_en:
            lbl_data = "📚 Data-based"
            lbl_inf  = "💡 Reasoning"
            no_data  = "No relevant internal data"
            rule_txt = (
                "Answer structure:\n"
                "📚 Data-based: (facts from internal data only, or 'No relevant data')\n"
                "💡 Reasoning: (free analysis using data + knowledge)\n"
                "Rules: Both sections required. Data-based = confirmed facts only.\n"
            )
        else:
            lbl_data = "📚 자료 기반"
            lbl_inf  = "💡 추론"
            no_data  = "관련 내부 자료 없음"
            rule_txt = (
                "답변 구조:\n"
                "📚 자료 기반: (내부 자료 사실만. 없으면 '관련 자료 없음')\n"
                "💡 추론: (자료와 지식을 연결한 자유 분석)\n"
                "규칙: 두 섹션 모두 작성. 자료 기반은 확인된 사실만.\n"
            )

        if context and len(context.strip()) >= 50:
            prompt = (
                f"{sys_block}"
                f"[{'Internal Data' if is_en else '내부 자료'}]\n{context[:1000]}\n\n"
                f"[{'Question' if is_en else '질문'}]\n{safe_q}\n\n"
                f"{rule_txt}\n"
                f"{'Answer' if is_en else '답변'}:\n"
            )
        else:
            prompt = (
                f"{sys_block}"
                f"[{'Question' if is_en else '질문'}]\n{safe_q}\n\n"
                f"{lbl_data}: {no_data}\n{lbl_inf}:\n"
            )

        try:
            answer = self.llm.call_gemma(
                prompt, timeout=120, use_cache=True,
                max_tokens=2000,   # 긴 답변 허용 (기존 700 → 2000)
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
