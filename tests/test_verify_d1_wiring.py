"""v0.4 Sprint 3 #7c — Verify D1 adaptive-budget + retry wiring.

Closes the cognitive-stages D1 expansion that #7a (planner) and #7b
(reflect) started. Verify is the grounding-critical stage —
D5.C.1 policy rule 1 already escalates it to the large tier when a
larger backend is registered (PR #481). This PR adds the D1 layer
on top: when ``JAMES_ADAPTIVE_BUDGET=1`` the fact_check call routes
through ``TaskBudget.assess("verify", query)`` and through
``complete_with_retry`` so a light task hits CAP_LIGHT with a
length-truncation retry path, instead of paying CAP_HEAVY upfront.

The grounding-critical D5 routing decision and the D1 cap decision
compose — both fire independently and feed the same router policy
+ retry helper that the other four stages now share.

Contract pinned here
  1. Flag OFF + default ctor → cap is 4096 (byte-identical).
  2. Flag OFF + explicit ``fact_check_max_tokens=N`` → cap is N.
  3. Flag ON + default ctor + light query → CAP_LIGHT.
  4. Flag ON + heavy query → CAP_HEAVY.
  5. Flag ON + length truncation → retry once at doubled cap.
  6. Fact-check disabled (JAMES_ENABLE_FACT_CHECK off) → no backend
     call at all — D1 surface stays cold (the cheaper heuristic
     path stays cheap).
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


class _VerifyCallCapture:
    """Records every backend.complete call. Returns a fact-check
    response shaped as JSON so the parser is happy. done_reasons
    drives the complete_with_retry retry decision."""

    JSON_OK = '{"unsupported": []}'

    def __init__(self, *, done_reasons=None):
        self.calls = []
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
        return SimpleNamespace(
            text=self.JSON_OK,
            error="",
            done_reason=dr,
            latency_ms=10,
            backend_id="ollama_local",
        )


class VerifyD1WiringTests(unittest.TestCase):

    QUERY = "What is Palantir's primary business model"   # light query
    ANSWER = "Palantir provides data integration software. " * 5
    CONTEXT = "Palantir Technologies operates an AI / data platform. " * 8

    def setUp(self):
        self._orig_budget = os.environ.get("JAMES_ADAPTIVE_BUDGET")
        self._orig_verify = os.environ.get("JAMES_ENABLE_VERIFY")
        self._orig_fc = os.environ.get("JAMES_ENABLE_FACT_CHECK")
        os.environ["JAMES_ENABLE_VERIFY"] = "1"
        os.environ["JAMES_ENABLE_FACT_CHECK"] = "1"

    def tearDown(self):
        for key, val in (
            ("JAMES_ADAPTIVE_BUDGET", self._orig_budget),
            ("JAMES_ENABLE_VERIFY", self._orig_verify),
            ("JAMES_ENABLE_FACT_CHECK", self._orig_fc),
        ):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _run(self, capture, *, query=None, **ctor_kw):
        from core.reasoning.verify import Verifier
        verifier = Verifier(**ctor_kw)
        q = query if query is not None else self.QUERY
        with patch("core.reasoning.backends.get_backend", return_value=capture), \
             patch("core.reasoning.router.resolve_backend",
                   side_effect=lambda *_a, **kw: kw.get("fallback_backend_id", "ollama_local")), \
             patch("core.reasoning.router.emit_route_event", return_value=None), \
             patch("core.reasoning.trace_schema.emit_trace_step", return_value=True), \
             patch("core.audit_bridge.mirror_to_audit_db", return_value=True):
            return verifier.verify(q, self.ANSWER, self.CONTEXT, force=True)

    def test_flag_off_default_cap_unchanged(self):
        """Path #1 — flag off + default → 4096."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "0"
        cap = _VerifyCallCapture()
        self._run(cap)
        self.assertEqual(len(cap.calls), 1,
            "Verify should hit backend once (fact_check) when "
            "JAMES_ENABLE_FACT_CHECK=1 and context is present.")
        self.assertEqual(cap.calls[0]["max_tokens"], 4096,
            "Default-off cap must stay at 4096 (byte-identical).")

    def test_flag_off_explicit_cap_honoured(self):
        """Path #2 — explicit int wins regardless of flag."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _VerifyCallCapture()
        self._run(cap, fact_check_max_tokens=800)
        self.assertEqual(cap.calls[0]["max_tokens"], 800)

    def test_flag_on_light_query_uses_light(self):
        """Path #3 — flag on + light query → CAP_LIGHT."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _VerifyCallCapture()
        self._run(cap)
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_LIGHT,
            "Light query (no heavy markers) → CAP_LIGHT=1200")

    def test_flag_on_heavy_query_uses_heavy(self):
        """Path #4 — heavy marker in query → CAP_HEAVY."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _VerifyCallCapture()
        # "단계" is in _HEAVY_MARKERS.
        heavy_q = "이 답변을 단계별로 검증해줘"
        self._run(cap, query=heavy_q)
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_HEAVY)

    def test_flag_on_retry_fires_on_length(self):
        """Path #5 — first call truncates → retry once at doubled cap."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        cap = _VerifyCallCapture(done_reasons=["length", "stop"])
        self._run(cap)
        self.assertEqual(len(cap.calls), 2,
            "Length truncation should trigger exactly one retry.")
        self.assertEqual(cap.calls[0]["max_tokens"], CAP_LIGHT)
        self.assertEqual(cap.calls[1]["max_tokens"], 2 * CAP_LIGHT,
            "Retry should double the cap (1200 → 2400).")

    def test_fact_check_disabled_skips_backend(self):
        """Path #6 — without JAMES_ENABLE_FACT_CHECK no backend call
        happens. D1 surface stays cold; the cheaper heuristic path
        stays cheap."""
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        os.environ.pop("JAMES_ENABLE_FACT_CHECK", None)
        cap = _VerifyCallCapture()
        self._run(cap)
        self.assertEqual(len(cap.calls), 0,
            "JAMES_ENABLE_FACT_CHECK off → no backend call. The "
            "security-scan heuristic still runs; D1 wiring is "
            "irrelevant on this path.")


if __name__ == "__main__":
    unittest.main()
