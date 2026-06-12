"""v0.5 G1.a — tenant identifier primitive for audit-log rows.

Per `docs/reviews/v0.5-b2-multi-tenant-isolation.md` §3.2. Mother-
platform: the contract surface only. Default-off → byte-identical
pre-G1.a behaviour when no env var is set and no `with_tenant_id`
override is active.

## What this module ships

  * `JAMES_TENANT_ID_ENV` — name of the env var (constant, for tests).
  * `JAMES_REQUIRE_TENANT_ID_ENV` — name of the enforcement env var.
  * `current_tenant_id()` → ``Optional[str]`` — resolves the active
    tenant from (1) thread-local override stack, (2) the
    `JAMES_TENANT_ID` env var. ``None`` if neither.
  * `with_tenant_id(tenant_id)` — context-manager that pushes a
    thread-local override for the duration of the `with` block.
    Used by admin tooling that writes audit rows on behalf of a
    specific tenant from a process without a single ambient
    tenant.
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
- **Not thread-safe across asyncio tasks.** The override stack
  uses `threading.local`, which carries per-thread but does NOT
  carry per-asyncio-task. Admin tooling using `with_tenant_id`
  inside an `async def` should either (a) use it at thread-pool
  call sites only, or (b) wait for the asyncio-aware variant
  scheduled in G1.b.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Final, Iterator, Optional


JAMES_TENANT_ID_ENV:         Final[str] = "JAMES_TENANT_ID"
JAMES_REQUIRE_TENANT_ID_ENV: Final[str] = "JAMES_REQUIRE_TENANT_ID"


# Thread-local override stack. `with_tenant_id` pushes; on exit,
# pops. The stack supports nested overrides (the innermost wins).
_local = threading.local()


def _stack() -> list:
    """Lazily-initialise + return the per-thread override stack."""
    stack = getattr(_local, "stack", None)
    if stack is None:
        stack = []
        _local.stack = stack
    return stack


def current_tenant_id() -> Optional[str]:
    """Resolve the active tenant id.

    Resolution order (first match wins):
      1. Innermost `with_tenant_id(...)` override on the current
         thread, if any.
      2. `JAMES_TENANT_ID` env var, if set + non-empty.
      3. ``None``.

    Returns the empty string as ``None`` so callers don't accidentally
    stamp an empty-string tenant_id (which is a different audit-row
    state from "no tenant scope known").
    """
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
    "is_tenant_isolation_enforced",
)
