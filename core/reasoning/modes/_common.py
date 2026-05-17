"""Cross-handler constants for the modes package.

Originally lived at module top of the monolithic ``core/reasoning/modes.py``
(Axis 6 user feedback, 2026-05-12). Moved here so handlers (chat /
wiki_edit / self_evolve / coding / meta) can pull only what they need
without re-importing each other.

Today only ``chat`` uses the continuity directives. The original
module-level comment notes that a future caller (e.g. handle_meta or
handle_coding) could re-use them without re-declaring; keeping them
in a shared module preserves that intent across the split.
"""
from __future__ import annotations


# Prepended to the LLM prompt whenever previous-turn context exists.
# Suppresses the canned "안녕하세요. 자메스입니다." greeting that the
# model emits when it treats every turn as a cold start, and tells it
# how to resolve Korean / English anaphora against the immediately-
# preceding turn.
CONTINUITY_DIRECTIVE_KO = (
    "[연속 대화 규칙] 이전 대화가 이어지고 있다. "
    "'안녕하세요', '저는 자메스입니다' 같은 인사·자기소개는 생략하라. "
    "사용자가 '이것', '그것', '위', '위와 관련', '위에서' 같은 지시어를 "
    "사용하면 직전 턴의 답변·질문 내용을 참조하라."
)
CONTINUITY_DIRECTIVE_EN = (
    "[Continuity rule] This is a continuing conversation. "
    "Skip greetings and self-introductions like \"Hello\" or "
    "\"I'm JAMES\". When the user uses anaphora like \"this\", "
    "\"that\", \"the above\", \"as mentioned\", resolve it against "
    "the most recent turn in the conversation history above."
)


__all__ = [
    "CONTINUITY_DIRECTIVE_KO",
    "CONTINUITY_DIRECTIVE_EN",
]
