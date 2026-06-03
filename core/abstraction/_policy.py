"""Per-entity egress decision — §5.7.13 §"Public API surface" / §5.7.12 §"Egress masking policy".

`Decision` is the 3-way outcome the abstraction layer takes per entity:
MASK / PASS / KEEP_LOCAL. `default_decider` builds the policy function
that the router/caller hands to `build_map`. Production callers may
substitute a query-conditioned classifier for `default_decider`; the
module is policy-agnostic per §5.7.13 non-goal #2.

Module-size discipline: this file holds policy only. Mask / unmask
lives in `_mask.py`; audit emit lives in `_audit.py`.
"""
from __future__ import annotations

from enum import Enum
from typing import Callable, Sequence


class Decision(str, Enum):
    """Per-entity egress outcome (§5.7.12 three-way)."""

    MASK = "mask"            # sensitive + closed-world → typed placeholder
    PASS = "pass"            # not sensitive → send real value
    KEEP_LOCAL = "keep"      # sensitive + open-world → never egress


def _entity_name(e: dict) -> str:
    return e.get("name") or e.get("label") or e.get("title") or e.get("entity_id") or ""


def _entity_type(e: dict) -> str:
    return e.get("entity_type") or e.get("type") or "concept"


def _is_sensitive(e: dict) -> bool:
    """Read the entity's sensitivity flag. §5.7.13 non-goal #1: this
    module does **not** classify sensitivity — it reads what the
    ingestion / wiki pipeline set.

    Accepts: `sensitive` (PoC field), `sensitivity` (chunk metadata
    convention). String values "1"/"true"/"yes"/"high"/"sensitive" map
    to True (matches the live `core/wiki_generator/_frontmatter.py`
    convention); empty / falsy / missing → False (conservative — an
    unflagged entity is treated as not-sensitive and PASSes through).
    """
    v = e.get("sensitive", e.get("sensitivity", False))
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "high", "sensitive")
    return bool(v)


def default_decider(
    *,
    open_world_types: Sequence[str] = (),
    open_world_names: Sequence[str] = (),
) -> Callable[[dict], Decision]:
    """Build the per-entity decision function (§5.7.12 three-way).

    semantic-dependence (closed vs open world) is approximated by
    explicit sets: an entity whose TYPE or NAME is in the open-world
    set needs its real-world identity for the reasoning, so when it's
    sensitive it becomes KEEP_LOCAL (never egress). Everything else
    sensitive → MASK. Non-sensitive → PASS.

    Production callers replace the sets with a query-conditioned
    classifier (§5.7.13 non-goal #2) — the module enforces the
    boundary, the caller picks the policy. Both `open_world_types`
    and `open_world_names` default to empty: with no policy input,
    every sensitive entity is MASK (the safer-egress default, since
    a wrongly-MASKed entity loses no information; a wrongly-PASSed
    one leaks).
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


__all__ = [
    "Decision",
    "default_decider",
    "_entity_name",
    "_entity_type",
    "_is_sensitive",
]
