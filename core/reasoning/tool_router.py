"""Tool Router — Cognitive Layer Phase 2 PR-8.

ARCHITECTURE.md §5.7.1: "Tool Router — select between chat / web
search / wiki edit / graph editor / memory write". The MVP is
infrastructure-only (wiring 0) — the registry + dispatch primitive
exists for Phase 2 PR-7 Planner / future reflection-driven tool calls
to consume.

Two trust classes:

  - **Read tools** (`is_write=False`) — web_search, wiki_read, etc.
    dispatch_tool() executes the handler directly. Result lands in
    the trace but does NOT touch the wiki.
  - **Write tools** (`is_write=True`) — wiki_edit, graph_node_edit,
    save_to_wiki, etc. dispatch_tool() **wraps the call as a Change
    Request** via core.change_request.create_cr per CLAUDE.md rule #3
    (self-modifying outcomes need human approval). The handler is
    NOT executed at dispatch time; the CR sits in 'open' status
    waiting for admin approval.

Trace contract:

  Every dispatch emits one TraceStep with stage="tool":
    applied_rule = "reasoning.tool.<tool_name>"
    backend_id   = "tool_router"
    output_summary brief — full output lives in the tool's own audit
    row (web_searcher's mirror_to_audit_db, wiki_editor's CR row, etc.)

This is the L0 contract — every cognitive-layer step writes one row
to ``audit_log``. replay_trace.py picks them up alongside synth /
reflect / verify rows.

Built-in tools registered at module import:

  - ``web_search``  — read-only; wraps tools/web/web_searcher.search_web
                      (admin role required per existing query.web_search
                      gate; this dispatcher does not duplicate the gate
                      because the underlying tool already enforces it
                      at the role level).

L0 backends were "wiring 0" infrastructure that L1 wired into 12
call sites. PR-8's Tool Router is the analogous primitive for tool
calls — the wiring step is **Phase 2 PR-7 (Planner)** or a future
reflection-driven tool-call PR.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from core.reasoning.trace_schema import (
    TraceStep,
    compute_inputs_hash,
    emit_trace_step,
    truncate_summary,
)


# ─── data shapes ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Tool:
    """One named callable the cognitive layer may dispatch.

    Fields:
      name:        canonical id, e.g. "web_search", "wiki_edit".
      description: short human-facing label (Korean OK).
      is_write:    True ⇒ dispatch routes through Change Request
                   (handler NOT executed; admin must approve first).
                   False ⇒ handler runs immediately, output returned.
      cr_target_type: when is_write=True, this is passed to
                      change_request.create_cr as ``target_type``.
                      Must be one of VALID_TARGET_TYPES.
      handler:     callable(args: dict, *, user_role: str) -> Any.
                   Free function; must NOT raise on user input —
                   convert errors into a string-y return value.
    """
    name:           str
    description:    str
    is_write:       bool
    handler:        Callable[..., Any]
    cr_target_type: str = ""


@dataclass
class ToolResult:
    """Returned to the dispatch caller. ``ok`` distinguishes
    successful execution / successful CR creation from the various
    failure modes (unknown tool, handler raise, CR create raise).
    """
    ok:        bool
    tool_name: str
    output:    str = ""
    error:     str = ""
    cr_id:     Optional[str] = None
    extras:    Dict[str, Any] = field(default_factory=dict)


# ─── registry ──────────────────────────────────────────────────────

_REGISTRY: Dict[str, Tool] = {}
_REGISTRY_LOCK = threading.Lock()


def register_tool(tool: Tool) -> None:
    """Add a tool to the registry. Idempotent re-registration with
    the same Tool instance is allowed (re-imports under test runners);
    a different instance under the same name raises so we don't
    silently overwrite an in-flight tool.
    """
    if not isinstance(tool, Tool):
        raise TypeError("register_tool expects a Tool instance")
    if not tool.name:
        raise ValueError("tool.name must be non-empty")
    with _REGISTRY_LOCK:
        existing = _REGISTRY.get(tool.name)
        if existing is not None and existing is not tool:
            raise ValueError(
                f"tool {tool.name!r} already registered with a "
                f"different instance"
            )
        _REGISTRY[tool.name] = tool


def get_tool(name: str) -> Tool:
    """Look up a tool by name. Unknown name → KeyError; the
    opt-in pattern matches the backend registry (L0)."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"no tool registered for {name!r}; "
            f"known: {sorted(_REGISTRY)}"
        ) from None


