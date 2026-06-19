"""Tool registry (v0.6.1 Phase C).

In-memory only. Built-in tools are registered at import time from
``core/agent_tools/builtins.py``. Future tools (e.g. the deferred
Phase E ``run_shell``) register here as well.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# Global cap. Individual tools MAY pin a lower per-call timeout via
# ``Tool.timeout_sec``; the dispatcher takes ``min(tool.timeout_sec,
# MAX_TOOL_TIMEOUT_SEC)``.
MAX_TOOL_TIMEOUT_SEC = 30


class ToolError(Exception):
    """Raised by tool handlers when input validation or execution
    fails in a way the caller should surface to the LLM as
    ``is_error: true`` rather than crashing the chat loop."""


@dataclass(frozen=True)
class Tool:
    """One callable an LLM may invoke via tool_use / function_call.

    ``input_schema`` follows the JSON-Schema-ish shape Anthropic and
    Ollama both accept (``{"type": "object", "properties": {...},
    "required": [...]}``). The dispatcher does NOT enforce schema
    validation beyond what each handler validates itself — schema is
    metadata for the LLM, not a runtime guard. Handlers MUST validate
    their own inputs (path safety etc.).
    """

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any], str], Any]   # (args, role) → result
    timeout_sec: int = MAX_TOOL_TIMEOUT_SEC
    # When True, the dispatcher writes an audit row BEFORE calling the
    # handler so a crash inside the handler still leaves a trace.
    # Default True; tools that produce huge output (e.g. read_file)
    # may skip the after-row to keep audit_log small.
    audit_pre_call: bool = True
    audit_post_call: bool = True


_TOOLS: Dict[str, Tool] = {}


def register_tool(tool: Tool) -> None:
    """Add ``tool`` to the registry. Overwrites an existing entry of
    the same name (last-write-wins; tests rely on this)."""
    if not isinstance(tool, Tool):
        raise TypeError("register_tool expects a Tool instance")
    if not tool.name or "/" in tool.name or "\\" in tool.name:
        raise ValueError(f"invalid tool name: {tool.name!r}")
    _TOOLS[tool.name] = tool


def get_tool(name: str) -> Optional[Tool]:
    return _TOOLS.get(name)


def list_tools() -> List[Tool]:
    """Deterministic order — registration order preserved by the
    underlying dict."""
    return list(_TOOLS.values())


def _clear_for_tests() -> None:
    """Internal helper for unit tests; not exported."""
    _TOOLS.clear()
