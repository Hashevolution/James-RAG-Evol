"""v0.4 Sprint 5 PR-T1.A — Layer 4 schema migration (T1 + T7 fields).

Sprint 5 entry memo (`docs/handovers/v0.4.0-sprint5-layer4-first-bundle-entry.md`)
§6 schema migration plan. Locked at §12.1: separate prep-PR
(`core/lifecycle/schema.py` lands at PR-0) **before** this migration
script so the validators / defaults helpers are already on `main`
when this script runs.

The script back-fills every wiki entity's frontmatter with the v0.4
T1 + T7 fields at v0.3-equivalent safe defaults:

  Source-level (T1):
    ``valid_from``  → None  (no temporal start constraint)
    ``valid_until`` → None  (no temporal end / indefinite validity)

  Edge-level (T1 + T7):
    ``validity``       → ``{"from": None, "to": None}``  (indefinite)
    ``status``         → ``{"active": True,
                            "superseded_by": None,
                            "superseded_at": None}``
    ``mutation_type``  → ``"active"``

Properties (every one pinned by `tests/test_migrate_v04_lifecycle.py`):

- **Idempotent.** Running ``--apply`` twice leaves the wiki
  byte-identical after the first run. The `apply_v04_*_defaults`
  helpers from PR-0 use `setdefault` semantics, so re-running on
  already-migrated entities is a no-op.
- **v0.3-equivalent behaviour.** Every default is the semantic
  identity of "no temporal constraint" — existing callers that
  read `confidence` / `sources` / `relations` see no change at the
  v0.3 read path.
- **Atomic per-file write.** Each entity file is rewritten via
  tempfile + `os.replace` to avoid half-written frontmatter on a
  crash. Same pattern as PR #459 (Phase A migration).
- **Snapshot.** Before any write, the script copies the wiki tree
  to ``wiki.pre-v04-migration/`` for rollback. Skippable with
  ``--no-snapshot`` (CI / already-backed-up cases).
- **Validation pass.** After writing each file, the migrated
  frontmatter is run through `validate_source_v04_fields` +
  `validate_edge_v04_fields` (PR-0). Validation failures halt the
  migration with an explicit row count so the operator can
  investigate before the wiki diverges.

Modes:

  ``--dry-run`` (default)   inspect only; no writes; print summary
  ``--apply``               write back; create snapshot first
  ``--verify``              every file has v0.4 fields + validates clean;
                            no writes; exit 0 if fully migrated
  ``--no-snapshot``         skip the snapshot step (use only if you
                            already have a backup)
  ``--root <path>``         wiki root (default: ``wiki``)
  ``--force``               overwrite existing snapshot directory

Operator workflow (entry memo §9):

  python scripts/migrate_v04_lifecycle.py                # dry-run
  python scripts/migrate_v04_lifecycle.py --apply        # write back
  python scripts/migrate_v04_lifecycle.py --verify       # confirm

Rollback (snapshot ↔ live):

  rmdir /s /q wiki                    # PowerShell: remove live tree
  rename wiki.pre-v04-migration wiki  # restore snapshot
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

# Project root on sys.path so `core.*` import works when the script
# is invoked from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows cp949 console crashes on em-dash in --help / log lines.
# Same helper Phase A migration + bench wrapper use.
try:
    from utils.console import ensure_utf8_console  # noqa: E402
    ensure_utf8_console()
except Exception:
    pass

from core.lifecycle.schema import (  # noqa: E402
    apply_v04_edge_defaults,
    apply_v04_source_defaults,
    validate_edge_v04_fields,
    validate_source_v04_fields,
)


DEFAULT_WIKI_ROOT = Path("wiki")
SNAPSHOT_SUFFIX = "pre-v04-migration"


# ───────────────────────────────────────────────────────────────
# Snapshot
# ───────────────────────────────────────────────────────────────


def snapshot_wiki(wiki_root: Path, force: bool = False) -> Path:
    """``wiki/`` → ``wiki.pre-v04-migration/`` mirror copy for rollback.

    Returns the snapshot path. Raises FileExistsError if the snapshot
    already exists and ``force`` is False (operator may have prior
    rollback state worth preserving).
    """
    snap = wiki_root.with_name(f"{wiki_root.name}.{SNAPSHOT_SUFFIX}")
    if snap.exists():
        if not force:
            raise FileExistsError(
                f"snapshot already exists: {snap}\n"
                f"  -> pass --force to overwrite, or remove it manually\n"
                f"     (rollback path would be lost on overwrite)"
            )
        shutil.rmtree(snap)
    print(f"[V04_MIGRATE] snapshot {wiki_root} -> {snap}")
    shutil.copytree(wiki_root, snap)
    return snap


# ───────────────────────────────────────────────────────────────
# Frontmatter parse / serialize (matches Phase A pattern)
# ───────────────────────────────────────────────────────────────


def _split_frontmatter(text: str) -> tuple[dict | None, str]:
    """Parse `--- ... ---` block. Returns (frontmatter_dict, body).
    Returns (None, original_text) when no parseable frontmatter found.
    """
    if not text.startswith("---"):
        return None, text
    end = text.find("---", 3)
    if end < 0:
        return None, text
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except Exception:
        return None, text
    body_tail = text[end + 3:]
    return fm, body_tail


def _serialize_frontmatter(fm: dict, body_tail: str) -> str:
    return (
        "---\n"
        + yaml.dump(
            fm,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=True,
        )
        + "---"
        + body_tail
    )


# ───────────────────────────────────────────────────────────────
# Per-file migration
# ───────────────────────────────────────────────────────────────


def _migrate_relation(rel: dict) -> tuple[dict, bool]:
    """Apply v0.4 defaults to one relation dict + its embedded sources.

    Returns (new_rel_dict, changed_flag).
    """
    changed = False

    # 1. Edge-level (T1 + T7) defaults
    migrated_edge = apply_v04_edge_defaults(rel)
    if migrated_edge != rel:
        changed = True

    # 2. Source-level (T1) defaults on every embedded source
    sources = migrated_edge.get("sources")
    if isinstance(sources, list):
        new_sources = []
        sources_changed = False
        for src in sources:
            if not isinstance(src, dict):
                new_sources.append(src)
                continue
            migrated_src = apply_v04_source_defaults(src)
            if migrated_src != src:
                sources_changed = True
            new_sources.append(migrated_src)
        if sources_changed:
            migrated_edge["sources"] = new_sources
            changed = True

    return migrated_edge, changed


def migrate_entity_file(path: Path) -> dict:
    """Migrate a single entity ``.md`` file. Returns stats dict.

    Idempotent. Files with no `relations` list are no-ops. Files with
    a parseable frontmatter and a relations list get every relation
    (and every source under each relation) defaulted to v0.4 shape.

    Validation pass runs after the defaults application — every
    migrated source + edge must pass the PR-0 validators. If
    validation fails, the file is NOT written; the error is recorded
    in stats so the operator can inspect.
    """
    stats = {
        "scanned": 1,
        "had_no_relations": 0,
        "mutated": 0,
        "relations_migrated": 0,
        "sources_migrated": 0,
        "validation_failed": 0,
        "errors": 0,
    }
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[V04_MIGRATE] read fail {path}: {e}")
        stats["errors"] = 1
        return stats

    fm, body_tail = _split_frontmatter(text)
    if fm is None:
        return stats

    relations = fm.get("relations")
    if not isinstance(relations, list) or not relations:
        stats["had_no_relations"] = 1
        return stats

    file_changed = False
    new_relations = []
    for rel in relations:
        if not isinstance(rel, dict):
            new_relations.append(rel)
            continue
        new_rel, rel_changed = _migrate_relation(rel)
        if rel_changed:
            stats["relations_migrated"] += 1
            file_changed = True
            # Count sources migrated this round
            old_sources = rel.get("sources", [])
            if isinstance(old_sources, list):
                for src in old_sources:
                    if isinstance(src, dict) and (
                        "valid_from" not in src
                        or "valid_until" not in src
                    ):
                        stats["sources_migrated"] += 1

        # Validation pass — both layers
        try:
            validate_edge_v04_fields(new_rel)
            for src in new_rel.get("sources", []) or []:
                if isinstance(src, dict):
                    validate_source_v04_fields(src)
        except ValueError as e:
            print(f"[V04_MIGRATE] validation fail {path}: {e}")
            stats["validation_failed"] = 1
            stats["errors"] = 1
            return stats

        new_relations.append(new_rel)

    if not file_changed:
        return stats

    fm["relations"] = new_relations
    stats["mutated"] = 1
    new_text = _serialize_frontmatter(fm, body_tail)
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception as e:
        print(f"[V04_MIGRATE] write fail {path}: {e}")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        stats["errors"] = 1
        stats["mutated"] = 0
    return stats


# ───────────────────────────────────────────────────────────────
# Wiki-wide walk
# ───────────────────────────────────────────────────────────────


def migrate_wiki(
    wiki_root: Path,
    *,
    dry_run: bool = False,
    verify: bool = False,
) -> dict:
    """Walk ``wiki_root/entity/**/*.md`` and migrate each file.

    Three modes:

      - ``verify=True``: no writes; every file must already have v0.4
        fields + validate clean. Stats include ``verify_failed`` count.
      - ``dry_run=True``: no writes; report what *would* change.
      - else: write back with atomic per-file rewrite.
    """
    totals: dict[str, Any] = {
        "scanned": 0,
        "had_no_relations": 0,
        "mutated": 0,
        "relations_migrated": 0,
        "sources_migrated": 0,
        "validation_failed": 0,
        "verify_failed": 0,
        "errors": 0,
    }
    entity_root = wiki_root / "entity"
    if not entity_root.is_dir():
        print(f"[V04_MIGRATE] no entity root: {entity_root}")
        return totals

    md_files = sorted(entity_root.rglob("*.md"))
    mode = "VERIFY" if verify else ("DRY-RUN" if dry_run else "APPLY")
    print(
        f"[V04_MIGRATE] mode={mode}: {len(md_files)} entity files "
        f"under {entity_root}"
    )

    if verify:
        for path in md_files:
            try:
                fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[V04_MIGRATE] verify read fail {path}: {e}")
                totals["errors"] += 1
                continue
            totals["scanned"] += 1
            if fm is None:
                continue
            relations = fm.get("relations")
            if not isinstance(relations, list):
                continue
            for rel in relations:
                if not isinstance(rel, dict):
                    continue
                missing = [
                    k for k in (
                        "validity", "status", "mutation_type",
                    ) if k not in rel
                ]
                if missing:
                    print(
                        f"[V04_MIGRATE] verify: {path} relation missing "
                        f"{missing}"
                    )
                    totals["verify_failed"] += 1
                    continue
                try:
                    validate_edge_v04_fields(rel)
                    for src in rel.get("sources", []) or []:
                        if isinstance(src, dict):
                            validate_source_v04_fields(src)
                except ValueError as e:
                    print(f"[V04_MIGRATE] verify validate fail {path}: {e}")
                    totals["verify_failed"] += 1
        return totals

    if dry_run:
        for path in md_files:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"[V04_MIGRATE] dry-run read fail {path}: {e}")
                totals["errors"] += 1
                continue
            totals["scanned"] += 1
            fm, _ = _split_frontmatter(text)
            if fm is None:
                continue
            relations = fm.get("relations")
            if not isinstance(relations, list) or not relations:
                totals["had_no_relations"] += 1
                continue
            for rel in relations:
                if not isinstance(rel, dict):
                    continue
                # Count what *would* be added — relations missing any
                # of the three T1+T7 keys
                if any(
                    k not in rel
                    for k in ("validity", "status", "mutation_type")
                ):
                    totals["relations_migrated"] += 1
                for src in rel.get("sources", []) or []:
                    if isinstance(src, dict) and (
                        "valid_from" not in src
                        or "valid_until" not in src
                    ):
                        totals["sources_migrated"] += 1
        totals["mutated"] = (
            totals["relations_migrated"] + totals["sources_migrated"]
        )
        return totals

    # apply
    for path in md_files:
        s = migrate_entity_file(path)
        for k in (
            "scanned", "had_no_relations", "mutated",
            "relations_migrated", "sources_migrated",
            "validation_failed", "errors",
        ):
            totals[k] += s.get(k, 0)
    return totals


# ───────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "v0.4 Sprint 5 PR-T1.A — back-fill T1 + T7 fields on "
            "every wiki entity. Dry-run by default."
        ),
    )
    ap.add_argument("--root", type=Path, default=DEFAULT_WIKI_ROOT)
    ap.add_argument(
        "--apply", action="store_true",
        help="actually write back; otherwise dry-run is the default",
    )
    ap.add_argument(
        "--verify", action="store_true",
        help=(
            "no writes; every file must already have v0.4 fields + "
            "validate clean. Use after --apply to confirm."
        ),
    )
    ap.add_argument(
        "--no-snapshot", action="store_true",
        help="skip the wiki.pre-v04-migration snapshot (use only if "
             "you already have a backup)",
    )
    ap.add_argument(
        "--force", action="store_true",
        help="overwrite existing wiki.pre-v04-migration directory",
    )
    args = ap.parse_args()

    if args.apply and args.verify:
        print("error: --apply and --verify are mutually exclusive")
        return 2

    wiki_root = args.root.resolve()
    if not wiki_root.is_dir():
        print(f"error: wiki root not found: {wiki_root}")
        return 2

    # Snapshot pass (only on --apply, before any writes)
    if args.apply and not args.no_snapshot:
        try:
            snapshot_wiki(wiki_root, force=args.force)
        except FileExistsError as e:
            print(f"error: {e}")
            return 2

    totals = migrate_wiki(
        wiki_root,
        dry_run=not (args.apply or args.verify),
        verify=args.verify,
    )

    print("\n[V04_MIGRATE] summary:")
    for k, v in totals.items():
        print(f"  {k:30s} {v}")

    # Exit codes
    if totals.get("errors", 0) > 0:
        print("\n[V04_MIGRATE] FAILED — see error log above")
        return 1
    if args.verify and totals.get("verify_failed", 0) > 0:
        print("\n[V04_MIGRATE] VERIFY FAILED — run --apply first")
        return 1
    if args.apply and totals.get("mutated", 0) == 0:
        print("\n[V04_MIGRATE] nothing to migrate (already at v0.4 shape)")
    elif args.apply:
        print(
            f"\n[V04_MIGRATE] OK — migrated {totals['mutated']} files. "
            f"Verify: python scripts/migrate_v04_lifecycle.py --verify"
        )
    elif args.verify:
        print("\n[V04_MIGRATE] VERIFY OK — wiki fully at v0.4 shape")
    else:
        print(
            f"\n[V04_MIGRATE] DRY-RUN OK — "
            f"{totals['relations_migrated']} relations + "
            f"{totals['sources_migrated']} sources would be migrated. "
            f"Run again with --apply to write."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
