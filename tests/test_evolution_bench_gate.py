"""Bench eval gate for self-evolution patches — #68 phase 2-A.

Coverage:
  - `run_bench_gate` returns `outcome_label='deployed'` on bench pass,
    `outcome_label='rolled_back'` on bench fail (with rollback fired).
  - `JAMES_EVOLUTION_GATE=0` skips the bench check; outcome_label is
    `deployed_gate_skipped` and `after_metrics={"gate":"skipped"}`.
  - `_summarize_report` produces the compact dict shape we ship to
    the audit log (small enough to keep `james_patch_log.jsonl`
    human-scannable).
  - `_latest_bench_report` picks the most-recent bench file by mtime
    and returns None when the reports/ dir is empty.
  - Source-level: `/admin/patch/approve` calls `run_bench_gate` and
    forwards `before_metrics`/`after_metrics`/`outcome` to
    `record_outcome`. A future refactor that drops the gate must
    consciously break this contract test.
  - Subprocess timeout / launch-failure paths fail-closed (gate
    treats them as regressions and rolls back).

Run:
  python -m unittest tests.test_evolution_bench_gate
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class GateEnabledEnvTests(unittest.TestCase):
    def setUp(self):
        self._orig = os.environ.get("JAMES_EVOLUTION_GATE")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("JAMES_EVOLUTION_GATE", None)
        else:
            os.environ["JAMES_EVOLUTION_GATE"] = self._orig

    def test_default_enabled(self):
        from tools.patch.bench_gate import _gate_enabled
        os.environ.pop("JAMES_EVOLUTION_GATE", None)
        self.assertTrue(_gate_enabled())

    def test_explicit_off_variants(self):
        from tools.patch.bench_gate import _gate_enabled
        for v in ("0", "false", "FALSE", "no", ""):
            os.environ["JAMES_EVOLUTION_GATE"] = v
            self.assertFalse(_gate_enabled(),
                             f"value {v!r} must disable the gate")

    def test_explicit_on_variants(self):
        from tools.patch.bench_gate import _gate_enabled
        for v in ("1", "true", "yes", "anything"):
            os.environ["JAMES_EVOLUTION_GATE"] = v
            self.assertTrue(_gate_enabled())


class TimeoutClampTests(unittest.TestCase):
    def setUp(self):
        self._orig = os.environ.get("JAMES_EVOLUTION_GATE_TIMEOUT_S")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("JAMES_EVOLUTION_GATE_TIMEOUT_S", None)
        else:
            os.environ["JAMES_EVOLUTION_GATE_TIMEOUT_S"] = self._orig

    def test_default_600(self):
        from tools.patch.bench_gate import _gate_timeout_s
        os.environ.pop("JAMES_EVOLUTION_GATE_TIMEOUT_S", None)
        self.assertEqual(_gate_timeout_s(), 600)

    def test_clamp_low(self):
        from tools.patch.bench_gate import _gate_timeout_s
        os.environ["JAMES_EVOLUTION_GATE_TIMEOUT_S"] = "5"
        self.assertEqual(_gate_timeout_s(), 30, "must clamp >= 30")

    def test_clamp_high(self):
        from tools.patch.bench_gate import _gate_timeout_s
        os.environ["JAMES_EVOLUTION_GATE_TIMEOUT_S"] = "99999"
        self.assertEqual(_gate_timeout_s(), 3600, "must clamp <= 3600")

    def test_garbage_falls_back_to_600(self):
        from tools.patch.bench_gate import _gate_timeout_s
        os.environ["JAMES_EVOLUTION_GATE_TIMEOUT_S"] = "not-a-number"
        self.assertEqual(_gate_timeout_s(), 600)


class ReportPickerTests(unittest.TestCase):
    """_latest_bench_report + _summarize_report shape contracts."""

    def test_latest_picks_most_recent(self):
        from tools.patch import bench_gate as bg
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            old = tdp / "bench_aaa_step7_20260101_000000.json"
            new = tdp / "bench_bbb_step7_20260507_120000.json"
            old.write_text("{}", encoding="utf-8")
            time.sleep(0.05)  # ensure mtime ordering
            new.write_text("{}", encoding="utf-8")
            with mock_patch.object(bg, "REPORTS_DIR", tdp):
                got = bg._latest_bench_report("step7")
                self.assertEqual(got, new)

    def test_latest_returns_none_when_empty(self):
        from tools.patch import bench_gate as bg
        with tempfile.TemporaryDirectory() as td:
            with mock_patch.object(bg, "REPORTS_DIR", Path(td)):
                self.assertIsNone(bg._latest_bench_report("step7"))

    def test_summarize_compact_shape(self):
        from tools.patch.bench_gate import _summarize_report
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({
                "git_sha": "abc1234",
                "total_seconds": 321.6,
                "queries": 3,
                "results": [
                    {"id": 1, "status": "ok", "blocked": False},
                    {"id": 2, "status": "ok", "blocked": True},
                    {"id": 3, "status": "error"},
                ],
            }, f)
            path = Path(f.name)
        try:
            s = _summarize_report(path)
            self.assertEqual(s["git_sha"], "abc1234")
            self.assertEqual(s["total_seconds"], 321.6)
            self.assertEqual(s["queries"], 3)
            self.assertEqual(s["ok"], 1)
            self.assertEqual(s["blocked"], 1)
            self.assertEqual(s["errors"], 1)
            self.assertIn(s["report_file"], path.name)
        finally:
            path.unlink(missing_ok=True)

    def test_summarize_handles_missing(self):
        from tools.patch.bench_gate import _summarize_report
        self.assertEqual(_summarize_report(None), {})
        self.assertEqual(_summarize_report(Path("/nonexistent/foo.json")), {})


class GateOutcomeTests(unittest.TestCase):
    """End-to-end on the gate orchestration. Mocks the subprocess
    runner so we don't actually need a live server."""

    def setUp(self):
        self._orig_gate = os.environ.get("JAMES_EVOLUTION_GATE")
        os.environ["JAMES_EVOLUTION_GATE"] = "1"

    def tearDown(self):
        if self._orig_gate is None:
            os.environ.pop("JAMES_EVOLUTION_GATE", None)
        else:
            os.environ["JAMES_EVOLUTION_GATE"] = self._orig_gate

    def _run(self, patch_id, target, suite="step7"):
        from tools.patch.bench_gate import run_bench_gate
        return asyncio.run(run_bench_gate(patch_id, target, suite=suite))

    def test_skipped_when_env_off(self):
        from tools.patch.bench_gate import run_bench_gate
        os.environ["JAMES_EVOLUTION_GATE"] = "0"
        result = self._run("p1", "./workspace/dummy.py")
        self.assertTrue(result.passed)
        self.assertEqual(result.outcome_label, "deployed_gate_skipped")
        self.assertEqual(result.after_metrics, {"gate": "skipped"})

    def test_passed_when_subprocess_returncode_0(self):
        from tools.patch import bench_gate as bg
        with mock_patch.object(
            bg, "_run_bench_check_blocking",
            return_value=(True, "ok"),
        ), mock_patch.object(
            bg, "_summarize_report",
            side_effect=[{"queries": 13, "ok": 11}, {"queries": 13, "ok": 11}],
        ):
            result = self._run("p1", "./workspace/dummy.py")
        self.assertTrue(result.passed)
        self.assertEqual(result.outcome_label, "deployed")
        self.assertEqual(result.after_metrics["queries"], 13)
        self.assertIn("bench gate passed", result.detail)

    def test_rollback_fired_on_subprocess_returncode_1(self):
        from tools.patch import bench_gate as bg
        # Stub restore_latest so we can assert it was called.
        called = {}
        def _fake_restore(target):
            called["target"] = target
            return True, "rollback ok"
        # Patch the lazy import target: tools.patch.patch_applier.restore_latest
        with mock_patch.object(
            bg, "_run_bench_check_blocking",
            return_value=(False, "q1: graph_paths=2 outside band"),
        ), mock_patch.object(
            bg, "_summarize_report",
            side_effect=[{"queries": 13}, {"queries": 13, "errors": 1}],
        ), mock_patch(
            "tools.patch.patch_applier.restore_latest", _fake_restore
        ):
            result = self._run("p1", "./workspace/dummy.py")
        self.assertFalse(result.passed)
        self.assertEqual(result.outcome_label, "rolled_back")
        self.assertEqual(called["target"], "./workspace/dummy.py")
        self.assertIn("rollback=ok", result.detail)
        self.assertIn("bench regression", result.detail)

    def test_rollback_failure_recorded_in_detail(self):
        from tools.patch import bench_gate as bg
        def _broken_restore(target):
            return False, "no backup found"
        with mock_patch.object(
            bg, "_run_bench_check_blocking",
            return_value=(False, "regression"),
        ), mock_patch.object(
            bg, "_summarize_report",
            return_value={},
        ), mock_patch(
            "tools.patch.patch_applier.restore_latest", _broken_restore
        ):
            result = self._run("p1", "./workspace/dummy.py")
        self.assertFalse(result.passed)
        self.assertEqual(result.outcome_label, "rolled_back")
        self.assertIn("rollback=FAIL", result.detail)
        self.assertIn("no backup found", result.detail)

    def test_subprocess_launch_failure_treated_as_regression(self):
        from tools.patch import bench_gate as bg
        # Real _run_bench_check_blocking with a bogus python path that
        # doesn't exist — subprocess.run raises FileNotFoundError.
        with mock_patch.object(bg, "sys") as mock_sys:
            mock_sys.executable = "/totally/not/a/real/python/binary"
            with mock_patch.object(bg, "_summarize_report", return_value={}), \
                 mock_patch("tools.patch.patch_applier.restore_latest",
                            return_value=(True, "ok")):
                result = self._run("p1", "./workspace/dummy.py")
            self.assertFalse(result.passed)
            self.assertEqual(result.outcome_label, "rolled_back")


class ApproveEndpointContractTests(unittest.TestCase):
    """Source-level: /admin/patch/approve must call run_bench_gate
    and pass before/after metrics into record_outcome."""

    def test_approve_endpoint_invokes_gate(self):
        import server_llmwiki as srv
        import inspect
        src = inspect.getsource(srv)
        self.assertIn("from tools.patch.bench_gate import run_bench_gate", src,
                      "/admin/patch/approve must import run_bench_gate")
        self.assertIn("await run_bench_gate(", src,
                      "approve handler must await run_bench_gate")
        self.assertIn("before_metrics=gate.before_metrics", src,
                      "approve handler must forward before_metrics")
        self.assertIn("after_metrics=gate.after_metrics", src,
                      "approve handler must forward after_metrics")
        self.assertIn("gate.outcome_label", src,
                      "approve handler must use gate.outcome_label, not its own ok/fail string")


if __name__ == "__main__":
    unittest.main()
