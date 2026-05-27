"""LEO L.B contract tests — evidence_scope routing axis.

Locks the new `evidence_scope` kwarg on `Router.select_backend`,
`resolve_backend`, and `_route_policy`, plus the L.B policy v1
narrow/wide override rule:

  - scope <= 0.30 → prefer small tier (else legacy)
  - scope >= 0.70 → prefer large / medium tier (else legacy)
  - 0.30 < scope < 0.70 → fall through to D5.C.1 budget rule
  - scope is None → D5.C.1 byte-identical (regression pin)
  - verify stage still wins over scope (grounding-critical invariant)
  - flag OFF → scope ignored entirely (returns legacy / fallback)

Companion to:
  - `test_router_skeleton.py` (D5.A flag + contract)
  - `test_router_capability.py` (D5.B tier registry)
  - `test_router_policy.py` (D5.C.1 verify/budget tree)
  - `test_evidence_scope.py` (L.A extractor, scalar producer)

L.B itself does not wire any production call site to pass
`evidence_scope` — that is L.C (engine.py Loop 1 → generate_answer
insertion). Until L.C lands, `evidence_scope` defaults to `None`
across the production call chain → behavior byte-identical to
post-L.A main.

See `docs/handovers/v0.4-leo-evidence-scope-routing-track.md` for
the full L.0 → L.D phase plan.
"""
from __future__ import annotations

import pytest

from core.reasoning.backends import (
    BackendCapability,
    CompletionResult,
    _clear_for_tests,
    register_backend,
)
from core.reasoning.budget import CAP_HEAVY, CAP_LIGHT, CAP_SUBSTITUTION
from core.reasoning.router import (
    Router,
    _SCOPE_NARROW_THRESHOLD,
    _SCOPE_WIDE_THRESHOLD,
    _route_policy,
    resolve_backend,
)


# ─── Stub backends (mirrors test_router_policy.py) ────────────────


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
    """Register small/medium/large stubs. Restore the registry after.

    Sets ``JAMES_LEGACY_BACKEND`` to a registered stub so policy
    fallback paths return a real registry key (post-2026-05-27 fix —
    pre-fix this used ``JAMES_LLM_MODEL=legacy_model`` but the router
    no longer treats model tags as backend IDs)."""
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_small", _StubSmall())
    register_backend("stub_medium", _StubMedium())
    register_backend("stub_large", _StubLarge())
    register_backend("stub_legacy", _StubSmall())  # fallback target
    yield
    backends_mod._REGISTRY.clear()
    backends_mod._REGISTRY.update(snapshot)


@pytest.fixture
def only_small_registered(monkeypatch):
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_small", _StubSmall())
    register_backend("stub_legacy", _StubSmall())
    yield
    backends_mod._REGISTRY.clear()
    backends_mod._REGISTRY.update(snapshot)


# ─── Threshold constant pin ───────────────────────────────────────


def test_threshold_constants_are_ordered():
    """Defends future tuning — narrow must be strictly < wide."""
    assert 0.0 <= _SCOPE_NARROW_THRESHOLD < _SCOPE_WIDE_THRESHOLD <= 1.0


# ─── Narrow scope (≤ 0.30) → small ────────────────────────────────


def test_narrow_scope_overrides_light_budget(all_tiers_registered):
    """Narrow scope forces small even when budget would say legacy.

    LEO open Q #4 answer in action — measurement promotes the
    decision one tier (LIGHT/None → small) when the signal is clear.
    """
    assert _route_policy(
        "synth", "any prompt", "", CAP_LIGHT, evidence_scope=0.10,
    ) == "stub_small"


def test_narrow_scope_at_threshold_exactly(all_tiers_registered):
    """Boundary value — scope == 0.30 still counts as narrow."""
    assert _route_policy(
        "synth", "any prompt", "", None,
        evidence_scope=_SCOPE_NARROW_THRESHOLD,
    ) == "stub_small"


def test_narrow_scope_falls_back_to_legacy_when_no_small(monkeypatch):
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_large", _StubLarge())
    register_backend("stub_legacy", _StubSmall())
    try:
        assert _route_policy(
            "synth", "any prompt", "", CAP_LIGHT, evidence_scope=0.10,
        ) == "stub_legacy"
    finally:
        backends_mod._REGISTRY.clear()
        backends_mod._REGISTRY.update(snapshot)


# ─── Wide scope (≥ 0.70) → large/medium ───────────────────────────


def test_wide_scope_overrides_light_budget(all_tiers_registered):
    """Wide scope forces large/medium even when budget would say legacy."""
    assert _route_policy(
        "synth", "any prompt", "", CAP_LIGHT, evidence_scope=0.90,
    ) == "stub_large"


def test_wide_scope_at_threshold_exactly(all_tiers_registered):
    """Boundary value — scope == 0.70 still counts as wide."""
    assert _route_policy(
        "synth", "any prompt", "", None,
        evidence_scope=_SCOPE_WIDE_THRESHOLD,
    ) == "stub_large"


