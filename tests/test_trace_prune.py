"""Trace file auto-prune — #81 phase 3-C.

Coverage:
  - `prune_old_traces` removes day-partitioned dirs strictly older
    than `today - keep_days`, keeps everything within the window.
  - `keep_days` clamped to [1, 365]; 0 / negative / garbage → safe
    defaults rather than wiping the entire directory.
  - Non-date directory names (e.g. an operator-created `archive/`)
    are skipped, never rmtree'd.
  - Empty / missing trace root → no exception, returns the documented
    shape.
  - Source-level: server_llmwiki.on_startup imports prune_old_traces
    and calls it with the JAMES_TRACE_RETENTION_DAYS env value.
  - Source-level: prune is wrapped in try so a housekeeping failure
    does not block server startup.

Run:
  python -m unittest tests.test_trace_prune
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PruneBasicTests(unittest.TestCase):
    def setUp(self):
        from core.observability import set_trace_root
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        set_trace_root(self.root)

    def tearDown(self):
        from core.observability import set_trace_root
        set_trace_root(None)
        self._tmp.cleanup()

    def _make_day_dir(self, day_offset: int, name: str = "trace.jsonl") -> Path:
        """Create a day directory `today + day_offset` with one file."""
        day = (datetime.now() - timedelta(days=-day_offset)).strftime("%Y-%m-%d") \
              if day_offset > 0 else \
              (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        # Simpler: always interpret offset as "days ago".
        day = (datetime.now() - timedelta(days=abs(day_offset))).strftime("%Y-%m-%d")
        d = self.root / day
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text("{}", encoding="utf-8")
        return d

    def test_missing_root_returns_documented_shape(self):
        from core.observability import prune_old_traces, set_trace_root
        # Set root to a path that doesn't exist.
        set_trace_root(Path(self._tmp.name) / "does-not-exist")
        result = prune_old_traces(keep_days=7)
        self.assertEqual(result, {"removed_days": [], "kept_days": [], "errors": []})

    def test_keeps_everything_within_window(self):
        from core.observability import prune_old_traces
        # Today + 1d ago + 6d ago all within 7-day keep window.
        for off in (0, 1, 6):
            self._make_day_dir(off)
        result = prune_old_traces(keep_days=7)
        self.assertEqual(result["removed_days"], [])
        self.assertEqual(len(result["kept_days"]), 3)
        # Files still on disk.
        for off in (0, 1, 6):
            day = (datetime.now() - timedelta(days=off)).strftime("%Y-%m-%d")
            self.assertTrue((self.root / day).exists(),
                            f"day {day} ({off}d old) must be kept")

    def test_removes_day_dirs_older_than_window(self):
        from core.observability import prune_old_traces
        self._make_day_dir(0)   # today — kept
        self._make_day_dir(7)   # exactly at boundary — kept (cutoff is strict <)
        self._make_day_dir(8)   # over boundary — removed
        self._make_day_dir(30)  # well over — removed
        result = prune_old_traces(keep_days=7)
        # 8d and 30d ago should be in removed_days; today + 7d ago kept.
        self.assertEqual(len(result["removed_days"]), 2)
        self.assertEqual(len(result["kept_days"]), 2)
        for off in (8, 30):
            day = (datetime.now() - timedelta(days=off)).strftime("%Y-%m-%d")
            self.assertFalse((self.root / day).exists(),
                             f"day {day} ({off}d old) must be removed")

    def test_keep_days_clamped_low_to_1(self):
        from core.observability import prune_old_traces
        self._make_day_dir(0)   # today — within any [1, 365] window
        self._make_day_dir(2)   # 2d ago — outside keep_days=1
        # keep_days=0 must clamp to 1, NOT wipe today.
        prune_old_traces(keep_days=0)
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertTrue((self.root / today).exists(),
                        "keep_days=0 must clamp to 1; today must survive")

    def test_keep_days_negative_clamped(self):
        from core.observability import prune_old_traces
        self._make_day_dir(0)
        prune_old_traces(keep_days=-100)
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertTrue((self.root / today).exists(),
                        "negative keep_days must not wipe today")

    def test_non_date_dir_skipped_not_deleted(self):
        from core.observability import prune_old_traces
        # An operator-created directory under reports/trace/ (e.g.
        # archive, backup) must NOT be deleted by the prune. Only
        # YYYY-MM-DD day partitions are eligible.
        weird = self.root / "operator-archive"
        weird.mkdir(parents=True, exist_ok=True)
        (weird / "important.json").write_text("{}", encoding="utf-8")
        result = prune_old_traces(keep_days=7)
        self.assertTrue(weird.exists(),
                        "non-date directories must never be removed")
        # The error log should mention it was skipped.
        self.assertTrue(any("operator-archive" in e for e in result["errors"]),
                        "skip should be logged for operator visibility")


class StartupHookContractTests(unittest.TestCase):
    """Source-level: server_llmwiki.on_startup imports prune_old_traces,
    reads JAMES_TRACE_RETENTION_DAYS, calls prune_old_traces, and the
    call is inside a try/except so housekeeping failure does not block
    startup."""

    def test_on_startup_invokes_prune(self):
        import server_llmwiki as srv
        import inspect
        src = inspect.getsource(srv.on_startup)
        self.assertIn("from core.observability import prune_old_traces", src,
                      "on_startup must import prune_old_traces")
        self.assertIn("JAMES_TRACE_RETENTION_DAYS", src,
                      "on_startup must read the retention env var")
        self.assertIn("prune_old_traces(keep_days=", src,
                      "on_startup must call prune_old_traces with keep_days kwarg")
        # Must be wrapped in try so housekeeping failure doesn't block startup.
        self.assertIn("except Exception", src,
                      "prune call must be inside a try/except — housekeeping "
                      "failures must never block server startup")


if __name__ == "__main__":
    unittest.main()
