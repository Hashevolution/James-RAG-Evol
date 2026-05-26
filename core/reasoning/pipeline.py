"""RAG retrieval pipeline — orchestrator only.

Originally extracted from ReasoningEngine.query() (#29 phase 3/3). After
Phase 1 PR-1 (reranker) + PR-2 (query rewriter) the file grew past the
20 KB CLAUDE.md rule #5 gate, so the loop bodies and the synth block
moved out:

  * Loop 0/1/2 step bodies → ``core/reasoning/pipeline_loops.py``
  * LLM answer-generation block (web fallback / retry / canonical RAG)
    → ``core/reasoning/pipeline_synth.py``

This module keeps the orchestration: STEP 0.5b query rewrite, loop
dispatch, post-loop context combine + unified_score, post_check +
sources header, delegate-to-synth, output filter, Memory Loom save,
timing, and the final result dict assembly.

Pipeline stages (in order):
  1. STEP 0.5b query rewrite (Phase 1 PR-2, opt-in)
  2. Loop state init
  3. Loop 0 retrieve → Loop 1 expand → Loop 2 verify (MAX_LOOP=2 fixed)
  4. Final context combine + unified_score v3
  5. post_check (security)
  6. LLM answer generation (delegated to pipeline_synth.generate_answer)
  7. Output filter (role-based)
  8. Memory Loom conditional save
  9. Timing print + result dict
"""
from __future__ import annotations

import time
from typing import Any, Dict

from core.reasoning.engine import MAX_LOOP, LOOP_TIMEOUT, TIMING_TARGET_SEC
from core.reasoning.pipeline_context import (
    apply_post_check_and_sources_header,
    build_unified_context,
)
from core.reasoning.pipeline_loops import (
    run_loop_0_retrieve, run_loop_1_expand, run_loop_2_verify,
)
from core.reasoning.pipeline_synth import generate_answer
from core.security_layer import filter_answer_by_role


