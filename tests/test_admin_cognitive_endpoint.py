"""Admin cognitive-feature-flag endpoints (UI-IA risk #5 fix).

Exercises `GET / POST /admin/settings/cognitive` end-to-end through
FastAPI's TestClient. Skips when `JAMES_API_KEY` is not available
(matches the pattern in test_change_request_endpoints.py).

The endpoints delegate to `core/feature_flags.py`; the registry-
level behaviour is pinned in `tests/test_feature_flags.py`. This
file focuses on the HTTP wiring: auth gate, request/response
shapes, audit log, and env-mutation side effects.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _read_api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


ALL_COGNITIVE_ENV_NAMES = (
    "JAMES_DISABLE_VERIFY",
    "JAMES_ENABLE_FACT_CHECK",
    "JAMES_ENABLE_REFLECT",
    "JAMES_ENABLE_PLANNER",
    "JAMES_ENABLE_QUERY_REWRITE",
    "JAMES_DISABLE_RERANK",
)


class CognitiveEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from core.auth import create_token
        cls._admin_token = create_token("admin-alice", "admin")
        cls._user_token  = create_token("user-bob",    "employee")
        cls._api_key     = _read_api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing; cannot exercise admin route")
        # Clean env so each test starts from documented defaults.
        self._snapshot = {n: os.environ.get(n) for n in ALL_COGNITIVE_ENV_NAMES}
        for n in ALL_COGNITIVE_ENV_NAMES:
            os.environ.pop(n, None)

    def tearDown(self):
        for n, v in self._snapshot.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _admin_headers(self):
        return {"Authorization": f"Bearer {self._admin_token}"}

    def _user_headers(self):
        return {"Authorization": f"Bearer {self._user_token}"}

    # ── GET ─────────────────────────────────────────────────────

    def test_get_returns_six_flags(self):
        r = self._client().get(
            f"/admin/settings/cognitive?api_key={self._api_key}",
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("flags", body)
        self.assertEqual(len(body["flags"]), 6)

    def test_get_default_state_with_clean_env(self):
        # setUp popped every cognitive env var; the response should
        # reflect documented defaults (verify ON, rerank ON, rest OFF).
        r = self._client().get(
            f"/admin/settings/cognitive?api_key={self._api_key}",
            headers=self._admin_headers(),
        )
        flags = {f["key"]: f["on"] for f in r.json()["flags"]}
        self.assertTrue(flags["verify"])
        self.assertTrue(flags["rerank"])
        self.assertFalse(flags["fact_check"])
        self.assertFalse(flags["planner"])
        self.assertFalse(flags["query_rewrite"])
        self.assertFalse(flags["reflect"])

    def test_get_requires_admin_settings_feature(self):
        # Non-admin (employee) must be rejected — admin.settings gate.
        r = self._client().get(
            f"/admin/settings/cognitive?api_key={self._api_key}",
            headers=self._user_headers(),
        )
        self.assertEqual(r.status_code, 403, r.text)

    # ── POST ────────────────────────────────────────────────────

    def test_post_toggles_a_single_flag_on(self):
        r = self._client().post(
            "/admin/settings/cognitive",
            json={"api_key": self._api_key, "flags": {"reflect": True}},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["deltas"]), 1)
        d = body["deltas"][0]
        self.assertEqual(d["key"], "reflect")
        self.assertFalse(d["before"])
        self.assertTrue(d["after"])
        # Side effect — env var actually set.
        self.assertEqual(os.environ.get("JAMES_ENABLE_REFLECT"), "1")

    def test_post_toggles_multiple_flags_at_once(self):
        r = self._client().post(
            "/admin/settings/cognitive",
            json={
                "api_key": self._api_key,
                "flags": {
                    "reflect": True,
                    "planner": True,
                    "verify":  False,
                },
            },
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        keys = {d["key"] for d in r.json()["deltas"]}
        self.assertEqual(keys, {"reflect", "planner", "verify"})
        self.assertEqual(os.environ.get("JAMES_ENABLE_REFLECT"), "1")
        self.assertEqual(os.environ.get("JAMES_ENABLE_PLANNER"), "1")
        self.assertEqual(os.environ.get("JAMES_DISABLE_VERIFY"), "1")

    def test_post_disable_polarity_off_then_on_round_trip(self):
        # Toggle verify OFF, then back ON, confirming the env var
        # gets popped on the second call (no stale "1" lingering).
        client = self._client()
        client.post(
            "/admin/settings/cognitive",
            json={"api_key": self._api_key, "flags": {"verify": False}},
            headers=self._admin_headers(),
        )
        self.assertEqual(os.environ.get("JAMES_DISABLE_VERIFY"), "1")
        client.post(
            "/admin/settings/cognitive",
            json={"api_key": self._api_key, "flags": {"verify": True}},
            headers=self._admin_headers(),
        )
        self.assertIsNone(os.environ.get("JAMES_DISABLE_VERIFY"))

    def test_post_empty_flags_dict_rejected(self):
        r = self._client().post(
            "/admin/settings/cognitive",
            json={"api_key": self._api_key, "flags": {}},
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("flags", r.json()["detail"])

    def test_post_unknown_flag_rejected(self):
        r = self._client().post(
            "/admin/settings/cognitive",
            json={
                "api_key": self._api_key,
                "flags": {"does_not_exist": True},
            },
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("unknown cognitive flag", r.json()["detail"])

    def test_post_non_bool_value_rejected(self):
        r = self._client().post(
            "/admin/settings/cognitive",
            json={
                "api_key": self._api_key,
                "flags": {"reflect": "yes"},
            },
            headers=self._admin_headers(),
        )
        self.assertEqual(r.status_code, 400)

    def test_post_requires_admin_settings_feature(self):
        r = self._client().post(
            "/admin/settings/cognitive",
            json={
                "api_key": self._api_key,
                "flags": {"reflect": True},
            },
            headers=self._user_headers(),
        )
        self.assertEqual(r.status_code, 403, r.text)

    # ── Round-trip GET → POST → GET ─────────────────────────────

    def test_post_then_get_reflects_new_state(self):
        client = self._client()
        client.post(
            "/admin/settings/cognitive",
            json={
                "api_key": self._api_key,
                "flags": {"fact_check": True, "rerank": False},
            },
            headers=self._admin_headers(),
        )
        r = client.get(
            f"/admin/settings/cognitive?api_key={self._api_key}",
            headers=self._admin_headers(),
        )
        flags = {f["key"]: f["on"] for f in r.json()["flags"]}
        self.assertTrue(flags["fact_check"])
        self.assertFalse(flags["rerank"])


if __name__ == "__main__":
    unittest.main()
