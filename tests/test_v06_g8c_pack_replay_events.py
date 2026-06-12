"""v0.6 G8.c — pack mount/unmount audit-replay event tests.

Covers:

  * Event type taxonomy — 2 new events are in `LIFECYCLE_EVENT_TYPES`.
  * `is_lifecycle_event` recognises both new types.
  * `register_pack` emits `EVT_ONTOLOGY_PACK_MOUNTED` with the pack's
    metadata.
  * `unmount_pack` emits `EVT_ONTOLOGY_PACK_UNMOUNTED`.
  * Emit failure does not roll back the mount / unmount.
  * `reconstruct_graph_at(t)` rebuilds `mounted_pack_ids` from the
    event stream (the snapshot replays which packs were mounted
    at time T).
  * Empty snapshot has empty `mounted_pack_ids` tuple.
  * Mount + later unmount → snapshot at end shows the pack gone.
  * Mount A, mount B, unmount A → snapshot shows [B].
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict
from unittest import mock

from core.lifecycle.replay_audit import (
    EVT_ONTOLOGY_PACK_MOUNTED,
    EVT_ONTOLOGY_PACK_UNMOUNTED,
    LIFECYCLE_EVENT_TYPES,
    is_lifecycle_event,
)
from core.lifecycle.replay_graph import reconstruct_graph_at
from core.ontology_packs import (
    OntologyPack,
    _reset_for_tests,
    register_pack,
    unmount_pack,
)


@contextmanager
def _patched_env(**env: str):
    saved: Dict[str, str] = {}
    unset_keys = []
    for k, v in env.items():
        if k in os.environ:
            saved[k] = os.environ[k]
        else:
            unset_keys.append(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ[k] = v
        for k in unset_keys:
            os.environ.pop(k, None)


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


def _make_pack(pack_id="test-pack", **overrides):
    return OntologyPack(
        pack_id=pack_id,
        requires_capability="cap_x",
        subtypes={
            "pack_subtype_" + pack_id.replace("-", "_"): {
                "parent": "document",
                "since": "v0.6",
            },
        },
        **overrides,
    )


class EventTaxonomyTests(unittest.TestCase):
    def test_mounted_is_lifecycle_event(self):
        self.assertTrue(is_lifecycle_event(EVT_ONTOLOGY_PACK_MOUNTED))

    def test_unmounted_is_lifecycle_event(self):
        self.assertTrue(is_lifecycle_event(EVT_ONTOLOGY_PACK_UNMOUNTED))

    def test_both_in_taxonomy_tuple(self):
        self.assertIn(EVT_ONTOLOGY_PACK_MOUNTED, LIFECYCLE_EVENT_TYPES)
        self.assertIn(EVT_ONTOLOGY_PACK_UNMOUNTED, LIFECYCLE_EVENT_TYPES)


class RegisterPackEmitsTests(unittest.TestCase):
    def setUp(self):
        _reset_for_tests()

    def test_register_emits_mounted_event(self):
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            with mock.patch(
                "core.lifecycle.replay_audit.emit_lifecycle_event"
            ) as m:
                register_pack(_make_pack(pack_id="emit-test"))
        m.assert_called_once()
        args, _ = m.call_args
        self.assertEqual(args[0], EVT_ONTOLOGY_PACK_MOUNTED)
        payload = args[1]
        self.assertEqual(payload["pack_id"], "emit-test")
        self.assertEqual(payload["requires_capability"], "cap_x")

    def test_emit_failure_does_not_rollback_mount(self):
        # Even if the audit emit raises, the in-memory mount stays.
        from core.ontology_packs import mounted_packs
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            with mock.patch(
                "core.lifecycle.replay_audit.emit_lifecycle_event",
                side_effect=RuntimeError("audit unavailable"),
            ):
                register_pack(_make_pack(pack_id="resilient-pack"))
            self.assertEqual(len(mounted_packs()), 1)


class UnmountPackEmitsTests(unittest.TestCase):
    def setUp(self):
        _reset_for_tests()

    def test_unmount_emits_unmounted_event(self):
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            register_pack(_make_pack(pack_id="to-unmount"))
            with mock.patch(
                "core.lifecycle.replay_audit.emit_lifecycle_event"
            ) as m:
                unmount_pack("to-unmount")
        m.assert_called_once()
        args, _ = m.call_args
        self.assertEqual(args[0], EVT_ONTOLOGY_PACK_UNMOUNTED)
        self.assertEqual(args[1]["pack_id"], "to-unmount")


class ReconstructGraphAtPackRebuildTests(unittest.TestCase):
    """The decisive G8.c test — reconstruct_graph_at rebuilds the
    pack registry as it was at time T."""

    def setUp(self):
        self.db_path = _make_temp_db_with_audit_schema()
        self.cutoff = datetime(2026, 6, 15, tzinfo=timezone.utc)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def _seed_event(self, *, ts: str, event_type: str, payload: dict):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, user_role, endpoint, blocked, "
                " event_type, event_payload) "
                "VALUES (?, 'system', 'evt', 0, ?, ?)",
                (ts, event_type, json.dumps(payload)),
            )
            conn.commit()
        finally:
            conn.close()

    def test_empty_db_yields_empty_pack_tuple(self):
        snap = reconstruct_graph_at(
            self.cutoff, audit_log_path=self.db_path,
        )
        self.assertEqual(snap.mounted_pack_ids, ())

    def test_single_mount_appears_in_snapshot(self):
        self._seed_event(
            ts="2026-06-10T00:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_MOUNTED,
            payload={"pack_id": "pack-alpha",
                     "requires_capability": "cap_x"},
        )
        snap = reconstruct_graph_at(
            self.cutoff, audit_log_path=self.db_path,
        )
        self.assertEqual(snap.mounted_pack_ids, ("pack-alpha",))

    def test_mount_then_unmount_yields_empty(self):
        self._seed_event(
            ts="2026-06-10T00:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_MOUNTED,
            payload={"pack_id": "pack-alpha",
                     "requires_capability": "cap_x"},
        )
        self._seed_event(
            ts="2026-06-11T00:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_UNMOUNTED,
            payload={"pack_id": "pack-alpha"},
        )
        snap = reconstruct_graph_at(
            self.cutoff, audit_log_path=self.db_path,
        )
        self.assertEqual(snap.mounted_pack_ids, ())

    def test_mount_a_mount_b_unmount_a_yields_b(self):
        self._seed_event(
            ts="2026-06-10T00:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_MOUNTED,
            payload={"pack_id": "pack-a",
                     "requires_capability": "cap_x"},
        )
        self._seed_event(
            ts="2026-06-10T01:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_MOUNTED,
            payload={"pack_id": "pack-b",
                     "requires_capability": "cap_x"},
        )
        self._seed_event(
            ts="2026-06-10T02:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_UNMOUNTED,
            payload={"pack_id": "pack-a"},
        )
        snap = reconstruct_graph_at(
            self.cutoff, audit_log_path=self.db_path,
        )
        self.assertEqual(snap.mounted_pack_ids, ("pack-b",))

    def test_replay_at_intermediate_time_sees_only_earlier_mounts(self):
        # Mount A at T1, mount B at T3, unmount A at T5.
        # Replay at T2 should see only A.
        self._seed_event(
            ts="2026-06-10T01:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_MOUNTED,
            payload={"pack_id": "pack-a",
                     "requires_capability": "cap_x"},
        )
        self._seed_event(
            ts="2026-06-10T03:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_MOUNTED,
            payload={"pack_id": "pack-b",
                     "requires_capability": "cap_x"},
        )
        self._seed_event(
            ts="2026-06-10T05:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_UNMOUNTED,
            payload={"pack_id": "pack-a"},
        )
        snap_t2 = reconstruct_graph_at(
            datetime(2026, 6, 10, 2, tzinfo=timezone.utc),
            audit_log_path=self.db_path,
        )
        self.assertEqual(snap_t2.mounted_pack_ids, ("pack-a",))

    def test_event_count_increments_for_pack_events(self):
        self._seed_event(
            ts="2026-06-10T00:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_MOUNTED,
            payload={"pack_id": "pack-counter",
                     "requires_capability": "cap_x"},
        )
        self._seed_event(
            ts="2026-06-10T01:00:00+00:00",
            event_type=EVT_ONTOLOGY_PACK_UNMOUNTED,
            payload={"pack_id": "pack-counter"},
        )
        snap = reconstruct_graph_at(
            self.cutoff, audit_log_path=self.db_path,
        )
        # Pack events are first-class lifecycle events, so they
        # increment event_count even though they don't touch edges.
        self.assertEqual(snap.event_count, 2)


class BackwardsCompatTests(unittest.TestCase):
    """Existing reconstruct_graph_at callers (pre-G8.c) must still
    work — the new field has a default empty tuple."""

    def setUp(self):
        self.db_path = _make_temp_db_with_audit_schema()
        self.cutoff = datetime(2026, 6, 15, tzinfo=timezone.utc)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_snapshot_has_mounted_pack_ids_attr(self):
        snap = reconstruct_graph_at(
            self.cutoff, audit_log_path=self.db_path,
        )
        # Attribute exists + default empty tuple on empty DB.
        self.assertTrue(hasattr(snap, "mounted_pack_ids"))
        self.assertEqual(snap.mounted_pack_ids, ())


if __name__ == "__main__":
    unittest.main()
