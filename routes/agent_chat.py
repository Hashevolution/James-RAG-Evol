"""Agent chat endpoint (v0.6.1 Phase C).

`POST /agent/chat/` — sends a user message into the LLM tool-use loop:

  1. LLM sees ``messages + tools``.
  2. If response contains ``tool_use``, dispatch each call via the
     `core/agent_tools` registry, append the tool-result as a new
     message, go to (1).
  3. Else return the final assistant text + the trace of every tool
     call that fired.

Admin-only for now (Phase D-2 will add per-call confirm UI before
opening up to non-admin roles). Loop capped at 5 iterations so a
runaway LLM can't drain the workspace.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routes._helpers import (
    _bearer_username,
    _require_admin,
    _write_audit,
    get_role_from_request,
)

router = APIRouter()

MAX_ITERATIONS = 5
DEFAULT_MAX_TOKENS = 1024


class AgentChatRequest(BaseModel):
    api_key: str
    message: str
    history: Optional[List[Dict[str, Any]]] = None
    backend: Optional[str] = None     # "anthropic" | "ollama" override
    max_tokens: Optional[int] = None
    system: Optional[str] = None


@router.post("/agent/chat/", summary="에이전트 챗 (LLM tool-use) [v0.6.1 Phase C]")
async def agent_chat_route(
    body: AgentChatRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Run one user-message turn through the LLM tool-use loop."""
    _require_admin(body.api_key, role)
    username = _bearer_username(request) or "admin"

    from core.agent_tools import dispatch, list_tools
    from core.agent_tools.backends import (
        BackendError,
        get_backend,
        tools_to_schema,
    )

    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="message must be non-empty")

    try:
        backend = get_backend(body.backend)
    except BackendError as e:
        raise HTTPException(status_code=400, detail=str(e))

    tools_schema = tools_to_schema(list_tools())
    max_tokens = max(64, min(int(body.max_tokens or DEFAULT_MAX_TOKENS), 4096))
    system = body.system or (
        "You are JAMES, an auditable knowledge platform's agent. You may "
        "call the listed tools to inspect and modify files in the "
        "operator-allowed folders. Do not invent file paths; ask the "
        "user when uncertain. Keep responses concise."
    )

    # Conversation state. Each backend accepts the Anthropic-style
    # shape; OllamaBackend internally adapts.
    messages: List[Dict[str, Any]] = list(body.history or [])
    messages.append({"role": "user", "content": body.message})

    trace: List[Dict[str, Any]] = []
    final_text = ""
    stop_reason = "end_turn"
    iter_count = 0

    for iter_count in range(1, MAX_ITERATIONS + 1):
        try:
            resp = backend.chat_with_tools(
                messages=messages, tools=tools_schema,
                system=system, max_tokens=max_tokens,
            )
        except BackendError as e:
            _write_audit(role, "/agent/chat/",
                         query=f"iter={iter_count}",
                         answer=f"backend error: {e}")
            raise HTTPException(status_code=502, detail=str(e))

        stop_reason = resp.get("stop_reason") or "end_turn"
        final_text = resp.get("text") or final_text
        calls = resp.get("tool_calls") or []

        if not calls or stop_reason != "tool_use":
            break

        # Append the assistant message that requested the tool use, so
        # the next iteration's history is consistent for both backends.
        assistant_content: List[Dict[str, Any]] = []
        if final_text:
            assistant_content.append({"type": "text", "text": final_text})
        for c in calls:
            assistant_content.append({
                "type": "tool_use",
                "id": c["id"], "name": c["name"], "input": c["input"],
            })
        messages.append({"role": "assistant", "content": assistant_content})

        # Run each tool, capture result.
        tool_result_blocks: List[Dict[str, Any]] = []
        for c in calls:
            d = dispatch(c["name"], c["input"], role=role)
            trace.append({
                "iter": iter_count,
                "name": c["name"],
                "input": c["input"],
                "ok": d.get("ok"),
                "error": d.get("error"),
                "elapsed_ms": d.get("elapsed_ms"),
            })
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": c["id"],
                "is_error": not d.get("ok"),
                "content": (
                    d.get("output") if d.get("ok")
                    else (d.get("error") or "unknown error")
                ),
            })
        messages.append({"role": "user", "content": tool_result_blocks})
        # Loop continues — backend sees the tool result + can decide
        # to call more tools or produce the final text.

    _write_audit(role, "/agent/chat/",
                 query=f"iters={iter_count}",
                 answer=f"stop={stop_reason} calls={len(trace)}")

    return {
        "ok": True,
        "text": final_text,
        "stop_reason": stop_reason,
        "iterations": iter_count,
        "tool_trace": trace,
        "backend": backend.name,
        "by": username,
    }
