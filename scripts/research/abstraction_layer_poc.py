"""Direction α — abstraction layer PROOF OF CONCEPT (deterministic mask/unmask).

NOT the production module. Validates the core security claim of
`docs/design/v0.4-direction-alpha-hybrid-cloud-tier.md` §3-§4.2 WITHOUT any
cloud dependency:

  - sensitive typed entities can be deterministically masked to typed
    placeholders (PERSON_1, ORG_2, ...),
  - the masked payload preserves relationship structure (same entity →
    same placeholder everywhere), so closed-world reasoning survives,
  - the reasoner's reply de-abstracts cleanly via a local-only map,
  - a cloud-introduced placeholder NOT in the map (a hallucinated entity)
    is flagged, never silently restored.

Promotion to a `core/` module + the cloud-egress trust zone requires the
`ARCHITECTURE.md` PR with the `architecture` label first (CLAUDE.md rule
#4). This file is exploration only.

Entity dict shape mirrors `core/graph_typed_filter.py`:
    {"name": str, "entity_type": str, "entity_id": str, "sensitive": bool}

Run:  python scripts/research/abstraction_layer_poc.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.ontology import ENTITY_TYPES  # noqa: E402


# ─── Per-entity egress decision (§4.2 three-way) ──────────────────────

class Decision(str, Enum):
    MASK = "mask"            # sensitive + closed-world → typed placeholder
    PASS = "pass"            # not sensitive → send real value
    KEEP_LOCAL = "keep"      # sensitive + open-world → never egress


def _entity_name(e: dict) -> str:
    return e.get("name") or e.get("label") or e.get("title") or e.get("entity_id") or ""


def _entity_type(e: dict) -> str:
    return e.get("entity_type") or e.get("type") or "concept"


def _is_sensitive(e: dict) -> bool:
    # PoC: entity carries an explicit flag; production reads the chunk
    # `sensitivity` metadata + ontology sensitive-relation participation.
    v = e.get("sensitive", e.get("sensitivity", False))
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "high", "sensitive")
    return bool(v)


def default_decider(
    *,
    open_world_types: Sequence[str] = (),
    open_world_names: Sequence[str] = (),
) -> Callable[[dict], Decision]:
    """Build a per-entity decision function.

    semantic-dependence (closed vs open world) is approximated in the PoC
    by explicit sets: an entity whose TYPE or NAME is marked open-world
    needs its real-world identity for the reasoning → KEEP_LOCAL when
    sensitive. Everything else sensitive → MASK. Non-sensitive → PASS.
    Production replaces the sets with a query-conditioned classifier.
    """
    ow_types = {t.lower() for t in open_world_types}
    ow_names = set(open_world_names)

    def decide(e: dict) -> Decision:
        if not _is_sensitive(e):
            return Decision.PASS
        if _entity_type(e).lower() in ow_types or _entity_name(e) in ow_names:
            return Decision.KEEP_LOCAL
        return Decision.MASK

    return decide


# ─── Abstraction map ──────────────────────────────────────────────────

@dataclass
class AbstractionMap:
    forward: Dict[str, str] = field(default_factory=dict)   # real name → placeholder
    reverse: Dict[str, str] = field(default_factory=dict)   # placeholder → real name
    keep_local: List[str] = field(default_factory=list)     # names that must NOT egress
    passed: List[str] = field(default_factory=list)         # names sent as-is
    _counters: Dict[str, int] = field(default_factory=dict)

    def placeholder_for(self, name: str, entity_type: str) -> str:
        if name in self.forward:
            return self.forward[name]
        t = entity_type.upper()
        self._counters[t] = self._counters.get(t, 0) + 1
        ph = f"{t}_{self._counters[t]}"
        self.forward[name] = ph
        self.reverse[ph] = name
        return ph


def build_map(entities: Sequence[dict], decide: Callable[[dict], Decision]) -> AbstractionMap:
    """Deterministic: same entity name → same placeholder; per-type counter
    advances in entity declaration order so the map is reproducible."""
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


# ─── Mask / unmask ────────────────────────────────────────────────────

def mask_text(text: str, amap: AbstractionMap) -> str:
    """Replace every masked entity name with its placeholder. Longest names
    first so a name that is a substring of another (e.g. '김철' ⊂ '김철수')
    can't corrupt the replacement."""
    for name in sorted(amap.forward, key=len, reverse=True):
        text = text.replace(name, amap.forward[name])
    return text


# Matches TYPE_n tokens whose TYPE is a known ontology type (uppercased).
# NB: a plain \b trailing boundary fails when a Korean particle is glued to
# the token ("PERSON_3의" — '3' and '의' are both \w, so no boundary). Use an
# explicit non-alnum lookbehind + a not-a-digit lookahead (so PERSON_12 is not
# split into PERSON_1 + 2); a trailing Korean particle is fine.
_KNOWN_TYPE_UPPER = {t.upper() for t in ENTITY_TYPES}
_PLACEHOLDER_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z]+)_(\d+)(?![0-9])")


