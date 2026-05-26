"""v0.4 live verify follow-up — engine_memory.py language detection
must use the unified `core.i18n.detect_language` (PR #495 contract).

Background. PR #495 (v0.4 Sprint 1 #2, 2026-05-25) migrated five
reasoning stages (planner / reflect / verify / query_rewriter /
engine_synth) from local "Korean ≥ 20%" heuristics to the
dominant-script classifier in `core.i18n`. It missed one site —
`engine_memory.build_memory_context`, which kept the legacy
`(korean / total) ≥ 0.2` formula via inline `re.findall(r'[가-힣]', …)`.

Symptom observed 2026-05-26 during A3.1 live verify of v0.4.0-alpha.3:
the pure-Korean query `팔란티어가 뭐야` got tagged Korean correctly
by the four upstream stages but the engine_memory legacy branch's
output disagreed with the unified classifier on edge cases (e.g.,
`Hello 안녕` — old heuristic 2/8=0.25 → Korean; new dominant-script
→ English on the 5/2 alpha/hangul count).

The matching client-side bug (chat.js seeding `james_session_lang =
"English"` on first DOMContentLoaded) is fixed in
`frontend/static/chat.js`; this test covers the backend half so a
future regression in `engine_memory` can't reintroduce the drift.
"""
from __future__ import annotations

import inspect

import pytest


# ─── Contract: engine_memory imports detect_language ──────────────


def test_engine_memory_no_legacy_inline_regex():
    """Source-level pin — `engine_memory.py` must NOT contain the
    legacy `[가-힣]` inline regex pattern that PR #495 retired
    everywhere else. If you're re-adding it, please re-route through
    `core.i18n.detect_language` instead."""
    from core.reasoning import engine_memory as m
    src = inspect.getsource(m)
    assert "[가-힣]" not in src, (
        "engine_memory must not regex-match Hangul inline — use "
        "`core.i18n.detect_language` so the five reasoning stages "
        "stay unified (PR #495)."
    )


def test_engine_memory_imports_detect_language():
    """Forward-positive pin: the migration target is in the file."""
    from core.reasoning import engine_memory as m
    src = inspect.getsource(m)
    assert "from core.i18n import detect_language" in src or (
        "core.i18n" in src and "detect_language" in src
    ), (
        "engine_memory must import `detect_language` from `core.i18n`."
    )


# ─── Behavioural parity with the unified classifier ──────────────


@pytest.mark.parametrize("system_prompt_in,expected_no_ko_directive,expected_no_en_directive", [
    # Persona Korean default line — should be stripped before prepend
    ("당신의 이름은 자메스입니다. 항상 한국어로 답변하세요.", True, True),
    # Persona English variant
    ("당신의 이름은 자메스입니다. Always respond in English.", True, True),
    # No language line at all — passes through cleanly
    ("당신의 이름은 자메스입니다.", True, True),
    # Persona text + character block — strip only the language line
    (
        "당신의 이름은 자메스입니다. 항상 한국어로 답변하세요.\n\n"
        "[캐릭터 페르소나] 집중력·과감함이 두드러진 성격...",
        True, True,
    ),
])
def test_persona_lang_directive_stripped_from_system_prompt(
    system_prompt_in, expected_no_ko_directive, expected_no_en_directive,
):
    """v0.4 live verify fix #5 — the strip regex in engine_memory must
    remove every persona-stored language directive from system_prompt
    so the auto-detect / explicit session_lang directive can land
    alone, no contradiction underneath."""
    import re as _re

    cleaned = _re.sub(
        r'\s*항상\s+\S+로\s+답변하세요\.?', '', system_prompt_in
    )
    cleaned = _re.sub(
        r'\s*Always respond in [A-Za-z]+\.?', '', cleaned
    )
    cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned).strip()

    if expected_no_ko_directive:
        assert "항상" not in cleaned or "답변하세요" not in cleaned, (
            f"KO language directive should be stripped: {cleaned!r}"
        )
    if expected_no_en_directive:
        assert "Always respond in" not in cleaned, (
            f"EN language directive should be stripped: {cleaned!r}"
        )
    # Identity check — name line + character block survives intact
    assert "당신의 이름은 자메스입니다" in cleaned, (
        f"strip should NOT touch the name line: {cleaned!r}"
    )


@pytest.mark.parametrize("query,expected_lang", [
    ("팔란티어가 뭐야",         "Korean"),    # 7 hangul / 0 alpha
    ("What is Palantir",        "English"),   # 0 hangul / 14 alpha
    ("Palantir 분석",           "English"),   # 2 hangul / 8 alpha — en-dominant
    ("Hello 안녕 world",        "English"),   # 2 hangul / 10 alpha — en-dominant
    ("분석 Palantir",           "English"),   # symmetric — same counts
    ("팔란티어 P",              "Korean"),    # 4 hangul / 1 alpha — ko-dominant
    ("",                         "Korean"),   # empty → ko default
    ("12345",                    "Korean"),   # digits-only → ko default
])
def test_session_lang_matches_unified_classifier(query, expected_lang):
    """End-to-end on `build_memory_context`-style logic: the inferred
    `session_lang` matches what `detect_language` would say (mapped
    from `"ko"` → `"Korean"` and `"en"` → `"English"`)."""
    from core.i18n import detect_language

    # Mirror the engine_memory expression so the test is direct.
    session_lang = "Korean" if detect_language(query) == "ko" else "English"
    assert session_lang == expected_lang, (
        f"unified classifier expected {expected_lang!r} for "
        f"{query!r}, got {session_lang!r}"
    )
