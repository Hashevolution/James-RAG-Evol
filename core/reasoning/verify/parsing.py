"""Parse the fact-check backend's JSON verdict.

Split out of the single-file ``core/reasoning/verify.py`` on 2026-09-26.
The file had reached 20,008 B against CLAUDE.md rule #5's 20 KB cap —
472 B of headroom — so it could not take another line. Same shape as the
v0.6 ``core/reasoning/reflect/`` split; ``__init__`` re-exports the
pre-split surface, so the move is a no-op for callers.
"""
from __future__ import annotations

import json
import re


_JSON_OBJ_RE = re.compile(r'\{[^{}]*"grounded"\s*:\s*(?:true|false)[^{}]*\}', re.DOTALL | re.IGNORECASE)


def _parse_fact_check(llm_text: str):
    """Return ``(grounded: bool, unsupported: List[str])`` or ``None``
    on parse failure (caller treats as "skip, accept").
    """
    if not llm_text:
        return None
    try:
        blob = json.loads(llm_text)
        if isinstance(blob, dict):
            grounded = bool(blob.get("grounded", True))
            unsupported = blob.get("unsupported", []) or []
            if not isinstance(unsupported, list):
                unsupported = []
            unsupported = [str(c)[:120] for c in unsupported if c]
            return (grounded, unsupported)
    except (json.JSONDecodeError, ValueError):
        pass
    # Slower path: regex sniff for the object body
    m = _JSON_OBJ_RE.search(llm_text)
    if m:
        try:
            blob = json.loads(m.group(0))
            grounded = bool(blob.get("grounded", True))
            unsupported = blob.get("unsupported", []) or []
            if isinstance(unsupported, list):
                unsupported = [str(c)[:120] for c in unsupported if c]
            return (grounded, unsupported)
        except (json.JSONDecodeError, ValueError):
            pass
    return None
