"""Agent-tool path permission endpoints (v0.6.1, Phase B).

Operator-facing admin surface for the user-registered paths that
`tools/code/sandbox.py::validate_path` accepts. See
`docs/design/v0.6-agent-tools-user-paths.md` for the trust contract.

Endpoints (admin-only, audit-logged):

  * `GET  /admin/agent/allowed-paths` → list registered paths + env
  * `POST /admin/agent/allowed-paths` `{"path": "/abs/path"}` → register

Paths are session-scoped (in-memory). Restart of the JAMES process
re-reads `JAMES_AGENT_ALLOWED_PATHS` env; the design memo §3 explains
why no runtime-remove endpoint ships in Phase B.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routes._helpers import (
    _bearer_username,
    _require_admin,
    _write_audit,
    get_role_from_request,
)

router = APIRouter()


class RegisterPathRequest(BaseModel):
    api_key: str
    path: str


@router.get(
    "/admin/agent/allowed-paths",
    summary="에이전트 도구 허용 경로 조회 [v0.6.1 Phase B]",
)
async def list_allowed_paths(
    api_key: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Return the current list of user-registered absolute paths the
    agent tools may read/write, plus the env that seeded them."""
    _require_admin(api_key, role)

    from tools.code.sandbox import (
        JAMES_AGENT_ALLOWED_PATHS_ENV,
        get_user_registered_paths,
    )

    paths = get_user_registered_paths()
    env_value = os.environ.get(JAMES_AGENT_ALLOWED_PATHS_ENV, "")

    return {
        "registered_paths": paths,
        "count": len(paths),
        "env_name": JAMES_AGENT_ALLOWED_PATHS_ENV,
        "env_value": env_value,
    }


@router.post(
    "/admin/agent/allowed-paths",
    summary="에이전트 도구 허용 경로 등록 [v0.6.1 Phase B]",
)
async def register_allowed_path(
    body: RegisterPathRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Register an absolute path as agent-tool-allowed for this server
    process. Critical-system roots (`/etc/`, `C:\\Windows\\`, …) are
    rejected at the sandbox layer; admin cannot override that block."""
    _require_admin(body.api_key, role)
    username = _bearer_username(request) or "admin"

    from tools.code.sandbox import register_user_path

    ok, msg = register_user_path(body.path)
    _write_audit(
        role,
        "/admin/agent/allowed-paths",
        query=f"register:{body.path}",
        answer=f"ok={ok}; {msg}",
    )
    if not ok:
        # Surface the specific reason so the admin can correct it
        # (path doesn't exist / under critical root / etc.).
        raise HTTPException(status_code=400, detail=msg)

    return {
        "registered": True,
        "path": body.path,
        "message": msg,
        "by": username,
    }


class UnregisterPathRequest(BaseModel):
    api_key: str
    path: str


@router.post(
    "/admin/agent/allowed-paths/remove",
    summary="에이전트 도구 허용 경로 제거 (세션 스코프) [v0.6.1 Phase D-1]",
)
async def unregister_allowed_path(
    body: UnregisterPathRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Session-scoped remove from the in-memory registry.

    **Not a permanent revoke.** Restarting the JAMES process re-reads
    `JAMES_AGENT_ALLOWED_PATHS` env, so paths persisted there will
    re-appear. To revoke permanently: edit the env and restart. See
    `docs/design/v0.6-agent-tools-user-paths.md` §3.

    Idempotent: removing a non-registered path returns 200 with a
    no-op message rather than 404 — the UI's "X" button is meant to
    be tap-and-forget.
    """
    _require_admin(body.api_key, role)
    username = _bearer_username(request) or "admin"

    from tools.code.sandbox import unregister_user_path

    ok, msg = unregister_user_path(body.path)
    _write_audit(
        role,
        "/admin/agent/allowed-paths/remove",
        query=f"unregister:{body.path}",
        answer=f"ok={ok}; {msg}",
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "removed": True,
        "path": body.path,
        "message": msg,
        "by": username,
        "session_scoped": True,
    }
