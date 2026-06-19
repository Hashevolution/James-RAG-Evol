"""v0.6.1 Phase 5a — Phase 4 gate wired into the cloud egress site.

Verifies the live wire in
``scripts/research/local_vs_cloud_paired.call_cloud_via_abstraction``:

1. With default env (force_local OFF + no cap), the gate is a pure
   no-op — the function reaches the cloud backend call as before.
2. ``JAMES_PRIVACY_FORCE_LOCAL=1`` + PII in prompt → RuntimeError
   "cloud refused by privacy gate".
3. ``JAMES_COST_CAP_MONTHLY_USD`` exceeded → RuntimeError
   "cloud refused by cost cap".
4. Source-level: the function MUST import ``check_query_privacy`` +
   ``check_cap`` from ``core.routing`` and refuse on a positive
   outcome. The source check guards the wire site against accidental
   removal in a future cleanup.

Cloud is never actually called in any of these tests — the gate
refuses before the abstraction module is even imported.
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "research"),
)


def _fresh_harness():
    """Re-import the harness so env changes between tests are
    picked up (the routing primitives resolve env at call time, but
    re-import keeps the test boundary clean)."""
    if "local_vs_cloud_paired" in sys.modules:
        return importlib.reload(sys.modules["local_vs_cloud_paired"])
    return importlib.import_module("local_vs_cloud_paired")


class PrivacyGateRefusalTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            k: os.environ.pop(k)
            for k in ("JAMES_PRIVACY_FORCE_LOCAL",
                      "JAMES_COST_CAP_MONTHLY_USD")
            if k in os.environ
        }

    def tearDown(self):
        for k in ("JAMES_PRIVACY_FORCE_LOCAL",
                  "JAMES_COST_CAP_MONTHLY_USD"):
            os.environ.pop(k, None)
        for k, v in self._env.items():
            os.environ[k] = v

    def test_privacy_gate_blocks_when_flag_on_and_pii_present(self):
        os.environ["JAMES_PRIVACY_FORCE_LOCAL"] = "1"
        harness = _fresh_harness()
        with self.assertRaises(RuntimeError) as ctx:
            harness.call_cloud_via_abstraction(
                prompt="주민번호 900101-1234567 의 의미",
            )
        self.assertIn("privacy gate", str(ctx.exception))

    def test_privacy_gate_silent_when_flag_off(self):
        # With the flag OFF (default), the gate must reach the
        # downstream egress call without raising. We mock
        # ``run_cloud_egress`` so the test is hermetic — no real
        # cloud backend reachable from CI.
        os.environ.pop("JAMES_PRIVACY_FORCE_LOCAL", None)
        harness = _fresh_harness()
        from unittest import mock

        class _Result:
            text = "answer"
            error = ""

        fake_egress = mock.MagicMock(return_value=(_Result(), []))
        # Patch the symbol on the abstraction module so the harness's
        # local import (``from core.abstraction import ...``) picks
        # the mock up.
        with mock.patch(
            "core.abstraction.run_cloud_egress",
            fake_egress,
        ):
            out = harness.call_cloud_via_abstraction(
                prompt="주민번호 900101-1234567 의 의미",
            )
        self.assertEqual(out, "answer")
        fake_egress.assert_called_once()


class CostCapRefusalTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            k: os.environ.pop(k)
            for k in ("JAMES_COST_CAP_MONTHLY_USD",
                      "JAMES_COST_CAP_FILE")
            if k in os.environ
        }
        import tempfile
        self.tmpdir = tempfile.mkdtemp(prefix="phase5a_cap_")
        self.tally = os.path.join(self.tmpdir, ".james_cost.json")
        os.environ["JAMES_COST_CAP_FILE"] = self.tally

    def tearDown(self):
        for k in ("JAMES_COST_CAP_MONTHLY_USD",
                  "JAMES_COST_CAP_FILE"):
            os.environ.pop(k, None)
        for k, v in self._env.items():
            os.environ[k] = v
        for f in os.listdir(self.tmpdir):
            try:
                os.remove(os.path.join(self.tmpdir, f))
            except OSError:
                pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def test_cost_cap_blocks_when_projection_exceeds(self):
        os.environ["JAMES_COST_CAP_MONTHLY_USD"] = "1.0"
        harness = _fresh_harness()
        # usd_estimate forces the cap projection to fail.
        with self.assertRaises(RuntimeError) as ctx:
            harness.call_cloud_via_abstraction(
                prompt="benign question",
                tokens_estimate=100,
                usd_estimate=5.0,
            )
        self.assertIn("cost cap", str(ctx.exception))


class WireSourceInvariantTests(unittest.TestCase):
    """The Phase 5a wire MUST stay at the call site. A future cleanup
    PR that accidentally removes the gate is caught here."""

    @classmethod
    def setUpClass(cls):
        harness = _fresh_harness()
        cls.src = inspect.getsource(harness.call_cloud_via_abstraction)

    def test_imports_routing_primitives(self):
        self.assertIn("from core.routing import", self.src,
                      "Phase 5a wire missing: routing import dropped")

    def test_calls_check_query_privacy(self):
        self.assertIn("check_query_privacy(", self.src,
                      "Phase 5a wire missing: privacy gate dropped")

    def test_calls_check_cap(self):
        self.assertIn("check_cap(", self.src,
                      "Phase 5a wire missing: cost cap dropped")

    def test_refuses_on_force_local(self):
        self.assertIn("force_local", self.src,
                      "Phase 5a wire missing: force_local refusal")

    def test_refuses_on_over_cap(self):
        self.assertIn("under_cap", self.src,
                      "Phase 5a wire missing: under_cap refusal")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
