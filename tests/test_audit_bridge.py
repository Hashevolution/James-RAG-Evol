"""Phase 1 — JSONL → SQLite audit mirroring.

Five existing JSONL writers now call ``mirror_to_audit_db`` after each
write so /admin/audit/list (DB-backed) can surface tool events. Tests
cover:

  1. Field mapping for each writer's actual dict shape.
  2. Defaults (missing time / role / event).
  3. Best-effort contract (bad inputs / bad DB path → False, no raise).
  4. End-to-end: trigger each writer, then confirm the SQLite table
     gained a row.
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

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


# audit_log schema lives in server_llmwiki; replicate here so tests
# don't depend on the server importing (much heavier).
_AUDIT_SCHEMA = """
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


def _fresh_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    conn = sqlite3.connect(f.name)
    conn.execute(_AUDIT_SCHEMA)
    conn.commit()
    conn.close()
    return f.name


def _rows(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM audit_log ORDER BY id ASC"
        ).fetchall()]
    finally:
        conn.close()


class MirrorRouterEntryTests(unittest.TestCase):
    """tools/router._log_tool_event dict shape."""

    def setUp(self):
        self.db = _fresh_db()

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def _router_entry(self, **overrides):
        e = {
            "time":            "2026-05-11T10:00:00",
            "event":           "TOOL_EXECUTED",
            "tool_used":       "read_file",
            "target_file":     "workspace/foo.py",
            "role":            "admin",
            "blocked":         False,
            "protected_block": False,
            "admin_override":  False,
            "sandbox_block":   False,
            "cap_denied":      False,
            "cap_token_id":    "tok-abc",
            "cap_action":      "fs.read",
            "exec_time_sec":   0.012,
            "layer":           "router",
        }
        e.update(overrides)
        return e

    def test_inserts_with_full_field_mapping(self):
        from core.audit_bridge import mirror_to_audit_db
        ok = mirror_to_audit_db(self._router_entry(), db_path=self.db)
        self.assertTrue(ok)
        rows = _rows(self.db)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["timestamp"],      "2026-05-11T10:00:00")
        self.assertEqual(r["user_role"],      "admin")
        self.assertEqual(r["endpoint"],       "tool:router:TOOL_EXECUTED")
        self.assertEqual(r["query"],          "read_file: workspace/foo.py")
        self.assertEqual(r["security_event"], "TOOL_EXECUTED")
        self.assertEqual(r["blocked"],        0)
        self.assertAlmostEqual(r["elapsed_sec"], 0.012)
        self.assertIsNone(r["ip_address"])
        # cap_token_id + cap_action survive in answer JSON.
        ans = json.loads(r["answer"])
        self.assertEqual(ans["cap_token_id"], "tok-abc")
        self.assertEqual(ans["cap_action"],   "fs.read")

    def test_blocked_truthy_maps_to_one(self):
        from core.audit_bridge import mirror_to_audit_db
        mirror_to_audit_db(self._router_entry(blocked=True), db_path=self.db)
        self.assertEqual(_rows(self.db)[0]["blocked"], 1)

    def test_admin_override_packed_into_answer(self):
        from core.audit_bridge import mirror_to_audit_db
        mirror_to_audit_db(
            self._router_entry(admin_override=True, protected_block=True),
            db_path=self.db,
        )
        ans = json.loads(_rows(self.db)[0]["answer"])
        self.assertTrue(ans["admin_override"])
        self.assertTrue(ans["protected_block"])


class MirrorSandboxEntryTests(unittest.TestCase):
    """tools/code/sandbox.log_security_event dict shape."""

    def setUp(self):
        self.db = _fresh_db()

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_sandbox_entry_inserts(self):
        from core.audit_bridge import mirror_to_audit_db
        entry = {
            "time":           "2026-05-11T11:00:00",
            "event":          "SANDBOX_BLOCK",
            "detail":         "../escape attempt",
            "blocked":        True,
            "role":           "external",
            "admin_override": False,
            "layer":          "sandbox",
        }
        ok = mirror_to_audit_db(entry, db_path=self.db)
        self.assertTrue(ok)
        r = _rows(self.db)[0]
        self.assertEqual(r["endpoint"],       "tool:sandbox:SANDBOX_BLOCK")
        self.assertEqual(r["user_role"],      "external")
        self.assertEqual(r["blocked"],        1)
        self.assertEqual(r["security_event"], "SANDBOX_BLOCK")
        ans = json.loads(r["answer"])
        self.assertEqual(ans["detail"], "../escape attempt")


class MirrorCodeReaderEntryTests(unittest.TestCase):
    """tools/code/code_reader._log_read — no ``role`` field."""

    def setUp(self):
        self.db = _fresh_db()

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_missing_role_defaults_to_unknown(self):
        from core.audit_bridge import mirror_to_audit_db
        entry = {
            "time":    "2026-05-11T12:00:00",
            "event":   "FILE_READ",
            "path":    "workspace/foo.py",
            "lines":   42,
            "success": True,
            "layer":   "code_reader",
        }
        mirror_to_audit_db(entry, db_path=self.db)
        r = _rows(self.db)[0]
        self.assertEqual(r["user_role"], "unknown")
        # ``path`` becomes the query field when tool_used is absent.
        self.assertEqual(r["query"],     "workspace/foo.py")
        self.assertEqual(r["endpoint"],  "tool:code_reader:FILE_READ")
        # lines + success not reserved — packed into answer.
        ans = json.loads(r["answer"])
        self.assertEqual(ans["lines"], 42)
        self.assertTrue(ans["success"])


