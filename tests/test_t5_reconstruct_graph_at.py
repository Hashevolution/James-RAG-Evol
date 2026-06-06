"""v0.4.2 PR-T5.B — reconstruct_graph_at primitive contract tests.

Pins the read-side contract for the T5 audit-only replay invariant
(``docs/design/v0.4.2-t5-replayable-audit-graph.md`` §4 + §6 Phase C).
Each test builds a synthetic audit_log (post-migration schema),
emits lifecycle rows via ``emit_lifecycle_event``, and asserts the
resulting :class:`GraphSnapshot`.

Invariants pinned (memo §4 API I1-I4):

  I1 audit-only  — no DB read beyond audit_log; no wiki / graph engine
                   access during reconstruction
  I2 supersede   — chains in snapshot match the order edges were emitted
  I3 cascade     — invalidate events remove ids from edges + add to
                   invalidated_ids
  I4 replay-eq   — snapshot at t = now is byte-equal to the snapshot
                   produced by reading the audit_log immediately after

These tests do NOT depend on mutation-site wiring (T1/T2/T2.D/T6/T7
→ emit_lifecycle_event) — that lands in T5.A.b or T5.B follow-up.
The wiring-integrated invariants (I4 against the live wiki) land
in PR-T5.D.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

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


class GraphSnapshotShapeTests(unittest.TestCase):
    def test_empty_db_returns_empty_snapshot(self):
        from core.lifecycle.replay_graph import reconstruct_graph_at
        db = _fresh_post_migration_db()
        try:
            snap = reconstruct_graph_at(datetime.now(), audit_log_path=db)
            self.assertEqual(snap.edges, {})
            self.assertEqual(snap.supersede_chains, {})
            self.assertEqual(snap.invalidated_ids, frozenset())
            self.assertEqual(snap.event_count, 0)
        finally:
            os.unlink(db)

    def test_pre_migration_db_returns_empty_snapshot(self):
        """A DB without the new columns must produce the empty
        snapshot — operators sometimes invoke replay before
        migrating."""
        from core.lifecycle.replay_graph import reconstruct_graph_at
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        conn = sqlite3.connect(f.name)
        conn.execute(_PRE_MIGRATION_SCHEMA)
        conn.commit()
        conn.close()
        try:
            snap = reconstruct_graph_at(datetime.now(), audit_log_path=f.name)
            self.assertEqual(snap.event_count, 0)
        finally:
            os.unlink(f.name)

    def test_nonexistent_db_returns_empty_snapshot(self):
        from core.lifecycle.replay_graph import reconstruct_graph_at
        snap = reconstruct_graph_at(
            datetime.now(),
            audit_log_path="/nonexistent/path/audit.db",
        )
        self.assertEqual(snap.event_count, 0)


class SupersedeChainTests(unittest.TestCase):
    """I2 — supersede chain ordering matches event-emission order."""

    def setUp(self):
        self.db = _fresh_post_migration_db()

    def tearDown(self):
        try:
            os.unlink(self.db)
        except OSError:
            pass

    def test_single_edge_created_appears_in_snapshot(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {"head_id": "head-1", "new_edge_id": "edge-1",
             "validity": {"from": "2026-06-06T10:00:00", "to": None}},
            db_path=self.db,
        )
        self.assertTrue(ok)
        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertIn("edge-1", snap.edges)
        self.assertEqual(snap.supersede_chains["head-1"],
                         ["head-1", "edge-1"])

    def test_chain_extended_preserves_insertion_order(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        # Three edges in succession under the same head.
        for new_id in ("a", "b", "c"):
            self.assertTrue(emit_lifecycle_event(
                EVT_SUPERSEDE_EDGE_CREATED,
                {"head_id": "h", "new_edge_id": new_id,
                 "validity": {"from": "2026-06-06T10:00:00", "to": None}},
                db_path=self.db,
            ))
        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        # Chain order = head then emission order.
        self.assertEqual(snap.supersede_chains["h"], ["h", "a", "b", "c"])

    def test_two_separate_chains_do_not_collide(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h1", "new_edge_id": "e1"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h2", "new_edge_id": "e2"},
                             db_path=self.db)
        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertEqual(set(snap.supersede_chains), {"h1", "h2"})
        self.assertEqual(snap.supersede_chains["h1"], ["h1", "e1"])
        self.assertEqual(snap.supersede_chains["h2"], ["h2", "e2"])

    def test_chain_extended_event_appends_link(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_SUPERSEDE_CHAIN_EXTENDED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "e1"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_SUPERSEDE_CHAIN_EXTENDED,
                             {"chain_head": "h", "new_link": "e2",
                              "validity": {}},
                             db_path=self.db)
        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertEqual(snap.supersede_chains["h"], ["h", "e1", "e2"])
        # The extended link is registered with a stub edge dict so
        # callers can resolve id → edge.
        self.assertIn("e2", snap.edges)


class CascadeAndExpirationTests(unittest.TestCase):
    """I3 — invalidate events remove ids from edges + add to
    invalidated_ids."""

    def setUp(self):
        self.db = _fresh_post_migration_db()

    def tearDown(self):
        try:
            os.unlink(self.db)
        except OSError:
            pass

    def test_cascade_invalidate_removes_edge(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_CASCADE_INVALIDATE,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "doomed"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_CASCADE_INVALIDATE,
                             {"invalidated_edges": ["doomed"],
                              "mutation_type": "invalidated"},
                             db_path=self.db)
        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertNotIn("doomed", snap.edges)
        self.assertIn("doomed", snap.invalidated_ids)

    def test_cascade_invalidate_single_edge_id_payload(self):
        """Backward-compat: some emit sites use {edge_id: "..."}
        rather than the canonical {invalidated_edges: [...]}."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_CASCADE_INVALIDATE,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "doomed"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_CASCADE_INVALIDATE,
                             {"edge_id": "doomed"},
                             db_path=self.db)
        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertIn("doomed", snap.invalidated_ids)

    def test_t1_expiration_invalidates_edge(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_T1_EXPIRATION_CASCADE,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "expiring"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_T1_EXPIRATION_CASCADE,
                             {"edge_id": "expiring",
                              "validity": {"to": "2026-06-06T11:00:00"}},
                             db_path=self.db)
        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertNotIn("expiring", snap.edges)
        self.assertIn("expiring", snap.invalidated_ids)

    def test_invalidate_after_recreate_keeps_it_invalidated(self):
        """A subsequent edge_created with the same id does NOT
        un-invalidate — replay reflects event order (last write wins
        only when handlers say so). edge_created carries the new
        edge dict back into edges, but the id stays in
        invalidated_ids as the historical record."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_CASCADE_INVALIDATE,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "x"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_CASCADE_INVALIDATE,
                             {"invalidated_edges": ["x"]},
                             db_path=self.db)
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "x"},
                             db_path=self.db)
        snap = reconstruct_graph_at(datetime.now(), audit_log_path=self.db)
        self.assertIn("x", snap.edges)        # last write wins for live state
        self.assertIn("x", snap.invalidated_ids)   # but history is preserved


class CutoffSemanticsTests(unittest.TestCase):
    """Replay respects the ``t`` cutoff: events strictly after t are
    excluded."""

    def setUp(self):
        self.db = _fresh_post_migration_db()

    def tearDown(self):
        try:
            os.unlink(self.db)
        except OSError:
            pass

    def test_event_after_t_excluded(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        t0 = datetime(2026, 6, 6, 10, 0, 0)
        t1 = datetime(2026, 6, 6, 11, 0, 0)
        t2 = datetime(2026, 6, 6, 12, 0, 0)
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "before"},
                             timestamp=t0.isoformat(), db_path=self.db)
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "after"},
                             timestamp=t2.isoformat(), db_path=self.db)
        snap = reconstruct_graph_at(t1, audit_log_path=self.db)
        self.assertIn("before", snap.edges)
        self.assertNotIn("after", snap.edges)
        self.assertEqual(snap.event_count, 1)

    def test_event_at_exact_t_included(self):
        """``timestamp <= t`` — exact-match is inclusive."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        t = datetime(2026, 6, 6, 10, 0, 0)
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "edge-at-t"},
                             timestamp=t.isoformat(), db_path=self.db)
        snap = reconstruct_graph_at(t, audit_log_path=self.db)
        self.assertIn("edge-at-t", snap.edges)


