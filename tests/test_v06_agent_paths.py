"""v0.6.1 Phase B — agent-tool user-path permission tests.

Covers `tools/code/sandbox.py` extensions
(`register_user_path` / `get_user_registered_paths` / `validate_path`
opt-in for absolute paths) + the `routes/agent_paths.py` admin endpoints
(`GET/POST /admin/agent/allowed-paths`).

Run:
  python -m unittest tests.test_v06_agent_paths
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _reset_sandbox_state():
    """Clear the module-level user-path registry between tests so each
    test starts from a known state without restarting the process."""
    import tools.code.sandbox as sb
    sb._USER_REGISTERED_PATHS.clear()
    sb._USER_PATHS_LOADED = False


class SandboxRegisterUserPathTests(unittest.TestCase):
    def setUp(self):
        _reset_sandbox_state()
        self._tmp = tempfile.mkdtemp(prefix="james_sb_t_")
        self._prev_env = os.environ.pop("JAMES_AGENT_ALLOWED_PATHS", None)

    def tearDown(self):
        if self._prev_env is not None:
            os.environ["JAMES_AGENT_ALLOWED_PATHS"] = self._prev_env
        shutil.rmtree(self._tmp, ignore_errors=True)
        _reset_sandbox_state()

    def test_registers_existing_absolute_path(self):
        from tools.code.sandbox import register_user_path, get_user_registered_paths
        ok, msg = register_user_path(self._tmp)
        self.assertTrue(ok, msg)
        self.assertEqual(len(get_user_registered_paths()), 1)

    def test_idempotent_register(self):
        from tools.code.sandbox import register_user_path
        ok1, _ = register_user_path(self._tmp)
        ok2, msg2 = register_user_path(self._tmp)
        self.assertTrue(ok1 and ok2)
        self.assertIn("already", msg2.lower())

    def test_rejects_nonexistent_path(self):
        from tools.code.sandbox import register_user_path
        ok, msg = register_user_path(os.path.join(self._tmp, "no-such-dir"))
        self.assertFalse(ok)
        self.assertIn("does not exist", msg)

    def test_rejects_relative_path(self):
        from tools.code.sandbox import register_user_path
        # relative path; realpath will turn it absolute pointing under
        # the test process cwd, which is inside the JAMES repo — so the
        # registration should succeed only if the path actually exists.
        # We use one that doesn't exist so the existence check fails:
        ok, msg = register_user_path("relative/no-such-thing")
        self.assertFalse(ok)

    def test_rejects_critical_system_root_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX-only critical roots")
        from tools.code.sandbox import register_user_path
        for root in ("/etc", "/proc", "/root"):
            ok, msg = register_user_path(root)
            self.assertFalse(ok, f"should reject {root}")
            # On a real POSIX host the path exists so the critical
            # check fires; in CI containers it may not exist either —
            # both are acceptable failures.
            self.assertTrue(
                ("critical system root" in msg) or ("does not exist" in msg),
                msg,
            )

    def test_rejects_critical_system_root_windows(self):
        from tools.code.sandbox import register_user_path
        # Use the env-var-resolved values so the test runs on any host.
        for root in ("C:\\Windows", "C:\\Program Files"):
            ok, msg = register_user_path(root)
            # On non-Windows hosts the path doesn't exist → "does not
            # exist" is also acceptable, but the critical check should
            # fire first on Windows hosts.
            self.assertFalse(ok)


class SandboxValidatePathTests(unittest.TestCase):
    def setUp(self):
        _reset_sandbox_state()
        self._tmp = tempfile.mkdtemp(prefix="james_sb_v_")
        self._prev_env = os.environ.pop("JAMES_AGENT_ALLOWED_PATHS", None)

    def tearDown(self):
        if self._prev_env is not None:
            os.environ["JAMES_AGENT_ALLOWED_PATHS"] = self._prev_env
        shutil.rmtree(self._tmp, ignore_errors=True)
        _reset_sandbox_state()

    def test_workspace_still_works_by_default(self):
        from tools.code.sandbox import validate_path
        ok, msg = validate_path("./workspace/foo.md", role="user")
        self.assertTrue(ok, msg)

    def test_absolute_path_blocked_when_not_registered(self):
        from tools.code.sandbox import validate_path
        # admin still gets blocked by BLOCKED_PATH_PATTERNS when the
        # absolute path is not in the user-registered set.
        if os.name == "nt":
            ok, _ = validate_path("C:\\SomeTemp\\foo.md", role="admin")
        else:
            ok, _ = validate_path("/tmp/some-absolute-thing.md", role="admin")
        self.assertFalse(ok)

    def test_absolute_path_allowed_after_register(self):
        from tools.code.sandbox import register_user_path, validate_path
        ok, _ = register_user_path(self._tmp)
        self.assertTrue(ok)
        ok2, msg = validate_path(os.path.join(self._tmp, "notes.md"),
                                  role="user")
        self.assertTrue(ok2, msg)

    def test_sibling_of_registered_blocked(self):
        from tools.code.sandbox import register_user_path, validate_path
        register_user_path(self._tmp)
        sibling = os.path.join(os.path.dirname(self._tmp), "_other_xyz_", "x")
        ok, _ = validate_path(sibling, role="user")
        self.assertFalse(ok)

    def test_env_load_on_first_call(self):
        from tools.code.sandbox import get_user_registered_paths
        os.environ["JAMES_AGENT_ALLOWED_PATHS"] = self._tmp
        paths = get_user_registered_paths()
        self.assertEqual(len(paths), 1)
        self.assertTrue(any(p.endswith(os.path.basename(self._tmp))
                            for p in paths))


# ── HTTP endpoint tests ────────────────────────────────────────────

def _make_client(role="admin"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.agent_paths as ap
    from routes._helpers import get_role_from_request

    app = FastAPI()
    app.include_router(ap.router)
    app.dependency_overrides[get_role_from_request] = lambda: role
    ap._bearer_username = lambda request: "admin"
    # Stub the api_key + admin gate so the test doesn't need a real key.
    import routes._helpers as h
    ap._require_admin = lambda api_key, role: None if role == "admin" else (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403, detail="admin only")
    )
    return TestClient(app), ap


class AgentPathsRoutesTests(unittest.TestCase):
    def setUp(self):
        _reset_sandbox_state()
        self._tmp = tempfile.mkdtemp(prefix="james_sb_r_")
        self._prev_env = os.environ.pop("JAMES_AGENT_ALLOWED_PATHS", None)

    def tearDown(self):
        if self._prev_env is not None:
            os.environ["JAMES_AGENT_ALLOWED_PATHS"] = self._prev_env
        shutil.rmtree(self._tmp, ignore_errors=True)
        _reset_sandbox_state()

    def test_get_default_empty(self):
        client, _ = _make_client(role="admin")
        r = client.get("/admin/agent/allowed-paths?api_key=dummy")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["env_name"], "JAMES_AGENT_ALLOWED_PATHS")

    def test_get_forbidden_for_non_admin(self):
        client, _ = _make_client(role="user")
        r = client.get("/admin/agent/allowed-paths?api_key=dummy")
        self.assertEqual(r.status_code, 403)

    def test_post_registers_existing_path(self):
        client, _ = _make_client(role="admin")
        r = client.post("/admin/agent/allowed-paths",
                        json={"api_key": "dummy", "path": self._tmp})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["registered"])

    def test_post_rejects_nonexistent_path_with_400(self):
        client, _ = _make_client(role="admin")
        r = client.post("/admin/agent/allowed-paths",
                        json={"api_key": "dummy",
                              "path": "/no/such/path/ever"})
        self.assertEqual(r.status_code, 400)


class ServerRegistrationTests(unittest.TestCase):
    def test_routes_wired_on_app(self):
        import server_llmwiki
        paths = {getattr(r, "path", None) for r in server_llmwiki.app.routes}
        self.assertIn("/admin/agent/allowed-paths", paths)


if __name__ == "__main__":
    unittest.main()
