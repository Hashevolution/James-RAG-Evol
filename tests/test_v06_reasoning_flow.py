"""v0.6 Phase 4 P4.3 — reasoning flow visualization tests.

Coverage:

`GET /admin/audit/recent-traces`:
  * Admin gate (employee → 403)
  * Empty trace root → `{ok: true, traces: []}`
  * Synthetic JSONL trace files → recent list returns trace_id +
    stage_count + first_ts_ns + last_ts_ns + question
  * `limit` parameter caps the result
  * `day` parameter selects partition; malformed day → 400

Frontend structure (lock tests):
  * `/admin/reasoning-flow` page exists
  * 3 swimlane containers present (phase-retrieve / phase-expand /
    phase-verify)
  * Trace selector + recent list + detail panel present
  * Technical jargon NOT leaked (e.g. `audit_log` raw, `JWT`,
    `reconstruct_graph_at`)
  * `reasoning-flow.js` exposes `window.JAMES_ReasoningFlow` with
    canonical functions + STAGE_META map
  * `reasoning-flow.css` carries canonical selectors
  * i18n keys present in BOTH EN and KO blocks
  * Server route registered
  * Admin entry-point link present in admin.html

Run:
  python -m unittest tests.test_v06_reasoning_flow
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-reasoning-flow-endpoint-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


REPO_ROOT = Path(__file__).resolve().parent.parent
HTML       = REPO_ROOT / "frontend" / "reasoning-flow.html"
JS         = REPO_ROOT / "frontend" / "static" / "reasoning-flow.js"
CSS        = REPO_ROOT / "frontend" / "static" / "reasoning-flow.css"
I18N       = REPO_ROOT / "frontend" / "static" / "i18n.js"
ADMIN_HTML = REPO_ROOT / "frontend" / "admin.html"
SERVER     = REPO_ROOT / "server_llmwiki.py"


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


def _seed_trace_files(day: str, traces: dict) -> None:
    """Write synthetic .jsonl trace files under the current trace root.

    `traces` = { trace_id: [stage_dict, ...] }
    """
    from core.observability import _trace_root
    root = _trace_root() / day
    root.mkdir(parents=True, exist_ok=True)
    for trace_id, entries in traces.items():
        path = root / f"{trace_id}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")


# ─── endpoint tests ────────────────────────────────────────────────


class RecentTracesEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")
        from core.observability import set_trace_root, current_trace_id
        self._tmp = tempfile.TemporaryDirectory()
        set_trace_root(Path(self._tmp.name))
        current_trace_id.set("")

    def tearDown(self):
        from core.observability import set_trace_root
        set_trace_root(None)
        self._tmp.cleanup()

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def test_employee_jwt_rejected(self):
        c = self._client()
        r = c.get("/admin/audit/recent-traces",
                  params={"api_key": self._api_key},
                  headers=_employee_headers())
        self.assertEqual(r.status_code, 403, r.text)

    def test_empty_trace_root_returns_empty(self):
        c = self._client()
        r = c.get("/admin/audit/recent-traces",
                  params={"api_key": self._api_key,
                          "day": "2026-06-13"},
                  headers=_admin_headers())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["traces"], [])

    def test_malformed_day_400(self):
        c = self._client()
        r = c.get("/admin/audit/recent-traces",
                  params={"api_key": self._api_key, "day": "garbage"},
                  headers=_admin_headers())
        self.assertEqual(r.status_code, 400, r.text)

    def test_recent_list_returns_summary_fields(self):
        day = "2026-06-13"
        traces = {
            "tr_a": [
                {"trace_id": "tr_a", "stage": "auth", "ts_ns": 1000,
                 "user_role": "alice"},
                {"trace_id": "tr_a", "stage": "retrieve",
                 "ts_ns": 1500, "query": "vacation policy"},
                {"trace_id": "tr_a", "stage": "answer", "ts_ns": 2000},
            ],
            "tr_b": [
                {"trace_id": "tr_b", "stage": "auth", "ts_ns": 500},
            ],
        }
        _seed_trace_files(day, traces)

        c = self._client()
        r = c.get("/admin/audit/recent-traces",
                  params={"api_key": self._api_key, "day": day},
                  headers=_admin_headers())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        rows = body["traces"]
        self.assertEqual(len(rows), 2)
        by_id = {x["trace_id"]: x for x in rows}
        self.assertEqual(by_id["tr_a"]["stage_count"], 3)
        self.assertEqual(by_id["tr_a"]["question"], "vacation policy")
        self.assertEqual(by_id["tr_a"]["user"], "alice")
        self.assertEqual(by_id["tr_a"]["first_ts_ns"], 1000)
        self.assertEqual(by_id["tr_a"]["last_ts_ns"], 2000)
        self.assertEqual(by_id["tr_b"]["stage_count"], 1)

    def test_limit_caps_result(self):
        day = "2026-06-13"
        traces = {}
        for i in range(5):
            traces[f"tr_{i}"] = [
                {"trace_id": f"tr_{i}", "stage": "auth", "ts_ns": i * 100},
            ]
        _seed_trace_files(day, traces)

        c = self._client()
        r = c.get("/admin/audit/recent-traces",
                  params={"api_key": self._api_key, "day": day,
                          "limit": 2},
                  headers=_admin_headers())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["traces"]), 2)


# ─── frontend structure tests ──────────────────────────────────────


class HtmlStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HTML.exists():
            raise unittest.SkipTest(f"reasoning-flow.html missing")
        cls.body = HTML.read_text(encoding="utf-8")

    def test_three_swimlanes_present(self):
        for phase_id in ("phase-retrieve", "phase-expand", "phase-verify"):
            self.assertIn(f'id="{phase_id}"', self.body,
                          f"missing swimlane: {phase_id}")

    def test_selector_present(self):
        for marker in ("flow-trace-input", "flow-load-btn",
                       "flow-refresh-btn", "flow-recent-list"):
            self.assertIn(marker, self.body)

    def test_detail_panel_present(self):
        for marker in ("flow-detail-panel", "flow-detail-content"):
            self.assertIn(marker, self.body)

    def test_no_technical_jargon(self):
        for term in ("trace_id 가 위조", "audit_log table",
                     "reconstruct_graph_at", "T7 supersede chain",
                     "JWT"):
            self.assertNotIn(term, self.body,
                             f"technical jargon leaked: {term!r}")

    def test_a11y_skip_link_and_roles(self):
        self.assertIn('class="skip-link"', self.body)
        self.assertEqual(self.body.count('role="region"'), 3)
        self.assertIn('aria-live="polite"', self.body)


class JsStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = JS.read_text(encoding="utf-8")

    def test_exposes_global(self):
        self.assertIn("window.JAMES_ReasoningFlow", self.body)
        for fn in ("loadRecentTraces", "loadTrace", "showStageDetail"):
            self.assertIn(fn, self.body)

    def test_stage_meta_covers_three_phases(self):
        for phase in ("'retrieve'", "'expand'", "'verify'"):
            self.assertIn(phase, self.body)

    def test_uses_canonical_endpoints(self):
        self.assertIn("/admin/audit/recent-traces", self.body)
        self.assertIn("/admin/trace/", self.body)


class CssStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = CSS.read_text(encoding="utf-8")

    def test_swimlane_selectors_present(self):
        for sel in (".swimlane", ".swimlane-header", ".swimlane-body",
                    ".stage-card", ".detail-stage-header",
                    ".flow-summary"):
            self.assertIn(sel, self.body, f"missing selector: {sel}")

    def test_44px_touch_target(self):
        self.assertIn("min-height: 44px", self.body)


class I18nKeysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = I18N.read_text(encoding="utf-8")

    def test_canonical_flow_keys_present_in_both_blocks(self):
        required = [
            "flow.page_title",
            "flow.title",
            "flow.intro",
            "flow.selector.title",
            "flow.selector.load",
            "flow.viz.title",
            "flow.phase.retrieve",
            "flow.phase.expand",
            "flow.phase.verify",
            "flow.detail.title",
            "admin.flow_link",
        ]
        for key in required:
            count = self.body.count(f"'{key}'")
            self.assertGreaterEqual(
                count, 2,
                f"i18n key {key!r} missing in EN or KO block "
                f"(count {count})",
            )


class EntryPointTests(unittest.TestCase):
    def test_admin_html_link(self):
        body = ADMIN_HTML.read_text(encoding="utf-8")
        self.assertIn('href="/admin/reasoning-flow"', body)
        self.assertIn('admin.flow_link', body)

    def test_server_route_registered(self):
        body = SERVER.read_text(encoding="utf-8")
        self.assertIn('@app.get("/admin/reasoning-flow"', body)
        self.assertIn("async def serve_reasoning_flow", body)


if __name__ == "__main__":
    unittest.main()
