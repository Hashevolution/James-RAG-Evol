"""PROJECT JAMES — Node attribute editor (cycle 12 PR-O6).

Companion to ``core/graph_editor.py``. Edge-level mutations
(PUT/POST/DELETE relation) shipped in Knowledge Cascade Phase E
(PR #271 / #273). PR-O6 adds the node-level path so admin can rename
an entity, refine its summary, add aliases (matching surface), correct
entity_type, or toggle sensitivity — all from the graph editor UI
without dropping to chat-based wiki editing.

The two modules live separately so each stays under the CLAUDE.md
rule #5 20 KB gate; they share file-I/O helpers via direct import.

Immutability rules (handover §3 항목 ⑥-b):
  - ``entity_id`` NEVER changes. It's the wiki's stable key; relations
    on other entities point at it. Admin who wants a "new entity"
    creates a fresh file via the existing wiki-create surface, not by
    repurposing an existing entity_id.
  - relations / sources are edge-level; the relation API in
    ``graph_editor.py`` mutates them. ``update_node_attributes``
    silently ignores those keys to keep the blast radius bounded.

Trust model:
  - admin only (server endpoint applies ``admin.data`` feature gate
    + ``JAMES_GRAPH_EDIT=1`` env flag opt-in).
  - audit log captures before+after dicts for the changed_fields only.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

# Share the file-I/O helpers with the relation editor — both modules
# read/write the same entity .md files via the same yaml frontmatter
# convention. A second copy of these helpers would invite drift.
from core.graph_editor import _load_entity_by_id, _write_entity
from core.relations_schema import (
    EXTRACT_SOURCE_ROLE,
    MANUAL_SOURCE_ROLE,
    validate_occurred_at,
)


# Allowlist of frontmatter fields ``update_node_attributes`` may touch.
# Anything else in the patch payload is silently dropped — a typo at
# the call site cannot accidentally write a new top-level field that
# downstream code doesn't know about.
NODE_EDITABLE_FIELDS = frozenset({
    "name",          # human-facing label
    "entity_type",   # one of NODE_ALLOWED_ENTITY_TYPES
    "aliases",       # list[str] — alternative names for matching
    "summary",       # description text shown in node-detail panel
    "sensitivity",   # "normal" | "sensitive" (mask_sensitive gate)
    # PR-11 event time-axis fields. Admit at filter level; honored only
    # when the target node's `entity_type == "event"` (memo §5.2). For
    # any other target type the two fields are *silently dropped* —
    # accidental clients posting them against a person/concept node
    # don't see a 400.
    "occurred_at",
    "occurred_at_precision",
})

NODE_ALLOWED_ENTITY_TYPES = frozenset({
    # 4 original (v0.1 — present in 99%+ of legacy wiki entities)
    "person", "org", "concept", "document",
    # α-8 horizontal extension (v0.4, 2026-06-03 — must mirror
    # core/ontology.py:ENTITY_TYPES). Without this validator extension,
    # admin node create/update endpoints would reject the new types
    # even though the ontology + typed filter expect them.
    "event", "date", "location", "quantity", "project",
})

NODE_ALLOWED_SENSITIVITY = frozenset({"normal", "sensitive"})

# Per-field caps. Wide enough for realistic wiki use; tight enough that
# a runaway client payload can't blow the frontmatter.
_NAME_CAP    = 200
_ALIAS_CAP   = 80     # per alias
_ALIAS_LIMIT = 20     # max aliases per entity
_SUMMARY_CAP = 4000


def _normalize_aliases(raw) -> List[str]:
    """Unique non-empty alias strings, each ≤ _ALIAS_CAP chars, bounded
    to _ALIAS_LIMIT total. Preserves insertion order so admin controls
    the UI display sequence.
    """
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen: set = set()
    for a in raw:
        if not isinstance(a, str):
            continue
        s = a.strip()[:_ALIAS_CAP]
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= _ALIAS_LIMIT:
            break
    return out


def update_node_attributes(
    entity_id: str,
    patch: Dict[str, Any],
    *,
    wiki_generator,
) -> Dict[str, Any]:
    """PUT-style node attribute update. Allowlisted fields only.

    Returns audit-friendly diff::

        {
          "entity_id":      "...",
          "path":           "wiki/.../foo.md",
          "before":         {"name": "...", ...},   # only changed fields
          "after":          {"name": "...", ...},
          "changed_fields": ["name", "summary"],
        }

    Raises:
      ValueError — entity_id unknown, patch contains an invalid
                   entity_type / sensitivity value, or patch is empty
                   after filtering.
    """
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch must be a non-empty dict")

    # Filter to allowlisted fields first so a malformed payload's other
    # keys can't reach the validation layer.
    filtered: Dict[str, Any] = {}
    for k in NODE_EDITABLE_FIELDS:
        if k in patch:
            filtered[k] = patch[k]
    if not filtered:
        raise ValueError(
            f"patch contains no editable fields; "
            f"allowed: {sorted(NODE_EDITABLE_FIELDS)}"
        )

    # Per-field validation + normalisation. Validation errors raise
    # ValueError so the endpoint can turn them into 400.
    cleaned: Dict[str, Any] = {}
    if "name" in filtered:
        name = filtered["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        cleaned["name"] = name.strip()[:_NAME_CAP]
    if "entity_type" in filtered:
        et = filtered["entity_type"]
        if et not in NODE_ALLOWED_ENTITY_TYPES:
            raise ValueError(
                f"entity_type must be one of "
                f"{sorted(NODE_ALLOWED_ENTITY_TYPES)}; got {et!r}"
            )
        cleaned["entity_type"] = et
    if "aliases" in filtered:
        cleaned["aliases"] = _normalize_aliases(filtered["aliases"])
    if "summary" in filtered:
        summary = filtered["summary"]
        if summary is None:
            cleaned["summary"] = ""
        elif not isinstance(summary, str):
            raise ValueError("summary must be a string (or null to clear)")
        else:
            cleaned["summary"] = summary[:_SUMMARY_CAP]
    if "sensitivity" in filtered:
        sv = filtered["sensitivity"]
        if sv not in NODE_ALLOWED_SENSITIVITY:
            raise ValueError(
                f"sensitivity must be one of "
                f"{sorted(NODE_ALLOWED_SENSITIVITY)}; got {sv!r}"
            )
        cleaned["sensitivity"] = sv

    # Load entity for the event-field branch (need its current
    # entity_type to decide whether occurred_at / precision are
    # honored or silently dropped) AND for the diff + write below.
    path, fm, body = _load_entity_by_id(entity_id, wiki_generator)

    # ── Event time-axis branch (memo §5.2) ──────────────────────
    # occurred_at / occurred_at_precision are honored only when the
    # *existing* node is type=event. For any other type both fields
    # are silently dropped, so an accidental client send doesn't
    # surface as a 400.
    has_event_payload = (
        "occurred_at" in filtered
        or "occurred_at_precision" in filtered
    )
    if has_event_payload and fm.get("entity_type") == "event":
        # Compose the would-be new (value, precision) pair from
        # patch ∪ existing, then validate the pair together so a
        # partial update (only one of the two changing) still gets
        # full ISO 8601 + enum verification.
        new_at = filtered.get(
            "occurred_at", fm.get("occurred_at"),
        )
        new_prec = filtered.get(
            "occurred_at_precision",
            fm.get("occurred_at_precision", "day"),
        )
        validate_occurred_at(new_at, precision=new_prec)
        if "occurred_at" in filtered:
            cleaned["occurred_at"] = filtered["occurred_at"]
        if "occurred_at_precision" in filtered:
            cleaned["occurred_at_precision"] = filtered["occurred_at_precision"]
    # else: non-event target → both fields silently dropped from cleaned.

    before: Dict[str, Any] = {}
    after:  Dict[str, Any] = {}
    changed: List[str] = []
    for k, new_val in cleaned.items():
        old_val = fm.get(k)
        if old_val == new_val:
            continue
        before[k] = old_val
        after[k] = new_val
        fm[k] = new_val
        changed.append(k)

    if not changed:
        # No-op write — return the diff shape with empty changed_fields
        # so the audit log can record "admin clicked save with no edits".
        return {
            "entity_id":      entity_id,
            "path":           str(path),
            "before":         {},
            "after":          {},
            "changed_fields": [],
        }

    # [B-2-A follow-up, PR #446] If summary changed, also rewrite the
    # body's `## 요약` section. Pre-fix the editor patched only the
    # frontmatter, so a Save from the graph node detail panel changed
    # `summary:` in the yaml header but left the visible body section
    # stale — the user reported "edit doesn't reflect immediately".
    if "summary" in changed:
        from core.wiki_generator import sync_summary_body
        body, _body_changed = sync_summary_body(body, fm.get("summary") or "")

    # Touch updated_at so cascade / monitoring picks up the change.
    fm["updated_at"] = datetime.now().isoformat()
    _write_entity(path, fm, body)

    # Refresh wiki_generator index so subsequent reads see the new name.
    # Best-effort — a refresh failure must not invalidate the on-disk
    # write that already succeeded.
    try:
        wiki_generator.refresh_entity_map()
    except Exception:
        pass

    return {
        "entity_id":      entity_id,
        "path":           str(path),
        "before":         before,
        "after":          after,
        "changed_fields": changed,
    }


# ─── Event node creation (PR-11a-2) ─────────────────────────────────
# Events live next to person/concept/org/document under
# `wiki/entity/<source>/event/`. Identity hash includes occurred_at +
# precision per design memo §12 open-question 2: two events on the
# same date with the same name resolve via the hash; events on
# different dates with the same name get distinct entity_ids.

_EVENT_ENTITY_ID_SALT = "JAMES_SECURE_V1"


def _normalize_event_name(name: str) -> str:
    """Filename-safe lowercase form. Mirrors `WikiGenerator._normalize_name`
    so event files coexist cleanly with the existing 4-type filenames.
    """
    return re.sub(r"[^\w가-힣]", "_", name.strip().lower())


def _generate_event_entity_id(
    name: str,
    occurred_at: str,
    occurred_at_precision: str,
) -> str:
    """Hash key: name + occurred_at + precision. Same SALT as the 4-type
    path keeps the overall id space behaving identically (8-hex suffix,
    `e_event_` prefix). The added time fields make distinct dates yield
    distinct ids when the same name recurs.
    """
    normalized = _normalize_event_name(name)
    raw = (
        f"{normalized}_event_{occurred_at}_{occurred_at_precision}"
        f"_{_EVENT_ENTITY_ID_SALT}"
    )
    h = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"e_event_{h}"


def create_event_node(
    name: str,
    occurred_at: str,
    *,
    wiki_generator,
    occurred_at_precision: str = "day",
    aliases: Optional[List[str]] = None,
    source_doc_id: Optional[str] = None,
    source_weight: float = 1.0,
) -> Dict[str, Any]:
    """Create a new `entity_type=event` file under
    ``<entity_path>/event/<normalized>.md`` and return the audit-style
    descriptor.

    Source provenance (Knowledge Cascade `sources[]`):
      - ``source_doc_id`` None → ``role: "manual"`` (admin click)
      - ``source_doc_id`` str  → ``role: "extract"`` (ingest path)

    Raises ``ValueError`` on:
      - empty / non-string ``name``
      - ``occurred_at`` not ISO 8601 parseable
      - ``occurred_at_precision`` not in the 5 supported buckets
      - ``source_weight`` outside ``[0, 1]``
      - file collision after dedup (extremely rare — different
        occurred_at with same normalized name)
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    validate_occurred_at(occurred_at, precision=occurred_at_precision)
    if not isinstance(source_weight, (int, float)):
        raise ValueError("source_weight must be a number")
    if not (0.0 <= float(source_weight) <= 1.0):
        raise ValueError(
            f"source_weight must be in [0, 1]; got {source_weight!r}"
        )

    entity_id = _generate_event_entity_id(
        name, occurred_at, occurred_at_precision,
    )
    cleaned_name    = name.strip()[:_NAME_CAP]
    cleaned_aliases = _normalize_aliases(aliases or [])
    now_iso         = datetime.now().isoformat()
    source_role     = (
        MANUAL_SOURCE_ROLE if source_doc_id is None else EXTRACT_SOURCE_ROLE
    )

    fm: Dict[str, Any] = {
        "entity_id":            entity_id,
        "entity_type":          "event",
        "name":                 cleaned_name,
        "aliases":              cleaned_aliases,
        "occurred_at":          occurred_at,
        "occurred_at_precision": occurred_at_precision,
        "sources": [{
            "doc_id":  source_doc_id,
            "weight":  float(source_weight),
            "role":    source_role,
            "ts":      now_iso,
        }],
        "relations":  [],
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    body = f"\n# {cleaned_name}\n\n*Event of {occurred_at}*\n"

    # Resolve target directory. wiki_generator.entity_path already
    # accounts for prod/test split.
    event_dir = wiki_generator.entity_path / "event"
    event_dir.mkdir(parents=True, exist_ok=True)

    # Always suffix the filename with the entity_id's 8-hex tail.
    # Reason: the hash incorporates name + occurred_at + precision, so
    # two events with the same name on different dates get different
    # filenames AND a duplicate creation (same name + same date) maps
    # to the same filename which collides at the existence check —
    # one branch, no ambiguity.
    normalized = _normalize_event_name(cleaned_name)
    file_path  = event_dir / f"{normalized}_{entity_id[-8:]}.md"
    if file_path.exists():
        raise ValueError(
            f"event already exists: entity_id={entity_id} "
            f"path={file_path}"
        )

    _write_entity(file_path, fm, body)

    # Refresh the index so subsequent reads see the new event.
    # Best-effort: an index refresh failure must not invalidate the
    # on-disk write that already succeeded.
    try:
        wiki_generator.refresh_entity_map()
    except Exception:
        pass

    return {
        "entity_id":   entity_id,
        "path":        str(file_path),
        "frontmatter": fm,
    }


__all__ = [
    "NODE_EDITABLE_FIELDS",
    "NODE_ALLOWED_ENTITY_TYPES",
    "NODE_ALLOWED_SENSITIVITY",
    "update_node_attributes",
    "create_event_node",
]
