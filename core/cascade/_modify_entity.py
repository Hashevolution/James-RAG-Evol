"""``core.cascade._modify_entity`` — entity-edit lifecycle cascade
(Phase 1: invalidate stale relations).

When a wiki entity is edited and saved, the graph (= the entity's
frontmatter ``relations:`` arrays — there is no separate graph store)
must not keep asserting relations the new text no longer supports.
``update_entity`` previously re-embedded the vector chunks only, leaving
the graph relations stale → graph reasoning could cite a relation the
edited text dropped.

This module re-extracts relations from the edited prose, diffs them
against the entity's current frontmatter relations, and **invalidates**
(preserves, never hard-deletes — replay audit) any relation the new text
no longer supports, emitting a lifecycle event per invalidation.

Phase 1 = invalidate the *dangerous* direction (graph asserting a dropped
relation). Phase 2 = materialise newly-implied edges (the safe direction)
as MANUAL-sourced relations with target_id UNRESOLVED, then back-fill via
``resolve_pending_relations`` — so the edited text's new relations become
real graph edges, not just a report.

Design: docs/design/v0.6.1-entity-edit-cascade.md.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ._helpers import _read_frontmatter, _write_frontmatter


def _triple_key(source: str, label: str, target: str):
    return (
        (source or "").strip().lower(),
        (label or "관련").strip().lower(),
        (target or "").strip().lower(),
    )


def _emit_invalidate(entity_name: str, rel: Dict[str, Any],
                     ts: str, user_role: str) -> None:
    try:
        from core.lifecycle.replay_audit import (
            EVT_CASCADE_INVALIDATE, emit_lifecycle_event,
        )
        emit_lifecycle_event(
            EVT_CASCADE_INVALIDATE,
            {
                "reason":  "entity_edit",
                "entity":  entity_name,
                "edge_id": rel.get("id") or "",
                "target":  rel.get("target"),
                "label":   rel.get("label"),
                "ts":      ts,
            },
            user_role=user_role,
        )
    except Exception:
        # lifecycle logging is best-effort; never break the edit.
        pass


def cascade_modify_entity(entity_path, entity_name: str, *,
                          wiki_generator, user_role: str = "admin") -> Dict[str, Any]:
    """Phase 1 entity-edit cascade. Best-effort: returns a summary dict
    and never raises (the caller's save must survive a cascade failure).

    Returns: {
      ok:             bool,    # the cascade ran (extraction succeeded)
      extracted:      bool,
      invalidated:    [{target, label, edge_id}],   # stale edges deactivated
      added:          [{target, label}],            # new MANUAL edges added
      skipped_reason: str,
    }
    """
    summary: Dict[str, Any] = {
        "ok": False, "extracted": False,
        "invalidated": [], "added": [], "skipped_reason": "",
    }
    if os.environ.get("JAMES_DISABLE_EDIT_CASCADE") == "1":
        summary["skipped_reason"] = "disabled"
        return summary
    try:
        path = Path(entity_path)
        parsed = _read_frontmatter(path)
        if not parsed:
            summary["skipped_reason"] = "no_frontmatter"
            return summary
        fm, body = parsed
        relations = fm.get("relations") or []

        # Re-extract relations from the edited prose (best-effort).
        try:
            new_ext = wiki_generator._llm_extract_document_entities(
                entity_name, body, {}) or {}
        except Exception as e:  # noqa: BLE001
            summary["skipped_reason"] = f"extract_failed: {e}"
            return summary
        summary["extracted"] = True

        new_rels = new_ext.get("relations", []) or []
        new_keys = {
            _triple_key(r.get("source"), r.get("label"), r.get("target"))
            for r in new_rels if isinstance(r, dict)
        }
        name_l = (entity_name or "").strip().lower()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ── invalidate stale edges (the dangerous direction) ──
        changed = False
        for rel in relations:
            if not isinstance(rel, dict):
                continue
            status = rel.get("status") or {}
            if status.get("active") is False:
                continue  # already inactive
            key = _triple_key(entity_name, rel.get("label"), rel.get("target"))
            if key not in new_keys:
                rel.setdefault("status", {})
                rel["status"]["active"] = False
                rel["status"]["invalidated_at"] = ts
                rel["mutation_type"] = "invalidated"
                changed = True
                summary["invalidated"].append({
                    "target":  rel.get("target"),
                    "label":   rel.get("label"),
                    "edge_id": rel.get("id") or "",
                })
                _emit_invalidate(entity_name, rel, ts, user_role)

        # ── Phase 2: materialise newly-implied edges (the safe direction) ──
        # New outgoing relations the edited text now asserts but the graph
        # lacks. Added as MANUAL-sourced edges (so a future doc cascade
        # preserves them) with target_id UNRESOLVED → resolved after write.
        from core.relations_schema import MANUAL_SOURCE_ROLE
        cur_keys = {
            _triple_key(entity_name, r.get("label"), r.get("target"))
            for r in relations if isinstance(r, dict)
        }
        for r in new_rels:
            if not isinstance(r, dict):
                continue
            if (r.get("source") or "").strip().lower() != name_l:
                continue
            tgt = (r.get("target") or "").strip()
            label = (r.get("label") or "관련").strip()[:20]
            if not tgt:
                continue
            key = _triple_key(entity_name, label, tgt)
            if key in cur_keys:
                continue
            try:
                conf = float(r.get("confidence", 0.7))
            except (TypeError, ValueError):
                conf = 0.7
            conf = max(0.0, min(1.0, conf))
            relations.append({
                "target":     tgt,
                "target_id":  "UNRESOLVED",
                "label":      label,
                "confidence": conf,
                "sources":    [{"doc_id": entity_name, "weight": conf,
                                "role": MANUAL_SOURCE_ROLE, "ts": ts}],
                "status":        {"active": True},
                "mutation_type": "active",
            })
            cur_keys.add(key)
            changed = True
            summary["added"].append({"target": tgt, "label": label})

        if changed:
            fm["relations"] = relations
            _write_frontmatter(path, fm, body)  # this IS the graph update
            # back-fill target_id for the freshly-added edges (best-effort).
            if summary["added"]:
                try:
                    wiki_generator.resolve_pending_relations()
                except Exception:
                    pass
        summary["ok"] = True
        return summary
    except Exception as e:  # noqa: BLE001
        summary["skipped_reason"] = f"error: {e}"
        return summary


__all__ = ["cascade_modify_entity"]
