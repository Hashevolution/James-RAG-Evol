"""Verifier constants, messages and the fact-check prompts.

Split out of the single-file ``core/reasoning/verify.py`` on 2026-09-26.
The file had reached 20,008 B against CLAUDE.md rule #5's 20 KB cap —
472 B of headroom — so it could not take another line. Same shape as the
v0.6 ``core/reasoning/reflect/`` split; ``__init__`` re-exports the
pre-split surface, so the move is a no-op for callers.
"""
from __future__ import annotations

from core.reasoning.backends import get_default_backend_id as _get_default_backend
DEFAULT_BACKEND_ID = _get_default_backend()
DEFAULT_FACT_CHECK_TIMEOUT_S = 30.0
# gemma4:e4b consumes ~500 hidden reasoning tokens before the first
# visible output on short structured prompts; cap below that floor
# → deterministic empty response (model burns the budget without
# surfacing any byte).
DEFAULT_FACT_CHECK_MAX_TOKENS = 4096

# 2026-09-27 — this number used to be a floor on *whether to verify at
# all*: `len(answer) < 30 → return accept`, skipping the security scan
# and the fact check together. It was backwards. A short answer is
# usually a bare factual claim, which is the kind that most needs
# grounding — the 9-character "Alex Karp" (Palantir's CEO, offered as
# Anthropic's) went out unverified because of it.
#
# Same number, opposite job: an answer at or under this length is
# treated as a **single bare claim**, so one unsupported claim means the
# whole answer is unsupported and annotation does not wait for
# ANNOTATE_THRESHOLD.
BARE_CLAIM_ANSWER_CHARS = 30

# Retained for the pre-2026-09-27 import surface. No longer gates
# anything — `verify()` now short-circuits only on an empty answer.
MIN_ANSWER_LEN_FOR_VERIFY = 30

# An "unsupported claim" count at or above this triggers annotation.
# The threshold exists so one borderline claim inside a long answer
# does not attach a warning to an otherwise sound response. It does not
# apply to a bare claim — see BARE_CLAIM_ANSWER_CHARS.
ANNOTATE_THRESHOLD = 2


_BLOCK_MSG_KO = (
    "(보안 검증: 응답에서 신뢰할 수 없는 출처의 지시 흔적이 감지되어 "
    "차단되었습니다. 질문을 다시 표현해 주세요.)"
)
_BLOCK_MSG_EN = (
    "(Security verification: the response contained instruction "
    "echoes from an untrusted source and was blocked. Please "
    "rephrase the question.)"
)


FACT_CHECK_PROMPT_KO = (
    "아래 답변의 핵심 주장들이 제공된 [내부 자료] 에 의해 직접 지지되는지 "
    "검증하라.\n\n"
    "[질문]\n{query}\n\n"
    "[답변]\n{answer}\n\n"
    "[내부 자료]\n{context}\n\n"
    "검증 규칙:\n"
    "- 답변 안의 명시적 주장 (사실 / 수치 / 인용) 만 대상으로 함\n"
    "- 자료가 지지하는 주장은 통과; 자료에 없거나 모순되는 주장만 'unsupported'\n"
    "- 일반 상식 (예: 'AI 는 기술이다') 은 자료에 없어도 통과\n\n"
    "JSON 으로만 응답하라:\n"
    '{{"grounded": true|false, "unsupported": ["짧은 주장 1", "..."]}}'
)

FACT_CHECK_PROMPT_EN = (
    "Verify whether the key claims in the answer are directly "
    "supported by the [Internal Data] below.\n\n"
    "[Question]\n{query}\n\n"
    "[Answer]\n{answer}\n\n"
    "[Internal Data]\n{context}\n\n"
    "Rules:\n"
    "- Only check explicit claims (facts, numbers, citations) inside "
    "the answer\n"
    "- Claims the data supports → pass; only claims that the data "
    "lacks or contradicts go into 'unsupported'\n"
    "- General common knowledge (e.g., 'AI is a technology') passes "
    "even without data support\n\n"
    "Respond with JSON only:\n"
    '{{"grounded": true|false, "unsupported": ["short claim 1", "..."]}}'
)
