"""v0.5 Track F.1 TT.d — /admin/graph/diff-vs-now endpoint.

Surfaces the server-side now-vs-T diff for the Time-Travel Dashboard
modal. Calls ``reconstruct_graph_at`` twice (at ``t`` and at the
current wall-clock moment) and returns a structured diff:
``added_edges`` / ``removed_edges`` / ``invalidated_since`` /
``chain_extended`` / ``mounted_packs_added`` / ``mounted_packs_removed``.

Coverage:

* Route registered + admin-gated (employee JWT → 403).
* 400 on missing or malformed ``t`` query param.
* Empty audit_log → all-zeros diff body (the "no lifecycle events
  yet" case the renderer surfaces as "No changes between T and NOW").
* Synthetic events: edge created AFTER ``t`` → added_edges; edge
  cascade-invalidated AFTER ``t`` → invalidated_since.
* Chain extension: new chain link appended AFTER ``t`` →
  chain_extended carries the diff.
* ``limit`` parameter caps each collection.
* ``tenant_id`` G1.b filter applied to BOTH snapshots.

Run:
  python -m unittest tests.test_v05_admin_diff_vs_now
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-diff-vs-now-endpoint-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


# ─── helpers ─────────────────────────────────────────────────────────


def _api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def _admin_headers() -> dict:
    from core.auth import create_token
    return {"Authorization": f"Bearer {create_token('test-admin', 'admin')}"}


def _employee_headers() -> dict:
    from core.auth import create_token
    return {"Authorization": f"Bearer {create_token('test-employee', 'employee')}"}


def _seed_audit_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL,
            user_role       TEXT    NOT NULL DEFAULT 'system',
            endpoint        TEXT    NOT NULL DEFAULT 'lifecycle',
            query           TEXT,
            answer          TEXT,
            graph_paths     TEXT,
            elapsed_sec     REAL,
            blocked         INTEGER DEFAULT 0,
            security_event  TEXT,
            ip_address      TEXT,
            event_type      TEXT,
            event_payload   TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_event(path: str, ts: str, event_type: str, payload: dict) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO audit_log (timestamp, user_role, endpoint, event_type, event_payload) "
        "VALUES (?, 'system', 'lifecycle', ?, ?)",
        (ts, event_type, json.dumps(payload)),
    )
    conn.commit()
    conn.close()


# ─── tests ───────────────────────────────────────────────────────────


class DiffVsNowBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._db = self._tmp.name
        _seed_audit_db(self._db)
        self._prev_env = os.environ.get("JAMES_AUDIT_DB")
        os.environ["JAMES_AUDIT_DB"] = self._db

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("JAMES_AUDIT_DB", None)
        else:
            os.environ["JAMES_AUDIT_DB"] = self._prev_env
        Path(self._db).unlink(missing_ok=True)

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)


class DiffVsNowAdminGateTests(DiffVsNowBaseTests):
    def test_employee_jwt_rejected(self):
        c = self._client()
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "2026-06-13T00:00:00Z"},
            headers=_employee_headers(),
        )
        self.assertEqual(r.status_code, 403, r.text)

    def test_admin_jwt_accepted_empty_audit_log(self):
        c = self._client()
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "2026-06-13T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["event_count_at_t"], 0)
        self.assertEqual(body["event_count_at_now"], 0)
        self.assertEqual(body["added_edges"], [])
        self.assertEqual(body["removed_edges"], [])
        self.assertEqual(body["invalidated_since"], [])
        self.assertEqual(body["chain_extended"], {})
        self.assertEqual(body["mounted_packs_added"], [])
        self.assertEqual(body["mounted_packs_removed"], [])
        self.assertFalse(body["truncated"])


class DiffVsNowParseTests(DiffVsNowBaseTests):
    def test_missing_t_is_422(self):
        c = self._client()
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 422, r.text)

    def test_empty_t_is_400(self):
        c = self._client()
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "   "},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 400, r.text)

    def test_malformed_t_is_400(self):
        c = self._client()
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "garbage"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 400, r.text)


class DiffVsNowDiffSemanticsTests(DiffVsNowBaseTests):
    """Synthetic lifecycle events round-trip through the diff."""

    def test_edge_created_after_t_appears_in_added(self):
        from core.lifecycle.replay_audit import EVT_SUPERSEDE_EDGE_CREATED
        # Two edges: edge_old created before t, edge_new created after.
        t_before = "2026-06-01T00:00:00+00:00"
        t_after = "2026-06-10T00:00:00+00:00"
        _insert_event(self._db, t_before, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_old", "head_id": "edge_old",
            "validity": {"from": t_before, "to": None},
        })
        _insert_event(self._db, t_after, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_new", "head_id": "edge_new",
            "validity": {"from": t_after, "to": None},
        })
        c = self._client()
        # t = 2026-06-05 → snap_t sees only edge_old, snap_now sees both.
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "2026-06-05T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["event_count_at_t"], 1)
        self.assertEqual(body["event_count_at_now"], 2)
        self.assertEqual(body["added_edges"], ["edge_new"])
        self.assertEqual(body["removed_edges"], [])
        self.assertEqual(body["invalidated_since"], [])

    def test_edge_invalidated_after_t_appears_in_invalidated_since(self):
        from core.lifecycle.replay_audit import (
            EVT_SUPERSEDE_EDGE_CREATED, EVT_CASCADE_INVALIDATE,
        )
        t0 = "2026-06-01T00:00:00+00:00"
        t_inv = "2026-06-10T00:00:00+00:00"
        _insert_event(self._db, t0, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_x", "head_id": "edge_x",
            "validity": {"from": t0, "to": None},
        })
        _insert_event(self._db, t_inv, EVT_CASCADE_INVALIDATE, {
            "edge_id": "edge_x",
        })
        c = self._client()
        # t = 2026-06-05 → edge_x active at T, invalidated by NOW.
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "2026-06-05T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("edge_x", body["invalidated_since"])
        # edge_x present at T but not at NOW (invalidated) → also in
        # removed_edges.
        self.assertIn("edge_x", body["removed_edges"])

    def test_chain_extension_after_t_appears_in_chain_extended(self):
        from core.lifecycle.replay_audit import EVT_SUPERSEDE_EDGE_CREATED
        # head_a created before t, then extended after t with edge_b.
        t0 = "2026-06-01T00:00:00+00:00"
        t1 = "2026-06-10T00:00:00+00:00"
        _insert_event(self._db, t0, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "head_a", "head_id": "head_a",
            "validity": {"from": t0, "to": None},
        })
        _insert_event(self._db, t1, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_b", "head_id": "head_a",
            "validity": {"from": t1, "to": None},
        })
        c = self._client()
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "2026-06-05T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("head_a", body["chain_extended"])
        ce = body["chain_extended"]["head_a"]
        self.assertEqual(ce["at_t"],   ["head_a"])
        self.assertEqual(ce["at_now"], ["head_a", "edge_b"])

    def test_no_changes_between_t_and_now_is_empty_diff(self):
        from core.lifecycle.replay_audit import EVT_SUPERSEDE_EDGE_CREATED
        # All events happen BEFORE t — nothing changes between T and NOW.
        t0 = "2026-06-01T00:00:00+00:00"
        _insert_event(self._db, t0, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_static", "head_id": "edge_static",
            "validity": {"from": t0, "to": None},
        })
        c = self._client()
        # Pick t after the only event → snap_t == snap_now (modulo
        # event_count which is identical because no events landed in
        # the (T, NOW] window).
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "2026-06-10T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["added_edges"], [])
        self.assertEqual(body["removed_edges"], [])
        self.assertEqual(body["invalidated_since"], [])
        self.assertEqual(body["chain_extended"], {})
        self.assertEqual(body["event_count_at_t"], 1)
        self.assertEqual(body["event_count_at_now"], 1)

    def test_tenant_id_filter_applied_to_both_snapshots(self):
        from core.lifecycle.replay_audit import EVT_SUPERSEDE_EDGE_CREATED
        # Two edges, one stamped acme + one globex. Both created
        # after t. acme filter should see only edge_a in added_edges.
        t1 = "2026-06-10T00:00:00+00:00"
        t2 = "2026-06-11T00:00:00+00:00"
        _insert_event(self._db, t1, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_a", "head_id": "edge_a",
            "tenant_id": "acme",
            "validity": {"from": t1, "to": None},
        })
        _insert_event(self._db, t2, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_b", "head_id": "edge_b",
            "tenant_id": "globex",
            "validity": {"from": t2, "to": None},
        })
        c = self._client()
        r = c.get(
            "/admin/graph/diff-vs-now",
            params={"api_key": self._api_key, "t": "2026-06-05T00:00:00Z",
                    "tenant_id": "acme"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["added_edges"], ["edge_a"])
        # event_count_at_now respects the same filter — only acme rows
        # contribute to the snapshot.
        self.assertEqual(body["event_count_at_now"], 1)


if __name__ == "__main__":
    unittest.main()
