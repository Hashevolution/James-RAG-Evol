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


# 2026-09-28 — rules rewritten after the annotation axis (#1161) caught
# this check flagging correct core answers as unsupported, 5 times in 3
# runs: "BTC와 비트코인은 같은 디지털 자산을 지칭한다", "Anthropic …
# develops … Claude". Two causes, both in the old wording:
#
#   * "직접 지지되는지" / "directly supported" set a literal bar. The
#     evidence writing "비트코인(BTC)" does not *state* that the two are
#     the same, so the equivalence failed. reflect's critique had the
#     same fault after #1151 (Q19, reflect-off-n3-20260928.md §3).
#   * The only common-knowledge example was "AI is a technology", which
#     the model did not generalise to definitions or abbreviations.
#
# Relaxing either is how "Alex Karp is Anthropic's CEO" gets through, so
# two limits come with it: inference holds only about the SAME subject
# (the #1151 wrong-subject guard, here in verify), and common knowledge
# means definitions — never a specific entity's attributes (who runs it,
# when, how much), which are exactly what retrieval is for and exactly
# what goes stale.
FACT_CHECK_PROMPT_KO = (
    "아래 답변의 핵심 주장들이 제공된 [내부 자료] 에 의해 뒷받침되는지 "
    "검증하라.\n\n"
    "[질문]\n{query}\n\n"
    "[답변]\n{answer}\n\n"
    "[내부 자료]\n{context}\n\n"
    "검증 규칙:\n"
    "- 답변 안의 명시적 주장 (사실 / 수치 / 인용) 만 대상으로 함\n"
    "- 다음은 '뒷받침됨' 으로 통과:\n"
    "  · 자료에 그대로 적힌 내용\n"
    "  · 자료 내용을 바꿔 말하거나 번역한 것\n"
    "  · 자료에서 곧바로 따라 나오는 결론 (예: 자료가 '블랙록의 비트코인 "
    "ETF IBIT' 라고 하면 'IBIT 는 블랙록이 발행한다' 는 뒷받침됨; 자료가 "
    "'비트코인(BTC)' 이라고 쓰면 'BTC 와 비트코인은 같다' 는 뒷받침됨)\n"
    "- 용어의 정의 · 약어 · 분류처럼 변하지 않는 일반 지식은 자료에 없어도 "
    "통과 (예: 'BTC 는 비트코인의 약어', 'ETF 는 상장지수펀드')\n"
    "- 단, **특정 대상의 구체 속성** (누가 CEO 인가 · 언제 설립됐나 · 수치 · "
    "날짜 · 누가 발행/개발하는가) 은 일반 지식으로 통과시키지 말고 자료로만 "
    "판정하라.\n"
    "- 결론은 **같은 대상**에 대해서만 성립한다. 자료가 다른 대상에 대해 "
    "말하는 사실을 근거로 삼지 마라 (예: 자료에 'Palantir CEO Alex Karp' "
    "만 있으면 'Anthropic 의 CEO 는 Alex Karp' 는 unsupported).\n"
    "- 위 어디에도 해당하지 않거나 자료와 모순되는 주장만 'unsupported'\n\n"
    "JSON 으로만 응답하라:\n"
    '{{"grounded": true|false, "unsupported": ["짧은 주장 1", "..."]}}'
)

FACT_CHECK_PROMPT_EN = (
    "Verify whether the key claims in the answer are supported by the "
    "[Internal Data] below.\n\n"
    "[Question]\n{query}\n\n"
    "[Answer]\n{answer}\n\n"
    "[Internal Data]\n{context}\n\n"
    "Rules:\n"
    "- Only check explicit claims (facts, numbers, citations) inside "
    "the answer\n"
    "- These count as SUPPORTED and pass:\n"
    "  · what the data states\n"
    "  · a paraphrase or translation of what the data states\n"
    "  · a conclusion that follows directly from the data (e.g. if the "
    "data says 'BlackRock's bitcoin ETF IBIT', then 'BlackRock issues "
    "IBIT' is supported; if it writes 'Bitcoin (BTC)', then 'BTC and "
    "Bitcoin are the same' is supported)\n"
    "- Stable general knowledge — definitions, abbreviations, "
    "categories — passes without data support (e.g. 'BTC is the ticker "
    "for Bitcoin', 'an ETF is an exchange-traded fund')\n"
    "- BUT a **specific entity's attributes** (who its CEO is, when it "
    "was founded, figures, dates, who issues or develops what) are NOT "
    "general knowledge: judge them against the data only.\n"
    "- A conclusion holds only about the **same subject**. Do not use a "
    "fact the data states about a different entity as support (e.g. if "
    "the data mentions only 'Palantir CEO Alex Karp', then 'Anthropic's "
    "CEO is Alex Karp' is unsupported).\n"
    "- Only claims that fit none of the above, or contradict the data, "
    "go into 'unsupported'\n\n"
    "Respond with JSON only:\n"
    '{{"grounded": true|false, "unsupported": ["short claim 1", "..."]}}'
)
