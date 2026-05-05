"""Backfill inverse `relations` for existing wiki entities (Issue #11).

Before this fix, `wiki_generator._build_entity_relations` only kept
relations whose `source == this entity's name`, leaving target-side
entities with `relations: []`. The result: `match_entities` could
locate an entity, but `expand_dynamic` had nothing to walk to, so
graph_paths stayed empty.

This one-shot script walks every existing entity, gathers their
outgoing relations, and ensures the corresponding target entity has
an inverse entry in its own `relations` field.

Usage:
    python scripts/migrate_inverse_relations.py             # dry run
    python scripts/migrate_inverse_relations.py --apply     # write

Idempotent: re-running after --apply is a no-op (existing inverse
entries are detected and skipped).

`relations` items are kept in the same shape `create_entity_file`
produces — `target`, `target_id`, `target_type`, `type`, `label`,
`confidence`, plus an `inferred: True` marker so analytics can
distinguish backfilled entries from LLM-extracted ones.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.wiki_generator import WikiGenerator  # noqa: E402

WIKI_BASE = ROOT / "wiki" / "entity"
FM_RE     = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def read_frontmatter(path: Path) -> tuple[dict, str] | None:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    return fm, m.group(2)


def write_frontmatter(path: Path, fm: dict, body: str) -> None:
    text = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False,
    ).rstrip()
    path.write_text(f"---\n{text}\n---\n{body}", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually rewrite files (default: dry run)")
    args = ap.parse_args()

    files = sorted(WIKI_BASE.rglob("*.md"))
    print(f"Scanning {len(files)} entity files under "
          f"{WIKI_BASE.relative_to(ROOT)}/")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    # Phase 1 — read everything, build lookup tables
    entries: dict[Path, tuple[dict, str]] = {}
    name_to_eid: dict[str, str]      = {}
    name_to_type: dict[str, str]     = {}
    eid_to_path: dict[str, Path]     = {}

    for f in files:
        parsed = read_frontmatter(f)
        if not parsed:
            continue
        fm, body = parsed
        entries[f] = (fm, body)
        eid  = fm.get("entity_id")
        name = fm.get("name")
        et   = fm.get("entity_type")
        if eid and name and et:
            name_to_eid[name]   = eid
            name_to_type[name]  = et
            eid_to_path[eid]    = f

    # Phase 2 — collect inverse edges
    # inverse_to_add: dst_eid → list of {target, label, confidence, target_id, target_type}
    inverse_to_add: dict[str, list[dict]] = defaultdict(list)

    for src_path, (fm, _body) in entries.items():
        src_name = fm.get("name", "")
        src_eid  = fm.get("entity_id", "")
        src_type = fm.get("entity_type", "concept")
        for rel in fm.get("relations") or []:
            if not isinstance(rel, dict):
                continue
            tgt_name = rel.get("target", "")
            tgt_id   = rel.get("target_id", "")
            label    = rel.get("label", "관련")
            conf     = rel.get("confidence", 0.7)

            if not tgt_id or tgt_id == "UNRESOLVED":
                tgt_id = name_to_eid.get(tgt_name, "")
            if not tgt_id or tgt_id not in eid_to_path:
                continue   # target entity not in wiki — skip

            inv_label = WikiGenerator._inverse_label_for(label)
            inverse_to_add[tgt_id].append({
                "target":      src_name,
                "target_id":   src_eid,
                "target_type": src_type,
                "label":       inv_label,
                "confidence":  conf,
            })

    # Phase 3 — apply per target entity (dedup against existing)
    files_changed = 0
    edges_added   = 0
    for tgt_eid, inv_list in inverse_to_add.items():
        path = eid_to_path[tgt_eid]
        fm, body = entries[path]
        existing = fm.get("relations") or []
        existing_keys = {
            (r.get("target", ""), r.get("label", ""))
            for r in existing if isinstance(r, dict)
        }
        added_here: list[dict] = []
        for inv_rel in inv_list:
            key = (inv_rel["target"], inv_rel["label"])
            if key in existing_keys:
                continue
            inv_rel["inferred"] = True   # backfill marker
            existing_keys.add(key)
            added_here.append(inv_rel)

        if not added_here:
            continue

        files_changed += 1
        edges_added   += len(added_here)
        new_relations = list(existing) + added_here
        fm["relations"] = new_relations
        rel_path = path.relative_to(ROOT)
        labels = sorted({r["label"] for r in added_here})
        targets = ", ".join(sorted({r["target"] for r in added_here}))[:80]
        print(f"  + {rel_path} (+{len(added_here)} edges; labels: {labels})")
        print(f"      from: {targets}")

        if args.apply:
            write_frontmatter(path, fm, body)

    print(f"\nresult: {files_changed}/{len(files)} files updated, "
          f"{edges_added} inverse edges added")
    if not args.apply and files_changed > 0:
        print("Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