def list_tools() -> Dict[str, Tool]:
    """Shallow copy of the registry — tests inspect this; production
    code goes through ``get_tool``.
    """
    return dict(_REGISTRY)


def _clear_for_tests() -> None:
    """Test helper. Production code never calls this."""
    with _REGISTRY_LOCK:
        _REGISTRY.clear()


# ─── dispatch ──────────────────────────────────────────────────────


def dispatch_tool(
    name: str,
    args: Optional[Dict[str, Any]] = None,
    *,
    user_role: str = "system",
    proposer: str = "",
) -> ToolResult:
    """Execute (read) or propose (write) the named tool.

    Always returns a ToolResult. Never raises.

    ``proposer`` is only consulted for write tools; defaults to
    ``user_role`` if empty. The CR system audits every state change
    with proposer+approver, so the caller should pass an authenticated
    username here rather than relying on the role string.
    """
    args = args or {}
    t0 = time.time()

    # Lookup
    try:
        tool = get_tool(name)
    except KeyError as e:
        result = ToolResult(
            ok=False, tool_name=name,
            error=f"unknown tool: {name}",
        )
        _emit_trace(
            tool_name=name,
            applied_rule=f"reasoning.tool.{name}",
            output_summary=str(e)[:200],
            latency_ms=int((time.time() - t0) * 1000),
            error="unknown tool",
            user_role=user_role,
        )
        return result

    # Write path — propose a Change Request, do NOT execute.
    if tool.is_write:
        return _dispatch_write(tool, args, user_role, proposer, t0)

    # Read path — execute directly.
    return _dispatch_read(tool, args, user_role, t0)


def _dispatch_read(
    tool: Tool,
    args: Dict[str, Any],
    user_role: str,
    t0: float,
) -> ToolResult:
    try:
        output = tool.handler(args, user_role=user_role)
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:200]}"
        _emit_trace(
            tool_name=tool.name,
            applied_rule=f"reasoning.tool.{tool.name}",
            output_summary="",
            latency_ms=int((time.time() - t0) * 1000),
            error=err,
            user_role=user_role,
        )
        return ToolResult(ok=False, tool_name=tool.name, error=err)

    output_str = output if isinstance(output, str) else (
        str(output) if output is not None else ""
    )
    _emit_trace(
        tool_name=tool.name,
        applied_rule=f"reasoning.tool.{tool.name}",
        output_summary=truncate_summary(output_str),
        latency_ms=int((time.time() - t0) * 1000),
        error="",
        user_role=user_role,
    )
    return ToolResult(ok=True, tool_name=tool.name, output=output_str)


