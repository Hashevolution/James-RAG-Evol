"""Router capability-token integration tests (#44 phase 3-2).

Coverage:
  - execute_tool denies non-admin attempts at fs.write actions before any
    other gate runs (CAPABILITY_DENIED is the failure mode).
  - employee can invoke fs.read tools (read_file) — relaxed in phase 3-2.
  - external is blocked from fs.read (employee+ required).
  - admin shell.exec issuance is allowed; non-admin denied.
  - capability token_id appears in the audit-log entry on success.
  - unknown tool name falls through to "tool.invoke" (admin-only) — fail-closed.

Run:
  python -m unittest tests.test_router_capability
  python tests/test_router_capability.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeTool:
    """Minimal stand-in for BaseTool — bypasses registry to keep
    these tests independent of which real tools are installed."""

    def __init__(self, name: str, authorize_ok: bool = True):
        self.name = name
        self._authorize_ok = authorize_ok

    def authorize(self, context: dict) -> bool:
        return self._authorize_ok

    def execute(self, input_data: dict) -> dict:
        return {"success": True, "result": "ok", "tool_used": self.name}


def _patch_audit_log():
    """Redirect router audit log to a tempfile for the duration of a test.

    Returns (patcher, log_path). The caller is responsible for stopping
    the patcher and reading log_path.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8",
    )
    tmp.close()
    import tools.router as router_mod
    patcher = mock.patch.object(router_mod, "AUDIT_LOG_PATH", tmp.name)
    patcher.start()
    return patcher, tmp.name


def _read_log(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class RouterCapabilityGateTests(unittest.TestCase):
    def setUp(self):
        self.patcher, self.log_path = _patch_audit_log()
        # Router prints emoji-laden status lines; on Windows cp949 stdout
        # this raises UnicodeEncodeError under unittest. Redirect to a
        # StringIO for the duration of each test — the audit log on disk
        # is what we actually assert against.
        self._stdout_ctx = redirect_stdout(io.StringIO())
        self._stdout_ctx.__enter__()
        # Inject fake tools so the test does not rely on the real registry.
        from tools import registry as reg
        self._saved_tools = dict(reg.TOOLS)
        reg.TOOLS["read_file"]    = _FakeTool("read_file")
        reg.TOOLS["code_editor"]  = _FakeTool("code_editor")
        reg.TOOLS["mystery_tool"] = _FakeTool("mystery_tool")

    def tearDown(self):
        from tools import registry as reg
        reg.TOOLS.clear()
        reg.TOOLS.update(self._saved_tools)
        self._stdout_ctx.__exit__(None, None, None)
        self.patcher.stop()
        try:
            os.unlink(self.log_path)
        except OSError:
            pass

    # ─── fs.read (relaxed to employee+) ───────────────────────────

    def test_employee_can_invoke_read_file(self):
        from tools.router import execute_tool
        result = execute_tool(
            {"name": "read_file", "input": {"path": "./workspace/x.py"}},
            {"user_role": "employee"},
        )
        self.assertTrue(result["success"], msg=result)

    def test_external_blocked_from_read_file(self):
        from tools.router import execute_tool
        result = execute_tool(
            {"name": "read_file", "input": {"path": "./workspace/x.py"}},
            {"user_role": "external"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "CAPABILITY_DENIED")

    def test_unknown_role_blocked(self):
        from tools.router import execute_tool
        result = execute_tool(
            {"name": "read_file", "input": {"path": "./workspace/x.py"}},
            {"user_role": "guest_attacker"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "CAPABILITY_DENIED")

    # ─── fs.write (admin only) ────────────────────────────────────

    def test_employee_blocked_from_code_editor(self):
        from tools.router import execute_tool
        result = execute_tool(
            {"name": "code_editor", "input": {"path": "./workspace/x.py"}},
            {"user_role": "employee"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "CAPABILITY_DENIED")

    def test_admin_can_invoke_code_editor(self):
        from tools.router import execute_tool
        result = execute_tool(
            {"name": "code_editor", "input": {"path": "./workspace/x.py"}},
            {"user_role": "admin"},
        )
        self.assertTrue(result["success"], msg=result)

    # ─── unknown tool falls through to tool.invoke (admin-only) ───

    def test_unknown_tool_admin_only(self):
        from tools.router import execute_tool
        # employee → blocked at capability gate (tool.invoke is admin-only)
        r1 = execute_tool(
            {"name": "mystery_tool", "input": {"path": ""}},
            {"user_role": "employee"},
        )
        self.assertFalse(r1["success"])
        self.assertEqual(r1["error"], "CAPABILITY_DENIED")
        # admin → passes capability gate (and reaches the fake tool)
        r2 = execute_tool(
            {"name": "mystery_tool", "input": {"path": ""}},
            {"user_role": "admin"},
        )
        self.assertTrue(r2["success"], msg=r2)

    # ─── audit log ────────────────────────────────────────────────

    def test_token_id_in_audit_on_success(self):
        from tools.router import execute_tool
        execute_tool(
            {"name": "read_file", "input": {"path": "./workspace/x.py"}},
            {"user_role": "admin"},
        )
        entries = _read_log(self.log_path)
        executed = [e for e in entries if e["event"] == "TOOL_EXECUTED"]
        self.assertTrue(executed, msg=f"no TOOL_EXECUTED in {entries}")
        e = executed[-1]
        self.assertEqual(e["cap_action"], "fs.read")
        self.assertIsNotNone(e["cap_token_id"])
        self.assertEqual(len(e["cap_token_id"]), 32)   # uuid4 hex

    def test_capability_denied_event_on_block(self):
        from tools.router import execute_tool
        execute_tool(
            {"name": "code_editor", "input": {"path": "./workspace/x.py"}},
            {"user_role": "employee"},
        )
        entries = _read_log(self.log_path)
        denied = [e for e in entries if e["event"] == "CAPABILITY_DENIED"]
        self.assertTrue(denied, msg=f"no CAPABILITY_DENIED in {entries}")
        self.assertTrue(denied[0]["cap_denied"])
        self.assertTrue(denied[0]["blocked"])
        self.assertEqual(denied[0]["cap_action"], "fs.write")

    # ─── ordering: capability check happens before authorize ──────

    def test_capability_blocks_before_tool_authorize(self):
        """Even a tool that would authorize() True must not run when
        the role lacks the capability — capability is the outer gate."""
        from tools import registry as reg
        # Tool that would say 'yes' to anyone, but capability still blocks.
        reg.TOOLS["promiscuous"] = _FakeTool("promiscuous", authorize_ok=True)
        from tools.router import execute_tool
        # 'promiscuous' is not in _TOOL_TO_ACTION → tool.invoke → admin-only.
        result = execute_tool(
            {"name": "promiscuous", "input": {"path": ""}},
            {"user_role": "external"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "CAPABILITY_DENIED")


if __name__ == "__main__":
    unittest.main()