class DeterminismAndIdempotenceTests(unittest.TestCase):
    """LOCK 4 — pure function. Same (t, audit_log_path) → byte-equal
    snapshot."""

    def setUp(self):
        self.db = _fresh_post_migration_db()

    def tearDown(self):
        try:
            os.unlink(self.db)
        except OSError:
            pass

    def test_two_reconstructions_byte_equal(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_CASCADE_INVALIDATE,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "e1"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "e2"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_CASCADE_INVALIDATE,
                             {"invalidated_edges": ["e1"]},
                             db_path=self.db)
        t = datetime.now()
        snap_a = reconstruct_graph_at(t, audit_log_path=self.db)
        snap_b = reconstruct_graph_at(t, audit_log_path=self.db)
        self.assertEqual(snap_a.edges, snap_b.edges)
        self.assertEqual(snap_a.supersede_chains, snap_b.supersede_chains)
        self.assertEqual(snap_a.invalidated_ids, snap_b.invalidated_ids)
        self.assertEqual(snap_a.event_count, snap_b.event_count)

    def test_replay_equality_round_trip(self):
        """I4 weaker form (until mutation wiring lands in T5.A.b):
        snapshot at t = now is equal to snapshot taken right after
        another emit doesn't change pre-existing rows."""
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "a"},
                             db_path=self.db)
        t_before = datetime.now()
        snap_before = reconstruct_graph_at(t_before, audit_log_path=self.db)
        # Emit something after t_before — must NOT change the snapshot
        # at t_before.
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "b"},
                             timestamp=(t_before + timedelta(hours=1))
                             .isoformat(),
                             db_path=self.db)
        snap_after = reconstruct_graph_at(t_before, audit_log_path=self.db)
        self.assertEqual(snap_before.edges, snap_after.edges)
        self.assertEqual(snap_before.event_count, snap_after.event_count)


