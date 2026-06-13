"""Critique → one-word issue tag extractor for the REVISE_PROMPT v2
path (Option B, 2026-06-05 §23).

Extracted from the legacy single-file ``core/reasoning/reflect.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

External callers (tests) import this directly:

    from core.reasoning.reflect import _extract_issue_flag

The re-export façade in ``core.reasoning.reflect.__init__`` preserves
that import shape.
"""
from __future__ import annotations

import re as _re


# ─── Issue-type extractor (critique → tag) ───────────────────────
#
# Maps the free-form critique text to one of the four canonical issue
# tags surfaced to REVISE_PROMPT_V2_*. The categories mirror the three
# dimensions enumerated in CRITIQUE_PROMPT_* (contradiction / missing
# core / ambiguity) plus 'general' as the catch-all. Order matters —
# earlier patterns win, so factual_error (most actionable) is checked
# before missing_core (which can appear as a side-comment in any
# critique). 'general' is the fallback when no specific term hit.
_ISSUE_TYPE_PATTERNS: tuple[tuple[_re.Pattern, str], ...] = (
    (_re.compile(
        r'(contradiction|factual\s+error|incorrect|wrong|inaccura|'
        r'사실\s*오류|모순|틀린|잘못)',
        _re.IGNORECASE), 'factual_error'),
    (_re.compile(
        r'(missing\s+core|not\s+answered|omitted|key\s+information|'
        r'incomplete|누락|빠진|답하지\s*않|핵심\s*누락)',
        _re.IGNORECASE), 'missing_core'),
    (_re.compile(
        r'(ambiguit|ambiguous|unclear|misread|vague|misleading|'
        r'모호|애매|오해)',
        _re.IGNORECASE), 'ambiguity'),
)


def _extract_issue_flag(critique_text: str) -> str:
    """Compress a free-form critique to one of four canonical tags
    (factual_error / missing_core / ambiguity / general).

    The tag is what reaches REVISE_PROMPT_V2_* — the critique text
    itself is never shown to the revise call. This is the structural
    fix for the meta-format problem (Option B, §23): the revise model
    cannot speak revision-speak when it does not see a review.

    'general' is the deliberate fallback when the critique mentions
    none of the three canonical dimensions — the revise call still
    knows there is some issue, but the prompt remains an answer-write
    task rather than a critique-acknowledgement task.
    """
    head = (critique_text or "")[:500]
    for pat, tag in _ISSUE_TYPE_PATTERNS:
        if pat.search(head):
            return tag
    return 'general'


__all__ = [
    "_ISSUE_TYPE_PATTERNS",
    "_extract_issue_flag",
]
