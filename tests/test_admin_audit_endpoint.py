"""W4 P6 — /admin/audit/list endpoint.

Coverage:
  - Admin gate (employee JWT → 403).
  - Category filter maps to endpoint-prefix subsets correctly.
  - Free-text q filter matches both `query` and `security_event`.
  - Pagination: limit cap, offset, total separate from items.
  - Unknown category collapses to "all" rather than 4xx.
  - Empty audit_log returns total=0 cleanly (no crash).
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
    "test-secret-for-audit-endpoint-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _seed_audit_db(path: str, rows: list[dict]) -> None:
    """Build an audit_log table with the columns server_llmwiki uses
    and insert the rows the test wants to see in the response."""
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
            "security_event, ip_address, blocked) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (r["timestamp"], r["user_role"], r["endpoint"],
             r.get("query"), r.get("security_event"),
             r.get("ip_address"), int(r.get("blocked", 0))),
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


class AuditListEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")
        # Replace the audit DB the module reads. `_AUDIT_DB` is captured
        # at import time as a module-level constant — patch all the
        # downstream bindings (server + routes/_helpers + routes/admin)
        # since the v0.4.x server-split moved /admin/audit/list to
        # routes/admin.py with its own snapshot.
        import server_llmwiki as srv
        import routes._helpers as _h
        import routes.admin as _a
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        self._saved = {
            "srv":     srv._AUDIT_DB,
            "helpers": _h._AUDIT_DB,
            "admin":   _a._AUDIT_DB,
        }
        srv._AUDIT_DB = self.db
        _h._AUDIT_DB = self.db
        _a._AUDIT_DB = self.db
        _seed_audit_db(self.db, self._fixture())

    def tearDown(self):
        import server_llmwiki as srv
        import routes._helpers as _h
        import routes.admin as _a
        srv._AUDIT_DB = self._saved["srv"]
        _h._AUDIT_DB = self._saved["helpers"]
        _a._AUDIT_DB = self._saved["admin"]
        Path(self.db).unlink(missing_ok=True)

    def _fixture(self) -> list[dict]:
        # 13 rows covering every category, plus a near-duplicate to
        # exercise the q substring filter. Phase 3 added 5 rows for
        # the new tools / attack / system endpoint prefixes.
        return [
            {"timestamp": "2026-05-11T01:00:00", "user_role": "admin",
             "endpoint": "/admin/users/approve", "query": "alice",
             "security_event": "approved role=manager", "ip_address": "127.0.0.1"},
            {"timestamp": "2026-05-11T01:01:00", "user_role": "admin",
             "endpoint": "/admin/users/reject",  "query": "carol",
             "security_event": "rejected (row deleted)"},
            {"timestamp": "2026-05-11T01:02:00", "user_role": "anonymous",
             "endpoint": "/signup/",             "query": "alice",
             "security_event": "signup_pending"},
            {"timestamp": "2026-05-11T01:03:00", "user_role": "anonymous",
             "endpoint": "/password/reset/confirm", "query": "alice",
             "security_event": "password_reset_completed"},
            {"timestamp": "2026-05-11T01:04:00", "user_role": "authenticated",
             "endpoint": "/api-keys/issue",      "query": "alice",
             "security_event": "api_key_issued prefix=jms_aaaaaaaa"},
            {"timestamp": "2026-05-11T01:05:00", "user_role": "authenticated",
             "endpoint": "/api-keys/revoke",     "query": "alice",
             "security_event": "api_key_revoked prefix=jms_aaaaaaaa"},
            {"timestamp": "2026-05-11T01:06:00", "user_role": "unknown",
             "endpoint": "/login/",              "query": "alice",
             "security_event": "login_failed"},
            {"timestamp": "2026-05-11T01:07:00", "user_role": "admin",
             "endpoint": "/query/",              "query": "what is X",
             "security_event": ""},
            # Phase 1 mirror — tool stream
            {"timestamp": "2026-05-11T01:08:00", "user_role": "admin",
             "endpoint": "tool:router:TOOL_EXECUTED",
             "query": "read_file: workspace/foo.py",
             "security_event": "TOOL_EXECUTED"},
            {"timestamp": "2026-05-11T01:09:00", "user_role": "external",
             "endpoint": "tool:sandbox:SANDBOX_BLOCK",
             "query": "../escape",
             "security_event": "SANDBOX_BLOCK", "blocked": 1},
            # Phase 2 mirror — attack stream
            {"timestamp": "2026-05-11T01:10:00", "user_role": "external",
             "endpoint": "attack:injection",
             "query": "ignore previous",
             "security_event": "injection", "blocked": 1},
            # Phase 2 mirror — system stream
            {"timestamp": "2026-05-11T01:11:00", "user_role": "system",
             "endpoint": "system:ERROR:orchestrator.startup",
             "query": "",
             "security_event": "orchestrator.startup"},
            {"timestamp": "2026-05-11T01:12:00", "user_role": "system",
             "endpoint": "system:INFO:llm_router.fallback",
             "query": "",
             "security_event": "llm_router.fallback"},
        ]

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _admin_hdr(self) -> dict:
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token('test-admin', 'admin')}"}

    def _user_hdr(self) -> dict:
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token('test-employee', 'employee')}"}

    # ── admin gate ──────────────────────────────────────────────
    def test_employee_jwt_rejected(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key},
            headers=self._user_hdr(),
        )
        self.assertEqual(r.status_code, 403)

    # ── default = all ───────────────────────────────────────────
    def test_default_returns_all_rows(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["category"], "all")
        self.assertEqual(body["total"], 13)
        # Default sort: id DESC. Newest fixture row is system:INFO:...
        self.assertEqual(body["items"][0]["endpoint"],
                         "system:INFO:llm_router.fallback")

    # ── category filters ────────────────────────────────────────
    def test_category_user_mgmt(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "category": "user_mgmt"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        endpoints = [it["endpoint"] for it in body["items"]]
        self.assertTrue(all(e.startswith("/admin/users/") for e in endpoints),
                        f"unexpected endpoint in user_mgmt: {endpoints}")
        self.assertEqual(body["total"], 2)

    def test_category_password_includes_signup(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "category": "password"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        endpoints = {it["endpoint"] for it in body["items"]}
        self.assertEqual(endpoints,
                         {"/signup/", "/password/reset/confirm"})
        self.assertEqual(body["total"], 2)

    def test_category_api_keys(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "category": "api_keys"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        self.assertEqual(body["total"], 2)
        for it in body["items"]:
            self.assertTrue(it["endpoint"].startswith("/api-keys/"))

    def test_category_auth(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "category": "auth"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["endpoint"], "/login/")

    def test_unknown_category_collapses_to_all(self):
        # UI typo or older client shouldn't 400 — collapse silently.
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "category": "garbage"},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["category"], "all")

    # ── q substring filter ──────────────────────────────────────
    def test_q_matches_query_field(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "q": "carol"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["query"], "carol")

    def test_q_matches_security_event_field(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "q": "jms_aaaaaaaa"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        # 2 rows mention the prefix (issue + revoke).
        self.assertEqual(body["total"], 2)

    def test_q_combined_with_category(self):
        # category narrows to api_keys (2 rows), q filters to one.
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key,
                    "category": "api_keys", "q": "revoke"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["endpoint"], "/api-keys/revoke")

    # ── pagination ──────────────────────────────────────────────
    def test_limit_cap(self):
        # Server caps at 500. We just want to confirm the cap doesn't
        # crash on a comically large value.
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "limit": 100000},
            headers=self._admin_hdr(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["limit"], 500)

    def test_offset_skips_rows_total_unaffected(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key,
                    "limit": 2, "offset": 5},
            headers=self._admin_hdr(),
        )
        body = r.json()
        self.assertEqual(body["total"], 13)
        self.assertEqual(len(body["items"]), 2)

    # ── Phase 3 categories: tools / attack / system ─────────────
    def test_category_tools(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "category": "tools"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        # Two fixture rows: tool:router:... and tool:sandbox:...
        self.assertEqual(body["total"], 2)
        for it in body["items"]:
            self.assertTrue(it["endpoint"].startswith("tool:"),
                            f"unexpected endpoint: {it['endpoint']}")

    def test_category_attack(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "category": "attack"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["endpoint"], "attack:injection")
        # Attack rows are blocked.
        self.assertTrue(body["items"][0]["blocked"])

    def test_category_system(self):
        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key, "category": "system"},
            headers=self._admin_hdr(),
        )
        body = r.json()
        # Two fixture rows: system:ERROR:... and system:INFO:...
        self.assertEqual(body["total"], 2)
        for it in body["items"]:
            self.assertTrue(it["endpoint"].startswith("system:"),
                            f"unexpected endpoint: {it['endpoint']}")

    def test_query_field_truncated_to_120(self):
        # Insert a long query and verify the trim.
        import server_llmwiki as srv
        long_q = "x" * 500
        conn = sqlite3.connect(srv._AUDIT_DB)
        conn.execute(
            "INSERT INTO audit_log (timestamp, user_role, endpoint, query) "
            "VALUES ('2026-05-12T00:00:00', 'admin', '/admin/users/approve', ?)",
            (long_q,),
        )
        conn.commit()
        conn.close()

        r = self._client().get(
            "/admin/audit/list",
            params={"api_key": self._api_key,
                    "category": "user_mgmt", "q": "x" * 100},
            headers=self._admin_hdr(),
        )
        item = r.json()["items"][0]
        self.assertLessEqual(len(item["query"]), 120)


if __name__ == "__main__":
    unittest.main()
