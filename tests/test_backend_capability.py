"""D5.B backend capability registry contract tests.

Locks the BackendCapability dataclass + helper API shape so D5.C
routing policy can rely on them. Also pins the two built-in
backends' declared capabilities so a refactor that drops a
declaration is caught here, not in production routing.
"""

import pytest

from core.reasoning.backends import (
    UNKNOWN_CAPABILITY,
    BackendCapability,
    _clear_for_tests,
    get_backend_capability,
    list_backends_by_tier,
    register_backend,
)


# ─── BackendCapability dataclass shape ─────────────────────────────


def test_capability_dataclass_is_frozen():
    cap = BackendCapability(tier="small", provider="local")
    with pytest.raises((AttributeError, Exception)):
        cap.tier = "large"  # frozen dataclass refuses mutation


def test_capability_fields():
    cap = BackendCapability(tier="medium", provider="sovereign")
    assert cap.tier == "medium"
    assert cap.provider == "sovereign"


def test_unknown_capability_is_unknown():
    assert UNKNOWN_CAPABILITY.tier == "unknown"
    assert UNKNOWN_CAPABILITY.provider == "unknown"


def test_capability_equality_by_value():
    a = BackendCapability(tier="small", provider="local")
    b = BackendCapability(tier="small", provider="local")
    assert a == b
    assert a != BackendCapability(tier="large", provider="local")


# ─── Built-in backend declarations ─────────────────────────────────


def test_ollama_local_declares_small_local():
    # Importing the module auto-registers the backend per
    # core/reasoning/backends/__init__.py autoregistration block.
    import core.reasoning.backends  # noqa: F401 — trigger autoregistration

    cap = get_backend_capability("ollama_local")
    assert cap.tier == "small"
    assert cap.provider == "local"


# claude_code_cli is opt-in via JAMES_ENABLE_CLAUDE_BACKEND=1.
# We assert the class-level attribute directly (no registration needed).
def test_claude_code_cli_class_declares_large_cloud():
    from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend

    assert ClaudeCodeCliBackend.capability.tier == "large"
    assert ClaudeCodeCliBackend.capability.provider == "cloud"


# ─── get_backend_capability behavior ───────────────────────────────


class _StubDeclared:
    backend_id = "stub_declared"
    capability = BackendCapability(tier="medium", provider="sovereign")

    def complete(self, prompt, *, system="", max_tokens=1024, timeout=60.0, **opts):
        from core.reasoning.backends import CompletionResult
        return CompletionResult(text="ok", backend_id=self.backend_id)


class _StubNoCapability:
    backend_id = "stub_legacy"

    def complete(self, prompt, *, system="", max_tokens=1024, timeout=60.0, **opts):
        from core.reasoning.backends import CompletionResult
        return CompletionResult(text="ok", backend_id=self.backend_id)


@pytest.fixture
def isolated_registry():
    """Snapshot/restore the registry around tests that mutate it."""
    import core.reasoning.backends as backends_mod
    snapshot = dict(backends_mod._REGISTRY)
    yield
    backends_mod._REGISTRY.clear()
    backends_mod._REGISTRY.update(snapshot)


def test_get_capability_returns_declared(isolated_registry):
    register_backend("stub_declared", _StubDeclared())
    assert get_backend_capability("stub_declared") == BackendCapability(
        tier="medium", provider="sovereign"
    )


def test_get_capability_returns_unknown_for_undeclared(isolated_registry):
    register_backend("stub_legacy", _StubNoCapability())
    assert get_backend_capability("stub_legacy") is UNKNOWN_CAPABILITY


def test_get_capability_returns_unknown_for_wrong_type(isolated_registry):
    class StubWrongType:
        backend_id = "stub_wrong"
        capability = "small"  # str, not BackendCapability

        def complete(self, prompt, *, system="", max_tokens=1024, timeout=60.0, **opts):
            from core.reasoning.backends import CompletionResult
            return CompletionResult(text="ok", backend_id=self.backend_id)

    register_backend("stub_wrong", StubWrongType())
    assert get_backend_capability("stub_wrong") is UNKNOWN_CAPABILITY


def test_get_capability_raises_keyerror_for_unregistered(isolated_registry):
    _clear_for_tests()
    with pytest.raises(KeyError):
        get_backend_capability("does_not_exist")


# ─── list_backends_by_tier behavior ───────────────────────────────


def test_list_by_tier_includes_declared(isolated_registry):
    _clear_for_tests()
    register_backend("a", _StubDeclared())  # tier=medium
    assert "a" in list_backends_by_tier("medium")


def test_list_by_tier_skips_undeclared(isolated_registry):
    _clear_for_tests()
    register_backend("legacy", _StubNoCapability())
    # legacy has no capability — it should not match any tier (not even "unknown")
    assert list_backends_by_tier("small") == []
    assert list_backends_by_tier("medium") == []
    assert list_backends_by_tier("large") == []
    assert list_backends_by_tier("unknown") == []


def test_list_by_tier_empty_for_unmatched_tier(isolated_registry):
    _clear_for_tests()
    register_backend("a", _StubDeclared())  # tier=medium
    assert list_backends_by_tier("small") == []


def test_list_by_tier_with_builtin_ollama():
    """Sanity — the auto-registered ollama_local lands under 'small'."""
    import core.reasoning.backends  # noqa: F401
    assert "ollama_local" in list_backends_by_tier("small")
