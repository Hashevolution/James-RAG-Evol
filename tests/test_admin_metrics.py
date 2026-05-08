"""GET /admin/metrics endpoint + aggregate_metrics — #81 phase 3-B.

Coverage:
  - `_percentile`: nearest-rank rules at 0/50/90/99/100, single-element
    list, empty list (no division-by-zero crash).
  - `_stage_latencies_from_trace`: ns-delta math, defensive sort on
    permuted entries, single-entry trace returns empty, explicit
    `latency_ms` on the last entry contributes a sample.
  - `aggregate_metrics`: window cutoff filters out old day-dirs and
    pre-cutoff lines, stage filter restricts output, repeated stage
    occurrences accumulate samples, malformed file is skipped silently.
  - `/admin/metrics` endpoint: source contract (registered + admin
    gate + response shape) and behavioral roundtrip via TestClient.

Run:
  python -m unittest tests.test_admin_metrics
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _admin_key() -> str:
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


def _write_trace_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


class PercentileTests(unittest.TestCase):
    def test_empty_returns_zero_no_crash(self):
        from core.trace_metrics import _percentile
        self.assertEqual(_percentile([], 50), 0.0)
        self.assertEqual(_percentile([], 99), 0.0)

    def test_single_element_returns_that_element(self):
        from core.trace_metrics import _percentile
        for p in (0, 50, 90, 99, 100):
            self.assertEqual(_percentile([42.0], p), 42.0)

    def test_p0_and_p100_clamp_to_endpoints(self):
        from core.trace_metrics import _percentile
        vs = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertEqual(_percentile(vs, 0), 1.0)
        self.assertEqual(_percentile(vs, 100), 5.0)
        self.assertEqual(_percentile(vs, -10), 1.0,
                         "negative percentile clamps to first")
        self.assertEqual(_percentile(vs, 200), 5.0)

    def test_p50_known_value(self):
        from core.trace_metrics import _percentile
        # 10 values: nearest-rank p50 = ceil(0.5 * 10) = 5th element.
        vs = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        self.assertEqual(_percentile(vs, 50), 50)
        self.assertEqual(_percentile(vs, 90), 90)
        self.assertEqual(_percentile(vs, 99), 100)


class StageLatencyDerivationTests(unittest.TestCase):
    def test_two_entries_yield_one_sample(self):
        from core.trace_metrics import _stage_latencies_from_trace
        out = _stage_latencies_from_trace([
            {"stage": "auth",     "ts_ns": 1_000_000_000},     # t=1.0s
            {"stage": "retrieve", "ts_ns": 1_500_000_000},     # t=1.5s
        ])
        # Latency for `auth` is the gap to the next stage = 500ms.
        self.assertIn("auth", out)
        self.assertEqual(len(out["auth"]), 1)
        self.assertAlmostEqual(out["auth"][0], 500.0, places=2)

    def test_single_entry_yields_no_samples(self):
        from core.trace_metrics import _stage_latencies_from_trace
        # Only one entry → no delta possible → empty (unless an
        # explicit latency_ms is present).
        out = _stage_latencies_from_trace([
            {"stage": "auth", "ts_ns": 1_000_000_000},
        ])
        self.assertEqual(out, {})

    def test_repeated_stage_accumulates(self):
        from core.trace_metrics import _stage_latencies_from_trace
        # retrieve appears twice (e.g. loop iteration).
        out = _stage_latencies_from_trace([
            {"stage": "retrieve", "ts_ns": 0},
            {"stage": "graph",    "ts_ns": 100_000_000},   # +100ms
            {"stage": "retrieve", "ts_ns": 200_000_000},   # +100ms
            {"stage": "answer",   "ts_ns": 500_000_000},   # +300ms
        ])
        # retrieve (1st) → graph: 100ms; retrieve (2nd) → answer: 300ms
        self.assertEqual(len(out["retrieve"]), 2)
        self.assertAlmostEqual(out["retrieve"][0], 100.0, places=2)
        self.assertAlmostEqual(out["retrieve"][1], 300.0, places=2)
        self.assertEqual(len(out["graph"]), 1)
        self.assertAlmostEqual(out["graph"][0], 100.0, places=2)

    def test_explicit_latency_ms_on_last_entry(self):
        from core.trace_metrics import _stage_latencies_from_trace
        out = _stage_latencies_from_trace([
            {"stage": "auth",   "ts_ns": 0},
            {"stage": "answer", "ts_ns": 1_000_000_000, "latency_ms": 1820.5},
        ])
        # answer is the last → its explicit latency_ms is added as a sample.
        self.assertIn("answer", out)
        self.assertAlmostEqual(out["answer"][0], 1820.5, places=2)

    def test_defensive_sort_on_permuted_entries(self):
        from core.trace_metrics import _stage_latencies_from_trace
        # Same trace data as test_two_entries but written out-of-order.
        out = _stage_latencies_from_trace([
            {"stage": "retrieve", "ts_ns": 1_500_000_000},
            {"stage": "auth",     "ts_ns": 1_000_000_000},
        ])
        # Defensive sort restores order → auth → retrieve = 500ms.
        self.assertIn("auth", out)
        self.assertAlmostEqual(out["auth"][0], 500.0, places=2)


class AggregateMetricsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_today_trace(self, tid: str, entries: list[dict]) -> None:
        day = datetime.now().strftime("%Y-%m-%d")
        _write_trace_jsonl(self.root / day / f"{tid}.jsonl", entries)

    def _ts(self, offset_ms: int = 0) -> int:
        # ts_ns = now + offset (handy for "this happened recently").
        return int(time.time() * 1_000_000_000) + offset_ms * 1_000_000

    def test_empty_root_returns_empty_dict(self):
        from core.trace_metrics import aggregate_metrics
        self.assertEqual(aggregate_metrics(trace_root=self.root), {})

    def test_single_trace_produces_stats(self):
        from core.trace_metrics import aggregate_metrics
        # Two stages 100ms apart.
        self._write_today_trace("t1", [
            {"trace_id": "t1", "stage": "auth",     "ts_ns": self._ts(0)},
            {"trace_id": "t1", "stage": "retrieve", "ts_ns": self._ts(100)},
        ])
        out = aggregate_metrics(trace_root=self.root)
        self.assertIn("auth", out)
        self.assertEqual(out["auth"]["count"], 1)
        self.assertAlmostEqual(out["auth"]["p50_ms"], 100.0, delta=1.0)

    def test_multiple_traces_accumulate(self):
        from core.trace_metrics import aggregate_metrics
        # Three traces, retrieve gap of 50/100/150 ms.
        for i, gap_ms in enumerate((50, 100, 150)):
            self._write_today_trace(f"t{i}", [
                {"trace_id": f"t{i}", "stage": "retrieve", "ts_ns": self._ts(0)},
                {"trace_id": f"t{i}", "stage": "answer",   "ts_ns": self._ts(gap_ms)},
            ])
        out = aggregate_metrics(trace_root=self.root)
        self.assertEqual(out["retrieve"]["count"], 3)
        # p50 is the middle (nearest-rank ceil(0.5*3) = 2nd) = 100.
        self.assertAlmostEqual(out["retrieve"]["p50_ms"], 100.0, delta=1.0)
        # max is 150.
        self.assertAlmostEqual(out["retrieve"]["max_ms"], 150.0, delta=1.0)

    def test_stage_filter_restricts_output(self):
        from core.trace_metrics import aggregate_metrics
        self._write_today_trace("t1", [
            {"trace_id": "t1", "stage": "retrieve", "ts_ns": self._ts(0)},
            {"trace_id": "t1", "stage": "graph",    "ts_ns": self._ts(50)},
            {"trace_id": "t1", "stage": "answer",   "ts_ns": self._ts(150)},
        ])
        out = aggregate_metrics(trace_root=self.root, stage_filter="retrieve")
        self.assertEqual(set(out.keys()), {"retrieve"},
                         "stage_filter must restrict to one stage")

    def test_window_cutoff_excludes_old_lines(self):
        from core.trace_metrics import aggregate_metrics
        # Write a trace with ts_ns from 25 hours ago (outside default 24h window).
        old_ns = int((time.time() - 25 * 3600) * 1_000_000_000)
        self._write_today_trace("old1", [
            {"trace_id": "old1", "stage": "auth",     "ts_ns": old_ns},
            {"trace_id": "old1", "stage": "retrieve", "ts_ns": old_ns + 100_000_000},
        ])
        out = aggregate_metrics(window_hours=24, trace_root=self.root)
        # Both entries are pre-cutoff → no auth samples.
        self.assertNotIn("auth", out)

    def test_old_day_directory_skipped(self):
        from core.trace_metrics import aggregate_metrics
        old_day = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        _write_trace_jsonl(
            self.root / old_day / "old.jsonl",
            [{"trace_id": "old", "stage": "auth",     "ts_ns": 1},
             {"trace_id": "old", "stage": "retrieve", "ts_ns": 2}],
        )
        out = aggregate_metrics(window_hours=24, trace_root=self.root)
        self.assertEqual(out, {},
                         "day directory before cutoff must be skipped entirely")

    def test_malformed_jsonl_line_skipped_silently(self):
        from core.trace_metrics import aggregate_metrics
        day = datetime.now().strftime("%Y-%m-%d")
        path = self.root / day / "t.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"trace_id": "t", "stage": "auth", "ts_ns": self._ts(0)}) + "\n")
            f.write("{ broken jsonl line\n")
            f.write(json.dumps({"trace_id": "t", "stage": "retrieve", "ts_ns": self._ts(100)}) + "\n")
        out = aggregate_metrics(trace_root=self.root)
        # Should still produce one auth sample despite the broken line.
        self.assertIn("auth", out)
        self.assertEqual(out["auth"]["count"], 1)

    def test_window_clamped_to_max(self):
        # window=99999 → clamped to 168 inside, no exception.
        from core.trace_metrics import aggregate_metrics
        out = aggregate_metrics(window_hours=99999, trace_root=self.root)
        self.assertIsInstance(out, dict)


class AdminMetricsEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._api_key = _admin_key()
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing; cannot exercise admin route")

    def tearDown(self):
        self._tmp.cleanup()

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def test_route_registered_and_admin_gated(self):
        import server_llmwiki as srv
        import inspect
        src = inspect.getsource(srv)
        self.assertIn('@app.get("/admin/metrics"', src)
        self.assertIn("from core.trace_metrics import aggregate_metrics", src)
        idx = src.index('@app.get("/admin/metrics"')
        window = src[idx:idx + 1500]
        self.assertIn("_require_admin(api_key, role)", window)
        self.assertIn("aggregate_metrics(", window)
        # Response shape contract.
        for key in ('"window_hours"', '"stage_filter"', '"stages"'):
            self.assertIn(key, window)

    def test_admin_gate_rejects_missing_jwt(self):
        client = self._client()
        r = client.get("/admin/metrics", params={"api_key": self._api_key})
        # No Bearer token → role becomes "employee" not "admin" → 403.
        self.assertEqual(r.status_code, 403)

    def test_endpoint_returns_documented_shape(self):
        # No traces in tmpdir; the response shape is still well-defined
        # (stages={}). We patch the trace root by monkeypatching the
        # aggregate_metrics call site? Simpler: inject via the public
        # function with a mocked trace_root not visible from the route.
        # Instead, just hit the live route and assert shape — empty
        # 'stages' is fine.
        client = self._client()
        r = client.get(
            "/admin/metrics",
            params={"api_key": self._api_key, "window_hours": 24},
            headers=_admin_headers(),
        )
        self.assertEqual(r.status_code, 200, f"got {r.status_code}: {r.text}")
        body = r.json()
        self.assertEqual(body["window_hours"], 24)
        self.assertEqual(body["stage_filter"], "")
        self.assertIsInstance(body["stages"], dict)


if __name__ == "__main__":
    unittest.main()
