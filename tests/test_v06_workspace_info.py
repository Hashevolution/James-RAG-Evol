"""v0.6.1 — routes/workspace_info.py tests.

Builds a minimal FastAPI app with just the workspace-info router,
overrides the role dependency, stubs the JWT subject, and exercises the
endpoint with and without JAMES_WORKSPACE set.

Run:
  python -m unittest tests.test_v06_workspace_info
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_client(user="alice", role="admin"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.workspace_info as wi
    from routes._helpers import get_role_from_request

    app = FastAPI()
    app.include_router(wi.router)
    app.dependency_overrides[get_role_from_request] = lambda: role
    wi._bearer_username = lambda request: user  # noqa: stub JWT subject
    return TestClient(app), wi


class WorkspaceInfoTests(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.get("JAMES_WORKSPACE")
        self._prev_pt = os.environ.get("JAMES_WORKSPACE_PER_TENANT")

    def tearDown(self):
        for name, prev in (
            ("JAMES_WORKSPACE", self._prev),
            ("JAMES_WORKSPACE_PER_TENANT", self._prev_pt),
        ):
            if prev is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = prev

    def test_default_when_env_unset(self):
        os.environ.pop("JAMES_WORKSPACE", None)
        client, _ = _make_client(user="alice")
        r = client.get("/workspace/info")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["is_default"])
        self.assertEqual(body["workspace_name"], "default")
        self.assertIn("workspace_path", body)
        self.assertIsInstance(body["entity_count"], int)

    def test_custom_when_env_set(self):
        os.environ["JAMES_WORKSPACE"] = "workspaces/dogfood-2026-06"
        client, _ = _make_client(user="alice")
        r = client.get("/workspace/info")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertFalse(body["is_default"])
        # Display name is the leaf of the env value (header is short).
        self.assertEqual(body["workspace_name"], "dogfood-2026-06")

    def test_per_tenant_flag_surfaced(self):
        os.environ["JAMES_WORKSPACE_PER_TENANT"] = "1"
        client, _ = _make_client(user="alice")
        r = client.get("/workspace/info")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["per_tenant_enabled"])

    def test_login_required(self):
        client, wi = _make_client(user="alice")
        wi._bearer_username = lambda request: None  # no JWT subject
        r = client.get("/workspace/info")
        self.assertEqual(r.status_code, 401)


class ServerRegistrationTests(unittest.TestCase):
    def test_route_registered_on_app(self):
        import server_llmwiki
        paths = {getattr(r, "path", None) for r in server_llmwiki.app.routes}
        self.assertIn("/workspace/info", paths)


if __name__ == "__main__":
    unittest.main()
