"""v0.5 Track F.1 TT.b — /admin/graph/reconstruct-at endpoint.

Surfaces the audit-only ``reconstruct_graph_at(t)`` primitive (T5.B,
PR #712) as a JSON-over-HTTP read for the Time-Travel Dashboard
renderer (``frontend/static/time-travel-renderer.js``).

Coverage:

* Route registered + admin-gated (employee JWT → 403).
* 400 on missing or malformed ``t`` query param.
* Empty audit_log → ``event_count=0`` with empty edges / chains /
  invalidated_ids + ``ok=true`` (the "pre-mutation-wiring" case the
  renderer must handle gracefully).
* Synthetic lifecycle events → ``event_count`` matches, edges /
  chains / invalidated_ids round-trip.
* ``limit`` parameter caps edges + sets ``truncated=true``.
* ``tenant_id`` filter (G1.b) — strict-exclusion preserved.
* Determinism — same audit_log + same ``t`` → byte-identical body.

Run:
  python -m unittest tests.test_v05_admin_reconstruct_at
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-reconstruct-at-endpoint-32chars-min",
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
    """Create the audit_log table the lifecycle event stream expects.

    Mirrors the T5.A schema (timestamp, event_type, event_payload)
    plus the legacy columns existing endpoints still touch.
    """
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


class ReconstructAtAdminGateTests(unittest.TestCase):
    """Endpoint must be admin-gated (employee role → 403)."""

    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing; cannot exercise admin route")
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

    def test_employee_jwt_rejected(self):
        c = self._client()
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "2026-06-13T00:00:00Z"},
            headers=_employee_headers(),
        )
        self.assertEqual(r.status_code, 403, r.text)

    def test_admin_jwt_accepted_empty_audit_log(self):
        c = self._client()
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "2026-06-13T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("event_count"), 0)
        self.assertEqual(body.get("edges"), {})
        self.assertEqual(body.get("supersede_chains"), {})
        self.assertEqual(body.get("invalidated_ids"), [])
        self.assertEqual(body.get("invalidated_count"), 0)
        self.assertEqual(body.get("mounted_pack_ids"), [])
        self.assertFalse(body.get("truncated"))
        # replayed_at must round-trip the cutoff (ISO 8601).
        self.assertTrue("2026-06-13" in body.get("replayed_at", ""))


class ReconstructAtTimestampParseTests(unittest.TestCase):
    """400 on missing / malformed ``t``."""

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

    def test_missing_t_is_422(self):
        # FastAPI's own validation handles a required-but-missing
        # query param with 422. (Our explicit "missing 't'" 400 only
        # fires when ``t`` is the empty string.)
        c = self._client()
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 422, r.text)

    def test_empty_t_is_400(self):
        c = self._client()
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "   "},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 400, r.text)

    def test_malformed_t_is_400(self):
        c = self._client()
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "not-a-timestamp"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 400, r.text)


class ReconstructAtRoundTripTests(unittest.TestCase):
    """Synthetic lifecycle events round-trip through the endpoint."""

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

    def _seed_two_edges_one_invalidated(self):
        from core.lifecycle.replay_audit import (
            EVT_SUPERSEDE_EDGE_CREATED,
            EVT_CASCADE_INVALIDATE,
        )
        t0 = "2026-06-01T00:00:00+00:00"
        t1 = "2026-06-02T00:00:00+00:00"
        t2 = "2026-06-03T00:00:00+00:00"
        _insert_event(self._db, t0, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_a",
            "head_id":     "edge_a",
            "validity":    {"from": t0, "to": None},
        })
        _insert_event(self._db, t1, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_b",
            "head_id":     "edge_b",
            "validity":    {"from": t1, "to": None},
        })
        _insert_event(self._db, t2, EVT_CASCADE_INVALIDATE, {
            "edge_id": "edge_b",
        })

    def test_roundtrip_two_edges_one_invalidated(self):
        self._seed_two_edges_one_invalidated()
        c = self._client()
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "2026-06-30T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["event_count"], 3)
        # edge_b was invalidated → only edge_a in edges, edge_b in
        # invalidated_ids.
        self.assertIn("edge_a", body["edges"])
        self.assertNotIn("edge_b", body["edges"])
        self.assertEqual(body["invalidated_ids"], ["edge_b"])
        self.assertEqual(body["invalidated_count"], 1)

    def test_t_cutoff_excludes_later_events(self):
        self._seed_two_edges_one_invalidated()
        c = self._client()
        # Cutoff before the invalidate event: edge_b should still be
        # present + not invalidated.
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "2026-06-02T12:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["event_count"], 2)
        self.assertIn("edge_a", body["edges"])
        self.assertIn("edge_b", body["edges"])
        self.assertEqual(body["invalidated_ids"], [])

    def test_determinism_same_inputs_same_body(self):
        self._seed_two_edges_one_invalidated()
        c = self._client()
        r1 = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "2026-06-30T00:00:00Z"},
            headers=_admin_headers(),
        )
        r2 = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "2026-06-30T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json(), r2.json())

    def test_limit_truncates_edges(self):
        # Seed 5 edges, ask for limit=2.
        from core.lifecycle.replay_audit import EVT_SUPERSEDE_EDGE_CREATED
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        for i in range(5):
            ts = (base + timedelta(hours=i)).isoformat()
            _insert_event(self._db, ts, EVT_SUPERSEDE_EDGE_CREATED, {
                "new_edge_id": "edge_{0}".format(i),
                "head_id":     "edge_{0}".format(i),
                "validity":    {"from": ts, "to": None},
            })
        c = self._client()
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "2026-06-30T00:00:00Z",
                    "limit": 2},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["event_count"], 5)
        self.assertEqual(len(body["edges"]), 2)
        self.assertTrue(body["truncated"])

    def test_tenant_id_filter_strict_exclusion(self):
        # Three edges: edge_a stamped acme, edge_b stamped globex,
        # edge_c unstamped. acme filter must see ONLY edge_a.
        from core.lifecycle.replay_audit import EVT_SUPERSEDE_EDGE_CREATED
        t0 = "2026-06-01T00:00:00+00:00"
        t1 = "2026-06-02T00:00:00+00:00"
        t2 = "2026-06-03T00:00:00+00:00"
        _insert_event(self._db, t0, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_a", "head_id": "edge_a",
            "tenant_id": "acme",
            "validity": {"from": t0, "to": None},
        })
        _insert_event(self._db, t1, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_b", "head_id": "edge_b",
            "tenant_id": "globex",
            "validity": {"from": t1, "to": None},
        })
        _insert_event(self._db, t2, EVT_SUPERSEDE_EDGE_CREATED, {
            "new_edge_id": "edge_c", "head_id": "edge_c",
            "validity": {"from": t2, "to": None},
        })
        c = self._client()
        r = c.get(
            "/admin/graph/reconstruct-at",
            params={"api_key": self._api_key, "t": "2026-06-30T00:00:00Z",
                    "tenant_id": "acme"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # Only edge_a should appear under acme; edge_b excluded by
        # mismatch, edge_c excluded by strict-exclusion (no stamp).
        self.assertIn("edge_a", body["edges"])
        self.assertNotIn("edge_b", body["edges"])
        self.assertNotIn("edge_c", body["edges"])
        self.assertEqual(body["event_count"], 1)


if __name__ == "__main__":
    unittest.main()
