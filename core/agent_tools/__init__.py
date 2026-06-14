"""v0.6.1 Phase C — agent tool registry + dispatcher + LLM tool-use loop.

The pieces here let an LLM (Anthropic Messages API ``tool_use`` or
Ollama function-calling) emit tool-call requests that JAMES dispatches
through the existing Phase 5.5 sandbox (`tools/code/sandbox.py`),
back-channels the results into the LLM loop, and audits every step.

Public surface:

  * :class:`Tool` — frozen dataclass describing one callable.
  * :func:`register_tool`, :func:`get_tool`, :func:`list_tools` —
    in-memory registry.
  * :func:`dispatch` — single entry point used by the agent-chat
    endpoint AND by anyone calling tools directly (operator scripts,
    tests). Centralises sandbox + audit + timeout.
  * :data:`MAX_TOOL_TIMEOUT_SEC` — global cap; individual tools may
    set a lower per-call timeout.

The 6 built-in tools live in :mod:`core.agent_tools.builtins`. They
are registered at module import; importing this package surface
auto-registers them via the builtins module's side effects.

LLM backends live in :mod:`core.agent_tools.backends`.

See ``docs/design/v0.6-agent-tools-user-paths.md`` §2 (G-B / G-C)
and ``ARCHITECTURE.md`` §5.7.15.
"""
from __future__ import annotations

from core.agent_tools.registry import (  # noqa: F401
    MAX_TOOL_TIMEOUT_SEC,
    Tool,
    ToolError,
    get_tool,
    list_tools,
    register_tool,
)
from core.agent_tools.dispatcher import dispatch  # noqa: F401

# Auto-register built-in tools at package import time. Side-effect
# import is intentional (matches `tools/__init__.py` pattern).
from core.agent_tools import builtins  # noqa: F401

__all__ = [
    "MAX_TOOL_TIMEOUT_SEC",
    "Tool",
    "ToolError",
    "get_tool",
    "list_tools",
    "register_tool",
    "dispatch",
]
