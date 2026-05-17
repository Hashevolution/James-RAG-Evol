"""Canonical RAG synth extracted from engine.py (chore split).

CLAUDE.md rule #5 module-size gate: ``engine.py`` over 23 KB. This
module hosts ``_generate_answer`` (the canonical RAG-context →
LLM-answer path) plus its KO/EN prompt-shape constants and the
``no-info`` normalisation helper.

Behaviour is byte-identical to the in-method version. The
``ReasoningEngine._generate_answer`` method becomes a thin
delegator so external callers (notably
``core/reasoning/pipeline_synth.py``) keep their existing
``engine._generate_answer(...)`` call shape.
"""
from __future__ import annotations

from typing import List

from core.reasoning.trace_helpers import trace_synth_call
from core.retrieval_engine import RetrievalEngine
from core.response_style import resolve_style


# RouterWrapper.call_gemma returns these strings on known failure modes
# (Gemma backend timeout / error). Synth treats them as "answer didn't
# come back"; downstream code (pipeline_synth.py retry path) checks for
# the same prefixes.
LLM_ERROR_PREFIXES = ("[Gemma 응답 없음]", "[Gemma 오류]", "LLM 응답 생성 중 오류")


NO_INFO_PATTERNS: List[str] = [
    "자료에 없음", "자료 없음", "자료에는 없", "자료에서 찾을 수 없",
    "찾을 수 없", "확인되지 않", "확인할 수 없", "언급되지 않",
    "제공되지 않", "제공된 컨텍스트에 없", "정보가 없", "정보 없",
    "어떠한 엔티티", "관련 정보가 없", "해당 정보가 없", "알 수 없", "모르겠",
]


def normalize_no_info(answer: str) -> str:
    """Prefix '자료에 없음. ' when the answer contains any of the
    NO_INFO_PATTERNS — surfaces the "no data" framing consistently for
    the pipeline retry path.
    """
    if not answer or "자료에 없음" in answer:
        return answer
    for pattern in NO_INFO_PATTERNS:
        if pattern.lower() in answer.lower():
            return f"자료에 없음. {answer}"
    return answer


def classify_query(query: str) -> str:
    """Coarse query-type tag used by some prompts. Kept for parity
    with the original engine.py helper; callers that rely on the
    exact return values must not change here without coordination.
    """
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


def generate_rag_answer(
    engine,
    question: str,
    context: str,
    system_prompt: str = "",
    response_style: str = "",
    selected_model: str = "",
) -> str:
    """RAG context + LLM 자유 추론. 한/영 자동 감지.

    ``response_style``: kept for API back-compat — v2 always returns
    the NATURAL_PRESET (single natural-flow guide, no rigid
    emoji-section template). See core/response_style.py for the
    v1→v2 redesign rationale.

    ``selected_model``: [#A2 phase 2] catalog-validated user pick.
    Empty string → use config.GEMMA_MODEL default.
    """
    style = resolve_style(response_style)

    safe_q = RetrievalEngine._sanitize(question, 300)
    sys_block = f"{system_prompt}\n\n" if system_prompt else ""

    # [P7-I18N] 언어 감지 — 영어 비율로 판단
    en_chars = sum(1 for c in question if c.isascii() and c.isalpha())
    is_en = en_chars > len(question) * 0.5 and len(question) > 3

    if is_en:
        lbl_data = "📚 Data-based"
        lbl_inf = "💡 Reasoning"
        no_data = "No relevant internal data"
        rule_txt = style.rule_text_en
    else:
        lbl_data = "📚 자료 기반"
        lbl_inf = "💡 추론"
        no_data = "관련 내부 자료 없음"
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
        # L1 wiring: trace_synth_call wraps so the canonical RAG
        # synthesis emits one reasoning audit row. Behaviour is
        # byte-identical — the helper forwards call_gemma's return
        # value untouched.
        answer = trace_synth_call(
            lambda: engine.llm.call_gemma(
                prompt, timeout=120, use_cache=True,
                max_tokens=style.max_tokens,
                model=selected_model or None,
            ),
            prompt,
            applied_rule="reasoning.synth.rag",
        )
        if not answer or any(answer.startswith(p) for p in LLM_ERROR_PREFIXES):
            return "답변 생성에 실패했습니다."
        return answer
    except Exception as e:
        engine._log("generate_answer.llm", e)
        return "LLM 응답 생성 중 오류가 발생했습니다."


__all__ = [
    "LLM_ERROR_PREFIXES",
    "NO_INFO_PATTERNS",
    "normalize_no_info",
    "classify_query",
    "generate_rag_answer",
]
