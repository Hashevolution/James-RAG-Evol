"""Workspace info endpoint (v0.6.1 — dogfooding ergonomics).

A tiny GET endpoint that surfaces the **active workspace** so the
frontend can show "📁 <workspace>" in the header — operator dogfooding
context: one JAMES server per process, one workspace per process, but
the operator may run multiple workspaces (default / dogfood-<date> /
research-cycle) on the same machine and wants to know *which one am I
looking at right now* without checking the terminal env.

Authorization mirrors `/templates/mine/list`: a logged-in JWT subject
is enough; no admin gate. Every user that can log in needs to see the
badge.

Contract:

  GET /workspace/info → 200 OK
    {
      "workspace_name": "dogfood-2026-06"   # display name (env raw)
                        | "default",         # when JAMES_WORKSPACE unset
      "workspace_path": "/abs/path/to/ws",   # resolved by core/plugins/workspace.py
      "is_default": True | False,            # JAMES_WORKSPACE unset
      "per_tenant_enabled": True | False,    # JAMES_WORKSPACE_PER_TENANT
      "entity_count": 313                    # best-effort, 0 on read error
    }

The handler is intentionally cheap — one env read + one
get_workspace_root() call + one (already in-memory) entity-index size.
The endpoint must NOT block on disk or LLM I/O; if the entity index is
not yet loaded it returns 0 rather than initialising it.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from routes._helpers import _bearer_username, get_role_from_request

router = APIRouter()


def _entity_count_best_effort() -> int:
    """Return the loaded entity index size, or 0 on any failure."""
    try:
        # Lazy-import server_llmwiki to avoid a circular import on
        # module load (server registers this router after import).
        import server_llmwiki  # noqa: F401
        rag = getattr(server_llmwiki, "rag_engine", None)
        if rag is None:
            return 0
        idx = getattr(rag.wiki_generator, "entity_id_index", None)
        return len(idx) if idx is not None else 0
    except Exception:
        return 0


@router.get("/workspace/info", summary="현재 워크스페이스 정보")
async def workspace_info_route(
    request: Request,
    role: str = Depends(get_role_from_request),
) -> Dict[str, Any]:
    """Return display info for the active workspace.

    Requires a logged-in JWT subject; otherwise 401. No admin gate —
    every operator/user that can log in needs the badge."""
    username = _bearer_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    from core.plugins.workspace import (
        JAMES_WORKSPACE_PER_TENANT_ENV,
        get_workspace_root,
    )

    raw = (os.environ.get("JAMES_WORKSPACE") or "").strip()
    is_default = not raw
    # Display name = the env value when set (most useful — operators
    # know what they typed), else "default" so the badge isn't empty.
    if is_default:
        display = "default"
    else:
        # If the operator passed an absolute or relative path, show
        # the leaf — header is short on space.
        display = os.path.basename(raw.rstrip("/\\")) or raw

    try:
        ws_path = str(get_workspace_root())
    except Exception:
        ws_path = ""

    per_tenant_raw = (os.environ.get(JAMES_WORKSPACE_PER_TENANT_ENV) or "").strip().lower()
    per_tenant = per_tenant_raw in ("1", "true", "yes", "on", "enabled")

    return {
        "workspace_name": display,
        "workspace_path": ws_path,
        "is_default": is_default,
        "per_tenant_enabled": per_tenant,
        "entity_count": _entity_count_best_effort(),
    }
