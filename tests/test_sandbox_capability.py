"""Sandbox-side capability gate tests (#44 phase 3-3).

Coverage:
  - policy_validate_path enforces PolicyEngine action policy
    (fs.read employee+, fs.write admin) before sandbox validate_path.
  - tools/code/* and tools/patch/patch_generator route through
    policy_validate_path even when called directly (not via router).
  - Legacy validate_path primitive still exists for sandbox internal use.

Run:
  python -m unittest tests.test_sandbox_capability
  python tests/test_sandbox_capability.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PolicyValidatePathTests(unittest.TestCase):
    """policy_validate_path: fail-closed gate before legacy validate_path."""

    def setUp(self):
        # Suppress emoji-laden stdout (Windows cp949 unittest hostility).
        self._stdout_ctx = redirect_stdout(io.StringIO())
        self._stdout_ctx.__enter__()

    def tearDown(self):
        self._stdout_ctx.__exit__(None, None, None)

    # ─── fs.read (employee+) ─────────────────────────────────────

    def test_employee_fs_read_workspace_allowed(self):
        from tools.code.sandbox import policy_validate_path
        ok, _ = policy_validate_path("./workspace/a.py", "employee", "fs.read")
        self.assertTrue(ok)

    def test_external_fs_read_denied_at_policy(self):
        from tools.code.sandbox import policy_validate_path
        ok, reason = policy_validate_path("./workspace/a.py", "external", "fs.read")
        self.assertFalse(ok)
        self.assertIn("policy.denied", reason)

    def test_unknown_role_fs_read_denied(self):
        from tools.code.sandbox import policy_validate_path
        ok, reason = policy_validate_path("./workspace/a.py", "user", "fs.read")
        self.assertFalse(ok)
        self.assertIn("policy.denied", reason)

    # ─── fs.write (admin only) ───────────────────────────────────

    def test_employee_fs_write_denied_at_policy(self):
        from tools.code.sandbox import policy_validate_path
        ok, reason = policy_validate_path("./workspace/a.py", "employee", "fs.write")
        self.assertFalse(ok)
        self.assertIn("policy.denied", reason)

    def test_admin_fs_write_workspace_allowed(self):
        from tools.code.sandbox import policy_validate_path
        ok, _ = policy_validate_path("./workspace/a.py", "admin", "fs.write")
        self.assertTrue(ok)

    # ─── defense-in-depth: legacy sandbox patterns still apply ──

    def test_admin_blocked_at_legacy_pattern(self):
        # PolicyEngine grants fs.write for admin, but sandbox's
        # BLOCKED_PATH_PATTERNS still bars core/ — defense-in-depth.
        from tools.code.sandbox import policy_validate_path
        ok, reason = policy_validate_path(
            "./core/security_layer.py", "admin", "fs.write",
        )
        self.assertFalse(ok)

    def test_employee_outside_allowed_paths_blocked(self):
        # Even with fs.read policy passing, legacy sandbox blocks
        # employee from paths outside ALLOWED_PATHS.
        from tools.code.sandbox import policy_validate_path
        ok, _ = policy_validate_path("./other_dir/a.py", "employee", "fs.read")
        self.assertFalse(ok)


class ToolMigrationTests(unittest.TestCase):
    """Direct tool calls (bypassing router) still hit PolicyEngine."""

    def setUp(self):
        self._stdout_ctx = redirect_stdout(io.StringIO())
        self._stdout_ctx.__enter__()
        # Workspace fixture for tool reads.
        self._tmpdir = tempfile.mkdtemp(prefix="james_phase33_")
        # tools depend on the literal "./workspace" prefix being in
        # ALLOWED_PATHS — easier to use that prefix directly.
        os.makedirs("./workspace", exist_ok=True)
        self._fixture = "./workspace/_phase33_fixture.py"
        with open(self._fixture, "w", encoding="utf-8") as f:
            f.write("# fixture\nprint('hi')\n")

    def tearDown(self):
        self._stdout_ctx.__exit__(None, None, None)
        try:
            os.unlink(self._fixture)
        except OSError:
            pass

    # ─── CodeReader ──────────────────────────────────────────────

    def test_code_reader_external_blocked(self):
        from tools.code.code_reader import CodeReader
        reader = CodeReader(user_role="external")
        ok, msg, _ = reader.read_file(self._fixture)
        self.assertFalse(ok)
        self.assertIn("경로 차단", msg)

    def test_code_reader_employee_allowed(self):
        from tools.code.code_reader import CodeReader
        reader = CodeReader(user_role="employee")
        ok, _, meta = reader.read_file(self._fixture)
        self.assertTrue(ok, msg=meta)

    # ─── CodeEditor ──────────────────────────────────────────────

    def test_code_editor_employee_blocked(self):
        from tools.code.code_editor import CodeEditor
        editor = CodeEditor(user_role="employee")
        ok, msg = editor.write_file(
            "./workspace/_phase33_employee.py", "# nope\n",
        )
        self.assertFalse(ok)
        self.assertIn("경로 차단", msg)
        # Make sure the file was NOT written despite legacy validate_path
        # would have allowed it (this is the whole point of phase 3-3).
        self.assertFalse(os.path.exists("./workspace/_phase33_employee.py"))

    def test_code_editor_admin_allowed(self):
        from tools.code.code_editor import CodeEditor
        editor = CodeEditor(user_role="admin")
        target = "./workspace/_phase33_admin.py"
        try:
            ok, _ = editor.write_file(target, "# ok\n")
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(target))
        finally:
            try:
                os.unlink(target)
            except OSError:
                pass

    # ─── ReadFileTool (BaseTool) — role from input_data ──────────

    def test_read_file_tool_external_blocked(self):
        from tools.code.read_file import ReadFileTool
        tool = ReadFileTool()
        result = tool.execute({"path": self._fixture, "role": "external"})
        self.assertFalse(result["success"])

    def test_read_file_tool_employee_allowed(self):
        from tools.code.read_file import ReadFileTool
        tool = ReadFileTool()
        result = tool.execute({"path": self._fixture, "role": "employee"})
        self.assertTrue(result["success"], msg=result)


if __name__ == "__main__":
    unittest.main()
