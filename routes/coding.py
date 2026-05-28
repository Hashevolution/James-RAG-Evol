"""Coding agent routes (Phase 5.5).

Extracted from server_llmwiki.py per docs/design/v0.4.x-server-split.md
PR-F. 4 endpoints + 3 Pydantic models moved verbatim — handler body
byte-identical (only ``@app.<m>`` -> ``@router.<m>``).

URL invariant: ``python scripts/audit_endpoint_paths.py origin/main``
must report 0-diff against the pre-PR-F baseline.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routes._helpers import (
    _AUDIT_DB,
    _write_audit,
    get_client_ip,
    get_role_from_request,
    verify_api_key,
)

router = APIRouter()

# ─── Pydantic models ───

class CodeReadRequest(BaseModel):
    api_key:    str
    path:       str
    start_line: int = 1
    end_line:   Optional[int] = None

class CodeAnalyzeRequest(BaseModel):
    api_key:       str
    path:          str
    analysis_type: str = "review"

class CodeEditRequest(BaseModel):
    api_key:     str
    path:        str
    content:     str
    start_line:  Optional[int] = None
    end_line:    Optional[int] = None

class CodeResponse(BaseModel):
    success: bool
    result:  str
    meta:    dict = {}

# ─── Endpoints ───

@router.post("/code/read/", response_model=CodeResponse, summary="코드 읽기 [P5.5]",
          description="workspace 내 파일 읽기 전용. Sandbox 검증 필수.")
async def code_read(
    data: CodeReadRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    verify_api_key(data.api_key)
    ip = get_client_ip(request)

    # employee 이상만 허용
    from core.security_layer import ROLE_LEVEL
    if ROLE_LEVEL.get(role, 0) < 1:
        raise HTTPException(status_code=403, detail="코드 읽기는 employee 이상 권한 필요")

    try:
        from tools.code.code_reader import CodeReader
        reader = CodeReader()
        ok, content, meta = reader.read_file(data.path, data.start_line, data.end_line)
        _write_audit(role, "/code/read/", query=data.path, ip_address=ip)
        return {"success": ok, "result": content, "meta": meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/code/analyze/", response_model=CodeResponse, summary="코드 분석 [P5.5]",
          description="JAMES Core Engine을 통한 코드 분석. Sandbox 검증 필수.")
async def code_analyze(
    data: CodeAnalyzeRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    verify_api_key(data.api_key)
    ip = get_client_ip(request)

    from core.security_layer import ROLE_LEVEL
    if ROLE_LEVEL.get(role, 0) < 1:
        raise HTTPException(status_code=403, detail="코드 분석은 employee 이상 권한 필요")

    try:
        from tools.code.code_analyzer import CodeAnalyzer
        analyzer = CodeAnalyzer(user_role=role)
        ok, result, meta = analyzer.analyze_file(data.path, data.analysis_type)
        _write_audit(role, "/code/analyze/", query=f"{data.path}:{data.analysis_type}",
                     answer=result[:200], ip_address=ip)
        return {"success": ok, "result": result, "meta": meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/code/edit/", response_model=CodeResponse, summary="코드 수정 [P5.5]",
          description="Sandbox 검증 통과 후 파일 수정. admin 전용.")
async def code_edit(
    data: CodeEditRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    verify_api_key(data.api_key)
    ip = get_client_ip(request)

    # [P5.5] 코드 수정은 admin 전용 (보수적 정책)
    if role != "admin":
        _write_audit(role, "/code/edit/",
                     security_event=f"edit_denied role={role}",
                     blocked=True, ip_address=ip)
        raise HTTPException(status_code=403, detail="코드 수정은 admin 권한 필요")

    try:
        from tools.code.code_editor import CodeEditor
        editor = CodeEditor()
        if data.start_line and data.end_line:
            ok, msg, diff = editor.replace_lines(
                data.path, data.start_line, data.end_line, data.content
            )
            meta = {"diff": diff[:500]}
        else:
            ok, msg = editor.write_file(data.path, data.content)
            meta = {}

        _write_audit(role, "/code/edit/", query=data.path,
                     answer=msg, ip_address=ip)
        return {"success": ok, "result": msg, "meta": meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/code/surface/", summary="공격 surface 수집 [P5.5]",
         description="코딩 에이전트 사용 중 수집된 보안 이벤트 조회. admin 전용.")
async def code_surface(
    api_key: str,
    role: str = Depends(get_role_from_request),
):
    """[Phase 4b-1] SQLite audit_log 기반 attack-surface 집계.

    이전: james_audit_tool.jsonl 을 통째로 읽어 4가지 event_type
    (SANDBOX_BLOCK / PATH_VIOLATION / ATTACK_SURFACE_SCAN /
    PROTECTED_FILE_BLOCK) 만 필터. 파일 누적 시 O(file size).
    이제: Phase 1 mirror 가 audit_log.security_event 에 동일 값을
    기록하므로 ``security_event IN (...)`` 단일 쿼리로 끝남. 응답
    스키마는 그대로 유지 (total_events / events / summary).
    """
    verify_api_key(api_key)
    if role != "admin":
        raise HTTPException(status_code=403, detail="admin 전용")

    _SURFACE_EVENTS = (
        "SANDBOX_BLOCK", "PATH_VIOLATION",
        "ATTACK_SURFACE_SCAN", "PROTECTED_FILE_BLOCK",
    )
    events: list = []
    try:
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in _SURFACE_EVENTS)
        rows = conn.execute(
            f"SELECT timestamp, user_role, endpoint, query, "
            f"       security_event, blocked "
            f"FROM audit_log "
            f"WHERE security_event IN ({placeholders}) "
            f"ORDER BY id ASC",
            _SURFACE_EVENTS,
        ).fetchall()
        conn.close()
        for r in rows:
            events.append({
                "time":    r["timestamp"],
                "event":   r["security_event"],
                "role":    r["user_role"],
                "detail":  (r["query"] or "")[:300],
                "blocked": bool(r["blocked"]),
            })
    except Exception:
        # audit_log unavailable → empty surface rather than 500
        # (matches the pre-migration behaviour of missing JSONL).
        pass

    return {
        "total_events": len(events),
        "events":       events[-50:],   # 최근 50개
        "summary": {
            "sandbox_blocks":   sum(1 for e in events if e["event"] == "SANDBOX_BLOCK"),
            "path_violations":  sum(1 for e in events if e["event"] == "PATH_VIOLATION"),
            "surface_scans":    sum(1 for e in events if e["event"] == "ATTACK_SURFACE_SCAN"),
            "protected_blocks": sum(1 for e in events if e["event"] == "PROTECTED_FILE_BLOCK"),
        }
    }
