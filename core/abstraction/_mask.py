"""Deterministic mask/unmask — §5.7.13 §"Module invariants" 1-3 + 6.

`AbstractionMap` holds the local-only real↔placeholder mapping for one
egress. `build_map` constructs it deterministically from typed graph
entities. `mask_text` replaces real names with placeholders before
egress (substring-safe, particle-safe). `unmask_text` reverses on the
reply and **flags** placeholder tokens absent from the local map —
never silently de-abstracts them.

Module-size discipline: this file holds the mask/unmask + map only.
Policy lives in `_policy.py`; audit emit lives in `_audit.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence, Tuple

from core.ontology import ENTITY_TYPES

from core.abstraction._policy import (
    Decision,
    _entity_name,
    _entity_type,
)


@dataclass
class AbstractionMap:
    """Per-query mapping between real entity names and typed placeholders.

    §5.7.13 invariant #5 (local-only map): instances are created per
    query and garbage-collected after `unmask_text`. They are **never**
    persisted, serialized, or sent over any wire. Same `PERSON_1` across
    different queries would be a re-identification risk by design.

    Field summary:
      • `forward`     — real name → placeholder (used by mask_text)
      • `reverse`     — placeholder → real name (used by unmask_text)
      • `keep_local`  — names that must NOT egress (Decision.KEEP_LOCAL)
      • `passed`      — names sent as-is (Decision.PASS, audit record)
      • `_counters`   — per-TYPE monotonic counter for new placeholders
    """

    forward: Dict[str, str] = field(default_factory=dict)
    reverse: Dict[str, str] = field(default_factory=dict)
    keep_local: List[str] = field(default_factory=list)
    passed: List[str] = field(default_factory=list)
    _counters: Dict[str, int] = field(default_factory=dict)

    def placeholder_for(self, name: str, entity_type: str) -> str:
        """Return the placeholder for `name`, allocating one on first
        sight. Same name → same placeholder (§5.7.13 invariant #1
        determinism + closed-world reasoning preservation per §5.7.12).
        """
        if name in self.forward:
            return self.forward[name]
        t = entity_type.upper()
        self._counters[t] = self._counters.get(t, 0) + 1
        ph = f"{t}_{self._counters[t]}"
        self.forward[name] = ph
        self.reverse[ph] = name
        return ph


def build_map(
    entities: Sequence[dict],
    decide: Callable[[dict], Decision],
) -> AbstractionMap:
    """Build an `AbstractionMap` from typed graph entities.

    §5.7.13 invariant #1 (determinism): per-TYPE counters advance in
    entity declaration order, so the same (entities, decide) input
    produces a byte-identical map. Required for §5.7.2 trace-schema
    replay — re-running the same query at time T+ε reconstructs the
    same map and therefore the same audit row.

    Empty / nameless entities are silently skipped (no placeholder is
    allocated for a missing name — there is nothing to mask).
    """
    amap = AbstractionMap()
    for e in entities:
        name = _entity_name(e)
        if not name:
            continue
        d = decide(e)
        if d is Decision.MASK:
            amap.placeholder_for(name, _entity_type(e))
        elif d is Decision.KEEP_LOCAL:
            if name not in amap.keep_local:
                amap.keep_local.append(name)
        else:  # PASS
            if name not in amap.passed:
                amap.passed.append(name)
    return amap


def mask_text(text: str, amap: AbstractionMap) -> str:
    """Replace every masked entity name with its placeholder.

    §5.7.13 invariant #2 (substring safety): longest names first, so a
    name that is a substring of another (e.g. '김철' ⊂ '김철수') cannot
    corrupt the replacement. Verified by PoC self-test §5.
    """
    for name in sorted(amap.forward, key=len, reverse=True):
        text = text.replace(name, amap.forward[name])
    return text


# Placeholder token regex.
#
# §5.7.13 invariant #3 (particle/boundary safety): plain `\b` trailing
# boundary fails when a Korean particle is glued to the token —
# `PERSON_3의` has no `\b` between the `3` and the `의` because both are
# `\w`. We use:
#   • non-alnum / non-underscore lookbehind  — placeholder must not be
#     in the middle of an identifier (`xPERSON_1` is not a match)
#   • not-a-digit lookahead                  — `PERSON_12` is one token
#     `PERSON_12`, not `PERSON_1` followed by `2`
# A trailing Korean particle is fine — `의` is not `[0-9]`, so the
# lookahead lets it through and the match ends at the digit.
_KNOWN_TYPE_UPPER = {t.upper() for t in ENTITY_TYPES}
_PLACEHOLDER_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z]+)_(\d+)(?![0-9])")


def unmask_text(text: str, amap: AbstractionMap) -> Tuple[str, List[str]]:
    """Restore placeholders to real names.

    Returns `(restored, flagged)` where `flagged` lists placeholder
    tokens that:
      • match the placeholder shape (`TYPE_n` with TYPE in the ontology)
      • are NOT in `amap.reverse` (the reasoner introduced them)

    §5.7.13 invariant #4 (hallucination flagging): flagged tokens are
    left **verbatim** in `restored` — never silently de-abstracted to
    a real name. Silent restoration would let the cloud inject content
    under a real entity name, which is the threat model this module
    exists to defeat.
    """
    flagged: List[str] = []

    def _sub(m: re.Match) -> str:
        token = m.group(0)
        if token in amap.reverse:
            return amap.reverse[token]
        if m.group(1) in _KNOWN_TYPE_UPPER:
            if token not in flagged:
                flagged.append(token)
        return token

    return _PLACEHOLDER_RE.sub(_sub, text), flagged


__all__ = [
    "AbstractionMap",
    "build_map",
    "mask_text",
    "unmask_text",
]
