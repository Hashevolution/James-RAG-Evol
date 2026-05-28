"""
PROJECT JAMES - Main Server v4.0 (Phase 4)

Phase 4 변경:
  [P4-SRV-1] Rate Limiting 미들웨어 (IP + role 기반)
  [P4-SRV-2] 감사 로그 SQLite DB (query + response + graph_path + security events)
  [P4-SRV-3] Write 권한 분리 — /upload/ admin 외 차단
  [P4-SRV-4] X-Role 개발용 헤더 제거 (DEV_MODE=0 시)
  [P4-SRV-5] Instruction Isolation 문서 업로드 시 적용
"""

# Reconfigure stdout/stderr to UTF-8 BEFORE any imports that print (config.py
# emits banner lines on import). Otherwise non-ASCII chars in any TIMING /
# diagnostic print path crash with UnicodeEncodeError on Windows cp949 console
# and propagate up to FastAPI as HTTP 400. Same helper used by admin scripts (#2/#24).
from utils.console import ensure_utf8_console
ensure_utf8_console()

import os
import re
import sqlite3
import time
from datetime import datetime
from collections import defaultdict
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from config import BASE_DIR, UPLOAD_DIR, WIKI_DIR, CHROMA_DIR
from core.graph_rag_engine import RAGEngine
from core.feedback_engine import FeedbackEngine
from processors.file_processor import FileProcessor

# Server-split scaffolding (v0.4.x cycle, PR-A) — auth/audit helpers
# moved to routes/_helpers.py. Re-imported here so handlers still inline
# in this module continue to use the same names. routes/<domain>.py
# modules import from routes/_helpers directly. See
# docs/design/v0.4.x-server-split.md.
from routes._helpers import (
    _AUDIT_DB,
    _require_feature,
    _write_audit,
    get_client_ip,
    get_role_from_request,
    resolve_api_key_principal,  # noqa: F401  back-compat re-export — test_api_key_middleware imports via server
    verify_api_key,
)
from routes._deps import (
    set_file_processor,
    set_rag_engine,
    set_rate_limiter,
)

# ─── [P4-SRV-2] 감사 로그 DB 초기화 ─────────────────────────

