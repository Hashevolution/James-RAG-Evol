"""F9.3 — pipeline STEP 0.5a entity anchor expansion helper.

Extracted from ``pipeline.py`` to keep that module under the 20 KB
CLAUDE.md rule #5 cap (PR-T7.C left ~3 KB headroom; F9.3 wiring +
trace emission ate into it). Mirrors the PR #518 split pattern
(``pipeline_context.build_unified_context`` /
``apply_post_check_and_sources_header``).

What this helper does
---------------------

1. Read the ``JAMES_ENABLE_ENTITY_ANCHOR`` env flag.
2. If set, run the query through ``EntityAnchorExpander`` and capture
   ``(expanded, anchors, hit)``.
3. Emit a trace step (``applied_rule="reasoning.retrieve.entity_anchor_expand"``)
   when the expander returned a hit so the operator can see anchor
   contribution distinctly from the LLM rewriter's downstream trace.
4. Return ``(query_for_rewriter, anchors_added, hit)`` — the caller
   (``pipeline.py``) feeds ``query_for_rewriter`` into STEP 0.5b's
   ``QueryRewriter.rewrite()``.

Flag-OFF invariant
------------------

When ``JAMES_ENABLE_ENTITY_ANCHOR`` is unset / not "1":
  - ``query_for_rewriter == safe_query`` byte-identical
  - ``anchors_added == []``
  - ``hit == False``
  - no audit trace row emitted

→ pipeline.py's downstream behaviour is byte-identical to pre-F9.3 main.

Failure isolation
-----------------

Every exception path is logged via ``engine._log`` and falls back to
the unchanged ``safe_query`` — F9.3 must not block retrieval if the
expander or its index build fails. Mirrors the rewriter's pre-existing
fallback discipline.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple


def apply_entity_anchor_expansion(
    engine,
    safe_query: str,
    user_role: str,
) -> Tuple[str, List[str], bool]:
    """Run STEP 0.5a entity-anchor pre-expansion. See module docstring.

    Returns ``(query_for_rewriter, anchors_added, hit)``.
    """
    query_for_rewriter = safe_query
    anchors_added: List[str] = []
    hit = False
    latency_ms = 0
    try:
        from core.retrieval.entity_anchor_expander import (
            entity_anchor_enabled, get_entity_anchor_expander,
        )
        if entity_anchor_enabled():
            t_anchor = time.time()
            try:
                expanded_text, anchors_added, hit = (
                    get_entity_anchor_expander().expand(safe_query)
                )
                if hit:
                    query_for_rewriter = expanded_text
            except Exception as e:
                engine._log("entity_anchor_expand", e, user_role)
            latency_ms = int((time.time() - t_anchor) * 1000)
            engine._elapsed(t_anchor, "STEP0.5a entity_anchor")
    except Exception as e:
        # Module-import failure (extremely defensive — should never
        # fire because the import is in tree at this point).
        engine._log("entity_anchor_module_import", e, user_role)

    if hit:
        _emit_anchor_trace_step(
            engine=engine,
            safe_query=safe_query,
            query_for_rewriter=query_for_rewriter,
            anchors_added=anchors_added,
            latency_ms=latency_ms,
            user_role=user_role,
        )

    return (query_for_rewriter, anchors_added, hit)


def _emit_anchor_trace_step(
    *,
    engine,
    safe_query: str,
    query_for_rewriter: str,
    anchors_added: List[str],
    latency_ms: int,
    user_role: str,
) -> None:
    """Emit a ``retrieve``-stage trace row attributing the anchor add
    to the entity-anchor expander (distinct from the LLM rewriter's
    own trace row downstream).

    ``stage="retrieve"`` + ``backend_id="graph_local"`` lets the
    operator grep the audit_log for ``applied_rule="reasoning.
    retrieve.entity_anchor_expand"`` to count anchor-expanded queries
    in production. Mirrors the rewriter's existing trace shape so
    the diagnostic surface stays consistent.
    """
    try:
        from core.reasoning.trace_schema import (
            TraceStep, compute_inputs_hash, truncate_summary,
            emit_trace_step,
        )
        extras: Dict[str, Any] = {
            "original_query": safe_query[:200],
            "expanded_query": query_for_rewriter[:200],
            "anchors_added":  anchors_added,
            "anchor_count":   len(anchors_added),
        }
        try:
            from core.observability import get_trace_id
            tid = get_trace_id()
            if tid:
                extras["trace_id"] = tid
        except Exception:
            pass
        emit_trace_step(
            TraceStep(
                stage="retrieve",
                backend_id="graph_local",
                parent_step_id="",
                inputs_hash=compute_inputs_hash(safe_query),
                output_summary=truncate_summary(
                    f"{safe_query} → {query_for_rewriter}"
                ),
                applied_rule="reasoning.retrieve.entity_anchor_expand",
                latency_ms=latency_ms,
            ),
            user_role=user_role,
            extras=extras,
        )
    except Exception as e:
        engine._log("entity_anchor_trace", e, user_role)


__all__ = ["apply_entity_anchor_expansion"]
