"""v0.6.1 Phase E — run_shell agent tool.

Covers the security contract: default-OFF gate, admin-only, cwd anchored
to an allowed folder, command allow-list (sandbox + the wider shell
list), shell selection, and the endpoint schema-hiding while disabled.

No network. Shell runs are local `echo` only.

Run:
  python -m unittest tests.test_v06_agent_shell
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ENV = "JAMES_AGENT_ENABLE_SHELL"


def _reset_sandbox_state():
    import tools.code.sandbox as sb
    sb._USER_REGISTERED_PATHS.clear()
    sb._USER_PATHS_LOADED = False


def _echo_args(cwd):
    """Cross-platform echo that prints a known marker."""
    if os.name == "nt":
        return {"command": "echo james_shell_ok", "cwd": cwd, "shell": "cmd"}
    return {"command": "echo james_shell_ok", "cwd": cwd, "shell": "bash"}


class ShellRegistrationTests(unittest.TestCase):
    def test_run_shell_registered(self):
        from core.agent_tools import list_tools, get_tool
        self.assertIn("run_shell", [t.name for t in list_tools()])
        self.assertIsNotNone(get_tool("run_shell"))


class ShellGateTests(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.pop(_ENV, None)
        _reset_sandbox_state()
        self._tmp = tempfile.mkdtemp(prefix="james_sh_")
        from tools.code.sandbox import register_user_path
        register_user_path(self._tmp)

    def tearDown(self):
        if self._prev is not None:
            os.environ[_ENV] = self._prev
        else:
            os.environ.pop(_ENV, None)
        shutil.rmtree(self._tmp, ignore_errors=True)
        _reset_sandbox_state()

    def test_disabled_by_default(self):
        from core.agent_tools import dispatch
        r = dispatch("run_shell", _echo_args(self._tmp), "admin")
        self.assertFalse(r["ok"])
        self.assertIn("disabled", r["error"])

    def test_enabled_admin_echo_runs(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        r = dispatch("run_shell", _echo_args(self._tmp), "admin")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["output"]["exit_code"], 0)
        self.assertIn("james_shell_ok", r["output"]["stdout"])

    def test_non_admin_refused_even_when_enabled(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        r = dispatch("run_shell", _echo_args(self._tmp), "user")
        self.assertFalse(r["ok"])
        self.assertIn("admin", r["error"])

    def test_blocked_command_refused(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        a = _echo_args(self._tmp)
        a["command"] = "curl http://example.com/x"
        r = dispatch("run_shell", a, "admin")
        self.assertFalse(r["ok"])
        self.assertIn("blocked", r["error"])

    def test_extra_blocked_shell_surface_refused(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        a = _echo_args(self._tmp)
        a["command"] = "Invoke-WebRequest http://example.com -OutFile x"
        r = dispatch("run_shell", a, "admin")
        self.assertFalse(r["ok"])
        self.assertIn("blocked", r["error"])

    def test_critical_cwd_refused(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        crit = "C:\\Windows" if os.name == "nt" else "/etc"
        a = _echo_args(crit)
        r = dispatch("run_shell", a, "admin")
        self.assertFalse(r["ok"])
        self.assertIn("cwd rejected", r["error"])

    def test_unregistered_absolute_cwd_refused(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        other = tempfile.mkdtemp(prefix="james_unreg_")
        try:
            a = _echo_args(other)
            r = dispatch("run_shell", a, "admin")
            self.assertFalse(r["ok"])
            self.assertIn("cwd rejected", r["error"])
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_unknown_shell_refused(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        a = _echo_args(self._tmp)
        a["shell"] = "fish"
        r = dispatch("run_shell", a, "admin")
        self.assertFalse(r["ok"])
        self.assertIn("unknown shell", r["error"])

    def test_missing_command_refused(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        r = dispatch("run_shell", {"cwd": self._tmp}, "admin")
        self.assertFalse(r["ok"])
        self.assertIn("command", r["error"])

    def test_output_cap(self):
        os.environ[_ENV] = "1"
        from core.agent_tools import dispatch
        # Generate > cap chars INSIDE the shell (a huge argv would hit
        # cmd's ~8191-char command-line limit on Windows).
        if os.name == "nt":
            a = {"command": 'Write-Output ("A"*9000)', "cwd": self._tmp,
                 "shell": "powershell"}
        else:
            a = {"command": "head -c 9000 /dev/zero | tr '\\0' A",
                 "cwd": self._tmp, "shell": "bash"}
        r = dispatch("run_shell", a, "admin")
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["output"]["truncated"])
        self.assertLessEqual(
            len(r["output"]["stdout"]) + len(r["output"]["stderr"]), 4000)


# ── Endpoint schema-hiding ─────────────────────────────────────────

class _RecordingBackend:
    name = "rec"

    def __init__(self):
        self.seen_tool_names = None

    def chat_with_tools(self, messages, tools, *, system=None, max_tokens=1024):
        self.seen_tool_names = [t["name"] for t in tools]
        return {"stop_reason": "end_turn", "text": "ok", "tool_calls": [], "raw": {}}


def _make_client(role="admin"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.agent_chat as ac
    from routes._helpers import get_role_from_request

    app = FastAPI()
    app.include_router(ac.router)
    app.dependency_overrides[get_role_from_request] = lambda: role
    ac._bearer_username = lambda request: "admin"
    ac._require_admin = lambda api_key, role: None
    return TestClient(app), ac


class ShellSchemaVisibilityTests(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.pop(_ENV, None)

    def tearDown(self):
        if self._prev is not None:
            os.environ[_ENV] = self._prev
        else:
            os.environ.pop(_ENV, None)

    def _run_once(self):
        client, _ = _make_client()
        rec = _RecordingBackend()
        import core.agent_tools.backends as be
        orig = be.get_backend
        be.get_backend = lambda name=None: rec
        try:
            r = client.post("/agent/chat/", json={"api_key": "x", "message": "hi"})
        finally:
            be.get_backend = orig
        self.assertEqual(r.status_code, 200, r.text)
        return rec.seen_tool_names

    def test_hidden_when_disabled(self):
        os.environ.pop(_ENV, None)
        names = self._run_once()
        self.assertNotIn("run_shell", names)
        self.assertIn("write_file", names)   # other tools still present

    def test_visible_when_enabled(self):
        os.environ[_ENV] = "1"
        names = self._run_once()
        self.assertIn("run_shell", names)


if __name__ == "__main__":
    unittest.main()
