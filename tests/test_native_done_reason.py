"""D6 follow-up — native Ollama `done_reason` exposure tests.

Coverage:
  • `BaseLLM.generate_meta` default returns `{"text": ..., "done_reason": ""}`
  • `OllamaClient.generate_meta` reads `GemmaClient._last_done_reason`
  • `RouterWrapper.call_gemma_meta` dispatches to `call_router_meta`
  • `call_router_meta` invokes provider's `generate_meta`
  • `ollama_local` backend prefers native signal, falls back to heuristic
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ─── BaseLLM.generate_meta default ───────────────────────────────


def test_basellm_default_generate_meta_returns_dict():
    """Provider that doesn't override `generate_meta` gets a graceful
    default that wraps `generate(...)` in the dict shape."""
    from llm.base import BaseLLM

    class _StubProvider(BaseLLM):
        name = "stub"

        def generate(self, messages, **kwargs):
            return "stub-text"

    p = _StubProvider()
    out = p.generate_meta([{"role": "user", "content": "hi"}])
    assert out == {"text": "stub-text", "done_reason": ""}


# ─── OllamaClient.generate_meta ─────────────────────────────────


def test_ollama_client_generate_meta_reads_done_reason():
    """OllamaClient holds a single GemmaClient instance so it can
    read `_last_done_reason` after `generate(...)` returns."""
    from llm.providers.ollama_client import OllamaClient

    c = OllamaClient()
    fake_gemma = MagicMock()
    fake_gemma.call_gemma.return_value = "ok"
    fake_gemma._last_done_reason = "length"
    c._gemma_client = fake_gemma

    out = c.generate_meta(
        [{"role": "user", "content": "hi"}],
        max_tokens=100, timeout=5, use_cache=False,
    )
    assert out == {"text": "ok", "done_reason": "length"}


def test_ollama_client_generate_meta_empty_when_no_done_reason():
    """If GemmaClient doesn't set _last_done_reason (cache hit / old
    Ollama / error), the returned done_reason is empty string."""
    from llm.providers.ollama_client import OllamaClient

    c = OllamaClient()
    fake_gemma = MagicMock()
    fake_gemma.call_gemma.return_value = "ok"
    fake_gemma._last_done_reason = ""
    c._gemma_client = fake_gemma

    out = c.generate_meta(
        [{"role": "user", "content": "hi"}],
        max_tokens=100, timeout=5, use_cache=False,
    )
    assert out["text"] == "ok"
    assert out["done_reason"] == ""


# ─── RouterWrapper.call_gemma_meta ──────────────────────────────


def test_router_wrapper_call_gemma_meta_dispatches_to_call_router_meta():
    """call_gemma_meta is just a thin shim over call_router_meta."""
    from llm.router import RouterWrapper

    rw = RouterWrapper("general")
    with patch("llm.router.call_router_meta") as mock_router_meta:
        mock_router_meta.return_value = {"text": "ok", "done_reason": "stop"}
        out = rw.call_gemma_meta("hi", task_type="general", timeout=30)
        mock_router_meta.assert_called_once_with(
            "hi", task_type="general", timeout=30,
        )
        assert out == {"text": "ok", "done_reason": "stop"}


def test_call_router_meta_uses_provider_generate_meta():
    """When a provider is routed, call_router_meta invokes
    provider.generate_meta and forwards the result dict."""
    from llm.router import call_router_meta

    fake_llm = MagicMock()
    fake_llm.generate_meta.return_value = {"text": "ok", "done_reason": "stop"}
    with patch("llm.router.route", return_value=fake_llm):
        out = call_router_meta("hi")
    assert out == {"text": "ok", "done_reason": "stop"}
    fake_llm.generate_meta.assert_called_once()


def test_call_router_meta_falls_back_to_gemma_client_when_no_route():
    """If no provider matches, call_router_meta falls back to direct
    GemmaClient.call_gemma + reads _last_done_reason."""
    from llm.router import call_router_meta

    fake_gemma = MagicMock()
    fake_gemma.call_gemma.return_value = "ok"
    fake_gemma._last_done_reason = "length"
    with patch("llm.router.route", return_value=None):
        with patch("core.gemma_client.GemmaClient", return_value=fake_gemma):
            out = call_router_meta("hi")
    assert out == {"text": "ok", "done_reason": "length"}


# ─── ollama_local backend prefers native, falls back to heuristic ─


def _run_backend_with_router(router):
    """Build an OllamaLocalBackend with the supplied router stand-in
    + call `.complete(...)` with cap=100. Returns the
    CompletionResult."""
    from core.reasoning.backends.ollama_local import OllamaLocalBackend

    b = OllamaLocalBackend()
    b._router = router
    return b.complete("any prompt", max_tokens=100)


def test_backend_prefers_native_done_reason_when_router_returns_dict():
    """RouterWrapper with `call_gemma_meta` returning a dict → backend
    consumes the native done_reason (no heuristic computation)."""
    router = MagicMock()
    router.call_gemma_meta.return_value = {
        "text": "anything",   # native says "stop" wins regardless of length
        "done_reason": "stop",
    }
    out = _run_backend_with_router(router)
    assert out.text == "anything"
    assert out.done_reason == "stop"


def test_backend_uses_native_length_signal():
    """Native `done_reason="length"` precision case — bypass heuristic."""
    router = MagicMock()
    router.call_gemma_meta.return_value = {
        "text": "Hello world.",   # ends with sentence terminator —
                                   # heuristic would say "stop"
        "done_reason": "length",   # but native says length wins
    }
    out = _run_backend_with_router(router)
    assert out.done_reason == "length"


def test_backend_falls_back_to_heuristic_when_native_empty():
    """Native returns `done_reason=""` (cache hit / old Ollama) →
    backend applies the legacy length+terminator heuristic."""
    router = MagicMock()
    # Long response with no sentence terminator at end → heuristic "length"
    truncated = "x" * 380
    router.call_gemma_meta.return_value = {
        "text": truncated,
        "done_reason": "",
    }
    out = _run_backend_with_router(router)
    assert out.done_reason == "length"  # heuristic fired


def test_backend_falls_back_to_call_gemma_when_meta_not_dict():
    """Older RouterWrapper without call_gemma_meta — backend falls
    through to `call_gemma` + heuristic. We simulate this with a
    router stand-in whose call_gemma_meta returns a non-dict."""
    router = MagicMock()
    router.call_gemma_meta.return_value = "not a dict"   # bad return type
    router.call_gemma.return_value = "Hello world."      # legacy path
    out = _run_backend_with_router(router)
    # call_gemma was used, heuristic decides done_reason
    assert out.text == "Hello world."
    assert out.done_reason == ""   # sentence terminator → clean stop
    router.call_gemma.assert_called_once()


def test_backend_falls_back_to_call_gemma_when_meta_attr_missing():
    """RouterWrapper without `call_gemma_meta` attribute at all → use
    `call_gemma` only. Tests legacy MagicMock pattern with `spec`."""
    from llm.router import RouterWrapper

    # spec=RouterWrapper without our new method on a stripped class
    class _LegacyRouter:
        def call_gemma(self, prompt, **kwargs):
            return "legacy response"

    router = _LegacyRouter()
    out = _run_backend_with_router(router)
    assert out.text == "legacy response"
    # spec doesn't have call_gemma_meta → backend uses legacy path
    # done_reason is "" because text is short and clean
    assert out.done_reason == ""

    # Verify the class doesn't have call_gemma_meta (regression guard)
    assert not hasattr(_LegacyRouter, "call_gemma_meta")
    # Verify the current RouterWrapper *does* expose it
    assert hasattr(RouterWrapper, "call_gemma_meta")


# ─── GemmaClient _last_done_reason stash ─────────────────────────


def test_gemma_client_resets_done_reason_on_each_call():
    """A new call must clear the previous call's stashed
    done_reason so an unrelated cache hit doesn't leak the prior
    truncation signal upward."""
    from core.gemma_client import GemmaClient

    c = GemmaClient()
    c._last_done_reason = "length"   # simulate prior call's stash

    # Call the reset path directly (we don't actually hit Ollama in
    # this unit test — the side effect we're checking is the
    # `self._last_done_reason = ""` line at the top of call_gemma).
    # Easiest: patch requests.post to short-circuit before hitting
    # ollama, but the reset happens before the post call, so we can
    # check the attribute after a deliberately-failing call.
    with patch("requests.post", side_effect=RuntimeError("fail-fast")):
        try:
            c.call_gemma("test prompt", use_cache=False)
        except Exception:
            pass
    # After the failed call, the reset (line at top of call_gemma)
    # already ran → empty stash
    assert c._last_done_reason == ""
