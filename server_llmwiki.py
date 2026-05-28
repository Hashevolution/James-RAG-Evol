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
import json
from datetime import datetime
from collections import defaultdict
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from config import BASE_DIR, UPLOAD_DIR, WIKI_DIR, CHROMA_DIR, MAX_UPLOAD_BYTES
from core.graph_rag_engine import RAGEngine
from core.feedback_engine import FeedbackEngine
from core.auth import (
    ALLOWED_ROLES,
)
from core.policy_engine import default_engine
from processors.file_processor import FileProcessor

# Server-split scaffolding (v0.4.x cycle, PR-A) — auth/audit helpers
# moved to routes/_helpers.py. Re-imported here so handlers still inline
# in this module continue to use the same names. routes/<domain>.py
# modules import from routes/_helpers directly. See
# docs/design/v0.4.x-server-split.md.
from routes._helpers import (
    _AUDIT_DB,
    _bearer_username,
    _require_admin,
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


@app.get("/admin/web-search-status", summary="웹 검색 엔진 상태 [3-E]")

# ── [4-B] Ollama + LLM 추천 API ──────────────────────────────────

# item #A2: 모드별 선택 가능한 모델 카탈로그.
#   - chat/retrieval/wiki_edit/self_evolve: 일반 대화/추론 (gemma 계열)
#     무게: light (e4b) → medium (12b) → heavy (27b)
#   - coding: 코딩 특화 (qwen-coder 계열) + gemma fallback
# 사용자가 mode 선택 시 두 번째 dropdown으로 후보 중 골라 사용.
# 설치되지 않은 후보는 그대로 노출하되 [⚠️ 미설치] 마커 + 설치 버튼.
# weight 분류는 어림짐작 (실제 파라미터 수가 아닌 *체감* 무게):
#   light  ≤ 4B  — 빠른 일상 대화
#   medium ≤ 13B — 균형, 분석 가능
#   heavy  ≥ 20B — 상세 분석/추론, 응답 느림

# /llm/install/ allowlist auto-derived from catalog so adding a candidate
# above does NOT also require remembering to update the install gate.























# ─── [#A6-1] Web search admin config — role permission + threshold ───

@app.get("/admin/web-search-config/", summary="웹 검색 설정 조회 [#A6-1]")
async def get_web_search_config(api_key: str,
                                 role: str = Depends(get_role_from_request)):
    """[#A6-1] Admin reads:
       - allowed_roles: which roles can trigger web search
       - threshold: unified_score below which web fallback fires
       - engine_status: live key/installed/exhausted state from
                        get_search_engine_status() so the admin UI
                        can render the right toast (TAVILY missing,
                        DDG fallback active, both missing, etc.)
    """
    _require_feature(api_key, role, "admin.settings")
    from core.web_search_config import load
    from tools.web.web_searcher import get_search_engine_status
    cfg = load()
    return {
        **cfg,
        "engine_status": get_search_engine_status(),
    }


class WebSearchConfigUpdate(BaseModel):
    api_key:        str
    allowed_roles:  list
    threshold:      float


@app.post("/admin/web-search-config/", summary="웹 검색 설정 갱신 [#A6-1]")
async def set_web_search_config(data: WebSearchConfigUpdate,
                                 role: str = Depends(get_role_from_request)):
    """Persist web-search settings. Validates role names against
    core.web_search_config.VALID_ROLES and threshold ∈ [0.0, 1.0].
    Empty allowed_roles is rejected — silently disabling web search
    is rarely the intent and harder to debug later (operator can
    clear TAVILY_API_KEY instead if they really want it off)."""
    _require_feature(data.api_key, role, "admin.settings")
    from core.web_search_config import save, validate_update
    clean_roles, clean_threshold, err = validate_update(
        data.allowed_roles, data.threshold,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    cfg = save(clean_roles, clean_threshold)
    _write_audit(role, "/admin/web-search-config/",
                 query=f"roles={clean_roles} threshold={clean_threshold}")
    return {"ok": True, **cfg}


# ─── Issue #15: per-task model selection persistence ───────────









async def web_search_status(api_key: str):
    """현재 활성 검색 엔진 (Tavily / DuckDuckGo) 상태 반환."""
    verify_api_key(api_key)   # api_key 검증만으로 충분 (상태 조회)
    try:
        # .env 파일이 있으면 런타임에 재로드 (환경변수 누락 방지)
        env_path = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and v and k not in os.environ:
                            os.environ[k] = v

        from tools.web.web_searcher import get_search_engine_status
        status = get_search_engine_status()
        status["env_key_set"] = bool(os.environ.get("TAVILY_API_KEY", "").strip())
        return status
    except Exception as e:
        return {
            "active_engine":    "unknown",
            "tavily_key":       bool(os.environ.get("TAVILY_API_KEY", "").strip()),
            "tavily_installed": False,
            "ddg_installed":    False,
            "error":            str(e),
        }


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

@app.get("/admin/performance/metrics/", summary="실시간 성능 지표 [P8-EVAL]")
async def get_perf_metrics(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.metrics")
    try:
        from tools.self.performance_evaluator import get_current_metrics
        from tools.self.importance_scorer import get_scorer_stats
        return {"performance": get_current_metrics(),
                "importance":  get_scorer_stats()}
    except Exception as e:
        return {"error": str(e)}


@app.post("/admin/performance/evaluate/", summary="수동 자기 채점 [P8-EVAL]")
async def manual_evaluate(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.performance_evaluator import run_evaluation
        return run_evaluation()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/performance/history/", summary="평가 이력 [P8-EVAL]")
async def get_perf_history(
    api_key: str, limit: int = 20,
    role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.performance_evaluator import get_eval_history
        return {"history": get_eval_history(limit)}
    except Exception as e:
        return {"history": [], "error": str(e)}








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

@app.get("/admin/character/", summary="성향 조회 [P7-EVO-D]")
async def get_character(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.character")
    try:
        # [P5c 2026-05-10] summary 필드 추가 — 16 trait 자연어 요약
        # (핵심/가치/스타일 3 라인). 프론트는 동일 룰의 JS 미러를 가지므로
        # 이 필드는 chat 등 다른 페이지가 같은 요약을 재사용할 수 있게
        # 노출하는 server-side 단일 소스 역할.
        from core.character_profile import get_profile, CharacterProfile
        profile = get_profile()
        return {
            "traits":  profile.get_with_meta(),
            "summary": CharacterProfile.build_summary(profile.get()),
        }
    except Exception as e:
        return {"traits": [], "error": str(e)}

class TraitUpdateRequest(BaseModel):
    api_key:  str
    trait_id: str
    value:    float

@app.post("/admin/character/", summary="성향 설정 [P7-EVO-D]")
async def set_character(data: TraitUpdateRequest,
                         role: str = Depends(get_role_from_request)):
    _require_feature(data.api_key, role, "admin.character")
    try:
        from core.character_profile import get_profile
        result = get_profile().set_trait(data.trait_id, data.value)
        _write_audit(role, "/admin/character/",
                     query=f"{data.trait_id}={data.value}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# [P1 unified UX, 2026-05-10] correlation graph + damping factor.
# Frontend renders this as edges between trait vertices on the radar
# chart and uses damping for ripple-animation magnitude — the same
# value the backend applies in set_trait, so the visual matches the
# saved data exactly.
@app.get("/admin/character/correlations",
         summary="성향 상관관계 그래프 [P1 unified UX]")
async def get_character_correlations(api_key: str,
                                      role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.character")
    try:
        from core.character_profile import CharacterProfile
        return {
            "correlations": CharacterProfile.get_correlations(),
            "damping":      CharacterProfile.get_damping(),
        }
    except Exception as e:
        return {"correlations": [], "damping": 0.0, "error": str(e)}



# ── P7-EVO-E: 능력 성장 API ─────────────────────────────────────

@app.get("/admin/knowledge/", summary="능력 성장 현황 [P7-EVO-E]")
async def get_knowledge(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.knowledge")
    try:
        from core.knowledge_tracker import get_tracker
        t = get_tracker()
        return {
            "domains":      t.get_domain_levels(),
            "capabilities": t.get_capabilities(),
            "recent_gains": t.get_recent_gains(),
        }
    except Exception as e:
        return {"error": str(e)}



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


@app.post("/code/read/", response_model=CodeResponse, summary="코드 읽기 [P5.5]",
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


@app.post("/code/analyze/", response_model=CodeResponse, summary="코드 분석 [P5.5]",
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


@app.post("/code/edit/", response_model=CodeResponse, summary="코드 수정 [P5.5]",
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


@app.get("/code/surface/", summary="공격 surface 수집 [P5.5]",
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


# ── Phase 7: Admin API ──────────────────────────────────────────────────────
# _require_admin, _require_feature — moved to routes/_helpers.py (v0.4.x
# server-split PR-A). Re-imported at top.


@app.get("/admin/dashboard", summary="관리자 대시보드 [P7]")
async def admin_dashboard(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.metrics")

    # ── 기본 카운트 ──────────────────────────────────────────
    try:    entity_count = len(rag_engine.wiki_generator.entity_id_index)
    except: entity_count = 0
    try:
        from core.auth import list_users
        user_count = len(list_users())
    except: user_count = 0

    # [Phase 4a] tool / attack 스트림 → SQLite audit_log 직접 조회.
    # 이전: james_attack_log.jsonl + james_audit_tool.jsonl 의 tail
    # 200줄을 8KB 청크 역방향 read 로 합쳤음. Phase 1+2 의 mirror 가
    # audit_log 에 tool:* / attack:* prefix 로 동일 데이터를 갖고 있어
    # ORDER BY id DESC LIMIT 200 한 번이면 됨. 인덱스 없는 단일 SELECT
    # 라도 SQLite 가 JSONL 역방향 청크보다 일관되게 빠름.
    security_events, recent_logs = 0, []
    try:
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT timestamp, endpoint, user_role, query, "
            " security_event, blocked "
            "FROM audit_log "
            "WHERE endpoint LIKE 'tool:%' OR endpoint LIKE 'attack:%' "
            "ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()
        for r in rows:
            ev = r["security_event"] or ""
            recent_logs.append({
                "time":    r["timestamp"],
                "event":   ev,
                "role":    r["user_role"],
                "blocked": bool(r["blocked"]),
                "detail":  (r["query"] or "")[:200],
            })
            if r["blocked"] or "BLOCK" in ev:
                security_events += 1
        # Match prior oldest-first ordering for the dashboard widget.
        recent_logs.reverse()
    except Exception:
        # audit_log 읽기 실패 시 dashboard 자체는 계속 동작.
        pass

    try:
        from tools.patch.patch_generator import list_patches
        pending_patches = len(list_patches("PENDING_APPROVAL"))
    except: pending_patches = 0
    try:
        from core.memory import MemoryStore
        stats = MemoryStore().get_stats()
        memory_count = sum(v for v in stats.values() if isinstance(v, int))
    except: memory_count = 0

    # ── [3-A] audit_log 기반 실시간 통계 ────────────────────
    today_queries   = 0
    avg_elapsed     = 0.0
    blocked_count   = 0
    elapsed_list    = []   # 응답 시간 그래프용
    recent_queries  = []   # 최근 쿼리 목록용

    try:
        from datetime import date as _date
        today_str = _date.today().isoformat()
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_log "
            "WHERE endpoint='/query/' "
            "ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()

        for row in rows:
            ts = (row["timestamp"] or "")[:10]
            if ts == today_str:
                today_queries += 1
            if row["elapsed_sec"]:
                elapsed_list.append(round(row["elapsed_sec"], 2))
            if row["blocked"]:
                blocked_count += 1
            if row["query"]:
                recent_queries.append({
                    "q":       (row["query"] or "")[:50],
                    "mode":    "",
                    "elapsed": row["elapsed_sec"],
                    "blocked": bool(row["blocked"]),
                    "ts":      row["timestamp"],
                })

        if elapsed_list:
            avg_elapsed = round(sum(elapsed_list) / len(elapsed_list), 2)
        # 응답 시간 그래프: 최근 20회 (시간순)
        elapsed_chart = list(reversed(elapsed_list[:20]))

    except Exception:
        elapsed_chart = []

    return {
        # 기존
        "entity_count":    entity_count,
        "user_count":      user_count,
        "security_events": security_events + blocked_count,
        "pending_patches": pending_patches,
        "memory_count":    memory_count,
        "diag_score":      100,
        "recent_logs":     recent_logs[-20:],
        # [3-A] 신규 실시간 통계
        "today_queries":   today_queries,
        "avg_elapsed":     avg_elapsed,
        "blocked_count":   blocked_count,
        "elapsed_chart":   elapsed_chart,       # 최근 20회 응답 시간
        "recent_queries":  recent_queries[:10], # 최근 10개 쿼리
        "vector_count":    rag_engine.vector_store.count(),
    }




# W4 P2-A — admin approves a pending signup (active=0 → active=1 + role).
# api_key arrives as a query param to match the frontend `api()` helper,
# which auto-appends ?api_key=... to every admin call. Body holds only
# the operation-specific fields.



# W4 P2-A — admin rejects a pending signup (DELETE the row).



# W4 P2-A — admin deactivates an active user (active=1 → active=0).



# ─── W4 P2-B: password change + reset-token workflow ────────────
# _bearer_username — moved to routes/_helpers.py (v0.4.x server-split PR-A).











# ─── W4 P3-1: user API keys (issue / list / revoke) ─────────────









@app.get("/admin/entities", summary="Entity 현황 — search + paging [item #1]")
async def admin_entities(
    api_key: str,
    q:       str = "",
    etype:   str = "",
    limit:   int = 100,
    offset:  int = 0,
    role:    str = Depends(get_role_from_request),
):
    """Entity inventory list.

    Query params (all optional):
      q       — substring filter on name + entity_id (case-insensitive)
      etype   — exact match on entity_type (e.g. concept / org / person)
      limit   — max rows returned (default 100, hard cap 500)
      offset  — paging offset (default 0)

    `type_counts` is computed over the FULL index (not the filtered slice)
    so the operator always sees corpus-wide totals. `total` is the count
    AFTER filters are applied; `total_all` is the unfiltered count.
    """
    _require_feature(api_key, role, "admin.data")
    from pathlib import Path

    # Clamp limit defensively — 500 covers any realistic v0.2 wiki.
    limit  = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    q_norm = (q or "").strip().lower()
    et_norm = (etype or "").strip().lower()

    entity_index = rag_engine.wiki_generator.entity_id_index
    type_counts: dict[str, int] = {}
    matched: list[dict] = []

    for eid, fpath in entity_index.items():
        try:
            fm = rag_engine.wiki_generator._read_frontmatter(Path(fpath))
            if not fm:
                continue
            etype_v = fm.get("entity_type", fm.get("type", "unknown"))
            type_counts[etype_v] = type_counts.get(etype_v, 0) + 1

            # Apply filters AFTER counting (counts reflect the full corpus).
            if et_norm and etype_v.lower() != et_norm:
                continue
            name = fm.get("name", "") or ""
            if q_norm and q_norm not in name.lower() and q_norm not in eid.lower():
                continue

            matched.append({
                "entity_id":      eid,
                "name":           name,
                "entity_type":    etype_v,
                "sensitivity":    fm.get("sensitivity", "internal"),
                "relation_count": len(fm.get("relations", [])),
            })
        except Exception:
            pass

    # Newest-name-first sort for stable paging UX.
    matched.sort(key=lambda e: (e["name"] or "").lower())
    sliced = matched[offset:offset + limit]

    return {
        "entities":   sliced,
        "type_counts": type_counts,
        "total":      len(matched),         # post-filter count
        "total_all":  len(entity_index),    # corpus-wide
        "limit":      limit,
        "offset":     offset,
        "filters":    {"q": q, "etype": etype},
    }


@app.get("/admin/entities/{entity_id}", summary="Entity 상세 [item #1]")
async def admin_entity_detail(
    entity_id: str,
    api_key:   str,
    role:      str = Depends(get_role_from_request),
):
    """One entity's full frontmatter + body + neighbor names.

    Used by the admin entities page click-to-expand modal so the
    operator can audit a wiki row without leaving the admin UI.
    """
    _require_feature(api_key, role, "admin.data")
    from pathlib import Path

    fpath = rag_engine.wiki_generator.entity_id_index.get(entity_id)
    if not fpath:
        raise HTTPException(status_code=404,
                            detail=f"entity not found: {entity_id}")

    p = Path(fpath)
    if not p.exists():
        raise HTTPException(status_code=404,
                            detail=f"entity file missing on disk: {fpath}")

    fm = rag_engine.wiki_generator._read_frontmatter(p) or {}
    raw = p.read_text(encoding="utf-8", errors="replace")
    # Body = everything after the second `---` frontmatter delimiter.
    parts = raw.split("---", 2)
    body = parts[2].strip() if len(parts) >= 3 else raw

    return {
        "entity_id":   entity_id,
        "name":        fm.get("name", ""),
        "entity_type": fm.get("entity_type", fm.get("type", "unknown")),
        "sensitivity": fm.get("sensitivity", "internal"),
        "frontmatter": fm,
        "relations":   fm.get("relations", []),
        "body":        body[:10000],   # safety cap on rendering
        "path":        str(p),
    }


@app.post("/admin/wiki/resolve-relations",
          summary="Wiki UNRESOLVED relation grand sweep [v0.3 사이클 6]")
async def admin_wiki_resolve_relations(
    api_key:     str,
    source_type: str = "prod",
    role:        str = Depends(get_role_from_request),
):
    """Run WikiGenerator.resolve_pending_relations() across the wiki to
    fill in any leftover ``target_id: UNRESOLVED`` rows in frontmatter
    relations. PR #253 wires the resolver into every ingest path; this
    endpoint exposes the same primitive as a manual grand sweep for
    operators after migrations, bulk imports, or hand edits to wiki
    files that introduce new entities the existing relations could now
    point at. Returns the count of resolved relations (0 if everything
    was already linked).
    """
    _require_feature(api_key, role, "admin.data")

    src = (source_type or "prod").strip().lower()
    if src not in ("prod", "test"):
        src = "prod"

    if src == rag_engine.wiki_generator.source_type:
        gen = rag_engine.wiki_generator
    else:
        from core.wiki_generator import WikiGenerator
        gen = WikiGenerator(source_type=src)

    relations_fixed = gen.resolve_pending_relations()

    return {
        "resolved":    relations_fixed,
        "source_type": src,
    }


@app.get("/admin/graph/snapshot", summary="Reasoning graph snapshot — nodes + edges [v0.2 Axis 3]")
async def admin_graph_snapshot(
    api_key:           str,
    source_type:       str  = "prod",
    include_sensitive: int  = 0,
    role:              str  = Depends(get_role_from_request),
):
    """Read-only enumeration of every wiki entity + ontology edge for
    the /admin/graph 3D visualizer. Admin-only; sensitive nodes/edges
    are dropped by default and require an explicit elevated role to
    surface (which v0.2 doesn't yet have — kept off for now).
    """
    _require_feature(api_key, role, "admin.data")
    from core.graph_snapshot import build_snapshot

    src = (source_type or "prod").strip().lower()
    if src not in ("prod", "test"):
        src = "prod"

    # v0.2: even admin cannot opt into sensitive — locked off until a
    # dedicated elevated role lands. Re-enable here when that role exists.
    include_sens = False
    _ = include_sensitive  # acknowledged but ignored at this gate

    # The shared engine's WikiGenerator is bound to its own source_type
    # at construction, so for cross-source viewing we instantiate a
    # fresh, scoped generator on demand.
    if src == rag_engine.wiki_generator.source_type:
        gen = rag_engine.wiki_generator
    else:
        from core.wiki_generator import WikiGenerator
        gen = WikiGenerator(source_type=src)

    return build_snapshot(
        wiki_generator    = gen,
        source_type       = src,
        include_sensitive = include_sens,
    )


@app.get("/admin/graph/events",
         summary="event 노드 시간 윈도우 조회 [PR-11c]")
async def admin_graph_events_get(
    api_key:         str,
    source_type:     str = "prod",
    occurred_after:  Optional[str] = None,
    occurred_before: Optional[str] = None,
    role:            str = Depends(get_role_from_request),
):
    """admin 만 호출 가능. snapshot 의 event-only 슬라이스 + 선택적
    occurred_at 윈도우 필터.

    Query params:
      - ``occurred_after`` / ``occurred_before`` 둘 다 optional, ISO 8601.
        둘 다 없을 때는 source_type 의 모든 event 반환 (filter 비활성).
      - 둘 중 하나라도 있으면 non-event 는 자동 제거 (memo §5.3).

    Returns: ``{"ok": true, "events": [{node fields...}]}``.
    Order: entity_id 사전순 — caller 가 별도 정렬이 필요하면 그쪽에서.

    400 surfacing 시나리오:
      - occurred_after / occurred_before 가 ISO 8601 파싱 실패
    """
    _require_feature(api_key, role, "admin.data")
    from core.event_time_filter import filter_entities_by_time_bucket
    from core.graph_snapshot import build_snapshot

    src = (source_type or "prod").strip().lower()
    if src not in ("prod", "test"):
        src = "prod"

    if src == rag_engine.wiki_generator.source_type:
        gen = rag_engine.wiki_generator
    else:
        from core.wiki_generator import WikiGenerator
        gen = WikiGenerator(source_type=src)

    snap = build_snapshot(
        wiki_generator=gen, source_type=src, include_sensitive=False,
    )
    # snapshot 의 node 는 `occurred_at` 을 안 싣는다 (visualizer 무관).
    # 본 endpoint 는 entity_id_index 를 직접 재방문해 frontmatter 의
    # occurred_at 까지 끌어와야 한다.
    enriched = []
    for n in snap.get("nodes", []) or []:
        if n.get("type") != "event":
            continue
        eid = n.get("id")
        path = gen.entity_id_index.get(eid)
        if not path:
            continue
        try:
            fm = gen._read_frontmatter(path) or {}
        except Exception:
            fm = {}
        enriched.append({
            **n,
            "occurred_at":           fm.get("occurred_at"),
            "occurred_at_precision": fm.get("occurred_at_precision", "day"),
        })

    try:
        filtered = filter_entities_by_time_bucket(
            enriched,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filtered.sort(key=lambda n: n.get("id", ""))
    return {"ok": True, "events": filtered}


# ─── /admin/graph/relation — Phase E graph editor (write path) ───
#
# docs/design/v0.3-knowledge-cascade.md §7. admin 이 `/admin/graph`
# 의 edge 별 sources / weight / role 을 직접 수정할 수 있게 하는 3
# endpoint. JAMES_GRAPH_EDIT=1 env flag 가 켜진 경우에만 활성화 —
# 의도치 않은 mutation 방지 (graceful degradation).
# ────────────────────────────────────────────────────────────────

def _require_graph_edit_enabled() -> None:
    from core.graph_editor import graph_edit_enabled
    if not graph_edit_enabled():
        raise HTTPException(
            status_code=403,
            detail="graph_edit_disabled: set JAMES_GRAPH_EDIT=1 to enable",
        )


def _truncate_audit_blob(d: dict, cap: int = 500) -> str:
    """audit log 의 query/answer 컬럼은 500 chars cap. sources before/
    after 가 길어질 수 있으므로 JSON dump 후 잘림."""
    s = json.dumps(d, ensure_ascii=False)
    return s if len(s) <= cap else s[:cap - 3] + "..."


@app.get("/admin/graph/relation",
         summary="relation 의 sources 조회 [Knowledge Cascade Phase E]")
async def admin_graph_relation_get(
    api_key:       str,
    src_entity_id: str,
    tgt_entity_id: str,
    relation_type: str,
    role:          str = Depends(get_role_from_request),
):
    """UI 의 edit modal 이 edge 클릭 시 호출. forward 측 relation 의
    sources 배열 + 기본 메타 반환. 없으면 404.
    Snapshot 에 sources 를 안 넣은 이유와 동기: payload 격리."""
    _require_graph_edit_enabled()
    _require_feature(api_key, role, "admin.data")

    from core.graph_editor import read_relation
    try:
        rel = read_relation(
            src_entity_id, tgt_entity_id, relation_type,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if rel is None:
        raise HTTPException(status_code=404, detail="relation not found")
    return {"ok": True, "relation": rel}


@app.put("/admin/graph/relation",
         summary="relation 의 sources 전체 교체 [Knowledge Cascade Phase E]")
async def admin_graph_relation_put(request: Request,
                                   role: str = Depends(get_role_from_request)):
    """forward + inverse 양쪽 relation 의 sources 배열을 body 의 값으로
    교체. confidence 는 자동 derive. relation 이 없으면 새로 생성.

    Body JSON:
      {
        "api_key":       "...",
        "src_entity_id": "e_org_joby",
        "tgt_entity_id": "e_org_nvidia",
        "relation_type": "RELATED_TO",
        "sources": [
          {"doc_id": null, "weight": 0.9, "role": "manual",
           "author": "admin", "note": "..."}
        ]
      }
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    src_id = (body.get("src_entity_id") or "").strip()
    tgt_id = (body.get("tgt_entity_id") or "").strip()
    rtype  = (body.get("relation_type") or "").strip()
    if not (src_id and tgt_id and rtype):
        raise HTTPException(
            status_code=400,
            detail="src_entity_id / tgt_entity_id / relation_type required",
        )
    sources = body.get("sources") or []
    if not isinstance(sources, list) or not sources:
        raise HTTPException(
            status_code=400,
            detail="sources (non-empty list) required — use DELETE to drop",
        )

    from core.graph_editor import replace_relation_sources
    try:
        result = replace_relation_sources(
            src_id, tgt_id, rtype, sources,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _write_audit(
        role, "/admin/graph/relation [PUT]",
        query=_truncate_audit_blob({
            "src": src_id, "tgt": tgt_id, "type": rtype,
        }),
        answer=_truncate_audit_blob({
            "fwd_before_n": len(result["forward"]["before"]),
            "fwd_after_n":  len(result["forward"]["after"]),
            "inv_synced":   result["inverse"] is not None,
        }),
    )
    return {"ok": True, "result": result}


@app.post("/admin/graph/relation/source",
          summary="relation 의 sources 에 한 줄 append [Knowledge Cascade Phase E]")
async def admin_graph_relation_append(request: Request,
                                      role: str = Depends(get_role_from_request)):
    """단일 source 를 forward + inverse 양쪽 relation 의 sources 배열에
    append. 다른 admin 의 PUT 과 commutative — 같은 source 를 두 번
    append 하면 두 row 모두 남는다 (dedup 은 admin 의 일).

    Body JSON:
      {
        "api_key":       "...",
        "src_entity_id": "...",
        "tgt_entity_id": "...",
        "relation_type": "RELATED_TO",
        "source": {"doc_id": null, "weight": 0.7, "role": "manual",
                   "note": "..."}
      }
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    src_id = (body.get("src_entity_id") or "").strip()
    tgt_id = (body.get("tgt_entity_id") or "").strip()
    rtype  = (body.get("relation_type") or "").strip()
    source = body.get("source")
    if not (src_id and tgt_id and rtype and isinstance(source, dict)):
        raise HTTPException(
            status_code=400,
            detail="src_entity_id / tgt_entity_id / relation_type / source required",
        )

    from core.graph_editor import append_relation_source
    try:
        result = append_relation_source(
            src_id, tgt_id, rtype, source,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _write_audit(
        role, "/admin/graph/relation/source [POST]",
        query=_truncate_audit_blob({
            "src": src_id, "tgt": tgt_id, "type": rtype,
            "role": source.get("role"),
        }),
        answer=_truncate_audit_blob({
            "fwd_after_n": len(result["forward"]["after"]),
            "inv_synced": result["inverse"] is not None,
        }),
    )
    return {"ok": True, "result": result}


@app.put("/admin/graph/node",
         summary="node attribute 편집 [cycle 12 PR-O6]")
async def admin_graph_node_put(request: Request,
                               role: str = Depends(get_role_from_request)):
    """admin 만 호출 가능. ``JAMES_GRAPH_EDIT=1`` env opt-in.

    Body JSON::

        {
          "api_key":   "...",
          "entity_id": "e_org_anthropic",
          "patch": {
            "name":        "Anthropic, PBC",
            "entity_type": "org",
            "aliases":     ["앤스로픽", "Anthropic AI"],
            "summary":     "AI safety company...",
            "sensitivity": "normal"
          }
        }

    Allowlisted fields only (NODE_EDITABLE_FIELDS in graph_editor.py).
    ``entity_id`` is immutable and must match the existing row — admin
    cannot repurpose an id by patching it.
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    entity_id = (body.get("entity_id") or "").strip()
    patch     = body.get("patch") or {}
    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id required")
    if not isinstance(patch, dict) or not patch:
        raise HTTPException(status_code=400, detail="patch must be a non-empty dict")

    from core.graph_node_editor import update_node_attributes
    try:
        result = update_node_attributes(
            entity_id, patch,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        msg = str(e)
        # entity_id-not-found vs validation-error: both surface 400 but
        # the not-found case is more naturally 404.
        if msg.startswith("entity_id not found") or msg.startswith("entity file unreadable"):
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    _write_audit(
        role, "/admin/graph/node [PUT]",
        query=_truncate_audit_blob({
            "entity_id":      entity_id,
            "changed_fields": result["changed_fields"],
        }),
        answer=_truncate_audit_blob({
            "path":           result["path"],
            "changed_n":      len(result["changed_fields"]),
        }),
    )
    return {"ok": True, "result": result}


@app.post("/admin/graph/event",
          summary="event 노드 생성 [PR-11a-2 graph evolution]")
async def admin_graph_event_post(request: Request,
                                 role: str = Depends(get_role_from_request)):
    """admin 만 호출 가능. ``JAMES_GRAPH_EDIT=1`` env opt-in.

    PR-11 graph evolution 의 admin 진입점. ingest path 는 여전히
    person/org/concept/document 4 type 만 emit; event 는 본 endpoint
    또는 후속 PR-11d (MemoryLoom date detection) 만 생성한다.

    Body JSON::

        {
          "api_key":               "...",
          "name":                  "2026 비트코인 ETF 승인",
          "occurred_at":           "2026-01-10",
          "occurred_at_precision": "day",          // optional, default "day"
          "aliases":               ["BTC ETF 승인"],  // optional
          "source_doc_id":         "d_sec_filing", // optional → role=manual when omitted
          "source_weight":         1.0             // optional, default 1.0
        }

    Returns::

        {
          "ok":          true,
          "entity_id":   "e_event_a1b2c3d4",
          "path":        "wiki/entity/prod/event/<normalized>.md",
          "frontmatter": { ... }                   // full new-file frontmatter
        }
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    name        = body.get("name")
    occurred_at = body.get("occurred_at")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="name required")
    if not isinstance(occurred_at, str) or not occurred_at.strip():
        raise HTTPException(status_code=400, detail="occurred_at required")

    precision     = body.get("occurred_at_precision", "day")
    aliases       = body.get("aliases")
    source_doc_id = body.get("source_doc_id")
    source_weight = body.get("source_weight", 1.0)

    from core.graph_node_editor import create_event_node
    try:
        result = create_event_node(
            name, occurred_at,
            wiki_generator=rag_engine.wiki_generator,
            occurred_at_precision=precision,
            aliases=aliases,
            source_doc_id=source_doc_id,
            source_weight=source_weight,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _write_audit(
        role, "/admin/graph/event [POST]",
        query=_truncate_audit_blob({
            "name":        name,
            "occurred_at": occurred_at,
            "precision":   precision,
        }),
        answer=_truncate_audit_blob({
            "entity_id":   result["entity_id"],
            "path":        result["path"],
        }),
    )
    return {"ok": True, **result}


@app.delete("/admin/graph/relation",
            summary="relation 자체 제거 [Knowledge Cascade Phase E]")
async def admin_graph_relation_delete(request: Request,
                                      role: str = Depends(get_role_from_request)):
    """forward + inverse 양쪽 relation 을 frontmatter 에서 제거.

    Body JSON:
      {
        "api_key":       "...",
        "src_entity_id": "...",
        "tgt_entity_id": "...",
        "relation_type": "RELATED_TO"
      }
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    src_id = (body.get("src_entity_id") or "").strip()
    tgt_id = (body.get("tgt_entity_id") or "").strip()
    rtype  = (body.get("relation_type") or "").strip()
    if not (src_id and tgt_id and rtype):
        raise HTTPException(
            status_code=400,
            detail="src_entity_id / tgt_entity_id / relation_type required",
        )

    from core.graph_editor import delete_relation
    try:
        result = delete_relation(
            src_id, tgt_id, rtype,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _write_audit(
        role, "/admin/graph/relation [DELETE]",
        query=_truncate_audit_blob({
            "src": src_id, "tgt": tgt_id, "type": rtype,
        }),
        answer=_truncate_audit_blob({
            "fwd_removed": result["forward"]["removed"],
            "inv_removed": result["inverse"]["removed"],
        }),
    )
    return {"ok": True, "result": result}


@app.get("/admin/memory", summary="Memory 현황 [P7]")
async def admin_memory(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.data")
    try:
        from core.memory import MemoryStore
        from core.memory.store import _connect
        stats = MemoryStore().get_stats()
        with _connect() as conn:
            prefs = [dict(r) for r in conn.execute(
                "SELECT key, value, updated_at FROM preferences ORDER BY updated_at DESC LIMIT 20"
            ).fetchall()]
        return {"stats": stats, "preferences": prefs}
    except Exception as e:
        return {"stats": {}, "preferences": [], "error": str(e)}










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


@app.get("/admin/trace/{trace_id}", summary="단일 trace 재생 [#81 phase 3-A]")
async def admin_trace_get(
    trace_id: str,
    api_key:  str,
    day:      str = "",
    role:     str = Depends(get_role_from_request),
):
    """Read back the per-stage JSONL entries for one `trace_id`.

    Path:
      trace_id: uuid7 hex (the value the /query/ response carries
                under `trace_id`).

    Query:
      day: YYYY-MM-DD lookup. Defaults to today. The trace files are
           date-partitioned, so this hint avoids a directory scan.

    Response:
      {"trace_id": "...", "day": "...", "count": N,
       "stages": [{"stage": "auth", "ts_ns": ..., ...}, ...]}

    404 when no trace file exists for the (trace_id, day) pair.
    Stages are returned in the order they were written (chronological).
    """
    _require_feature(api_key, role, "admin.metrics")
    from core.observability import read_trace
    # Normalize the day arg: empty/whitespace → today (read_trace default).
    day_arg = (day or "").strip() or None
    stages = read_trace(trace_id, day=day_arg)
    if not stages:
        raise HTTPException(
            status_code=404,
            detail=f"trace not found: trace_id={trace_id} day={day_arg or 'today'}",
        )
    from datetime import datetime
    return {
        "trace_id": trace_id,
        "day":      day_arg or datetime.now().strftime("%Y-%m-%d"),
        "count":    len(stages),
        "stages":   stages,
    }


@app.get("/admin/episodic/{session_id}",
         summary="Cognitive Phase 3 PR-9b — 세션의 episodic events 조회")
async def admin_episodic_get(
    session_id: str,
    api_key:    str,
    limit:      int = 50,
    stage:      str = "",
    role:       str = Depends(get_role_from_request),
):
    """Session-scoped reasoning trail dump for debugging.

    Returns the most recent episodic events for one session. Each
    event = one cognitive-stage decision (plan / reflect / verify /
    synth) with its summary, score, and trace_id back-link.

    Path:
      session_id: the session whose trail to dump.

    Query:
      limit: 1..200, default 50.
      stage: optional comma-separated filter
             (e.g. ``stage=plan,verify``).

    Response:
      {"session_id": "...", "count": N,
       "events": [{"event_id", "turn_id", "ts", "stage", "summary",
                   "score", "extras", "trace_id"}, ...]}

    Permission: admin.metrics (same as /admin/trace/* — both are
    debugging surfaces over the reasoning audit data).
    """
    _require_feature(api_key, role, "admin.metrics")
    limit = max(1, min(int(limit or 50), 200))
    stages_filter: tuple = ()
    if stage and stage.strip():
        stages_filter = tuple(
            s.strip() for s in stage.split(",") if s.strip()
        )

    try:
        from core.memory.episodic import get_episodic_memory
        events = get_episodic_memory().recent_events(
            session_id, limit=limit, stages=stages_filter,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"episodic store unavailable: {type(e).__name__}",
        )

    return {
        "session_id": session_id,
        "count":      len(events),
        "events":     [
            {
                "event_id":  ev.event_id,
                "turn_id":   ev.turn_id,
                "ts":        ev.ts,
                "stage":     ev.stage,
                "summary":   ev.summary,
                "score":     ev.score,
                "extras":    ev.extras,
                "trace_id":  ev.trace_id,
            }
            for ev in events
        ],
    }


@app.get("/admin/metrics", summary="Per-stage 레이턴시 히스토그램 [#81 phase 3-B]")
async def admin_metrics_get(
    api_key:      str,
    window_hours: int  = 24,
    stage:        str  = "",
    role:         str  = Depends(get_role_from_request),
):
    """Per-stage latency stats over recent traces.

    Walks `reports/trace/` for the window and computes per-stage
    p50/p90/p99/max + sample count from consecutive `ts_ns` deltas.

    Query:
      window_hours: lookback window (default 24, clamped to [1, 168]).
      stage:        optional single-stage filter (e.g. `retrieve`).

    Response:
      {"window_hours": N, "stage_filter": "...",
       "stages": {"retrieve": {count, p50_ms, p90_ms, p99_ms, max_ms},
                  "graph":    {...}, ...}}

    See `core/trace_metrics.py::aggregate_metrics` for the latency
    derivation rationale (per-trace ts_ns deltas vs explicit fields).
    """
    _require_feature(api_key, role, "admin.metrics")
    from core.trace_metrics import aggregate_metrics
    stage_filter = (stage or "").strip() or None
    stats = aggregate_metrics(window_hours=window_hours,
                              stage_filter=stage_filter)
    return {
        "window_hours": max(1, min(int(window_hours or 24), 168)),
        "stage_filter": stage_filter or "",
        "stages":       stats,
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
_AUDIT_CATEGORIES = {
    "user_mgmt": ("/admin/users/",),
    "password":  ("/password/", "/signup/"),
    "api_keys":  ("/api-keys/",),
    "auth":      ("/login/",),
    "query":     ("/query/", "/upload/"),
    "tools":     ("tool:",),
    "attack":    ("attack:",),
    "system":    ("system:",),
}

@app.get("/admin/audit/list", summary="감사 로그 조회 (W4 P6)")
async def admin_audit_list(
    api_key:  str,
    category: str = "all",
    q:        str = "",
    limit:    int = 100,
    offset:   int = 0,
    role:     str = Depends(get_role_from_request),
):
    """Read audit_log rows with category + free-text filter.

    Query params:
      category — "user_mgmt" | "password" | "api_keys" | "auth" |
                 "query" | "all" (default). Unknown values collapse
                 to "all" to avoid a 400 on a UI typo.
      q        — substring on (query OR security_event), case-insensitive
                 via LIKE.
      limit    — hard cap 500, default 100.
      offset   — default 0.

    Response shape (per row): id, timestamp, endpoint, user_role,
    ip_address, query (= filename for /upload/, username for
    /signup/ etc.), security_event, blocked.

    Admin-gated. The audit_log table has no per-row ACL — anyone with
    admin can see every row, including security_event strings that
    may carry sensitive context (rejected passwords are NOT logged
    verbatim by _write_audit; only the rule name surfaces).
    """
    _require_feature(api_key, role, "admin.audit_log")
    limit  = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    qstr   = (q or "").strip()
    cat    = category if category in _AUDIT_CATEGORIES else "all"

    where_parts: list = []
    params:      list = []
    if cat != "all":
        prefixes = _AUDIT_CATEGORIES[cat]
        # one LIKE per prefix joined with OR — the table is small enough
        # (audit_log is the only event surface) that a UNION is overkill.
        where_parts.append(
            "(" + " OR ".join("endpoint LIKE ?" for _ in prefixes) + ")"
        )
        params.extend(p + "%" for p in prefixes)
    if qstr:
        where_parts.append(
            "(query LIKE ? OR security_event LIKE ?)"
        )
        like = f"%{qstr}%"
        params.extend([like, like])

    where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    items: list = []
    total: int  = 0
    try:
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        total = int(conn.execute(
            f"SELECT COUNT(*) AS c FROM audit_log{where}", params,
        ).fetchone()["c"])
        rows = conn.execute(
            f"SELECT id, timestamp, endpoint, user_role, ip_address, "
            f"query, security_event, blocked FROM audit_log{where} "
            f"ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        for r in rows:
            items.append({
                "id":             r["id"],
                "timestamp":      r["timestamp"],
                "endpoint":       r["endpoint"],
                "user_role":      r["user_role"],
                "ip_address":     r["ip_address"],
                "query":          (r["query"] or "")[:120],
                "security_event": r["security_event"] or "",
                "blocked":        bool(r["blocked"]),
            })
        conn.close()
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e),
                "category": cat, "q": qstr,
                "limit": limit, "offset": offset}

    return {"items": items, "total": total,
            "category": cat, "q": qstr,
            "limit": limit, "offset": offset}


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

@app.get("/admin/features/list", summary="권한 매트릭스 조회 (W4-Q1)")
async def admin_features_list(
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """Catalog + currently-effective allowed set per role.

    Response shape:
      {
        "roles":    ["admin", "manager", "employee", "external"],
        "features": [ {id, description, default_allowed, effective}, ... ]
      }

    The ``effective`` map per feature is keyed by role and carries
    ``{allowed, source}`` where ``source ∈ {"default","override"}``
    so the UI can render override rows distinctly.
    """
    _require_feature(api_key, role, "admin.policy_matrix")
    from core.feature_registry import list_effective
    return {
        "roles":    sorted(ALLOWED_ROLES),
        "features": list_effective(),
    }


class FeatureOverrideRequest(BaseModel):
    feature_id: str
    role:       str
    allowed:    bool

@app.post("/admin/features/override",
          summary="권한 매트릭스 override 설정 (W4-Q1)")
async def admin_features_override(
    data:    FeatureOverrideRequest,
    request: Request,
    api_key: str = "",
    role:    str = Depends(get_role_from_request),
):
    """Set one (feature_id, role) override.

    Validation lives inside ``set_override`` — unknown feature_id or
    role returns False, surfaced here as 400. Idempotent: re-setting
    the same value just updates the timestamp + updated_by.
    """
    _require_feature(api_key, role, "admin.policy_matrix")
    from core.feature_registry import set_override

    # Read caller username from the JWT subject for audit-log
    # attribution. Optional — if missing (DEV_MODE / X-Role), we
    # still write the row but updated_by is None.
    try:
        from core.auth import verify_token
        caller = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            caller = (verify_token(auth_header[7:].strip()) or {}).get("sub")
    except Exception:
        caller = None

    ok = set_override(data.feature_id, data.role, data.allowed,
                      updated_by=caller)
    ip = get_client_ip(request)
    if not ok:
        _write_audit(role, "/admin/features/override",
                     query=f"{data.feature_id}/{data.role}",
                     security_event="override_failed (unknown feature or role)",
                     ip_address=ip)
        raise HTTPException(
            status_code=400,
            detail="알 수 없는 feature_id 또는 role 입니다.",
        )
    _write_audit(role, "/admin/features/override",
                 query=f"{data.feature_id}/{data.role}",
                 security_event=f"override_set allowed={data.allowed}",
                 ip_address=ip)
    return {"ok": True, "feature_id": data.feature_id,
            "role": data.role, "allowed": data.allowed}


class FeatureResetRequest(BaseModel):
    feature_id: str
    # role 이 명시되면 그 한 행만 reset, 비어있으면 feature 전체 reset
    role:       Optional[str] = None

@app.post("/admin/features/reset",
          summary="권한 매트릭스 override 제거 → 기본값 복원 (W4-Q1)")
async def admin_features_reset(
    data:    FeatureResetRequest,
    request: Request,
    api_key: str = "",
    role:    str = Depends(get_role_from_request),
):
    """Remove overrides for a feature.

    Two modes:
      - role specified  → delete that single override row.
      - role omitted/empty → delete every override for the feature
                              (full reset to default).

    Returns the number of rows actually deleted, so the UI can show
    "0개 reset" when the feature already used the defaults.
    """
    _require_feature(api_key, role, "admin.policy_matrix")
    from core.feature_registry import clear_override, clear_all_overrides_for

    ip = get_client_ip(request)
    if data.role:
        deleted = 1 if clear_override(data.feature_id, data.role) else 0
        scope_label = f"{data.feature_id}/{data.role}"
    else:
        deleted = clear_all_overrides_for(data.feature_id)
        scope_label = data.feature_id
    _write_audit(role, "/admin/features/reset",
                 query=scope_label,
                 security_event=f"override_cleared count={deleted}",
                 ip_address=ip)
    return {"ok": True, "deleted": deleted, "scope": scope_label}


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
def _file_mgmt_roots() -> dict:
    from config import BASE_DIR, WIKI_DIR, UPLOAD_DIR
    media = os.path.join(BASE_DIR, "media")
    return {
        "wiki":    os.path.abspath(WIKI_DIR),
        "uploads": os.path.abspath(UPLOAD_DIR),
        "media":   os.path.abspath(media),
    }

# Filename allowlist for downloads. We never expose source code, env
# files, secret DBs, etc. — even if path traversal were somehow bypassed,
# this extension gate is a second line of defense.
_FILE_DOWNLOAD_ALLOWED_EXTS = (
    ".md", ".txt", ".pdf", ".docx", ".doc", ".xlsx", ".xls",
    ".pptx", ".ppt", ".csv", ".html", ".htm", ".json", ".yaml", ".yml",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff",
    ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".mp3", ".wav", ".m4a", ".aac", ".flac",
    ".hwpx", ".hwp",
)


def _resolve_under_root(root_key: str, rel_path: str) -> str:
    """Validate (root_key, rel_path) → safe absolute path.

    Returns the absolute path or raises HTTPException 400 on:
      - unknown root_key
      - rel_path that escapes the root (.. traversal, drive letters,
        UNC paths, symlinks pointing outside)

    `os.path.realpath` follows symlinks, so a malicious symlink under
    the root that points to /etc/passwd is caught.
    """
    roots = _file_mgmt_roots()
    if root_key not in roots:
        raise HTTPException(status_code=400, detail="invalid root")
    root = roots[root_key]
    if not os.path.isdir(root):
        # Not yet created (e.g. media/) — return root anyway, callers
        # will produce empty listings.
        return root if not (rel_path or "").strip() else None
    rel = (rel_path or "").lstrip("/\\").strip()
    candidate = os.path.realpath(os.path.join(root, rel))
    # Final containment check.
    if not candidate.startswith(root + os.sep) and candidate != root:
        raise HTTPException(status_code=400, detail="path escapes root")
    return candidate


@app.get("/admin/files/tree", summary="파일 트리 조회 [item #2]")
async def admin_files_tree(
    api_key:    str,
    root:       str = "wiki",
    path:       str = "",
    max_depth:  int = 3,
    role:       str = Depends(get_role_from_request),
):
    """Read-only directory listing rooted at one of the allowed roots.

    `max_depth` clamped to [1, 5] — a 5-level recursive listing on a
    big wiki could be slow and produce a fat JSON, but we don't need
    deeper. `1` lists immediate children only.
    """
    _require_feature(api_key, role, "admin.data")
    max_depth = max(1, min(int(max_depth or 3), 5))
    base = _resolve_under_root(root, path)
    if not base or not os.path.isdir(base):
        return {"root": root, "path": path, "children": [],
                "exists": False}

    def walk(dir_abs: str, depth: int) -> list:
        try:
            entries = sorted(os.listdir(dir_abs))
        except OSError:
            return []
        out = []
        for name in entries:
            if name.startswith("."):       # hide dotfiles (.git, .env shadows)
                continue
            full = os.path.join(dir_abs, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            if os.path.isdir(full):
                node = {
                    "name":     name,
                    "type":     "dir",
                    "mtime":    int(st.st_mtime),
                    "children": walk(full, depth - 1) if depth > 1 else [],
                }
            else:
                node = {
                    "name":  name,
                    "type":  "file",
                    "size":  st.st_size,
                    "mtime": int(st.st_mtime),
                }
            out.append(node)
        return out

    return {
        "root":     root,
        "path":     path,
        "exists":   True,
        "children": walk(base, max_depth),
    }


@app.get("/admin/files/search", summary="파일명 검색 [item #2]")
async def admin_files_search(
    api_key: str,
    q:       str,
    root:    str = "wiki",
    limit:   int = 100,
    role:    str = Depends(get_role_from_request),
):
    """Filename substring search under one root. Case-insensitive.

    Returns a flat list (not nested). Capped at `limit` matches (default
    100, max 500) so a one-character query doesn't dump the whole tree.
    """
    _require_feature(api_key, role, "admin.data")
    qstr  = (q or "").strip().lower()
    if not qstr:
        return {"q": "", "matches": [], "total": 0, "root": root}
    limit = max(1, min(int(limit or 100), 500))
    base  = _resolve_under_root(root, "")
    if not base or not os.path.isdir(base):
        return {"q": qstr, "matches": [], "total": 0, "root": root}

    matches = []
    for dirpath, dirnames, filenames in os.walk(base):
        # Skip hidden dirs.
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            if qstr in name.lower():
                full = os.path.join(dirpath, name)
                rel  = os.path.relpath(full, base).replace("\\", "/")
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                matches.append({
                    "name":  name,
                    "path":  rel,
                    "size":  st.st_size,
                    "mtime": int(st.st_mtime),
                })
                if len(matches) >= limit:
                    return {"q": qstr, "matches": matches,
                            "total": len(matches), "truncated": True,
                            "root": root}
    return {"q": qstr, "matches": matches, "total": len(matches),
            "root": root}


_FILE_VIEW_TEXT_EXTS = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv",
    ".jsonl", ".log", ".tsv",
})


@app.get("/admin/files/view", summary="파일 인라인 보기 [item #2-view]")
async def admin_files_view(
    api_key: str,
    root:    str,
    path:    str,
    max_kb:  int = 256,
    role:    str = Depends(get_role_from_request),
):
    """Read-only inline view of a text file under an allowed root.

    Sibling to ``/admin/files/download`` but tuned for the admin-side
    file management modal: returns ``{name, size, ext, content}`` JSON
    suitable for rendering in a ``<pre>`` block. The same ``admin.data``
    feature gate applies — this endpoint is intended to be called from
    the in-page JavaScript (Authorization header automatically attached
    by ``fetch()``), unlike the download path which is a new-tab
    ``<a href>`` click and therefore loses the JWT header.

    Defenses (in order):

    1. ``admin.data`` feature gate (api_key + role).
    2. ``_resolve_under_root`` rejects unknown root + path traversal.
    3. Extension allowlist: text-only (``.md / .txt / .json / .yaml /
       .yml / .csv / .jsonl / .log / .tsv``). Binary / source-code
       extensions refused with 415 — operator should use download.
    4. ``max_kb`` cap (default 256, max 1024) — accidentally opening
       a multi-MB file in a modal would lock the browser.

    Audit log records every view.
    """
    _require_feature(api_key, role, "admin.data")
    if not (path or "").strip():
        raise HTTPException(status_code=400, detail="path required")
    full = _resolve_under_root(root, path)
    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")
    ext = os.path.splitext(full)[1].lower()
    if ext not in _FILE_VIEW_TEXT_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"extension {ext} not viewable inline; use download",
        )
    max_kb = max(1, min(int(max_kb or 256), 1024))
    try:
        size = os.path.getsize(full)
    except OSError:
        raise HTTPException(status_code=404, detail="stat failed")
    if size > max_kb * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"file {size} bytes exceeds max_kb={max_kb}; use download",
        )
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"read failed: {e}")
    _write_audit(role, "/admin/files/view/",
                 query=os.path.basename(full), elapsed_sec=0)
    return {
        "root":    root,
        "path":    path,
        "name":    os.path.basename(full),
        "size":    size,
        "ext":     ext,
        "content": content,
    }


@app.get("/admin/files/download", summary="파일 다운로드 [item #2]")
async def admin_files_download(
    api_key: str,
    root:    str,
    path:    str,
    role:    str = Depends(get_role_from_request),
):
    """Download a single file from an allowed root.

    Defenses (in order):
      1. admin gate (api_key + role)
      2. _resolve_under_root rejects unknown root + path traversal
      3. extension allowlist (no .py / .env / .db / etc.)
      4. file must exist + be a regular file (not dir, not symlink to
         outside — realpath already followed in step 2)

    Uses FileResponse — FastAPI streams the file, doesn't load it into
    memory. Audit log records every download.
    """
    _require_feature(api_key, role, "admin.data")
    if not (path or "").strip():
        raise HTTPException(status_code=400, detail="path required")
    full = _resolve_under_root(root, path)
    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")
    ext = os.path.splitext(full)[1].lower()
    if ext not in _FILE_DOWNLOAD_ALLOWED_EXTS:
        raise HTTPException(
            status_code=403,
            detail=f"extension {ext} not allowed for download",
        )
    _write_audit(role, "/admin/files/download/",
                 query=os.path.basename(full), elapsed_sec=0)
    from fastapi.responses import FileResponse
    return FileResponse(
        path=full,
        filename=os.path.basename(full),
        media_type="application/octet-stream",
    )


@app.delete("/admin/files",
            summary="업로드 파일 + 파생 cascade 삭제 [Knowledge Cascade Phase C]")
async def admin_files_delete(
    api_key: str,
    path:    str,
    role:    str = Depends(get_role_from_request),
):
    """uploads/ 의 파일 하나를 삭제하고 그로부터 파생된 모든 wiki entity /
    relation source / vector chunks 까지 cascade.

    docs/design/v0.3-knowledge-cascade.md §5 — Phase C.

    Trust boundary:
      - admin.data feature gate
      - root='uploads' 로 hard-coded (wiki/ entity 의 직접 삭제는
        기존 chat 의 ``delete_entity`` 가 처리 — 다른 cascade 의미)
      - ``_resolve_under_root`` 가 path traversal 차단
      - 파일은 ``uploads/.deleted/{ts}_{name}`` 으로 backup, 즉시 purge
        하지 않음 (N 일 후 운영 cleanup 의 일)
    """
    _require_feature(api_key, role, "admin.data")
    if not (path or "").strip():
        raise HTTPException(status_code=400, detail="path required")

    # 'uploads' root 하에서만 동작 — wiki 의 entity 직접 삭제는 다른 경로.
    full = _resolve_under_root("uploads", path)
    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")

    physical_filename = os.path.basename(full)

    from core.cascade import cascade_delete_upload
    try:
        summary = cascade_delete_upload(
            physical_filename,
            wiki_generator = rag_engine.wiki_generator,
            vector_store   = rag_engine.vector_store,
            upload_dir     = _file_mgmt_roots()["uploads"],
            user_role      = role,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 결과 + audit. cascade 결과의 핵심 숫자만 JSON 으로 압축해 answer
    # 컬럼에 저장 (max 500 chars). 자세한 summary 는 응답 본문에 그대로.
    counts = summary.get("counts", {})
    audit_blob = json.dumps({
        "doc_entity_id":           summary.get("doc_entity_id"),
        "orphan_entities_deleted": summary.get("orphan_entities_deleted"),
        "relations_recomputed":    counts.get("relations_recomputed"),
        "relations_dropped":       counts.get("relations_dropped"),
        "vector_deleted":          summary.get("vector_deleted"),
        "file_backup":             summary.get("file_backup"),
    }, ensure_ascii=False)
    _write_audit(
        role, "/admin/files/delete",
        query=physical_filename,
        answer=audit_blob,
        elapsed_sec=0,
    )
    return {"ok": True, "summary": summary}


@app.put("/admin/files",
         summary="업로드 파일 내용 교체 + 파생 cascade 갱신 [Knowledge Cascade Phase D]")
async def admin_files_modify(
    request:     Request,
    file:        UploadFile = File(...),
    api_key:     str        = Form(...),
    path:        str        = Form(...),
    role:        str        = Depends(get_role_from_request),
):
    """`uploads/` 의 기존 파일을 새 multipart file 로 교체하고 파생
    cascade 를 재실행.

    docs/design/v0.3-knowledge-cascade.md §6 — Phase D.

    Trust boundary:
      - admin.data feature gate
      - root='uploads' hard-coded, `_resolve_under_root` 가 path traversal 차단
      - 새 content 도 PolicyEngine sanitize_for_ingestion 통과
      - 옛 파일은 `uploads/.deleted/{ts}_{name}` 으로 backup
    """
    _require_feature(api_key, role, "admin.data")
    if not (path or "").strip():
        raise HTTPException(status_code=400, detail="path required")

    full = _resolve_under_root("uploads", path)
    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")

    physical_filename = os.path.basename(full)

    # 새 파일을 메모리에 모은 뒤 cascade 에 넘긴다. 동일한 size cap.
    new_bytes = b""
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        new_bytes += chunk
        if len(new_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="파일 크기 초과")

    # PolicyEngine sanitize — content extraction (텍스트 파일 / OCR 등은
    # 추후 follow-up. 이번 PR 은 텍스트 직접 교체 경로). file_processor 가
    # 일관된 entry point.
    # NOTE: process_file expects a path; 임시 파일에 dump 후 처리.
    import tempfile
    suffix = os.path.splitext(file.filename or physical_filename)[1] or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(new_bytes)
        tmp_path = tf.name
    try:
        tc = file_processor.process_file(tmp_path, file.filename or physical_filename)
        raw_content, _decision = default_engine.sanitize_for_ingestion(
            tc, source=file.filename or physical_filename,
        )
        new_meta = file_processor.generate_file_metadata(raw_content)
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass

    from core.cascade import cascade_modify_doc
    from utils.tokenizer import split_chunks
    try:
        summary = cascade_modify_doc(
            physical_filename,
            raw_content,
            wiki_generator = rag_engine.wiki_generator,
            vector_store   = rag_engine.vector_store,
            upload_dir     = _file_mgmt_roots()["uploads"],
            new_metadata   = new_meta,
            user_role      = role,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # cascade_modify_doc 가 vector 의 add 는 하지 않으므로 (signature
    # 의존 회피), 여기서 새 chunks 를 다시 넣는다.
    try:
        new_chunks = split_chunks(raw_content)
        rag_engine.vector_store.add_documents_with_meta(
            texts=new_chunks,
            source=summary["original_filename"],
            metadata={
                "sensitivity": new_meta.get("sensitivity", "internal"),
                "owner":       new_meta.get("owner", "system"),
                "category":    new_meta.get("category", "기타"),
                "source_type": "prod",
            },
        )
    except Exception as e:
        print(f"[FILES_PUT] vector re-add fail: {e}")

    cc = summary.get("cascade_counts", {})
    audit_blob = json.dumps({
        "doc_entity_id":           summary.get("doc_entity_id"),
        "sidecar_present":         summary.get("sidecar_present"),
        "diff":                    summary.get("diff"),
        "orphan_entities_deleted": summary.get("orphan_entities_deleted"),
        "relations_dropped":       cc.get("relations_dropped"),
        "file_backup":             summary.get("file_backup"),
    }, ensure_ascii=False)
    _write_audit(
        role, "/admin/files [PUT]",
        query=physical_filename,
        answer=audit_blob,
        elapsed_sec=0,
    )
    return {"ok": True, "summary": summary}


@app.get("/admin/settings", summary="설정 조회 [P7]")
async def admin_settings_get(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.settings")
    from config import GEMMA_MODEL
    try:
        from core.memory import MemoryStore
        persona = MemoryStore().get_persona()
    except Exception:
        persona = {}
    return {"model": GEMMA_MODEL, "max_loop": 2,
            "protected": os.environ.get("JAMES_PROTECTED_FILES",""),
            "persona": persona}


@app.get("/admin/persona", summary="Persona 조회 [P7]")
async def admin_persona_get(api_key: str, role: str = Depends(get_role_from_request)):
    verify_api_key(api_key)   # api_key만 검증 (role 무관)
    try:
        from core.memory import MemoryStore
        return {"persona": MemoryStore().get_persona()}
    except Exception as e:
        return {"persona": {}, "error": str(e)}


class PersonaRequest(BaseModel):
    api_key:  str
    name:     str = ""
    style:    str = ""
    language: str = ""
    custom:   str = ""


@app.post("/admin/persona", summary="Persona 설정 [P7]")
async def admin_persona_set(data: PersonaRequest,
                             role: str = Depends(get_role_from_request)):
    verify_api_key(data.api_key)   # api_key만 검증 (role 무관)
    try:
        from core.memory import MemoryStore
        from core.memory.store import _connect
        # persona 테이블 없으면 자동 생성
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS persona (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
        store = MemoryStore()
        saved = {}
        if data.name:     store.set_persona("name",     data.name);     saved["name"]     = data.name
        if data.style:    store.set_persona("style",    data.style);    saved["style"]    = data.style
        if data.language: store.set_persona("language", data.language); saved["language"] = data.language
        if data.custom is not None:
            store.set_persona("custom", data.custom); saved["custom"] = data.custom
        _write_audit(role, "/admin/persona",
                     query=f"name={data.name} style={data.style[:20]}")
        print(f"[PERSONA] 저장 완료: {saved}")
        return {"success": True, "persona": store.get_persona(), "saved": saved}
    except Exception as e:
        print(f"[PERSONA] 저장 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Persona 저장 실패: {e}")


class AdminSettingsRequest(BaseModel):
    api_key:         str
    model:           str = ""
    max_loop:        int = 2
    protected_files: str = ""


@app.post("/admin/settings", summary="설정 변경 [P7]")
async def admin_settings_post(data: AdminSettingsRequest, role: str = Depends(get_role_from_request)):
    _require_feature(data.api_key, role, "admin.settings")
    if data.protected_files:
        os.environ["JAMES_PROTECTED_FILES"] = data.protected_files
    _write_audit(role, "/admin/settings", query=f"model={data.model}")
    return {"success": True, "applied": {"model": data.model, "max_loop": data.max_loop}}


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


@app.get("/admin/settings/cognitive",
         summary="cognitive feature flags 조회 [UI-IA risk #5]")
async def admin_settings_cognitive_get(
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """Read-only snapshot of the six cognitive-layer feature flags.
    See `docs/UI_API_MAPPING.md` §8 risk signal #5 and
    `core/feature_flags.py` for the registry."""
    _require_feature(api_key, role, "admin.settings")
    from core.feature_flags import read_cognitive_flags
    return {"flags": read_cognitive_flags()}


class CognitiveFlagsRequest(BaseModel):
    api_key: str
    flags:   dict = {}   # {flag_key: bool, ...}


@app.post("/admin/settings/cognitive",
          summary="cognitive feature flags 변경 [UI-IA risk #5]")
async def admin_settings_cognitive_post(
    data: CognitiveFlagsRequest,
    role: str = Depends(get_role_from_request),
):
    """Toggle one or more cognitive features. Body shape::

        {"api_key": "...", "flags": {"reflect": true, "verify": false}}

    Returns per-key (before, after) delta for the audit log.
    Persistence is in-process only — a restart reverts to the
    boot `.env` values.
    """
    _require_feature(data.api_key, role, "admin.settings")
    if not isinstance(data.flags, dict) or not data.flags:
        raise HTTPException(
            status_code=400,
            detail="flags must be a non-empty dict {flag_key: bool, ...}",
        )

    from core.feature_flags import apply_cognitive_flags
    try:
        deltas = apply_cognitive_flags(data.flags)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _write_audit(
        role, "/admin/settings/cognitive",
        query=_truncate_audit_blob({
            "changed": [
                {"key": d["key"], "before": d["before"], "after": d["after"]}
                for d in deltas
            ],
        }),
    )
    return {"success": True, "deltas": deltas}


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

from core import change_request as _cr_mod
from core import change_request_apply as _cr_apply


class _CrProposeRequest(BaseModel):
    api_key:       str
    target_type:   str
    target_id:     str
    title:         str
    description:   str = ""
    proposed_diff: dict   # JSON-serialisable; structure is target_type-specific
    base_hash:     str
    labels:        list[str] = []


@app.post("/admin/cr/", summary="Change Request — propose (any auth user)")
async def cr_propose(
    data:    _CrProposeRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    # Any authenticated caller can propose. Identity is the JWT
    # subject — body carries no ``proposer`` field.
    verify_api_key(data.api_key)
    proposer = _bearer_username(request)
    if not proposer:
        raise HTTPException(status_code=401, detail="login required to propose")
    try:
        cr = _cr_mod.create_cr(
            target_type=data.target_type,
            target_id=data.target_id,
            title=data.title,
            description=data.description,
            proposed_diff=data.proposed_diff,
            base_hash=data.base_hash,
            proposer=proposer,
            labels=data.labels,
            role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "cr": _cr_as_dict(cr)}


@app.get("/admin/cr/", summary="Change Request — list (auth user)")
async def cr_list(
    api_key:     str,
    request:     Request,
    status:      Optional[str] = None,
    target_type: Optional[str] = None,
    proposer:    Optional[str] = None,
    limit:       int = 50,
    offset:      int = 0,
    role:        str = Depends(get_role_from_request),
):
    verify_api_key(api_key)
    caller = _bearer_username(request)
    if not caller:
        raise HTTPException(status_code=401, detail="login required")
    # Non-admins see only their own proposals — admin override
    # passes through proposer filter unchanged.
    if role != "admin":
        proposer = caller
    try:
        rows = _cr_mod.list_crs(
            status=status, target_type=target_type,
            proposer=proposer, limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok":    True,
        "items": [_cr_as_dict(cr) for cr in rows],
        "limit": limit, "offset": offset,
    }


@app.get("/admin/cr/{cr_id}", summary="Change Request — detail (auth user)")
async def cr_detail(
    cr_id:   str,
    api_key: str,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    verify_api_key(api_key)
    caller = _bearer_username(request)
    if not caller:
        raise HTTPException(status_code=401, detail="login required")
    cr = _cr_mod.get_cr(cr_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="cr not found")
    # Non-admins can read a CR only if they're the proposer or have
    # left at least one review on it. Admin sees everything.
    if role != "admin" and cr.proposer != caller:
        reviews = _cr_mod.list_reviews(cr_id)
        if not any(rv.reviewer == caller for rv in reviews):
            raise HTTPException(status_code=403,
                detail="cr is not visible to this user")
    return {
        "ok":      True,
        "cr":      _cr_as_dict(cr),
        "reviews": [_review_as_dict(r) for r in _cr_mod.list_reviews(cr_id)],
    }


class _CrApproveRequest(BaseModel):
    api_key: str


@app.post("/admin/cr/{cr_id}/approve",
          summary="Change Request — approve (admin only)")
async def cr_approve(
    cr_id:   str,
    data:    _CrApproveRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    _require_admin(data.api_key, role)
    approver = _bearer_username(request)
    if not approver:
        raise HTTPException(status_code=401,
            detail="admin JWT required to approve")
    try:
        cr = _cr_apply.merge_cr(cr_id, approver=approver, role=role)
    except ValueError as exc:
        # State machine refusals (self-approval, already-merged,
        # not-found) surface as 400.
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        # apply-side failure that doesn't change state.
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "cr": _cr_as_dict(cr)}


class _CrRejectRequest(BaseModel):
    api_key: str
    reason:  str = ""


@app.post("/admin/cr/{cr_id}/reject",
          summary="Change Request — reject (admin only)")
async def cr_reject(
    cr_id:   str,
    data:    _CrRejectRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    _require_admin(data.api_key, role)
    reviewer = _bearer_username(request)
    if not reviewer:
        raise HTTPException(status_code=401,
            detail="admin JWT required to reject")
    try:
        cr = _cr_mod.reject_cr(
            cr_id, reviewer=reviewer, reason=data.reason, role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "cr": _cr_as_dict(cr)}


class _CrReviewRequest(BaseModel):
    api_key:  str
    decision: str            # "approve" / "request_changes" / "comment"
    body:     str = ""


@app.post("/admin/cr/{cr_id}/review",
          summary="Change Request — review/comment (any auth user)")
async def cr_review(
    cr_id:   str,
    data:    _CrReviewRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    verify_api_key(data.api_key)
    reviewer = _bearer_username(request)
    if not reviewer:
        raise HTTPException(status_code=401, detail="login required to review")
    try:
        rv = _cr_mod.add_review(
            cr_id, reviewer=reviewer, decision=data.decision,
            body=data.body, role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "review": _review_as_dict(rv)}


def _cr_as_dict(cr) -> dict:
    """Shape a ChangeRequest dataclass for JSON output. Mirrors the
    table columns 1:1 so the UI can render without remapping."""
    return {
        "cr_id":         cr.cr_id,
        "target_type":   cr.target_type,
        "target_id":     cr.target_id,
        "title":         cr.title,
        "description":   cr.description,
        "proposed_diff": cr.proposed_diff,
        "base_hash":     cr.base_hash,
        "proposer":      cr.proposer,
        "status":        cr.status,
        "labels":        cr.labels,
        "created_at":    cr.created_at,
        "updated_at":    cr.updated_at,
        "merged_at":     cr.merged_at,
        "merged_by":     cr.merged_by,
        "reject_reason": cr.reject_reason,
    }


def _review_as_dict(rv) -> dict:
    return {
        "review_id":  rv.review_id,
        "cr_id":      rv.cr_id,
        "reviewer":   rv.reviewer,
        "decision":   rv.decision,
        "body":       rv.body,
        "created_at": rv.created_at,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_llmwiki:app", host="127.0.0.1", port=8000, reload=True)
