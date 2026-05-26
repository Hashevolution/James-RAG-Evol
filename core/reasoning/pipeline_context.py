"""Post-loop context build + post-check extracted from pipeline.py.

CLAUDE.md rule #5 module-size gate: ``pipeline.py`` hit 19 KB / 20 KB
after the LEO L.C scope-wiring addition. Any further synth-layer
addition (Sprint 5 Layer 4 invariants, scope payload extensions, etc.)
would breach. This module hosts the post-loop context combine + the
post-check + sources-header block so the outer orchestrator stays
under cap.

Two pure-helper functions, behaviour byte-identical to the in-place
blocks (this is a pure refactor; the existing test suite is the
contract).

  * ``build_unified_context`` — unified_score v3 calculation +
    graph context string assembly + final_context concat. Reads
    ``loop_state`` populated by Loops 0/1/2; returns the assembled
    context string and the unified score for downstream use.
  * ``apply_post_check_and_sources_header`` — engine.security.post_check
    + the [관련 자료 목록] prepend. Reads ``loop_state["docs"]`` for
    source names; returns the post-check'd / header-prefixed context.

Both functions take the engine + user_role to support the existing
``engine._log(...)`` error path and ``engine.security.post_check(...)``
call site. ``engine.graph.build_graph_context_str`` is the inner
graph rendering used unchanged.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Tuple

# Relevance gate threshold — mirrors the local constant pre-extraction
# and the ``_RELEVANCE_THRESHOLD`` in ``core.reasoning.evidence_scope``
# (kept synchronized; a single-source consolidation refactor would
# touch this file + evidence_scope.py + the graph_engine.py MAX_DEPTH
# consolidation candidate simultaneously, out of scope here).
_RELEVANCE_GATE: float = 0.45


def build_unified_context(
    engine,
    loop_state: Dict[str, Any],
    user_role: str,
) -> Tuple[str, float]:
    """unified_score v3 + graph context build + final_context assembly.

    Reads from ``loop_state``:
      - ``docs``           — top-k reranked retrieval docs
      - ``graph_context``  — DFS-expanded entity dicts
      - ``graph_paths``    — reasoning path strings
      - ``avg_vec_score``  — average vector similarity across docs
      - ``doc_context``    — text block built by build_doc_context

    Returns:
        ``(final_context, unified_score)`` — the concatenated text
        block ready for the post_check stage + the unified score in
        ``[0, 1]`` for the downstream "low_relevance" branch decision.

    Failure mode: any exception is logged via ``engine._log`` and the
    function returns ``(loop_state["doc_context"], 0.0)`` — same
    fallback the in-place block used.

    unified_score v3 rationale (preserved from the inline comment):
      - ChromaDB always returns results, so doc count alone is
        insufficient. avg_vec_score must clear ``_RELEVANCE_GATE``
        (0.45) for "real evidence" classification.
      - weights: doc_score 55% + vec_quality 20% + graph_score 25%
        (graph alone caps at 25% so a graph-only answer can't pretend
        it had retrieval evidence).
    """
    t_ctx = time.time()
    try:
        docs = loop_state["docs"]
        graph_ctx = loop_state["graph_context"]
        graph_pth = loop_state["graph_paths"]
        avg_vec = loop_state["avg_vec_score"]

        if avg_vec >= _RELEVANCE_GATE and len(docs) > 0:
            # gate passed → real evidence present
            doc_score = min(1.0, len(docs) / 3.0)
            vec_quality = min(1.0, (avg_vec - _RELEVANCE_GATE) / 0.25)
        else:
            # gate failed → no real evidence (doc count ignored)
            doc_score = 0.0
            vec_quality = 0.0

        graph_score = min(1.0, len(graph_pth) / 2.0)

        unified_score = (
            0.55 * doc_score
            + 0.20 * vec_quality
            + 0.25 * graph_score
        )

        graph_ctx_str = engine.graph.build_graph_context_str(
            graph_ctx,
            graph_pth,
            unified_score=unified_score,
        )
        final_context = loop_state["doc_context"] + graph_ctx_str
        gate_label = "pass" if avg_vec >= _RELEVANCE_GATE else "fail"
        print(
            f"[CONTEXT] unified={unified_score:.3f} "
            f"len={len(final_context)} (gate={gate_label} "
            f"vec={avg_vec:.3f} doc={doc_score:.2f} "
            f"graph={graph_score:.2f})"
        )
    except Exception as e:
        engine._log("context_build", e, user_role)
        final_context = loop_state["doc_context"]
        unified_score = 0.0
    engine._elapsed(t_ctx, "context_build")
    return final_context, unified_score


def apply_post_check_and_sources_header(
    engine,
    loop_state: Dict[str, Any],
    final_context: str,
    user_role: str,
) -> str:
    """Security post_check + [관련 자료 목록] sources-header prepend.

    Returns the ``safe_context`` string ready for synth. When
    post_check denies, returns an empty context (matches the in-place
    block's behaviour exactly). When the context is empty or no source
    names are available, the [관련 자료 목록] header is omitted.

    item #5-A rationale (preserved verbatim from the inline comment):
    the LLM should cite source files in its first line; rule_text
    in response_style.py instructs it to read this [관련 자료] header
    and reproduce filenames in the answer.

    Source names are truncated to the basename of the path (split on
    ``/`` and ``\\``) and capped at 60 chars to keep the header
    compact. Top 5 docs only.
    """
    try:
        sec_post = engine.security.post_check(final_context, user_role)
        safe_context = sec_post["context"] if sec_post["allowed"] else ""
    except Exception as e:
        engine._log("post_check", e, user_role)
        safe_context = final_context

    source_names = []
    seen_sources = set()
    for d in (loop_state.get("docs") or [])[:5]:
        s = d.get("source") or d.get("name") or d.get("path") or ""
        if s and s not in seen_sources:
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
    return safe_context


__all__ = [
    "build_unified_context",
    "apply_post_check_and_sources_header",
]
