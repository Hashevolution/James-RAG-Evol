"""Workspace root resolver — ``JAMES_WORKSPACE=`` env (Track C PR-C6).

Multi-instance hosting groundwork: one JAMES process per workspace,
with the same code base serving different data roots. Read at
startup; consulted by ``config.py`` for the four data directories
(``RAW_DIR`` / ``WIKI_DIR`` / ``UPLOAD_DIR`` / ``CHROMA_DIR``) — see
PR-C6.b (#421, 2026-05-23) for the consumption side.

Layering: this module defines the env var, the resolver, and the
failure modes; ``config.py`` consumes the resolved root once at
module-import time and the existing path constants stay as plain
``os.path.join`` strings so the ~100 import sites across the codebase
are unchanged. With ``JAMES_WORKSPACE`` unset the resolver returns
the project root, byte-identical to the pre-v0.3 codepath.

Env semantics
-------------
- ``JAMES_WORKSPACE`` unset → :data:`BASE_DIR` (current behavior).
- ``JAMES_WORKSPACE=`` (empty) → :data:`BASE_DIR` (same as unset —
  operator's empty value is interpreted as "use default", not as
  "explicitly empty". This is *different* from ``JAMES_PACKS=``,
  which treats empty as a refused-start signal: packs is what JAMES
  *runs as*, workspace is just where it stores).
- ``JAMES_WORKSPACE=/abs/path`` → absolute path used as-is.
- ``JAMES_WORKSPACE=relative/path`` → joined against :data:`BASE_DIR`
  and resolved.

Failure modes (all raise :class:`PluginLoadError` at startup):

- Resolved path is not a directory → operator must create it first.
- Resolved path is unreadable / unstatable.

The resolver does NOT create the directory automatically. Operator
intent matters here — silent creation of an unintended path (typo
in env value) is worse than a loud refusal.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from core.plugins.errors import PluginLoadError

# Project root, derived from this file's location. Equivalent to
# ``config.BASE_DIR`` but imported locally to keep ``core/plugins/``
# free of upward coupling to the project root.
_THIS_FILE = Path(__file__).resolve()
BASE_DIR: Path = _THIS_FILE.parent.parent.parent


def get_workspace_root(
    env: Optional[dict] = None,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    """Resolve the workspace root from ``JAMES_WORKSPACE``.

    Arguments:
      env:       env-var dict; defaults to ``os.environ``. Tests pass a
                 literal dict to drive arbitrary inputs without
                 depending on global state.
      base_dir:  the project root used as the relative-path anchor and
                 the default when env is unset. Defaults to
                 :data:`BASE_DIR`. Tests pass a temp directory.

    Returns:
      Absolute :class:`pathlib.Path` to the workspace root.

    Raises:
      :class:`PluginLoadError` — env value is set to a non-empty
      string that doesn't resolve to an existing directory.
    """
    env_map = os.environ if env is None else env
    anchor = base_dir if base_dir is not None else BASE_DIR

    raw = env_map.get("JAMES_WORKSPACE")
    if raw is None or raw.strip() == "":
        # Unset OR explicit empty → default to BASE_DIR. This
        # preserves byte-identical behavior with the pre-PR-C6 codepath.
        return anchor

    workspace_str = raw.strip()
    candidate = Path(workspace_str)
    if not candidate.is_absolute():
        # Resolve against the project root, not the process CWD —
        # CWD can drift (e.g., a systemd service started from /).
        candidate = anchor / candidate
    resolved = candidate.resolve()

    if not resolved.exists():
        raise PluginLoadError(
            f"JAMES_WORKSPACE={workspace_str!r} resolves to "
            f"{resolved} which does not exist. Create the directory "
            f"before starting JAMES; the resolver does not create it "
            f"automatically (silent creation of an unintended path "
            f"would be worse than a loud refusal)."
        )
    if not resolved.is_dir():
        raise PluginLoadError(
            f"JAMES_WORKSPACE={workspace_str!r} resolves to "
            f"{resolved} which exists but is not a directory."
        )

    return resolved


def workspace_path(*parts: str, env: Optional[dict] = None) -> Path:
    """Resolve a path under the workspace root.

    Convenience wrapper for the eventual path-replacement code
    (``wiki/`` / ``uploads/`` / ``reports/`` / ``chroma_db/``). Tests
    pass an env dict; production code calls without arguments.

    Example::

        workspace_path("wiki", "entity", "prod")
        # → <workspace_root>/wiki/entity/prod
    """
    root = get_workspace_root(env=env)
    return root.joinpath(*parts)


# ─── v0.6 Phase 3 P3.2 — per-tenant workspace isolation ─────────────


import re

# Tenant ids must be path-safe AND match the same identifier shape
# the SDK scaffolder enforces for pack ids (see
# `james/pack/scaffold.py::_PACK_ID_RE`). This rules out path
# separators, dots, NUL bytes, shell metachars, and case-folding
# ambiguity — all of which are well-known sources of path-traversal
# CVEs in multi-tenant systems that derive on-disk paths from
# user-controllable identifiers.
_TENANT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")

JAMES_WORKSPACE_PER_TENANT_ENV: str = "JAMES_WORKSPACE_PER_TENANT"


def _tenant_per_tenant_enabled(env_map) -> bool:
    raw = (env_map.get(JAMES_WORKSPACE_PER_TENANT_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on", "enabled")


def _validate_tenant_id_for_path(tenant_id: str) -> str:
    """Return ``tenant_id`` iff it matches the path-safe identifier
    pattern; raise :class:`PluginLoadError` otherwise.

    The validation is **strict by design**: a tenant id that surfaces
    in an on-disk path MUST NOT contain ``.`` or ``/`` or backslash
    or NUL or whitespace, MUST start with a lowercase letter, and
    MUST only use ``[a-z0-9_-]``. Loose validation invites
    ``../`` traversal + shell-metachar injection in operator tooling
    that ``ls`` over workspace paths.
    """
    if not isinstance(tenant_id, str) or not tenant_id:
        raise PluginLoadError(
            "per-tenant workspace requires a non-empty tenant_id"
        )
    if not _TENANT_ID_RE.match(tenant_id):
        raise PluginLoadError(
            f"tenant_id {tenant_id!r} is not path-safe; "
            f"must match {_TENANT_ID_RE.pattern}"
        )
    return tenant_id


def get_workspace_root_for_tenant(
    tenant_id: Optional[str] = None,
    *,
    env: Optional[dict] = None,
    base_dir: Optional[Path] = None,
) -> Path:
    """Resolve the workspace root for a specific tenant.

    When ``JAMES_WORKSPACE_PER_TENANT`` is set (truthy) AND a
    non-empty ``tenant_id`` is provided OR resolvable from the
    active per-request tenant scope, returns
    ``<workspace_root>/<tenant_id>/`` — a sibling directory under
    the base workspace.

    When the flag is unset OR no tenant_id resolves: returns the
    base ``get_workspace_root()`` (byte-identical to pre-Phase-3
    behaviour).

    Args:
        tenant_id: explicit tenant id. If ``None``, the function
            asks :func:`core.lifecycle.tenant.current_tenant_id` for
            the active per-request override (set by
            :class:`core.security.tenant_request.TenantHeaderMiddleware`)
            — so callers in the request path don't have to plumb
            tenant_id through every function.
        env: optional env-var dict override; defaults to
            ``os.environ``.
        base_dir: optional project-root anchor; defaults to
            :data:`BASE_DIR`.

    Returns:
        Absolute :class:`pathlib.Path` to the (per-tenant or base)
        workspace root.

    Raises:
        :class:`PluginLoadError` — when per-tenant mode is enabled
        AND tenant_id is non-empty but does NOT pass the path-safe
        validation pattern (``^[a-z][a-z0-9_-]*$``).

    The directory is created if it does not exist (matching the
    operator expectation that turning the flag on is sufficient to
    start serving the tenant — they should not need a separate
    ``mkdir`` step). Parent directory (the base workspace) MUST
    exist; the base resolver raises if not.
    """
    env_map = os.environ if env is None else env

    if not _tenant_per_tenant_enabled(env_map):
        # Flag off → byte-identical to pre-Phase-3 behaviour. The
        # tenant_id argument is ignored.
        return get_workspace_root(env=env, base_dir=base_dir)

    # Per-tenant mode. Resolve the tenant id from the explicit arg
    # OR the per-request scope.
    effective = tenant_id
    if effective is None or effective == "":
        try:
            from core.lifecycle.tenant import current_tenant_id
            effective = current_tenant_id()
        except Exception:
            effective = None
    if not effective:
        # Per-tenant mode enabled but no tenant resolved → fall
        # back to the base root. This is the safe default for
        # housekeeping paths that legitimately don't belong to any
        # tenant; the audit-emit enforce gate
        # (`JAMES_REQUIRE_TENANT_ID=1`) is the layer that catches
        # unscoped tenant emits, not this resolver.
        return get_workspace_root(env=env, base_dir=base_dir)

    validated = _validate_tenant_id_for_path(effective)
    base_root = get_workspace_root(env=env, base_dir=base_dir)
    per_tenant = base_root / validated
    per_tenant.mkdir(parents=True, exist_ok=True)
    return per_tenant


__all__ = [
    "BASE_DIR",
    "JAMES_WORKSPACE_PER_TENANT_ENV",
    "get_workspace_root",
    "get_workspace_root_for_tenant",
    "workspace_path",
]
