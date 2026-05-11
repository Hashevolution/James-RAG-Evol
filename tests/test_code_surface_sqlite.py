"""Phase 4b-1 — /code/surface/ migrated to SQLite audit_log.

The endpoint previously tail-read james_audit_tool.jsonl. Phase 1's
bridge mirrors the same events into audit_log.security_event, so the
endpoint can run a single bounded query instead.

Coverage:
  - Admin gate (employee → 403, no api_key → 401).
  - 4 event_type buckets populate the summary counts.
  - events list trimmed to last 50.
  - Non-surface events excluded.
  - Empty audit_log returns total_events=0 cleanly.
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
    "test-secret-for-code-surface-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


_SCHEMA = """
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
"""


def _seed(path: str, rows: list[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
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


class CodeSurfaceSqliteTests(unittest.TestCase):
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
        base = "2026-05-11T10:"
        return [
            # 4 surface event types — 1 each (counts the summary).
            {"timestamp": base + "00:00", "user_role": "external",
             "endpoint": "tool:sandbox:SANDBOX_BLOCK",
             "query":    "../etc/passwd",
             "security_event": "SANDBOX_BLOCK", "blocked": 1},
            {"timestamp": base + "01:00", "user_role": "external",
             "endpoint": "tool:sandbox:PATH_VIOLATION",
             "query":    "/etc/shadow",
             "security_event": "PATH_VIOLATION", "blocked": 1},
            {"timestamp": base + "02:00", "user_role": "admin",
             "endpoint": "tool:code_analyzer:ATTACK_SURFACE_SCAN",
             "query":    "workspace",
             "security_event": "ATTACK_SURFACE_SCAN"},
            {"timestamp": base + "03:00", "user_role": "external",
             "endpoint": "tool:code_editor:PROTECTED_FILE_BLOCK",
             "query":    "core/security_layer.py",
             "security_event": "PROTECTED_FILE_BLOCK", "blocked": 1},
            # Non-surface event — must be excluded.
            {"timestamp": base + "04:00", "user_role": "admin",
             "endpoint": "tool:router:TOOL_EXECUTED",
             "query":    "read_file: ok.py",
             "security_event": "TOOL_EXECUTED"},
            # /query/ row — also excluded.
            {"timestamp": base + "05:00", "user_role": "admin",
             "endpoint": "/query/", "query": "hello",
             "security_event": ""},
        ]

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _hdr(self, role: str) -> dict:
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token('test-' + role, role)}"}

    # ── Auth gate ───────────────────────────────────────────────
    def test_employee_returns_403(self):
        r = self._client().get(
            "/code/surface/",
            params={"api_key": self._api_key},
            headers=self._hdr("employee"),
        )
        self.assertEqual(r.status_code, 403)

    def test_no_api_key_returns_400_or_401(self):
        r = self._client().get(
            "/code/surface/",
            headers=self._hdr("admin"),
        )
        self.assertIn(r.status_code, (400, 401, 422))

    # ── Summary counts ──────────────────────────────────────────
    def test_summary_counts_each_event_type(self):
        r = self._client().get(
            "/code/surface/",
            params={"api_key": self._api_key},
            headers=self._hdr("admin"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        s = body["summary"]
        self.assertEqual(s["sandbox_blocks"],    1)
        self.assertEqual(s["path_violations"],   1)
        self.assertEqual(s["surface_scans"],     1)
        self.assertEqual(s["protected_blocks"],  1)
        # 4 surface rows total; non-surface rows excluded.
        self.assertEqual(body["total_events"], 4)

    def test_events_field_only_contains_surface_event_types(self):
        r = self._client().get(
            "/code/surface/",
            params={"api_key": self._api_key},
            headers=self._hdr("admin"),
        )
        body = r.json()
        evs = {e["event"] for e in body["events"]}
        self.assertEqual(
            evs,
            {"SANDBOX_BLOCK", "PATH_VIOLATION",
             "ATTACK_SURFACE_SCAN", "PROTECTED_FILE_BLOCK"},
        )
        # TOOL_EXECUTED row must be absent.
        self.assertNotIn("TOOL_EXECUTED", evs)

    def test_event_entry_shape(self):
        r = self._client().get(
            "/code/surface/",
            params={"api_key": self._api_key},
            headers=self._hdr("admin"),
        )
        events = r.json()["events"]
        for e in events:
            for k in ("time", "event", "role", "detail", "blocked"):
                self.assertIn(k, e, f"missing {k} in {e}")

    # ── Bounded list ────────────────────────────────────────────
    def test_events_capped_at_50(self):
        # Insert 60 PATH_VIOLATION rows. /code/surface/ should return
        # only the last 50 events.
        import server_llmwiki as srv
        conn = sqlite3.connect(srv._AUDIT_DB)
        for i in range(60):
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, user_role, endpoint, security_event, blocked) "
                "VALUES (?, 'external', 'tool:sandbox:PATH_VIOLATION', "
                "'PATH_VIOLATION', 1)",
                (f"2026-06-01T00:{i:02d}:00",),
            )
        conn.commit()
        conn.close()

        r = self._client().get(
            "/code/surface/",
            params={"api_key": self._api_key},
            headers=self._hdr("admin"),
        )
        body = r.json()
        # 4 from fixture + 60 added = 64; events trimmed to 50.
        self.assertEqual(body["total_events"], 64)
        self.assertEqual(len(body["events"]),  50)


class CodeSurfaceEmptyDbTests(unittest.TestCase):
    """Empty audit_log → zero rows, no crash."""

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
        conn = sqlite3.connect(self.db)
        conn.execute(_SCHEMA)
        conn.commit()
        conn.close()

    def tearDown(self):
        import server_llmwiki as srv
        srv._AUDIT_DB = self._saved_db
        Path(self.db).unlink(missing_ok=True)

    def test_empty_db_returns_zero_counts(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        from core.auth import create_token
        client = TestClient(srv.app)
        r = client.get(
            "/code/surface/",
            params={"api_key": self._api_key},
            headers={"Authorization": f"Bearer {create_token('a', 'admin')}"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total_events"], 0)
        self.assertEqual(body["events"], [])
        self.assertEqual(body["summary"]["sandbox_blocks"],    0)
        self.assertEqual(body["summary"]["path_violations"],   0)
        self.assertEqual(body["summary"]["surface_scans"],     0)
        self.assertEqual(body["summary"]["protected_blocks"],  0)


if __name__ == "__main__":
    unittest.main()
