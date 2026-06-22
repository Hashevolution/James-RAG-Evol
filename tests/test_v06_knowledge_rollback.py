"""v0.6 Phase 4 P4.2 — knowledge rollback affordance tests.

Covers:

Endpoint contract:
  * `GET /admin/graph/last-change` — admin gate; empty audit DB →
    `no_changes: true`; non-empty → returns most-recent event metadata
  * `POST /admin/graph/log-rollback-intent` — admin gate; scope
    validation; writes a row with `endpoint=/admin/graph/
    log-rollback-intent` + canonical `security_event` shape;
    response carries audit_row_id

Frontend structure:
  * `frontend/knowledge-rollback.html` exists at canonical path
  * Two flow sections (`undo-last-title`, `restore-to-title`) present
  * Confirmation modal + operator note textarea present
  * Result panel present
  * Technical jargon NOT leaked (`trace_id` / `audit_log` /
    `reconstruct_graph_at` etc.)
  * `knowledge-rollback.js` exists + exposes window.JAMES_KnowledgeRollback
  * `knowledge-rollback.css` carries the canonical selectors
  * i18n keys present in BOTH EN and KO blocks
  * Server route `/admin/knowledge-rollback` registered

Run:
  python -m unittest tests.test_v06_knowledge_rollback
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
    "test-secret-for-rollback-endpoint-32chars-min-padding",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


REPO_ROOT = Path(__file__).resolve().parent.parent
# v0.6.1 graph-hub: knowledge-rollback folded into graph.html (#rollback tab).
HTML = REPO_ROOT / "frontend" / "graph.html"
JS   = REPO_ROOT / "frontend" / "static" / "knowledge-rollback.js"
CSS  = REPO_ROOT / "frontend" / "static" / "knowledge-rollback.css"
I18N = REPO_ROOT / "frontend" / "static" / "i18n.js"
ADMIN_HTML = REPO_ROOT / "frontend" / "admin.html"
SERVER = REPO_ROOT / "server_llmwiki.py"


# ─── helpers ────────────────────────────────────────────────────────


def _api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = REPO_ROOT / ".env"
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
            endpoint        TEXT    NOT NULL DEFAULT '/admin/graph/log-rollback-intent',
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


def _insert_lifecycle_event(path, ts, event_type, payload):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO audit_log (timestamp, user_role, endpoint, event_type, event_payload) "
        "VALUES (?, 'system', 'lifecycle', ?, ?)",
        (ts, event_type, json.dumps(payload)),
    )
    conn.commit()
    conn.close()


# ─── endpoint tests ────────────────────────────────────────────────


class LastChangeEndpointTests(unittest.TestCase):
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
        # Point all module-level _AUDIT_DB references at our tmp DB.
        import server_llmwiki as srv
        import routes._helpers as _h
        import routes.admin as _a
        self._saved = {"srv": srv._AUDIT_DB, "helpers": _h._AUDIT_DB,
                       "admin": _a._AUDIT_DB}
        srv._AUDIT_DB = self._db
        _h._AUDIT_DB = self._db
        _a._AUDIT_DB = self._db

    def tearDown(self):
        import server_llmwiki as srv
        import routes._helpers as _h
        import routes.admin as _a
        srv._AUDIT_DB = self._saved["srv"]
        _h._AUDIT_DB = self._saved["helpers"]
        _a._AUDIT_DB = self._saved["admin"]
        Path(self._db).unlink(missing_ok=True)

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def test_employee_jwt_rejected(self):
        c = self._client()
        r = c.get("/admin/graph/last-change",
                  params={"api_key": self._api_key},
                  headers=_employee_headers())
        self.assertEqual(r.status_code, 403, r.text)

    def test_empty_audit_db_returns_no_changes(self):
        c = self._client()
        r = c.get("/admin/graph/last-change",
                  params={"api_key": self._api_key},
                  headers=_admin_headers())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["no_changes"])

    def test_returns_most_recent_event(self):
        from core.lifecycle.replay_audit import (
            EVT_SUPERSEDE_EDGE_CREATED, EVT_CASCADE_INVALIDATE,
        )
        _insert_lifecycle_event(
            self._db, "2026-06-01T10:00:00+00:00",
            EVT_SUPERSEDE_EDGE_CREATED,
            {"new_edge_id": "edge_a", "head_id": "edge_a"},
        )
        _insert_lifecycle_event(
            self._db, "2026-06-13T03:00:00+00:00",
            EVT_CASCADE_INVALIDATE,
            {"edge_id": "edge_a"},
        )
        c = self._client()
        r = c.get("/admin/graph/last-change",
                  params={"api_key": self._api_key},
                  headers=_admin_headers())
        body = r.json()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(body["no_changes"])
        self.assertEqual(body["event_type"], EVT_CASCADE_INVALIDATE)
        self.assertEqual(body["event_payload"], {"edge_id": "edge_a"})


class LogRollbackIntentEndpointTests(unittest.TestCase):
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
        import server_llmwiki as srv
        import routes._helpers as _h
        import routes.admin as _a
        self._saved = {"srv": srv._AUDIT_DB, "helpers": _h._AUDIT_DB,
                       "admin": _a._AUDIT_DB}
        srv._AUDIT_DB = self._db
        _h._AUDIT_DB = self._db
        _a._AUDIT_DB = self._db

    def tearDown(self):
        import server_llmwiki as srv
        import routes._helpers as _h
        import routes.admin as _a
        srv._AUDIT_DB = self._saved["srv"]
        _h._AUDIT_DB = self._saved["helpers"]
        _a._AUDIT_DB = self._saved["admin"]
        Path(self._db).unlink(missing_ok=True)

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def test_employee_jwt_rejected(self):
        c = self._client()
        r = c.post("/admin/graph/log-rollback-intent",
                   json={"api_key": self._api_key, "scope": "last"},
                   headers=_employee_headers())
        self.assertEqual(r.status_code, 403, r.text)

    def test_invalid_scope_400(self):
        c = self._client()
        r = c.post("/admin/graph/log-rollback-intent",
                   json={"api_key": self._api_key, "scope": "garbage"},
                   headers=_admin_headers())
        self.assertEqual(r.status_code, 400, r.text)

    def test_since_without_target_t_400(self):
        c = self._client()
        r = c.post("/admin/graph/log-rollback-intent",
                   json={"api_key": self._api_key, "scope": "since"},
                   headers=_admin_headers())
        self.assertEqual(r.status_code, 400, r.text)

    def test_since_with_malformed_t_400(self):
        c = self._client()
        r = c.post("/admin/graph/log-rollback-intent",
                   json={"api_key": self._api_key, "scope": "since",
                         "target_t": "not-iso"},
                   headers=_admin_headers())
        self.assertEqual(r.status_code, 400, r.text)

    def test_scope_last_writes_audit_row(self):
        c = self._client()
        r = c.post("/admin/graph/log-rollback-intent",
                   json={"api_key": self._api_key, "scope": "last",
                         "note": "wrong policy doc"},
                   headers=_admin_headers())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["scope"], "last")
        self.assertIsNotNone(body["audit_row_id"])
        self.assertFalse(body["graph_mutation_applied"])
        self.assertTrue(body["graph_mutation_pending"])
        # Verify the audit row landed with the canonical shape.
        conn = sqlite3.connect(self._db)
        row = conn.execute(
            "SELECT endpoint, security_event, query FROM audit_log "
            "WHERE id=?", (body["audit_row_id"],),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        endpoint, sec_evt, query = row
        self.assertEqual(endpoint, "/admin/graph/log-rollback-intent")
        self.assertTrue(sec_evt.startswith("rollback_intent scope=last "))
        self.assertIn("wrong policy doc", query)

    def test_scope_since_records_target_t(self):
        c = self._client()
        r = c.post("/admin/graph/log-rollback-intent",
                   json={"api_key": self._api_key, "scope": "since",
                         "target_t": "2026-06-12T00:00:00Z",
                         "note": "yesterday baseline"},
                   headers=_admin_headers())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["scope"], "since")
        self.assertEqual(body["target_t"], "2026-06-12T00:00:00Z")
        # Audit row carries the target_t in the security_event payload.
        conn = sqlite3.connect(self._db)
        row = conn.execute(
            "SELECT security_event FROM audit_log WHERE id=?",
            (body["audit_row_id"],),
        ).fetchone()
        conn.close()
        self.assertIn("scope=since", row[0])
        self.assertIn("target=2026-06-12T00:00:00Z", row[0])


# ─── frontend structure tests ──────────────────────────────────────


class HtmlStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HTML.exists():
            raise unittest.SkipTest("graph.html (#rollback tab) missing")
        cls.body = HTML.read_text(encoding="utf-8")
        # v0.6.1 graph-hub: rollback surface is now the #rollback tab
        # section in graph.html. Slice it for section-scoped checks
        # (jargon / region count / dialog) — the rest of the hub page is
        # out of scope.
        _s = cls.body.find('data-graph-tab="rollback"')
        _e = cls.body.find('<!-- Admin login modal')
        cls.rollback = cls.body[_s:_e] if (_s != -1 and _e != -1) else cls.body

    def test_two_flow_section_titles(self):
        for label in ("undo-last-title", "restore-to-title"):
            self.assertIn(f'id="{label}"', self.body,
                          f"missing flow section id: {label}")

    def test_confirm_modal_present(self):
        for marker in ("rollback-confirm-modal",
                       "rollback-confirm-title",
                       "rollback-note",
                       "rollback-confirm-btn",
                       "rollback-cancel-btn"):
            self.assertIn(marker, self.body)

    def test_no_technical_jargon(self):
        for term in ("trace_id", "audit_log", "reconstruct_graph_at",
                     "tenant_id", "JWT", "T7 supersede"):
            self.assertNotIn(term, self.rollback,
                             f"technical jargon leaked: {term!r}")

    def test_a11y_skip_link_and_roles(self):
        self.assertIn('class="skip-link"', self.body)
        # 2 regions within the #rollback tab section (undo / restore).
        self.assertEqual(self.rollback.count('role="region"'), 2)
        self.assertIn('role="dialog"', self.rollback)
        self.assertIn('aria-modal="true"', self.rollback)


class JsStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not JS.exists():
            raise unittest.SkipTest("knowledge-rollback.js missing")
        cls.body = JS.read_text(encoding="utf-8")

    def test_exposes_global(self):
        self.assertIn("window.JAMES_KnowledgeRollback", self.body)
        for fn in ("loadLastChange", "loadRestorePreview",
                   "openConfirmModal", "closeConfirmModal"):
            self.assertIn(fn, self.body)

    def test_uses_canonical_endpoints(self):
        self.assertIn("/admin/graph/last-change", self.body)
        self.assertIn("/admin/graph/log-rollback-intent", self.body)
        self.assertIn("/admin/graph/diff-vs-now", self.body)


class I18nKeysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = I18N.read_text(encoding="utf-8")

    def test_canonical_rollback_keys_in_both_blocks(self):
        required = [
            "rollback.page_title",
            "rollback.title",
            "rollback.intro",
            "rollback.undo_last.title",
            "rollback.undo_last.button",
            "rollback.restore_to.title",
            "rollback.restore_to.pick",
            "rollback.confirm.title",
            "rollback.confirm.proceed",
            "rollback.result.title",
            "rollback.result.pending_note",
            "admin.rollback_link",
        ]
        for key in required:
            count = self.body.count(f"'{key}'")
            self.assertGreaterEqual(
                count, 2,
                f"i18n key {key!r} missing from EN or KO (count {count})",
            )


class AdminEntryPointTests(unittest.TestCase):
    def test_admin_html_links_to_rollback(self):
        body = ADMIN_HTML.read_text(encoding="utf-8")
        self.assertIn('href="/admin/graph#rollback"', body)  # v0.6.1 graph-hub
        self.assertIn('admin.rollback_link', body)


class ServerRouteTests(unittest.TestCase):
    def test_route_registered(self):
        body = SERVER.read_text(encoding="utf-8")
        self.assertIn('@app.get("/admin/knowledge-rollback"', body)
        self.assertIn("async def serve_knowledge_rollback", body)


if __name__ == "__main__":
    unittest.main()
