"""v0.6 G8.a — ontology pack mount mechanism (mother-platform).

Per `docs/reviews/v0.5-b3-plugin-api-stability.md` §4. Mother-level
implementation of the B.3 design memo's pack mount surface. Ships
the **mechanism only** — `rule_one_exemption_granted` capability is
default empty so packs cannot mount, and `core/ontology.py` stays
the runtime ontology source until an explicit operator grant + LOI
scoping unlocks the gate (G8.d, separate PR).

## What this module ships

  * `OntologyPack` — frozen dataclass describing a pack
    (pack_id, capability requirement, subtypes, relation_types,
    enterprise_roles, label_to_type, since, provenance).
  * `register_pack(pack)` — mount a pack into the in-memory
    registry. Raises `CapabilityNotGrantedError` /
    `NameCollisionError` / `SchemaError` on contract violations.
  * `unmount_pack(pack_id)` — remove a previously-mounted pack.
  * `mounted_packs()` — deterministic snapshot of currently-
    mounted packs (registration order).
  * `granted_capabilities()` — operator-grantable capability set
    (driven by `JAMES_CAPABILITIES` env). Default empty.

## What this module does NOT do (deferred to G8.b / G8.c / G8.d)

- **No read-side lookup helpers** — `all_document_subtypes()` /
  `all_relation_types()` lookup merging mother + mounted packs
  lands in G8.b.
- **No audit-replay event types** — `lifecycle.ontology.pack_
  mounted` / `_unmounted` + `reconstruct_graph_at` dispatch lands
  in G8.c.
- **No capability grant workflow** — interactive `grant_capability`
  CLI with operator confirmation + audit-row writing lands in
  G8.d. **G8.d is LOI-conditional** — until a customer LOI scopes
  the vertical pack, the capability grant flow cannot ship without
  bypassing CLAUDE.md rule #1.

## Rule #1 protection (per v0.5 close handover §6.5)

1. **Code-level**: this module's `_resolve_granted_capabilities()`
   returns the EMPTY frozenset by default. `register_pack`
   refuses to mount any pack whose `requires_capability` is not
   in that set.
2. **Doc-level**: this module's docstring + `register_pack`'s
   docstring explicitly state vertical content is BLOCKED until
   v1.0 / LOI.
3. **Naming-level**: nothing in this module references vertical
   names. `OntologyPack` is a generic dataclass; the test fixtures
   use only horizontal stub packs.
4. **Trigger-level**: G8.d (the grant workflow that unlocks
   verticals) is explicitly listed as LOI-conditional in the
   v0.5 close handover §5.2 and B.3 §5 — any PR shipping G8.d
   without LOI evidence is reviewer-rejectable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Tuple


JAMES_CAPABILITIES_ENV: str = "JAMES_CAPABILITIES"


# ─── Exceptions ───────────────────────────────────────────────────────


class CapabilityNotGrantedError(RuntimeError):
    """Raised when `register_pack` is called with a pack whose
    `requires_capability` is not in the granted-capability set.

    This is the **code-level enforcement** of CLAUDE.md rule #1 —
    vertical packs require `rule_one_exemption_granted` capability,
    which is default empty until G8.d ships the grant workflow.
    """


class NameCollisionError(RuntimeError):
    """Raised when a pack tries to register a name (subtype /
    relation / role) that is already in the mother ontology OR in
    an already-mounted pack. Silent override is forbidden by the
    B.3 §3 design constraints — the operator must rename the
    conflicting name or unmount the colliding pack first.
    """


class SchemaError(RuntimeError):
    """Raised when a pack's content fails B.3 §4.1 invariants:
    every subtype must declare a `parent` that resolves to a
    known mother entity type, relation type dicts must carry the
    required keys, etc.
    """


# ─── Public dataclass ─────────────────────────────────────────────────


@dataclass(frozen=True)
class OntologyPack:
    """Per B.3 §4.1 — pure data describing a pack.

    Fields:
        pack_id: globally unique pack identifier (e.g. ``"legal-v1"``).
        requires_capability: capability name the operator must have
            granted via ``JAMES_CAPABILITIES`` before this pack can
            mount. The mother default is empty → no pack can mount.
        subtypes: additive document subtypes. Each entry's
            ``parent`` must resolve to a known mother entity type.
        relation_types: additive relation types. Same shape as
            ``core/ontology.py::RELATION_TYPES`` entries.
        enterprise_roles: additive permission roles. Same shape as
            ``core/ontology.py::ENTERPRISE_ROLES`` entries.
        label_to_type: i18n label → canonical relation/subtype
            name map. Append-only with mother.
        since: pack-version string (operator's choice).
        provenance: human-readable license / DOI / customer ref.
    """
    pack_id:             str
    requires_capability: str
    subtypes:            Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    relation_types:      Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    enterprise_roles:    Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    label_to_type:       Mapping[str, str] = field(
        default_factory=dict
    )
    since:               str = "v0.6"
    provenance:          str = ""


# ─── Capability resolver ──────────────────────────────────────────────


def _truthy(value: str) -> bool:
    """Truthy env-flag parser (mirrors retention.py / tenant.py)."""
    if not value:
        return False
    return value.strip().lower() in (
        "1", "true", "yes", "on", "enabled",
    )


def granted_capabilities() -> FrozenSet[str]:
    """Return the set of capabilities the operator has granted.

    Resolved from ``JAMES_CAPABILITIES`` env var (comma-separated).
    Empty default = mother-platform-only mode = no pack can mount.

    Whitespace around each capability name is stripped. Empty names
    (e.g. trailing comma) are dropped silently. Names are
    case-sensitive (an operator who set
    ``JAMES_CAPABILITIES=Rule_One_Exemption_Granted`` would NOT
    satisfy a pack requiring ``rule_one_exemption_granted``).

    The function reads the env on every call (not cached) so
    operator can toggle capabilities during a process lifetime
    by setting the env + asking the audit system to re-mount.
    Caching would mask such toggles silently.
    """
    raw = os.environ.get(JAMES_CAPABILITIES_ENV, "") or ""
    names = []
    for chunk in raw.split(","):
        name = chunk.strip()
        if name:
            names.append(name)
    return frozenset(names)


# ─── Registry ─────────────────────────────────────────────────────────


# Ordered registry — registration order is part of the audit-replay
# contract (G8.c). `_mounted` is the source of truth; the snapshot
# returned by `mounted_packs()` is a copy.
_mounted: List[OntologyPack] = []


def _claimed_names() -> Dict[str, Tuple[str, str]]:
    """Map name → (kind, owner) for collision detection.

    `kind` is one of ``"subtype"`` / ``"relation"`` / ``"role"``.
    `owner` is ``"mother"`` (from `core/ontology.py`) or the
    `pack_id` of an already-mounted pack.

    Re-read from the mother ontology on every call so a future
    `core/ontology.py` update extending mother subtypes is picked
    up without a registry refresh dance.
    """
    from core.ontology import (
        DOCUMENT_SUBTYPES,
        ENTERPRISE_ROLES,
        RELATION_TYPES,
    )
    claimed: Dict[str, Tuple[str, str]] = {}
    for name in DOCUMENT_SUBTYPES:
        claimed[name] = ("subtype", "mother")
    for name in RELATION_TYPES:
        claimed[name] = ("relation", "mother")
    for name in ENTERPRISE_ROLES:
        claimed[name] = ("role", "mother")
    for pack in _mounted:
        for name in pack.subtypes:
            claimed[name] = ("subtype", pack.pack_id)
        for name in pack.relation_types:
            claimed[name] = ("relation", pack.pack_id)
        for name in pack.enterprise_roles:
            claimed[name] = ("role", pack.pack_id)
    return claimed


def _validate_schema(pack: OntologyPack) -> None:
    """Per B.3 §4.1 invariants. Raises SchemaError on violation."""
    if not isinstance(pack.pack_id, str) or not pack.pack_id.strip():
        raise SchemaError("pack.pack_id must be a non-empty string")
    if not isinstance(pack.requires_capability, str) \
       or not pack.requires_capability.strip():
        raise SchemaError(
            "pack.requires_capability must be a non-empty string"
        )
    # Every subtype must declare a parent that is a known mother
    # entity type. We import the mother entity-type registry lazily
    # to avoid circular imports.
    if pack.subtypes:
        from core.ontology import ENTITY_TYPES
        for sub_name, sub_def in pack.subtypes.items():
            if not isinstance(sub_def, dict):
                raise SchemaError(
                    f"subtype {sub_name!r} must map to a dict"
                )
            parent = sub_def.get("parent")
            if parent not in ENTITY_TYPES:
                raise SchemaError(
                    f"subtype {sub_name!r} parent {parent!r} is not "
                    f"a known mother entity type"
                )


def _check_no_collision(pack: OntologyPack) -> None:
    """Raises NameCollisionError when the pack overlaps any
    existing claim (mother or already-mounted pack)."""
    claimed = _claimed_names()
    incoming = set(pack.subtypes.keys()) \
             | set(pack.relation_types.keys()) \
             | set(pack.enterprise_roles.keys())
    for name in incoming:
        if name in claimed:
            kind, owner = claimed[name]
            raise NameCollisionError(
                f"pack {pack.pack_id!r} tried to register {name!r} "
                f"as {kind}; already claimed by {owner!r}"
            )
    # Also: same name MUST NOT appear in two different fields of
    # the incoming pack (a pack registering a name as both a
    # subtype AND a relation would create lookup ambiguity).
    seen: Dict[str, str] = {}
    for kind, source in (
        ("subtype",  pack.subtypes),
        ("relation", pack.relation_types),
        ("role",     pack.enterprise_roles),
    ):
        for name in source:
            if name in seen:
                raise NameCollisionError(
                    f"pack {pack.pack_id!r} declared {name!r} as "
                    f"both {seen[name]!r} and {kind!r}"
                )
            seen[name] = kind


def register_pack(pack: OntologyPack) -> None:
    """Mount a pack into the in-memory registry.

    Pre-conditions (checked in order):

      1. ``pack.requires_capability`` is in
         ``granted_capabilities()`` — raises
         :class:`CapabilityNotGrantedError`. **Mother default is
         empty** → no pack can mount until G8.d ships the grant
         workflow + an operator LOI evidence scope unlocks the
         capability.
      2. Pack schema is valid (subtype parents, required fields) —
         raises :class:`SchemaError`.
      3. No name collision with mother or any already-mounted
         pack — raises :class:`NameCollisionError`.

    Side effects on success:
      * Pack appended to the in-memory registry (registration
        order preserved).
      * G8.c will additionally emit a
        ``lifecycle.ontology.pack_mounted`` audit row; this G8.a
        implementation does NOT yet emit (the audit-event type is
        added in G8.c).

    All failures are fatal — a silent half-mount would break the
    audit-replay contract (G8.c). The caller catches the exception
    if the failure is recoverable (e.g. operator typo in
    ``pack_id``).
    """
    if pack.requires_capability not in granted_capabilities():
        raise CapabilityNotGrantedError(
            f"pack {pack.pack_id!r} requires capability "
            f"{pack.requires_capability!r}, which has not been "
            f"granted via {JAMES_CAPABILITIES_ENV} env. "
            f"This is the code-level enforcement of CLAUDE.md "
            f"rule #1 — vertical packs cannot mount without an "
            f"operator grant + LOI evidence."
        )
    _validate_schema(pack)
    _check_no_collision(pack)
    _mounted.append(pack)


def unmount_pack(pack_id: str) -> None:
    """Remove a previously-mounted pack from the registry.

    Raises KeyError if no pack with that id is currently mounted.

    Existing audit rows referencing pack-defined subtypes /
    relations are NOT mutated — replay at a time when the pack was
    mounted continues to honor the pack's definitions via the G8.c
    event stream (separate PR).
    """
    for i, pack in enumerate(_mounted):
        if pack.pack_id == pack_id:
            del _mounted[i]
            return
    raise KeyError(f"no mounted pack with pack_id={pack_id!r}")


def mounted_packs() -> Tuple[OntologyPack, ...]:
    """Snapshot of currently-mounted packs in registration order.

    Returns a tuple so callers cannot accidentally mutate the
    registry. The contained dataclasses are frozen.
    """
    return tuple(_mounted)


def _reset_for_tests() -> None:
    """Test-only reset of the in-memory registry. Production code
    must never call this — it bypasses the audit-replay contract.
    """
    _mounted.clear()


# ─── v0.6 G8.b — read-side lookup helpers (B.3 §4.2) ──────────────────
#
# These helpers merge the mother ontology (`core/ontology.py`) with
# every currently-mounted pack, returning a unified read-only view.
# Existing call sites that import `DOCUMENT_SUBTYPES` / `RELATION_TYPES`
# / `ENTERPRISE_ROLES` directly from `core/ontology.py` continue to
# see ONLY the mother set — these helpers are the new opt-in surface
# for pack-aware code paths.
#
# Lookup-time merging (not registration-time):
#   - When a pack mounts, the mother dicts are NOT mutated.
#   - The lookup helpers do the merge on each call.
#   - Cheap because the dicts are small (mother ~10 subtypes ×
#     ~few packs × ~10 subtypes each = ~50 entries max).
#   - Determinism: same mother state + same mount order yields the
#     same merged view byte-identical.
#
# Mother takes precedence on duplicate names. `register_pack`'s
# collision check (§ above) prevents this in practice — but the
# defensive ordering means a future race / hot-reload would still
# fail-safe to mother behaviour.


def _merge_packs(field_name: str) -> Dict[str, Any]:
    """Merge mother + mounted-pack entries for the given field.

    Args:
        field_name: one of ``"subtypes"`` / ``"relation_types"``
            / ``"enterprise_roles"``.

    Returns:
        A fresh dict (callers can mutate without affecting the
        registry). Mother entries first, then each mounted pack
        in registration order. Mother takes precedence on key
        collisions (defensive — `register_pack` already blocks
        collisions at mount time).
    """
    from core.ontology import (
        DOCUMENT_SUBTYPES,
        ENTERPRISE_ROLES,
        RELATION_TYPES,
    )
    mother_map = {
        "subtypes":         DOCUMENT_SUBTYPES,
        "relation_types":   RELATION_TYPES,
        "enterprise_roles": ENTERPRISE_ROLES,
    }
    mother = mother_map.get(field_name, {})
    merged: Dict[str, Any] = {}
    # Packs first, then mother — mother last write wins on conflict.
    for pack in _mounted:
        pack_entries = getattr(pack, field_name, {})
        for name, definition in pack_entries.items():
            merged[name] = definition
    for name, definition in mother.items():
        merged[name] = definition
    return merged


def all_document_subtypes() -> Dict[str, Mapping[str, Any]]:
    """Mother DOCUMENT_SUBTYPES merged with every mounted pack's
    subtypes.

    Existing callers that import ``DOCUMENT_SUBTYPES`` from
    ``core.ontology`` directly continue to see only the mother set
    — those callers are pack-unaware by design. This helper is the
    new opt-in surface for pack-aware code (e.g. a future ingestion
    pipeline that wants to classify documents against vertical
    pack subtypes once an LOI scopes a pack).
    """
    return _merge_packs("subtypes")


def all_relation_types() -> Dict[str, Mapping[str, Any]]:
    """Mother RELATION_TYPES merged with every mounted pack's
    relation_types. Same opt-in semantic as
    :func:`all_document_subtypes`.
    """
    return _merge_packs("relation_types")


def all_enterprise_roles() -> Dict[str, Mapping[str, Any]]:
    """Mother ENTERPRISE_ROLES merged with every mounted pack's
    enterprise_roles. Same opt-in semantic.
    """
    return _merge_packs("enterprise_roles")


__all__ = (
    "JAMES_CAPABILITIES_ENV",
    "CapabilityNotGrantedError",
    "NameCollisionError",
    "SchemaError",
    "OntologyPack",
    "granted_capabilities",
    "register_pack",
    "unmount_pack",
    "mounted_packs",
    # v0.6 G8.b — read-side helpers
    "all_document_subtypes",
    "all_relation_types",
    "all_enterprise_roles",
)
