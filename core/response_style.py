"""Response-style — natural-flow answer prompt.

Why this module exists (v2 — 2026-05-08 redesign)
--------------------------------------------------
v1 (PR #72) tried to control answer length via three max_token presets
(brief=600, standard=1200, detailed=2000) plus a rigid 📚/💡 two-section
template. User feedback rejected the approach: cutting tokens makes
answers feel truncated, and the emoji-labelled sections feel mechanical.

What the user wants instead: a Claude-style natural answer flow —
**core answer → supporting evidence → alternative perspective / follow-up
suggestion** — composed as connected prose, with the model picking
the right length for the question.

v2 design
---------
- Single preset (`NATURAL`). The `brief` / `standard` / `detailed` ids
  still resolve to it for backward compat (so existing API consumers
  keep working) but they all behave identically.
- `max_tokens=8192` everywhere [#A8-5 2026-05-09 — was 2000].
  User feedback: "대화 글자수가 중간에 짤리지 않고 최대한 다 나올수
  있도록". 2000 ≈ 1500 Korean characters, which truncates report-style
  multi-section answers. 8192 fits gemma's default 8K context safely
  and lets larger-context models stretch when needed. Hard ceiling
  retained as runaway-LLM defense.
- `force_two_sections=False` — no rigid template. The `rule_text_*`
  block teaches the flow as guidance, not a formatting requirement.
- Rule text instructs prose composition, explicit "do NOT use 📚/💡
  labels", and "short questions get short answers, complex questions
  get the full flow".

The module-level constants (BRIEF / STANDARD / DETAILED / VALID_STYLES)
and `resolve_style()` API are preserved so the call sites in
core/reasoning/engine.py / modes.py / pipeline.py and the
QueryRequest.response_style field continue to work without churn.

Split note (2026-08-26): the ``StylePreset`` dataclass and the three
preset instances moved to ``core/response_style_presets.py`` when this
file crossed CLAUDE.md rule #5's 20 KB ceiling. They are re-exported
below, so every existing ``from core.response_style import ...`` — the
call sites in core/reasoning/*, core/answer_style_classifier.py,
core/memory/extractor.py and routes/query.py — keeps working unchanged.
"""
from __future__ import annotations

import os

from core.response_style_presets import (  # noqa: F401  (re-export)
    BRIEF,
    DETAILED,
    DETAILED_PRESET,
    NATURAL_PRESET,
    STANDARD,
    StylePreset,
    TERSE,
    TERSE_PRESET,
    VALID_STYLES,
)

__all__ = [
    "BRIEF", "STANDARD", "DETAILED", "TERSE", "VALID_STYLES",
    "StylePreset", "NATURAL_PRESET", "TERSE_PRESET", "DETAILED_PRESET",
    "resolve_style",
]


_STYLE_REGISTRY = {
    "terse": TERSE_PRESET,
    "natural": NATURAL_PRESET,
    # brief / standard keep resolving to NATURAL (v2 decision: the v1
    # token-cutting presets were rejected by user feedback). "detailed"
    # now resolves to the real DETAILED_PRESET (2026-06-26) — a
    # format/verbosity variant that reproduces source detail, NOT a
    # token-cut preset.
    "brief": NATURAL_PRESET,
    "standard": NATURAL_PRESET,
    "detailed": DETAILED_PRESET,
}


def resolve_style(explicit: str = "") -> StylePreset:
    """Resolve the active style preset, honoring user/operator override.

    Resolution order:
      1. ``explicit`` arg (QueryRequest.response_style API field)
      2. ``JAMES_RESPONSE_STYLE`` env
      3. default → NATURAL_PRESET (production byte-identical)

    2026-06-04 fix — restore override (the v2 hardcode ignored both
    inputs and forced NATURAL, blocking any user style request = mother
    platform defect, see memory
    feedback_response_style_hardcode_platform_defect). Default behavior
    is unchanged: with no explicit and no env, returns NATURAL exactly
    as before. Only an explicit/env style id (e.g. "terse") diverges.

    Unrecognized ids fall through to NATURAL (forgiving — a typo
    shouldn't break the answer path). The v1 token-cutting presets
    (brief/standard/detailed) are NOT resurrected; they map to NATURAL.
    """
    requested = (explicit or "").strip().lower()
    if not requested:
        requested = (os.getenv("JAMES_RESPONSE_STYLE", "") or "").strip().lower()
    if not requested:
        return NATURAL_PRESET
    return _STYLE_REGISTRY.get(requested, NATURAL_PRESET)
