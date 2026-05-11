"""Hard merge wiki entities by synonym group (Issue #20).

PR #19 wired ``wiki/synonyms.yaml`` into a bidirectional alias index so
that ``match_entities("BTC")`` and ``match_entities("비트코인")`` both
land on whichever .md the LLM happened to write first. The two .md
files still co-exist, though, and any other entity that points at the
"wrong" one keeps its incoming graph edge attached to the duplicate.

This one-shot script collapses each synonym group into a single
canonical entity:

  1. For every group in ``wiki/synonyms.yaml`` find the .md whose
     ``normalized_name`` matches the canonical surface form. That is
     the survivor.
  2. Find every other .md whose ``normalized_name`` matches one of the
     group's alias forms. Those are the drops.
  3. Reject the group (loud warning, no changes) if any drop has a
     different ``entity_type`` than the canonical — Aider-the-org and
     Aider-the-concept must not silently fuse.
  4. Absorb each drop into the canonical: union ``aliases``,
     ``sources``, ``embedding_refs``; merge ``relations`` (dedup on
     ``(target_id, label)`` and skip self-loops); take ``max``
     ``confidence``; fall back to drop ``attributes`` only for keys
     the canonical lacks.
  5. Rewrite every other .md whose ``relations[*].target_id`` equals
     a dropped ``entity_id`` so it points at the canonical instead
     (with the same ``(target_id, label)`` dedup pass).
  6. Delete the dropped .md files.

Usage::

    python scripts/migrate_entity_hard_dedup.py             # dry run
    python scripts/migrate_entity_hard_dedup.py --apply     # write
    python scripts/migrate_entity_hard_dedup.py --apply --no-backup

Idempotent: re-running after ``--apply`` is a no-op (the dropped .md
files no longer exist, so each group resolves to one .md and there
is nothing to merge).

Safety:
  - ``--apply`` writes a zip backup of ``wiki/entity/prod/`` to
    ``workspace/backups/entity_prod_<UTC>.zip`` before any mutation
    unless ``--no-backup`` is set. The script aborts if the backup
    cannot be written.
  - ChromaDB needs no follow-up action. Document chunks are keyed by
    UUID and the metadata schema does not store ``entity_id`` (only
    ``source``/``sensitivity``/``owner``/``category``/``source_type``).
    Entity → ``entity_id`` resolution happens at query time from .md
    frontmatter via ``graph_engine.match_entities`` (which now sees
    the merged canonical + alias index), so the migration is
    reflected automatically at next query without re-indexing.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.console import ensure_utf8_console  # noqa: E402

ensure_utf8_console()

WIKI_BASE     = ROOT / "wiki" / "entity" / "prod"
SYNONYMS_FILE = ROOT / "wiki" / "synonyms.yaml"
BACKUP_DIR    = ROOT / "workspace" / "backups"
FM_RE         = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


# -- helpers --------------------------------------------------------------


def normalize(name: str) -> str:
    """Mirror of ``WikiGenerator._normalize_name`` — kept inline so the
    script stays runnable without instantiating WikiGenerator."""
    return re.sub(r"[^\w가-힣]", "_", str(name).strip().lower())


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


def union_list(*lists: object) -> list:
    """Order-preserving dedup union of any number of list-likes."""
    seen: set = set()
    out: list = []
    for lst in lists:
        if not isinstance(lst, list):
            if lst:
                lst = [lst]
            else:
                continue
        for item in lst:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def dedup_relations(rels: list, drop_target: str | None = None) -> list:
    """Dedup on (target_id, label). Drop self-loops where target_id
    equals ``drop_target`` (used to strip the canonical→canonical
    relations that arise when absorbing a drop entity)."""
    seen: set = set()
    out: list = []
    for r in rels:
        if not isinstance(r, dict):
            continue
        tid = r.get("target_id", "")
        lbl = r.get("label", "")
        if drop_target and tid == drop_target:
            continue   # self-loop after rewrite
        key = (tid, lbl)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# -- backup ---------------------------------------------------------------


def make_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = BACKUP_DIR / f"entity_prod_{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in WIKI_BASE.rglob("*.md"):
            zf.write(f, f.relative_to(WIKI_BASE))
    return out


# -- core -----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually rewrite/delete files (default: dry run)")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the pre-apply backup zip (NOT recommended)")
    args = ap.parse_args()

    if not SYNONYMS_FILE.exists():
        print(f"[FATAL] synonyms.yaml not found: {SYNONYMS_FILE}")
        return 2

    if not WIKI_BASE.exists():
        print(f"[FATAL] wiki entity dir not found: {WIKI_BASE}")
        return 2

    groups = yaml.safe_load(SYNONYMS_FILE.read_text(encoding="utf-8")) or []
    if not isinstance(groups, list):
        print("[FATAL] synonyms.yaml is not a list of groups")
        return 2

    files = sorted(WIKI_BASE.rglob("*.md"))
    print(f"Scanning {len(files)} entity files under "
          f"{WIKI_BASE.relative_to(ROOT)}/")
    print(f"Synonym groups: {len(groups)}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    # Phase 1 — index every entity ----------------------------------------
    entries: dict[Path, tuple[dict, str]]    = {}
    norm_to_path: dict[str, list[Path]]      = defaultdict(list)
    eid_to_path: dict[str, Path]             = {}

    for f in files:
        parsed = read_frontmatter(f)
        if not parsed:
            continue
        fm, body = parsed
        entries[f] = (fm, body)
        nn = fm.get("normalized_name") or normalize(fm.get("name", ""))
        if nn:
            norm_to_path[nn].append(f)
        eid = fm.get("entity_id")
        if eid:
            eid_to_path[eid] = f

    # Phase 2 — resolve groups -------------------------------------------
    # canonical_path → list[drop_path]
    plan: list[tuple[Path, list[Path]]] = []
    drop_eid_to_canonical_eid: dict[str, str] = {}
    skipped: list[str] = []

    for grp in groups:
        if not isinstance(grp, dict):
            continue
        canonical = grp.get("canonical")
        aliases   = grp.get("aliases") or []
        if not canonical:
            continue
        forms = [canonical] + [a for a in aliases if a]
        norms = list({normalize(f): None for f in forms}.keys())   # ordered set

        # collect every .md whose normalized_name matches any form
        matched: list[Path] = []
        for nn in norms:
            for p in norm_to_path.get(nn, []):
                if p not in matched:
                    matched.append(p)

        if not matched:
            continue   # no entities use this group at all — silent skip
        if len(matched) == 1:
            continue   # already a single .md — nothing to merge

        # canonical = match whose normalized_name equals normalize(canonical)
        canon_norm = normalize(canonical)
        canon_paths = [p for p in matched
                       if (entries[p][0].get("normalized_name")
                           or normalize(entries[p][0].get("name", "")))
                       == canon_norm]

        if len(canon_paths) == 0:
            # canonical name has no .md — promote the first match to
            # canonical so we still merge, but be loud about it.
            canonical_path = matched[0]
            print(f"  [WARN] group '{canonical}': no .md matches the "
                  f"canonical surface form; promoting "
                  f"{canonical_path.relative_to(ROOT)} as survivor")
        elif len(canon_paths) > 1:
            print(f"  [SKIP] group '{canonical}': {len(canon_paths)} "
                  f"entities share the canonical normalized_name "
                  f"({[p.name for p in canon_paths]}) — manual review")
            skipped.append(canonical)
            continue
        else:
            canonical_path = canon_paths[0]

        drops = [p for p in matched if p != canonical_path]

        # entity_type sanity check
        canon_type = entries[canonical_path][0].get("entity_type")
        type_conflicts = [
            p for p in drops
            if entries[p][0].get("entity_type") != canon_type
        ]
        if type_conflicts:
            print(f"  [SKIP] group '{canonical}': entity_type conflict "
                  f"(canonical={canon_type}, conflicts="
                  f"{[(p.name, entries[p][0].get('entity_type')) for p in type_conflicts]}"
                  f") — split into separate groups in synonyms.yaml")
            skipped.append(canonical)
            continue

        plan.append((canonical_path, drops))
        canon_eid = entries[canonical_path][0].get("entity_id", "")
        for dp in drops:
            drop_eid = entries[dp][0].get("entity_id", "")
            if drop_eid and canon_eid:
                drop_eid_to_canonical_eid[drop_eid] = canon_eid

    if not plan:
        print("\nNo groups need merging — wiki already deduplicated.")
        if skipped:
            print(f"({len(skipped)} groups skipped: {skipped})")
        return 0

    # Phase 3 — absorb drops into canonical ------------------------------
    for canonical_path, drops in plan:
        canon_fm, canon_body = entries[canonical_path]
        canon_eid = canon_fm.get("entity_id", "")
        canon_name = canon_fm.get("name", "")
        rel_canon = canonical_path.relative_to(ROOT)
        print(f"\nGroup: {canon_name} ← {[p.stem for p in drops]}")
        print(f"  canonical: {rel_canon} ({canon_eid})")

        # union aliases, sources, embedding_refs
        merged_aliases   = union_list(canon_fm.get("aliases"))
        merged_sources   = union_list(canon_fm.get("sources"))
        merged_embed     = union_list(canon_fm.get("embedding_refs"))
        merged_relations = list(canon_fm.get("relations") or [])
        max_conf = float(canon_fm.get("confidence", 1.0) or 1.0)

        for drop_path in drops:
            drop_fm, _drop_body = entries[drop_path]
            drop_eid = drop_fm.get("entity_id", "")
            drop_name = drop_fm.get("name", "")
            print(f"  drop: {drop_path.relative_to(ROOT)} ({drop_eid})")

            # aliases: include the drop's name as a surface form
            merged_aliases = union_list(
                merged_aliases, [drop_name], drop_fm.get("aliases"),
            )
            merged_sources = union_list(
                merged_sources, drop_fm.get("sources"),
            )
            merged_embed = union_list(
                merged_embed, drop_fm.get("embedding_refs"),
            )
            try:
                max_conf = max(max_conf, float(drop_fm.get("confidence", 0)))
            except (TypeError, ValueError):
                pass

            # relations: prepend drop's relations (dedup later)
            for r in drop_fm.get("relations") or []:
                if isinstance(r, dict):
                    merged_relations.append(dict(r))

            # attributes: fill canonical gaps from drop
            canon_attrs = canon_fm.get("attributes") or {}
            drop_attrs  = drop_fm.get("attributes") or {}
            if isinstance(canon_attrs, dict) and isinstance(drop_attrs, dict):
                for k, v in drop_attrs.items():
                    canon_attrs.setdefault(k, v)
                canon_fm["attributes"] = canon_attrs

        # rewrite drop target_ids on the canonical's own relations too
        for r in merged_relations:
            if isinstance(r, dict):
                tid = r.get("target_id", "")
                if tid in drop_eid_to_canonical_eid:
                    r["target_id"] = drop_eid_to_canonical_eid[tid]

        merged_relations = dedup_relations(merged_relations,
                                           drop_target=canon_eid)

        canon_fm["aliases"]        = merged_aliases
        canon_fm["sources"]        = merged_sources
        canon_fm["embedding_refs"] = merged_embed
        canon_fm["relations"]      = merged_relations
        canon_fm["confidence"]     = max_conf
        canon_fm["updated_at"]     = datetime.now(timezone.utc).isoformat()
        entries[canonical_path] = (canon_fm, canon_body)

        added = [r for r in merged_relations
                 if r not in (canon_fm.get("relations") or [])]
        print(f"    → relations: {len(merged_relations)}, "
              f"aliases: {len(merged_aliases)}, sources: {len(merged_sources)}")

    # Phase 4 — rewrite incoming target_ids on every other entity --------
    drop_paths_set = {dp for _, drops in plan for dp in drops}
    rewritten_count = 0
    rewritten_paths: list[Path] = []
    for path, (fm, body) in entries.items():
        if path in drop_paths_set:
            continue   # going to be deleted — don't bother
        if path in {cp for cp, _ in plan}:
            continue   # already rewritten in Phase 3
        rels = fm.get("relations") or []
        if not rels:
            continue
        changed = False
        new_rels: list = []
        for r in rels:
            if not isinstance(r, dict):
                new_rels.append(r)
                continue
            tid = r.get("target_id", "")
            if tid in drop_eid_to_canonical_eid:
                r = dict(r)
                r["target_id"] = drop_eid_to_canonical_eid[tid]
                changed = True
            new_rels.append(r)
        if changed:
            fm["relations"] = dedup_relations(new_rels,
                                              drop_target=fm.get("entity_id"))
            entries[path] = (fm, body)
            rewritten_count += 1
            rewritten_paths.append(path)

    if rewritten_paths:
        print(f"\nIncoming rewrites ({len(rewritten_paths)} entities):")
        for p in sorted(rewritten_paths):
            print(f"  - {p.relative_to(ROOT)}")

    # Phase 5 — apply ----------------------------------------------------
    summary_groups = len(plan)
    summary_drops  = sum(len(d) for _, d in plan)
    print("\n--- summary ---")
    print(f"groups merged:     {summary_groups}")
    print(f"entities dropped:  {summary_drops}")
    print(f"entities rewritten (incoming): {rewritten_count}")
    if skipped:
        print(f"groups skipped (conflict): {len(skipped)} → {skipped}")
    print("ChromaDB:          no action needed — chunk metadata does "
          "not carry entity_id; entity resolution is .md-driven at "
          "query time.")

    if not args.apply:
        print("\nRe-run with --apply to write changes.")
        return 0

    # backup
    if not args.no_backup:
        backup_path = make_backup()
        print(f"\n[BACKUP] {backup_path.relative_to(ROOT)} "
              f"({backup_path.stat().st_size} bytes)")
    else:
        print("\n[BACKUP] skipped (--no-backup)")

    # write canonicals + rewritten entries
    for path, (fm, body) in entries.items():
        if path in drop_paths_set:
            continue
        write_frontmatter(path, fm, body)

    # delete drops
    for dp in drop_paths_set:
        dp.unlink()
        print(f"  - deleted: {dp.relative_to(ROOT)}")

    print(f"\n[APPLY] {summary_drops} files deleted, "
          f"{summary_groups + rewritten_count} files rewritten.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
