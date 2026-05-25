"""Backfill entity-name overlap RELATED_TO relations on existing wiki entities.

v0.4 Sprint 1 #1 follow-up — closes the data-correctness gap that
PR #493 fixed at the ingestion plumbing layer. Wiki entities
created before PR #493 (e.g. the 2026-05-25 "비트코인 spot ETF
11개 일괄 승인" event row) keep their broken state until either
the source document is re-ingested or this script applies the
overlap detection directly on the entity frontmatter.

Workflow:

  --dry-run (default)
    Walks every entity under `wiki/entity/prod/{org,event,
    concept,document,person}`, computes the overlap snapshot
    once, runs `_infer_overlap_relations` for each entity, and
    prints what would be added. No files touched.

  --apply
    Same walk + same computation, but writes the new
    RELATED_TO relations into each entity's frontmatter
    relations list. Backup the wiki directory before running.

  --entity-type {org|event|concept|document|person}
    Restrict the walk to one entity type. Default: all types.

  --entity-id <eid>
    Restrict to a single entity by id (matches the
    `entity_id` frontmatter field). Useful for testing the
    fix on the specific case (e.g.
    `--entity-id e_event_22d304d2` for the 비트코인 event).

  --confidence-floor <float>
    Skip emitted relations below this confidence. Default 0.5
    (the `_infer_overlap_relations` baseline).

Each emitted relation carries:
  - confidence = 0.5
  - inferred   = True
  - sources[]  = [{role: "inferred-overlap-backfill", ts: <now>}]

The "backfill" suffix on the role distinguishes the post-hoc
write from ingestion-time relations (`inferred-overlap`).
Operators can audit which relations came from this script
with a single grep:

  grep -lr "role: inferred-overlap-backfill" wiki/entity/prod/
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Allow the script to import core/* when run from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _write_frontmatter_inline(path: Path, fm: dict) -> None:
    """Replace the frontmatter block of an entity .md file with `fm`
    (yaml-serialized), preserving the body below the second `---`.

    Mirrors the inline pattern in
    `core/wiki_generator/_merge.py:_merge_relations_into_existing_entity`
    so the file shape stays identical to what ingestion writes.
    """
    import yaml
    text = path.read_text(encoding="utf-8")
    # Split on the second '---\n' to separate frontmatter from body
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: missing frontmatter delimiter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"{path.name}: missing closing frontmatter delimiter")
    body = text[end + len("\n---\n"):].lstrip("\n")
    new_text = (
        "---\n"
        + yaml.dump(fm, allow_unicode=True, default_flow_style=False)
        + "---\n\n"
        + body
    )
    path.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true",
        help="write changes to wiki frontmatter (default: dry-run only)",
    )
    parser.add_argument(
        "--entity-type", choices=("org", "event", "concept", "document", "person"),
        default=None,
        help="restrict to one entity type (default: all types)",
    )
    parser.add_argument(
        "--entity-id", default=None,
        help="restrict to one entity by entity_id (e.g. e_event_22d304d2)",
    )
    parser.add_argument(
        "--confidence-floor", type=float, default=0.5,
        help="skip emitted relations below this confidence (default 0.5)",
    )
    parser.add_argument(
        "--wiki-root", default=None,
        help="wiki root override (default: config.WIKI_DIR)",
    )
    args = parser.parse_args()

    from config import WIKI_DIR
    wiki_root = Path(args.wiki_root or WIKI_DIR)
    if not wiki_root.exists():
        print(f"[ERROR] wiki root not found: {wiki_root}")
        return 2

    from core.wiki_generator import WikiGenerator

    # Use the production WikiGenerator so the overlap snapshot is
    # computed from the same code path that ingestion uses.
    # WikiGenerator reads WIKI_DIR from config; --wiki-root override
    # is honored via env if the operator runs it explicitly.
    wg = WikiGenerator(source_type="prod")

    print(f"[BACKFILL] wiki_root = {wiki_root}")
    print(f"[BACKFILL] mode      = {'APPLY (writes)' if args.apply else 'DRY-RUN (no writes)'}")
    print(f"[BACKFILL] entities loaded: {len(wg.entity_id_index)}")

    snapshot = wg._build_overlap_snapshot()
    print(f"[BACKFILL] overlap snapshot keys: {len(snapshot)}")

    ts_now = datetime.now().isoformat()
    role = "inferred-overlap-backfill"

    walk_types = (args.entity_type,) if args.entity_type \
        else ("org", "event", "concept", "document", "person")

    total_inspected = 0
    total_emitted = 0
    total_written = 0
    files_changed = 0

    for et in walk_types:
        d = wiki_root / "entity" / "prod" / et
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            fm = wg._read_frontmatter(f)
            if not fm:
                continue
            eid = fm.get("entity_id", "")
            if args.entity_id and eid != args.entity_id:
                continue
            total_inspected += 1
            name = fm.get("name", "")
            if not name:
                continue
            overlap_rels = wg._infer_overlap_relations(
                name, snapshot, doc_id=None, ts=ts_now,
            )
            # Filter: skip relations already present (by target+label)
            # and below the confidence floor.
            existing = {
                (r.get("target", ""), r.get("label", ""))
                for r in (fm.get("relations") or [])
                if isinstance(r, dict)
            }
            new_rels = []
            for r in overlap_rels:
                if r.get("confidence", 0.0) < args.confidence_floor:
                    continue
                key = (r.get("target", ""), r.get("label", ""))
                if key in existing:
                    continue
                # Stamp the backfill role + ts (without doc_id, since
                # there is no fresh source doc — this is a post-hoc
                # plumbing-fix application).
                r["sources"] = [{
                    "doc_id": None,
                    "weight": r.get("confidence", 0.5),
                    "role":   role,
                    "ts":     ts_now,
                }]
                new_rels.append(r)

            if not new_rels:
                continue
            total_emitted += len(new_rels)

            print(f"  [{et}] {name!r} (id={eid}) +{len(new_rels)} relation(s):")
            for r in new_rels:
                print(f"      -> {r['target']!r} ({r.get('target_type','')}/"
                      f"{r.get('target_id','')}) conf={r['confidence']}")

            if args.apply:
                # Append new relations into the existing list (don't
                # replace — explicit ingestion-time relations stay).
                merged = list(fm.get("relations") or [])
                merged.extend(new_rels)
                fm["relations"] = merged
                fm["updated_at"] = ts_now
                try:
                    _write_frontmatter_inline(f, fm)
                    total_written += len(new_rels)
                    files_changed += 1
                except Exception as e:
                    print(f"      ERROR writing {f.name}: {e}")

    print("")
    print(f"[BACKFILL] inspected      : {total_inspected} entities")
    print(f"[BACKFILL] would emit     : {total_emitted} new relations")
    if args.apply:
        print(f"[BACKFILL] written        : {total_written} relations across "
              f"{files_changed} files")
    else:
        print("[BACKFILL] DRY-RUN -- pass --apply to actually write the changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