class AuditOnlyInvariantTests(unittest.TestCase):
    """I1 — reconstruct_graph_at must NOT read the wiki, the graph
    engine, or any module beyond the audit_log SELECT.

    Approach: import the module fresh and assert that the file
    list it touches contains only the audit_log DB path. A coarser
    but solid signal is the absence of imports of core.graph_engine,
    core.workspace, core.memory etc — but checking for negative
    imports is brittle. We instead pin the *positive* side: the
    function never opens any file other than the audit DB during a
    reconstruct call.
    """

    def test_only_reads_the_audit_db(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_SUPERSEDE_EDGE_CREATED,
        )
        from core.lifecycle import replay_graph as rg
        db = _fresh_post_migration_db()
        try:
            emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                                 {"head_id": "h", "new_edge_id": "e"},
                                 db_path=db)

            opened_paths = []
            real_connect = sqlite3.connect

            def spy_connect(path, *a, **kw):
                opened_paths.append(path)
                return real_connect(path, *a, **kw)

            # Monkeypatch the sqlite3 used by the replay_graph module
            # so we observe every connection it opens.
            saved = rg.sqlite3.connect
            rg.sqlite3.connect = spy_connect
            try:
                rg.reconstruct_graph_at(datetime.now(), audit_log_path=db)
            finally:
                rg.sqlite3.connect = saved

            # Every connect call must target the audit DB. No wiki,
            # no knowledge_tracker DB, no graph engine state.
            self.assertTrue(all(p == db for p in opened_paths),
                            f"unexpected DB opens: {opened_paths}")
        finally:
            os.unlink(db)


