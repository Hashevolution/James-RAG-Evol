"""Cloud-egress abstraction layer — §5.7.13 trust contract.

The single place where sensitive entity strings are deterministically
replaced with typed placeholders on the way *out* to a cloud reasoner,
and where the reply is reversed on the way *in*. §5.7.12 defines the
boundary (cloud-egress trust zone); this package enforces it.

Public API (frozen per §5.7.13, mirrors design memo §3):

  from core.abstraction import (
      Decision, AbstractionMap, default_decider,
      build_map, mask_text, unmask_text, emit_egress_event,
  )

Caller contract (per §5.7.13):
  1. PolicyEngine MUST gate the egress decision BEFORE build_map runs.
     This module enforces the egress; it does not authorize it.
  2. Every build_map → mask_text → (cloud call) → unmask_text sequence
     emits one `reason:egress` row via `emit_egress_event`. Failure to
     audit is the same as failure to mask — caller MUST NOT proceed.
  3. `flagged` entries from `unmask_text` are surfaced to the
     user-facing reply, never silently stripped.

Module layout (private, not part of contract):
  - `_policy.py` — Decision + default_decider
  - `_mask.py`   — AbstractionMap + build_map + mask_text + unmask_text
  - `_audit.py`  — emit_egress_event

The split honors rule #5 (module-size discipline) — each private file
stays well under the 20 KB ceiling and is independently testable
without touching the others.
"""
from __future__ import annotations

from core.abstraction._audit import emit_egress_event
from core.abstraction._mask import (
    AbstractionMap,
    build_map,
    mask_text,
    unmask_text,
)
from core.abstraction._policy import Decision, default_decider

__all__ = [
    "Decision",
    "AbstractionMap",
    "default_decider",
    "build_map",
    "mask_text",
    "unmask_text",
    "emit_egress_event",
]
