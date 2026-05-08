"""RAG retrieval pipeline extracted from ReasoningEngine.query() (#29 phase 3/3).

Same composition pattern as core/reasoning/modes.py: a free function taking
the engine instance and the closure variables it needs. Body code is
byte-identical to the original in-method block (lines 243-584 of post-phase-2
engine.py) except `self.X` → `engine.X` and the trailing return assembly
moved out of the surrounding query() context.

Pipeline stages (in order):
  1. STEP 0.5b query expansion (currently no-op — kept for Phase 9 multimodal)
  2. Loop state init
  3. Loop 0 retrieve → Loop 1 expand → Loop 2 verify (MAX_LOOP=2 fixed)
  4. Final context combine + unified_score v3
  5. post_check (security)
  6. LLM answer generation + [3-E] web search fallback for low-relevance
  7. Output filter (role-based)
  8. Memory Loom conditional save
  9. Timing print + result dict
"""
from __future__ import annotations

import time
from typing import Any, Dict

from core.reasoning.engine import MAX_LOOP, LOOP_TIMEOUT, TIMING_TARGET_SEC
from core.security_layer import filter_answer_by_role
from core.observability import log_stage


def run_retrieval_pipeline(
    engine,
    safe_query: str,
    system_prompt: str,
    user_role: str,
    source_type: str,
    t_start: float,
    response_style: str = "",
) -> Dict[str, Any]:
    # ── STEP 0.5b: query expansion [P5] ──────────────────
    # core/query_expander.py (was core/jepa_adapter.py — 단순 동의어
    # 사전, JEPA 메커니즘과 무관) 현재 비활성화 상태.
    # → Phase 9에서 멀티모달 임베딩 확장 시 재활성화 예정
    # → 현재는 원본 쿼리 그대로 사용 (0ms 오버헤드)
    t_qexp = time.time()
    expanded_query = safe_query   # 확장 없이 원본 사용
    engine._elapsed(t_qexp, "STEP0.5 query_expand")

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
                    hybrid_search_fn= engine.retrieval.hybrid_search,
                    user_role       = user_role,
                    source_type     = source_type,
                    top_k           = 8,
                )
            except Exception as e:
                engine._log("loop0_orchestrator", e, user_role)
                # fallback: 기존 방식
                docs = engine.retrieval.hybrid_search(
                    safe_query, top_k=8,
                    user_role=user_role,
                    source_type=source_type,
                )
            docs = docs[:5]
            loop_state["docs"] = docs
            doc_ctx, avg_score = engine.retrieval.build_doc_context(
                [d.get("text", "") for d in docs],
                [d.get("score", 0.5) for d in docs],
            )
            loop_state["doc_context"]   = doc_ctx
            loop_state["avg_vec_score"] = avg_score
            print(f"  docs={len(docs)} avg_score={avg_score:.3f}")
            # [#47 phase 1] retrieve stage — top_k actually returned, best
            # vector score, and the BM25 score of doc[0] when it carries one.
            top_doc = docs[0] if docs else {}
            log_stage(
                "retrieve",
                top_k=len(docs),
                avg_vec_score=round(avg_score, 4),
                top_vector_score=round(top_doc.get("score", 0.0), 4),
                top_bm25_score=round(top_doc.get("bm25", 0.0), 4) if "bm25" in top_doc else None,
                source_type=source_type,
            )

        # ── Loop 1: Expand (Graph DFS) ────────────────
        elif loop_idx == 1:
            print(f"\n[LOOP-{loop_idx}] expand")
            try:
                entities = engine.retrieval.extract_entities(
                    safe_query,
                    [d.get("text", "") for d in loop_state["docs"][:3]],
                    timeout=30,
                )
                snapshot   = engine.graph.build_entity_map_snapshot()
                entity_ids = engine.graph.match_entities(entities, snapshot)
                valid_ids  = engine.graph.validate_integrity(entity_ids)

                graph_ctx, graph_paths = engine.graph.expand_dynamic(
                    valid_ids, source_type_filter=source_type
                )
                graph_ctx   = engine.graph.rank_nodes(graph_ctx)
                graph_ctx   = engine.security.filter_graph(graph_ctx, user_role)
                graph_paths = engine.graph.verify_reasoning(graph_paths)

                loop_state["graph_context"] = graph_ctx
                loop_state["graph_paths"]   = graph_paths
                print(f"  entities={len(entities)} graph_nodes={len(graph_ctx)} paths={len(graph_paths)}")
                # [#47 phase 1] graph stage — entities matched, paths walked,
                # and the integrity-validated id count as observability fields.
                log_stage(
                    "graph",
                    entities_extracted=len(entities),
                    entity_ids_matched=len(entity_ids),
                    valid_entity_ids=len(valid_ids),
                    graph_nodes=len(graph_ctx),
                    paths_walked=len(graph_paths),
                )
            except Exception as e:
                engine._log("loop1_expand", e, user_role)
                log_stage("graph", error=str(e)[:200])

        # ── Loop 2: Verify (최종 컨텍스트 결합) ──────
        elif loop_idx == 2:
            print(f"\n[LOOP-{loop_idx}] verify")
            # 추가 ABAC 일관성 검증 (보안 loop 관통)
            try:
                abac = engine.security.abac_consistency_check(
                    user_role,
                    loop_state["docs"],
                    loop_state["graph_context"],
                    "",
                )
                if not abac["consistent"]:
                    print(f"  [ABAC] 위반 {len(abac['violations'])}개")
            except Exception as e:
                engine._log("loop2_abac", e, user_role)

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
                    engine._log("loop2_tool", e, user_role)

        engine._elapsed(t_loop, f"LOOP-{loop_idx}")

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

        graph_ctx_str = engine.graph.build_graph_context_str(
            graph_ctx,
            graph_pth,
            unified_score=unified_score,
        )
        final_context = loop_state["doc_context"] + graph_ctx_str
        print(f"[CONTEXT] unified={unified_score:.3f} len={len(final_context)}"
              f" (gate={'pass' if avg_vec >= RELEVANCE_GATE else 'fail'}"
              f" vec={avg_vec:.3f} doc={doc_score:.2f} graph={graph_score:.2f})")
    except Exception as e:
        engine._log("context_build", e, user_role)
        final_context = loop_state["doc_context"]
    engine._elapsed(t_ctx, "context_build")

    # ── Post-check ───────────────────────────────────────
    try:
        sec_post = engine.security.post_check(final_context, user_role)
        safe_context = sec_post["context"] if sec_post["allowed"] else ""
    except Exception as e:
        engine._log("post_check", e, user_role)
        safe_context = final_context

    # item #5-A: 답변에 "관련 파일은 X.md, Y.md입니다" 형태로
    # source 파일을 먼저 명시하기 위해 context 앞에 [관련 자료]
    # 섹션을 prepend. 모델이 이 헤더를 보고 답변 첫 줄에 인용하도록
    # rule_text가 지시한다 (response_style.py 참조).
    source_names = []
    seen_sources = set()
    for d in (loop_state.get("docs") or [])[:5]:
        s = d.get("source") or d.get("name") or d.get("path") or ""
        if s and s not in seen_sources:
            # 너무 긴 경로는 잘라서 표시
            s_disp = s.split("/")[-1].split("\\")[-1]
            source_names.append(s_disp[:60])
            seen_sources.add(s)
    if safe_context.strip() and source_names:
        sources_header = (
            "[관련 자료 목록]\n"
            + "\n".join(f"- {s}" for s in source_names)
            + "\n\n[자료 내용]\n"
        )
        safe_context = sources_header + safe_context

    # ── LLM 답변 생성 ────────────────────────────────────
    t_llm = time.time()
    try:
        sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""

        # [P7] retrieval 결과 품질에 따라 분기
        # [#A6-1 2026-05-08] threshold + role gate 동적 로드
        from core.web_search_config import get_threshold, is_role_allowed
        low_relevance = (
            not safe_context
            or len(safe_context.strip()) < 50
            or unified_score < get_threshold()
        )

        # [#A6-2] web_results를 outer scope에 선언 — 답변 후 return dict에
        # 노출하기 위해. low_relevance 진입 안 하면 빈 리스트 → web_used=False.
        web_results: list = []

        if low_relevance:
            # ── [3-E 경로 A] 내부 자료 없음 → 웹 검색 시도 ──
            web_context = ""
            try:
                from tools.web.web_searcher import (
                    search_web, format_search_results,
                    record_search, should_promote_to_longterm,
                    save_as_longterm, update_knowledge_level, is_save_command,
                )
                # [#A6-1] admin-only hardcode → role allowlist (settings).
                if is_role_allowed(user_role):
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
                                summary = engine.llm.call_gemma(
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
            # #44 phase 4: web 결과는 low-trust → PolicyEngine.quarantine 통과
            # ("ignore previous instructions" 류 injection 패턴 중립화).
            # safe_context 는 이미 retrieval/graph 단계의 ABAC + 문서 ingestion 시
            # sanitize_document_content() 를 거친 high-trust 영역이므로 추가 처리 없음.
            if web_context:
                from core.policy_engine import default_engine, TrustedContent
                web_clean, _ = default_engine.quarantine(
                    TrustedContent(text=web_context, source="web", trust="low")
                )
                combined_context = web_clean + "\n\n" + safe_context
            else:
                combined_context = safe_context
            from core.response_style import resolve_style as _resolve_style
            _style = _resolve_style(response_style)
            # Pick the right-language flow guide for the no-context
            # web-fallback prompt below. Same heuristic as engine + chat.
            _korean = sum(1 for c in safe_query if "가" <= c <= "힣")
            _is_ko = _korean >= max(1, len(safe_query) * 0.2)
            _rule = _style.rule_text_ko if _is_ko else _style.rule_text_en
            answer_raw = engine.llm.call_gemma(
                f"{sys_prefix}"
                f"{'[웹 검색 결과 포함]' if web_context else ''}"
                f"\n{_rule}\n질문: {safe_query}\n\n답변:",
                use_cache=(not web_context), timeout=90,
                max_tokens=_style.max_tokens,
            ) if not combined_context.strip() else engine._generate_answer(
                safe_query,
                combined_context,
                system_prompt,
                response_style=response_style,
            )
            answer_raw = answer_raw if answer_raw else ""

            if answer_raw and not any(
                answer_raw.startswith(p) for p in engine._LLM_ERROR_PREFIXES
            ):
                print(f"[ROUTER] retrieval_fallback (score={unified_score:.3f}) → LLM 직접")
                answer = answer_raw
            else:
                answer = engine._generate_answer(safe_query, safe_context, system_prompt, response_style=response_style)
        else:
            # 관련 자료 있음 → System Prompt + RAG 컨텍스트 + LLM 답변
            answer = engine._generate_answer(safe_query, safe_context, system_prompt, response_style=response_style)

        # [P7] "자료 없음" 단독 응답(추론 없음)이면 system_prompt 포함 재시도
        _no_data = ("자료에 없음. 관련된", "답변 생성에 실패", "LLM 응답 생성 중 오류")
        if answer and any(answer.startswith(p) for p in _no_data):
            sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
            from core.response_style import resolve_style as _resolve_style
            _style_retry = _resolve_style(response_style)
            _korean_r = sum(1 for c in safe_query if "가" <= c <= "힣")
            _is_ko_r = _korean_r >= max(1, len(safe_query) * 0.2)
            _rule_r = _style_retry.rule_text_ko if _is_ko_r else _style_retry.rule_text_en
            retry = engine.llm.call_gemma(
                f"{sys_prefix}{_rule_r}\n"
                f"질문: {safe_query}\n\n"
                "(내부 자료에는 직접 언급이 없습니다. "
                "위 가이드를 따라 자연스럽게 답하세요.)\n답변:",
                use_cache=False, timeout=60, max_tokens=_style_retry.max_tokens,
            )
            if retry and not any(retry.startswith(p) for p in engine._LLM_ERROR_PREFIXES):
                print(f"[ROUTER] post_check → 재시도 (persona 포함)")
                answer = retry

    except Exception as e:
        engine._log("generate_answer", e, user_role)
        answer = "답변 생성 중 오류가 발생했습니다."
    engine._elapsed(t_llm, "LLM_generate")
    # [#47 phase 1] answer stage — model latency + size signals so a
    # diagnoser can tell "blank answer because LLM timed out" from
    # "blank answer because retrieval was empty".
    log_stage(
        "answer",
        latency_ms=int((time.time() - t_llm) * 1000),
        answer_len=len(answer or ""),
        answer_starts_with_error=any(
            (answer or "").startswith(p) for p in engine._LLM_ERROR_PREFIXES
        ),
    )

    # ── Output Filter ────────────────────────────────────
    # #44 phase 2-C: gate the role-based filter through PolicyEngine.can_emit
    # so the output stage is wired to the same engine as retrieval/graph.
    # Phase-1 can_emit always allows (filter_answer_by_role still mutates);
    # future tightening can add real refuse-to-emit semantics here.
    try:
        from core.policy_engine import default_engine as _policy
        wiki_persons = []
        if user_role == "external":
            wiki_persons = [
                fm.get("name", "")
                for eid, fp in engine.graph.wiki_generator.entity_id_index.items()
                for fm in [engine.graph.wiki_generator._read_frontmatter(__import__("pathlib").Path(fp))]
                if fm and fm.get("entity_type") == "person" and fm.get("name")
            ]
        if _policy.can_emit(user_role, answer).allowed:
            answer = filter_answer_by_role(
                answer, user_role,
                loop_state["graph_context"],
                wiki_person_names=wiki_persons,
            )
    except Exception as e:
        engine._log("output_filter", e, user_role)

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
        engine._log("memory_loom", e, user_role)

    # ── 타이밍 출력 ──────────────────────────────────────
    total = time.time() - t_start
    flag  = "✅" if total <= TIMING_TARGET_SEC else "⚠️ 초과"
    print(f"\n[TIMING] 총: {total:.2f}s / {TIMING_TARGET_SEC:.0f}s → {flag}")
    stats = engine.llm.get_cache_stats()
    print(f"[CACHE]  {stats['hit_rate_%']} hits={stats['hits']} misses={stats['misses']}")

    # [#A6-2] 웹 검색 사용 여부 + 출처 URL — 답변 bubble의 "🌐 웹 검색
    # 사용됨" 배지 + 출처 리스트에 사용. low-trust 외부 데이터임을 사용자
    # 에게 명시적으로 알려 신뢰도 판단 가능하게.
    web_used    = bool(web_results)
    web_sources = [
        {"title": (r.get("title") or "")[:120],
         "url":   r.get("url", ""),
         "engine": r.get("engine", "")}
        for r in web_results[:5] if r.get("url")
    ]

    return {
        "answer":        answer,
        "graph_paths":   loop_state["graph_paths"],
        "graph_used":    len(loop_state["graph_context"]),
        "sources":       [d.get("source", "unknown") for d in loop_state["docs"][:3]],
        # [#A6-2] web search 사용 여부 + 출처
        "web_used":      web_used,
        "web_sources":   web_sources,
        # [#65 phase 3] full chunk texts that fed the LLM, surfaced for
        # RAGAS `context_precision` / `context_recall` evaluation against
        # the live retrieval path. The /query/ endpoint admin-gates the
        # exposure; consumers outside the endpoint already see the same
        # data via `loop_state["docs"]` if they hold the engine.
        "retrieved_contexts": [d.get("text", "") for d in loop_state["docs"]],
        "blocked":       False,
        "timing_sec":    round(total, 2),
        "unified_score": round(unified_score if "unified_score" in dir() else 0.0, 3),
        "loop_count":    min(MAX_LOOP + 1, 3),
    }
