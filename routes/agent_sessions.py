"""Agent chat session CRUD endpoints (v0.6.1 UX overhaul).

Server-side persistence for separate agent conversations. Admin-only,
audit-logged. Backed by ``core/agent_sessions.py`` (SQLite in
``james_data.db``).

Endpoints:

  * `GET    /admin/agent/sessions`        → newest-first summaries
  * `POST   /admin/agent/sessions`        `{title?}` → create
  * `GET    /admin/agent/sessions/{sid}`  → one session incl. messages
  * `PUT    /admin/agent/sessions/{sid}`  `{title?, messages?}` → update
  * `DELETE /admin/agent/sessions/{sid}`  → delete
"""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routes._helpers import (
    _bearer_username,
    _require_admin,
    _write_audit,
    get_role_from_request,
)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    api_key: str
    title: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    api_key: str
    title: Optional[str] = None
    messages: Optional[List[Any]] = None


class DeleteSessionRequest(BaseModel):
    api_key: str


@router.get("/admin/agent/sessions", summary="에이전트 세션 목록 [v0.6.1]")
async def list_agent_sessions(
    api_key: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    _require_admin(api_key, role)
    from core import agent_sessions as asx
    return {"sessions": asx.list_sessions()}


@router.post("/admin/agent/sessions", summary="에이전트 세션 생성 [v0.6.1]")
async def create_agent_session(
    body: CreateSessionRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    _require_admin(body.api_key, role)
    username = _bearer_username(request) or "admin"
    from core import agent_sessions as asx
    sess = asx.create_session(body.title)
    _write_audit(role, "/admin/agent/sessions",
                 query=f"create:{sess['id']}", answer="ok")
    return {"ok": True, "session": sess, "by": username}


@router.get("/admin/agent/sessions/{sid}", summary="에이전트 세션 조회 [v0.6.1]")
async def get_agent_session(
    sid: str,
    api_key: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    _require_admin(api_key, role)
    from core import agent_sessions as asx
    sess = asx.get_session(sid)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"no such session: {sid!r}")
    return {"ok": True, "session": sess}


@router.put("/admin/agent/sessions/{sid}", summary="에이전트 세션 수정 [v0.6.1]")
async def update_agent_session(
    sid: str,
    body: UpdateSessionRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    _require_admin(body.api_key, role)
    from core import agent_sessions as asx
    sess = asx.update_session(sid, title=body.title, messages=body.messages)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"no such session: {sid!r}")
    _write_audit(role, "/admin/agent/sessions",
                 query=f"update:{sid}", answer=f"msgs={sess['msg_count']}")
    return {"ok": True, "session": sess}


@router.delete("/admin/agent/sessions/{sid}", summary="에이전트 세션 삭제 [v0.6.1]")
async def delete_agent_session(
    sid: str,
    api_key: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    _require_admin(api_key, role)
    from core import agent_sessions as asx
    removed = asx.delete_session(sid)
    _write_audit(role, "/admin/agent/sessions",
                 query=f"delete:{sid}", answer=f"removed={removed}")
    return {"ok": True, "removed": removed}