def _dispatch_write(
    tool: Tool,
    args: Dict[str, Any],
    user_role: str,
    proposer: str,
    t0: float,
) -> ToolResult:
    """Wrap the write as a Change Request (CLAUDE.md rule #3 —
    self-modifying outcomes need human approval). The tool's handler
    is NOT called at dispatch time; admin runs it via the CR
    approve flow.
    """
    if not tool.cr_target_type:
        err = (
            f"tool {tool.name!r} is_write=True but cr_target_type is "
            f"empty — cannot propose Change Request"
        )
        _emit_trace(
            tool_name=tool.name,
            applied_rule=f"reasoning.tool.{tool.name}",
            output_summary="",
            latency_ms=int((time.time() - t0) * 1000),
            error=err,
            user_role=user_role,
        )
        return ToolResult(ok=False, tool_name=tool.name, error=err)

    proposer = proposer or user_role or "system"
    try:
        from core.change_request import create_cr, compute_base_hash
        # Caller may pass an explicit base_hash; otherwise derive
        # from the proposed_diff so concurrent CRs against the same
        # target stay distinguishable.
        base_hash = args.get("base_hash") or compute_base_hash(
            str(args.get("proposed_diff", "")).encode("utf-8")
        )
        cr = create_cr(
            target_type=tool.cr_target_type,
            target_id=args.get("target_id", ""),
            title=args.get("title") or f"[tool] {tool.name}",
            description=args.get("description", ""),
            proposed_diff=args.get("proposed_diff", {}),
            base_hash=base_hash,
            proposer=proposer,
            labels=args.get("labels", ()),
            role=user_role,
        )
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:200]}"
        _emit_trace(
            tool_name=tool.name,
            applied_rule=f"reasoning.tool.{tool.name}",
            output_summary="",
            latency_ms=int((time.time() - t0) * 1000),
            error=err,
            user_role=user_role,
        )
        return ToolResult(ok=False, tool_name=tool.name, error=err)

    _emit_trace(
        tool_name=tool.name,
        applied_rule=f"reasoning.tool.{tool.name}",
        output_summary=f"CR {cr.cr_id} proposed",
        latency_ms=int((time.time() - t0) * 1000),
        error="",
        user_role=user_role,
        extras={"cr_id": cr.cr_id, "cr_target_type": tool.cr_target_type},
    )
    return ToolResult(
        ok=True, tool_name=tool.name,
        output=f"CR {cr.cr_id} created",
        cr_id=cr.cr_id,
        extras={"cr_target_type": tool.cr_target_type},
    )


# ─── trace emit ────────────────────────────────────────────────────


def _emit_trace(
    *,
    tool_name: str,
    applied_rule: str,
    output_summary: str,
    latency_ms: int,
    error: str,
    user_role: str,
    extras: Optional[Dict[str, Any]] = None,
) -> None:
    emit_extras: Dict[str, Any] = dict(extras or {})
    emit_extras["tool"] = tool_name
    try:
        from core.observability import get_trace_id
        tid = get_trace_id()
        if tid:
            emit_extras["trace_id"] = tid
    except Exception:
        pass

    try:
        emit_trace_step(
            TraceStep(
                stage="tool",
                backend_id="tool_router",
                parent_step_id="",
                inputs_hash=compute_inputs_hash(tool_name),
                output_summary=output_summary,
                applied_rule=applied_rule,
                latency_ms=latency_ms,
                error=error,
            ),
            user_role=user_role,
            extras=emit_extras,
        )
    except Exception:
        # Trace emit is best-effort — never block tool dispatch on
        # audit_log unavailability.
        pass


# ─── built-in tools ────────────────────────────────────────────────
#
# Module-level auto-registration matches the backend registry pattern
# (core/reasoning/backends/__init__.py). Built-ins are kept tight —
# new tools register from their own modules rather than ballooning
# this file.

def _autoregister_builtins() -> None:
    # web_search: thin wrapper around tools.web.web_searcher so the
    # cognitive layer can request a search without each caller
    # learning the underlying module's call shape.
    def _web_search(args: Dict[str, Any], *, user_role: str) -> str:
        try:
            from tools.web.web_searcher import search_web, format_search_results
        except ImportError:
            return "web_search unavailable: web_searcher module not importable"
        query = (args.get("query") or "").strip()
        if not query:
            return "web_search error: query argument required"
        max_results = int(args.get("max_results", 4))
        results = search_web(query, max_results=max_results)
        if not results:
            return "no web results"
        return format_search_results(results)

    register_tool(Tool(
        name="web_search",
        description="외부 웹 검색 (Tavily / DDG fallback)",
        is_write=False,
        handler=_web_search,
    ))


_autoregister_builtins()


__all__ = [
    "Tool",
    "ToolResult",
    "register_tool",
    "get_tool",
    "list_tools",
    "dispatch_tool",
]
