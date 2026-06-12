"""v0.4.2 PR-T5.A — event taxonomy + emit + migration contract tests.

Pins the write-side contract for the T5 audit-only replay invariant
(``docs/design/v0.4.2-t5-replayable-audit-graph.md`` §2 + §4 I1):

  1. ``LIFECYCLE_EVENT_TYPES`` covers every existing lifecycle
     mutation path (T1 / T2 / T2.D / T6 / T7 + migration backfill).
  2. ``is_lifecycle_event`` is exact-match (no prefix lookalikes).
  3. ``emit_lifecycle_event`` round-trips on a real SQLite (post-
     migration schema), never raises on bad input, and refuses to
     write non-lifecycle event types.
  4. The migration script is idempotent, snapshots once, and verify
     mode exits non-zero against an un-migrated DB.

Tests pin the design memo's Decision LOCKs (§7):
  LOCK 1 — event_payload is a JSON string column on audit_log
  LOCK 2 — emit is synchronous in-transaction
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Pre-migration audit_log schema (v0.4.1) — matches
# ``tests/test_replay_trace.py``'s _AUDIT_SCHEMA so we exercise the
# real upgrade path.
_PRE_MIGRATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,
    user_role    TEXT    NOT NULL,
    endpoint     TEXT    NOT NULL,
    query        TEXT,
    answer       TEXT,
    graph_paths  TEXT,
    blocked      INTEGER DEFAULT 0,
    security_event TEXT,
    elapsed_sec  REAL,
    ip_address   TEXT
)
"""


def _fresh_pre_migration_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    conn = sqlite3.connect(f.name)
    conn.execute(_PRE_MIGRATION_SCHEMA)
    conn.commit()
    conn.close()
    return f.name


def _fresh_post_migration_db() -> str:
    """A DB with the T5.A columns already applied — used by the
    emit / round-trip tests so they don't depend on the migration
    script's correctness."""
    path = _fresh_pre_migration_db()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE audit_log ADD COLUMN event_type TEXT")
    conn.execute("ALTER TABLE audit_log ADD COLUMN event_payload TEXT")
    conn.commit()
    conn.close()
    return path


class EventTypeTaxonomyTests(unittest.TestCase):
    """LIFECYCLE_EVENT_TYPES covers every mutation path the design memo
    enumerates, exposes a stable name set, and rejects lookalikes."""

    def test_taxonomy_covers_every_design_memo_mutation(self):
        from core.lifecycle import replay_audit as ra
        # Memo §3 table: T7 supersede (2), T6 cascade (1), T1 expiration (1),
        # T2 contradiction (1), T2.D ingest (1), migration backfill (1) = 7.
        # v0.6 G8.c (B.3 §4.4): + ontology pack mounted (1) + unmounted (1) = 9.
        self.assertEqual(len(ra.LIFECYCLE_EVENT_TYPES), 9)
        # Each entry must be a string starting with 'lifecycle.'.
        for evt in ra.LIFECYCLE_EVENT_TYPES:
            self.assertIsInstance(evt, str)
            self.assertTrue(evt.startswith("lifecycle."),
                            f"non-lifecycle name in taxonomy: {evt!r}")

    def test_taxonomy_constants_match_strings(self):
        from core.lifecycle import replay_audit as ra
        # Each EVT_* constant must equal its design-memo name.
        self.assertEqual(ra.EVT_SUPERSEDE_EDGE_CREATED,
                         "lifecycle.supersede.edge_created")
        self.assertEqual(ra.EVT_SUPERSEDE_CHAIN_EXTENDED,
                         "lifecycle.supersede.chain_extended")
        self.assertEqual(ra.EVT_CASCADE_INVALIDATE,
                         "lifecycle.cascade.invalidate")
        self.assertEqual(ra.EVT_T1_EXPIRATION_CASCADE,
                         "lifecycle.t1.expiration_cascade")
        self.assertEqual(ra.EVT_T2_DISPATCH_CONTRADICTION,
                         "lifecycle.t2.dispatch_contradiction")
        self.assertEqual(ra.EVT_T2D_INGEST_DISPATCH,
                         "lifecycle.t2d.ingest_dispatch")
        self.assertEqual(ra.EVT_BACKFILL_SNAPSHOT,
                         "lifecycle.backfill.snapshot")

    def test_taxonomy_is_frozen_tuple(self):
        from core.lifecycle import replay_audit as ra
        self.assertIsInstance(ra.LIFECYCLE_EVENT_TYPES, tuple)
        # Tuple of distinct strings (no duplicate aliases).
        self.assertEqual(len(set(ra.LIFECYCLE_EVENT_TYPES)),
                         len(ra.LIFECYCLE_EVENT_TYPES))


