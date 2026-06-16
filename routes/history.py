"""History routes (PR-H of v0.4.x server-split)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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

# ─── Endpoints ───

@router.get("/history/", summary="대화 히스토리 조회 [P7]")
async def get_history(
    api_key:    str,
    session_id: str = "default",
    limit:      int = 20,
    role:       str = Depends(get_role_from_request),
):
    verify_api_key(api_key)
    try:
        from core.memory import MemoryStore
        turns = MemoryStore().get_recent_turns(session_id, limit)
        return {"session_id": session_id, "turns": turns, "count": len(turns)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/sessions/", summary="세션 목록 조회 [P7]")
async def get_sessions(
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    verify_api_key(api_key)
    try:
        from core.memory import MemoryStore
        return {"sessions": MemoryStore().get_all_sessions()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/history/sessions/rename/", summary="세션 이름 변경 [3-D]")
async def rename_session(
    api_key:    str,
    session_id: str,
    name:       str,
    role:       str = Depends(get_role_from_request),
):
    """[3-D] 세션에 사용자 지정 이름 부여."""
    verify_api_key(api_key)
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id 필요")
    if len(name) > 60:
        raise HTTPException(status_code=400, detail="이름은 60자 이내")
    try:
        from core.memory import MemoryStore
        ok = MemoryStore().set_session_name(session_id, name.strip())
        return {"success": ok, "session_id": session_id, "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/history/sessions/favorite/",
    summary="세션 즐겨찾기 토글 [v0.6.1 v12]",
)
async def set_session_favorite(
    api_key:    str,
    session_id: str,
    favorited:  bool,
    role:       str = Depends(get_role_from_request),
):
    """v0.6.1 v12 (2026-06-16) — 세션을 즐겨찾기로 고정/해제.

    Operator catch: the v0.6.1 v8 favorite primitive lived in
    localStorage only, so the PC web and phone web didn't see the
    same star state. This endpoint promotes favorites to the same
    cross-device store as session names — any client signed in with
    the same api_key + JWT sees the same list.
    """
    verify_api_key(api_key)
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id 필요")
    try:
        from core.memory import MemoryStore
        ok = MemoryStore().set_session_favorite(session_id, bool(favorited))
        return {
            "success":    ok,
            "session_id": session_id,
            "favorited":  bool(favorited),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/history/sessions/favorites/",
    summary="즐겨찾기 세션 SID 목록 [v0.6.1 v12]",
)
async def get_session_favorites(
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """v0.6.1 v12 (2026-06-16) — 즐겨찾기 SID 리스트. 클라이언트가
    boot 시 한 번 호출해서 localStorage 캐시와 union/replace 한다.
    /history/sessions/ 의 응답에도 ``is_favorite`` 가 포함되므로
    엄밀히 필요하진 않지만, 가벼운 polling 경로로 노출.
    """
    verify_api_key(api_key)
    try:
        from core.memory import MemoryStore
        return {"favorites": MemoryStore().get_favorite_session_ids()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/history/", summary="대화 히스토리 삭제 [P7]")
async def delete_history(
    api_key:    str,
    session_id: str = "default",
    role:       str = Depends(get_role_from_request),
):
    verify_api_key(api_key)
    try:
        from core.memory import MemoryStore
        ok = MemoryStore().delete_session(session_id)
        return {"success": ok, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/history/summarize/", summary="세션 요약 저장 [P7]")
async def summarize_session(
    api_key:    str,
    session_id: str = "default",
    role:       str = Depends(get_role_from_request),
):
    """
    세션 대화를 LLM으로 요약해서 장기 기억에 저장.
    세션 종료 시 또는 수동 호출.
    """
    verify_api_key(api_key)
    try:
        from core.memory import MemoryStore
        store = MemoryStore()

        # 해당 세션 대화 조회
        turns = store.get_recent_turns(session_id, limit=20)
        if not turns:
            return {"success": False, "message": "저장된 대화 없음"}

        # 대화 텍스트 구성
        dialogue = "\n".join([
            f"{'User' if t['role']=='user' else '자메스'}: {t['content'][:200]}"
            for t in turns
        ])

        # LLM으로 요약 생성 (#13: router 경유)
        from llm.router import RouterWrapper
        llm = RouterWrapper("general")
        summary_prompt = (
            f"아래 대화를 3줄 이내로 핵심만 요약해줘. "
            f"주제와 결론 중심으로.\n\n{dialogue[:1500]}\n\n요약:"
        )
        summary = llm.call_gemma(summary_prompt, timeout=60, use_cache=False)
        if not summary:
            summary = dialogue[:200] + "..."

        # 주제 추출
        topic_prompt = (
            f"아래 대화의 주제를 단어 2~3개로 표현해줘.\n\n{dialogue[:500]}\n\n주제:"
        )
        topic = llm.call_gemma(topic_prompt, timeout=30, use_cache=False) or ""
        topic = topic.strip()[:30]

        # 장기 기억에 저장
        ok = store.save_session_summary(session_id, summary, topic)

        return {
            "success":    ok,
            "session_id": session_id,
            "summary":    summary,
            "topic":      topic,
            "turns":      len(turns) // 2,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/long-term/", summary="장기 기억 조회 [P7]")
async def get_long_term(
    api_key: str,
    limit:   int = 5,
    role:    str = Depends(get_role_from_request),
):
    """이전 세션 요약 목록 조회."""
    verify_api_key(api_key)
    try:
        from core.memory import MemoryStore
        summaries = MemoryStore().get_session_summaries(limit)
        return {"summaries": summaries, "count": len(summaries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
