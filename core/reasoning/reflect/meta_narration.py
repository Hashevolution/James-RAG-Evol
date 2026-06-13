"""Meta-narrative detection + stripping for the reflection loop.

Extracted from the legacy single-file ``core/reasoning/reflect.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

External callers (tests) import these directly:

    from core.reasoning.reflect import (
        _looks_like_meta_narration, _strip_meta_narration,
    )

The re-export façade in ``core.reasoning.reflect.__init__`` preserves
that import shape.

## Why this exists

v0.4 live verify fix #6 (2026-05-26): meta-narrative detector +
stripper. Even with the REVISE_PROMPT directives explicitly
forbidding meta-text, Gemma 4 occasionally opens the revision with
the model commenting on the critique it just received ("제시해주신
검토 결과... 매우 날카롭고 정확합니다... 이러한 결함을 완벽하게
보완하여... [핵심 전략]..."). The user never saw the critique,
so this preamble is pure noise that pushes the actual answer below
the fold. Live-verified on the 2026-05-26 NVIDIA query.

Strategy:
  1. If revised_text head matches any meta-narrative pattern AND
  2. a paragraph-separator line ("***" / "---") exists later, return
     the body AFTER the separator (that's where the LLM resumed the
     real answer in observed cases). Else
  3. Fall back to the draft — safer than serving meta-text.

Patterns are conservative; they target phrases that only appear when
the model is reflecting on the critique, not in regular answers.
"""
from __future__ import annotations


_META_NARRATIVE_PATTERNS = (
    # Korean meta-narrative openings observed in production. `\S*` slot
    # absorbs the connecting particles between the verb roots (검토 +
    # 결과를 + 반영 / 검토 + 를 + 바탕) without anchoring to a specific
    # particle form.
    r'^\s*제시\s*해주신',
    r'^\s*지적\s*해주신',
    r'^\s*검토\s*\S*\s*(반영|바탕|읽고|반영하여)',
    r'^\s*이러한\s+(결함|문제|지적)',
    r'^\s*개정\s*된?\s+(답변|버전)',
    r'^\s*재작성',
    r'^\s*\[?핵심\s+전략\]?',
    # English meta-narrative openings
    r'^\s*Based\s+on\s+(the|your)\s+(review|critique|feedback)',
    r'^\s*Here\s+is\s+(my|the)\s+revised',
    r'^\s*I(\'ve|\s+have)\s+(revised|rewritten|updated)',
    r'^\s*Below\s+is\s+the\s+revised',
    r'^\s*Thank\s+you\s+for\s+the\s+(feedback|review|critique)',
    r'^\s*\[?Core\s+strategy\]?',
    # 2026-06-05 §22 extension — PM-13 yielded 29/100 e4b meta-mode
    # answers post cap[:1000] fix; none matched the original 6 EN
    # patterns above. The post-cap-fix Gemma 4 revision openings are
    # different: heading-style ("## Revised Answer"), reflexive-style
    # ("This revision focuses on..."), and persona ("Hello, I am JAMES.
    # I will follow the plan"). These are clearly meta — the model is
    # describing its revision, not answering — but they sit outside
    # the original opener vocabulary.
    r'^\s*\*?\*?##?\s*Revised\s+(Answer|Draft|Version)\*?\*?:?',
    r'^\s*\*\*\s*Revised\s+(Answer|Draft|Version)\s*\*?\*?:?',
    r'^\s*This\s+revision\s+(focuses|addresses|maintains|assumes|adopts|tightens|reflects|incorporates)',
    r'^\s*This\s+revised\s+(answer|draft|version|response)',
    r'^\s*Hello,?\s+I\s+am\s+JAMES\.\s*I\s+will\s+follow',
)


def _looks_like_meta_narration(text: str) -> bool:
    """Return True when `text` opens with a meta-narrative pattern."""
    import re
    head = text[:300]
    for pat in _META_NARRATIVE_PATTERNS:
        if re.search(pat, head, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def _strip_meta_narration(revised: str) -> str:
    """If `revised` opens with meta-narrative, return the body after
    the first paragraph separator (``***`` / ``---`` / ``===`` on its
    own line). Returns empty string when no separator is found OR the
    extracted body is too short to be a real answer — caller falls
    back to draft on empty.
    """
    if not _looks_like_meta_narration(revised):
        return revised
    import re
    sep_match = re.search(
        r'^\s*([*\-=]{3,})\s*$', revised, re.MULTILINE,
    )
    if not sep_match:
        return ""
    body = revised[sep_match.end():].strip()
    # Sanity floor — body must be substantive, not just a heading.
    if len(body) < 100:
        return ""
    return body


__all__ = [
    "_META_NARRATIVE_PATTERNS",
    "_looks_like_meta_narration",
    "_strip_meta_narration",
]
