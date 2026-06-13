"""v0.5 G1.a — tenant identifier primitive for audit-log rows.

Per `docs/reviews/v0.5-b2-multi-tenant-isolation.md` §3.2. Mother-
platform: the contract surface only. Default-off → byte-identical
pre-G1.a behaviour when no env var is set and no `with_tenant_id`
override is active.

## What this module ships

  * `JAMES_TENANT_ID_ENV` — name of the env var (constant, for tests).
  * `JAMES_REQUIRE_TENANT_ID_ENV` — name of the enforcement env var.
  * `current_tenant_id()` → ``Optional[str]`` — resolves the active
    tenant from (1) the current asyncio task's contextvars-backed
    override stack, (2) the thread-local override stack, (3) the
    `JAMES_TENANT_ID` env var. ``None`` if none resolve.
  * `with_tenant_id(tenant_id)` — sync context-manager that pushes a
    thread-local override for the duration of the `with` block.
    Used by admin tooling that writes audit rows on behalf of a
    specific tenant from a process without a single ambient
    tenant.
  * `with_tenant_id_async(tenant_id)` — async context-manager (v0.6
    G2.c) that pushes a contextvars-backed override propagating
    across `await` points + into child tasks created inside the
    block. Use this from FastAPI / asyncio handlers.
  * `is_tenant_isolation_enforced()` → ``bool`` — true iff
    `JAMES_REQUIRE_TENANT_ID` is set to a recognised truthy value.
    The audit-emitter consults this to decide whether emit
    requires a resolved tenant_id (enforce mode) or treats absence
    as "single-tenant mode" (default).

## Integration

The corresponding emit-side wire-in lives in
`core/lifecycle/replay_audit.py::emit_lifecycle_event` (extended
in the same PR). When `tenant_id` is resolvable (override OR env),
the value is stamped into the row's `event_payload` JSON under
the key `tenant_id` — no schema migration. Pattern mirrors the G4
retention_class field (landed PR #848).

## What this module is NOT

- **Not a routing token.** The downstream replay-side filter
  (G1.b) reads the stamped field to scope queries; that lands
  in a separate PR. This module only writes.
- **Not an RBAC layer.** Tenant_id is an audit-trail correlation
  primitive. Cross-tenant query prevention is handled at the
  HTTP layer (reverse proxy + per-tenant routes), not here.
- **Not thread-safe across asyncio tasks (sync API only).** The
  synchronous `with_tenant_id` override stack uses
  `threading.local`, which carries per-thread but does NOT
  carry per-asyncio-task. Async callers should use
  `with_tenant_id_async` (v0.6 G2.c) — a contextvars-backed
  variant that DOES propagate across `await` points + into
  child tasks created inside its `async with` block.
"""
from __future__ import annotations

import contextvars
import os
import threading
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Final, Iterator, List, Optional


JAMES_TENANT_ID_ENV:         Final[str] = "JAMES_TENANT_ID"
JAMES_REQUIRE_TENANT_ID_ENV: Final[str] = "JAMES_REQUIRE_TENANT_ID"


# Thread-local override stack. `with_tenant_id` pushes; on exit,
# pops. The stack supports nested overrides (the innermost wins).
_local = threading.local()

# v0.6 G2.c — contextvars-backed override stack for async callers.
# `with_tenant_id_async` populates this; `current_tenant_id` checks
# it BEFORE the thread-local stack so an async caller's per-task
# override wins over an ambient thread-level override.
#
# Why a separate stack: `contextvars.ContextVar` propagates across
# `await` points but not across `threading.Thread.start` boundaries
# — so mixing one stack risks losing the ambient thread tenant when
# an async caller spawns a sync worker. Two stacks keep the
# semantics crisp: thread-local for sync code, contextvars for
# async code, both readable from `current_tenant_id`.
_async_stack: contextvars.ContextVar[Optional[List[Optional[str]]]] = (
    contextvars.ContextVar("james_tenant_async_stack", default=None)
)


def _stack() -> list:
    """Lazily-initialise + return the per-thread override stack."""
    stack = getattr(_local, "stack", None)
    if stack is None:
        stack = []
        _local.stack = stack
    return stack


def _async_stack_get() -> Optional[List[Optional[str]]]:
    """Read the current task's async override stack, or None if no
    `with_tenant_id_async` is active on this task."""
    return _async_stack.get()


