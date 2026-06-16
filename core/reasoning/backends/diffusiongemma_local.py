"""DiffusionGemma backend — OpenAI-compatible HTTP adapter.

Spike — v0.6.1 v18 (2026-06-16).

Target serving stack: **vLLM** (native DiffusionGemma support since
2026 — `vllm.entrypoints.openai.api_server`) or **llama.cpp-server**
(Unsloth GGUF). Either exposes `/v1/chat/completions` with the same
shape as the OpenAI API, so this adapter doesn't care which one is
running — it just speaks the wire format.

Why an HTTP adapter and not an Ollama tag:
  - Ollama IS a valid serving path (Unsloth GGUF + ``ollama create``)
    and would work transparently through the existing ``ollama_local``
    backend. This adapter exists for the operator who runs vLLM or
    llama.cpp-server directly, which is the configuration that
    matches the public DiffusionGemma latency claim (1,100 tok/s,
    block-parallel denoising). Going through Ollama gives the
    correctness but not the speed.
  - It also keeps the diffusion-specific quirks (no Ollama
    ``done_reason``, model-side block size, denoising schedule)
    isolated from the byte-identical Ollama path.

Activation (off by default — explicit opt-in):

    JAMES_ENABLE_DIFFUSIONGEMMA=1     # register the backend at boot
    JAMES_DIFFUSIONGEMMA_URL=http://127.0.0.1:8001
                                       # vLLM / llama.cpp-server base
                                       # (without /v1)
    JAMES_DIFFUSIONGEMMA_MODEL=google/diffusiongemma-26b-a4b-it
                                       # name the server registered

then routing:

    JAMES_REASONING_BACKEND=diffusiongemma_local
    # or per-stage:
    JAMES_BACKEND_SYNTH=diffusiongemma_local

A stock JAMES install with none of those set never reaches this
adapter — same opt-in pattern as ``claude_code_cli``.

Honest framing — this is a SPIKE. No quality / latency claim is made
by registering the adapter. The Direction α paired measurement
harness (``scripts/research/local_vs_cloud_paired.py``) is the
gatekeeper: run a 5-axis Quality Delta Card against
``gemma4:e4b`` before promoting this backend to anyone's default.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

from core.reasoning.backends import BackendCapability, CompletionResult


_DEFAULT_URL = "http://127.0.0.1:8001"
_DEFAULT_MODEL = "google/diffusiongemma-26b-a4b-it"
# A pathological prompt should not let the operator turn an LLM call
# into a denial-of-service. 1 MiB is the same bound the Claude CLI
# backend applies. Diffusion canvas is fixed-size and short
# generations are the typical case for JAMES (abstention / citation),
# so the bound is conservative.
_MAX_PROMPT_BYTES = 1024 * 1024


def _resolve_url() -> str:
    return (os.environ.get("JAMES_DIFFUSIONGEMMA_URL") or _DEFAULT_URL).rstrip("/")


def _resolve_model() -> str:
    return os.environ.get("JAMES_DIFFUSIONGEMMA_MODEL") or _DEFAULT_MODEL


class DiffusionGemmaLocalBackend:
    """OpenAI-compatible /v1/chat/completions caller.

    Stateless. The shared ``requests.Session`` is constructed lazily
    on the first call so importing the module never opens a socket;
    tests inject a fake session via ``self._session = ...``.
    """

    backend_id = "diffusiongemma_local"

    # D5.B capability declaration. DiffusionGemma is a 26B MoE with
    # 3.8B active params — sits between "small" (≤4B) and "medium"
    # (12-27B). Declaring "medium" since the operator-facing
    # serving cost (VRAM, throughput) matches the medium tier
    # rather than the small one. ``provider="local"`` because the
    # adapter hits a localhost URL by default; an operator pointing
    # ``JAMES_DIFFUSIONGEMMA_URL`` at a remote sovereign endpoint
    # effectively re-tiers the provider, same as ``ollama_local``.
    capability = BackendCapability(tier="medium", provider="local")

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        # Constructor-time resolution = snapshot at registry boot.
        # Tests pass explicit overrides; production reads env.
        self._url = (url or _resolve_url()).rstrip("/")
        self._model = model or _resolve_model()
        self._session: Optional[requests.Session] = None

    # ── Public API ────────────────────────────────────────────────

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        timeout: float = 60.0,
        model: Optional[str] = None,
        use_cache: bool = True,        # accepted, not honored (HTTP layer)
        temperature: Optional[float] = None,
        think: Optional[bool] = None,   # accepted, not honored
        **opts,                         # tolerate future kwargs
    ) -> CompletionResult:
        t0 = time.time()
        url = f"{self._url}/v1/chat/completions"
        chosen_model = (model or self._model).strip() or _DEFAULT_MODEL

        # Compose chat messages — system+user pair, mirroring the
        # OpenAI shape. JAMES's existing modes.py / pipeline.py pass
        # system_prompt to .complete; we surface it as a real role
        # rather than joining into the user content so the diffusion
        # canvas can route it to the system slot in its template.
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system[:_MAX_PROMPT_BYTES]})
        messages.append({"role": "user", "content": (prompt or "")[:_MAX_PROMPT_BYTES]})

        body: Dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "max_tokens": int(max(1, max_tokens)),
            "stream": False,
        }
        if temperature is not None:
            body["temperature"] = float(temperature)

        try:
            session = self._get_session()
        except Exception as e:
            # session construction is trivial — but guard for the
            # paranoid case where requests itself is broken.
            return CompletionResult(
                text="", backend_id=self.backend_id, model=chosen_model,
                latency_ms=int((time.time() - t0) * 1000),
                error=f"session init failed: {type(e).__name__}: {str(e)[:120]}",
            )

        # ── HTTP round trip ──
        try:
            resp = session.post(
                url,
                data=json.dumps(body),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=timeout,
            )
        except requests.Timeout:
            return CompletionResult(
                text="", backend_id=self.backend_id, model=chosen_model,
                latency_ms=int((time.time() - t0) * 1000),
                error="timeout",
            )
        except requests.RequestException as e:
            return CompletionResult(
                text="", backend_id=self.backend_id, model=chosen_model,
                latency_ms=int((time.time() - t0) * 1000),
                error=f"{type(e).__name__}: {str(e)[:120]}",
            )

        latency_ms = int((time.time() - t0) * 1000)

        if resp.status_code != 200:
            # Body might be JSON {"error": {...}} or a vLLM stack
            # trace. Trim either way so a 5 MB error page doesn't
            # land in the trace store.
            body_snippet = (resp.text or "")[:200].strip()
            return CompletionResult(
                text="", backend_id=self.backend_id, model=chosen_model,
                latency_ms=latency_ms,
                error=f"HTTP {resp.status_code}: {body_snippet}",
            )

        try:
            data = resp.json()
        except ValueError as e:
            return CompletionResult(
                text="", backend_id=self.backend_id, model=chosen_model,
                latency_ms=latency_ms,
                error=f"non-JSON response: {type(e).__name__}",
            )

        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            return CompletionResult(
                text="", backend_id=self.backend_id, model=chosen_model,
                latency_ms=latency_ms,
                error="response has no choices[]",
            )

        first = choices[0] if isinstance(choices[0], dict) else {}
        msg = first.get("message") if isinstance(first.get("message"), dict) else {}
        text = (msg.get("content") or "") if isinstance(msg, dict) else ""
        # OpenAI-compatible servers (vLLM / llama.cpp-server) populate
        # ``finish_reason`` with the same vocabulary ("stop", "length",
        # …) Ollama's ``done_reason`` uses, so we forward it verbatim.
        finish_reason = first.get("finish_reason") or ""
        done_reason = "length" if finish_reason == "length" else ""

        return CompletionResult(
            text=text or "",
            backend_id=self.backend_id,
            model=chosen_model,
            latency_ms=latency_ms,
            error="",
            done_reason=done_reason,
        )

    # ── Internal helpers ───────────────────────────────────────────

    def _get_session(self) -> requests.Session:
        # Lazy so importing the module is free of side effects.
        if self._session is None:
            self._session = requests.Session()
        return self._session


__all__ = ["DiffusionGemmaLocalBackend"]
