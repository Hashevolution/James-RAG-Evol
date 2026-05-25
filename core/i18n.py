"""Language detection helpers — single source of truth.

v0.4 Sprint 1 #2 (2026-05-25). Before this module, four reasoning
stages (planner / reflect / verify / query_rewriter) each defined
their own `_is_korean(text)` with the heuristic *"Korean characters
≥ 20% of text length"*, while `engine_synth.py` used a different
heuristic *"English alphabetic chars > 50% → English, else Korean"*.
The two paths disagreed on mixed Korean/English queries (e.g.
"Palantir 분석"), causing the synth stage to occasionally emit an
English answer for a query that the upstream stages had already
classified as Korean.

This module unifies both paths under one contract:

  - `detect_language(text)` → `"ko"` or `"en"`. Dominant-script
    classification: whichever count (Korean syllable blocks vs
    Latin alphabetic chars) is larger wins. Ties + empty / digit-
    only text default to `"ko"` (operator's primary language).

  - `is_korean(text)` → `bool`. Thin shim returning
    `detect_language(text) == "ko"`. Mirrors the function name
    the four pre-D6 reasoning stages already used, so the migration
    is a one-line import swap.

The default-to-Korean tie-break is deliberate: JAMES's primary
operator is a Korean speaker, and mixed-language queries on a
Korean operator's terminal are almost always Korean-intent with
foreign-language entity names embedded ("Palantir 분석" — the
"분석" is the user-facing language). Same default lands by chance
in the legacy `_is_korean` heuristic (anything with ≥ 20% Korean
chars was classified Korean even if the rest was English).
"""

from __future__ import annotations

_KO_SYLLABLE_START = "가"
_KO_SYLLABLE_END = "힣"


def detect_language(text: str) -> str:
    """Classify a text as `"ko"` or `"en"` by dominant script.

    The two character counts:
      - Korean = the Hangul syllable block range U+AC00–U+D7A3
        (``"가"`` through ``"힣"``). Jamo (U+1100–U+11FF) is not
        counted — virtually all user text uses precomposed
        syllables.
      - English = ASCII alphabetic characters (``str.isascii()``
        AND ``str.isalpha()``), case-insensitive.

    Tie-breaking: ties or zero counts (digits-only / symbols-only /
    empty) → ``"ko"``. This matches the legacy `_is_korean` default-
    Korean behavior for non-textual inputs and prevents a
    classifier flip on borderline content.

    No external dependencies (no langdetect / fasttext / etc.) — the
    heuristic is intentionally cheap and deterministic so it runs
    on every reasoning-stage prompt without overhead.
    """
    if not text:
        return "ko"
    korean_chars = sum(
        1 for c in text
        if _KO_SYLLABLE_START <= c <= _KO_SYLLABLE_END
    )
    en_chars = sum(
        1 for c in text
        if c.isascii() and c.isalpha()
    )
    if korean_chars == 0 and en_chars == 0:
        return "ko"
    if korean_chars >= en_chars:
        return "ko"
    return "en"


def is_korean(text: str) -> bool:
    """Convenience predicate — mirror of legacy `_is_korean(text)`.

    Returns True when `detect_language(text) == "ko"`. Empty / digit-
    only / tied counts → True (default-to-Korean tie-break, same
    as `detect_language`).
    """
    return detect_language(text) == "ko"


__all__ = ["detect_language", "is_korean"]
