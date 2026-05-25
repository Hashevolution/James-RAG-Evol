"""D5.C.1 router policy decision-tree contract tests.

Locks the policy in `core/reasoning/router._route_policy` so D5.C.2
wiring + D5.D alias resolution can rely on it. Companion to
`test_router_skeleton.py` (D5.A flag/contract) and
`test_backend_capability.py` (D5.B capability tags).

Decision tree under test:
  1. verify stage → prefer large, then medium, else legacy
  2. budget_signal == CAP_SUBSTITUTION → prefer small, else legacy
  3. budget_signal == CAP_HEAVY → prefer large, then medium, else legacy
  4. otherwise (CAP_LIGHT, None, unknown) → legacy
"""

import pytest

from core.reasoning.backends import (
    BackendCapability,
    CompletionResult,
    _clear_for_tests,
    register_backend,
)
from core.reasoning.budget import CAP_HEAVY, CAP_LIGHT, CAP_SUBSTITUTION
from core.reasoning.router import Router, _route_policy


# ─── Stub backends ────────────────────────────────────────────────


class _StubSmall:
    backend_id = "stub_small"
    capability = BackendCapability(tier="small", provider="local")

    def complete(self, prompt, *, system="", max_tokens=1024, timeout=60.0, **opts):
        return CompletionResult(text="ok", backend_id=self.backend_id)


class _StubMedium:
    backend_id = "stub_medium"
    capability = BackendCapability(tier="medium", provider="sovereign")

    def complete(self, prompt, *, system="", max_tokens=1024, timeout=60.0, **opts):
        return CompletionResult(text="ok", backend_id=self.backend_id)


class _StubLarge:
    backend_id = "stub_large"
    capability = BackendCapability(tier="large", provider="cloud")

    def complete(self, prompt, *, system="", max_tokens=1024, timeout=60.0, **opts):
        return CompletionResult(text="ok", backend_id=self.backend_id)


@pytest.fixture
def all_tiers_registered(monkeypatch):
    """Register small/medium/large stubs. Restore the registry after."""
    monkeypatch.setenv("JAMES_LLM_MODEL", "legacy_model")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_small", _StubSmall())
    register_backend("stub_medium", _StubMedium())
    register_backend("stub_large", _StubLarge())
    yield
    backends_mod._REGISTRY.clear()
    backends_mod._REGISTRY.update(snapshot)


@pytest.fixture
def only_small_registered(monkeypatch):
    """The stock-install case — only ollama_local-equivalent in the
    registry. Tests the "fall back to legacy when preferred tier
    unavailable" branch."""
    monkeypatch.setenv("JAMES_LLM_MODEL", "legacy_model")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_small", _StubSmall())
    yield
    backends_mod._REGISTRY.clear()
    backends_mod._REGISTRY.update(snapshot)


# ─── Rule 1: verify stage → prefer large ─────────────────────────


def test_verify_prefers_large(all_tiers_registered):
    assert _route_policy("verify", "any prompt", "", None) == "stub_large"


def test_verify_falls_back_to_medium_when_no_large(monkeypatch):
    monkeypatch.setenv("JAMES_LLM_MODEL", "legacy_model")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_medium", _StubMedium())
    try:
        assert _route_policy("verify", "any prompt", "", None) == "stub_medium"
    finally:
        backends_mod._REGISTRY.clear()
        backends_mod._REGISTRY.update(snapshot)


def test_verify_falls_back_to_legacy_when_only_small(only_small_registered):
    # verify is grounding-critical so it would prefer large/medium,
    # but if only small is registered, fall back to legacy (not small)
    assert _route_policy("verify", "any prompt", "", None) == "legacy_model"


# ─── Rule 2: CAP_SUBSTITUTION → prefer small ─────────────────────


def test_substitution_prefers_small(all_tiers_registered):
    assert _route_policy(
        "query_rewriter", "그대로 알려줘", "", CAP_SUBSTITUTION
    ) == "stub_small"


def test_substitution_falls_back_to_legacy_when_no_small(monkeypatch):
    monkeypatch.setenv("JAMES_LLM_MODEL", "legacy_model")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_large", _StubLarge())
    try:
        # No small registered, only large — substitution rule falls back
        # to legacy (not large; routing only escalates when budget asks for it)
        assert _route_policy(
            "synth", "그대로 출력", "", CAP_SUBSTITUTION
        ) == "legacy_model"
    finally:
        backends_mod._REGISTRY.clear()
        backends_mod._REGISTRY.update(snapshot)


# ─── Rule 3: CAP_HEAVY → prefer large, then medium ──────────────


def test_heavy_prefers_large(all_tiers_registered):
    assert _route_policy(
        "synth", "step by step 분석해", "", CAP_HEAVY
    ) == "stub_large"


def test_heavy_falls_back_to_medium_when_no_large(monkeypatch):
    monkeypatch.setenv("JAMES_LLM_MODEL", "legacy_model")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_small", _StubSmall())
    register_backend("stub_medium", _StubMedium())
    try:
        assert _route_policy(
            "synth", "multi-step", "", CAP_HEAVY
        ) == "stub_medium"
    finally:
        backends_mod._REGISTRY.clear()
        backends_mod._REGISTRY.update(snapshot)


def test_heavy_falls_back_to_legacy_when_only_small(only_small_registered):
    assert _route_policy("synth", "multi-step", "", CAP_HEAVY) == "legacy_model"


# ─── Rule 4: CAP_LIGHT / None / unknown → legacy ────────────────


def test_light_falls_back_to_legacy(all_tiers_registered):
    # Light budget doesn't trigger escalation even with all tiers available
    assert _route_policy("synth", "short answer", "", CAP_LIGHT) == "legacy_model"


def test_none_budget_falls_back_to_legacy(all_tiers_registered):
    assert _route_policy("synth", "any prompt", "", None) == "legacy_model"


def test_unknown_budget_falls_back_to_legacy(all_tiers_registered):
    # Unknown integer signal (not one of CAP_SUBSTITUTION/LIGHT/HEAVY)
    assert _route_policy("synth", "any prompt", "", 999) == "legacy_model"


# ─── Router.select_backend integrates _route_policy ────────────


def test_router_flag_on_dispatches_to_policy(all_tiers_registered):
    """The flag-on branch of Router.select_backend now consults
    _route_policy (replaces the D5.A stub that always returned legacy)."""
    r = Router(enabled=True)
    # verify always escalates → large (even with budget=None)
    assert r.select_backend("verify", "any") == "stub_large"
    # synth + heavy budget → large
    assert r.select_backend("synth", "multi-step", budget_signal=CAP_HEAVY) == "stub_large"
    # synth + substitution budget → small
    assert r.select_backend("synth", "그대로", budget_signal=CAP_SUBSTITUTION) == "stub_small"
    # synth + light budget → legacy
    assert r.select_backend("synth", "any", budget_signal=CAP_LIGHT) == "legacy_model"


def test_router_flag_off_still_legacy_regardless_of_tiers(all_tiers_registered):
    """D5.A invariant holds: flag-off ignores capability tiers entirely
    and returns the legacy backend on every call. D5.C.1 must not break this."""
    r = Router(enabled=False)
    assert r.select_backend("verify", "any") == "legacy_model"
    assert r.select_backend("synth", "any", budget_signal=CAP_HEAVY) == "legacy_model"
    assert r.select_backend("query_rewriter", "any", budget_signal=CAP_SUBSTITUTION) == "legacy_model"
