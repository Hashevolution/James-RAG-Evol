"""D6 — `complete_with_retry` + `OllamaLocalBackend.done_reason` heuristic.

Closes the D1 design-intent ↔ wiring gap (retry_doubled was defined
and contract-tested but never called from any production call site).

Coverage:
  • `complete_with_retry` retries when `done_reason == "length"`
  • Single retry only (no spiral)
  • Cap saturated at `max_cap` (default CAP_HEAVY) — no extra call
  • Backends without `done_reason` attribute → pre-D6 behavior (no retry)
  • Backends with `done_reason == ""` → no retry
  • `**opts` forwarded on both first call and retry
  • `OllamaLocalBackend.done_reason` heuristic — length-suspicious +
    no-sentence-end → "length"; clean stop → ""
"""

from __future__ import annotations

from unittest.mock import MagicMock

from core.reasoning.backends import CompletionResult
from core.reasoning.budget import (
    CAP_HEAVY,
    CAP_LIGHT,
    CAP_SUBSTITUTION,
    complete_with_retry,
    retry_doubled,
)


# ─── complete_with_retry — happy paths ────────────────────────────


def test_no_retry_when_done_reason_empty():
    """Default — backend returns clean response, no done_reason. No retry."""
    backend = MagicMock()
    backend.complete.return_value = CompletionResult(
        text="ok", backend_id="stub", done_reason=""
    )
    out = complete_with_retry(backend, "any", cap=CAP_LIGHT)
    assert out.text == "ok"
    backend.complete.assert_called_once()


def test_no_retry_when_done_reason_stop():
    """Other terminal reasons (e.g. ollama 'stop') do not trigger retry."""
    backend = MagicMock()
    backend.complete.return_value = CompletionResult(
        text="ok", backend_id="stub", done_reason="stop"
    )
    out = complete_with_retry(backend, "any", cap=CAP_LIGHT)
    assert out.text == "ok"
    backend.complete.assert_called_once()


def test_retry_fires_on_done_reason_length():
    """The D6 happy path — truncation detected → one retry with doubled cap."""
    backend = MagicMock()
    backend.complete.side_effect = [
        CompletionResult(text="trunc...", backend_id="stub", done_reason="length"),
        CompletionResult(text="full answer", backend_id="stub", done_reason=""),
    ]
    out = complete_with_retry(backend, "any", cap=CAP_LIGHT)
    assert out.text == "full answer"
    assert backend.complete.call_count == 2
    # Second call must use doubled cap
    first_cap = backend.complete.call_args_list[0].kwargs["max_tokens"]
    second_cap = backend.complete.call_args_list[1].kwargs["max_tokens"]
    assert first_cap == CAP_LIGHT
    assert second_cap == retry_doubled(CAP_LIGHT, max_cap=CAP_HEAVY)


def test_retry_only_once_even_if_still_truncated():
    """A misclassified light task that's still truncated at the retry cap
    should NOT spiral — return the second result and stop."""
    backend = MagicMock()
    backend.complete.return_value = CompletionResult(
        text="still trunc...", backend_id="stub", done_reason="length"
    )
    complete_with_retry(backend, "any", cap=CAP_LIGHT)
    # The function returns the *retry* result when one was issued —
    # in this case the second (still-truncated) response, not a third.
    assert backend.complete.call_count == 2


def test_retry_capped_at_max_cap():
    """Already at CAP_HEAVY → no retry (cap can't grow)."""
    backend = MagicMock()
    backend.complete.return_value = CompletionResult(
        text="trunc at heavy", backend_id="stub", done_reason="length"
    )
    out = complete_with_retry(backend, "any", cap=CAP_HEAVY)
    assert backend.complete.call_count == 1
    assert out.text == "trunc at heavy"


def test_retry_with_custom_max_cap():
    """Caller can lower the ceiling; retry honors it."""
    backend = MagicMock()
    backend.complete.return_value = CompletionResult(
        text="trunc", backend_id="stub", done_reason="length"
    )
    complete_with_retry(backend, "any", cap=400, max_cap=600)
    # 400 * 2 = 800, but max_cap=600 → retry to 600
    assert backend.complete.call_count == 2
    assert backend.complete.call_args_list[1].kwargs["max_tokens"] == 600


