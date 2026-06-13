"""Abstention-softener triggers + retry-prompt builder.

Extracted from the legacy single-file ``core/reasoning/pipeline_synth.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

cycle γ Phase D2 — softener triggers + retry prompt. Helpers are
module-level so the contract is unit-testable without instantiating
the engine. JAMES_SOFTENER_BILINGUAL=1 is the only new env knob;
default OFF keeps Korean-only behaviour byte-identical to
pre-Phase-D2. Path D positioning honoured: this fills a design gap
(cross-lingual coverage) without taking JAMES into the HALT-RAG
specialty-verifier category. See
memory/feedback_path_d_james_not_specialty_verifier.md.
"""
from __future__ import annotations


_KOREAN_NO_DATA_TRIGGERS: tuple = (
    "자료에 없음. 관련된",
    "답변 생성에 실패",
    "LLM 응답 생성 중 오류",
)

# English abstention triggers mirror the RGB scorer's _ABSTENTION_EN
# pattern set (core/reasoning/../external/rgb_scorer.py) so the
# softener fires on the same set of model outputs that the published
# RGB benchmark scores as "abstention" — keeps end-to-end semantics
# consistent across the JAMES pipeline + the external scorer it's
# being evaluated against. NOT a HALT-RAG-style NLI verifier — just
# a startswith() trigger mirror, axis-aligned with abst_f1 primary.
_ENGLISH_NO_DATA_TRIGGERS: tuple = (
    "Insufficient information",
    "Insufficient context",
    "Insufficient evidence",
    "I cannot find",
    "I can not find",
    "I can't find",
    "I cannot answer",
    "I can not answer",
    "I can't answer",
    "I cannot determine",
    "I can not determine",
    "I can't determine",
    "I don't know",
    "I do not know",
    "Unable to answer",
    "Unable to determine",
    "No information available",
    "No relevant information",
    "Not enough information",
)


def _abstention_triggers(*, bilingual: bool) -> tuple:
    """Return the tuple of answer-prefix substrings that trigger the
    softener retry pass.

    Default = Korean only (back-compat with pre-Phase-D2 deployments).
    ``bilingual=True`` adds English equivalents mirroring the RGB
    scorer's abstention pattern set — closes the Korean-only design
    gap surfaced by Phase B+C+D measurement on RGB-en.
    """
    if bilingual:
        return _KOREAN_NO_DATA_TRIGGERS + _ENGLISH_NO_DATA_TRIGGERS
    return _KOREAN_NO_DATA_TRIGGERS


def _build_retry_prompt(
    *,
    sys_prefix: str,
    rule_text: str,
    query: str,
    is_korean: bool,
    bilingual: bool,
) -> str:
    """Build the retry-no-info prompt in the query's language.

    Pre-Phase-D2 path = Korean-only prompt regardless of query
    language. With ``bilingual=True`` AND English query
    (``is_korean=False``), the prompt scaffolding switches to
    English so the model isn't asked an English question with a
    Korean parenthetical and a Korean "답변:" prompt — both of
    which empirically derailed RGB-en query #3 in the Phase D
    measurement.

    Korean queries always get the Korean prompt (regardless of
    ``bilingual``) — back-compat preserved.
    """
    if is_korean or not bilingual:
        return (
            f"{sys_prefix}{rule_text}\n"
            f"질문: {query}\n\n"
            "(내부 자료에는 직접 언급이 없습니다. "
            "위 가이드를 따라 자연스럽게 답하세요.)\n답변:"
        )
    # bilingual=True + English query → English scaffold
    return (
        f"{sys_prefix}{rule_text}\n"
        f"Question: {query}\n\n"
        "(The internal materials do not contain a direct mention. "
        "Follow the guide above to respond naturally — if you cannot "
        "answer from the provided context, say so explicitly.)\n"
        "Answer:"
    )


__all__ = [
    "_KOREAN_NO_DATA_TRIGGERS",
    "_ENGLISH_NO_DATA_TRIGGERS",
    "_abstention_triggers",
    "_build_retry_prompt",
]
