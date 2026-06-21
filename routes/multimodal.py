"""Multimodal /analyze/* + /screen/analyze/ routes (PR-H)."""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from config import UPLOAD_DIR
from routes._deps import get_file_processor, get_rag_engine
from routes._helpers import (
    _require_feature,
    _write_audit,
    get_role_from_request,
    verify_api_key,
)


class _LazySingleton:
    def __init__(self, getter):
        object.__setattr__(self, "_getter", getter)
    def __getattr__(self, name):
        return getattr(self._getter(), name)


rag_engine = _LazySingleton(get_rag_engine)
file_processor = _LazySingleton(get_file_processor)
router = APIRouter()

# ─── Pydantic ───

class ScreenRequest(BaseModel):
    api_key:  str
    question: str = ""
    region:   Optional[list] = None   # [x, y, w, h]

# ─── Endpoints ───

@router.post("/analyze/image/", summary="이미지 분석 [P7-VIS-1]")
async def analyze_image(
    file:    UploadFile = File(...),
    api_key: str = Form(...),
    role:    str = Depends(get_role_from_request),
):
    """이미지 파일 업로드 → EXIF + LLaVA 분석 → 결과 반환."""
    verify_api_key(api_key)
    suffix  = os.path.splitext(file.filename)[1].lower()
    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"지원 형식: {allowed}")

    # 임시 저장
    tmp_path = os.path.join(UPLOAD_DIR, f"vis_{int(time.time())}{suffix}")
    with open(tmp_path, "wb") as f:
        f.write(await file.read())

    try:
        from tools.multimodal.image_analyzer import analyze_image as _analyze
        result = _analyze(tmp_path)
        _write_audit(role, "/analyze/image/", query=file.filename,
                     answer=str(result.get("description",""))[:80])
        return {
            "filename":    file.filename,
            "analyzed_at": datetime.now().isoformat(),
            "description": result.get("description",""),
            "date":        result.get("date",""),
            "location":    result.get("location",""),
            "persons":     result.get("persons",[]),
            "tags":        result.get("tags",[]),
            "exif":        result.get("exif",{}),
            "success":     result.get("success", True),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try: os.remove(tmp_path)
        except Exception: pass

@router.post("/analyze/video/", summary="영상 분석 [P7-VID-1]")
async def analyze_video(
    file:    UploadFile = File(...),
    api_key: str = Form(...),
    role:    str = Depends(get_role_from_request),
):
    """영상 파일 업로드 → OpenCV 장면 + Whisper 자막 분석."""
    verify_api_key(api_key)
    suffix  = os.path.splitext(file.filename)[1].lower()
    allowed = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"지원 형식: {allowed}")

    tmp_path = os.path.join(UPLOAD_DIR, f"vid_{int(time.time())}{suffix}")
    with open(tmp_path, "wb") as f:
        f.write(await file.read())

    try:
        from tools.multimodal.video_analyzer import analyze_video as _analyze
        result = _analyze(tmp_path)
        _write_audit(role, "/analyze/video/", query=file.filename,
                     answer=str(result.get("summary",""))[:80])
        return {
            "filename":    file.filename,
            "analyzed_at": datetime.now().isoformat(),
            "summary":     result.get("summary",""),
            "duration":    result.get("duration",""),
            "scenes":      result.get("scenes",[]),
            "transcript":  result.get("transcript",""),
            "tags":        result.get("tags",[]),
            "success":     result.get("success", True),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try: os.remove(tmp_path)
        except Exception: pass

@router.post("/vision/upload/", summary="비전 이미지 업로드 (챗 첨부) [v18.7]")
async def vision_upload(
    file:    UploadFile = File(...),
    api_key: str = Form(...),
    role:    str = Depends(get_role_from_request),
):
    """챗 비전 첨부용 경량 업로드.

    이미지를 UPLOAD_DIR 에 저장하고 server-side 경로만 반환한다 —
    분석/인제스트 없음 (그건 handle_vision 가 POST /query/ 흐름에서
    수행). 반환된 image_path 를 클라이언트가 다음 /query/ 요청에 실어
    보내면, 서버가 _safe_image_path 로 UPLOAD_DIR 격리를 재검증한 뒤
    vision 모드로 라우팅한다. (클라이언트가 경로를 변조해도 격리
    재검증에서 걸러진다.)
    """
    verify_api_key(api_key)

    # ROLE_ALLOWED 와 동일 정책 — external(일상챗 전용) 차단.
    from core.intent_classifier import ROLE_ALLOWED
    if "vision" not in ROLE_ALLOWED.get(role, set()):
        raise HTTPException(status_code=403, detail="비전 분석 권한이 없습니다.")

    suffix  = os.path.splitext(file.filename or "")[1].lower()
    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    if suffix not in allowed:
        raise HTTPException(status_code=400,
                            detail=f"지원 형식: {sorted(allowed)}")

    data = await file.read()
    try:
        from config import MAX_UPLOAD_BYTES
        cap = MAX_UPLOAD_BYTES
    except Exception:
        cap = 20 * 1024 * 1024
    if len(data) > cap:
        raise HTTPException(status_code=413,
                            detail="이미지가 너무 큽니다.")

    import uuid
    name = f"chatvis_{int(time.time())}_{uuid.uuid4().hex[:8]}{suffix}"
    dest = os.path.join(UPLOAD_DIR, name)
    with open(dest, "wb") as f:
        f.write(data)

    _write_audit(role, "/vision/upload/", query=(file.filename or "")[:80],
                 answer=f"saved {name} ({len(data)} bytes)")
    return {
        "image_path": os.path.abspath(dest),
        "filename":   file.filename or name,
        "bytes":      len(data),
    }

@router.post("/screen/analyze/", summary="화면 분석 [P7-SCR-1]")
async def screen_analyze(
    data: ScreenRequest,
    role: str = Depends(get_role_from_request),
):
    """화면 캡처 → OCR → LLM 분석. admin 전용."""
    _require_feature(data.api_key, role, "admin.tools")
    try:
        from tools.screen.screen_agent import run_screen_analysis
        region = tuple(data.region) if data.region else None
        result = run_screen_analysis(data.question, region)
        _write_audit(role, "/screen/analyze/",
                     query=data.question[:60],
                     answer=result.get("analysis","")[:80])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
