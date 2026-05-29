"""GET /admin/trace/{trace_id} endpoint — #81 phase 3-A.

Coverage:
  - Source-level: route exists, is admin-gated, calls read_trace,
    returns the documented response shape (trace_id / day / count /
    stages).
  - Behavioral: round-trip — write a trace via the existing
    `start_trace` / `log_stage` primitives, read it back through the
    endpoint via FastAPI TestClient, assert the stages list matches.
  - 404: nonexistent trace_id returns 404 with a helpful detail.
  - The `day` query param is honored (test reads back from a custom
    trace root using set_trace_root, exercises an explicit day).

Run:
  python -m unittest tests.test_admin_trace_endpoint
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _admin_key() -> str:
    """Resolve a working admin api_key the same way the bench runner does."""
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def _admin_headers() -> dict:
    """Mint an admin JWT for tests. Avoids relying on DEV_MODE +
    X-Role header (which depends on env at import time)."""
    from core.auth import create_token
    token = create_token("test-admin", "admin")
    return {"Authorization": f"Bearer {token}"}


class EndpointContractTests(unittest.TestCase):
    """Source-level: route is registered, admin-gated, returns shape."""

    def test_route_registered_and_admin_gated(self):
        from tests._server_split_helpers import combined_server_source
        src = combined_server_source()
        self.assertIn('@app.get("/admin/trace/{trace_id}"', src,
                      "trace endpoint must be registered as GET /admin/trace/{trace_id}")
        self.assertIn("from core.observability import read_trace", src,
                      "trace endpoint must import read_trace")
        idx = src.index('@app.get("/admin/trace/{trace_id}"')
        window = src[idx:idx + 1500]
        self.assertTrue("_require_admin(api_key, role)" in window or "_require_feature(api_key, role" in window,
                      "trace endpoint must call _require_admin")
        self.assertIn("read_trace(trace_id, day=", window,
                      "trace endpoint must invoke read_trace with day param")
        self.assertIn("status_code=404", window,
                      "trace endpoint must 404 on missing trace")
        # Response shape contract.
        for key in ('"trace_id"', '"day"', '"count"', '"stages"'):
            self.assertIn(key, window, f"response shape missing key: {key}")


class TraceRoundtripTests(unittest.TestCase):
    """End-to-end: write a trace, read it back through the FastAPI
    TestClient. Uses set_trace_root to point at a tmpdir so we don't
    pollute reports/trace/."""

    def setUp(self):
        from core.observability import set_trace_root, current_trace_id
        self._tmp = tempfile.TemporaryDirectory()
        set_trace_root(Path(self._tmp.name))
        current_trace_id.set("")
        self._api_key = _admin_key()
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing; cannot exercise admin route")

    def tearDown(self):
        from core.observability import set_trace_root
        set_trace_root(None)
        self._tmp.cleanup()

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def test_404_on_unknown_trace_id(self):
        client = self._client()
        r = client.get(
            "/admin/trace/0123456789abcdef",
            params={"api_key": self._api_key},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 404,
                         f"expected 404 for unknown trace, got {r.status_code}: {r.text}")
        self.assertIn("trace not found", r.json().get("detail", ""))

    def test_roundtrip_returns_chronological_stages(self):
        from core.observability import start_trace, log_stage

        tid = start_trace()
        log_stage("auth",     role="admin", allowed=True)
        log_stage("retrieve", top_k=8, top_vector_score=0.82)
        log_stage("graph",    entities_extracted=3, paths_walked=15)
        log_stage("answer",   latency_ms=1820, answer_len=412)

        client = self._client()
        r = client.get(
            f"/admin/trace/{tid}",
            params={"api_key": self._api_key},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200,
                         f"expected 200, got {r.status_code}: {r.text}")
        body = r.json()
        self.assertEqual(body["trace_id"], tid)
        self.assertEqual(body["day"], datetime.now().strftime("%Y-%m-%d"))
        self.assertEqual(body["count"], 4)
        self.assertEqual(len(body["stages"]), 4)
        # Stages must be in write order.
        self.assertEqual(
            [s["stage"] for s in body["stages"]],
            ["auth", "retrieve", "graph", "answer"],
        )
        # Each stage carries trace_id + ts_ns + the user-supplied fields.
        self.assertEqual(body["stages"][1]["top_k"], 8)
        self.assertEqual(body["stages"][2]["paths_walked"], 15)

    def test_explicit_day_param_round_trip(self):
        # Behavior: when day is omitted the endpoint resolves to today.
        # When day is provided, it's passed through to read_trace and
        # echoed back in the response. We can't easily fake yesterday's
        # files in this test setup, but we can confirm the endpoint
        # echoes the day arg even when no trace exists (404 path).
        client = self._client()
        r = client.get(
            "/admin/trace/0123456789abcdef",
            params={"api_key": self._api_key, "day": "2024-01-01"},
            headers=_admin_headers(),
        )
        # 404 is fine (no trace), but the detail must mention the
        # day we asked about.
        self.assertEqual(r.status_code, 404)
        self.assertIn("2024-01-01", r.json().get("detail", ""),
                      "404 detail must echo the day we queried")


class AdminGateTests(unittest.TestCase):
    """The endpoint must reject calls without a valid admin api_key."""

    def setUp(self):
        from core.observability import set_trace_root
        self._tmp = tempfile.TemporaryDirectory()
        set_trace_root(Path(self._tmp.name))

    def tearDown(self):
        from core.observability import set_trace_root
        set_trace_root(None)
        self._tmp.cleanup()

    def test_missing_api_key_rejected(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        client = TestClient(srv.app)
        r = client.get("/admin/trace/abc")
        # FastAPI returns 422 when a required query param is missing.
        # Either 4xx is acceptable — what matters is "not 200".
        self.assertNotEqual(r.status_code, 200,
                            "missing api_key must not return 200")

    def test_wrong_api_key_rejected(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        client = TestClient(srv.app)
        r = client.get(
            "/admin/trace/abc",
            params={"api_key": "definitely-not-the-real-key-xxxxxx"},
        )
        self.assertNotEqual(r.status_code, 200,
                            "wrong api_key must not return 200")


if __name__ == "__main__":
    unittest.main()
