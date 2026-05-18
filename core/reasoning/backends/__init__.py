"""Backend registry for the cognitive middleware layer (L0 MVP).

ARCHITECTURE.md §5.7.2 contract: LLM 호출은 명명된 어댑터를 통해서만
발생, 미들웨어는 모델 SDK 직접 import 금지. 새 백엔드는 registry 만
확장, schema (core/reasoning/trace_schema.TraceStep) 는 확장 안 함.

Two adapters ship with L0:

  - ``ollama_local``     — wraps the existing RouterWrapper.call_gemma
                           path; byte-identical to v0.3.0 behavior.
                           Always registered.
  - ``claude_code_cli``  — spawns the `claude` CLI as a subprocess.
                           Registered only when the operator opts in via
                           ``JAMES_ENABLE_CLAUDE_BACKEND=1`` — off by
                           default so a stock JAMES install never reaches
                           an external CLI without explicit consent.

L0 is wiring-free — the registry exists but core/reasoning/pipeline.py
still calls ``engine.llm.call_gemma(...)`` directly. L1 swaps those call
sites onto ``get_backend(name).complete(...)`` + emit_trace_step.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Protocol, runtime_checkable


@dataclass(frozen=True)
class CompletionResult:
    """One backend's response. Backends never raise on the user-facing
    path — they return ``error="..."`` and let the caller decide. This
    matches RouterWrapper's existing "_LLM_ERROR_PREFIXES" pattern in
    core/reasoning/engine.py.
    """
    text: str
    backend_id: str
    model: str = ""
    latency_ms: int = 0
    error: str = ""


@runtime_checkable
class Backend(Protocol):
    """Every backend exposes one method. Optional kwargs (system,
    max_tokens, timeout) match the shape pipeline.py already passes to
    ``call_gemma`` — L1's wiring stays mechanical.
    """
    backend_id: str

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        timeout: float = 60.0,
        **opts,
    ) -> CompletionResult: ...


_REGISTRY: Dict[str, Backend] = {}


def register_backend(name: str, backend: Backend) -> None:
    """Add a backend to the registry. Idempotent re-registration with
    the same instance is allowed (re-imports under test runners); a
    different instance under the same name raises so we don't silently
    overwrite an in-flight backend.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("backend name must be a non-empty str")
    if not isinstance(backend, Backend):
        raise TypeError(
            f"object registered as {name!r} does not satisfy the "
            f"Backend protocol (missing .complete or .backend_id)"
        )
    existing = _REGISTRY.get(name)
    if existing is not None and existing is not backend:
        raise ValueError(
            f"backend {name!r} already registered with a different instance"
        )
    _REGISTRY[name] = backend


def get_backend(name: str) -> Backend:
    """Look a backend up. Unknown name → KeyError; the opt-in pattern
    is intentional — a caller asking for ``claude_code_cli`` when the
    operator hasn't enabled it gets a loud failure, not silent fallback.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"no backend registered for {name!r}; "
            f"known: {sorted(_REGISTRY)}"
        ) from None


def list_backends() -> Dict[str, Backend]:
    """Shallow copy of the registry — tests inspect this; production
    code goes through get_backend.
    """
    return dict(_REGISTRY)


def _clear_for_tests() -> None:
    """Test helper. Production code never calls this."""
    _REGISTRY.clear()


def get_default_backend_id() -> str:
    """Resolve the default backend name for cognitive stages.

    Reads ``JAMES_REASONING_BACKEND`` from the environment. Empty /
    unset → ``"ollama_local"`` (the v0.3.0 byte-identical default).
    When set, the value is validated against ``_REGISTRY``:

      * Known backend (e.g. ``claude_code_cli`` while
        ``JAMES_ENABLE_CLAUDE_BACKEND=1``) → use it.
      * Unknown name (typo, or claude_code_cli requested without the
        opt-in env) → warn once + fall back to ollama_local. This
        avoids the failure mode where a misspelled env silently
        breaks every cognitive stage at once.

    Each stage module calls this at import time, so changing the
    env requires a server restart (the existing JAMES pattern).
    """
    requested = os.environ.get("JAMES_REASONING_BACKEND", "").strip()
    if not requested:
        return "ollama_local"
    if requested in _REGISTRY:
        return requested
    # The Claude backend requires its own opt-in (JAMES_ENABLE_CLAUDE_BACKEND=1)
    # before it joins the registry — so a JAMES_REASONING_BACKEND=claude_code_cli
    # without that flag lands here. Print rather than raise so a typo or
    # half-configured operator setup doesn't take the pipeline down.
    print(
        f"[BACKEND] JAMES_REASONING_BACKEND={requested!r} not registered "
        f"(known: {sorted(_REGISTRY)}) → fallback to 'ollama_local'. "
        f"For Claude backend also set JAMES_ENABLE_CLAUDE_BACKEND=1."
    )
    return "ollama_local"


# ─── auto-registration ─────────────────────────────────────────────
# ollama_local is always registered — it wraps RouterWrapper which is
# the v0.3.0 default path. claude_code_cli is opt-in via env so a stock
# install can't accidentally route prompts to an external CLI.

def _autoregister() -> None:
    from core.reasoning.backends.ollama_local import OllamaLocalBackend
    register_backend("ollama_local", OllamaLocalBackend())

    if os.environ.get("JAMES_ENABLE_CLAUDE_BACKEND") == "1":
        from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend
        register_backend("claude_code_cli", ClaudeCodeCliBackend())


_autoregister()


__all__ = [
    "Backend",
    "CompletionResult",
    "register_backend",
    "get_backend",
    "list_backends",
    "get_default_backend_id",
]
