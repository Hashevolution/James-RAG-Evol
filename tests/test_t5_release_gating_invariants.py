"""v0.4.2 PR-T5.D — release-gating invariants (5).

These are the contract-level tests that must stay green for any
future v0.4.2.x patch to be safely cut. They pin the design memo's
5 invariants (memo §6 Phase E):

  1. test_graph_replay_at_t_matches_event_log
     — replay = event-log fold (I4 weak form, mutation-wiring-free)
  2. test_replay_audit_only_no_db_scan
     — I1 (audit-only): no DB read beyond the audit_log SELECT
  3. test_replay_preserves_supersede_chain
     — I2 (supersede chain): T7 chain order preserved through emit /
       reconstruct round-trip
  4. test_replay_respects_cascade_invalidate
     — I3 (cascade): T6 invalidate cleanly removes ids from edges +
       adds to invalidated_ids
  5. test_reasoning_trace_replay_invariant
     — ARCHITECTURE.md §5.7.2: reasoning-trace replay coexists with
       lifecycle replay in the same audit_log (no interference)

Strong I4 (reconstruct_graph_at against the *live* on-disk wiki)
requires mutation-site wiring (T1/T2/T2.D/T6/T7 → emit_lifecycle_
event), which is out of scope for T5.D — it lands in the v0.4.2.x
wiring follow-up. Until then the contract is the round-trip form
above: every event emit_lifecycle_event writes becomes exactly one
fold step in the snapshot.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def _fresh_post_migration_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    conn = sqlite3.connect(f.name)
    conn.execute(_PRE_MIGRATION_SCHEMA)
    conn.execute("ALTER TABLE audit_log ADD COLUMN event_type TEXT")
    conn.execute("ALTER TABLE audit_log ADD COLUMN event_payload TEXT")
    conn.commit()
    conn.close()
    return f.name


class T5ReleaseGatingInvariants(unittest.TestCase):
    """The 5 invariants the design memo (§6 Phase E) pins for v0.4.2
    closure. Failure on any of these blocks a v0.4.2.x patch
    release."""

    def setUp(self):
        self.db = _fresh_post_migration_db()

    def tearDown(self):
        try:
            os.unlink(self.db)
        except OSError:
            pass

    # ── Invariant 1 (I4 weak form) ───────────────────────────────────
    def test_graph_replay_at_t_matches_event_log(self):
        """For every sequence of emit_lifecycle_event calls, the
        resulting snapshot's event_count equals the number of valid
        events written (each emit → exactly one fold step)."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_CASCADE_INVALIDATE,
            EVT_T1_EXPIRATION_CASCADE,
            EVT_BACKFILL_SNAPSHOT,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at

        # Mix of event types, all should fold.
        events = [
            (EVT_BACKFILL_SNAPSHOT,
             {"edges": {"seed": {"id": "seed", "validity": {}}}}),
            (EVT_SUPERSEDE_EDGE_CREATED,
             {"head_id": "h", "new_edge_id": "e1"}),
            (EVT_SUPERSEDE_EDGE_CREATED,
             {"head_id": "h", "new_edge_id": "e2"}),
            (EVT_CASCADE_INVALIDATE,
             {"invalidated_edges": ["e1"]}),
            (EVT_T1_EXPIRATION_CASCADE,
             {"edge_id": "e2"}),
        ]
        for evt, payload in events:
            self.assertTrue(emit_lifecycle_event(evt, payload,
                                                 db_path=self.db))

        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertEqual(snap.event_count, len(events),
                         "each successful emit must produce exactly one "
                         "fold step")

    # ── Invariant 2 (I1) ─────────────────────────────────────────────
    def test_replay_audit_only_no_db_scan(self):
        """reconstruct_graph_at opens only the audit_log database —
        no wiki file read, no knowledge_tracker DB, no graph-engine
        state access. Monkeypatches sqlite3.connect and asserts every
        connect call targets the audit DB path."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle import replay_graph as rg

        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "e"},
                             db_path=self.db)

        opened_paths = []
        real_connect = sqlite3.connect

        def spy_connect(path, *a, **kw):
            opened_paths.append(path)
            return real_connect(path, *a, **kw)

        saved = rg.sqlite3.connect
        rg.sqlite3.connect = spy_connect
        try:
            rg.reconstruct_graph_at(datetime.now(),
                                     audit_log_path=self.db)
        finally:
            rg.sqlite3.connect = saved

        self.assertTrue(opened_paths,
                        "expected at least one DB open during reconstruct")
        self.assertTrue(all(p == self.db for p in opened_paths),
                        f"reconstruct opened non-audit paths: {opened_paths}")

    # ── Invariant 3 (I2) ─────────────────────────────────────────────
    def test_replay_preserves_supersede_chain(self):
        """T7 supersede chain order is preserved through the emit /
        reconstruct round-trip. Multiple chains do not leak into
        each other."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at

        # Two parallel chains; emit in interleaved order.
        for emit_seq in [
            ("h1", "a"), ("h2", "x"),
            ("h1", "b"), ("h2", "y"),
            ("h1", "c"), ("h2", "z"),
        ]:
            head, eid = emit_seq
            emit_lifecycle_event(
                EVT_SUPERSEDE_EDGE_CREATED,
                {"head_id": head, "new_edge_id": eid},
                db_path=self.db,
            )

        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        # Both chains present, in emission order, no cross-contamination.
        self.assertEqual(snap.supersede_chains["h1"], ["h1", "a", "b", "c"])
        self.assertEqual(snap.supersede_chains["h2"], ["h2", "x", "y", "z"])

    # ── Invariant 4 (I3) ─────────────────────────────────────────────
    def test_replay_respects_cascade_invalidate(self):
        """T6 cascade.invalidate removes ids from snapshot.edges AND
        adds them to snapshot.invalidated_ids — history preserved
        even when state is gone."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_CASCADE_INVALIDATE,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at

        # Two edges, invalidate one.
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "live"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "gone"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_CASCADE_INVALIDATE,
                             {"invalidated_edges": ["gone"],
                              "mutation_type": "invalidated"},
                             db_path=self.db)

        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertIn("live", snap.edges)
        self.assertNotIn("gone", snap.edges,
                         "invalidated edge must not appear in edges")
        self.assertIn("gone", snap.invalidated_ids,
                      "invalidated edge must appear in invalidated_ids")

    # ── Invariant 5 (§5.7.2 trace coexistence) ───────────────────────
    def test_reasoning_trace_replay_invariant(self):
        """Reasoning-trace rows (no event_type) and lifecycle rows
        (event_type IS NOT NULL) coexist in the same audit_log table
        without interference.

        Pre-existing reasoning rows are filtered out by
        reconstruct_graph_at's WHERE clause and never reach the fold;
        lifecycle rows are routed only to the lifecycle fold.
        """
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at

        # Insert a v0.4.1-shape reasoning row (no event_type).
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, user_role, endpoint, query, answer) "
                "VALUES (?, ?, ?, ?, ?)",
                ("2026-06-06T09:00:00", "admin",
                 "reasoning.synth.rag",
                 "왜 X 인가?", "X 이기 때문에."),
            )
            conn.commit()
        finally:
            conn.close()

        # Lifecycle event added on top.
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "e1"},
                             db_path=self.db)

        snap = reconstruct_graph_at(datetime.now(),
                                     audit_log_path=self.db)
        # Snapshot folds only the lifecycle event.
        self.assertEqual(snap.event_count, 1)
        self.assertIn("e1", snap.edges)

        # The reasoning row is still readable by anyone who needs it.
        conn = sqlite3.connect(self.db)
        try:
            (n_reasoning,) = conn.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE endpoint = 'reasoning.synth.rag'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(n_reasoning, 1,
                         "reasoning trace row must be preserved alongside "
                         "lifecycle rows")


if __name__ == "__main__":
    unittest.main()
