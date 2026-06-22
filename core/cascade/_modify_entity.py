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


def _propagate_inbound_t6(entity_name, invalidated, *,
                          wiki_generator, user_role, ts):
    """Phase 3 — for each invalidated outgoing edge A→B: invalidate the
    inverse edge B→A on the target entity, and (if A→B carries an edge id)
    T6-cascade facts derived from it. Best-effort; never raises."""
    out = {"inverse_invalidated": [], "derived_invalidated": []}
    idx = getattr(wiki_generator, "entity_id_index", {}) or {}
    name_l = (entity_name or "").strip().lower()
    inv_label_fn = getattr(wiki_generator, "_inverse_label_for", None)
    entity_root = getattr(wiki_generator, "entity_path", None)

    for inv in invalidated:
        # (a) inverse edge B→A on the target entity
        tgt_id = inv.get("target_id")
        tpath = idx.get(tgt_id) if tgt_id else None
        if tpath:
            try:
                parsed = _read_frontmatter(Path(tpath))
            except Exception:
                parsed = None
            if parsed:
                tfm, tbody = parsed
                want_label = None
                if callable(inv_label_fn):
                    try:
                        want_label = (inv_label_fn(inv.get("label")) or "").strip().lower()
                    except Exception:
                        want_label = None
                changed = False
                for r in (tfm.get("relations") or []):
                    if not isinstance(r, dict):
                        continue
                    if (r.get("status") or {}).get("active") is False:
                        continue
                    if (r.get("target") or "").strip().lower() != name_l:
                        continue
                    # prefer the computed inverse label; else any B→A edge
                    # (entity pairs rarely carry multiple distinct relations).
                    if want_label and (r.get("label") or "").strip().lower() != want_label:
                        continue
                    r.setdefault("status", {})
                    r["status"]["active"] = False
                    r["status"]["invalidated_at"] = ts
                    r["mutation_type"] = "invalidated"
                    changed = True
                    out["inverse_invalidated"].append({
                        "entity_id": tgt_id, "label": r.get("label"),
                    })
                    _emit_invalidate(entity_name, r, ts, user_role)
                if changed:
                    try:
                        _write_frontmatter(Path(tpath), tfm, tbody)
                    except Exception:
                        pass
        # (b) T6 — facts derived from the invalidated edge (needs an id)
        eid = inv.get("edge_id")
        if eid and entity_root:
            try:
                from core.lifecycle.causality import invalidate_derived_facts
                derived = invalidate_derived_facts(eid, entity_root)
                if derived:
                    out["derived_invalidated"].extend(derived)
            except Exception:
                pass
    return out


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
        "invalidated": [], "added": [],
        "inverse_invalidated": [], "derived_invalidated": [],
        "skipped_reason": "",
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
                    "target":    rel.get("target"),
                    "target_id": rel.get("target_id") or "",
                    "label":     rel.get("label"),
                    "edge_id":   rel.get("id") or "",
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

        # ── Phase 3: inbound (inverse edge) + T6 derived-fact propagation ──
        # An invalidated outgoing edge A→B leaves a stale inverse B→A on
        # the target entity, and any fact DERIVED from A→B. Sweep both so
        # the whole neighbourhood stays consistent, not just A's own row.
        if summary["invalidated"]:
            prop = _propagate_inbound_t6(
                entity_name, summary["invalidated"],
                wiki_generator=wiki_generator, user_role=user_role, ts=ts)
            summary["inverse_invalidated"] = prop["inverse_invalidated"]
            summary["derived_invalidated"] = prop["derived_invalidated"]

        summary["ok"] = True
        return summary
    except Exception as e:  # noqa: BLE001
        summary["skipped_reason"] = f"error: {e}"
        return summary


__all__ = ["cascade_modify_entity"]
