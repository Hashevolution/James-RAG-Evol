"""Tool dispatcher (v0.6.1 Phase C).

Single entry point for every tool call. Wraps the handler with:

  * Tool lookup (404-equivalent → ``is_error: true`` for the LLM loop).
  * Audit log: one row before the call, one after (success / error /
    timeout). Both rows include the tool name + role + caller; neither
    includes the full input/output (kept compact for audit_log
    ergonomics).
  * Timeout enforcement via a worker thread + ``join(timeout)``. The
    underlying Phase 5.5 sandbox already kills subprocess children on
    its own timeout, so this layer is the fallback for in-process
    blocking handlers.
  * Uniform return shape ``{ok, output|error, tool_name, elapsed_ms}``
    so the LLM loop never branches on exception types.

The dispatcher does **not** enforce the path safety contract — every
file/edit/grep tool calls ``policy_validate_path`` itself. Defence in
depth.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict

from core.agent_tools.registry import (
    MAX_TOOL_TIMEOUT_SEC,
    ToolError,
    get_tool,
)


def _audit(role: str, tool_name: str, phase: str, detail: str = "") -> None:
    """Write one audit row. Failures here MUST NOT break the tool
    call — the dispatcher is the only audit sink that's allowed to
    swallow exceptions silently (mirrors `tools/code/sandbox.py`
    `log_security_event`)."""
    try:
        from routes._helpers import _write_audit
        _write_audit(
            role,
            f"agent_tool:{tool_name}",
            query=f"phase={phase}",
            answer=(detail or "")[:300],
        )
    except Exception:
        pass


def _err(tool_name: str, msg: str, *, elapsed_ms: int = 0) -> Dict[str, Any]:
    return {
        "ok": False,
        "tool_name": tool_name,
        "error": msg,
        "elapsed_ms": elapsed_ms,
    }


def _ok(tool_name: str, output: Any, *, elapsed_ms: int) -> Dict[str, Any]:
    return {
        "ok": True,
        "tool_name": tool_name,
        "output": output,
        "elapsed_ms": elapsed_ms,
    }


def dispatch(
    tool_name: str,
    args: Dict[str, Any],
    role: str = "admin",
) -> Dict[str, Any]:
    """Look up + run ``tool_name`` with ``args``. Always returns the
    uniform result dict; never raises (except for bugs in this
    module)."""
    tool = get_tool(tool_name)
    if tool is None:
        _audit(role, tool_name, phase="lookup_fail")
        return _err(tool_name, f"unknown tool: {tool_name!r}")

    if not isinstance(args, dict):
        return _err(tool_name, "args must be a dict")

    if tool.audit_pre_call:
        _audit(role, tool_name, phase="pre", detail=str(list(args.keys())))

    timeout = max(1, min(int(tool.timeout_sec or MAX_TOOL_TIMEOUT_SEC),
                         MAX_TOOL_TIMEOUT_SEC))
    result_holder: Dict[str, Any] = {}
    start = time.monotonic()

    def _run():
        try:
            result_holder["value"] = tool.handler(args, role)
        except ToolError as e:
            result_holder["error"] = str(e)
        except Exception as e:  # noqa: BLE001 — handler boundary
            result_holder["error"] = f"{type(e).__name__}: {e}"

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    if th.is_alive():
        # Thread can't be killed cleanly in Python; the daemon flag
        # ensures it dies with the process. The caller sees a timeout
        # error; the handler may continue in the background until it
        # finishes or the process exits. Real subprocess timeouts are
        # handled by the sandbox layer one level down (10s default).
        msg = f"tool timed out after {timeout}s"
        _audit(role, tool_name, phase="timeout", detail=msg)
        return _err(tool_name, msg, elapsed_ms=elapsed_ms)

    if "error" in result_holder:
        msg = result_holder["error"]
        if tool.audit_post_call:
            _audit(role, tool_name, phase="error", detail=msg)
        return _err(tool_name, msg, elapsed_ms=elapsed_ms)

    output = result_holder.get("value")
    if tool.audit_post_call:
        # Don't dump the full output into audit — just a size hint.
        size_hint = (
            f"{len(output)} chars" if isinstance(output, str)
            else f"type={type(output).__name__}"
        )
        _audit(role, tool_name, phase="ok", detail=size_hint)
    return _ok(tool_name, output, elapsed_ms=elapsed_ms)