def _init_audit_db():
    conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT    NOT NULL,
            user_role    TEXT    NOT NULL,
            endpoint     TEXT    NOT NULL,
            query        TEXT,
            answer       TEXT,
            graph_paths  TEXT,     -- JSON 배열
            blocked      INTEGER   DEFAULT 0,
            security_event TEXT,
            elapsed_sec  REAL,
            ip_address   TEXT
        )
    """)
    conn.commit()
    conn.close()
    print(f"[AUDIT] DB 초기화: {_AUDIT_DB}")

_init_audit_db()

# ─── [P4-SRV-1] Rate Limiter ─────────────────────────────────

class RateLimiter:
    """
    [P4-SRV-1] IP 기반 Rate Limiting.

    규칙:
      - /query/ : window당 최대 요청 수 제한
      - /upload/: 더 엄격 (관리자 전용)
      - 초과 시 429 반환
    """
    def __init__(self, max_requests: int = 30, window_sec: int = 60):
        self.max_requests = max_requests
        self.window_sec   = window_sec
        self._requests    = defaultdict(list)   # ip → [timestamp, ...]

    def check(self, ip: str, endpoint: str = "/query/") -> bool:
        """True = 허용, False = 초과"""
        now = time.time()
        window_start = now - self.window_sec

        # 오래된 기록 제거
        self._requests[ip] = [t for t in self._requests[ip] if t > window_start]

        limit = self.max_requests
        if "/upload/" in endpoint:
            limit = 5   # 업로드는 더 엄격

        if len(self._requests[ip]) >= limit:
            return False

        self._requests[ip].append(now)
        return True

    def remaining(self, ip: str) -> int:
        now = time.time()
        self._requests[ip] = [t for t in self._requests[ip] if t > now - self.window_sec]
        return max(0, self.max_requests - len(self._requests[ip]))

_rate_limiter = RateLimiter(max_requests=30, window_sec=60)

# ─── App 초기화 ──────────────────────────────────────────────

app = FastAPI(
    title="PROJECT JAMES - AI Knowledge Engine",
    description="Graph-RAG + SecurityLayer + ABAC + JWT + Audit (Phase 7)",
    version="7.0.0",
)

# ─── 정적 파일 서빙 ─────────────────────────────────────────

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
STATIC_DIR   = os.path.join(FRONTEND_DIR, "static")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """개발 환경 — 정적 파일 캐시 비활성화"""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_index():
    index = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return HTMLResponse("<h1>PROJECT JAMES</h1><p>frontend/index.html 없음</p>")


# [2026-05-10] readiness probe — k8s/docker/uptime monitor 표준 경로.
# 인증 X (operational endpoint). DB / vector store / LLM 의 실 가용성은
# /status/ 가 보고하므로 여기는 process-alive 만 확인한다.
@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok"}


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def serve_admin():
    admin = os.path.join(FRONTEND_DIR, "admin.html")
    if os.path.exists(admin):
        return FileResponse(admin)
    return HTMLResponse("<h1>Admin</h1><p>frontend/admin.html 없음</p>")


@app.get("/workspace", response_class=HTMLResponse, include_in_schema=False)
async def serve_workspace():
    """[W7-B] Standalone workspace page — data explorer + (W8) jobs.

    Public route by design — the HTML is reachable without admin auth so
    employees can log in here directly. The data endpoints behind it
    (``/artifacts/mine/*`` and admin-only ``/admin/artifacts/*``) gate
    on the matrix; this HTML doesn't carry secrets.
    """
    page = os.path.join(FRONTEND_DIR, "workspace.html")
    if os.path.exists(page):
        return FileResponse(page)
    return HTMLResponse("<h1>Workspace</h1><p>frontend/workspace.html 없음</p>")


@app.get("/admin/graph", response_class=HTMLResponse, include_in_schema=False)
async def serve_admin_graph():
    """v0.2 Axis 3 — 3D reasoning-graph observability page.

    The HTML itself is public (the user is gated client-side by a login
    flow before any API call); the data endpoint /admin/graph/snapshot
    is admin-only via _require_admin().
    """
    page = os.path.join(FRONTEND_DIR, "graph.html")
    if os.path.exists(page):
        return FileResponse(page)
    return HTMLResponse("<h1>Reasoning Graph</h1><p>frontend/graph.html 없음</p>")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(WIKI_DIR,   exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)

rag_engine     = RAGEngine(default_role="external")
file_processor = FileProcessor()
# bearer_scheme moved to routes/_helpers.py (single source of truth for
# Depends(bearer_scheme) across server + extracted routers).

# Register singletons with routes/_deps so extracted routers can fetch them
# via get_rag_engine() / get_file_processor() / get_rate_limiter().
# Must precede any app.include_router() call below.
set_rag_engine(rag_engine)
set_file_processor(file_processor)
set_rate_limiter(_rate_limiter)

# v0.4.x server-split PR-A.1 — auth/upload/admin-user-mgmt routes
# moved to routes/auth.py. include_router AFTER set_* singletons.
from routes.auth import router as auth_router
app.include_router(auth_router)

# v0.4.x server-split PR-B — LLM/Ollama routes moved to routes/llm.py.
from routes.llm import router as llm_router
# Back-compat re-exports for tests that scan server_llmwiki via srv.<name>:
from routes.llm import (  # noqa: F401
    _allowed_install_models,
    _install_progress,
    _model_catalog,
    _start_install_with_progress,
    llm_active,
)
app.include_router(llm_router)

# v0.4.x server-split PR-C — workspace jobs + scheduler routes.
from routes.jobs import router as jobs_router
app.include_router(jobs_router)

# v0.4.x server-split PR-D — W7-A data artifact + upload-history routes.
from routes.artifacts import router as artifacts_router
app.include_router(artifacts_router)

# v0.4.x server-split PR-E — Phase 7 self-evolution + learn + patch.
from routes.evolution import router as evolution_router
app.include_router(evolution_router)

# v0.4.x server-split PR-F — coding agent routes.
from routes.coding import router as coding_router
app.include_router(coding_router)

# v0.4.x server-split PR-G — remaining /admin/* routes.
from routes.admin import router as admin_router
# Back-compat re-exports for tests that access via srv.<name>:
from routes.admin import (  # noqa: F401
    _AUDIT_CATEGORIES,
    _file_mgmt_roots,
    _resolve_under_root,
    _truncate_audit_blob,
)
app.include_router(admin_router)



@app.on_event("startup")
async def on_startup():
    """서버 시작 시 자동 실행."""
    import asyncio

    # [PR-C5b 2026-05-23] Plugin pack loader — JAMES_PACKS env-driven.
    # Reads packs/general/ (and any operator-listed packs) at startup,
    # validates each manifest, and populates core/plugins/registry. In
    # v0.3 the registry is populated but not yet *consumed* — consumer
    # wiring lands in PR-C5c when core/reasoning/modes/ +
    # core/retrieval/ start reading the registered Protocol instances.
    # Therefore STEP 7 results are byte-identical at this point (the
    # registry exists but no code path reads from it).
    #
    # Failure semantics: ``PluginLoadError`` and ``PluginVersionError``
    # are intentionally propagated and will halt server startup, per the
    # design memo's "no silent fallback" contract. An operator who has
    # broken JAMES_PACKS (typo'd pack name, corrupt manifest, SemVer
    # mismatch) sees the failure at startup, not 30 minutes later when
    # the first query lands. See docs/PLUGIN_AUTHORING.md §5.
    try:
        from core.plugins.loader import load_packs_from_env
        from core.plugins.registry import get_registry
        manifests = load_packs_from_env()
        counts = get_registry().slot_counts()
        pack_list = ", ".join(f"{m.name} v{m.version}" for m in manifests)
        print(
            f"[PLUGINS] loaded {len(manifests)} pack(s): {pack_list} — "
            f"slots: ontology={counts['ontology']}, prompts={counts['prompts']}, "
            f"ui={counts['ui']}, scorers={counts['scorers']}"
        )
    except ImportError as _import_exc:
        # Defensive only — core.plugins lands in v0.3. An ImportError
        # here means the package is missing entirely (likely a partial
        # checkout); print and continue so the rest of startup proceeds.
        print(f"[PLUGINS] skipped — package not importable: {_import_exc}")

    # #81 phase 3-C: prune trace files older than the retention window
    # so reports/trace/ doesn't grow unbounded over weeks of usage.
    # One-shot per process restart — operators wanting more frequent
    # housekeeping run a cron / scheduled task. Default 7 days; env
    # override clamped to [1, 365].
    try:
        from core.observability import prune_old_traces
        keep = int(os.environ.get("JAMES_TRACE_RETENTION_DAYS", "7"))
        result = prune_old_traces(keep_days=keep)
        if result["removed_days"]:
            print(f"[OBSERVABILITY] trace prune: removed {len(result['removed_days'])} day-dir(s) "
                  f"older than {keep}d ({', '.join(result['removed_days'])})")
        if result["errors"]:
            print(f"[OBSERVABILITY] trace prune errors: {result['errors']}")
    except Exception as e:
        # Housekeeping must never block server startup.
        print(f"[STARTUP] trace prune skipped: {e}")

    # [W7-A 2026-05-11] Backfill data_artifacts for any pre-W7 files
    # already sitting in uploads/. Idempotent — only inserts rows that
    # don't already have an origin_path match with uploaded_by='legacy'.
    # Fail-safe: any error is logged and skipped, never blocks startup.
    try:
        from core.data_artifacts import backfill_from_uploads_dir
        n = backfill_from_uploads_dir(UPLOAD_DIR)
        if n > 0:
            print(f"[DATA] backfilled {n} legacy artifact row(s) from {UPLOAD_DIR}")
    except Exception as e:
        print(f"[STARTUP] data-artifact backfill skipped: {e}")

    # [W8-D 2026-05-11] Background scheduler — re-fires scheduled
    # jobs (``every:N`` / ``hourly`` / ``daily:HH:MM`` /
    # ``weekly:DOW:HH:MM``) and sweeps stale workspace/results/ dirs
    # once a day. Daemon thread; per-tick errors are logged, never
    # propagate. Disabled via ``JAMES_DISABLE_SCHEDULER=1`` for
    # one-shot CLI / test harness setups.
    if os.environ.get("JAMES_DISABLE_SCHEDULER", "0") != "1":
        try:
            from core.scheduler import default_scheduler
            default_scheduler.start()
            print(f"[SCHED] background scheduler started "
                  f"(poll={default_scheduler.poll_interval_sec}s, "
                  f"retention={default_scheduler.retention_days}d)")
        except Exception as e:
            print(f"[STARTUP] scheduler start skipped: {e}")

    # [PR plan-3, 2026-05-09] LLM readiness check + friendly install
    # guidance. If Ollama has 0 models, every /query/ would fail. We
    # emit a clear console banner pointing operators to the admin
    # first-run wizard so they don't waste time debugging "[Gemma 응답
    # 없음]" mysteries. Resolver gracefully degrades — no crash, just
    # a clear next-step.
    try:
        from core.model_resolver import resolution_snapshot
        snap = resolution_snapshot()
        installed = snap.get("installed", [])
        if not installed:
            chat_warn = snap.get("chat", {}).get("warning", "")
            print("=" * 60)
            print("[STARTUP] ⚠️  Ollama에 설치된 모델이 0개입니다.")
            print("[STARTUP]   → /query/ 호출 시 실패하거나 RuntimeError 발생.")
            print("[STARTUP]   → 다음 중 하나로 모델을 설치하세요:")
            print("[STARTUP]      a) admin 페이지(/admin) 접속 → 자동 추천 wizard")
            print("[STARTUP]      b) 터미널에서: ollama pull gemma3:4b")
            if chat_warn:
                print(f"[STARTUP]   resolver 메시지: {chat_warn}")
            print("=" * 60)
        else:
            chat_tag = snap.get("chat", {}).get("tag", "")
            chat_src = snap.get("chat", {}).get("source", "")
            print(f"[STARTUP] LLM 준비됨 — chat 모델: {chat_tag} (source: {chat_src}, "
                  f"설치된 모델 {len(installed)}개)")
    except Exception as e:
        print(f"[STARTUP] LLM readiness check skipped: {e}")

    async def _index():
        await asyncio.sleep(3)
        try:
            from tools.self.file_scanner import (
                scan_project, build_wiki_content,
                save_to_wiki, index_to_vector
            )
            result  = scan_project(force=False)
            changed = result["changed"]
            if not changed:
                print(f"[SCANNER] 변경 없음 (총 {result['total']}개)")
                return
            print(f"[SCANNER] 변경 감지: {len(changed)}개")
            content = build_wiki_content(result)
            save_to_wiki(content)
            # ★ 서버의 vector_store 직접 전달
            chunks = index_to_vector(
                content,
                vector_store=rag_engine.vector_store
            )
            print(f"[SCANNER] ✅ 자기 인식 완료 ({chunks} chunks)")
        except Exception as e:
            print(f"[STARTUP] 자기 인식 실패: {e}")

    asyncio.create_task(_index())

# ─── 인증 헬퍼 ───────────────────────────────────────────────
# verify_api_key, resolve_api_key_principal, get_role_from_request,
# get_client_ip — moved to routes/_helpers.py (v0.4.x server-split PR-A,
# single source of truth across server + extracted routers). Re-imported
# at top of this module for back-compat with handlers still inline here.

# ─── Pydantic 모델 ───────────────────────────────────────────



# W4 P1-B — self-service signup.


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


class StatusResponse(BaseModel):
    status:            str
    upload_dir:        str
    wiki_dir:          str
    chroma_dir:        str
    indexed_documents: int
    version:           str

# ─── 미들웨어: Rate Limiting ─────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """[P4-SRV-1] Rate Limiting 미들웨어"""
    ip = get_client_ip(request)
    endpoint = request.url.path

    # 체크 필요한 엔드포인트만. /signup/ + /password/reset/confirm 도
    # unauthenticated 표적이라 같은 IP-window 로 brute-force 차단.
    if endpoint in ("/query/", "/upload/", "/login/", "/signup/",
                    "/password/reset/confirm"):
        if not _rate_limiter.check(ip, endpoint):
            remaining = _rate_limiter.remaining(ip)
            _write_audit(
                user_role="unknown", endpoint=endpoint,
                security_event=f"rate_limit_exceeded ip={ip}",
                ip_address=ip,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"요청 한도 초과. {_rate_limiter.window_sec}초 후 재시도하세요.",
                    "remaining": remaining,
                },
                headers={"Retry-After": str(_rate_limiter.window_sec)},
            )

    response = await call_next(request)
    return response

# ─── API ─────────────────────────────────────────────────────



# W4 P1-B — self-service signup. Creates a pending (active=0,
# role=external) row. An admin must approve and assign a role before
# the account can log in. The endpoint never reveals whether a username
# already exists: success and duplicate share one response body and
# both return 200. Only policy violations get a distinct 400.





@app.post("/query/", response_model=QueryResponse, summary="질의응답 (권한 기반)")
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

    question   = data.question.strip()
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


@app.get("/status/", response_model=StatusResponse, summary="서버 상태")
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








# ─── Issue #15: per-task model selection persistence ───────────











@app.get("/hardware/", summary="PC 하드웨어 정보 조회 [P3-1]")
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


@app.get("/history/", summary="대화 히스토리 조회 [P7]")
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


@app.get("/history/sessions/", summary="세션 목록 조회 [P7]")
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


@app.post("/history/sessions/rename/", summary="세션 이름 변경 [3-D]")
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


@app.delete("/history/", summary="대화 히스토리 삭제 [P7]")
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


@app.post("/history/summarize/", summary="세션 요약 저장 [P7]")
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


@app.get("/history/long-term/", summary="장기 기억 조회 [P7]")
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


# ── Phase 7: 자기진화 API ──────────────────────────────────────

















# ── P7-EVO-B + P8-EVAL-1 + P8-LEARN-1 API ─────────────────────













# ── P7-EVO-C: 피드백 API ────────────────────────────────────────

class FeedbackRequest(BaseModel):
    api_key:      str
    direction_id: str
    signal:       str
    query:        str = ""

@app.post("/feedback/", summary="피드백 전송 [P7-EVO-C]")
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

@app.get("/feedback/stats/", summary="피드백 통계 [P7-EVO-C]")
async def get_feedback_stats_api(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from core.feedback_engine import get_feedback_stats
        return get_feedback_stats()
    except Exception as e:
        return {"error": str(e)}



# ── P7-EVO-D: 성향 캐릭터 API ───────────────────────────────────





# [P1 unified UX, 2026-05-10] correlation graph + damping factor.
# Frontend renders this as edges between trait vertices on the radar
# chart and uses damping for ripple-animation magnitude — the same
# value the backend applies in set_trait, so the visual matches the
# saved data exactly.



# ── P7-EVO-E: 능력 성장 API ─────────────────────────────────────




# ── P7-VIS-1 / P7-VID-1: 멀티모달 분석 API ─────────────────────

@app.post("/analyze/image/", summary="이미지 분석 [P7-VIS-1]")
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


@app.post("/analyze/video/", summary="영상 분석 [P7-VID-1]")
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



# ── P7-SCR-1: Screen Agent API ──────────────────────────────────

class ScreenRequest(BaseModel):
    api_key:  str
    question: str = ""
    region:   Optional[list] = None   # [x, y, w, h]

@app.post("/screen/analyze/", summary="화면 분석 [P7-SCR-1]")
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


@app.get("/")
async def root():
    return {
        "message":  "PROJECT JAMES v4.0 가동 중",
        "features": ["JWT Auth","Graph-RAG","ABAC+RBAC","Ontology",
                     "Output Filter","Rate Limiting","Audit DB","Instruction Isolation",
                     "Coding Agent (Phase 5.5)"],
        "docs":     "http://127.0.0.1:8000/docs",
    }

# ─── Phase 5.5: 코딩 에이전트 엔드포인트 ──────────────────────














# ── Phase 7: Admin API ──────────────────────────────────────────────────────
# _require_admin, _require_feature — moved to routes/_helpers.py (v0.4.x
# server-split PR-A). Re-imported at top.






# W4 P2-A — admin approves a pending signup (active=0 → active=1 + role).
# api_key arrives as a query param to match the frontend `api()` helper,
# which auto-appends ?api_key=... to every admin call. Body holds only
# the operation-specific fields.



# W4 P2-A — admin rejects a pending signup (DELETE the row).



# W4 P2-A — admin deactivates an active user (active=1 → active=0).



# ─── W4 P2-B: password change + reset-token workflow ────────────
# _bearer_username — moved to routes/_helpers.py (v0.4.x server-split PR-A).











# ─── W4 P3-1: user API keys (issue / list / revoke) ─────────────



















# ─── /admin/graph/relation — Phase E graph editor (write path) ───
#
# docs/design/v0.3-knowledge-cascade.md §7. admin 이 `/admin/graph`
# 의 edge 별 sources / weight / role 을 직접 수정할 수 있게 하는 3
# endpoint. JAMES_GRAPH_EDIT=1 env flag 가 켜진 경우에만 활성화 —
# 의도치 않은 mutation 방지 (graceful degradation).
# ────────────────────────────────────────────────────────────────



























@app.get("/trace/poll/{trace_id}", summary="실시간 추론 단계 polling [real-reasoning-stream]")
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








@app.post("/export/", summary="답변 문서 export [item #4]")
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




# ─── W4 P6: audit log browser ──────────────────────────────────
# The legacy /admin/dashboard "최근 쿼리 로그" widget filters on
# endpoint='/query/', so every user-management / password / api-key
# event (which all write rows correctly via _write_audit) is
# invisible in the UI. This endpoint exposes the full audit_log with
# a category coarse filter + free-text search so admins can review
# privileged actions without dropping to sqlite3.
#
# Categories map to endpoint prefixes:
#   user_mgmt  →  /admin/users/...
#   password   →  /password/...  + /signup/
#   api_keys   →  /api-keys/...
#   auth       →  /login/
#   query      →  /query/  + /upload/  (user-driven content events)
#   tools      →  tool:...          (Phase 1 — router + tools/code/*)
#   attack     →  attack:...        (Phase 2 — security_layer.log_attack)
#   system     →  system:...        (Phase 2 — 11 *system* log writers)
#   all        →  no endpoint filter



# ─── W7-A: data artifacts (per-upload lifecycle tracking) ──────
# Two surfaces:
#   /admin/artifacts/*  — admin.data feature, sees every user's rows
#   /artifacts/mine/*   — data.view_own feature, scoped to JWT subject









# ─── W8-A: workspace jobs (run / list / detail / download) ─────
# Sync execution — the handlers complete in seconds for typical wiki
# sizes. /jobs/run blocks until the row reaches done/failed. Scheduler
# (cron-driven) is W8-A2; this PR is pure on-demand execution.





# ─── W8-D: schedule a recurring job ────────────────────────────





# ─── W8-D follow-up: unschedule + scheduler status ─────────────













# ── admin-side mirrors (admin.data feature, sees every owner) ──





# ─── W4-Q1: feature capability matrix ──────────────────────────
# Admin-only surface to inspect + adjust the per-role feature gate
# (core/feature_registry.py + PolicyEngine.can_use_feature).
# Q2 wires the runtime checks into existing endpoints; Q3 ships
# the admin matrix UI. Q1 stands up only the management surface.









# ────────────────────────────────────────────────────────────────────
# [#2 file management tab, 2026-05-09] /admin/files/* endpoints —
# unified file inspection (tree + search + download). Upload + history
# are kept on existing endpoints (/upload/, /admin/uploads/history/).
#
# Trust boundary: ALL three endpoints are admin-gated AND constrain
# every path argument to a fixed allowlist of root directories. The
# allowlist is the *only* thing standing between an arbitrary client
# string and `open(path)` — path traversal would expose .env, secret
# DBs, anything on the operator's filesystem.
# ────────────────────────────────────────────────────────────────────

# Roots the file-mgmt tab is allowed to inspect. Each entry maps a
# user-facing key to an absolute path; client requests reference the
# key, the server resolves the path. New roots must be added here
# explicitly — rejecting unknown root keys is part of the trust gate.

# Filename allowlist for downloads. We never expose source code, env
# files, secret DBs, etc. — even if path traversal were somehow bypassed,
# this extension gate is a second line of defense.






























# ─── Cognitive feature toggles (UI-IA risk signal #5 fix) ────────
#
# Six cognitive-layer features (reflect / verify / fact_check /
# planner / query_rewrite / rerank) ship live in the backend but
# had no admin UI before this endpoint pair. `core/feature_flags.py`
# is the single source of truth for the env-var ↔ semantic mapping;
# both endpoints delegate to it.
#
# Persistence model: in-process env mutation only, mirroring the
# existing `/admin/settings` POST that already does
# `os.environ["JAMES_PROTECTED_FILES"] = ...`. A container restart
# re-reads the boot `.env`, so durable changes are still an
# operator concern. Surfacing this in the UI (a "session-only"
# banner) is PR-2 frontend work.








# ─── PR-CR-B2: Change Request endpoints ─────────────────────────
#
# Six endpoints back the v0.2.x Change Request primitive
# (docs/handovers/v0.2.x-cr-track.md, docs/ARCHITECTURE.md §5.6).
#
# Auth model is mixed by design:
#   - propose / list / detail / review:  any authenticated user.
#   - approve / reject:                  admin only.
# The JWT subject claim is the source of identity at every write —
# request bodies do not carry ``proposer`` / ``approver`` fields,
# so a client holding only a body can't self-impersonate.



























if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_llmwiki:app", host="127.0.0.1", port=8000, reload=True)