def current_tenant_id() -> Optional[str]:
    """Resolve the active tenant id.

    Resolution order (first match wins):
      1. Innermost `with_tenant_id_async(...)` override on the
         current asyncio task (v0.6 G2.c), if any.
      2. Innermost `with_tenant_id(...)` override on the current
         thread, if any.
      3. `JAMES_TENANT_ID` env var, if set + non-empty.
      4. ``None``.

    Returns the empty string as ``None`` so callers don't accidentally
    stamp an empty-string tenant_id (which is a different audit-row
    state from "no tenant scope known").

    Async/sync interaction: the async stack is per-task; the
    thread-local stack is per-thread. A `with_tenant_id_async` block
    that internally calls a sync helper (e.g. via
    `run_in_executor`) carries its tenant scope across the await
    boundary, then drops back to the thread-local stack when the
    sync worker runs in a different thread.
    """
    async_stack = _async_stack_get()
    if async_stack:
        return async_stack[-1]
    stack = _stack()
    if stack:
        return stack[-1]
    raw = os.environ.get(JAMES_TENANT_ID_ENV)
    if raw and raw.strip():
        return raw.strip()
    return None


@contextmanager
def with_tenant_id(tenant_id: Optional[str]) -> Iterator[None]:
    """Override the active tenant id for the `with` block.

    Pushes ``tenant_id`` onto the thread-local override stack on
    entry; pops on exit (even if the block raised).

    Pass ``None`` to explicitly NULL the override for the block —
    this is the "admin tooling running unscoped over the entire
    audit-log" case. Calling ``current_tenant_id()`` inside such a
    block returns ``None`` even if ``JAMES_TENANT_ID`` is set.

    Nesting is supported — innermost wins, outer overrides restore
    naturally on exit.
    """
    stack = _stack()
    stack.append(tenant_id)
    try:
        yield
    finally:
        # Defensive pop — never trust the stack length if the
        # caller did something exotic (e.g., manually mutated
        # the local). Pop the last element only if it matches.
        if stack and stack[-1] is tenant_id:
            stack.pop()


@asynccontextmanager
async def with_tenant_id_async(tenant_id: Optional[str]) -> AsyncIterator[None]:
    """Async-task-aware override (v0.6 G2.c).

    Pushes ``tenant_id`` onto the current task's contextvars-backed
    override stack on entry; pops on exit. Designed for FastAPI /
    asyncio handlers that need the tenant scope to survive ``await``
    points within the same task — the threading.local-backed
    :func:`with_tenant_id` does not propagate across awaits in a
    single thread (see the v0.5 G1.a docstring note).

    Pattern::

        async def handler(req):
            tenant_id = req.state.tenant_id
            async with with_tenant_id_async(tenant_id):
                # Every audit emit inside this block stamps tenant_id,
                # even after `await` points and across `asyncio.gather`
                # child tasks (provided they were scheduled inside
                # the block — contextvars copy on task creation).
                return await do_work(req)

    `asyncio.gather` semantics: subtasks created inside the block
    inherit the parent task's contextvars at creation time, so they
    see the override. Subtasks created OUTSIDE the block do not.

    Nesting is supported — innermost wins, outer overrides restore
    naturally on exit, mirroring the sync :func:`with_tenant_id`.
    """
    stack = list(_async_stack_get() or [])
    stack.append(tenant_id)
    token = _async_stack.set(stack)
    try:
        yield
    finally:
        # Restore the previous stack snapshot. We don't pop in-place
        # because the ContextVar's value is a list reference; another
        # task created during the block may still hold a reference to
        # the longer list. Setting the token back to the prior value
        # restores the correct visible state for THIS task; siblings
        # keep their inherited reference unchanged (matches the
        # `contextvars.Context.copy` semantic).
        _async_stack.reset(token)


def is_tenant_isolation_enforced() -> bool:
    """True iff `JAMES_REQUIRE_TENANT_ID` is set to a truthy value.

    Recognised truthy values: ``1``, ``true``, ``yes``, ``on``,
    ``enabled``. Everything else (empty / unset / ``0`` / ``false``
    / arbitrary other string) is falsy.

    The audit-emitter calls this to decide whether the absence of
    a resolvable tenant_id should cause emit to return ``False``
    (enforce mode) or proceed unstamped (single-tenant mode, the
    v0.5 default).
    """
    raw = (os.environ.get(JAMES_REQUIRE_TENANT_ID_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on", "enabled")


__all__ = (
    "JAMES_TENANT_ID_ENV",
    "JAMES_REQUIRE_TENANT_ID_ENV",
    "current_tenant_id",
    "with_tenant_id",
    "with_tenant_id_async",
    "is_tenant_isolation_enforced",
)