class IsLifecycleEventTests(unittest.TestCase):
    """is_lifecycle_event is exact-match — a typo or prefix-only
    lookalike must NOT slip through."""

    def test_known_event_types_return_true(self):
        from core.lifecycle import replay_audit as ra
        for evt in ra.LIFECYCLE_EVENT_TYPES:
            self.assertTrue(ra.is_lifecycle_event(evt),
                            f"registered type rejected: {evt!r}")

    def test_typo_in_event_type_returns_false(self):
        from core.lifecycle.replay_audit import is_lifecycle_event
        # Typo / lookalike — must not silently slip in.
        for bad in (
            "lifecycle.cascadx.invalidate",
            "lifecycle.supersede.edge_create",   # missing trailing 'd'
            "lifecycle.t1.expiration",            # missing _cascade
            "Lifecycle.cascade.invalidate",       # capital L
            "lifecycle..cascade.invalidate",      # double dot
        ):
            self.assertFalse(is_lifecycle_event(bad),
                             f"lookalike accepted: {bad!r}")

    def test_non_lifecycle_endpoints_return_false(self):
        from core.lifecycle.replay_audit import is_lifecycle_event
        # Reasoning trace + security events live in the same table
        # but must not be confused with lifecycle events.
        for non in (
            "reasoning.synth.rag",
            "reasoning.synth.web_fallback",
            "reasoning.verify.security",
            "tool:wiki:write",
            "",
            None,
            0,
            object(),
        ):
            self.assertFalse(is_lifecycle_event(non))


