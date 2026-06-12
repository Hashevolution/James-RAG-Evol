"""v0.5 G1.b — replay-side tenant filter tests.

Covers:

  * `tenant_id=None` (default) → byte-identical to pre-G1.b:
    every row visible regardless of stamp.
  * `tenant_id="<id>"` → only payload-stamped matching rows fold in.
  * Strict-exclusion semantic: rows without a `tenant_id` field
    are EXCLUDED when filter is set (not treated as "match-all").
  * Determinism: same audit_log + same `t` + same filter ⇒ same
    snapshot.
  * Composition: G1.a write-side stamping + G1.b read-side filter
    produces the correct round-trip.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from core.lifecycle.replay_audit import (
    EVT_SUPERSEDE_EDGE_CREATED,
    emit_lifecycle_event,
)
from core.lifecycle.replay_graph import reconstruct_graph_at


def _make_temp_db_with_audit_schema() -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="james-test-")
    os.close(fd)
    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE audit_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                user_role       TEXT,
                endpoint        TEXT,
                query           TEXT,
                answer          TEXT,
                graph_paths     TEXT,
                blocked         INTEGER NOT NULL DEFAULT 0,
                security_event  TEXT,
                elapsed_sec     REAL,
                ip_address      TEXT,
                event_type      TEXT,
                event_payload   TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return path


def _seed_supersede_event(
    db_path: str, *, ts: str, edge_id: str,
    tenant_id: str = None,
) -> None:
    """Seed one supersede event directly via SQL (not emit) so we
    control timestamp + payload exactly for filter tests."""
    payload = {
        "edge_id":          edge_id,
        "new_edge_id":      "new_" + edge_id,
        "mutation_type":    "superseded",
        "supersede_ts":     ts,
        # Match the supersede handler's expected payload shape
        # (per `replay_graph.py::_handle_supersede_edge_created`).
        "validity": {
            "from": ts,
            "to":   None,
        },
        "sources": [],
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO audit_log "
            "(timestamp, user_role, endpoint, blocked, "
            " event_type, event_payload) "
            "VALUES (?, 'system', 'evt', 0, ?, ?)",
            (ts, EVT_SUPERSEDE_EDGE_CREATED, json.dumps(payload)),
        )
        conn.commit()
    finally:
        conn.close()


class DefaultBehaviourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db_with_audit_schema()
        _seed_supersede_event(
            cls.db_path,
            ts="2026-06-10T00:00:00+00:00",
            edge_id="e_a",
            tenant_id="tenant_acme",
        )
        _seed_supersede_event(
            cls.db_path,
            ts="2026-06-10T01:00:00+00:00",
            edge_id="e_b",
            tenant_id="tenant_globex",
        )
        _seed_supersede_event(
            cls.db_path,
            ts="2026-06-10T02:00:00+00:00",
            edge_id="e_c",
            # No tenant_id stamp
        )
        cls.cutoff = datetime(2026, 6, 11, tzinfo=timezone.utc)

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def test_default_none_sees_all_rows(self):
        # Pre-G1.b byte-identical: all 3 rows fold in.
        snap = reconstruct_graph_at(self.cutoff, audit_log_path=self.db_path)
        self.assertEqual(snap.event_count, 3)

    def test_default_none_keyword_only(self):
        # tenant_id is keyword-only — positional usage must fail.
        with self.assertRaises(TypeError):
            reconstruct_graph_at(self.cutoff, self.db_path, None, None)  # type: ignore[misc]


class FilterAppliesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db_with_audit_schema()
        _seed_supersede_event(
            cls.db_path,
            ts="2026-06-10T00:00:00+00:00",
            edge_id="e_acme_a",
            tenant_id="tenant_acme",
        )
        _seed_supersede_event(
            cls.db_path,
            ts="2026-06-10T01:00:00+00:00",
            edge_id="e_globex_a",
            tenant_id="tenant_globex",
        )
        _seed_supersede_event(
            cls.db_path,
            ts="2026-06-10T02:00:00+00:00",
            edge_id="e_acme_b",
            tenant_id="tenant_acme",
        )
        _seed_supersede_event(
            cls.db_path,
            ts="2026-06-10T03:00:00+00:00",
            edge_id="e_no_tenant",
        )
        cls.cutoff = datetime(2026, 6, 11, tzinfo=timezone.utc)

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def test_acme_filter_returns_only_acme_rows(self):
        snap = reconstruct_graph_at(
            self.cutoff,
            audit_log_path=self.db_path,
            tenant_id="tenant_acme",
        )
        # Two acme events.
        self.assertEqual(snap.event_count, 2)

    def test_globex_filter_returns_only_globex_row(self):
        snap = reconstruct_graph_at(
            self.cutoff,
            audit_log_path=self.db_path,
            tenant_id="tenant_globex",
        )
        self.assertEqual(snap.event_count, 1)

    def test_unknown_tenant_returns_empty(self):
        snap = reconstruct_graph_at(
            self.cutoff,
            audit_log_path=self.db_path,
            tenant_id="tenant_does_not_exist",
        )
        self.assertEqual(snap.event_count, 0)

    def test_strict_exclusion_no_stamp_excluded(self):
        # The "e_no_tenant" event has no tenant_id stamp. When the
        # filter is set, it MUST be excluded (not treated as
        # "match-all"). The acme filter returns 2 events
        # (e_acme_a + e_acme_b), NOT 3.
        snap = reconstruct_graph_at(
            self.cutoff,
            audit_log_path=self.db_path,
            tenant_id="tenant_acme",
        )
        # 2, not 3.
        self.assertEqual(snap.event_count, 2)


class DeterminismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db_with_audit_schema()
        for i in range(5):
            _seed_supersede_event(
                cls.db_path,
                ts=f"2026-06-10T0{i}:00:00+00:00",
                edge_id=f"e_{i}",
                tenant_id="tenant_x" if i % 2 == 0 else "tenant_y",
            )
        cls.cutoff = datetime(2026, 6, 11, tzinfo=timezone.utc)

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def test_same_inputs_same_output(self):
        a = reconstruct_graph_at(
            self.cutoff,
            audit_log_path=self.db_path,
            tenant_id="tenant_x",
        )
        b = reconstruct_graph_at(
            self.cutoff,
            audit_log_path=self.db_path,
            tenant_id="tenant_x",
        )
        self.assertEqual(a.event_count, b.event_count)
        self.assertEqual(a.replayed_at, b.replayed_at)
        self.assertEqual(set(a.edges.keys()), set(b.edges.keys()))


class G1aG1bCompositionTests(unittest.TestCase):
    """G1.a emit_lifecycle_event stamps tenant_id; G1.b
    reconstruct_graph_at reads it. End-to-end check."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db_with_audit_schema()
        cls.cutoff = datetime(2026, 6, 12, tzinfo=timezone.utc)
        # G1.a path: emit_lifecycle_event with tenant_id kwarg.
        # Explicit timestamps (deterministic test — no reliance on
        # datetime.now() which would put rows past midnight-UTC
        # cutoff strings).
        ok1 = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {
                "edge_id": "e_compose_acme",
                "new_edge_id": "new_e_compose_acme",
                "mutation_type": "superseded",
                "supersede_ts": "2026-06-10T00:00:00+00:00",
                "validity": {
                    "from": "2026-06-10T00:00:00+00:00",
                    "to":   None,
                },
                "sources": [],
            },
            db_path=cls.db_path,
            timestamp="2026-06-10T00:00:00+00:00",
            tenant_id="tenant_acme",
        )
        ok2 = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {
                "edge_id": "e_compose_globex",
                "new_edge_id": "new_e_compose_globex",
                "mutation_type": "superseded",
                "supersede_ts": "2026-06-10T01:00:00+00:00",
                "validity": {
                    "from": "2026-06-10T01:00:00+00:00",
                    "to":   None,
                },
                "sources": [],
            },
            db_path=cls.db_path,
            timestamp="2026-06-10T01:00:00+00:00",
            tenant_id="tenant_globex",
        )
        assert ok1 and ok2

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def test_g1a_stamped_rows_filtered_by_g1b(self):
        snap = reconstruct_graph_at(
            self.cutoff,
            audit_log_path=self.db_path,
            tenant_id="tenant_acme",
        )
        self.assertEqual(snap.event_count, 1)


if __name__ == "__main__":
    unittest.main()