# ─── backward compat — backends without `done_reason` ────────────


def test_backend_without_done_reason_attr_no_retry():
    """A pre-D6 backend / plugin backend that doesn't set `done_reason`
    should never trigger retry. Pre-D6 behavior preserved."""
    class _LegacyResult:
        """Mimic a CompletionResult without the done_reason field."""
        text = "ok"
        backend_id = "legacy"
        error = ""
        # No `done_reason` attribute at all

    backend = MagicMock()
    backend.complete.return_value = _LegacyResult()
    complete_with_retry(backend, "any", cap=CAP_LIGHT)
    backend.complete.assert_called_once()


# ─── kwargs forwarded ──────────────────────────────────────────────


def test_opts_forwarded_on_both_calls():
    """`**opts` (e.g. `system`, `temperature`, `use_cache`) must be
    forwarded as-is on both the first call and the retry."""
    backend = MagicMock()
    backend.complete.side_effect = [
        CompletionResult(text="trunc", backend_id="stub", done_reason="length"),
        CompletionResult(text="full", backend_id="stub", done_reason=""),
    ]
    complete_with_retry(
        backend, "any", cap=CAP_SUBSTITUTION,
        timeout=30.0, system="sys prompt", temperature=0.5,
    )
    for call in backend.complete.call_args_list:
        assert call.kwargs["timeout"] == 30.0
        assert call.kwargs["system"] == "sys prompt"
        assert call.kwargs["temperature"] == 0.5


# ─── OllamaLocalBackend.done_reason heuristic ─────────────────────


class _FakeRouter:
    """Stand-in for RouterWrapper. The test sets `_response_text` to
    control what `call_gemma` returns."""

    def __init__(self, response_text):
        self._response_text = response_text

    def call_gemma(self, prompt, **kwargs):
        return self._response_text


def _run_ollama(text, max_tokens):
    """Construct an OllamaLocalBackend that returns `text` and call
    `.complete(...)` with the given `max_tokens`. Returns the
    CompletionResult."""
    from core.reasoning.backends.ollama_local import OllamaLocalBackend

    b = OllamaLocalBackend()
    b._router = _FakeRouter(text)  # bypass lazy init
    return b.complete("any prompt", max_tokens=max_tokens)


def test_ollama_done_reason_empty_on_clean_stop():
    # Short response ending with a sentence terminator → no truncation
    out = _run_ollama("Hello. This is fine.", max_tokens=1000)
    assert out.done_reason == ""


def test_ollama_done_reason_length_on_long_no_sentence_end():
    # Long response (≥ 90% of cap×4 chars) ending with no terminator
    # → truncation suspected. cap=100 tokens → 400 chars budget →
    # 360+ chars without terminator triggers.
    truncated = "x" * 380  # 380 chars, no sentence end
    out = _run_ollama(truncated, max_tokens=100)
    assert out.done_reason == "length"


def test_ollama_done_reason_empty_when_long_but_sentence_ends():
    # Long response BUT ends with terminator — natural stop
    long_clean = ("Lorem ipsum dolor sit amet, consectetur. " * 9).rstrip()
    out = _run_ollama(long_clean, max_tokens=100)
    # Ends with "." → clean stop
    assert out.done_reason == ""


def test_ollama_done_reason_empty_when_short_no_sentence_end():
    # Short response without terminator — but not length-suspicious
    out = _run_ollama("short", max_tokens=1000)
    assert out.done_reason == ""


def test_ollama_done_reason_handles_korean_terminator():
    # Korean common terminators '다', '요', '음' must register as clean stop
    out = _run_ollama("팔란티어는 데이터 분석 회사입니다", max_tokens=10)
    # Ends with "다" → clean stop
    assert out.done_reason == ""


def test_ollama_done_reason_handles_json_terminator():
    # JSON-style outputs ending with `}` or `]` are clean stops
    out = _run_ollama('{"grounded": true}', max_tokens=10)
    assert out.done_reason == ""
