"""v0.4 Sprint 3 #7a — Planner D1 adaptive-budget + retry wiring.

Mirrors the existing query_rewriter D1+D6 wiring (PR #486 / D6 cycle,
PR #461 / D1.B) on the Planner stage. Before this PR, the Planner held
``self._max_tokens = 4096`` so:

  - it never participated in D1 adaptive budgeting — every planning
    call paid CAP_HEAVY (4096) even on trivial queries.
  - it never participated in D6 retry — ``complete_with_retry`` is a
    no-op when cap == CAP_HEAVY (already at the ceiling), so wiring
    it through would have changed nothing.

This PR makes both wirings *available* — gated behind
``JAMES_ADAPTIVE_BUDGET=1`` like query_rewriter, so flag-off behaviour
is byte-identical to pre-#7a.

Contract pinned here
  1. Flag OFF + default constructor → cap is DEFAULT_MAX_TOKENS=4096
     (byte-identical to pre-#7a). No D1 / D6 surface change.
  2. Flag OFF + explicit `max_tokens=N` → cap is N (baseline / unit
     test path). No D1 / D6 surface change.
  3. Flag ON + default constructor → cap is TaskBudget.assess(
     "planner", prompt). Light prompt → CAP_LIGHT=1200; heavy
     marker → CAP_HEAVY=4096.
  4. Flag ON + truncated response (done_reason="length") → retry
     once with doubled cap (complete_with_retry path).
  5. The D5 router gets the adaptive cap as `budget_signal` when D1
     is active, and `None` when off — preserves the "no fake signal
     under flag-off" invariant.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.reasoning.budget import (  # noqa: E402
    CAP_HEAVY,
    CAP_LIGHT,
)


class _PlannerCallCapture:
    """Records every backend.complete call so the test can assert the
    cap and decide what to return (first call vs retry)."""

    def __init__(self, *, plan_json='{"subtasks": ["a", "b"], "rationale": "ok"}',
                 done_reasons=None):
        self.calls = []
        self.plan_json = plan_json
        # done_reasons is a list of strings to return for successive
        # calls. Default: all "stop" → no retry.
        self.done_reasons = list(done_reasons or [])

    def complete(self, prompt, *, max_tokens, timeout, **opts):
        idx = len(self.calls)
        self.calls.append({
            "prompt": prompt,
            "max_tokens": max_tokens,
            "timeout": timeout,
            "opts": opts,
        })
        dr = (
            self.done_reasons[idx]
            if idx < len(self.done_reasons)
            else "stop"
        )
        return SimpleNamespace(
            text=self.plan_json,
            error="",
            done_reason=dr,
            latency_ms=10,
            backend_id="ollama_local",
        )


class PlannerD1WiringTests(unittest.TestCase):

    QUERY = "비트코인 ETF 가격 분석 방법을 단계별로 설명해줘"  # heavy marker "단계"

    def setUp(self):
        self._orig_budget = os.environ.get("JAMES_ADAPTIVE_BUDGET")
        self._orig_planner = os.environ.get("JAMES_ENABLE_PLANNER")
        # Planner has its own opt-in (JAMES_ENABLE_PLANNER) separate
        # from D1 — enable it for the duration of the test class.
        os.environ["JAMES_ENABLE_PLANNER"] = "1"

    def tearDown(self):
        for key, val in (
            ("JAMES_ADAPTIVE_BUDGET", self._orig_budget),
            ("JAMES_ENABLE_PLANNER", self._orig_planner),
        ):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _run_planner(self, capture, **planner_kwargs):
        from core.reasoning.planner import Planner
        planner = Planner(**planner_kwargs)
        with patch("core.reasoning.backends.get_backend", return_value=capture), \
             patch("core.reasoning.router.resolve_backend",
                   side_effect=lambda *_a, **kw: kw.get("fallback_backend_id", "ollama_local")), \
             patch("core.reasoning.router.emit_route_event", return_value=None), \
             patch("core.reasoning.trace_schema.emit_trace_step", return_value=True):
            return planner.plan(self.QUERY, force=True)

    def test_flag_off_default_cap_unchanged(self):
        """Path #3 in the docstring — flag off, default ctor → 4096."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "0"
        cap = _PlannerCallCapture()
        self._run_planner(cap)
        self.assertEqual(len(cap.calls), 1,
            "Default-off path should call backend.complete exactly once")
        self.assertEqual(cap.calls[0]["max_tokens"], 4096,
            "JAMES_ADAPTIVE_BUDGET=0 with default ctor must keep the "
            "pre-#7a cap of 4096 — byte-identical invariant.")

    def test_flag_off_explicit_max_tokens_honoured(self):
        """Path #2 — explicit int bypasses TaskBudget entirely."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"  # flag on, but explicit cap wins
        cap = _PlannerCallCapture()
        self._run_planner(cap, max_tokens=600)
        self.assertEqual(cap.calls[0]["max_tokens"], 600,
            "Explicit max_tokens must override the adaptive heuristic "
            "(matches query_rewriter D1.B contract).")

    def test_flag_on_heavy_query_caps_at_heavy(self):
        """Path #3 with heavy marker — assess returns CAP_HEAVY."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _PlannerCallCapture()
        self._run_planner(cap)
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_HEAVY,
            "단계 in the query is a heavy-synthesis marker; "
            "TaskBudget.assess should return CAP_HEAVY (4096).")

    def test_flag_on_light_query_caps_at_light(self):
        """Light prompt → CAP_LIGHT (no heavy marker present)."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _PlannerCallCapture()
        from core.reasoning.planner import Planner
        light_q = "What is Palantir's primary business model"
        planner = Planner()
        with patch("core.reasoning.backends.get_backend", return_value=cap), \
             patch("core.reasoning.router.resolve_backend",
                   side_effect=lambda *_a, **kw: kw.get("fallback_backend_id", "ollama_local")), \
             patch("core.reasoning.router.emit_route_event", return_value=None), \
             patch("core.reasoning.trace_schema.emit_trace_step", return_value=True):
            planner.plan(light_q, force=True)
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_LIGHT,
            "Light query with no heavy markers → CAP_LIGHT=1200")

    def test_flag_on_retry_fires_on_length_truncation(self):
        """Path #4 — done_reason='length' triggers complete_with_retry's
        single retry at doubled cap (1200 → 2400 here).

        Uses a query without heavy markers so the assess returns
        CAP_LIGHT; heavy markers would push to CAP_HEAVY (the ceiling)
        where retry would be a no-op."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _PlannerCallCapture(
            done_reasons=["length", "stop"],
        )
        from core.reasoning.planner import Planner
        # No heavy markers ("compare" / "decompose" / "step" / "단계"
        # / "분석" etc.) — picks CAP_LIGHT path.
        light_q = "What is the primary business model"
        planner = Planner()
        with patch("core.reasoning.backends.get_backend", return_value=cap), \
             patch("core.reasoning.router.resolve_backend",
                   side_effect=lambda *_a, **kw: kw.get("fallback_backend_id", "ollama_local")), \
             patch("core.reasoning.router.emit_route_event", return_value=None), \
             patch("core.reasoning.trace_schema.emit_trace_step", return_value=True), \
             patch("core.audit_bridge.mirror_to_audit_db", return_value=True):
            planner.plan(light_q, force=True)
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_LIGHT,
            "Light query → CAP_LIGHT=1200 on first call")
        self.assertEqual(len(cap.calls), 2,
            "Length truncation should trigger exactly one retry "
            "(complete_with_retry contract).")
        self.assertEqual(cap.calls[1]["max_tokens"], 2 * CAP_LIGHT,
            "Retry should double the cap (1200 → 2400).")


