"""``handle_chat`` — direct-LLM mode, no retrieval.

Extracted from the monolithic ``core/reasoning/modes.py`` in the
v0.3.x rule-#5 split. Body is byte-identical to the pre-split version;
only the ``CONTINUITY_DIRECTIVE_*`` imports moved into ``._common``.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict

from core.reasoning.trace_helpers import trace_synth_call

from ._common import CONTINUITY_DIRECTIVE_KO, CONTINUITY_DIRECTIVE_EN


# ────────────────────────────────────────────────────────────────────
# chat — direct LLM, no retrieval
# ────────────────────────────────────────────────────────────────────
def handle_chat(
    engine,
    safe_query: str,
    system_prompt: str,
    memory_context: str,
    user_role: str,
    t_start: float,
    response_style: str = "",
    selected_model: str = "",   # [#A2 phase 2] catalog-validated user pick
    hist_ctx: str = "",         # [N-3 2026-05-13] current-session prior turns only
) -> Dict[str, Any]:
    from core.response_style import resolve_style
    style = resolve_style(response_style)

    # Detect language by Korean character ratio to pick the
    # right-language flow guide. Same heuristic as engine._generate_answer.
    korean_chars = sum(1 for c in safe_query if "가" <= c <= "힣")
    is_ko = korean_chars >= max(1, len(safe_query) * 0.2)
    rule_txt = style.rule_text_ko if is_ko else style.rule_text_en

    t_direct = time.time()
    try:
        # system_prompt + memory_context + flow guide 주입
        sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
        # [N-3 2026-05-13] Gate the continuity directive on
        # ``hist_ctx`` — the *current* session's prior turns — not on
        # the union ``memory_context`` which also blends long-term
        # session summaries and stored preferences. Previously a brand-
        # new session with prior-session summaries would still fire
        # the directive: greetings were suppressed and the LLM resolved
        # "위/이것/그것" against other sessions' content, surfacing
        # as "새 세션인데 일상 인사가 안 됨 + 이전 세션 답변이 새 세션
        # 에서 나오는 현상" (handover §3 사이클 1 N-3).
        # ``memory_context`` is still passed into the prompt below —
        # long-term summaries remain useful background — but only an
        # actual current-session continuation activates the rule.
        if hist_ctx:
            continuity_rule = CONTINUITY_DIRECTIVE_KO if is_ko else CONTINUITY_DIRECTIVE_EN
            mem_prefix = f"{continuity_rule}\n\n{memory_context}\n\n"
        elif memory_context:
            mem_prefix = f"{memory_context}\n\n"
        else:
            mem_prefix = ""
        _chat_prompt = f"{sys_prefix}{mem_prefix}{rule_txt}\n질문: {safe_query}\n\n답변:"
        raw_answer = trace_synth_call(
            _chat_prompt,
            applied_rule="reasoning.synth.chat",
            user_role=user_role,
            use_cache=True,
            timeout=60,
            max_tokens=style.max_tokens,
            model=selected_model or None,
        )
        # Preserve paragraph breaks (\n\n) — user feedback wants
        # natural 문단 separation, not a single block of text.
        # Collapse 3+ newlines to exactly 2 to keep things tidy.
        if raw_answer:
            answer = re.sub(r"\n{3,}", "\n\n", raw_answer).strip()
        else:
            answer = ""
        if not answer or any(answer.startswith(p) for p in engine._LLM_ERROR_PREFIXES):
            answer = "죄송합니다. 답변을 생성하지 못했습니다."
    except Exception as e:
        engine._log("direct_llm", e, user_role)
        answer = "죄송합니다. 답변 생성 중 오류가 발생했습니다."
    engine._elapsed(t_direct, "DIRECT_LLM(chat)")

    # Memory 추출 + 저장 (응답에 영향 없음)
    try:
        from core.memory import extract_memory, validate_memory
        from core.memory import MemoryStore
        candidate = extract_memory(safe_query, answer)
        if validate_memory(candidate):
            MemoryStore().save(candidate)
            print(f"[MEMORY] 저장: {candidate['type']}")
    except Exception as e:
        engine._log("memory_extract", e, user_role)

    return {
        "answer":        answer,
        "mode":          "chat",
        "graph_paths":   [],
        "graph_used":    0,
        "sources":       [],
        "blocked":       False,
        "timing_sec":    round(time.time() - t_start, 2),
        "unified_score": 0.0,
        "loop_count":    0,
    }


__all__ = ["handle_chat"]
