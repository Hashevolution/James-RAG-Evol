"""W7-A data artifact + upload-history routes.

Extracted from server_llmwiki.py per docs/design/v0.4.x-server-split.md
PR-D. 5 endpoints moved verbatim — handler body byte-identical (only
``@app.<m>`` -> ``@router.<m>``).

URL invariant: ``python scripts/audit_endpoint_paths.py origin/main``
must report 0-diff against the pre-PR-D baseline.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from routes._helpers import (
    _AUDIT_DB,
    _bearer_username,
    _require_feature,
    get_role_from_request,
)

router = APIRouter()


# ─── Endpoints ─────────────────────────────────────────────────────

@router.get("/admin/uploads/history/",
         summary="업로드 파일 이력 [item #7-C]")
async def admin_uploads_history(
    api_key: str,
    limit:   int = 50,
    offset:  int = 0,
    q:       str = "",
    role:    str = Depends(get_role_from_request),
):
    """[#7-C] Read /upload/ rows from the audit_log SQLite table.

    Returned shape (per row): timestamp, filename (= audit `query`
    field — `_write_audit` for /upload/ stores file.filename here),
    user_role, ip_address, blocked, security_event.

    Pagination via limit/offset (default 50 / 0). Optional `q` does a
    case-sensitive LIKE %...% on filename. Both bound as parameters —
    SQLite parameterisation is the trust boundary for the search box.

    Admin-gated; unrelated audit endpoints already exist for the wider
    log surface.
    """
    _require_feature(api_key, role, "admin.data")
    # Hard cap to keep the JSON payload bounded and avoid the
    # browser locking up if an operator passes ?limit=999999.
    limit  = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))
    qstr   = (q or "").strip()

    items: list = []
    total: int  = 0
    try:
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if qstr:
            cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM audit_log "
                "WHERE endpoint='/upload/' AND query LIKE ?",
                (f"%{qstr}%",),
            ).fetchone()
            rows = conn.execute(
                "SELECT * FROM audit_log "
                "WHERE endpoint='/upload/' AND query LIKE ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (f"%{qstr}%", limit, offset),
            ).fetchall()
        else:
            cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM audit_log "
                "WHERE endpoint='/upload/'"
            ).fetchone()
            rows = conn.execute(
                "SELECT * FROM audit_log "
                "WHERE endpoint='/upload/' "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        total = int(cnt["c"]) if cnt else 0
        for r in rows:
            items.append({
                "timestamp":      r["timestamp"] or "",
                "filename":       r["query"] or "",
                "user_role":      r["user_role"] or "",
                "ip_address":     r["ip_address"] or "",
                "blocked":        bool(r["blocked"]),
                "security_event": r["security_event"] or "",
            })
        conn.close()
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e),
                "limit": limit, "offset": offset, "q": qstr}

    return {"items": items, "total": total,
            "limit": limit, "offset": offset, "q": qstr}

@router.get("/admin/artifacts/list", summary="데이터 아티팩트 — 관리자 전체 조회 (W7-A)")
async def admin_artifacts_list(
    api_key: str,
    status:  str = "",
    q:       str = "",
    limit:   int = 50,
    offset:  int = 0,
    role:    str = Depends(get_role_from_request),
):
    """All artifacts (every uploader). admin.data feature."""
    _require_feature(api_key, role, "admin.data")
    from core.data_artifacts import list_artifacts, count_artifacts
    s = status.strip() or None
    qstr = q.strip() or None
    return {
        "items":  list_artifacts(status=s, q=qstr, limit=limit, offset=offset),
        "total":  count_artifacts(status=s, q=qstr),
        "status": s or "",
        "q":      qstr or "",
        "limit":  limit,
        "offset": offset,
    }

@router.get("/admin/artifacts/{artifact_id}", summary="아티팩트 상세 — 관리자 (W7-A)")
async def admin_artifacts_detail(
    artifact_id: str,
    api_key:     str,
    role:        str = Depends(get_role_from_request),
):
    """Admin view — owner ignored, returns the row regardless."""
    _require_feature(api_key, role, "admin.data")
    from core.data_artifacts import get_artifact
    row = get_artifact(artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return row

@router.get("/artifacts/mine/list", summary="내 데이터 아티팩트 (W7-A)")
async def mine_artifacts_list(
    request: Request,
    status:  str = "",
    q:       str = "",
    limit:   int = 50,
    offset:  int = 0,
    role:    str = Depends(get_role_from_request),
):
    """User self-view. JWT subject is the scope — non-JWT callers
    (system api_key only) are denied because there's no "own" to
    bind. data.view_own feature gates the role (every role allowed
    by default; admin can revoke per role)."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "data.view_own").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (data.view_own)")
    username = _bearer_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    from core.data_artifacts import list_artifacts, count_artifacts
    s = status.strip() or None
    qstr = q.strip() or None
    return {
        "items":  list_artifacts(username=username, status=s, q=qstr,
                                 limit=limit, offset=offset),
        "total":  count_artifacts(username=username, status=s, q=qstr),
        "status": s or "",
        "q":      qstr or "",
        "limit":  limit,
        "offset": offset,
    }

@router.get("/artifacts/mine/{artifact_id}", summary="내 아티팩트 상세 (W7-A)")
async def mine_artifacts_detail(
    artifact_id: str,
    request:     Request,
    role:        str = Depends(get_role_from_request),
):
    """Self-view. ``get_artifact(requester_username=...)`` returns None
    when the row belongs to someone else — surfaces as 404 here so a
    caller can't probe other users' artifact ids."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "data.view_own").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (data.view_own)")
    username = _bearer_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    from core.data_artifacts import get_artifact
    row = get_artifact(artifact_id, requester_username=username)
    if row is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return row
