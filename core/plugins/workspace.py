"""Workspace root resolver — ``JAMES_WORKSPACE=`` env (Track C PR-C6).

Multi-instance hosting groundwork: one JAMES process per workspace,
with the same code base serving different data roots. Read at
startup; consulted by future path-resolution code (``wiki/`` /
``uploads/`` / ``reports/`` / ``chroma_db/``) once the path-replacement
follow-up PR lands.

**v0.3 scope is intentionally minimal**: this module defines the env
var, the resolver, and the failure modes. The existing path constants
in ``config.py`` are NOT yet rewritten to consume the resolver — that
is a separate PR (PR-C6.b) because it's a large structural edit that
must verify each call site of ``BASE_DIR`` / ``WIKI_DIR`` /
``UPLOAD_DIR`` / ``CHROMA_DIR`` lands cleanly.

Per ``docs/design/v0.3-plugin-api.md`` §"`JAMES_WORKSPACE=` env (§C-6)
— deferred to a separate PR":

> Plugin loader can ignore the env in v0.3 — the default is "the
> current directory", which is byte-identical to today.

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


__all__ = [
    "BASE_DIR",
    "get_workspace_root",
    "workspace_path",
]
