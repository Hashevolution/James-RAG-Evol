"""Main /query/ endpoint (PR-H of v0.4.x server-split)."""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.feedback_engine import FeedbackEngine
from routes._deps import get_rag_engine
from routes._helpers import (
    _require_feature,
    _write_audit,
    get_client_ip,
    get_role_from_request,
)


class _LazySingleton:
    def __init__(self, getter):
        object.__setattr__(self, "_getter", getter)
    def __getattr__(self, name):
        return getattr(self._getter(), name)


rag_engine = _LazySingleton(get_rag_engine)
router = APIRouter()


def _safe_image_path(raw: str) -> str:
    """Return ``raw`` only if it resolves to an existing file INSIDE
    UPLOAD_DIR; else "". Blocks path-traversal / arbitrary-file-read via
    a client-supplied ``image_path`` (the client can only reference files
    it legitimately uploaded through /analyze/image/).
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        import os
        from config import UPLOAD_DIR
        base = os.path.realpath(UPLOAD_DIR)
        target = os.path.realpath(raw)
        if os.path.commonpath([base, target]) != base:
            return ""           # outside UPLOAD_DIR → reject
        return target if os.path.isfile(target) else ""
    except Exception:
        return ""

# ─── Pydantic ───

class QueryRequest(BaseModel):
    api_key:          str
    question:         str
    source_type:      str = "prod"
    session_id:       str = "default"   # 대화 세션 구분
    session_language: str = ""          # [STEP2-A] 세션 언어 (빈 문자열=기본)
    # [#65 phase 3] admin-only debug field. When True AND the resolved
    # role is "admin", the response carries `retrieved_contexts` (the
    # actual chunk texts that fed the LLM). Used by `eval/ragas/run_ragas.py
    # --live` to drive RAGAS evaluation against the live retrieval path.
    # Non-admin callers see no behavior change — the field is silently
    # dropped from the response shape.
    include_contexts: bool = False
    # Response shape control — brief / standard / detailed. Empty
    # string falls through to JAMES_RESPONSE_STYLE env then `standard`.
    # See core/response_style.py for the resolver and preset defs.
    response_style:   str  = ""
    # Client-supplied trace_id (item: real reasoning stream). When set,
    # the server uses this id instead of generating a new one — letting
    # the client poll /trace/poll/{trace_id} for stage events as they
    # arrive (real reasoning stream, replacing the fake 2.5s timer
    # placeholder). Empty → server generates uuid7 as before.
    trace_id:         str  = ""
    # item #6: client-side mode picker. When non-empty + recognised +
    # role-allowed, bypasses the QueryRouter intent classifier and
    # routes straight to that mode handler. Permitted values:
    # chat / retrieval / meta / coding / wiki_edit / self_evolve.
    mode_override:    str  = ""
    # [#A8-6] User explicitly asked for additional web exploration.
    # When True AND role is in web_search_config.allowed_roles, pipeline's
    # `low_relevance` gate is bypassed — web search runs regardless of
    # `unified_score < threshold`. Chat UI surfaces this via a
    # "🌐 웹으로 더 조사" chip on low-confidence answers; click re-issues
    # the same question with this flag set.
    force_web_search: bool = False
    # [#A2 phase 2] User-selected LLM tag from the secondary picker.
    # Validated server-side against core.model_catalog before being passed
    # to call_gemma. Empty string OR a tag not in the per-mode catalog
    # silently falls back to the mode default (security: client cannot
    # request arbitrary Ollama tags).
    selected_model:   str  = ""
    # [v18.7 vision-wire] Server-side path of a previously-uploaded image
    # (e.g. the temp file written by POST /analyze/image/). When set and
    # the path resolves INSIDE UPLOAD_DIR (path-traversal guard) and the
    # role is vision-allowed, the engine routes this turn to vision mode
    # (handle_vision → local llava). A path outside UPLOAD_DIR, or a
    # non-existent file, is silently dropped — the query proceeds as text.
    image_path:       str  = ""

class QueryResponse(BaseModel):
    question:       str
    answer:         str
    sources:        list
    blocked:        bool  = False
    role_used:      str   = "external"
    graph_paths:    list  = []
    timing_sec:     float = 0.0
    unified_score:  float = 0.0    # [3-B] 신뢰도 배지
    mode:           str   = ""
    session_id:     str   = ""
    direction_id:   str   = ""
    # [#65 phase 3] populated only when request.include_contexts AND role==admin.
    retrieved_contexts: Optional[list] = None
    # [#47 phase 1] end-to-end trace correlation. Always populated; users
    # quote this on bug reports so we can read back the per-stage trace.
    trace_id:       str   = ""
    # [#A6-2] 웹 검색 사용 여부 + 출처 URL — 답변 bubble의 "🌐 웹 검색
    # 사용됨" 배지 + 출처 리스트. internal-only 답변엔 둘 다 빈/false.
    web_used:       bool  = False
    web_sources:    list  = []
    # [#A8-7] chat-side "📥 위키 저장" chip이 approve API에 보낼 proposal id.
    # 빈 문자열이면 chip 숨김. web_used=true일 때만 채워진다.
    pending_save_proposal_id: str = ""

# ─── Endpoints ───

@router.post("/query/", response_model=QueryResponse, summary="질의응답 (권한 기반)")
async def query(
    data:    QueryRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    # [W4-Q2-c] api_key + feature gate. query.basic defaults to ALL
    # roles (admin/manager/employee/external) so default behaviour is
    # unchanged — anyone with a valid api_key still hits the engine.
    # Operators who want to revoke query access for a specific role
    # (e.g. lock down external during incident response) now have a
    # matrix knob without revoking the user's api_key.
    _require_feature(data.api_key, role, "query.basic")
    ip = get_client_ip(request)

    # [#47 phase 1] start a trace at the API edge. Stage logs from any
    # downstream module reading `current_trace_id` correlate to this id.
    # Client-supplied trace_id takes precedence (real-reasoning-stream
    # feature) — lets the client poll /trace/poll/{trace_id} the moment
    # it sends the request, before /query/ has returned a response.
    # Sanity-check the supplied id (alphanumeric + hyphens only, 8-64
    # chars) to keep filesystem path-safety guarantees from
    # observability._trace_file_for.
    from core.observability import start_trace, log_stage
    import re as _re
    client_tid = (data.trace_id or "").strip()
    if client_tid and _re.fullmatch(r"[A-Za-z0-9_\-]{8,64}", client_tid):
        trace_id = start_trace(client_tid)
    else:
        trace_id = start_trace()

    # Track 2c bidi input gate (2026-06-02) — strip Unicode bidirectional
    # formatting + zero-width controls before the LLM sees the query.
    # See core/input_normalization.py and
    # reports/research-runs/bidi-normalization-audit-20260602.md §7.2 for
    # the runtime-gate vs test-fixture-preservation discipline.
    from core.input_normalization import normalize_user_input
    _raw_question = data.question.strip()
    question, _norm_audit = normalize_user_input(_raw_question)
    if _norm_audit["chars_dropped"]:
        log_stage("input_normalize", role=role, **_norm_audit)
    session_id = data.session_id or "default"
    if not question:
        log_stage("auth", role=role, allowed=False, reason="empty_question")
        raise HTTPException(status_code=400, detail="질문이 비어 있습니다.")

    log_stage("auth", role=role, allowed=True, session_id=session_id,
              question_len=len(question), include_contexts=data.include_contexts)

    t_start = time.time()
    result  = rag_engine.query(
        user_query       = question,
        user_role        = role,
        session_id       = session_id,
        session_language = data.session_language,  # [STEP2-A] 세션 언어
        response_style   = data.response_style,    # brief/standard/detailed
        mode_override    = data.mode_override,     # item #6: chat 페이지 모드 picker
        force_web_search = data.force_web_search,  # [#A8-6] explicit web exploration
        selected_model   = data.selected_model,    # [#A2 phase 2] user-picked LLM tag
        image_path       = _safe_image_path(data.image_path),  # vision-wire
    )
    elapsed = time.time() - t_start

    log_stage("complete", elapsed_ms=int(elapsed * 1000),
              blocked=bool(result.get("blocked", False)),
              answer_len=len(result.get("answer", "") or ""),
              graph_paths=len(result.get("graph_paths") or []),
              mode=result.get("mode", ""))

    answer = result.get("answer", "")

    # [P4-SRV-2] 감사 로그
    _write_audit(
        user_role      = role,
        endpoint       = "/query/",
        query          = question,
        answer         = answer,
        graph_paths    = result.get("graph_paths", []),
        blocked        = result.get("blocked", False),
        security_event = "blocked" if result.get("blocked") else "",
        elapsed_sec    = elapsed,
        ip_address     = ip,
    )

    # [P7] 대화 히스토리 자동 저장
    if not result.get("blocked") and answer:
        try:
            from core.memory import MemoryStore
            MemoryStore().save_turn(
                session_id = session_id,
                question   = question,
                answer     = answer,
                mode       = result.get("mode", ""),
            )
        except Exception as e:
            print(f"[HISTORY] 저장 실패: {e}")

    # [P7-EVO] 자기진화 관찰 — 개선 신호 자동 수집
    if not result.get("blocked"):
        try:
            from tools.self.evo_analyzer import observe_and_signal
            signal = observe_and_signal(question, {
                **result,
                "unified_score": result.get("unified_score", 1.0),
            })
            if signal:
                print(f"[EVO] 신호 감지: {signal['type']} "
                      f"score={signal.get('score','-'):.3f}")
        except Exception:
            pass

    # [P7-EVO-B] 중요도 측정 — LOOM 연동
    if not result.get("blocked"):
        try:
            from tools.self.importance_scorer import score_query
            imp = score_query(
                question,
                unified_score = result.get("unified_score", 1.0),
                answer        = result.get("answer", ""),
            )
            if imp["propose_wiki"]:
                print(f"[EVO-B] wiki 보강 제안 대상: '{question[:40]}'")
        except Exception:
            pass

    # [P8-EVAL-1] 성능 지표 기록
    try:
        from tools.self.performance_evaluator import record_query
        record_query(question, result, elapsed)
    except Exception:
        pass

    response = {
        "question":      question,
        "answer":        answer,
        "sources":       result.get("sources", []),
        "blocked":       result.get("blocked", False),
        "role_used":     role,
        "graph_paths":   result.get("graph_paths", []),
        "timing_sec":    round(elapsed, 2),
        "mode":          result.get("mode", ""),
        "session_id":    session_id,
        "unified_score": round(result.get("unified_score", 0.0), 3),  # [3-B] 신뢰도
        "direction_id":  FeedbackEngine.make_direction_id(
            result.get("mode",""), question
        ) if not result.get("blocked") else "",
        # [#47 phase 1] correlate response to per-stage trace file.
        "trace_id":      trace_id,
        # [#A6-2] 웹 검색 사용됨 배지 + 출처 URL (자료 부족 fallback 시).
        "web_used":      bool(result.get("web_used", False)),
        "web_sources":   result.get("web_sources", []),
        # [#A8-7] chat-side 위키 저장 chip용 proposal id
        "pending_save_proposal_id": result.get("pending_save_proposal_id", ""),
    }
    # [#65 phase 3] admin-only RAGAS evaluation hook. The chunk texts that
    # fed the LLM are surfaced only when (a) caller opted in via
    # `include_contexts=true` AND (b) resolved role is "admin". Other
    # roles see the same response shape as before.
    if data.include_contexts and role == "admin":
        response["retrieved_contexts"] = result.get("retrieved_contexts", [])
    return response
