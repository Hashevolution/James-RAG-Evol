"""LLM routing unified settings — admin HTTP surface (v0.6.1).

GET  /admin/llm-settings/  → snapshot for the Settings UI panel
POST /admin/llm-settings/  → partial-update (only keys in the body
                             are written; unknown keys → 400)

See ``docs/design/v0.6-llm-routing-unification.md`` + ARCHITECTURE
§5.7.16.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routes._helpers import (
    _bearer_username,
    _require_admin,
    _write_audit,
    get_role_from_request,
)

router = APIRouter()


class UpdateSettingsRequest(BaseModel):
    api_key: str
    settings: Dict[str, str]
    # Optional: keys the operator wants to *clear* (revert to env
    # fallback). Same admin gate as `settings`.
    clear: Optional[list] = None


@router.get("/admin/llm-settings/",
            summary="LLM 라우팅 통합 설정 조회 [v0.6.1]")
async def list_llm_settings(
    api_key: str,
    request: Request,
    role: str = Depends(get_role_from_request),
) -> Dict[str, Any]:
    _require_admin(api_key, role)
    from core.llm_settings import as_dict
    return as_dict()


@router.post("/admin/llm-settings/",
             summary="LLM 라우팅 통합 설정 저장 [v0.6.1]")
async def update_llm_settings(
    body: UpdateSettingsRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
) -> Dict[str, Any]:
    """Partial update + optional clear-to-env. Validates per-key via
    `core.llm_settings._validate` (called by `set`)."""
    _require_admin(body.api_key, role)
    username = _bearer_username(request) or "admin"

    from core.llm_settings import as_dict, clear, set as set_

    written: Dict[str, str] = {}
    errors: Dict[str, str] = {}

    # Writes first.
    if body.settings:
        for k, v in body.settings.items():
            try:
                set_(k, v, by=username)
                written[k] = v
            except ValueError as e:
                errors[k] = str(e)

    # Then clears.
    cleared: list = []
    if body.clear:
        for k in body.clear:
            try:
                clear(k)
                cleared.append(k)
            except ValueError as e:
                errors[k] = str(e)

    _write_audit(
        role, "/admin/llm-settings/",
        query=f"set={list(written.keys())} clear={cleared}",
        answer=f"errors={list(errors.keys())}",
    )

    if errors and not written and not cleared:
        # Nothing landed and everything errored — surface as 400.
        raise HTTPException(status_code=400, detail=errors)

    return {
        "written": written,
        "cleared": cleared,
        "errors": errors,
        "snapshot": as_dict(),
        "by": username,
    }