def run_retrieval_pipeline(
    engine,
    safe_query: str,
    system_prompt: str,
    user_role: str,
    source_type: str,
    t_start: float,
    response_style: str = "",
    force_web_search: bool = False,   # [#A8-6] 사용자가 chip 클릭 시 True
    selected_model: str = "",         # [#A2 phase 2] catalog-validated user pick
) -> Dict[str, Any]:
    # ── STEP 0.5b: query rewrite (Phase 1 PR-2) ─────────
    # Cognitive Layer §5.7.1 Query Rewriter. Replaces the historical
    # no-op kept here since v0.1 (the slot was reserved for this).
    # Opt-in via JAMES_ENABLE_QUERY_REWRITE=1 — default OFF so a stock
    # JAMES install pays no extra LLM round-trip per query. When
    # enabled, the rewriter goes through the Backend registry (L0)
    # using the local Ollama path; failures fall back to the original
    # query so the pipeline always proceeds.
    t_qexp = time.time()
    expanded_query = safe_query
    rewrite_latency_ms = 0
    rewrite_attempted = False
    try:
        from core.retrieval.query_rewriter import get_query_rewriter
        # [PR-2 시인성 개선 2026-05-18] rewriter 가 backend.complete()
        # 를 실제로 호출했는지 여부를 ``attempted`` 로 분리해서 받는다.
        # 이전엔 (query, latency) 만 받았고 trace emit 도 ``expanded !=
        # safe`` 일 때만 — 결과적으로 사용자가 env 를 켰는데도 trace
        # 가 비어 있으면 "env 도달 안 함" / "rewriter 가 silent fail"
        # / "LLM 이 의미적으로 동일한 문자열 반환" 을 구분할 수 없었다.
        expanded_query, rewrite_latency_ms, rewrite_attempted = (
            get_query_rewriter().rewrite(safe_query)
        )
    except Exception as e:
        engine._log("query_rewrite", e, user_role)
    engine._elapsed(t_qexp, "STEP0.5 query_rewrite")

    # Emit one trace step for the rewrite stage so the replay tool sees
    # rewrite → retrieve → rerank → synth in chronological order. Use
    # the existing "retrieve" stage with a descriptive applied_rule —
    # adding a "rewrite" stage to ALLOWED_STAGES would require a §5.7.2
    # schema change (architecture-labelled PR), which this PR avoids.
    #
    # Emit whenever the rewriter actually called the backend (regardless
    # of whether the output differs from the input). If the input and
    # output match we still surface the row with "no change" so the
    # operator can confirm the rewriter ran. Skipped cases (env off,
    # short query, backend lookup miss) emit nothing — those are not
    # rewrite attempts.
    if rewrite_attempted:
        try:
            from core.reasoning.trace_schema import (
                TraceStep, compute_inputs_hash, truncate_summary,
                emit_trace_step,
            )
            _changed = expanded_query != safe_query
            _rewrite_extras: Dict[str, Any] = {
                "original_query": safe_query[:200],
                "rewritten_query": expanded_query[:200],
                "changed": _changed,
            }
            try:
                from core.observability import get_trace_id
                _tid = get_trace_id()
                if _tid:
                    _rewrite_extras["trace_id"] = _tid
            except Exception:
                pass
            _summary = (
                f"{safe_query} → {expanded_query}" if _changed
                else f"no change: {safe_query}"
            )
            emit_trace_step(
                TraceStep(
                    stage="retrieve",
                    backend_id="ollama_local",
                    parent_step_id="",
                    inputs_hash=compute_inputs_hash(safe_query),
                    output_summary=truncate_summary(_summary),
                    applied_rule="reasoning.retrieve.query_rewrite",
                    latency_ms=rewrite_latency_ms,
                ),
                user_role=user_role,
                extras=_rewrite_extras,
            )
        except Exception as e:
            engine._log("query_rewrite_trace", e, user_role)

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
    # Step bodies live in pipeline_loops.py to keep this file slim;
    # the orchestrator still owns timeout coordination + timing prints.
    # ══════════════════════════════════════════
    for loop_idx in range(MAX_LOOP + 1):
        t_loop = time.time()

        # 루프 단계별 timeout 감시
        if time.time() - t_start > LOOP_TIMEOUT * (loop_idx + 1):
            print(f"[LOOP] Loop-{loop_idx} TIMEOUT → 조기 종료")
            break

        if loop_idx == 0:
            run_loop_0_retrieve(engine, loop_state, safe_query, user_role, source_type)
        elif loop_idx == 1:
            run_loop_1_expand(engine, loop_state, safe_query, user_role, source_type)
        elif loop_idx == 2:
            run_loop_2_verify(engine, loop_state, user_role)

        engine._elapsed(t_loop, f"LOOP-{loop_idx}")

    # ── 최종 컨텍스트 결합 + Post-check + sources header ──
    # Extracted to pipeline_context.py (chore/v0.4-pipeline-split).
    # `build_unified_context` returns (final_context, unified_score)
    # after running the unified_score v3 + graph context build;
    # `apply_post_check_and_sources_header` runs the security post_check
    # and prepends the [관련 자료 목록] header for citation hinting.
    # Both helpers preserve the v0.3.0+L.C behaviour byte-identical —
    # this split is module-size hygiene (CLAUDE.md rule #5), not a
    # semantic change.
    final_context, unified_score = build_unified_context(
        engine, loop_state, user_role,
    )
    safe_context = apply_post_check_and_sources_header(
        engine, loop_state, final_context, user_role,
    )

    # ── LEO L.C — evidence-scope measurement + scope-context bind ───
    # When JAMES_SCOPE_ROUTING is ON, compute the post-Loop-1 scope
    # from loop_state (docs / graph_context / graph_paths populated by
    # Loops 0 and 1 above) and bind it via `scope_context(...)` so any
    # synth-layer LLM call inside the `with` block can read it via
    # `evidence_scope.get_current_scope()` and pick a scope-appropriate
    # backend (LEO L.B router policy v1).
    #
    # Flag-OFF invariant: `scope_routing_enabled()` returns False →
    # `_scope_breakdown` stays None → `scope_context(None)` is a no-op
    # binding → trace_helpers reads None → resolve_backend gets
    # `evidence_scope=None` → router falls back to D5 budget policy →
    # byte-identical to post-L.B main.
    #
    # `chat` / `meta` / `wiki_edit` / `self_evolve` / `coding` modes
    # never reach this point (mode dispatch in engine._query_impl
    # routes them to `handle_*` helpers before run_retrieval_pipeline),
    # so the LEO open Q #3 mode gate is naturally satisfied with no
    # extra branch here.
    from core.reasoning.evidence_scope import (
        compute_scope,
        scope_context,
        scope_routing_enabled,
    )
    _scope_breakdown = None
    if scope_routing_enabled():
        try:
            _scope_breakdown = compute_scope(
                docs=loop_state["docs"],
                graph_context=loop_state["graph_context"],
                graph_paths=loop_state["graph_paths"],
            )
            print(
                f"[SCOPE] evidence_scope={_scope_breakdown.scope:.3f} "
                f"(k={_scope_breakdown.effective_k:.2f} "
                f"H={_scope_breakdown.score_entropy:.2f} "
                f"g={_scope_breakdown.graph_reach:.2f} "
                f"s={_scope_breakdown.doc_spread:.2f})"
            )
        except Exception as e:
            engine._log("scope_compute", e, user_role)

    # ── LLM 답변 생성 (delegated to pipeline_synth) ──────
    # generate_answer handles the three-way branch (web fallback /
    # canonical RAG / no-info retry) and emits the three L1 trace
    # rows on the call_gemma sites. Returns an AnswerBlock with the
    # text + web search results + the optional save-proposal id.
    #
    # The `with scope_context(...)` wrapper covers generate_answer +
    # the reflect / verify passes that run inside it, so all five
    # synth-path trace_synth_call invocations (rag, web_summary,
    # web_fallback, retry_no_info, plus reflect/verify call sites
    # that go through trace_helpers) see the same scope.
    with scope_context(_scope_breakdown):
        _synth = generate_answer(
            engine, safe_query, safe_context, system_prompt, user_role,
            unified_score,
            response_style=response_style,
            selected_model=selected_model,
            force_web_search=force_web_search,
        )
    answer = _synth.answer
    web_results = _synth.web_results
    pending_save_proposal_id = _synth.pending_save_proposal_id

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
        # [#A8-7] chat-side "위키 저장" chip이 approve할 proposal id (있을 때만)
        "pending_save_proposal_id": pending_save_proposal_id,
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
