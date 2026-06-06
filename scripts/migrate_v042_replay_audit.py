"""v0.4.2 PR-T5.A — audit_log schema migration (T5 replay audit columns).

v0.4.2 T5 design memo §3 PR-T5.A scope. Adds two columns to the
``audit_log`` SQLite table so lifecycle mutation events can be
captured for the audit-only replay invariant (memo §2):

  * ``event_type`` (TEXT, nullable)    — one of
    :data:`core.lifecycle.replay_audit.LIFECYCLE_EVENT_TYPES`,
    or NULL on existing reasoning rows.
  * ``event_payload`` (TEXT, nullable) — JSON-encoded mutation
    payload (edge ids, validity, mutation_type, …).

Pre-existing rows (reasoning trace, security, etc.) keep both new
columns NULL — they remain readable by the existing replay
(``test_replay_trace.py`` §5.7.2). New lifecycle rows use the
columns; the read-side primitive (PR-T5.B) routes by
``event_type IS NOT NULL`` + :func:`is_lifecycle_event`.

Properties (every one pinned by
``tests/test_migrate_v042_replay_audit.py``):

* **Idempotent.** Running ``--apply`` twice is a no-op after the
  first run. ``ALTER TABLE … ADD COLUMN`` is wrapped in an
  introspection check (``PRAGMA table_info``) so a re-run does
  not raise.
* **v0.4.1-equivalent behavior.** Existing reasoning / security
  rows are byte-identical. Existing replay
  (``tests/test_replay_trace.py``) keeps reading the historic
  columns only.
* **Snapshot first.** ``--apply`` defaults to copying the audit DB
  to ``<db>.pre-v042-migration`` so the operator has a one-step
  rollback path. ``--no-snapshot`` skips when the operator has
  already taken one.

Operator workflow::

    # 1. Dry-run (default) — report which columns are missing
    python scripts/migrate_v042_replay_audit.py --db audit.db

    # 2. Apply with snapshot (creates audit.db.pre-v042-migration)
    python scripts/migrate_v042_replay_audit.py --db audit.db --apply

    # 3. Verify (re-introspect — should report no missing columns)
    python scripts/migrate_v042_replay_audit.py --db audit.db --verify

Design memo: ``docs/design/v0.4.2-t5-replayable-audit-graph.md`` §3.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console  # noqa: E402
    ensure_utf8_console()
except Exception:
    pass


# Columns the migration adds. (column_name, sql_type) tuples — kept
# small so a future T5.A.b can extend the list without rewriting the
# add/verify loops.
NEW_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("event_type",    "TEXT"),
    ("event_payload", "TEXT"),
)


def _existing_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Return the column names already present on ``table``.

    Uses ``PRAGMA table_info`` so the introspection works on any
    SQLite version and does not require write access.
    """
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
    return [r[1] for r in rows]


def _missing_columns(conn: sqlite3.Connection) -> List[Tuple[str, str]]:
    existing = set(_existing_columns(conn, "audit_log"))
    return [(name, sql_type) for name, sql_type in NEW_COLUMNS
            if name not in existing]


def _snapshot(db_path: Path) -> Path:
    """Copy the DB file to ``<db>.pre-v042-migration``.

    Returns the snapshot path. Raises ``FileExistsError`` if a
    snapshot already exists — operator must ``--no-snapshot`` or
    rename the existing one explicitly.
    """
    snap = db_path.with_name(db_path.name + ".pre-v042-migration")
    if snap.exists():
        raise FileExistsError(
            f"Snapshot already exists at {snap}. Pass --no-snapshot to skip "
            "or rename it before re-running --apply."
        )
    shutil.copy2(db_path, snap)
    return snap


def migrate(
    db_path: Path,
    *,
    apply: bool = False,
    snapshot: bool = True,
    verify: bool = False,
) -> int:
    """Run the migration. Returns 0 on success, non-zero on failure
    (for CLI exit codes).

    Modes:
      * ``apply=False, verify=False`` (default): dry-run — report
        missing columns, no write.
      * ``apply=True``: add missing columns. Snapshots first unless
        ``snapshot=False``.
      * ``verify=True``: re-introspect and exit non-zero if any
        column is still missing.
    """
    if not db_path.exists():
        print(f"[T5.A migrate] FATAL: db not found: {db_path}")
        return 2

    conn = sqlite3.connect(str(db_path))
    try:
        existing = _existing_columns(conn, "audit_log")
        if "id" not in existing:
            print("[T5.A migrate] FATAL: audit_log table missing — "
                  "this DB has no v0.3+ audit schema.")
            return 2

        missing = _missing_columns(conn)
        if verify:
            if missing:
                print(f"[T5.A migrate] VERIFY FAIL: missing columns: "
                      f"{[name for name, _ in missing]}")
                return 1
            print("[T5.A migrate] VERIFY OK: every T5 column is present.")
            return 0

        if not missing:
            print("[T5.A migrate] No-op: every T5 column is already present.")
            return 0

        if not apply:
            print(f"[T5.A migrate] DRY-RUN: would add columns: "
                  f"{[(name, sql_type) for name, sql_type in missing]}")
            print("[T5.A migrate]   Re-run with --apply to perform the migration.")
            return 0

        if snapshot:
            snap = _snapshot(db_path)
            print(f"[T5.A migrate] Snapshot: {snap}")
        else:
            print("[T5.A migrate] Snapshot: skipped (--no-snapshot)")

        for name, sql_type in missing:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {name} {sql_type}")
            print(f"[T5.A migrate] Added column: {name} {sql_type}")
        conn.commit()

        # Post-write verification — re-introspect.
        post = set(_existing_columns(conn, "audit_log"))
        for name, _ in NEW_COLUMNS:
            if name not in post:
                print(f"[T5.A migrate] FATAL: column {name} did not land")
                return 2
        print("[T5.A migrate] APPLY OK")
        return 0
    finally:
        conn.close()


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="v0.4.2 PR-T5.A: add event_type + event_payload "
                    "columns to audit_log (idempotent, snapshots first)."
    )
    ap.add_argument("--db", required=True,
                    help="Path to the audit_log SQLite database.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="Perform the migration. Snapshots first by default.")
    mode.add_argument("--verify", action="store_true",
                      help="Re-introspect and exit non-zero if columns are "
                           "missing. No write.")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="Skip the .pre-v042-migration snapshot. Use only "
                         "when an external backup is already in place.")
    args = ap.parse_args(argv)

    return migrate(
        Path(args.db),
        apply=args.apply,
        snapshot=not args.no_snapshot,
        verify=args.verify,
    )


if __name__ == "__main__":
    sys.exit(main())
