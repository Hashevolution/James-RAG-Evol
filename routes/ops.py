"""Operational endpoints — status, hardware, trace, export, root JSON (PR-H)."""
from __future__ import annotations

import os
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from config import CHROMA_DIR, UPLOAD_DIR, WIKI_DIR
from routes._deps import get_rag_engine
from routes._helpers import (
    get_role_from_request,
    verify_api_key,
)


class _LazySingleton:
    def __init__(self, getter):
        object.__setattr__(self, "_getter", getter)
    def __getattr__(self, name):
        return getattr(self._getter(), name)


rag_engine = _LazySingleton(get_rag_engine)
router = APIRouter()

# ─── Pydantic ───

class StatusResponse(BaseModel):
    status:            str
    upload_dir:        str
    wiki_dir:          str
    chroma_dir:        str
    indexed_documents: int
    version:           str

# ─── Endpoints ───

@router.get("/status/", response_model=StatusResponse, summary="서버 상태")
async def status(api_key: str):
    verify_api_key(api_key)
    return {
        "status":            "running",
        "upload_dir":        os.path.abspath(UPLOAD_DIR),
        "wiki_dir":          os.path.abspath(WIKI_DIR),
        "chroma_dir":        os.path.abspath(CHROMA_DIR),
        "indexed_documents": rag_engine.vector_store.count(),
        "version":           "7.0.0",
    }

@router.get("/hardware/", summary="PC 하드웨어 정보 조회 [P3-1]")
async def hardware_info(
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """자메스를 실행하는 PC 하드웨어 측정 — 무기/장비 형식 반환."""
    verify_api_key(api_key)
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(__file__))
        from tools.system.hardware_inspector import get_hardware_specs
        specs = get_hardware_specs()
        return {"ok": True, "specs": specs}
    except Exception as e:
        # psutil 없는 환경 — 기본값 반환. [F821 fix 2026-05-11]
        # ``platform`` was referenced without import; before this fix
        # the fallback path raised NameError → 500 instead of the
        # friendly default specs. Imported locally so the happy path
        # is not taxed with an unused module load.
        import platform
        return {
            "ok": False,
            "specs": {
                "cpu":  {"name": platform.processor(), "cores": os.cpu_count(),
                         "level": 5, "weapon": {"icon":"🧮","name":"Mainstream CPU","role":"Compute","desc":"Mainstream inference"}},
                "ram":  {"total_gb": 0, "level": 5,
                         "weapon": {"icon":"💾","name":"Standard Memory","role":"Memory","desc":"Multi-session general use"}},
                "gpu":  {"name": "Unknown", "level": 0, "found": False,
                         "weapon": {"icon":"⚡","name":"CPU-only","role":"AI Acceleration","desc":"CPU-only inference (slow on large models)"}},
                "disk": {"total_gb": 0, "level": 5,
                         "weapon": {"icon":"🗄️","name":"Team Storage","role":"Storage","desc":"Mid-size knowledge base"}},
                "overall_level": 5,
                "james_rank": "Production Tier",
            },
            "error": str(e),
        }

@router.get("/")
async def root():
    return {
        "message":  "PROJECT JAMES v4.0 가동 중",
        "features": ["JWT Auth","Graph-RAG","ABAC+RBAC","Ontology",
                     "Output Filter","Rate Limiting","Audit DB","Instruction Isolation",
                     "Coding Agent (Phase 5.5)"],
        "docs":     "http://127.0.0.1:8000/docs",
    }

@router.get("/trace/poll/{trace_id}", summary="실시간 추론 단계 polling [real-reasoning-stream]")
async def trace_poll(
    trace_id: str,
    api_key:  str,
    after_ns: int = 0,
    role:     str = Depends(get_role_from_request),
):
    """Stream real reasoning stages as they arrive in the JSONL file.

    Client flow:
      1. Generate a uuid hex on the client (e.g. crypto.randomUUID).
      2. Submit POST /query/ with the trace_id field in the body.
      3. Immediately start polling this endpoint every ~200ms with
         after_ns increasing each call (last seen ts_ns) — minimises
         duplicate transfer.
      4. Render each new event in the chat bubble (retrieve / graph /
         answer / complete with their actual fields).
      5. Stop polling when the response arrives OR an event with
         stage='complete' is in the returned list.

    Auth: api_key only (no admin requirement). The trace_id itself
    acts as a capability — uuid hex is unguessable, so a different
    user cannot poll someone else's trace. Same trust model as
    /query/.

    Path arg sanitization: only alphanumerics + hyphen + underscore
    (8-64 chars). Keeps `core.observability._trace_file_for` from
    looking outside `reports/trace/<day>/`.
    """
    verify_api_key(api_key)

    # Path traversal guard — same regex as /query/'s client_tid check.
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_\-]{8,64}", trace_id):
        raise HTTPException(status_code=400,
                            detail="invalid trace_id format")

    from core.observability import read_trace
    rows = read_trace(trace_id)
    # Only return events newer than the last seen timestamp.
    new_rows = [r for r in rows if int(r.get("ts_ns") or 0) > int(after_ns or 0)]
    is_complete = any(r.get("stage") == "complete" for r in rows)

    return {
        "trace_id":  trace_id,
        "events":    new_rows,
        "complete":  is_complete,
        "total":     len(rows),
    }

@router.post("/export/", summary="답변 문서 export [item #4]")
async def export_answer(request: Request, role: str = Depends(get_role_from_request)):
    """Export an answer (or arbitrary content) to .md / .txt / .docx.

    Body:
      content:   text to export (typically a JAMES answer the user
                 wants to save).
      format:    "md" / "txt" / "docx" (default "md"). "pdf" is
                 documented as v0.3+ and silently downgrades to "md"
                 with `fallback_reason` set in the response headers.
      filename:  optional stem (no extension). Sanitized server-side.
      api_key:   required (matches the rest of the API contract).

    Returns: file bytes with proper MIME + Content-Disposition.

    Why a POST instead of GET: the answer content may be hundreds of
    KB. URL length limits would bite a GET. Also keeps the answer
    text out of access logs.

    Auth: api_key check only (no admin requirement). Any logged-in
    user may export their own answers — same trust model as the
    chat /query/ endpoint.
    """
    from fastapi.responses import Response
    body = await request.json()
    api_key  = body.get("api_key", "")
    content  = body.get("content", "") or ""
    fmt      = body.get("format", "md")
    filename = body.get("filename", "")

    verify_api_key(api_key)
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content must be a string")
    # Sanity cap — 1MB of text is more than enough for an answer.
    if len(content.encode("utf-8")) > 1_000_000:
        raise HTTPException(
            status_code=413,
            detail="content too large (>1MB); split into multiple exports",
        )

    from tools.export.document_exporter import export_document
    result = export_document(content, format=fmt, filename=filename)

    # ASCII-encode the filename for the header. Browsers handle utf-8
    # via the filename* RFC 5987 form when present, but the plain
    # `filename=` must stay ASCII-safe.
    ascii_name = re.sub(r"[^\w.\-]+", "_", result.filename)
    headers = {
        "Content-Disposition":
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(result.filename)}",
        "X-James-Export-Format": result.actual_format,
    }
    if result.fallback_reason:
        headers["X-James-Export-Fallback"] = result.fallback_reason[:256]

    return Response(
        content=result.data,
        media_type=result.mime,
        headers=headers,
    )
