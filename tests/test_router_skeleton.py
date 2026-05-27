"""D5.A skeleton contract tests.

Pins the default-off invariant + the stub policy for the auto-router.
D5.C will extend these with policy assertions; D5.A only locks the
shape so subsequent PRs land without surprise behavior shifts.

See `docs/handovers/v0.3.x-direction5-auto-routing-track.md` for the
full phase plan.
"""

import pytest

from core.reasoning.router import (
    _DEFAULT_BACKEND_ID,
    Router,
    _auto_router_enabled,
    _legacy_backend_id,
)


# ─── flag detection ─────────────────────────────────────────────────


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("JAMES_AUTO_ROUTER", raising=False)
    assert _auto_router_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_flag_on_recognized(monkeypatch, value):
    monkeypatch.setenv("JAMES_AUTO_ROUTER", value)
    assert _auto_router_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "blah", "2"])
def test_flag_off_or_invalid_treated_as_off(monkeypatch, value):
    monkeypatch.setenv("JAMES_AUTO_ROUTER", value)
    assert _auto_router_enabled() is False


# ─── legacy backend resolution ─────────────────────────────────────


def test_legacy_backend_uses_env_when_set(monkeypatch):
    """JAMES_LEGACY_BACKEND overrides the default registry key —
    test-injection point. Production normally leaves this unset."""
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    assert _legacy_backend_id() == "stub_legacy"


def test_legacy_backend_falls_back_when_unset(monkeypatch):
    monkeypatch.delenv("JAMES_LEGACY_BACKEND", raising=False)
    assert _legacy_backend_id() == _DEFAULT_BACKEND_ID


def test_legacy_backend_falls_back_when_empty(monkeypatch):
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "")
    assert _legacy_backend_id() == _DEFAULT_BACKEND_ID


def test_legacy_backend_ignores_jamesllm_model(monkeypatch):
    """Regression pin (2026-05-27): JAMES_LLM_MODEL is a model tag
    (e.g. 'gemma4:e4b'), not a registry backend ID. Pre-fix
    `_legacy_backend_id` read it and returned the tag, causing
    get_backend(tag) to KeyError on every router fallback path under
    JAMES_AUTO_ROUTER=1 with only the small-tier ollama_local
    registered. Pin: setting JAMES_LLM_MODEL must NOT affect the
    registry-key resolution."""
    monkeypatch.setenv("JAMES_LLM_MODEL", "gemma3:12b")
    monkeypatch.delenv("JAMES_LEGACY_BACKEND", raising=False)
    assert _legacy_backend_id() == _DEFAULT_BACKEND_ID


# ─── Router contract ───────────────────────────────────────────────


def test_router_flag_off_returns_legacy(monkeypatch):
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    r = Router(enabled=False)
    assert r.enabled is False
    assert r.select_backend("query_rewriter", "팔란티어가 뭐야") == "stub_legacy"


def test_router_flag_on_stub_also_returns_legacy(monkeypatch):
    """D5.A stub — flag-on currently returns legacy. D5.C replaces this."""
    monkeypatch.setenv("JAMES_LEGACY_BACKEND", "stub_legacy")
    r = Router(enabled=True)
    assert r.enabled is True
    assert r.select_backend("query_rewriter", "팔란티어가 뭐야") == "stub_legacy"


def test_router_default_construction_consults_env(monkeypatch):
    monkeypatch.delenv("JAMES_AUTO_ROUTER", raising=False)
    r_off = Router()
    assert r_off.enabled is False

    monkeypatch.setenv("JAMES_AUTO_ROUTER", "1")
    r_on = Router()
    assert r_on.enabled is True


def test_router_explicit_enabled_overrides_env(monkeypatch):
    monkeypatch.setenv("JAMES_AUTO_ROUTER", "1")
    r = Router(enabled=False)
    assert r.enabled is False


def test_router_accepts_all_stages():
    """Contract pin: every D1 ReasoningStage value is a valid call."""
    r = Router(enabled=False)
    for stage in ("query_rewriter", "planner", "reflect", "verify", "synth"):
        out = r.select_backend(stage, "test")
        assert isinstance(out, str) and out


def test_router_accepts_optional_kwargs():
    """Contract pin: context + budget_signal are accepted (D5.C will use)."""
    r = Router(enabled=False)
    out = r.select_backend(
        "verify",
        "test prompt",
        context="some retrieved context",
        budget_signal=1200,
    )
    assert isinstance(out, str) and out
