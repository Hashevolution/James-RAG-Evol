"""Phase 2 PR-8 — tool router unit tests.

ARCHITECTURE.md §5.7.1 Tool Router. MVP is infrastructure-only (no
pipeline wiring); these tests pin the registry + dispatch + trace
emission + CR-E hook contract so a future planner / reflection-
driven caller can rely on them.

Coverage:
  * Tool dataclass + ToolResult dataclass shape
  * register_tool: rejects non-Tool / empty name / different instance
                   under same name; idempotent for same instance
  * get_tool: unknown → KeyError
  * dispatch_tool (read path): handler called, output returned, trace
                                row emitted, latency tracked
  * dispatch_tool (read path): handler raises → ToolResult.ok=False
                                + error row
  * dispatch_tool (unknown tool): ToolResult.ok=False, no handler call
  * dispatch_tool (write path): wraps as Change Request via
                                 core.change_request.create_cr;
                                 handler NOT called at dispatch time;
                                 CR id surfaces in result.cr_id +
                                 trace extras
  * dispatch_tool (write path): missing cr_target_type → error
  * Built-in: web_search registered automatically
  * Trace emit: stage="tool", applied_rule="reasoning.tool.<name>",
                extras carry tool name + (when CR) cr_id
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


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


def _rows(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM audit_log "
            "WHERE endpoint = 'reason:tool' ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()


class ToolDataclassTests(unittest.TestCase):

    def test_tool_fields(self):
        from core.reasoning.tool_router import Tool
        t = Tool(name="x", description="d", is_write=False,
                 handler=lambda a, **kw: "ok")
        self.assertEqual(t.name, "x")
        self.assertFalse(t.is_write)
        self.assertEqual(t.cr_target_type, "")

    def test_tool_result_default_shape(self):
        from core.reasoning.tool_router import ToolResult
        r = ToolResult(ok=True, tool_name="x")
        self.assertEqual(r.output, "")
        self.assertEqual(r.error, "")
        self.assertIsNone(r.cr_id)
        self.assertEqual(r.extras, {})


class RegistryTests(unittest.TestCase):

    def test_built_in_web_search_registered(self):
        from core.reasoning.tool_router import list_tools
        tools = list_tools()
        self.assertIn("web_search", tools)
        self.assertFalse(tools["web_search"].is_write)

    def test_register_rejects_non_tool(self):
        from core.reasoning.tool_router import register_tool
        with self.assertRaises(TypeError):
            register_tool("not-a-tool")   # type: ignore[arg-type]

    def test_register_rejects_empty_name(self):
        from core.reasoning.tool_router import Tool, register_tool
        with self.assertRaises(ValueError):
            register_tool(Tool(
                name="", description="x", is_write=False,
                handler=lambda a, **kw: "",
            ))

    def test_register_idempotent_same_instance(self):
        from core.reasoning.tool_router import Tool, register_tool, get_tool
        t = Tool(name="ping_test_idem",
                 description="x", is_write=False,
                 handler=lambda a, **kw: "")
        register_tool(t)
        register_tool(t)   # must not raise
        self.assertIs(get_tool("ping_test_idem"), t)

    def test_register_rejects_different_instance_same_name(self):
        from core.reasoning.tool_router import Tool, register_tool
        t1 = Tool(name="ping_test_collide", description="a",
                  is_write=False, handler=lambda a, **kw: "")
        t2 = Tool(name="ping_test_collide", description="b",
                  is_write=False, handler=lambda a, **kw: "")
        register_tool(t1)
        with self.assertRaises(ValueError):
            register_tool(t2)

    def test_get_tool_unknown_raises_keyerror(self):
        from core.reasoning.tool_router import get_tool
        with self.assertRaises(KeyError):
            get_tool("definitely_not_registered")


class DispatchReadTests(unittest.TestCase):
    """Read-path dispatch: handler executes, output returned, trace
    row emitted, errors converted to ToolResult.ok=False.
    """

    def _register_tool(self, *, handler, name="ut_read_tool"):
        from core.reasoning.tool_router import Tool, register_tool
        try:
            register_tool(Tool(name=name, description="ut",
                               is_write=False, handler=handler))
        except ValueError:
            # already registered from a prior test — refresh
            from core.reasoning.tool_router import _REGISTRY
            _REGISTRY[name] = Tool(name=name, description="ut",
                                    is_write=False, handler=handler)
        return name

    def test_happy_path_returns_output_and_emits_trace(self):
        from core.reasoning.tool_router import dispatch_tool
        called = {"n": 0, "role": ""}
        def h(args, *, user_role):
            called["n"] += 1
            called["role"] = user_role
            return f"hello {args.get('q', '')}"

        name = self._register_tool(handler=h)
        db = _fresh_db()
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            result = dispatch_tool(name, {"q": "world"},
                                   user_role="employee")
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "hello world")
        self.assertEqual(called["n"], 1)
        self.assertEqual(called["role"], "employee")

        rows = _rows(db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["endpoint"], "reason:tool")
        self.assertEqual(rows[0]["security_event"],
                         f"reasoning.tool.{name}")
        self.assertFalse(rows[0]["blocked"])

    def test_handler_raises_returns_error_result_and_emits_blocked(self):
        from core.reasoning.tool_router import dispatch_tool
        def h(args, *, user_role):
            raise RuntimeError("backend down")

        name = self._register_tool(handler=h,
                                    name="ut_read_tool_raises")
        db = _fresh_db()
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            result = dispatch_tool(name, {}, user_role="admin")
        self.assertFalse(result.ok)
        self.assertIn("RuntimeError", result.error)
        self.assertIn("backend down", result.error)
        rows = _rows(db)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])

    def test_unknown_tool_returns_error_result(self):
        from core.reasoning.tool_router import dispatch_tool
        db = _fresh_db()
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            result = dispatch_tool("not_registered", {})
        self.assertFalse(result.ok)
        self.assertIn("unknown tool", result.error)
        rows = _rows(db)
        # the unknown-tool path still emits one trace row for audit
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])


class DispatchWriteTests(unittest.TestCase):
    """Write-path dispatch: handler NOT executed, CR proposed via
    change_request.create_cr, cr_id surfaces in ToolResult.cr_id +
    trace extras. The handler being unused is the whole point —
    admin approves the CR, and admin-side apply runs the real handler.
    """

    def _register_write_tool(self, *, target_type="wiki_entity",
                               name="ut_write_tool"):
        from core.reasoning.tool_router import Tool, _REGISTRY
        handler = MagicMock(side_effect=AssertionError(
            "write tool handler must NOT execute at dispatch time"
        ))
        t = Tool(name=name, description="ut", is_write=True,
                 handler=handler, cr_target_type=target_type)
        _REGISTRY[name] = t   # bypass collision rejection between tests
        return name, handler

    def test_write_dispatch_creates_cr_does_not_call_handler(self):
        from core.reasoning.tool_router import dispatch_tool
        name, handler = self._register_write_tool()
        fake_cr = MagicMock()
        fake_cr.cr_id = "cr_test_001"

        with patch("core.change_request.create_cr",
                   return_value=fake_cr) as mock_create, \
             patch("core.change_request.compute_base_hash",
                   return_value="bh_abc"):
            result = dispatch_tool(
                name,
                {"target_id": "e_concept_x",
                 "proposed_diff": {"name": "new"},
                 "title": "rename"},
                user_role="admin", proposer="admin_user",
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.cr_id, "cr_test_001")
        handler.assert_not_called()
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["target_type"], "wiki_entity")
        self.assertEqual(kwargs["target_id"], "e_concept_x")
        self.assertEqual(kwargs["proposer"], "admin_user")

    def test_write_dispatch_missing_cr_target_type_errors(self):
        from core.reasoning.tool_router import Tool, dispatch_tool, _REGISTRY
        name = "ut_write_no_target"
        _REGISTRY[name] = Tool(
            name=name, description="ut", is_write=True,
            handler=lambda a, **kw: "should never run",
            cr_target_type="",   # ← missing
        )
        result = dispatch_tool(name, {}, user_role="admin")
        self.assertFalse(result.ok)
        self.assertIn("cr_target_type", result.error)

    def test_write_create_cr_raises_returns_error_result(self):
        from core.reasoning.tool_router import dispatch_tool
        name, _ = self._register_write_tool(name="ut_write_cr_raises")
        with patch("core.change_request.create_cr",
                   side_effect=ValueError("unknown target_type")), \
             patch("core.change_request.compute_base_hash",
                   return_value="bh"):
            result = dispatch_tool(
                name, {"target_id": "e1", "title": "t"},
                user_role="admin",
            )
        self.assertFalse(result.ok)
        self.assertIn("unknown target_type", result.error)

    def test_write_emits_trace_with_cr_id_in_extras(self):
        from core.reasoning.tool_router import dispatch_tool
        name, _ = self._register_write_tool(name="ut_write_trace_cr")
        fake_cr = MagicMock()
        fake_cr.cr_id = "cr_xyz"
        db = _fresh_db()
        with patch("core.change_request.create_cr", return_value=fake_cr), \
             patch("core.change_request.compute_base_hash",
                   return_value="bh"), \
             patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            dispatch_tool(
                name, {"target_id": "e1", "title": "t"},
                user_role="admin", proposer="admin_user",
            )
        rows = _rows(db)
        self.assertEqual(len(rows), 1)
        import json
        ans = json.loads(rows[0]["answer"])
        self.assertEqual(ans.get("cr_id"), "cr_xyz")
        self.assertEqual(ans.get("tool"), name)


class TraceExtrasTests(unittest.TestCase):

    def test_tool_name_in_trace_extras(self):
        from core.reasoning.tool_router import Tool, dispatch_tool, _REGISTRY
        name = "ut_trace_extras"
        _REGISTRY[name] = Tool(
            name=name, description="ut", is_write=False,
            handler=lambda a, **kw: "ok",
        )
        db = _fresh_db()
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            dispatch_tool(name, {}, user_role="employee")
        rows = _rows(db)
        import json
        ans = json.loads(rows[0]["answer"])
        self.assertEqual(ans.get("tool"), name)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
