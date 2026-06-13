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
import sqlite3
import time
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import BASE_DIR, UPLOAD_DIR, WIKI_DIR, CHROMA_DIR
from core.graph_rag_engine import RAGEngine
from processors.file_processor import FileProcessor

# Server-split scaffolding (v0.4.x cycle, PR-A) — auth/audit helpers
# moved to routes/_helpers.py. Re-imported here so handlers still inline
# in this module continue to use the same names. routes/<domain>.py
# modules import from routes/_helpers directly. See
# docs/design/v0.4.x-server-split.md.
from routes._helpers import (
    _AUDIT_DB,
    _write_audit,
    get_client_ip,
    # Back-compat re-exports for tests that access these via srv.<name>
    # — server itself no longer uses them after PR-H route extraction.
    bearer_scheme,            # noqa: F401  test_api_key_middleware
    get_role_from_request,    # noqa: F401  test_api_key_middleware (inspect.getsource)
    resolve_api_key_principal,  # noqa: F401  test_api_key_middleware
    verify_api_key,           # noqa: F401  test_api_key_middleware
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

# Rate limiter — operator-safe defaults (30/60s, ~0.5 req/s) for
# production single-operator workflow. Env overrides exist for
# benchmark loops (matrix runner sets MAX=10000 to effectively
# disable; per α-6 Phase 2 rate-limit corruption post-mortem #671).
_RATE_LIMIT_MAX = int(os.environ.get("JAMES_RATE_LIMIT_MAX", "30"))
_RATE_LIMIT_WINDOW_SEC = int(os.environ.get("JAMES_RATE_LIMIT_WINDOW_SEC", "60"))
_rate_limiter = RateLimiter(max_requests=_RATE_LIMIT_MAX,
                            window_sec=_RATE_LIMIT_WINDOW_SEC)

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


# v0.5 — enterprise security headers (CSP report-only by default +
# X-Frame-Options / X-Content-Type-Options / Referrer-Policy /
# Permissions-Policy). HSTS opt-in via env. See
# `core/security/headers.py` for the env-driven config table and
# `docs/reviews/v0.5-ui-6-inline-style-audit.md` §4 for the CSP
# graduation path.
from core.security.headers import build_security_headers  # noqa: E402
from core.security.csp_nonce import (  # noqa: E402
    csp_use_nonce_for_scripts,
    csp_use_nonce_for_styles,
    new_nonce,
)
# v0.6 Phase 1 P1.2 — trusted forwarded-headers middleware. MUST be
# added BEFORE `security_headers_middleware` (which uses request
# state) and BEFORE `rate_limit_middleware` (which calls
# `get_client_ip`). FastAPI middleware execution order is LIFO of
# registration (the LAST added runs FIRST on the inbound path), so
# the explicit `add_middleware` call below appears AFTER the two
# `@app.middleware("http")` decorators in source order — which is
# correct: the class-based middleware ends up outermost (runs first
# inbound, last outbound), overlaying the trusted forwarded headers
# onto `request.scope` before any downstream middleware sees the
# client IP or scheme. See `core/security/forwarded.py` for the env
# config (`JAMES_TRUSTED_PROXIES`).
from core.security.forwarded import (  # noqa: E402
    TrustedForwardedHeadersMiddleware,
)
# v0.6 Phase 3 P3.1 — per-request tenant resolution from a signed
# `X-Tenant-Id` header. Default-off (no secret configured) → no-op
# pass-through; preserves single-tenant v0.5 behaviour byte-identical.
# Operator config: see `docs/deployment/v0.6-saas-tenant-isolation.md`.
from core.security.tenant_request import (  # noqa: E402
    TenantHeaderMiddleware,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Apply enterprise security headers to every response.

    Headers are computed once per request via
    `core.security.headers.build_security_headers()` (which reads
    env config). The middleware does NOT overwrite headers that
    earlier middleware / route handlers have already set — this
    keeps the API contract additive (existing /healthz responses
    etc. don't see Content-Type rewrites).

    v0.6 Track C — per-request CSP nonce: a fresh nonce is minted
    on every request and stashed on ``request.state.csp_nonce`` so
    downstream template renderers can interpolate it into
    ``<style nonce="X">`` / ``<script nonce="X">`` blocks. Whether
    the nonce appears in the CSP directive itself depends on the
    operator-facing env flags
    ``JAMES_CSP_USE_NONCE_SCRIPT`` / ``_STYLE`` — both default off
    so the response headers are byte-identical to pre-v0.6 until
    an operator opts in. See ``core/security/csp_nonce.py`` for
    the readiness rationale (script-src safe today; style-src
    blocked on the UI #6 inline-style migration).
    """
    nonce = new_nonce()
    # Always attach the nonce to request state, even when neither
    # flag is on — costs ~22 bytes per request and makes the
    # template-render path uniform regardless of CSP mode.
    request.state.csp_nonce = nonce

    response = await call_next(request)
    headers = build_security_headers(
        script_nonce=(nonce if csp_use_nonce_for_scripts() else None),
        style_nonce=(nonce if csp_use_nonce_for_styles() else None),
    )
    for name, value in headers.items():
        # `Response.headers` is a MutableHeaders — `setdefault` is
        # the safe primitive (no overwrite if a downstream layer
        # already set the same header).
        if name not in response.headers:
            response.headers[name] = value
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


@app.get("/admin/reasoning-flow", response_class=HTMLResponse, include_in_schema=False)
async def serve_reasoning_flow():
    """v0.6 Phase 4 P4.3 — non-developer reasoning flow visualization.

    3-swimlane horizontal flow viewer (RETRIEVE / EXPAND / VERIFY) for
    audit traces. Reuses the existing `/admin/trace/{trace_id}`
    primitive + the new `/admin/audit/recent-traces` listing endpoint.
    HTML is public; backend endpoints admin-gate.
    """
    page = os.path.join(FRONTEND_DIR, "reasoning-flow.html")
    if os.path.exists(page):
        return FileResponse(page)
    return HTMLResponse(
        "<h1>Reasoning flow</h1><p>frontend/reasoning-flow.html 없음</p>"
    )


@app.get("/admin/knowledge-rollback", response_class=HTMLResponse, include_in_schema=False)
async def serve_knowledge_rollback():
    """v0.6 Phase 4 P4.2 — knowledge rollback affordance.

    Non-developer operator surface for "Undo recent change" / "Restore
    to past moment". HTML is public (no secrets); the backend endpoints
    it calls (`/admin/graph/last-change`, `/admin/graph/diff-vs-now`,
    `/admin/graph/log-rollback-intent`) all admin-gate.
    """
    page = os.path.join(FRONTEND_DIR, "knowledge-rollback.html")
    if os.path.exists(page):
        return FileResponse(page)
    return HTMLResponse(
        "<h1>Knowledge Rollback</h1><p>frontend/knowledge-rollback.html 없음</p>"
    )


@app.get("/onboarding", response_class=HTMLResponse, include_in_schema=False)
async def serve_onboarding():
    """v0.6 Phase 4 P4.1 — operator onboarding 5-step flow.

    Non-developer operator quickstart: welcome / search / audit log /
    change review / time-travel restore. State persistence via
    localStorage (`james_onboarding_completed`); admin page (P4.4)
    exposes a "restart onboarding" link that clears the flag.

    Public route by design — the HTML doesn't carry secrets; the
    downstream pages it points at (`/admin`, `/admin/graph`) gate
    on JWT.
    """
    page = os.path.join(FRONTEND_DIR, "onboarding.html")
    if os.path.exists(page):
        return FileResponse(page)
    return HTMLResponse("<h1>Onboarding</h1><p>frontend/onboarding.html 없음</p>")


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

# v0.4.x server-split PR-H — final extraction:
from routes.query import router as query_router
# Back-compat re-exports for tests that import via server
# (test_a2_phase2 imports QueryRequest, test_force_web_chip/test_web_used_badge
# / test_query_include_contexts use srv.QueryRequest/srv.QueryResponse).
from routes.query import QueryRequest, QueryResponse  # noqa: F401
app.include_router(query_router)

from routes.history import router as history_router
app.include_router(history_router)

from routes.feedback import router as feedback_router
from routes.feedback import FeedbackRequest  # noqa: F401  back-compat
app.include_router(feedback_router)

from routes.multimodal import router as multimodal_router
from routes.multimodal import ScreenRequest  # noqa: F401  back-compat
app.include_router(multimodal_router)

from routes.ops import router as ops_router
from routes.ops import StatusResponse  # noqa: F401  back-compat
app.include_router(ops_router)



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


# v0.6 Phase 1 P1.2 — install the trusted forwarded-headers
# middleware. `add_middleware` registers a class-based middleware
# that wraps the entire app, so it runs FIRST on the inbound
# request (before the `@app.middleware("http")` rate-limit + CSP
# header middlewares above). Default behaviour preserved
# byte-identical: when `JAMES_TRUSTED_PROXIES` is unset the
# middleware is a no-op pass-through.
app.add_middleware(TrustedForwardedHeadersMiddleware)

# v0.6 Phase 3 P3.1 — install the per-request tenant resolution
# middleware. Registered AFTER the forwarded middleware so that
# Starlette's outer-most-LIFO order puts forwarded outside tenant:
# the inbound request flows forwarded → tenant → rest of app, so by
# the time tenant resolution runs, scope["client"] has the true
# end-client IP overlay (though the trust check inside the tenant
# middleware re-validates against the ORIGINAL ASGI peer). Default
# behaviour preserved byte-identical: when `JAMES_TENANT_HEADER_SECRET`
# is unset the middleware is a no-op pass-through.
app.add_middleware(TenantHeaderMiddleware)


# ─── API ─────────────────────────────────────────────────────



# W4 P1-B — self-service signup. Creates a pending (active=0,
# role=external) row. An admin must approve and assign a role before
# the account can log in. The endpoint never reveals whether a username
# already exists: success and duplicate share one response body and
# both return 200. Only policy violations get a distinct 400.















# ─── Issue #15: per-task model selection persistence ───────────

























# ── Phase 7: 자기진화 API ──────────────────────────────────────

















# ── P7-EVO-B + P8-EVAL-1 + P8-LEARN-1 API ─────────────────────













# ── P7-EVO-C: 피드백 API ────────────────────────────────────────






# ── P7-EVO-D: 성향 캐릭터 API ───────────────────────────────────





# [P1 unified UX, 2026-05-10] correlation graph + damping factor.
# Frontend renders this as edges between trait vertices on the radar
# chart and uses damping for ripple-animation magnitude — the same
# value the backend applies in set_trait, so the visual matches the
# saved data exactly.



# ── P7-EVO-E: 능력 성장 API ─────────────────────────────────────




# ── P7-VIS-1 / P7-VID-1: 멀티모달 분석 API ─────────────────────






# ── P7-SCR-1: Screen Agent API ──────────────────────────────────





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