class EmitLifecycleEventTests(unittest.TestCase):
    """emit_lifecycle_event writes a row with the expected fields and
    never raises on bad input (matches audit_bridge contract)."""

    def setUp(self):
        self.db = _fresh_post_migration_db()

    def tearDown(self):
        try:
            os.unlink(self.db)
        except OSError:
            pass

    def test_emit_round_trips_event_type_and_payload(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        payload = {
            "head_id":      "edge-abc-001",
            "new_edge_id":  "edge-abc-002",
            "supersede_ts": "2026-06-06T12:00:00",
            "validity":     {"from": "2026-06-06T12:00:00", "to": None},
        }
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED, payload, db_path=self.db,
        )
        self.assertTrue(ok)

        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute(
                "SELECT event_type, event_payload, endpoint, user_role "
                "FROM audit_log"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        evt, payload_json, endpoint, role = rows[0]
        self.assertEqual(evt, EVT_SUPERSEDE_EDGE_CREATED)
        # LOCK 1: payload is JSON string.
        self.assertEqual(json.loads(payload_json), payload)
        # endpoint mirrors event_type so legacy /admin/audit/list shows it.
        self.assertEqual(endpoint, EVT_SUPERSEDE_EDGE_CREATED)
        # default user_role is 'system'.
        self.assertEqual(role, "system")

    def test_emit_accepts_korean_in_payload_without_escape(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_CASCADE_INVALIDATE,
        )
        payload = {"reason": "출처 모두 빈 상태에서 도출된 사실 → 무효화"}
        ok = emit_lifecycle_event(
            EVT_CASCADE_INVALIDATE, payload, db_path=self.db,
        )
        self.assertTrue(ok)
        conn = sqlite3.connect(self.db)
        try:
            (raw,) = conn.execute(
                "SELECT event_payload FROM audit_log"
            ).fetchone()
        finally:
            conn.close()
        # ensure_ascii=False — Korean stays readable, no \uXXXX clutter.
        self.assertIn("출처", raw)

    def test_emit_rejects_unknown_event_type(self):
        from core.lifecycle.replay_audit import emit_lifecycle_event
        ok = emit_lifecycle_event(
            "lifecycle.cascadx.invalidate",
            {"x": 1},
            db_path=self.db,
        )
        self.assertFalse(ok)
        conn = sqlite3.connect(self.db)
        try:
            (n,) = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
        finally:
            conn.close()
        self.assertEqual(n, 0,
                         "unknown event type must not produce a row")

    def test_emit_rejects_non_dict_payload(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_CASCADE_INVALIDATE,
        )
        for bad in ("string", 123, ["list"], None):
            ok = emit_lifecycle_event(
                EVT_CASCADE_INVALIDATE, bad, db_path=self.db,
            )
            self.assertFalse(ok, f"non-dict payload accepted: {bad!r}")

    def test_emit_never_raises_on_bad_db_path(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_CASCADE_INVALIDATE,
        )
        # Unwritable path — must return False, not raise. Matches
        # audit_bridge.mirror_to_audit_db contract.
        ok = emit_lifecycle_event(
            EVT_CASCADE_INVALIDATE,
            {"x": 1},
            db_path="/nonexistent/dir/does/not/exist/audit.db",
        )
        self.assertFalse(ok)

    def test_emit_writes_to_pre_migration_db_returns_false(self):
        """A DB without the event_type column must return False
        rather than raising — operators sometimes start the engine
        before running the migration."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_CASCADE_INVALIDATE,
        )
        pre = _fresh_pre_migration_db()
        try:
            ok = emit_lifecycle_event(
                EVT_CASCADE_INVALIDATE, {"x": 1}, db_path=pre,
            )
            self.assertFalse(ok)
        finally:
            try:
                os.unlink(pre)
            except OSError:
                pass

    def test_emit_uses_explicit_timestamp_when_provided(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_T1_EXPIRATION_CASCADE,
        )
        ts = "2026-06-06T15:30:00"
        ok = emit_lifecycle_event(
            EVT_T1_EXPIRATION_CASCADE, {"edge_id": "e1"},
            timestamp=ts, db_path=self.db,
        )
        self.assertTrue(ok)
        conn = sqlite3.connect(self.db)
        try:
            (got,) = conn.execute(
                "SELECT timestamp FROM audit_log"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(got, ts)


class MigrationScriptTests(unittest.TestCase):
    """migrate_v042_replay_audit is idempotent, snapshots once, and
    verify mode exits non-zero on a pre-migration DB."""

    def setUp(self):
        self.db = _fresh_pre_migration_db()
        # Path for the snapshot the script creates.
        self.snap = self.db + ".pre-v042-migration"

    def tearDown(self):
        for p in (self.db, self.snap):
            try:
                os.unlink(p)
            except OSError:
                pass

    def _run(self, *args):
        from scripts import migrate_v042_replay_audit as m
        return m.main(["--db", self.db, *args])

    def test_dry_run_reports_missing_columns_no_write(self):
        rc = self._run()
        self.assertEqual(rc, 0)
        # DB column list unchanged.
        conn = sqlite3.connect(self.db)
        try:
            cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(audit_log)"
            ).fetchall()]
        finally:
            conn.close()
        self.assertNotIn("event_type", cols)
        self.assertNotIn("event_payload", cols)

    def test_apply_adds_columns_and_snapshots(self):
        rc = self._run("--apply")
        self.assertEqual(rc, 0)
        # Both columns landed.
        conn = sqlite3.connect(self.db)
        try:
            cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(audit_log)"
            ).fetchall()]
        finally:
            conn.close()
        self.assertIn("event_type", cols)
        self.assertIn("event_payload", cols)
        # Snapshot exists.
        self.assertTrue(os.path.exists(self.snap))

    def test_apply_idempotent_after_first_run(self):
        rc1 = self._run("--apply")
        self.assertEqual(rc1, 0)
        # Pre-existing snapshot must block the second snapshot attempt
        # — operator runs --no-snapshot to re-apply.
        rc2 = self._run("--apply", "--no-snapshot")
        self.assertEqual(rc2, 0)

    def test_verify_fails_on_pre_migration_db(self):
        rc = self._run("--verify")
        self.assertEqual(rc, 1)

    def test_verify_succeeds_after_apply(self):
        self.assertEqual(self._run("--apply"), 0)
        self.assertEqual(self._run("--verify"), 0)


class PreMigrationCompatibilityTests(unittest.TestCase):
    """Existing reasoning rows (no event_type) keep working — replay
    trace at §5.7.2 stays green after the migration."""

    def test_existing_rows_keep_null_in_new_columns(self):
        db = _fresh_pre_migration_db()
        try:
            # Insert a v0.4.1-style reasoning row.
            conn = sqlite3.connect(db)
            try:
                conn.execute(
                    "INSERT INTO audit_log "
                    "(timestamp, user_role, endpoint, query, answer) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("2026-06-06T10:00:00", "admin",
                     "reasoning.synth.rag", "Q?", "A."),
                )
                conn.commit()
            finally:
                conn.close()
            # Migrate.
            from scripts import migrate_v042_replay_audit as m
            self.assertEqual(m.main(["--db", db, "--apply"]), 0)
            # The pre-existing row keeps NULL on both new columns.
            conn = sqlite3.connect(db)
            try:
                rows = conn.execute(
                    "SELECT event_type, event_payload FROM audit_log"
                ).fetchall()
            finally:
                conn.close()
            self.assertEqual(rows, [(None, None)])
        finally:
            for p in (db, db + ".pre-v042-migration"):
                try:
                    os.unlink(p)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
