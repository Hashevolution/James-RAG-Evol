"""How much evidence a downstream stage is allowed to see.

One number, read from one env var, shared by every stage that reasons
over the same retrieved context.

Why it is shared
----------------
synth writes the draft from ``JAMES_SYNTH_CONTEXT_CHARS`` characters of
context (``core/reasoning/engine_synth.py``, default 8000). Any stage
that then judges that draft against "the evidence" while seeing **less**
evidence than synth did will read a claim supported only by the unseen
tail as unsupported. The stage is not wrong about what it can see; it
was handed a smaller world.

This has now been found twice:

* **critique** (#1151, 2026-09-26) — fixed at the time by reading this
  same env var, which is what this module generalises.
* **verify's fact check** — ``context[:2000]`` hard-coded against
  synth's 8000, so a grounded claim could be annotated "not directly
  supported by the source data" for no reason but the window.

`eval/qvt/capture_integrity.py` exists for the same reason on the
measurement side: #1149 showed that guards copied between two files
drift, and the copy that is not maintained is the one that fails.

Truncation is never silent. A caller that trims to this budget states
that it did so inside the prompt, so the model does not read an absent
tail as absent support.
"""
from __future__ import annotations

import os

# Matches core/reasoning/engine_synth.py's default. If that moves, this
# follows it via the shared env var rather than needing its own edit.
DEFAULT_EVIDENCE_CHARS = 8000
EVIDENCE_CHARS_ENV = "JAMES_SYNTH_CONTEXT_CHARS"


def resolve_evidence_chars() -> int:
    """Characters of evidence a judging stage may see.

    Falls back to the default for a missing, non-numeric or
    non-positive value — a misconfigured env must not silently shrink
    a stage's view to nothing.
    """
    raw = os.environ.get(EVIDENCE_CHARS_ENV, "")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_EVIDENCE_CHARS
    return value if value > 0 else DEFAULT_EVIDENCE_CHARS


__all__ = [
    "DEFAULT_EVIDENCE_CHARS",
    "EVIDENCE_CHARS_ENV",
    "resolve_evidence_chars",
]