def test_wide_scope_falls_back_to_medium_when_no_large(monkeypatch):
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    _clear_for_tests()
    register_backend("stub_small", _StubSmall())
    register_backend("stub_medium", _StubMedium())
    register_backend("stub_legacy", _StubSmall())
    try:
        assert _route_policy(
            "synth", "any prompt", "", CAP_LIGHT, evidence_scope=0.90,
        ) == "stub_medium"
    finally:
        backends_mod._REGISTRY.clear()
        backends_mod._REGISTRY.update(snapshot)


# ─── Mid-band (0.30 < scope < 0.70) → fall through to budget ─────


def test_mid_scope_falls_through_to_budget_substitution(all_tiers_registered):
    """Mid scope leaves D5.C.1 substitution rule in charge."""
    assert _route_policy(
        "synth", "그대로 출력", "", CAP_SUBSTITUTION, evidence_scope=0.50,
    ) == "stub_small"


def test_mid_scope_falls_through_to_budget_heavy(all_tiers_registered):
    """Mid scope leaves D5.C.1 heavy rule in charge."""
    assert _route_policy(
        "synth", "multi-step 분석", "", CAP_HEAVY, evidence_scope=0.50,
    ) == "stub_large"


def test_mid_scope_falls_through_to_budget_light(all_tiers_registered):
    """Mid scope + light budget → legacy (D5.C.1 rule 4 unchanged)."""
    assert _route_policy(
        "synth", "short", "", CAP_LIGHT, evidence_scope=0.50,
    ) == "stub_legacy"


# ─── scope=None → D5.C.1 unchanged (regression pin) ──────────────


def test_scope_none_is_byte_identical_to_d5_c1(all_tiers_registered):
    """When evidence_scope is None, every D5.C.1 outcome is preserved."""
    # Rule 1: verify
    assert _route_policy("verify", "p", "", None, evidence_scope=None) == "stub_large"
    # Rule 2: substitution
    assert _route_policy(
        "synth", "p", "", CAP_SUBSTITUTION, evidence_scope=None,
    ) == "stub_small"
    # Rule 3: heavy
    assert _route_policy(
        "synth", "p", "", CAP_HEAVY, evidence_scope=None,
    ) == "stub_large"
    # Rule 4: light / unknown
    assert _route_policy(
        "synth", "p", "", CAP_LIGHT, evidence_scope=None,
    ) == "stub_legacy"


# ─── verify stage wins over scope (rule 1 priority) ──────────────


def test_verify_wins_over_narrow_scope(all_tiers_registered):
    """Grounding-critical stage overrides even a clear narrow scope."""
    assert _route_policy(
        "verify", "p", "", None, evidence_scope=0.05,
    ) == "stub_large"


def test_verify_wins_over_wide_scope(all_tiers_registered):
    """Grounding-critical stage and wide scope happen to agree, but the
    selection comes from rule 1 not rule 2."""
    assert _route_policy(
        "verify", "p", "", None, evidence_scope=0.99,
    ) == "stub_large"


# ─── Router.select_backend kwarg acceptance ──────────────────────


def test_select_backend_accepts_evidence_scope_kwarg():
    """L.B signature pin — kwarg accepted even when flag OFF."""
    r = Router(enabled=False)
    out = r.select_backend(
        "synth", "prompt", context="ctx",
        budget_signal=CAP_LIGHT, evidence_scope=0.5,
    )
    assert isinstance(out, str) and out


def test_select_backend_flag_off_ignores_scope(monkeypatch):
    """Flag OFF returns legacy regardless of scope (byte-identical)."""
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    r = Router(enabled=False)
    for scope in (0.0, 0.1, 0.5, 0.9, 1.0):
        assert r.select_backend(
            "synth", "p", evidence_scope=scope,
        ) == "stub_legacy"


def test_select_backend_flag_on_uses_scope(all_tiers_registered):
    """Flag ON + scope passed → policy applies."""
    r = Router(enabled=True)
    assert r.select_backend(
        "synth", "p", evidence_scope=0.10,
    ) == "stub_small"
    assert r.select_backend(
        "synth", "p", evidence_scope=0.90,
    ) == "stub_large"


# ─── resolve_backend kwarg acceptance ────────────────────────────


def test_resolve_backend_accepts_evidence_scope_kwarg(monkeypatch):
    """High-level helper exposes the same surface."""
    monkeypatch.setenv("JAMES_AUTO_ROUTER", "0")
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    out = resolve_backend(
        "synth", "p", evidence_scope=0.5, fallback_backend_id="legacy",
    )
    # Flag OFF — fallback wins, scope is ignored
    assert out == "legacy"


def test_resolve_backend_flag_on_propagates_scope(
    monkeypatch, all_tiers_registered,
):
    monkeypatch.setenv("JAMES_AUTO_ROUTER", "1")
    out = resolve_backend(
        "synth", "p", evidence_scope=0.90, fallback_backend_id="ignored",
    )
    assert out == "stub_large"