class MirrorCodeAnalyzerEntryTests(unittest.TestCase):
    """tools/code/code_analyzer._log_analysis — has tool_used + elapsed_sec."""

    def setUp(self):
        self.db = _fresh_db()

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_elapsed_sec_field_recognised(self):
        from core.audit_bridge import mirror_to_audit_db
        entry = {
            "time":          "2026-05-11T13:00:00",
            "event":         "CODE_ANALYSIS",
            "tool_used":     "code_analyzer",
            "path":          "workspace/foo.py",
            "analysis_type": "ast",
            "elapsed_sec":   0.250,
            "success":       True,
            "layer":         "tool",
        }
        mirror_to_audit_db(entry, db_path=self.db)
        r = _rows(self.db)[0]
        self.assertAlmostEqual(r["elapsed_sec"], 0.250)
        self.assertEqual(r["query"], "code_analyzer: workspace/foo.py")
        ans = json.loads(r["answer"])
        self.assertEqual(ans["analysis_type"], "ast")


class MirrorCodeEditorEntryTests(unittest.TestCase):
    """tools/code/code_editor._log_edit — operation + detail fields."""

    def setUp(self):
        self.db = _fresh_db()

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_editor_entry_packs_operation_into_answer(self):
        from core.audit_bridge import mirror_to_audit_db
        entry = {
            "time":      "2026-05-11T14:00:00",
            "event":     "CODE_EDIT",
            "tool_used": "code_editor",
            "path":      "workspace/foo.py",
            "operation": "patch_apply",
            "success":   True,
            "detail":    "applied 3 hunks",
            "layer":     "tool",
        }
        mirror_to_audit_db(entry, db_path=self.db)
        r = _rows(self.db)[0]
        self.assertEqual(r["security_event"], "CODE_EDIT")
        ans = json.loads(r["answer"])
        self.assertEqual(ans["operation"], "patch_apply")
        self.assertEqual(ans["detail"],    "applied 3 hunks")


class BestEffortContractTests(unittest.TestCase):
    """The bridge must never raise — audit mirroring sits in the hot path."""

    def setUp(self):
        self.db = _fresh_db()

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_non_dict_returns_false(self):
        from core.audit_bridge import mirror_to_audit_db
        for bad in (None, "string", 42, [1, 2], object()):
            self.assertFalse(mirror_to_audit_db(bad, db_path=self.db))
        self.assertEqual(len(_rows(self.db)), 0)

    def test_bad_db_path_returns_false_does_not_raise(self):
        from core.audit_bridge import mirror_to_audit_db
        ok = mirror_to_audit_db(
            {"event": "X", "role": "admin"},
            db_path="/nonexistent/dir/" + os.urandom(8).hex() + ".db",
        )
        self.assertFalse(ok)

    def test_missing_time_uses_now(self):
        from core.audit_bridge import mirror_to_audit_db
        ok = mirror_to_audit_db(
            {"event": "TEST", "role": "admin", "layer": "test"},
            db_path=self.db,
        )
        self.assertTrue(ok)
        # timestamp NOT NULL, so insert succeeded → bridge filled it.
        r = _rows(self.db)[0]
        self.assertTrue(r["timestamp"])

    def test_missing_event_falls_back(self):
        from core.audit_bridge import mirror_to_audit_db
        ok = mirror_to_audit_db(
            {"role": "admin", "layer": "x"},
            db_path=self.db,
        )
        self.assertTrue(ok)
        self.assertEqual(_rows(self.db)[0]["endpoint"], "tool:x:EVENT")

    def test_empty_extras_no_answer(self):
        from core.audit_bridge import mirror_to_audit_db
        mirror_to_audit_db(
            {"event": "X", "role": "admin", "layer": "y", "time": "t"},
            db_path=self.db,
        )
        self.assertIsNone(_rows(self.db)[0]["answer"])


class EndpointPrefixContractTests(unittest.TestCase):
    """Phase 3 will add a category 'tools' filtering ``endpoint LIKE 'tool:%'``.
    Lock that prefix in so a future writer rename doesn't break the
    category boundary silently."""

    def setUp(self):
        self.db = _fresh_db()

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_all_writer_layers_produce_tool_prefix(self):
        from core.audit_bridge import mirror_to_audit_db
        for layer in ("router", "sandbox", "code_reader", "tool"):
            mirror_to_audit_db(
                {"event": "E", "role": "admin", "layer": layer, "time": "t"},
                db_path=self.db,
            )
        for r in _rows(self.db):
            self.assertTrue(r["endpoint"].startswith("tool:"),
                            f"endpoint={r['endpoint']} not prefixed")


if __name__ == "__main__":
    unittest.main()
