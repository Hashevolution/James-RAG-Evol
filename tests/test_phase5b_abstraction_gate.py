"""v0.6.1 Phase 5b — defense-in-depth gate inside run_cloud_egress.

§5.7.13 caller obligation #1 puts PolicyEngine gating on the caller
side. Phase 5a wired the gate at
`local_vs_cloud_paired.call_cloud_via_abstraction`. Phase 5b adds a
runner-side re-check so a future caller that bypasses the §5.7.13 §1
obligation still cannot egress when the operator has opted in.

Verified:

1. Default OFF / no-cap → byte-identical to pre-5b (backend is
   called as before; the gate is a pure no-op).
2. `JAMES_PRIVACY_FORCE_LOCAL=1` + PII in prompt → backend NOT
   called; returned CompletionResult.error starts with
   "refused: privacy gate".
3. `JAMES_COST_CAP_MONTHLY_USD` exceeded → backend NOT called;
   CompletionResult.error starts with "refused: cost cap".
4. Source-level: the imports + the two gate branches MUST stay
   present at the top of run_cloud_egress so a future cleanup that
   accidentally removes them is caught at PR time.

All behaviour tests use a stub backend so no real cloud is reached.
"""
from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from unittest import mock

from core.abstraction import run_cloud_egress
from core.abstraction._policy import default_decider
from core.reasoning.backends import CompletionResult


class _StubBackend:
    """Minimal backend that records whether it was called.

    Mirrors the `Backend` protocol just enough for `run_cloud_egress`
    (a `backend_id` attribute + a `complete(...)` method returning a
    `CompletionResult`).
    """

    backend_id = "stub_cloud"

    def __init__(self):
        self.calls = 0

    def complete(self, masked_prompt, **_):
        self.calls += 1
        return CompletionResult(
            text="ok",
            backend_id=self.backend_id,
        )


class GatePassThroughTests(unittest.TestCase):
    """Default env → byte-identical no-op (backend is called)."""

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

    def test_default_passes_through_to_backend(self):
        be = _StubBackend()
        result, flagged = run_cloud_egress(
            backend=be, prompt="benign question with no PII",
            entities=[], decider=default_decider(),
        )
        self.assertEqual(be.calls, 1, "backend must be called when "
                         "gate is OFF")
        self.assertEqual(result.error, "")
        self.assertEqual(flagged, [])


class PrivacyGateRefusalTests(unittest.TestCase):
    """Runner-side privacy gate trips on PII when the env flag is ON."""

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

    def test_privacy_refusal_skips_backend(self):
        os.environ["JAMES_PRIVACY_FORCE_LOCAL"] = "1"
        be = _StubBackend()
        result, flagged = run_cloud_egress(
            backend=be,
            prompt="주민번호 900101-1234567 의 의미",
            entities=[], decider=default_decider(),
        )
        self.assertEqual(be.calls, 0,
                         "privacy refusal must not call the backend")
        self.assertTrue(result.error.startswith("refused: privacy gate"),
                        f"error did not match: {result.error!r}")
        self.assertEqual(flagged, [])

    def test_privacy_off_with_pii_still_calls_backend(self):
        """Flag OFF (default) — PII present but gate does not block."""
        os.environ.pop("JAMES_PRIVACY_FORCE_LOCAL", None)
        be = _StubBackend()
        result, _ = run_cloud_egress(
            backend=be,
            prompt="주민번호 900101-1234567 의 의미",
            entities=[], decider=default_decider(),
        )
        self.assertEqual(be.calls, 1)
        self.assertEqual(result.error, "")


class CostCapRefusalTests(unittest.TestCase):
    """Runner-side cost cap trips when the projection exceeds."""

    def setUp(self):
        self._env = {
            k: os.environ.pop(k)
            for k in ("JAMES_COST_CAP_MONTHLY_USD",
                      "JAMES_COST_CAP_FILE")
            if k in os.environ
        }
        self.tmpdir = tempfile.mkdtemp(prefix="phase5b_cap_")
        os.environ["JAMES_COST_CAP_FILE"] = os.path.join(
            self.tmpdir, ".james_cost.json"
        )

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

    def test_cost_cap_with_prefilled_tally_blocks(self):
        """Pre-fill the tally over the cap, then run egress —
        check_cap snapshots the existing usd_est >= cap and refuses."""
        from core.routing import CostBudget
        budget = CostBudget(
            os.environ["JAMES_COST_CAP_FILE"], cap_usd=1.0,
        )
        budget.record(tokens=0, usd_est=2.0)  # over-cap pre-load
        os.environ["JAMES_COST_CAP_MONTHLY_USD"] = "1.0"
        be = _StubBackend()
        result, _ = run_cloud_egress(
            backend=be, prompt="benign question",
            entities=[], decider=default_decider(),
        )
        self.assertEqual(be.calls, 0,
                         "cost-cap refusal must not call the backend")
        self.assertTrue(result.error.startswith("refused: cost cap"),
                        f"error did not match: {result.error!r}")


class WireSourceInvariantTests(unittest.TestCase):
    """Source-level: the Phase 5b gate MUST stay at the runner entry.
    A future cleanup that drops the imports or the two branches is
    caught here."""

    @classmethod
    def setUpClass(cls):
        cls.src = inspect.getsource(run_cloud_egress)

    def test_imports_check_query_privacy(self):
        self.assertIn("check_query_privacy", self.src,
                      "Phase 5b wire missing: privacy gate import")

    def test_imports_check_cap(self):
        self.assertIn("check_cap", self.src,
                      "Phase 5b wire missing: cost cap import")

    def test_emits_refused_privacy_audit_reason(self):
        self.assertIn("refused_privacy_gate", self.src,
                      "Phase 5b wire missing: privacy audit reason")

    def test_emits_refused_cost_cap_audit_reason(self):
        self.assertIn("refused_cost_cap", self.src,
                      "Phase 5b wire missing: cost-cap audit reason")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