def unmask_text(text: str, amap: AbstractionMap) -> Tuple[str, List[str]]:
    """Restore placeholders to real names. Returns (restored, flagged) where
    `flagged` lists placeholder tokens shaped like ours, of a known type,
    that are NOT in the map → a reasoner-introduced (hallucinated) entity.
    These are left verbatim, never silently restored."""
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


# ─── Self-test (the de-risking evidence) ──────────────────────────────

def _hr(title: str) -> None:
    print(f"\n{'─' * 4} {title} {'─' * 4}")


def _selftest() -> int:
    ok = True

    # 1) Closed-world org chart: all three people masked, reasoning survives.
    _hr("1. closed-world org chart (mask + structural reasoning + restore)")
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
        {"name": "이영희", "entity_type": "person", "sensitive": True},
        {"name": "박민수", "entity_type": "person", "sensitive": True},
        {"name": "영업팀", "entity_type": "org", "sensitive": False},
    ]
    docs = (
        "김철수는 영업팀의 팀장이다. "
        "이영희는 김철수에게 보고한다. "
        "박민수는 이영희에게 보고한다."
    )
    amap = build_map(entities, default_decider())
    masked = mask_text(docs, amap)
    print(f"  map: {amap.forward}")
    print(f"  passed (non-sensitive, sent as-is): {amap.passed}")
    print(f"  masked → cloud: {masked}")
    # the external reasoner only sees placeholders; '영업팀' passes through.
    assert "김철수" not in masked and "이영희" not in masked and "박민수" not in masked
    assert "영업팀" in masked, "non-sensitive entity should pass through"
    # simulate a correct closed-world cloud answer over placeholders
    cloud_reply = "PERSON_3의 보고라인 최상단은 PERSON_1 이다."
    restored, flagged = unmask_text(cloud_reply, amap)
    print(f"  cloud reply (placeholders): {cloud_reply}")
    print(f"  restored: {restored}   flagged: {flagged}")
    ok &= restored == "박민수의 보고라인 최상단은 김철수 이다." and not flagged
    print(f"  PASS={restored == '박민수의 보고라인 최상단은 김철수 이다.' and not flagged}")

    # 2) Hallucinated placeholder not in map → flagged, not restored.
    _hr("2. hallucinated placeholder is flagged (safety)")
    bad_reply = "최상단은 PERSON_1 이며, PERSON_9 도 관여한다."
    restored2, flagged2 = unmask_text(bad_reply, amap)
    print(f"  reply: {bad_reply}")
    print(f"  restored: {restored2}   flagged: {flagged2}")
    ok &= flagged2 == ["PERSON_9"] and "PERSON_9" in restored2
    print(f"  PASS={flagged2 == ['PERSON_9'] and 'PERSON_9' in restored2}")

    # 3) Open-world entity → KEEP_LOCAL (never egress).
    _hr("3. open-world sensitive entity stays local (no mask, no egress)")
    med = [
        {"name": "와파린", "entity_type": "concept", "sensitive": True},
        {"name": "아스피린", "entity_type": "concept", "sensitive": True},
        {"name": "환자김", "entity_type": "person", "sensitive": True},
    ]
    # drug names need real-world meaning → mark 'concept' type open-world.
    decide = default_decider(open_world_types=["concept"])
    amap3 = build_map(med, decide)
    print(f"  keep_local (no cloud): {amap3.keep_local}")
    print(f"  masked map: {amap3.forward}")
    # patient name is closed-world-safe (structural) → masked; drugs kept local.
    ok &= set(amap3.keep_local) == {"와파린", "아스피린"} and "환자김" in amap3.forward
    print(f"  PASS={set(amap3.keep_local) == {'와파린', '아스피린'} and '환자김' in amap3.forward}")

    # 4) Determinism: same input → same map twice.
    _hr("4. determinism")
    a = build_map(entities, default_decider()).forward
    b = build_map(entities, default_decider()).forward
    ok &= a == b
    print(f"  {a}\n  {b}\n  PASS={a == b}")

    # 5) Substring safety: a name contained in another.
    _hr("5. substring-safe masking")
    ents5 = [
        {"name": "김철", "entity_type": "person", "sensitive": True},
        {"name": "김철수", "entity_type": "person", "sensitive": True},
    ]
    amap5 = build_map(ents5, default_decider())
    masked5 = mask_text("김철수와 김철은 다른 사람이다.", amap5)
    print(f"  map: {amap5.forward}")
    print(f"  masked: {masked5}")
    restored5, _ = unmask_text(masked5, amap5)
    ok &= restored5 == "김철수와 김철은 다른 사람이다."
    print(f"  restored: {restored5}   PASS={restored5 == '김철수와 김철은 다른 사람이다.'}")

    print(f"\n{'=' * 40}\nALL PASS = {ok}\n{'=' * 40}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
