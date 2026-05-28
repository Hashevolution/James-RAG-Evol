"""Feedback routes (PR-H of v0.4.x server-split)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes._deps import get_rag_engine
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
router = APIRouter()

# ─── Pydantic ───

class FeedbackRequest(BaseModel):
    api_key:      str
    direction_id: str
    signal:       str
    query:        str = ""

# ─── Endpoints ───

@router.post("/feedback/", summary="피드백 전송 [P7-EVO-C]")
async def submit_feedback(
    data: FeedbackRequest,
    role: str = Depends(get_role_from_request),
):
    verify_api_key(data.api_key)
    try:
        from core.feedback_engine import accumulate_feedback
        result = accumulate_feedback(data.direction_id, data.signal, data.query)
        _write_audit(role, "/feedback/", query=f"{data.signal}:{data.direction_id[:20]}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/feedback/stats/", summary="피드백 통계 [P7-EVO-C]")
async def get_feedback_stats_api(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from core.feedback_engine import get_feedback_stats
        return get_feedback_stats()
    except Exception as e:
        return {"error": str(e)}
