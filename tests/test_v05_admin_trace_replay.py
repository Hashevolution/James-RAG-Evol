"""v0.5 Track F.1 TT.c — /admin/graph/trace-replay endpoint.

Surfaces the per-stage JSONL trace files (``core.observability``,
``/admin/trace/{trace_id}``) with a time-travel cutoff so the
dashboard can show "what the reasoner was doing at moment T".

Coverage:

* Route registered + admin-gated (employee JWT → 403).
* 404 on missing trace_id.
* No cutoff → every stage returned (parity with ``/admin/trace``).
* ISO cutoff → only stages with ``ts_ns <= cutoff_ns`` returned;
  ``replayed_count`` reflects the filter, ``total_count`` reflects
  the underlying file.
* 400 on malformed ``t``.
* ``day`` param honored (read from a tmp trace root).
* Determinism — same trace + same ``t`` → identical body.

Run:
  python -m unittest tests.test_v05_admin_trace_replay
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-trace-replay-endpoint-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


# ─── helpers ─────────────────────────────────────────────────────────


def _api_key() -> str:
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
    from core.auth import create_token
    return {"Authorization": f"Bearer {create_token('test-admin', 'admin')}"}


def _employee_headers() -> dict:
    from core.auth import create_token
    return {"Authorization": f"Bearer {create_token('test-employee', 'employee')}"}


def _ns_for_iso(iso: str) -> int:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _seed_trace(trace_id: str, day: str, stages: list) -> None:
    """Write a synthetic JSONL trace file under the current trace root."""
    import json
    from core.observability import _trace_root
    root = _trace_root() / day
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{trace_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for s in stages:
            f.write(json.dumps(s) + "\n")


# ─── tests ───────────────────────────────────────────────────────────


class TraceReplayBaseTests(unittest.TestCase):
    """Common setUp/tearDown — install a tmp trace root + JAMES_API_KEY."""

    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing; cannot exercise admin route")
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


class TraceReplayAdminGateTests(TraceReplayBaseTests):
    def test_employee_jwt_rejected(self):
        c = self._client()
        r = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key, "trace_id": "missing"},
            headers=_employee_headers(),
        )
        self.assertEqual(r.status_code, 403, r.text)

    def test_missing_trace_returns_404(self):
        c = self._client()
        r = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key,
                    "trace_id": "no-such-trace",
                    "day": "2026-06-01"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 404, r.text)
        self.assertIn("trace not found", r.json().get("detail", ""))


class TraceReplayRoundTripTests(TraceReplayBaseTests):
    """Filtering by ``t`` cutoff round-trips correctly."""

    def _seed_5_stages(self) -> tuple[str, str, list]:
        trace_id = "tr_test_abcdef0123"
        day = "2026-06-01"
        # 5 stages, one every 10 minutes starting 00:00 UTC. The
        # cutoff tests use a midpoint between stage 2 and stage 3.
        stages = []
        for i, (stage, offset_min) in enumerate([
            ("auth",     0),
            ("retrieve", 10),
            ("graph",    20),
            ("answer",   30),
            ("complete", 40),
        ]):
            iso = "2026-06-01T00:{0:02d}:00+00:00".format(offset_min)
            stages.append({
                "trace_id": trace_id,
                "stage":    stage,
                "ts_ns":    _ns_for_iso(iso),
                "order":    i,
            })
        _seed_trace(trace_id, day, stages)
        return trace_id, day, stages

    def test_no_cutoff_returns_all_stages(self):
        trace_id, day, stages = self._seed_5_stages()
        c = self._client()
        r = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key, "trace_id": trace_id,
                    "day": day},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["total_count"], 5)
        self.assertEqual(body["replayed_count"], 5)
        self.assertEqual(len(body["stages"]), 5)
        self.assertIsNone(body["t"])

    def test_cutoff_filters_later_stages(self):
        trace_id, day, _ = self._seed_5_stages()
        c = self._client()
        # Cutoff between stage 2 (10 min) and stage 3 (20 min).
        r = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key, "trace_id": trace_id,
                    "day": day, "t": "2026-06-01T00:15:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total_count"], 5)
        self.assertEqual(body["replayed_count"], 2)
        self.assertEqual(len(body["stages"]), 2)
        self.assertEqual(
            [s["stage"] for s in body["stages"]],
            ["auth", "retrieve"],
        )
        self.assertTrue(body["t"].startswith("2026-06-01T00:15:00"))

    def test_cutoff_at_exact_stage_includes_that_stage(self):
        trace_id, day, _ = self._seed_5_stages()
        c = self._client()
        # Cutoff exactly at stage 2's ts → inclusive (<=).
        r = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key, "trace_id": trace_id,
                    "day": day, "t": "2026-06-01T00:10:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["replayed_count"], 2)
        self.assertEqual(
            [s["stage"] for s in body["stages"]],
            ["auth", "retrieve"],
        )

    def test_cutoff_before_first_stage_returns_empty(self):
        trace_id, day, _ = self._seed_5_stages()
        c = self._client()
        r = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key, "trace_id": trace_id,
                    "day": day, "t": "2026-05-30T00:00:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total_count"], 5)
        self.assertEqual(body["replayed_count"], 0)
        self.assertEqual(body["stages"], [])

    def test_malformed_t_is_400(self):
        trace_id, day, _ = self._seed_5_stages()
        c = self._client()
        r = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key, "trace_id": trace_id,
                    "day": day, "t": "not-a-timestamp"},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 400, r.text)

    def test_determinism(self):
        trace_id, day, _ = self._seed_5_stages()
        c = self._client()
        r1 = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key, "trace_id": trace_id,
                    "day": day, "t": "2026-06-01T00:25:00Z"},
            headers=_admin_headers(),
        )
        r2 = c.get(
            "/admin/graph/trace-replay",
            params={"api_key": self._api_key, "trace_id": trace_id,
                    "day": day, "t": "2026-06-01T00:25:00Z"},
            headers=_admin_headers(),
        )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json(), r2.json())


if __name__ == "__main__":
    unittest.main()
