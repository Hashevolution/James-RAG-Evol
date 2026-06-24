"""Claude Code CLI agent backend (v0.6.1).

Cloud Claude via the local Claude Code CLI (``claude -p``), which uses the
operator's **Max-plan login — no API key required**. Split out of
``backends.py`` to keep that module under the 20 KB gate (rule #5).

The CLI returns plain text (no native tool_use), so this backend folds
the tool list into the system prompt (``_tools_prompt``) and the agent
loop's ``_extract_text_tool_call`` recovers the JSON call the model
emits. Gated behind ``JAMES_AGENT_ALLOW_CLOUD=1`` (still cloud egress —
data goes to Anthropic) but, unlike the ``anthropic`` HTTP backend, needs
no ``ANTHROPIC_API_KEY``.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.agent_tools.backends import (
    AgentBackend,
    BackendError,
    ENV_ALLOW_CLOUD,
    ENV_ANTHROPIC_MODEL,
    _DEFAULT_ANTHROPIC_MODEL,
    _settings_get,
    _tools_prompt,
    cloud_allowed,
)


def _messages_to_transcript(messages: List[Dict[str, Any]]) -> str:
    """Flatten the conversation into a single text transcript for the
    `claude -p` CLI (which takes one prompt, not a message array)."""
    label = {"user": "User", "assistant": "Assistant", "tool": "Tool"}
    lines: List[str] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if isinstance(content, str):
            txt = content
        elif isinstance(content, list):
            parts: List[str] = []
            for b in content:
                if not isinstance(b, dict):
                    parts.append(str(b))
                    continue
                bt = b.get("type")
                if bt == "text":
                    parts.append(b.get("text") or "")
                elif bt == "tool_use":
                    parts.append(
                        f"[called {b.get('name')} with "
                        f"{json.dumps(b.get('input') or {}, ensure_ascii=False)}]")
                elif bt == "tool_result":
                    c = b.get("content")
                    if not isinstance(c, str):
                        try:
                            c = json.dumps(c, ensure_ascii=False)
                        except Exception:
                            c = str(c)
                    parts.append(f"[tool result: {c}]")
            txt = "\n".join(p for p in parts if p)
        else:
            txt = "" if content is None else json.dumps(content, ensure_ascii=False)
        lines.append(f"{label.get(role, role)}: {txt}")
    lines.append("Assistant:")
    return "\n".join(lines)


class ClaudeCliBackend(AgentBackend):
    name = "claude_cli"

    def __init__(self, model: Optional[str] = None, timeout: float = 120.0):
        if not cloud_allowed():
            raise BackendError(
                f"claude_cli backend disabled by default — it sends data to "
                f"Anthropic via the Claude CLI (Max-plan login). Enable cloud "
                f"on the agent page or set {ENV_ALLOW_CLOUD}=1 to opt in (no "
                f"API key needed; the `claude` CLI must be installed and "
                f"logged in)."
            )
        self.model = (model
                      or _settings_get("agent_anthropic_model",
                                       ENV_ANTHROPIC_MODEL,
                                       _DEFAULT_ANTHROPIC_MODEL)).strip() or None
        self.timeout = timeout

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        try:
            from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend
        except Exception as e:  # noqa: BLE001
            raise BackendError(f"claude cli backend unavailable: {e}")

        sys_full = ((system + "\n\n") if system else "") + _tools_prompt(tools)
        prompt = _messages_to_transcript(messages)
        try:
            res = ClaudeCodeCliBackend().complete(
                prompt, system=sys_full, model=self.model,
                max_tokens=max_tokens, timeout=self.timeout,
                # The CLI must NOT use its own tools (it would run agentic
                # file ops in a sandboxed temp cwd and never reach the
                # operator's registered folders). Force pure-text output;
                # JAMES dispatches the tool call it emits.
                disallow_tools=True,
            )
        except Exception as e:  # noqa: BLE001
            raise BackendError(f"claude cli error: {e}")
        if getattr(res, "error", None):
            raise BackendError(f"claude cli: {res.error}")
        text = (getattr(res, "text", "") or "").strip()
        return {
            "stop_reason": "end_turn",
            "text": text,
            "tool_calls": [],
            "raw": {"backend": "claude_cli"},
        }
