"""
PROJECT JAMES — Graph Snapshot (v0.2 Axis 3 Observability)

Read-only enumeration of every wiki entity + ontology relation as a single
JSON-serializable structure for the `/admin/graph` 3D reasoning visualizer.

Design notes:
  * Sibling to `core/graph_engine.py` so the latter stays well under the
    20 KB module-size gate (Axis 1).
  * `core/wiki_generator.py` already exposes `entity_id_index` and
    `_read_frontmatter()`; we reuse them rather than re-walking the disk
    layout or duplicating frontmatter parsing.
  * `core/ontology.py:RELATION_TYPES` is the single source of truth for
    `sensitive=True` relations — we filter those by default.
  * Cache key is `(source_type, include_sensitive, max_mtime)` so
    in-process invalidation is automatic on any wiki edit.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.ontology import RELATION_TYPES, normalize_relation


# ─── Cache ────────────────────────────────────────────────────

_CACHE_LOCK = threading.Lock()
_CACHE: Dict[Tuple[str, bool], Tuple[float, Dict[str, Any]]] = {}
# key:   (source_type, include_sensitive)
# value: (max_mtime_seen, snapshot_dict)


def _scan_max_mtime(entity_path: Path, entity_types: List[str]) -> float:
    """Walk wiki/entity/<src>/{type}/*.md and return the max mtime.

    Cheap O(N) scandir; cache invalidation hinges on this returning a
    strictly higher value when any entity file is added / edited.
    """
    latest = 0.0
    for t in entity_types:
        d = entity_path / t
        if not d.exists():
            continue
        try:
            with os.scandir(d) as it:
                for ent in it:
                    if ent.is_file() and ent.name.endswith(".md"):
                        m = ent.stat().st_mtime
                        if m > latest:
                            latest = m
        except OSError:
            continue
    return latest


# ─── Snapshot builder ─────────────────────────────────────────

def _entity_id_pattern_ok(eid: str) -> bool:
    """Same shape as graph_engine's integrity check. Lightweight inline
    copy so this module has zero dependency on graph_engine."""
    if not isinstance(eid, str) or not eid.startswith("e_"):
        return False
    parts = eid.split("_")
    if len(parts) < 3:
        return False
    return all(c.isalnum() or c == "_" for c in eid)


def build_snapshot(
    wiki_generator,
    source_type: str = "prod",
    include_sensitive: bool = False,
) -> Dict[str, Any]:
    """Materialize the full entity-and-relation graph as JSON.

    Args:
        wiki_generator:    a `WikiGenerator` instance whose `entity_id_index`
                           and `_read_frontmatter` we read. Pulled from the
                           shared `rag_engine.wiki_generator` so we do not
                           rebuild the index.
        source_type:       'prod' / 'test' / 'all'. Defaults to 'prod'. The
                           wiki_generator we receive is already source-scoped
                           (see WikiGenerator.__init__), so this argument is
                           informational metadata only.
        include_sensitive: if False (default), drop:
                             - any node whose `sensitivity == "sensitive"`
                             - any edge whose ontology entry has
                               `sensitive == True` (HAS_SECRET, etc.)
                           True is allowed only by callers that already
                           gated the request on an elevated role.

    Returns: dict with keys `nodes`, `edges`, `meta`. See MODULE docstring
    for the wire shape.
    """
    cache_key = (source_type, bool(include_sensitive))
    entity_path: Path = wiki_generator.entity_path
    entity_types: List[str] = wiki_generator.entity_types
    max_mtime = _scan_max_mtime(entity_path, entity_types)

    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] == max_mtime:
            return cached[1]

    # Cache miss → disk has been touched since the last snapshot. A
    # *different* RAGEngine instance (e.g. the throwaway one constructed
    # inside `tools.web.web_searcher.save_as_longterm`) may have written
    # new entity files without updating THIS instance's in-memory
    # `entity_id_index`. The mtime scan above catches the disk change,
    # but rebuilding from a stale index would still skip the new files —
    # the user saw this as "wiki entity added, /graph stale until server
    # restart". Re-scan disk before the rebuild so newly-written entities
    # appear on the next snapshot.
    refresh = getattr(wiki_generator, "refresh_entity_map", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass

    # ── Load every entity frontmatter once. ──
    raw_entities: Dict[str, Dict[str, Any]] = {}
    for eid, fpath in wiki_generator.entity_id_index.items():
        if not _entity_id_pattern_ok(eid):
            continue
        try:
            fm = wiki_generator._read_frontmatter(Path(fpath))
        except Exception:
            fm = None
        if not fm:
            continue
        raw_entities[eid] = fm

    # ── Pass 1: build node list with sensitivity filter. ──
    nodes: List[Dict[str, Any]] = []
    kept_ids: set[str] = set()
    for eid, fm in raw_entities.items():
        sensitivity = fm.get("sensitivity", "internal")
        if not include_sensitive and sensitivity == "sensitive":
            continue
        nodes.append({
            "id":          eid,
            "name":        fm.get("name", eid),
            "type":        fm.get("entity_type", fm.get("type", "concept")),
            "sensitivity": sensitivity,
            "degree":      0,  # filled in pass 2
        })
        kept_ids.add(eid)

    # ── Pass 2: walk relations, drop sensitive types, count degree. ──
    edges: List[Dict[str, Any]] = []
    degree: Dict[str, int] = {nid: 0 for nid in kept_ids}
    for eid, fm in raw_entities.items():
        if eid not in kept_ids:
            continue
        for rel in fm.get("relations", []) or []:
            if not isinstance(rel, dict):
                continue
            target_id = rel.get("target_id") or ""
            if not target_id or target_id == "UNRESOLVED":
                continue
            if target_id == eid:
                continue
            if target_id not in kept_ids:
                # target was filtered out (sensitive, or missing file)
                continue

            raw_type = rel.get("type") or rel.get("label") or "RELATED_TO"
            std = normalize_relation(raw_type)
            info = RELATION_TYPES.get(std, {})
            if not include_sensitive and info.get("sensitive", False):
                continue

            try:
                weight = float(info.get("weight", 0.7))
            except (TypeError, ValueError):
                weight = 0.7
            try:
                conf = float(rel.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0

            edges.append({
                "s":        eid,
                "t":        target_id,
                "type":     std,
                "weight":   round(weight, 3),
                "conf":     round(conf, 3),
                "inferred": bool(rel.get("inferred", False)),
            })
            degree[eid]      = degree.get(eid, 0) + 1
            degree[target_id] = degree.get(target_id, 0) + 1

    # Backfill degree onto node dicts.
    for n in nodes:
        n["degree"] = degree.get(n["id"], 0)

    # ── Soft-cap edges to keep payload bounded. Top weight + conf wins. ──
    EDGE_HARD_CAP = 10_000
    truncated = False
    if len(edges) > EDGE_HARD_CAP:
        edges.sort(key=lambda e: (e["weight"] * e["conf"]), reverse=True)
        edges = edges[:EDGE_HARD_CAP]
        truncated = True

    # ── Snapshot hash for cache validation tests. ──
    sig_src = json.dumps(
        {"n": len(nodes), "e": len(edges), "m": max_mtime},
        sort_keys=True,
    ).encode("utf-8")
    snapshot_hash = hashlib.sha1(sig_src).hexdigest()[:12]

    snapshot = {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "source_type":     source_type,
            "include_sensitive": bool(include_sensitive),
            "node_count":      len(nodes),
            "edge_count":      len(edges),
            "truncated":       truncated,
            "edge_hard_cap":   EDGE_HARD_CAP,
            "generated_at_ns": time.time_ns(),
            "snapshot_hash":   snapshot_hash,
        },
    }

    with _CACHE_LOCK:
        _CACHE[cache_key] = (max_mtime, snapshot)

    return snapshot


def invalidate_cache() -> None:
    """Test/admin escape hatch — drop every cached snapshot."""
    with _CACHE_LOCK:
        _CACHE.clear()
