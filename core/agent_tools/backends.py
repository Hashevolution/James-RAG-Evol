"""LLM backends for the agent tool-use loop (v0.6.1 Phase C).

Two backends, runtime-selectable via ``JAMES_AGENT_BACKEND`` env:

  * ``anthropic`` — Anthropic Messages API ``tool_use`` (cloud). Uses
    ``httpx`` directly; no anthropic SDK dependency. API key from
    ``ANTHROPIC_API_KEY``. Cloud egress flows through this module's
    HTTP call — for production deployments, an operator that wants
    abstraction-layer (§5.7.12) masking should set
    ``JAMES_FORCE_CLOUD=1`` and add a wrapper at the call site
    (deferred to Phase E when ``run_shell`` arrives).
  * ``ollama`` — Ollama ``/api/chat`` with ``tools`` array. Local. The
    model must support function-calling (mxtral works well; gemma3:4b
    less reliable). Host from ``OLLAMA_HOST`` (default
    ``http://localhost:11434``); model from ``JAMES_AGENT_OLLAMA_MODEL``
    (default ``mxtral:latest``).

Both backends share the ``AgentBackend`` interface
(``chat_with_tools``) so the agent-chat endpoint can swap without
caring which one is active.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


ENV_BACKEND = "JAMES_AGENT_BACKEND"
ENV_OLLAMA_HOST = "OLLAMA_HOST"
ENV_OLLAMA_MODEL = "JAMES_AGENT_OLLAMA_MODEL"
ENV_ANTHROPIC_KEY = "ANTHROPIC_API_KEY"
ENV_ANTHROPIC_MODEL = "JAMES_AGENT_ANTHROPIC_MODEL"

# Risk #2 mitigation (2026-06-15): the AnthropicBackend talks directly
# to api.anthropic.com via httpx, bypassing the §5.7.12 cloud-egress
# abstraction trust zone (mask / PolicyEngine / audit `reason:egress`
# row). Until Phase E wraps the call site, instantiation is gated on
# an explicit opt-in env so a stock JAMES install can NOT silently
# leak operator data to a third-party service. Default behaviour:
# anthropic backend refuses to initialise. Operator that knowingly
# accepts the trade-off sets `JAMES_AGENT_ALLOW_CLOUD=1`.
ENV_ALLOW_CLOUD = "JAMES_AGENT_ALLOW_CLOUD"


class BackendError(Exception):
    """LLM backend call failed (HTTP / parse / missing key)."""


class AgentBackend(ABC):
    """Each backend takes a conversation + the JAMES tool registry's
    schema list and returns:

      ``{"stop_reason": "tool_use"|"end_turn"|"error",
         "text": "...",                     # for end_turn / error
         "tool_calls": [                   # for tool_use
            {"id": "...", "name": "...", "input": {...}}
         ],
         "raw": {...}                      # backend-specific echo
        }``

    The agent-chat endpoint loops: send messages → if ``tool_use``,
    dispatch each call + append a tool-result message → send again.
    """

    name: str = "base"

    @abstractmethod
    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        ...


# ── Anthropic ────────────────────────────────────────────────────

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


class AnthropicBackend(AgentBackend):
    name = "anthropic"

    def __init__(self,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: float = 60.0):
        # Risk #2 (2026-06-15): cloud-egress gate. Refuse to construct
        # unless the operator has explicitly opted in. See module-level
        # ENV_ALLOW_CLOUD docstring.
        allow = (os.environ.get(ENV_ALLOW_CLOUD) or "").strip().lower()
        if allow not in ("1", "true", "yes", "on", "enabled"):
            raise BackendError(
                f"anthropic backend disabled by default — bypasses §5.7.12 "
                f"abstraction trust zone (cloud egress mask + audit). Set "
                f"{ENV_ALLOW_CLOUD}=1 to opt in (Phase E will wrap this "
                f"call site)."
            )
        self.api_key = api_key or os.environ.get(ENV_ANTHROPIC_KEY, "").strip()
        if not self.api_key:
            raise BackendError(
                f"{ENV_ANTHROPIC_KEY} env not set; cannot use anthropic backend"
            )
        self.model = (model
                      or _settings_get("agent_anthropic_model",
                                        ENV_ANTHROPIC_MODEL,
                                        _DEFAULT_ANTHROPIC_MODEL)).strip()
        self.timeout = timeout

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        import httpx

        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
        }
        if system:
            body["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(_ANTHROPIC_URL, headers=headers,
                                    content=json.dumps(body))
        except httpx.HTTPError as e:
            raise BackendError(f"anthropic http error: {e}")
        if resp.status_code >= 400:
            raise BackendError(
                f"anthropic {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise BackendError(f"anthropic bad json: {e}")

        # Parse Anthropic response shape:
        #   content: [{type:"text"|"tool_use", ...}]
        #   stop_reason: "end_turn" | "tool_use" | ...
        stop_reason = data.get("stop_reason") or "end_turn"
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for block in data.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text") or "")
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input") or {},
                })
        return {
            "stop_reason": stop_reason,
            "text": "".join(text_parts).strip(),
            "tool_calls": tool_calls,
            "raw": data,
        }


# ── Ollama ───────────────────────────────────────────────────────

_DEFAULT_OLLAMA_HOST = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "mxtral:latest"


class OllamaBackend(AgentBackend):
    name = "ollama"

    def __init__(self,
                 host: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: float = 120.0):
        self.host = (host or os.environ.get(ENV_OLLAMA_HOST)
                     or _DEFAULT_OLLAMA_HOST).rstrip("/")
        self.model = (model
                      or _settings_get("agent_ollama_model",
                                        ENV_OLLAMA_MODEL,
                                        _DEFAULT_OLLAMA_MODEL)).strip()
        self.timeout = timeout

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        import httpx

        # Ollama expects tools in OpenAI function-call schema:
        #   {type:"function", function:{name, description, parameters}}
        ol_tools = [{
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description") or "",
                "parameters": t.get("input_schema") or {"type": "object"},
            },
        } for t in tools]

        msgs = list(messages)
        if system:
            msgs = [{"role": "system", "content": system}] + msgs

        body = {
            "model": self.model,
            "messages": msgs,
            "tools": ol_tools,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        url = self.host + "/api/chat"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, content=json.dumps(body),
                                    headers={"Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise BackendError(f"ollama http error: {e}")
        if resp.status_code >= 400:
            raise BackendError(f"ollama {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise BackendError(f"ollama bad json: {e}")

        msg = data.get("message") or {}
        text = (msg.get("content") or "").strip()
        raw_calls = msg.get("tool_calls") or []
        tool_calls: List[Dict[str, Any]] = []
        for i, call in enumerate(raw_calls):
            fn = call.get("function") or {}
            args = fn.get("arguments")
            # Ollama may return arguments as a JSON string OR a dict.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tool_calls.append({
                "id": call.get("id") or f"ollama-{i}",
                "name": fn.get("name"),
                "input": args or {},
            })
        stop_reason = "tool_use" if tool_calls else "end_turn"
        return {
            "stop_reason": stop_reason,
            "text": text,
            "tool_calls": tool_calls,
            "raw": data,
        }


# ── Factory ──────────────────────────────────────────────────────

def _settings_get(key: str, env_name: str, default: str) -> str:
    """v0.6.1 — DB-first via core.llm_settings, env fallback."""
    try:
        from core.llm_settings import get as _get
        return _get(key, env_name, default)
    except Exception:
        return os.environ.get(env_name, default)


def get_backend(name: Optional[str] = None,
                model: Optional[str] = None) -> AgentBackend:
    """Resolve the active backend from ``name`` (test / UI override) or
    the unified LLM settings repository (DB-first, ``JAMES_AGENT_BACKEND``
    env fallback). Defaults to ``ollama`` (local-first is JAMES'
    identity).

    ``model`` is an optional per-call model override (the agent-chat UI
    passes the dropdown selection). An empty string is treated as "no
    override" so the backend falls back to the DB / env / default model.
    """
    selected = (name or _settings_get("agent_backend", ENV_BACKEND, "ollama")).strip().lower()
    model = (model or "").strip() or None
    if selected == "anthropic":
        return AnthropicBackend(model=model)
    if selected == "ollama":
        return OllamaBackend(model=model)
    raise BackendError(
        f"unknown backend {selected!r}; expected 'anthropic' or 'ollama'"
    )


def tools_to_schema(tools_list) -> List[Dict[str, Any]]:
    """Convert ``Tool`` instances into the schema list both backends
    accept (`{name, description, input_schema}`)."""
    return [{
        "name": t.name,
        "description": t.description,
        "input_schema": t.input_schema,
    } for t in tools_list]
