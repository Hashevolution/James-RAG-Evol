"""Admin dashboard load delay fix (item #2-A, 2026-05-08).

User feedback: "어드민 페이지로 이동할때 시간이 다소 딜레이".

Diagnosis: /admin/dashboard read entire JSONL audit logs line-by-
line, then sliced [-20:]. On a long-running install the file grows
indefinitely → load time scales with total file size even though only
the tail is needed.

Fix: `_read_jsonl_tail(path, max_lines)` seeks from EOF in 8KB chunks
until enough newlines are buffered. O(N) where N = max_lines, not
O(file size). Used in admin_dashboard to read the recent logs.

Tests cover:
  - Empty / missing files return [] (graceful)
  - Small files (smaller than max_lines) read whole
  - Large files read only the last max_lines entries
  - Each entry is JSON-decoded; malformed lines silently dropped
  - Order: oldest-first (matches prior caller expectation)
  - Performance smoke: a 50k-line file should complete in well under
    1 second (the prior whole-file read was the slow path)

Run:
  python -m unittest tests.test_admin_dashboard_tail
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class JsonlTailHelperTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Import lazily so the test file works even if server_llmwiki
        # has heavy boot-time effects.
        import server_llmwiki as srv
        cls.srv = srv

    def _write_jsonl(self, lines):
        """Write a temp file, return its path. Caller cleans up."""
        f = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".jsonl"
        )
        for line in lines:
            f.write(line + "\n")
        f.close()
        return f.name

    def test_helper_function_exists(self):
        self.assertTrue(hasattr(self.srv, "_read_jsonl_tail"),
                        "_read_jsonl_tail helper must exist")

    def test_missing_file_returns_empty(self):
        out = self.srv._read_jsonl_tail("/tmp/_nope_does_not_exist_.jsonl", 50)
        self.assertEqual(out, [])

    def test_empty_file_returns_empty(self):
        path = self._write_jsonl([])
        try:
            out = self.srv._read_jsonl_tail(path, 50)
            self.assertEqual(out, [])
        finally:
            os.unlink(path)

    def test_small_file_returns_all(self):
        path = self._write_jsonl([
            json.dumps({"i": 1}),
            json.dumps({"i": 2}),
            json.dumps({"i": 3}),
        ])
        try:
            out = self.srv._read_jsonl_tail(path, 50)
            self.assertEqual(len(out), 3)
            self.assertEqual([r["i"] for r in out], [1, 2, 3],
                "must preserve oldest-first ordering")
        finally:
            os.unlink(path)

    def test_large_file_returns_only_tail(self):
        # 1000 lines, ask for last 50.
        path = self._write_jsonl([json.dumps({"i": i}) for i in range(1000)])
        try:
            out = self.srv._read_jsonl_tail(path, 50)
            self.assertEqual(len(out), 50,
                f"must return exactly max_lines (got {len(out)})")
            # Last 50 should be 950..999 (oldest-first inside the tail).
            self.assertEqual(out[0]["i"], 950)
            self.assertEqual(out[-1]["i"], 999)
        finally:
            os.unlink(path)

    def test_malformed_lines_silently_skipped(self):
        path = self._write_jsonl([
            json.dumps({"i": 1}),
            "this is not json",
            json.dumps({"i": 2}),
            "{broken: ",
            json.dumps({"i": 3}),
        ])
        try:
            out = self.srv._read_jsonl_tail(path, 50)
            self.assertEqual([r["i"] for r in out], [1, 2, 3],
                "malformed lines must be silently dropped, valid kept")
        finally:
            os.unlink(path)

    def test_perf_50k_lines_under_one_second(self):
        # The whole point — fast even when the file is large.
        path = self._write_jsonl(
            [json.dumps({"i": i, "blocked": False}) for i in range(50000)]
        )
        try:
            t0 = time.perf_counter()
            out = self.srv._read_jsonl_tail(path, 200)
            dt = time.perf_counter() - t0
            self.assertEqual(len(out), 200)
            self.assertLess(dt, 1.0,
                f"50k-line tail read took {dt:.2f}s (expected < 1s) — "
                f"the whole point of this fix is sublinear in file size")
        finally:
            os.unlink(path)


class DashboardEndpointWiringTests(unittest.TestCase):
    """The endpoint should call the helper, not iterate the whole file."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def _endpoint_body(self) -> str:
        idx = self.src.index('@app.get("/admin/dashboard"')
        rest = self.src[idx + 1:]
        m = re.search(r"\n@app\.", rest)
        end = idx + 1 + m.start() if m else idx + 8000
        return self.src[idx:end]

    def test_uses_tail_helper(self):
        body = self._endpoint_body()
        self.assertIn("_read_jsonl_tail", body,
            "admin_dashboard must use the tail helper, not raw `for line in f`")

    def test_no_full_file_iteration(self):
        body = self._endpoint_body()
        # The old pattern — `with open(...) as f: for line in f` — should
        # be gone from the dashboard handler. Specifically the pattern
        # that was the slow path.
        self.assertNotIn("for line in f:\n                    try:\n                        e = json.loads(line)",
                         body,
                         "old full-file loop should be replaced by helper")


if __name__ == "__main__":
    unittest.main()