class AdaptiveBudgetEnabledHelperTests(unittest.TestCase):
    """budget.adaptive_budget_enabled() — pinned as the single source
    of truth for the D1 opt-in flag. The 5 reasoning stages (existing:
    query_rewriter, synth; v0.4 Sprint 3: planner, reflect, verify)
    must all read the same env semantics."""

    def setUp(self):
        self._orig = os.environ.get("JAMES_ADAPTIVE_BUDGET")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("JAMES_ADAPTIVE_BUDGET", None)
        else:
            os.environ["JAMES_ADAPTIVE_BUDGET"] = self._orig

    def test_default_off(self):
        os.environ.pop("JAMES_ADAPTIVE_BUDGET", None)
        from core.reasoning.budget import adaptive_budget_enabled
        self.assertFalse(adaptive_budget_enabled(),
            "Default-off invariant — no env var → flag off")

    def test_truthy_values_enable(self):
        from core.reasoning.budget import adaptive_budget_enabled
        for val in ("1", "true", "TRUE", "yes", "YES", "on", "ON"):
            with self.subTest(val=val):
                os.environ["JAMES_ADAPTIVE_BUDGET"] = val
                self.assertTrue(adaptive_budget_enabled())

    def test_falsy_values_silence(self):
        from core.reasoning.budget import adaptive_budget_enabled
        for val in ("0", "false", "no", "off", "", "garbage"):
            with self.subTest(val=val):
                os.environ["JAMES_ADAPTIVE_BUDGET"] = val
                self.assertFalse(adaptive_budget_enabled())


if __name__ == "__main__":
    unittest.main()