class IncludeFilterTests(unittest.TestCase):
    """`include_event_types` lets PR-T5.C narrow the snapshot to e.g.
    only T7 events when checking cross-chain consistency vs
    `reconstruct_view_at`."""

    def setUp(self):
        self.db = _fresh_post_migration_db()

    def tearDown(self):
        try:
            os.unlink(self.db)
        except OSError:
            pass

    def test_include_filter_skips_other_types(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event,
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_CASCADE_INVALIDATE,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        emit_lifecycle_event(EVT_SUPERSEDE_EDGE_CREATED,
                             {"head_id": "h", "new_edge_id": "e"},
                             db_path=self.db)
        emit_lifecycle_event(EVT_CASCADE_INVALIDATE,
                             {"invalidated_edges": ["e"]},
                             db_path=self.db)
        # Only T7 supersede events — invalidate should NOT remove e.
        snap = reconstruct_graph_at(
            datetime.now(),
            audit_log_path=self.db,
            include_event_types=(EVT_SUPERSEDE_EDGE_CREATED,),
        )
        self.assertIn("e", snap.edges)
        self.assertEqual(snap.invalidated_ids, frozenset())
        self.assertEqual(snap.event_count, 1)


class MalformedRowsTests(unittest.TestCase):
    """Defence-in-depth: malformed event_payload JSON or unknown
    event_type rows are skipped — they cannot crash the snapshot."""

    def test_malformed_payload_skipped(self):
        from core.lifecycle.replay_graph import reconstruct_graph_at
        db = _fresh_post_migration_db()
        try:
            # Hand-craft a malformed row.
            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, user_role, endpoint, event_type, event_payload) "
                "VALUES (?, ?, ?, ?, ?)",
                ("2026-06-06T10:00:00", "system",
                 "lifecycle.supersede.edge_created",
                 "lifecycle.supersede.edge_created",
                 "{not valid json"),
            )
            conn.commit()
            conn.close()
            snap = reconstruct_graph_at(datetime.now(), audit_log_path=db)
            # Skipped — no edges, no count.
            self.assertEqual(snap.edges, {})
            self.assertEqual(snap.event_count, 0)
        finally:
            os.unlink(db)

    def test_unknown_event_type_skipped(self):
        from core.lifecycle.replay_graph import reconstruct_graph_at
        db = _fresh_post_migration_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, user_role, endpoint, event_type, event_payload) "
                "VALUES (?, ?, ?, ?, ?)",
                ("2026-06-06T10:00:00", "system",
                 "lifecycle.cascadx.invalidate",
                 "lifecycle.cascadx.invalidate",
                 json.dumps({"invalidated_edges": ["x"]})),
            )
            conn.commit()
            conn.close()
            snap = reconstruct_graph_at(datetime.now(), audit_log_path=db)
            self.assertEqual(snap.event_count, 0)
            self.assertEqual(snap.invalidated_ids, frozenset())
        finally:
            os.unlink(db)


class BackfillSnapshotTests(unittest.TestCase):
    """Backfill events bootstrap the snapshot from a known baseline
    (for operators whose pre-migration wiki cannot re-derive every
    historical mutation)."""

    def test_backfill_bootstraps_edges_and_chains(self):
        from core.lifecycle.replay_audit import (
            emit_lifecycle_event, EVT_BACKFILL_SNAPSHOT,
        )
        from core.lifecycle.replay_graph import reconstruct_graph_at
        db = _fresh_post_migration_db()
        try:
            emit_lifecycle_event(
                EVT_BACKFILL_SNAPSHOT,
                {
                    "edges": {
                        "e1": {"id": "e1", "validity": {}},
                        "e2": {"id": "e2", "validity": {}},
                    },
                    "supersede_chains": {"h": ["h", "e1", "e2"]},
                    "invalidated_ids": ["e_old"],
                },
                db_path=db,
            )
            snap = reconstruct_graph_at(datetime.now(), audit_log_path=db)
            self.assertEqual(set(snap.edges), {"e1", "e2"})
            self.assertEqual(snap.supersede_chains, {"h": ["h", "e1", "e2"]})
            self.assertIn("e_old", snap.invalidated_ids)
        finally:
            os.unlink(db)


if __name__ == "__main__":
    unittest.main()
