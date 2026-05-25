"""v0.4 Sprint 3 #7b — Reflect D1 adaptive-budget + retry wiring.

Same shape as test_planner_d1_wiring (#7a) on the ReflectionLoop
stage. Pre-#7b reflect held fixed critique=4096 / revise=1024 caps
so D1 and D6 both went unused. This PR opens both wirings behind
``JAMES_ADAPTIVE_BUDGET=1`` (D1 opt-in flag, shared single source
of truth via budget.adaptive_budget_enabled).

Contract pinned here
  1. Flag OFF + default ctor → caps are 4096 / 1024 (byte-identical
     to pre-#7b). Two separate defaults preserved.
  2. Flag OFF + explicit critique_max_tokens / revise_max_tokens
     → those values are honoured (baseline / unit-test path).
  3. Flag ON + default ctor → both sub-stages share
     TaskBudget.assess("reflect", query). Heavy marker → CAP_HEAVY;
     light → CAP_LIGHT.
  4. Flag ON + length truncation on a light query → retry once at
     doubled cap via complete_with_retry.
  5. Flag ON + explicit revise_max_tokens, default critique → only
     critique routes through assess; revise stays at the explicit
     int. The two caps are independent.
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

from core.reasoning.budget import CAP_HEAVY, CAP_LIGHT  # noqa: E402


class _ReflectCallCapture:
    """Records every backend.complete call. ReflectionLoop hits the
    backend twice per pass — once for critique, once for revise.
    The critique result must avoid the 'NO_ISSUES' shortcut so the
    revise pass actually runs."""

    def __init__(self, *, done_reasons=None):
        self.calls = []
        # Default both stages return non-NO_ISSUES text → revise fires.
        # done_reasons drives complete_with_retry retry decisions.
        self.done_reasons = list(done_reasons or [])

    def complete(self, prompt, *, max_tokens, timeout, **opts):
        idx = len(self.calls)
        self.calls.append({
            "prompt": prompt,
            "max_tokens": max_tokens,
            "timeout": timeout,
        })
        dr = (
            self.done_reasons[idx]
            if idx < len(self.done_reasons)
            else "stop"
        )
        # Distinguish critique vs revise via prompt content. critique
        # template includes "review" / "검토"; revise includes "Revise"
        # / "개정".
        if "Critically review" in prompt or "비판적으로 검토" in prompt:
            text = "Issue: missing detail on point X."
        else:
            text = "Revised answer that fixes point X."
        return SimpleNamespace(
            text=text,
            error="",
            done_reason=dr,
            latency_ms=10,
            backend_id="ollama_local",
        )


class ReflectD1WiringTests(unittest.TestCase):

    QUERY = "What is Palantir's primary business model"   # light
    DRAFT = ("Palantir provides software for data integration. " * 5)

    def setUp(self):
        self._orig_budget = os.environ.get("JAMES_ADAPTIVE_BUDGET")
        self._orig_reflect = os.environ.get("JAMES_ENABLE_REFLECT")
        os.environ["JAMES_ENABLE_REFLECT"] = "1"

    def tearDown(self):
        for key, val in (
            ("JAMES_ADAPTIVE_BUDGET", self._orig_budget),
            ("JAMES_ENABLE_REFLECT", self._orig_reflect),
        ):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _run(self, capture, **kw):
        from core.reasoning.reflect import ReflectionLoop
        loop = ReflectionLoop(**kw)
        with patch("core.reasoning.backends.get_backend", return_value=capture), \
             patch("core.reasoning.router.resolve_backend",
                   side_effect=lambda *_a, **kw: kw.get("fallback_backend_id", "ollama_local")), \
             patch("core.reasoning.router.emit_route_event", return_value=None), \
             patch("core.reasoning.trace_schema.emit_trace_step", return_value=True), \
             patch("core.audit_bridge.mirror_to_audit_db", return_value=True):
            return loop.reflect(self.QUERY, self.DRAFT, force=True)

    def test_flag_off_default_caps_unchanged(self):
        """Path #1 — flag OFF + default ctor → 4096 (critique) +
        1024 (revise). Two separate defaults preserved."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "0"
        cap = _ReflectCallCapture()
        self._run(cap)
        self.assertEqual(len(cap.calls), 2,
            "Reflect should hit backend twice (critique + revise) "
            "when critique returns a non-NO_ISSUES response.")
        self.assertEqual(cap.calls[0]["max_tokens"], 4096,
            "Default-off critique cap must stay at 4096.")
        self.assertEqual(cap.calls[1]["max_tokens"], 1024,
            "Default-off revise cap must stay at 1024.")

    def test_flag_off_explicit_caps_honoured(self):
        """Path #2 — explicit ints win regardless of flag state."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"  # flag on, but ints win
        cap = _ReflectCallCapture()
        self._run(cap, critique_max_tokens=600, revise_max_tokens=400)
        self.assertEqual(cap.calls[0]["max_tokens"], 600)
        self.assertEqual(cap.calls[1]["max_tokens"], 400)

    def test_flag_on_light_query_shares_cap_across_stages(self):
        """Path #3 — flag ON + default ctor + light query → both
        sub-stages get CAP_LIGHT from a single assess() call."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _ReflectCallCapture()
        self._run(cap)
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_LIGHT,
            "Light query → CAP_LIGHT on critique")
        self.assertEqual(cap.calls[1]["max_tokens"], CAP_LIGHT,
            "Light query → same CAP_LIGHT on revise (shared assess)")

    def test_flag_on_heavy_query_uses_heavy(self):
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _ReflectCallCapture()
        from core.reasoning.reflect import ReflectionLoop
        heavy_q = "Compare these two products step by step"  # heavy markers
        loop = ReflectionLoop()
        with patch("core.reasoning.backends.get_backend", return_value=cap), \
             patch("core.reasoning.router.resolve_backend",
                   side_effect=lambda *_a, **kw: kw.get("fallback_backend_id", "ollama_local")), \
             patch("core.reasoning.router.emit_route_event", return_value=None), \
             patch("core.reasoning.trace_schema.emit_trace_step", return_value=True), \
             patch("core.audit_bridge.mirror_to_audit_db", return_value=True):
            loop.reflect(heavy_q, self.DRAFT, force=True)
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_HEAVY,
            "Heavy marker in query → CAP_HEAVY on critique")
        self.assertEqual(cap.calls[1]["max_tokens"], CAP_HEAVY,
            "Heavy marker in query → CAP_HEAVY on revise too")

    def test_flag_on_retry_fires_on_length(self):
        """Path #4 — light query + critique truncates → retry once
        at doubled cap (1200 → 2400). Revise still runs after retry."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        # call[0] = critique cap=1200, truncated → retry
        # call[1] = critique retry cap=2400, stop
        # call[2] = revise cap=1200, stop
        cap = _ReflectCallCapture(done_reasons=["length", "stop", "stop"])
        self._run(cap)
        self.assertEqual(len(cap.calls), 3,
            "Critique truncation should trigger one retry + still "
            "run revise after.")
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_LIGHT,
            "First critique call at CAP_LIGHT=1200.")
        self.assertEqual(cap.calls[1]["max_tokens"], 2 * CAP_LIGHT,
            "Critique retry at doubled cap=2400.")
        self.assertEqual(cap.calls[2]["max_tokens"], CAP_LIGHT,
            "Revise runs after critique retry at CAP_LIGHT.")

    def test_flag_on_explicit_revise_independent_of_critique(self):
        """Path #5 — independent caps: explicit revise stays fixed,
        critique routes through assess."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _ReflectCallCapture()
        self._run(cap, revise_max_tokens=512)
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_LIGHT,
            "Critique routes through assess (None + flag-on).")
        self.assertEqual(cap.calls[1]["max_tokens"], 512,
            "Explicit revise_max_tokens wins over assess.")


if __name__ == "__main__":
    unittest.main()
