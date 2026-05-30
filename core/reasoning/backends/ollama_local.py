"""Adapter around RouterWrapper.call_gemma — the v0.3.0 default LLM path.

After L1 wiring (Track 1 PR-A, 2026-05-19) every synth call site goes
through ``get_backend("ollama_local").complete(...)`` rather than
RouterWrapper directly. This adapter remains byte-identical to the
v0.3.0 prompt path — the same prompt, the same model, the same
RouterWrapper call — so JAMES with no env overrides behaves exactly
as it did before the wiring.
"""
from __future__ import annotations

import time
from typing import Optional

from core.reasoning.backends import BackendCapability, CompletionResult


class OllamaLocalBackend:
    """Wrap RouterWrapper("general"). Lazy LLM instantiation — importing
    this module must not spin up the LLM router (test isolation +
    autoregistration in core/reasoning/backends/__init__.py).
    """

    backend_id = "ollama_local"

    # D5.B capability declaration. Default Ollama model on a stock
    # install is ``gemma4:e4b`` (4B class) → "small" tier. ``provider``
    # is "local" because RouterWrapper hits ``localhost:11434`` by
    # default. Operators pointing JAMES at a remote Ollama (e.g.
    # Hetzner sovereign) effectively re-tier this backend; v1 records
    # the default deployment and D5.C policy degrades gracefully when
    # the actual ``JAMES_LLM_MODEL`` exceeds the tier expectation.
    capability = BackendCapability(tier="small", provider="local")

    def __init__(self) -> None:
        self._router = None   # constructed on first .complete()

    def _llm(self):
        if self._router is None:
            from llm.router import RouterWrapper
            self._router = RouterWrapper("general")
        return self._router

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        timeout: float = 60.0,
        model: Optional[str] = None,
        use_cache: bool = True,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,
        **opts,
    ) -> CompletionResult:
        # RouterWrapper.call_gemma already absorbs system_prompt via the
        # prompt body in JAMES's existing pattern (modes.py / pipeline.py
        # both prepend "system_prompt\\n\\n" to the user prompt). To stay
        # byte-identical with the v0.3.0 call path, the caller still
        # prepends; we don't double-prepend here.
        composed = f"{system}\n\n{prompt}" if system else prompt

        # D6 follow-up (2026-05-25) — prefer the native Ollama
        # `done_reason` exposed via `RouterWrapper.call_gemma_meta`.
        # Falls back to the legacy `call_gemma` + length+terminator
        # heuristic when:
        #   - RouterWrapper has no `call_gemma_meta` (older deploys
        #     or non-Ollama backends)
        #   - the native signal is empty (Ollama < 0.1.30, or
        #     GemmaClient hit a cache → no fresh ollama response)
        # The fallback preserves the D6 base PR #486 behavior so
        # `complete_with_retry` (`core.reasoning.budget`) still
        # observes a "length" signal on truncation-suspicious text.
        t0 = time.time()
        native_done_reason = ""
        router = self._llm()
        # Native path is attempted only when the router actually has
        # `call_gemma_meta` AND returns a dict. MagicMock auto-creates
        # missing attributes (so `hasattr` alone isn't a usable signal
        # — test mocks would always look like they support the new
        # method). Requiring a dict return value gracefully rejects
        # auto-mocked attributes + future provider implementations
        # that haven't migrated to the dict shape.
        try:
            text = None
            meta_fn = getattr(router, "call_gemma_meta", None)
            if callable(meta_fn):
                try:
                    meta = meta_fn(
                        composed,
                        timeout=timeout,
                        use_cache=use_cache,
                        max_tokens=max_tokens,
                        model=model or None,
                        temperature=temperature,
                        think=think,
                    )
                except Exception:
                    meta = None
                if isinstance(meta, dict):
                    text = meta.get("text", "") or ""
                    native_done_reason = meta.get("done_reason", "") or ""
            if text is None:
                text = router.call_gemma(
                    composed,
                    timeout=timeout,
                    use_cache=use_cache,
                    max_tokens=max_tokens,
                    model=model or None,
                    temperature=temperature,
                    think=think,
                )
        except Exception as e:
            return CompletionResult(
                text="",
                backend_id=self.backend_id,
                model=model or "",
                latency_ms=int((time.time() - t0) * 1000),
                error=f"{type(e).__name__}: {str(e)[:200]}",
            )

        # RouterWrapper returns error strings rather than raising for the
        # known Gemma failure modes — preserve that signal in `error` so
        # downstream emit_trace_step marks the row blocked=True.
        _ERR_PREFIXES = ("[Gemma 응답 없음]", "[Gemma 오류]",
                         "LLM 응답 생성 중 오류")
        is_err = bool(text) and any(text.startswith(p) for p in _ERR_PREFIXES)

        # done_reason resolution: native first, heuristic fallback.
        # Native values follow Ollama's vocabulary ("stop" / "length" /
        # "load" / "" if unavailable). Heuristic only fires when:
        #   - native is empty (signal missing)
        #   - text is non-error
        # so a "stop" from native does NOT get overridden by the
        # heuristic — the precise native signal wins.
        done_reason = ""
        if native_done_reason:
            done_reason = native_done_reason
        elif text and not is_err:
            # Legacy heuristic (PR #486, D6 base) — two-signal:
            #   1. length ≥ 90% × cap × 4 chars (token ≈ 4-char approx)
            #   2. no sentence terminator at end
            # Both must fire to mark as "length".
            char_budget_approx = max(max_tokens, 1) * 4
            length_suspicious = len(text) >= char_budget_approx * 0.9
            stripped = text.rstrip()
            sentence_end = stripped.endswith((
                ".", "?", "!", "다", "요", "음", "}", "]", "\"", "'", ")"
            ))
            if length_suspicious and not sentence_end:
                done_reason = "length"

        return CompletionResult(
            text=text or "",
            backend_id=self.backend_id,
            model=model or "",
            latency_ms=int((time.time() - t0) * 1000),
            error=("backend reported error string" if is_err else ""),
            done_reason=done_reason,
        )


__all__ = ["OllamaLocalBackend"]
