"""Loop 0 / 1 / 2 step functions extracted from pipeline.py for size cleanup.

CLAUDE.md rule #5 module-size gate: pipeline.py grew past 33 KB after
Phase 1 PR-1 (reranker) + PR-2 (query rewriter). This module hosts the
three loop-step bodies so the outer ``run_retrieval_pipeline`` orchestrator
stays slim. Behaviour is byte-identical to v0.3.0 + Phase 1 PR-1/PR-2 —
this is a pure refactor (the test suite is the contract).

Each step takes the engine instance + a shared ``loop_state`` dict that
the orchestrator initialises before the loop and reads after. Each step
mutates ``loop_state`` in place — matching the original in-loop pattern
where local writes against ``loop_state[...]`` propagated to subsequent
iterations and to the post-loop context-combine block.

Three steps:
  - ``run_loop_0_retrieve`` — orchestrator hybrid_search + cross-encoder
    rerank (Phase 1 PR-1) + retrieve audit row
  - ``run_loop_1_expand``    — entity extraction + graph DFS + ABAC graph
    filter + graph audit row
  - ``run_loop_2_verify``    — ABAC consistency check + optional tool
    execution (placeholder for Phase 2)
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict

from core.observability import log_stage


def run_loop_0_retrieve(
    engine,
    loop_state: Dict[str, Any],
    safe_query: str,
    user_role: str,
    source_type: str,
) -> None:
    """Loop 0 — orchestrator-driven retrieval + cross-encoder rerank.

    Returns nothing; ``loop_state`` is mutated in place with:
      - ``docs``            — top-5 reranked docs (or vector-order
                              fallback when rerank is disabled / fails)
      - ``doc_context``     — concatenated text block built by
                              ``RetrievalEngine.build_doc_context``
      - ``avg_vec_score``   — average vector score over docs
    """
    print("\n[LOOP-0] retrieve (Orchestrator)")
    # α-6 S1 sector ablation — `JAMES_DISABLE_RAG_RETRIEVAL=1` skips
    # vector + BM25 retrieval entirely. The model receives no
    # retrieved context (must answer from parametric knowledge or
    # refuse). Used by α-6 cell `C_minus` (pure LLM baseline).
    if os.environ.get("JAMES_DISABLE_RAG_RETRIEVAL") == "1":
        loop_state["docs"] = []
        loop_state["doc_context"] = ""
        loop_state["avg_vec_score"] = 0.0
        log_stage("retrieve", top_k=0, avg_vec_score=0.0,
                  top_vector_score=0.0, top_bm25_score=None,
                  source_type=source_type, sector_disabled=True)
        print("  docs=0 (S1 disabled — JAMES_DISABLE_RAG_RETRIEVAL=1)")
        return
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

    # ── Phase 1 PR-1: cross-encoder rerank ─────────
    # orchestrator returns 8 docs by vector score; the reranker
    # scores each (query, doc.text) pair and reorders. The
    # original [:5] truncation now happens *inside* rerank()
    # so the top-5 reflects rerank order, not vector order.
    #
    # JAMES_DISABLE_RERANK=1 or model load failure → rerank()
    # returns docs[:top_k] unchanged → byte-identical to v0.3.0.
    t_rerank = time.time()
    pre_rerank_count = len(docs)
    try:
        from core.retrieval.rerank import get_reranker
        docs = get_reranker().rerank(safe_query, docs, top_k=5)
    except Exception as e:
        engine._log("loop0_rerank", e, user_role)
        docs = docs[:5]
    rerank_ms = int((time.time() - t_rerank) * 1000)

    # Emit one trace step for the rerank stage so the replay
    # tool sees the cognitive-layer step alongside synth rows.
    try:
        from core.reasoning.trace_schema import (
            TraceStep, compute_inputs_hash, truncate_summary,
            emit_trace_step,
        )
        top = docs[0] if docs else {}
        top_summary = (
            f"top: {(top.get('source') or top.get('name') or '?')[:60]} "
            f"rerank={top.get('rerank_score', float('nan')):.3f}"
            if docs else "no docs"
        )
        trace_extras: Dict[str, Any] = {
            "pre_rerank_count": pre_rerank_count,
            "post_rerank_count": len(docs),
        }
        try:
            from core.observability import get_trace_id
            _tid = get_trace_id()
            if _tid:
                trace_extras["trace_id"] = _tid
        except Exception:
            pass
        emit_trace_step(
            TraceStep(
                stage="rerank",
                backend_id="cross_encoder",
                parent_step_id="",
                inputs_hash=compute_inputs_hash(safe_query),
                output_summary=truncate_summary(top_summary),
                applied_rule="reasoning.rerank.cross_encoder",
                latency_ms=rerank_ms,
            ),
            user_role=user_role,
            extras=trace_extras,
        )
    except Exception as e:
        engine._log("loop0_rerank_trace", e, user_role)

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


def run_loop_1_expand(
    engine,
    loop_state: Dict[str, Any],
    safe_query: str,
    user_role: str,
    source_type: str,
) -> None:
    """Loop 1 — entity extraction + graph DFS + ABAC graph filter.

    Mutates ``loop_state`` with ``graph_context`` and ``graph_paths``.
    """
    print("\n[LOOP-1] expand")
    # α-6 S2 sector ablation — `JAMES_DISABLE_GRAPH=1` skips graph
    # traversal entirely. Vector RAG (`loop_state["docs"]`) still runs.
    # Used by α-6 cells `C_minus` / `C_rag-basic` / `C_rag-cited`.
    if os.environ.get("JAMES_DISABLE_GRAPH") == "1":
        loop_state["graph_context"] = []
        loop_state["graph_paths"]   = []
        log_stage("graph", entities_extracted=0, entity_ids_matched=0,
                  valid_entity_ids=0, graph_nodes=0, paths_walked=0,
                  sector_disabled=True)
        return
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


def run_loop_2_verify(
    engine,
    loop_state: Dict[str, Any],
    user_role: str,
) -> None:
    """Loop 2 — ABAC consistency check + optional tool execution.

    Tool execution is gated on ``loop_state["pending_actions"]`` —
    historically a placeholder. Phase 2 PR-8 (Tool Router) will
    populate it.
    """
    print("\n[LOOP-2] verify")
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


__all__ = [
    "run_loop_0_retrieve",
    "run_loop_1_expand",
    "run_loop_2_verify",
]
