"""Phase 4a — dashboard reader migration + legacy /admin/audit removal.

Replaces tests/test_admin_dashboard_tail.py (which proved the old
``_read_jsonl_tail`` helper worked correctly; that helper is gone).

Coverage:
  - /admin/audit (legacy multi-stream JSONL reader) returns 404 — the
    endpoint was deleted in this PR.
  - /admin/dashboard's ``security_events`` count + ``recent_logs`` list
    are sourced from the SQLite audit_log table, filtered to
    ``endpoint LIKE 'tool:%' OR endpoint LIKE 'attack:%'``. The
    JSONL files on disk are now irrelevant to this endpoint.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-dashboard-audit-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _seed(path: str, rows: list[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL,
            user_role       TEXT    NOT NULL,
            endpoint        TEXT    NOT NULL,
            query           TEXT,
            answer          TEXT,
            graph_paths     TEXT,
            elapsed_sec     REAL,
            blocked         INTEGER DEFAULT 0,
            security_event  TEXT,
            ip_address      TEXT
        )
    """)
    for r in rows:
        conn.execute(
            "INSERT INTO audit_log "
            "(timestamp, user_role, endpoint, query, "
            " security_event, blocked) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (r["timestamp"], r["user_role"], r["endpoint"],
             r.get("query"), r.get("security_event"),
             int(r.get("blocked", 0))),
        )
    conn.commit()
    conn.close()


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


class LegacyAuditEndpointRemovedTests(unittest.TestCase):
    """The legacy GET /admin/audit endpoint was deleted in this PR.
    Confirm the surface area is gone and the route does not silently
    fall through to a 200."""

    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _admin_hdr(self) -> dict:
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token('test-admin', 'admin')}"}

    def test_legacy_endpoint_returns_404(self):
        r = self._client().get(
            "/admin/audit",
            params={"api_key": self._api_key},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 404,
                         f"Legacy /admin/audit must be gone (got {r.status_code})")

    def test_legacy_handler_symbol_gone(self):
        # Defence in depth: even an unmounted route's handler shouldn't
        # be importable, since a future refactor could re-mount it.
        import server_llmwiki as srv
        self.assertFalse(hasattr(srv, "admin_audit"),
                         "Old admin_audit handler must be removed")

    def test_read_jsonl_tail_helper_gone(self):
        # _read_jsonl_tail was the only consumer of /admin/audit's
        # JSONL-tail strategy. Its sole caller (admin_dashboard) now
        # reads SQLite, so the helper is dead.
        import server_llmwiki as srv
        self.assertFalse(hasattr(srv, "_read_jsonl_tail"),
                         "_read_jsonl_tail must be removed once dashboard "
                         "no longer uses it")


class DashboardSqliteSourcedTests(unittest.TestCase):
    """/admin/dashboard's ``security_events`` and ``recent_logs`` panels
    now come from audit_log (tool:* / attack:* rows). Prior versions
    tail-read james_audit_tool.jsonl + james_attack_log.jsonl."""

    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")
        import server_llmwiki as srv
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        self._saved_db = srv._AUDIT_DB
        srv._AUDIT_DB = self.db
        _seed(self.db, self._fixture())

    def tearDown(self):
        import server_llmwiki as srv
        srv._AUDIT_DB = self._saved_db
        Path(self.db).unlink(missing_ok=True)

    def _fixture(self) -> list[dict]:
        # Mix of tool / attack rows (counted) and a /query/ row
        # (NOT counted — the dashboard's tool/attack panel skips it).
        return [
            {"timestamp": "2026-05-11T10:00:00", "user_role": "admin",
             "endpoint": "tool:router:TOOL_EXECUTED",
             "query": "read_file: workspace/foo.py",
             "security_event": "TOOL_EXECUTED"},
            {"timestamp": "2026-05-11T10:01:00", "user_role": "external",
             "endpoint": "tool:sandbox:SANDBOX_BLOCK",
             "query": "../escape",
             "security_event": "SANDBOX_BLOCK", "blocked": 1},
            {"timestamp": "2026-05-11T10:02:00", "user_role": "external",
             "endpoint": "attack:injection",
             "query": "ignore previous",
             "security_event": "injection", "blocked": 1},
            # Non-security-pane row (must be ignored by recent_logs):
            {"timestamp": "2026-05-11T10:03:00", "user_role": "admin",
             "endpoint": "/query/", "query": "hello",
             "security_event": ""},
            # System row (also outside tool/attack pane):
            {"timestamp": "2026-05-11T10:04:00", "user_role": "system",
             "endpoint": "system:INFO:orchestrator.start",
             "query": "",
             "security_event": "orchestrator.start"},
        ]

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _admin_hdr(self) -> dict:
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token('test-admin', 'admin')}"}

    def test_security_events_counts_blocked_and_block_events(self):
        r = self._client().get(
            "/admin/dashboard",
            params={"api_key": self._api_key},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # security_events =
        #   panel count (tool/attack rows w/ blocked or BLOCK event)
        # + blocked_count (rows on /query/ with blocked=1).
        # Fixture: 2 blocked rows (sandbox+attack) panel-side; 0 query.
        self.assertGreaterEqual(body["security_events"], 2,
                                "must count blocked tool/attack rows")

    def test_recent_logs_only_has_tool_and_attack_rows(self):
        r = self._client().get(
            "/admin/dashboard",
            params={"api_key": self._api_key},
            headers=self._admin_hdr(),
        )
        body = r.json()
        recent = body.get("recent_logs", [])
        events = {e.get("event") for e in recent}
        # Tool + attack rows present.
        self.assertIn("TOOL_EXECUTED", events)
        self.assertIn("SANDBOX_BLOCK", events)
        self.assertIn("injection",     events)
        # /query/ row (security_event="") and system row excluded.
        self.assertNotIn("orchestrator.start", events)

    def test_recent_logs_shape(self):
        r = self._client().get(
            "/admin/dashboard",
            params={"api_key": self._api_key},
            headers=self._admin_hdr(),
        )
        recent = r.json().get("recent_logs", [])
        self.assertTrue(recent, "fixture has rows; recent_logs should be non-empty")
        for e in recent:
            # New shape — keys the admin.html widget consumes.
            for key in ("time", "event", "role", "blocked"):
                self.assertIn(key, e, f"missing {key} in entry {e}")


if __name__ == "__main__":
    unittest.main()
