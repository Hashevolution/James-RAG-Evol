"""v0.4.1 PR-T6.A — Layer 4 schema migration (T6 derived_from field).

v0.4.1 entry memo §3 PR-T6.A scope. Adds ``derived_from: []`` to every
relation in every wiki entity. The validator + defaults helpers
land first at ``core/lifecycle/schema.py``
(``apply_t6_edge_defaults`` + ``validate_edge_t6_derived_from``); this
script back-fills the wiki on disk.

Default field value (every newly-migrated relation):

  ``derived_from: []``  (no inferred-fact dependencies — v0.3-equivalent)

Properties (every one pinned by ``tests/test_migrate_v041_lifecycle.py``):

- **Idempotent.** Running ``--apply`` twice leaves the wiki byte-
  identical after the first run. ``apply_t6_edge_defaults`` uses
  ``setdefault`` semantics, so re-running on already-migrated entities
  is a no-op.
- **v0.3-equivalent behavior.** The default ``[]`` says "no derivation
  base" — existing callers that don't yet read ``derived_from`` see
  no behavior change.
- **Atomic per-file write.** ``tempfile.NamedTemporaryFile`` +
  ``os.replace`` so a crash mid-write doesn't half-update a file.
- **Snapshot first.** ``--apply`` defaults to copying the wiki to
  ``wiki.pre-v041-migration/`` so the operator has a one-step
  rollback path. ``--no-snapshot`` skips when the operator has
  already taken one.

Operator workflow::

    # 1. Dry-run (default) — count entities that would change
    python scripts/migrate_v041_lifecycle.py --root wiki

    # 2. Apply with snapshot (creates wiki.pre-v041-migration/)
    python scripts/migrate_v041_lifecycle.py --root wiki --apply

    # 3. Verify (rerun apply path — should be byte-stable)
    python scripts/migrate_v041_lifecycle.py --root wiki --verify
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Tuple

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console  # noqa: E402
    ensure_utf8_console()
except Exception:
    pass

from core.lifecycle.schema import (  # noqa: E402
    apply_t6_edge_defaults,
)


DEFAULT_WIKI_ROOT = Path("wiki")
SNAPSHOT_SUFFIX = "pre-v041-migration"


# ───────────────────────────────────────────────────────────────
# Snapshot
# ───────────────────────────────────────────────────────────────


def snapshot_wiki(wiki_root: Path, force: bool = False) -> Path:
    """``wiki/`` → ``wiki.pre-v041-migration/`` mirror copy for rollback."""
    snap = wiki_root.with_name(f"{wiki_root.name}.{SNAPSHOT_SUFFIX}")
    if snap.exists():
        if not force:
            raise FileExistsError(
                f"snapshot already exists: {snap}\n"
                f"  -> pass --force to overwrite, or remove it manually\n"
                f"     (rollback path would be lost on overwrite)"
            )
        shutil.rmtree(snap)
    print(f"[V041_MIGRATE] snapshot {wiki_root} -> {snap}")
    shutil.copytree(wiki_root, snap)
    return snap


# ───────────────────────────────────────────────────────────────
# Frontmatter parse / serialize (mirrors v04 migration pattern)
# ───────────────────────────────────────────────────────────────


def _split_frontmatter(text: str) -> tuple[dict | None, str]:
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


def _migrate_relation(rel: dict) -> Tuple[dict, bool]:
    """Apply T6 defaults to one relation. Returns (new_rel, changed)."""
    migrated = apply_t6_edge_defaults(rel)
    return migrated, migrated != rel


def migrate_entity_file(path: Path) -> dict:
    """Migrate a single entity .md file in memory. Returns stats dict.

    Stats:
      {"changed": bool, "relations_total": int, "relations_changed": int,
       "new_text": str | None}

    Does NOT write back — the caller decides (dry-run vs apply).
    """
    text = path.read_text(encoding="utf-8")
    fm, body_tail = _split_frontmatter(text)
    if not isinstance(fm, dict):
        return {
            "changed": False,
            "relations_total": 0,
            "relations_changed": 0,
            "new_text": None,
        }
    relations = fm.get("relations") or []
    if not isinstance(relations, list):
        return {
            "changed": False,
            "relations_total": 0,
            "relations_changed": 0,
            "new_text": None,
        }

    new_rels = []
    changed_count = 0
    for rel in relations:
        if not isinstance(rel, dict):
            new_rels.append(rel)
            continue
        migrated, changed = _migrate_relation(rel)
        new_rels.append(migrated)
        if changed:
            changed_count += 1

    if changed_count == 0:
        return {
            "changed": False,
            "relations_total": len(relations),
            "relations_changed": 0,
            "new_text": None,
        }

    fm["relations"] = new_rels
    new_text = _serialize_frontmatter(fm, body_tail)
    return {
        "changed": True,
        "relations_total": len(relations),
        "relations_changed": changed_count,
        "new_text": new_text,
    }


def _write_atomic(path: Path, text: str) -> None:
    """tempfile + os.replace — crash mid-write never half-updates."""
    dirpath = path.parent
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(dirpath),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


# ───────────────────────────────────────────────────────────────
# Top-level walker
# ───────────────────────────────────────────────────────────────


def migrate_wiki(
    wiki_root: Path,
    *,
    apply: bool = False,
    verify: bool = False,
) -> dict:
    """Walk ``wiki_root`` for entity .md files, apply T6 defaults.

    Modes:
      - ``apply=False``: dry-run. Counts changes; no writes.
      - ``apply=True``: write back changed files atomically.
      - ``verify=True``: dry-run, but assert zero changes (idempotency check
        run after ``--apply``).
    """
    entity_root = wiki_root / "entity"
    if not entity_root.exists():
        print(f"[V041_MIGRATE] no entity dir at {entity_root}; nothing to do")
        return {
            "files_scanned": 0,
            "files_changed": 0,
            "relations_changed": 0,
            "verify_violations": 0,
        }

    files_scanned = 0
    files_changed = 0
    relations_changed = 0
    verify_violations = 0

    for path in sorted(entity_root.rglob("*.md")):
        files_scanned += 1
        stats = migrate_entity_file(path)
        if not stats["changed"]:
            continue
        files_changed += 1
        relations_changed += stats["relations_changed"]
        if verify:
            verify_violations += 1
            print(
                f"[V041_MIGRATE][VERIFY-VIOLATION] {path} would change "
                f"({stats['relations_changed']} relations) — re-run --apply"
            )
            continue
        if apply:
            _write_atomic(path, stats["new_text"])

    return {
        "files_scanned":     files_scanned,
        "files_changed":     files_changed,
        "relations_changed": relations_changed,
        "verify_violations": verify_violations,
    }


# ───────────────────────────────────────────────────────────────
# CLI entry
# ───────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description="v0.4.1 PR-T6.A — T6 derived_from migration. "
                    "Default is --dry-run."
    )
    ap.add_argument("--root", type=Path, default=DEFAULT_WIKI_ROOT,
                    help="Wiki root (default: ./wiki).")
    ap.add_argument("--apply", action="store_true",
                    help="Write changes back. Default = dry-run.")
    ap.add_argument("--verify", action="store_true",
                    help="Dry-run + assert zero pending changes "
                         "(idempotency check after --apply).")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="Skip snapshot creation when --apply.")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing snapshot.")
    args = ap.parse_args()

    if args.apply and args.verify:
        print("[V041_MIGRATE] --apply and --verify are mutually exclusive")
        return 2

    if not args.root.exists():
        print(f"[V041_MIGRATE] wiki root not found: {args.root}")
        return 2

    if args.apply and not args.no_snapshot:
        try:
            snapshot_wiki(args.root, force=args.force)
        except FileExistsError as e:
            print(f"[V041_MIGRATE] {e}")
            return 2

    stats = migrate_wiki(args.root, apply=args.apply, verify=args.verify)

    print("[V041_MIGRATE] === summary ===")
    print(f"  files_scanned:     {stats['files_scanned']}")
    print(f"  files_changed:     {stats['files_changed']}")
    print(f"  relations_changed: {stats['relations_changed']}")
    if args.verify:
        print(f"  verify_violations: {stats['verify_violations']}")
        if stats["verify_violations"] > 0:
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
