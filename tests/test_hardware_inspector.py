"""hardware_inspector._get_gpu — debug-trail + fallback ordering.

Coverage:
  - On a real machine the call returns either {found: True} via
    one of the three fallbacks, or {found: False} with a non-empty
    `debug` trail. Either way it MUST NOT raise.
  - The `debug` field is always a list (added in this PR — replaces
    silent `except: pass`).
  - JAMES_HW_DEBUG=1 mirrors trace lines to stdout (operator workflow).

Run:
  python -m unittest tests.test_hardware_inspector
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


class GpuDebugTrailTests(unittest.TestCase):
    def setUp(self):
        self._orig = os.environ.get("JAMES_HW_DEBUG")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("JAMES_HW_DEBUG", None)
        else:
            os.environ["JAMES_HW_DEBUG"] = self._orig

    def test_returns_dict_with_required_keys(self):
        from tools.system.hardware_inspector import _get_gpu
        r = _get_gpu()
        for k in ("name", "vram_gb", "found", "debug"):
            self.assertIn(k, r, f"missing key: {k}")
        self.assertIsInstance(r["debug"], list,
                              "debug field must be a list (was added "
                              "in this PR — silent except replacement)")

    def test_debug_trail_non_empty_on_any_outcome(self):
        # Either at least one fallback wrote a trace line, or all
        # three exhausted (still a non-empty trail). The bug we're
        # guarding against is silent-everything → impossible to diagnose.
        from tools.system.hardware_inspector import _get_gpu
        r = _get_gpu()
        self.assertGreater(len(r["debug"]), 0,
                           "debug trail must record at least one trace "
                           "line; silent fallback was the v0.2.0 bug")

    def test_stdout_silent_when_env_off(self):
        from tools.system.hardware_inspector import _get_gpu
        os.environ.pop("JAMES_HW_DEBUG", None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            _get_gpu()
        self.assertNotIn("[HW_GPU]", buf.getvalue(),
                         "trace must not leak to stdout when env unset")

    def test_stdout_mirrors_when_env_on(self):
        from tools.system.hardware_inspector import _get_gpu
        os.environ["JAMES_HW_DEBUG"] = "1"
        buf = io.StringIO()
        with redirect_stdout(buf):
            _get_gpu()
        self.assertIn("[HW_GPU]", buf.getvalue(),
                      "JAMES_HW_DEBUG=1 must mirror trace to stdout")

    def test_does_not_raise(self):
        # Hard contract: regardless of platform / driver state,
        # _get_gpu never raises. /hardware/ endpoint depends on this.
        from tools.system.hardware_inspector import _get_gpu
        try:
            _get_gpu()
        except Exception as e:
            self.fail(f"_get_gpu raised: {type(e).__name__}: {e}")


if __name__ == "__main__":
    unittest.main()
