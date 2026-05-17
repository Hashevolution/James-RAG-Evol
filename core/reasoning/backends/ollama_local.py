"""Adapter around RouterWrapper.call_gemma — the v0.3.0 default LLM path.

Byte-identical to existing core/reasoning/pipeline.py calls. L1's
wiring step will swap ``engine.llm.call_gemma(prompt, ...)`` for
``get_backend("ollama_local").complete(prompt, ...)`` without changing
which model runs or what prompt format reaches it.
"""
from __future__ import annotations

import time
from typing import Optional

from core.reasoning.backends import CompletionResult


class OllamaLocalBackend:
    """Wrap RouterWrapper("general"). Lazy LLM instantiation — importing
    this module must not spin up the LLM router (test isolation +
    autoregistration in core/reasoning/backends/__init__.py).
    """

    backend_id = "ollama_local"

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
        **opts,
    ) -> CompletionResult:
        # RouterWrapper.call_gemma already absorbs system_prompt via the
        # prompt body in JAMES's existing pattern (modes.py / pipeline.py
        # both prepend "system_prompt\\n\\n" to the user prompt). To stay
        # byte-identical with the v0.3.0 call path, the caller still
        # prepends; we don't double-prepend here.
        composed = f"{system}\n\n{prompt}" if system else prompt

        t0 = time.time()
        try:
            text = self._llm().call_gemma(
                composed,
                timeout=timeout,
                use_cache=use_cache,
                max_tokens=max_tokens,
                model=model or None,
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

        return CompletionResult(
            text=text or "",
            backend_id=self.backend_id,
            model=model or "",
            latency_ms=int((time.time() - t0) * 1000),
            error=("backend reported error string" if is_err else ""),
        )


__all__ = ["OllamaLocalBackend"]
