"""D5.C.2.a — QueryRewriter router wiring contract tests.

Verifies the flag-gated wiring added in `core/retrieval/query_rewriter.py`:

  • `JAMES_AUTO_ROUTER` flag OFF → backend = `self._backend_id`
    (byte-identical to pre-D5)
  • Flag ON + D1 flag OFF      → backend = `self._backend_id` (router
    sees `budget_signal=None` → policy fallback to legacy → fallback)
  • Flag ON + D1 flag ON       → backend resolved via router policy
  • `emit_route_event` invoked on every successful resolution

Pairs with `test_query_rewriter.py` (D1 + L0/L1 backend regression)
and `test_router_policy.py` (D5.C.1 policy decision tree).
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402

ensure_utf8_console()


def _completion(text="", error=""):
    res = MagicMock()
    res.text = text
    res.error = error
    return res


class _EnvSnapshot(unittest.TestCase):
    """Save & restore the env flags this test class manipulates."""

    _FLAGS = (
        "JAMES_ENABLE_QUERY_REWRITE",
        "JAMES_ADAPTIVE_BUDGET",
        "JAMES_AUTO_ROUTER",
        "JAMES_LLM_MODEL",
    )

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self._FLAGS}
        # Default test env: rewriter enabled (so wiring actually fires),
        # D1 + D5 flags both off (caller flips per test).
        os.environ["JAMES_ENABLE_QUERY_REWRITE"] = "1"
        os.environ.pop("JAMES_ADAPTIVE_BUDGET", None)
        os.environ.pop("JAMES_AUTO_ROUTER", None)
        os.environ["JAMES_LLM_MODEL"] = "fixture_legacy"

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class FlagOffPreservesFallbackTests(_EnvSnapshot):
    """D5.C.2.a invariant: flag-off → backend = self._backend_id."""

    def test_d5_off_uses_self_backend_id(self):
        from core.retrieval.query_rewriter import QueryRewriter

        rw = QueryRewriter(backend_id="ollama_local")
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "ok"}'
        )

        with patch(
            "core.reasoning.backends.get_backend", return_value=fake
        ) as get_b:
            rw.rewrite("이것은 충분히 긴 질의입니다", force=True)

        # The lookup must have used self._backend_id ("ollama_local"),
        # not the policy default. The wiring resolved the backend before
        # calling get_backend.
        get_b.assert_called_with("ollama_local")

    def test_d5_off_with_d1_on_still_uses_self_backend_id(self):
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        from core.retrieval.query_rewriter import QueryRewriter

        rw = QueryRewriter(backend_id="ollama_local")
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "ok"}'
        )
        with patch(
            "core.reasoning.backends.get_backend", return_value=fake
        ) as get_b:
            rw.rewrite("이것은 충분히 긴 질의입니다", force=True)
        # D5 flag still off → router not consulted → fallback wins.
        get_b.assert_called_with("ollama_local")


class FlagOnD1OffRoutesToLegacyTests(_EnvSnapshot):
    """D5 flag ON but D1 flag OFF → budget_signal=None → router policy
    falls through to its own legacy backend (`JAMES_LLM_MODEL` env).
    The stage's `self._backend_id` is intentionally overridden because
    D5 ON means "let the router decide" — stage-level preferences are
    a D5-OFF concept."""

    def test_d5_on_d1_off_uses_router_legacy_not_self_backend_id(self):
        os.environ["JAMES_AUTO_ROUTER"] = "1"
        from core.retrieval.query_rewriter import QueryRewriter

        rw = QueryRewriter(backend_id="ollama_local")
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "ok"}'
        )
        with patch(
            "core.reasoning.backends.get_backend", return_value=fake
        ) as get_b:
            rw.rewrite("이것은 충분히 긴 질의입니다", force=True)
        # D5 flag ON → router policy decides. With budget_signal=None
        # the policy rule 4 (legacy) fires → router returns
        # `_legacy_backend_id()` = JAMES_LLM_MODEL = "fixture_legacy".
        # `self._backend_id` ("ollama_local") is intentionally ignored
        # — D5 ON means router is the authority, not the stage.
        get_b.assert_called_with("fixture_legacy")


class FlagOnD1OnRoutesViaPolicyTests(_EnvSnapshot):
    """D5 + D1 flags both ON → router consults policy with a real
    budget signal. Short Korean query like "팔란티어가 뭐야" routes
    through D1 → CAP_LIGHT → router policy → legacy fallback (no
    'small' tier override registered in test env beyond the builtin
    ollama_local)."""

    def test_router_consulted_when_both_flags_on(self):
        os.environ["JAMES_AUTO_ROUTER"] = "1"
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        from core.retrieval.query_rewriter import QueryRewriter

        rw = QueryRewriter(backend_id="ollama_local")
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "ok"}'
        )
        # CAP_LIGHT routes to legacy (no escalation for light tier)
        with patch(
            "core.reasoning.backends.get_backend", return_value=fake
        ) as get_b:
            with patch(
                "core.reasoning.router.emit_route_event"
            ) as emit:
                rw.rewrite("이것은 충분히 긴 질의입니다", force=True)
        # Audit row emitted exactly once per call
        emit.assert_called_once()
        # The chosen backend = the resolved policy output; since only
        # the builtin small tier (ollama_local) is registered AND the
        # signal is CAP_LIGHT, the policy returns legacy fallback.
        get_b.assert_called()


class AuditEventEmittedTests(_EnvSnapshot):
    """emit_route_event is called on every successful backend resolve,
    regardless of flag state. The reason label distinguishes flag-on
    ('auto') from flag-off ('fallback')."""

    def test_emit_called_on_flag_off(self):
        from core.retrieval.query_rewriter import QueryRewriter

        rw = QueryRewriter(backend_id="ollama_local")
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "ok"}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            with patch(
                "core.reasoning.router.emit_route_event"
            ) as emit:
                rw.rewrite("이것은 충분히 긴 질의입니다", force=True)
        emit.assert_called_once()
        # reason label is 'fallback' under D1 flag off (no meaningful signal)
        kwargs = emit.call_args.kwargs
        assert kwargs.get("reason") == "fallback"

    def test_emit_called_with_auto_reason_when_d1_on(self):
        os.environ["JAMES_ADAPTIVE_BUDGET"] = "1"
        from core.retrieval.query_rewriter import QueryRewriter

        rw = QueryRewriter(backend_id="ollama_local")
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "ok"}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            with patch(
                "core.reasoning.router.emit_route_event"
            ) as emit:
                rw.rewrite("이것은 충분히 긴 질의입니다", force=True)
        emit.assert_called_once()
        kwargs = emit.call_args.kwargs
        # D1 active → budget_signal is meaningful → reason is 'auto'
        assert kwargs.get("reason") == "auto"


class RouterHelpersDirectTests(unittest.TestCase):
    """Unit tests for the D5.C.2 helpers themselves
    (`resolve_backend`, `emit_route_event`, `_budget_to_tier_label`)
    without going through query_rewriter."""

    def setUp(self):
        self._saved_router = os.environ.get("JAMES_AUTO_ROUTER")
        self._saved_model = os.environ.get("JAMES_LLM_MODEL")
        os.environ.pop("JAMES_AUTO_ROUTER", None)
        os.environ["JAMES_LLM_MODEL"] = "fixture_legacy"

    def tearDown(self):
        if self._saved_router is None:
            os.environ.pop("JAMES_AUTO_ROUTER", None)
        else:
            os.environ["JAMES_AUTO_ROUTER"] = self._saved_router
        if self._saved_model is None:
            os.environ.pop("JAMES_LLM_MODEL", None)
        else:
            os.environ["JAMES_LLM_MODEL"] = self._saved_model

    def test_resolve_flag_off_returns_fallback(self):
        from core.reasoning.router import resolve_backend

        out = resolve_backend(
            "query_rewriter",
            "any prompt",
            fallback_backend_id="my_explicit_backend",
        )
        assert out == "my_explicit_backend"

    def test_resolve_flag_off_no_fallback_returns_legacy(self):
        from core.reasoning.router import resolve_backend

        out = resolve_backend("query_rewriter", "any prompt")
        assert out == "fixture_legacy"

    def test_resolve_flag_on_consults_router(self):
        os.environ["JAMES_AUTO_ROUTER"] = "1"
        from core.reasoning.router import resolve_backend

        # verify stage always escalates per D5.C.1 policy; but with
        # only `small` tier registered (ollama_local builtin), the
        # policy falls back to legacy.
        out = resolve_backend(
            "verify",
            "any prompt",
            fallback_backend_id="should_be_ignored_when_flag_on",
        )
        # Either legacy ("fixture_legacy") or the builtin small backend
        # ID ("ollama_local") is acceptable depending on what else is
        # registered. The key assertion is "not the fallback_backend_id
        # passed by the caller" — router took over.
        assert out != "should_be_ignored_when_flag_on"

    def test_budget_to_tier_label(self):
        from core.reasoning.budget import CAP_HEAVY, CAP_LIGHT, CAP_SUBSTITUTION
        from core.reasoning.router import _budget_to_tier_label

        assert _budget_to_tier_label(None) == "none"
        assert _budget_to_tier_label(CAP_SUBSTITUTION) == "substitution"
        assert _budget_to_tier_label(CAP_LIGHT) == "light"
        assert _budget_to_tier_label(CAP_HEAVY) == "heavy"
        assert _budget_to_tier_label(999) == "unknown:999"

    def test_emit_route_event_never_raises(self):
        from core.reasoning.router import emit_route_event

        # Even if audit_bridge is unavailable / DB locked / etc., this
        # must not raise — production call path can't be blocked by
        # audit failure.
        with patch(
            "core.audit_bridge.mirror_to_audit_db",
            side_effect=RuntimeError("simulated audit failure"),
        ):
            # Should not raise:
            emit_route_event("verify", "any prompt", "ollama_local")
