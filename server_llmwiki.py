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
import uuid
import time
import json
from datetime import datetime
from collections import defaultdict
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from config import UPLOAD_DIR, WIKI_DIR, CHROMA_DIR, API_KEY, MAX_UPLOAD_BYTES
from core.graph_rag_engine import RAGEngine
from core.feedback_engine import FeedbackEngine
from core.auth import (
    authenticate, get_role_from_token, ALLOWED_ROLES, DEV_MODE,
    signup as _auth_signup, list_users as _auth_list_users,
    approve_user as _auth_approve_user,
    reject_user as _auth_reject_user,
    deactivate_user as _auth_deactivate_user,
    verify_token as _auth_verify_token,
)
from core.auth_reset import (
    change_password    as _auth_change_password,
    issue_reset_token  as _auth_issue_reset_token,
    consume_reset_token as _auth_consume_reset_token,
    RESET_TOKEN_TTL_SEC,
)
from core.api_keys import (
    issue_api_key  as _api_key_issue,
    revoke_api_key as _api_key_revoke,
    list_api_keys  as _api_key_list,
    verify_api_key as _api_key_verify,
)
from core.policy_engine import default_engine
from processors.file_processor import FileProcessor

try:
    from config import BASE_DIR
    _AUDIT_DB = os.path.join(BASE_DIR, "james_audit.db")
except ImportError:
    _AUDIT_DB = "james_audit.db"

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

def _write_audit(
    user_role: str,
    endpoint:  str,
    query:     str     = "",
    answer:    str     = "",
    graph_paths: list  = None,
    blocked:   bool    = False,
    security_event: str = "",
    elapsed_sec: float = 0.0,
    ip_address: str    = "",
):
    """[P4-SRV-2] 감사 로그 DB 기록 (graph_path 포함)"""
    try:
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.execute(
            """INSERT INTO audit_log
               (timestamp, user_role, endpoint, query, answer, graph_paths,
                blocked, security_event, elapsed_sec, ip_address)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now().isoformat(),
                user_role,
                endpoint,
                query[:500],
                answer[:500],
                json.dumps(graph_paths or [], ensure_ascii=False)[:1000],
                int(blocked),
                security_event[:200],
                round(elapsed_sec, 2),
                ip_address,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[AUDIT] 로그 기록 실패: {e}")

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
bearer_scheme  = HTTPBearer(auto_error=False)


@app.on_event("startup")
async def on_startup():
    """서버 시작 시 자동 실행."""
    import asyncio

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

def verify_api_key(api_key: str):
    """Accept either the system API_KEY or a per-user ``jms_...`` key.

    Raises 403 if neither matches. This function only validates the
    credential; role-based authorization continues to consult
    ``get_role_from_request`` (so a bare system key still gets the
    employee role, and a user key gets the owner's actual role).
    """
    if api_key and api_key.startswith("jms_"):
        if _api_key_verify(api_key) is not None:
            return
    elif api_key == API_KEY:
        return
    raise HTTPException(status_code=403, detail="API Key 오류")


def resolve_api_key_principal(api_key: str) -> Optional[dict]:
    """Non-raising counterpart to ``verify_api_key``.

    Returns ``{"source", "username", "role"}`` or None. Used by
    ``get_role_from_request`` to map a user key to the owner's role
    without raising on miss (the caller decides whether absence is
    an error).
    """
    if not api_key:
        return None
    if api_key.startswith("jms_"):
        out = _api_key_verify(api_key)
        if out is not None:
            return {"source": "user", **out}
        return None
    if api_key == API_KEY:
        # System key intentionally does NOT carry admin authority by
        # itself — pairing it with an admin JWT is still required for
        # admin endpoints. Returning "employee" here keeps the
        # pre-P3-2 behaviour identical for system-only callers.
        return {"source": "system", "username": "system", "role": "employee"}
    return None


def get_role_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_role: Optional[str] = Header(None, alias="X-Role"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """JWT > user API key > X-Role (dev) > default employee.

    [W4 P3-2] User API keys (``jms_...``) now surface the owner's
    role to authorization gates. The system key remains employee
    so a leaked .env value cannot self-elevate to admin.
    """
    if credentials and credentials.credentials:
        role = get_role_from_token(credentials.credentials)
        print(f"[AUTH] JWT role: {role}")
        return role

    # W4 P3-2: X-API-Key header takes precedence over ?api_key= so
    # clients on shared proxies (where logs may capture the URL) can
    # move the credential out of the URL line.
    key = (x_api_key or "").strip() or request.query_params.get("api_key", "")
    if key:
        principal = resolve_api_key_principal(key)
        if principal and principal["source"] == "user":
            print(f"[AUTH] user API key: {principal['username']} (role={principal['role']})")
            return principal["role"]

    if x_role and x_role in ALLOWED_ROLES:
        if DEV_MODE:
            print(f"[AUTH] X-Role 헤더 사용: {x_role} (개발 모드)")
            return x_role

    # [P7-FIX] JWT 없어도 api_key 검증은 엔드포인트에서 수행됨
    # 로컬 전용 시스템: api_key 통과 = 신뢰 사용자 → employee 수준 부여
    return "employee"

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ─── Pydantic 모델 ───────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    api_key:  str = ""   # 선택적

class LoginResponse(BaseModel):
    token:        str   # 기존 필드 유지
    access_token: str   # admin.js 호환용 (동일 값)
    role:         str
    username:     str

# W4 P1-B — self-service signup.
class SignupRequest(BaseModel):
    username: str
    password: str

class SignupResponse(BaseModel):
    ok:      bool
    # Identical message for success and duplicate (enumeration defense).
    # Policy-violation responses populate this with the specific reason
    # and return HTTP 400 instead of 200.
    message: str

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

class UploadResponse(BaseModel):
    status:      str
    filename:    str
    category:    str
    summary:     str
    keywords:    list
    sensitivity: str = "internal"

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

@app.post("/login/", response_model=LoginResponse, summary="로그인 (JWT 발급)")
async def login(data: LoginRequest, request: Request):
    ip     = get_client_ip(request)
    result = authenticate(data.username, data.password)
    if result is None:
        _write_audit("unknown", "/login/", query=data.username,
                     security_event="login_failed", ip_address=ip)
        raise HTTPException(status_code=401, detail="인증 실패: 사용자명 또는 비밀번호 오류")
    _write_audit(result["role"], "/login/", query=data.username, ip_address=ip)
    # access_token 필드 추가 (프론트엔드 호환)
    result["access_token"] = result.get("token", "")
    return result


# W4 P1-B — self-service signup. Creates a pending (active=0,
# role=external) row. An admin must approve and assign a role before
# the account can log in. The endpoint never reveals whether a username
# already exists: success and duplicate share one response body and
# both return 200. Only policy violations get a distinct 400.
_SIGNUP_ACCEPTED_MSG = "가입 요청이 접수되었습니다. 관리자 승인 후 사용 가능합니다."

@app.post("/signup/", response_model=SignupResponse,
          summary="회원가입 신청 (관리자 승인 후 활성화)")
async def signup(data: SignupRequest, request: Request):
    ip     = get_client_ip(request)
    result = _auth_signup(data.username, data.password)

    if result.status == "policy":
        _write_audit(
            "anonymous", "/signup/", query=data.username,
            security_event=f"signup_rejected_policy: {result.error}",
            ip_address=ip,
        )
        # Policy reasons are deliberately public — the rule itself does
        # not leak account existence, only the rule.
        raise HTTPException(status_code=400, detail=result.error)

    if result.status == "duplicate":
        # Audit log distinguishes; the response intentionally does not.
        _write_audit(
            "anonymous", "/signup/", query=data.username,
            security_event="signup_rejected_duplicate", ip_address=ip,
        )
    else:  # "ok"
        _write_audit(
            "anonymous", "/signup/", query=data.username,
            security_event="signup_pending", ip_address=ip,
        )

    return SignupResponse(ok=True, message=_SIGNUP_ACCEPTED_MSG)


@app.post("/upload/", response_model=UploadResponse, summary="파일 업로드 (admin 전용)")
async def upload(
    request:     Request,
    file:        UploadFile = File(...),
    api_key:     str        = Form(...),
    source_type: str        = Form("prod"),
    instruction: str        = Form(""),     # 챗 저장 지시 (선택)
    role:        str        = Depends(get_role_from_request),
):
    # [W4-Q2-c] api_key + role-level feature gate. Default matrix
    # allows upload.file for admin + manager (catalog Q1) — system
    # api_key alone (role=employee) is denied, so a leaked .env value
    # no longer suffices to ingest documents. Operators can override
    # for specific roles via /admin/features/override.
    _require_feature(api_key, role, "upload.file")
    ip = get_client_ip(request)

    # 영상은 ffmpeg → Whisper ASR 으로 처리. 실제 ffmpeg 호출 + 음성
    # 추출 + STT 는 processors/file_processor.py::extract_video. 운영자
    # 환경에 ffmpeg 가 없으면 그쪽에서 명시적 RuntimeError → process_file
    # 의 try/except 가 "[처리 오류]" placeholder 로 변환 → 업로드 자체는
    # 진행 (vector 인덱스에 한 줄 오류 메시지만 들어감, silent failure 아님).

    allowed_ext = (
        ".pdf",".png",".jpg",".jpeg",".bmp",".tiff",".webp",
        ".txt",".md",".csv",".html",".htm",
        ".mp4",".avi",".mov",".mkv",".webm",      # video-asr

        ".docx",".doc",".xlsx",".xls",".pptx",".ppt",
        ".hwpx",".hwp",
        ".mp3",".wav",".m4a",".ogg",
    )
    if not any(file.filename.lower().endswith(ext) for ext in allowed_ext):
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식")

    unique_name = str(uuid.uuid4()) + "_" + file.filename
    filepath    = os.path.join(UPLOAD_DIR, unique_name)
    total_size  = 0

    try:
        with open(filepath, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk: break
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_BYTES:
                    f.close(); os.remove(filepath)
                    raise HTTPException(status_code=413, detail="파일 크기 초과")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(filepath): os.remove(filepath)
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {e}")

    # [W7-A 2026-05-11] Register the artifact as soon as the bytes land
    # on disk. Status moves to 'indexed' after successful processing or
    # 'failed' if any step raises. The JWT subject (preferred) or
    # 'system' (system api_key only) becomes uploaded_by — the latter
    # surfaces in the audit log so a leaked-key upload is still
    # attributable to "the operator".
    from core.data_artifacts import (
        register_artifact as _da_register,
        update_status     as _da_update_status,
    )
    rel_path = os.path.join("uploads", unique_name).replace("\\", "/")
    artifact_uploader = _bearer_username(request) or "system"
    try:
        artifact_id = _da_register(
            origin_path=rel_path,
            origin_name=file.filename,
            origin_size=total_size,
            uploaded_by=artifact_uploader,
            status="uploaded",
        )
    except Exception as _e:
        # Never block the upload on a tracking-row failure.
        print(f"[UPLOAD] data_artifacts register skipped: {_e}")
        artifact_id = None

    try:
        # #44 phase 4-B: process_file 가 TrustedContent 반환.
        # #44 phase 4-C: ingestion 검역은 PolicyEngine 단일 chokepoint
        # (`default_engine.sanitize_for_ingestion`) 로 라우팅. 기존
        # `sanitize_document_content` 는 backwards-compat shim 으로 유지되며
        # 동일한 코드 경로(extract_data_only + log_attack) 를 사용한다.
        tc = file_processor.process_file(filepath, file.filename)
        print(f"[UPLOAD] provenance source={tc.source} trust={tc.trust} "
              f"file={file.filename}")

        # [P4-SRV-5] Instruction Isolation — PolicyEngine ingestion gate
        raw_content, _sanitize_decision = default_engine.sanitize_for_ingestion(
            tc, source=file.filename,
        )

        meta   = file_processor.generate_file_metadata(raw_content)
        from utils.tokenizer import split_chunks
        chunks = split_chunks(raw_content)

        # [P7-FIX] 업로드는 서버 내부 작업
        # Memory Trust는 사용자 쿼리 신뢰도 검증용 — 업로드에 적용 불필요
        # api_key 검증(verify_api_key) 통과 = 신뢰된 요청으로 처리

        rag_engine.vector_store.add_documents_with_meta(
            texts=chunks, source=file.filename,
            metadata={
                "sensitivity": meta.get("sensitivity", "internal"),
                "owner":       meta.get("owner", "system"),
                "category":    meta.get("category", "기타"),
                "source_type": "prod",
            },
        )
        # [W8-C 2026-05-11] capture entity_ids so we can write
        # wiki_links rows after the entity files are on disk. The
        # process_document_for_entities return type was unused before;
        # we now consume it to make the artifact ↔ entity relation
        # queryable from /admin/artifacts/<id> + the workspace UI.
        created_entity_ids: list = []
        try:
            created_entity_ids = list(
                rag_engine.wiki_generator.process_document_for_entities(
                    file.filename, raw_content, [],
                    user_role="admin",
                    metadata=meta,
                ) or []
            )
        except TypeError:
            # 구버전 시그니처 fallback (metadata/user_role 미지원)
            try:
                created_entity_ids = list(
                    rag_engine.wiki_generator.process_document_for_entities(
                        file.filename, raw_content, []
                    ) or []
                )
            except AttributeError:
                pass
        except AttributeError:
            # process_document_for_entities 없음 → 문서 entity 직접 생성
            try:
                doc_entity = {
                    "name":        os.path.splitext(file.filename)[0],
                    "type":        "document",
                    "relations":   [],
                    "attributes": {
                        "summary":   meta.get("summary", ""),
                        "category":  meta.get("category", "기타"),
                        "keywords":  ", ".join(meta.get("keywords", [])),
                    },
                    "sensitivity": meta.get("sensitivity", "internal"),
                    "source_type": "prod",
                }
                created_path = rag_engine.wiki_generator.create_entity_file(
                    doc_entity, file.filename, []
                )
                # create_entity_file returns the .md file path.
                # The entity_id matches the stem (no extension).
                if created_path:
                    from pathlib import Path as _PathW8C
                    created_entity_ids.append(_PathW8C(created_path).stem)
            except Exception as wiki_err:
                print(f"[UPLOAD] wiki entity 생성 skip: {wiki_err}")
        except Exception as e:
            print(f"[UPLOAD] entity 처리 skip: {e}")

        # [W8-C 2026-05-11] write wiki_links rows. Best-effort — a
        # failure here does NOT roll back the upload (the bytes are on
        # disk and the vector store / wiki .md files exist). It only
        # means the artifact ↔ entity relation isn't queryable for
        # this upload; subsequent uploads continue to track.
        if artifact_id and created_entity_ids:
            try:
                from core.data_artifacts import link_entity
                for eid in created_entity_ids:
                    if eid:
                        link_entity(artifact_id, eid)
                print(f"[UPLOAD] linked {len(created_entity_ids)} entities "
                      f"to artifact {artifact_id}")
            except Exception as _e:
                print(f"[UPLOAD] link_entity skipped: {_e}")

        # ── [P7] Media Store — 이미지/영상/오디오 날짜별 폴더 보관 ──
        MEDIA_EXTS = {
            ".jpg",".jpeg",".png",".gif",".webp",".bmp",".tiff",
            ".mp4",".avi",".mov",".mkv",".webm",
            ".mp3",".wav",".m4a",".aac",".flac",
        }
        fname_lower = file.filename.lower()
        if any(fname_lower.endswith(ext) for ext in MEDIA_EXTS):
            try:
                from tools.multimodal.media_store import (
                    store_media, store_with_instruction, MEDIA_BASE
                )
                # 절대 경로로 변환 (상대 경로 오류 방지)
                abs_filepath = os.path.abspath(filepath)
                print(f"[UPLOAD] 미디어 저장 시작: {abs_filepath}")
                print(f"[UPLOAD] MEDIA_BASE: {os.path.abspath(MEDIA_BASE)}")

                analysis = {
                    "path":        abs_filepath,
                    "type":        "media_image" if any(
                        fname_lower.endswith(e)
                        for e in [".jpg",".jpeg",".png",".gif",".webp",".bmp"]
                    ) else "media_video",
                    "date":        "",
                    "location":    "",
                    "persons":     [],
                    "tags":        meta.get("keywords", []),
                    "description": meta.get("summary", ""),
                    "analyzed_at": __import__("datetime").datetime.now().isoformat(),
                }
                if instruction.strip():
                    store_result = store_with_instruction(
                        src_path    = abs_filepath,
                        instruction = instruction,
                        analysis    = analysis,
                        source_type = source_type,
                        move        = False,
                    )
                else:
                    store_result = store_media(
                        src_path    = abs_filepath,
                        analysis    = analysis,
                        source_type = source_type,
                        move        = False,
                    )

                if store_result.get("success"):
                    # store_with_instruction → "stored_path"
                    # store_media → "original_path"
                    stored = (store_result.get("stored_path")
                              or store_result.get("original_path",""))
                    print(f"[UPLOAD] ✅ 미디어 보관 완료: {stored}")
                else:
                    err = store_result.get("error","알 수 없는 오류")
                    print(f"[UPLOAD] ❌ 미디어 보관 실패: {err}")
            except Exception as media_err:
                import traceback
                print(f"[UPLOAD] media_store skip: {media_err}")
                print(traceback.format_exc())

        try:
            for f_name in os.listdir(UPLOAD_DIR):
                if f_name.endswith("_" + file.filename) and f_name != unique_name:
                    os.remove(os.path.join(UPLOAD_DIR, f_name))
        except Exception:
            pass

        # [W7-A] mark indexed only after vector + entity steps succeeded.
        if artifact_id:
            try:
                _da_update_status(artifact_id, "indexed")
            except Exception as _e:
                print(f"[UPLOAD] status update skipped: {_e}")

        result_data = {
            "status":      "ok",
            "filename":    unique_name,
            "category":    meta.get("category","기타"),
            "summary":     meta.get("summary",""),
            "keywords":    meta.get("keywords",[]),
            "sensitivity": meta.get("sensitivity","internal"),
            "artifact_id": artifact_id,   # [W7-A]
        }
        _write_audit(role, "/upload/", query=file.filename, ip_address=ip)
        return result_data
    except HTTPException:
        # [W7-A] HTTPException propagation — surface but mark failed
        # so the operator can find it via /admin/artifacts/list.
        if artifact_id:
            try: _da_update_status(artifact_id, "failed")
            except Exception: pass
        raise
    except Exception as e:
        if artifact_id:
            try: _da_update_status(artifact_id, "failed")
            except Exception: pass
        raise HTTPException(status_code=500, detail=f"분석 실패: {e}")


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
def _model_catalog():
    """Mode → ordered list of (tag, weight) candidates.

    [#A2 phase 2] Implementation moved to `core.model_catalog` so the
    reasoning engine can validate `selected_model` without importing
    server_llmwiki (circular dep). Public name kept for back-compat
    with `tests/test_model_catalog_per_mode.py:test_catalog_function_exists`.
    """
    from core.model_catalog import model_catalog
    return model_catalog()

# /llm/install/ allowlist auto-derived from catalog so adding a candidate
# above does NOT also require remembering to update the install gate.
def _allowed_install_models():
    out = set()
    for cands in _model_catalog().values():
        for tag, _ in cands:
            if tag:
                out.add(tag)
    return out


@app.get("/llm/modes/", summary="챗 페이지 모드 picker 옵션 [item #6 + #A2]")
async def llm_modes(api_key: str, role: str = Depends(get_role_from_request)):
    """Mode picker가 채울 옵션 목록 + 모델 후보 카탈로그.

    api_key만 검증 (admin 아님). role-allowed 모드만 반환해서 클라이언트
    가 권한 없는 모드를 보지 않도록 한다.

    각 옵션:
      key:         서버에 보낼 mode_override 값
      label:       사용자 노출 라벨
      desc:        한 줄 설명
      keywords:    자동 추천에 사용 (클라이언트 측 keyword match)
      model:       기본(default) 모델 태그 — backward compat
      installed:   기본 모델 설치 상태 — backward compat
      models:      [item #A2] 후보 리스트 — 두 번째 dropdown용
                   각 원소: {"tag": str, "weight": "light|medium|heavy",
                            "installed": bool, "default": bool}
    """
    verify_api_key(api_key)
    from core.intent_classifier import ROLE_ALLOWED
    from config import GEMMA_MODEL, CODING_MODEL
    allowed = ROLE_ALLOWED.get(role, {"chat", "retrieval"})

    # 설치된 모델 set 한 번에 조회 (Ollama API).
    installed_set = set()
    try:
        import urllib.request
        with urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=2,
        ) as r:
            data = json.loads(r.read())
        for m in data.get("models", []):
            installed_set.add(m.get("name", ""))
    except Exception:
        pass   # Ollama 미실행 — installed=False로 모두 표시됨

    def _mark(model: str) -> bool:
        """Ollama list와 매칭. 정확 일치 OR 태그 prefix (e.g.
        gemma4:e4b ≈ gemma4)."""
        if not model:
            return True   # meta 같이 LLM 안 쓰는 모드는 항상 'installed'
        if model in installed_set:
            return True
        prefix = model.split(":", 1)[0]
        return any(name.startswith(prefix + ":") or name == prefix
                   for name in installed_set)

    catalog = _model_catalog()

    def _models_for(mode_key: str, default_tag: str) -> list:
        """Build the candidate list dict for a mode."""
        cands = catalog.get(mode_key, [])
        out = []
        for tag, weight in cands:
            out.append({
                "tag":       tag,
                "weight":    weight,
                "installed": _mark(tag),
                "default":   tag == default_tag,
            })
        return out

    options = [
        {"key": "auto",     "label": "🤖 자동",
         "desc": "질문 의도를 자동 분류 (기본)",
         "keywords": [],
         "model": "", "installed": True, "models": []},
        {"key": "chat",     "label": "💬 일상 대화",
         "desc": "검색 없이 LLM 직답",
         "keywords": ["안녕", "고마워", "hi", "hello"],
         "model": GEMMA_MODEL, "installed": _mark(GEMMA_MODEL),
         "models": _models_for("chat", GEMMA_MODEL)},
        {"key": "retrieval","label": "🔍 자료 검색",
         "desc": "내부 wiki + 그래프 추론",
         "keywords": ["뭐야", "무엇", "설명", "알려줘", "what is"],
         "model": GEMMA_MODEL, "installed": _mark(GEMMA_MODEL),
         "models": _models_for("retrieval", GEMMA_MODEL)},
        {"key": "meta",     "label": "📚 자료 목록",
         "desc": "보유 wiki 인벤토리 (LLM 미사용)",
         "keywords": ["목록", "리스트", "어떤 자료", "list"],
         "model": "", "installed": True, "models": []},
        {"key": "coding",   "label": "💻 코딩",
         "desc": "코딩 특화 모델",
         "keywords": ["코드", "함수", "버그", "python", "def ",
                      "javascript", "code", "function"],
         "model": CODING_MODEL, "installed": _mark(CODING_MODEL),
         "models": _models_for("coding", CODING_MODEL)},
        {"key": "wiki_edit","label": "✏️ Wiki 편집 (admin)",
         "desc": "지식 추가/수정/삭제",
         "keywords": ["수정해", "추가해", "삭제해"],
         "model": GEMMA_MODEL, "installed": _mark(GEMMA_MODEL),
         "models": _models_for("wiki_edit", GEMMA_MODEL)},
        {"key": "self_evolve","label": "🧬 자기진화 (admin)",
         "desc": "코드 분석 / 자기 개선",
         "keywords": ["네 코드", "구조 분석", "스스로"],
         "model": GEMMA_MODEL, "installed": _mark(GEMMA_MODEL),
         "models": _models_for("self_evolve", GEMMA_MODEL)},
    ]
    # auto는 항상 허용. 나머지는 role 권한 확인.
    filtered = [o for o in options if o["key"] == "auto" or o["key"] in allowed]
    return {"modes": filtered, "role": role}


# [#A8-8] In-memory install progress tracker. Keyed by model tag.
# Populated by the background thread that streams Ollama's pull API.
# Frontend polls /admin/llm/install-progress?model=... every 2s.
# Survives single server lifetime — restart wipes (operator can re-pull
# if needed; partial Ollama downloads resume on retry).
_install_progress: dict = {}   # model -> {status, percent, completed, total, error}
_install_lock     = None       # set lazily — threading import deferred


def _start_install_with_progress(model: str) -> None:
    """Background thread: stream Ollama's POST /api/pull and write
    progress to _install_progress[model]. Ollama returns NDJSON like:
        {"status": "pulling manifest"}
        {"status": "downloading", "digest": "...", "total": N, "completed": N}
        {"status": "verifying sha256"}
        {"status": "success"}
    We compute percent = completed / total when both fields present.
    """
    import threading, urllib.request, json as _json
    global _install_lock
    if _install_lock is None:
        _install_lock = threading.Lock()

    def _runner():
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/pull",
                data=_json.dumps({"name": model, "stream": True}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3600) as r:
                for raw in r:   # NDJSON line stream
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    try:
                        evt = _json.loads(line)
                    except Exception:
                        continue
                    status    = evt.get("status", "")
                    completed = evt.get("completed")
                    total     = evt.get("total")
                    percent   = None
                    if isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
                        percent = round((completed / total) * 100, 1)
                    with _install_lock:
                        _install_progress[model] = {
                            "status":    status,
                            "completed": completed,
                            "total":     total,
                            "percent":   percent,
                            "error":     "",
                            "done":      status == "success",
                        }
                    if status == "success":
                        # [PR plan-1] resolver cache invalidation so
                        # the freshly-installed model is selectable
                        # immediately on the next /query/ without
                        # waiting 60s TTL.
                        try:
                            from core.model_resolver import invalidate_cache
                            invalidate_cache()
                        except Exception:
                            pass
                        break
        except Exception as e:
            with _install_lock:
                _install_progress[model] = {
                    "status":    "error",
                    "completed": None,
                    "total":     None,
                    "percent":   None,
                    "error":     f"{type(e).__name__}: {e}",
                    "done":      True,
                }

    t = threading.Thread(target=_runner, daemon=True, name=f"ollama-pull-{model}")
    t.start()


@app.post("/llm/install/", summary="Ollama 모델 설치 (admin) [item #6 + #A8-8]")
async def llm_install(api_key: str, model: str,
                      role: str = Depends(get_role_from_request)):
    """Trigger `ollama pull <model>` via Ollama's HTTP streaming API
    in a background thread. Returns immediately so the admin page can
    show a progress bar while the multi-GB download runs.

    Admin-gated. Model name validated against catalog allowlist.

    [#A8-8 2026-05-09] Replaced subprocess.Popen with HTTP streaming —
    the CLI fire-and-forget had no progress visibility. Now the
    background thread parses Ollama's NDJSON pull stream and writes
    {percent, completed, total, status} to _install_progress[model],
    which the admin UI polls.
    """
    _require_feature(api_key, role, "admin.settings")
    ALLOWED_MODELS = _allowed_install_models() | {"llava:13b"}
    if model not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=400,
            detail="model not in allowlist. Use admin /admin/llm/install for arbitrary models.",
        )
    # Reset any prior progress entry so the polling client gets fresh state.
    _install_progress[model] = {
        "status":    "starting",
        "completed": None,
        "total":     None,
        "percent":   0.0,
        "error":     "",
        "done":      False,
    }
    try:
        _start_install_with_progress(model)
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="ollama API에 접근할 수 없습니다 (localhost:11434). ollama 서비스가 실행 중인지 확인.",
        )
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"install 시작 실패: {type(e).__name__}: {e}")
    return {"ok": True, "model": model,
            "message": f"{model} 설치 시작됨. 진행 상황은 admin 페이지 또는 "
                       f"GET /admin/llm/install-progress?model={model} 로 확인."}


@app.get("/admin/llm/install-progress", summary="모델 설치 진행률 [item #A8-8]")
async def llm_install_progress(api_key: str, model: str,
                                role: str = Depends(get_role_from_request)):
    """Frontend polls this every 2-3s while the install button is in
    progress mode. Returns the latest snapshot of the background
    thread's progress dict, or {status: 'idle'} if no install is/was
    running for this model.

    Response shape:
      {status, percent, completed, total, done, error, model}
    """
    _require_feature(api_key, role, "admin.settings")
    snap = _install_progress.get(model)
    if not snap:
        return {"model": model, "status": "idle",
                "percent": None, "completed": None, "total": None,
                "done": False, "error": ""}
    return {"model": model, **snap}


@app.get("/admin/llm/installed", summary="설치된 Ollama 모델 목록 [4-B]")
async def llm_installed(api_key: str, role: str = Depends(get_role_from_request)):
    """현재 Ollama에 설치된 모델 목록."""
    _require_feature(api_key, role, "admin.settings")
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            data = _json.loads(r.read())
        models = [
            {
                "name":     m.get("name",""),
                "size_gb":  round(m.get("size",0) / 1e9, 1),
                "modified": m.get("modified_at","")[:10],
            }
            for m in data.get("models", [])
        ]
        return {"ok": True, "models": models, "count": len(models)}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e),
                "hint": "Ollama가 실행 중인지 확인하세요 (ollama serve)"}


@app.get("/admin/llm/resolution",
         summary="현재 모델 resolution 상태 [PR plan-1, 2026-05-09]")
async def llm_resolution(api_key: str, role: str = Depends(get_role_from_request)):
    """[PR plan-1] 운영자 가시성 — call_gemma(model=None)이 어떤 모델을
    실제 사용하는지 + 폴백 사유.

    설치된 모델이 config의 default와 다를 때 어디로 fallback 됐는지
    감지하기 위함. resolver는 silent하게 동작하지만 결정 사유는 여기서
    조회 가능.

    Returned shape:
      {chat: {tag, source, warning, fallback_chain},
       coding: {tag, source, warning, fallback_chain},
       installed: [...],
       preference: {chat: [...], coding: [...]},
       ttl_s: 60}
    """
    _require_feature(api_key, role, "admin.settings")
    from core.model_resolver import resolution_snapshot
    return resolution_snapshot()


@app.get("/admin/llm/recommend", summary="하드웨어 기반 LLM 추천 [4-B]")
async def llm_recommend(api_key: str, role: str = Depends(get_role_from_request)):
    """현재 하드웨어 스펙에 맞는 LLM 모델 추천."""
    _require_feature(api_key, role, "admin.settings")
    try:
        from tools.system.hardware_inspector import get_hardware_specs, get_llm_recommendations
        specs = get_hardware_specs()
        recs  = get_llm_recommendations(specs)
        return {
            "ok":      True,
            "specs_summary": {
                "gpu":    f"{specs['gpu'].get('name','?')} ({specs['gpu'].get('vram_gb',0)}GB VRAM)",
                "ram":    f"{specs['ram'].get('total_gb',0)}GB RAM",
                "level":  specs.get("overall_level", 0),
            },
            "recommendations": recs,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/admin/llm/pull", summary="Ollama 모델 다운로드 [4-B]")
async def llm_pull(
    api_key: str,
    model:   str,
    role: str = Depends(get_role_from_request),
):
    """Ollama 모델 pull (다운로드). 시간이 걸릴 수 있음."""
    _require_feature(api_key, role, "admin.settings")
    if not model or len(model) > 60:
        raise HTTPException(status_code=400, detail="model명 오류")
    # 보안: 허용 모델만
    from tools.system.hardware_inspector import LLM_CATALOG
    allowed = {m["tag"] for m in LLM_CATALOG}
    if model not in allowed:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 모델: {model}")
    try:
        import urllib.request, json as _json
        body = _json.dumps({"name": model, "stream": False}).encode()
        req  = urllib.request.Request(
            "http://localhost:11434/api/pull",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = _json.loads(r.read())
        _write_audit(role, "/admin/llm/pull", query=model, elapsed_sec=0)
        return {"ok": True, "model": model, "status": resp.get("status","done")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/llm/delete", summary="Ollama 모델 삭제 [4-B]")
async def llm_delete(
    api_key: str,
    model:   str,
    role: str = Depends(get_role_from_request),
):
    """Ollama 모델 삭제."""
    _require_feature(api_key, role, "admin.settings")
    try:
        import urllib.request, json as _json
        body = _json.dumps({"name": model}).encode()
        req  = urllib.request.Request(
            "http://localhost:11434/api/delete",
            data=body,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        urllib.request.urlopen(req, timeout=10)
        # [PR plan-1] resolver cache invalidation — deleted model must
        # not be used on the next /query/.
        try:
            from core.model_resolver import invalidate_cache
            invalidate_cache()
        except Exception:
            pass
        _write_audit(role, "/admin/llm/delete", query=model, elapsed_sec=0)
        return {"ok": True, "model": model, "deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

def _list_installed_ollama_models() -> set:
    """ollama list 결과에서 설치된 모델 이름 set 반환. 실패 시 빈 set."""
    try:
        import urllib.request, json as _json
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        return {m.get("name", "") for m in data.get("models", []) if m.get("name")}
    except Exception:
        return set()


@app.get("/admin/llm/selections", summary="task별 LLM 매핑 조회 [#15]")
async def llm_selections_get(
    api_key: str,
    role: str = Depends(get_role_from_request),
):
    """현재 ``llm.selection`` 의 ``task_type → model`` 매핑 전체 반환."""
    _require_feature(api_key, role, "admin.settings")
    from llm.selection import get_all_selections
    return {"selections": get_all_selections()}


@app.post("/admin/llm/select", summary="task별 LLM 매핑 저장 [#15]")
async def llm_select_set(
    api_key:   str,
    task_type: str,
    model:     str,
    role: str = Depends(get_role_from_request),
):
    """``task_type`` 의 추론에 사용할 model을 지정. ollama에 설치된 model만 허용."""
    _require_feature(api_key, role, "admin.settings")
    task_type = (task_type or "").strip()
    model     = (model or "").strip()
    if not task_type or len(task_type) > 32:
        raise HTTPException(status_code=400, detail="task_type 필수 (1-32자)")
    if not model or len(model) > 80:
        raise HTTPException(status_code=400, detail="model 필수 (1-80자)")

    installed = _list_installed_ollama_models()
    if installed and model not in installed:
        raise HTTPException(
            status_code=400,
            detail=f"'{model}' 미설치 (ollama list 기준). /admin/llm/installed 확인.",
        )

    from llm.selection import set_model_for_task
    set_model_for_task(task_type, model)
    _write_audit(role, "/admin/llm/select", query=f"{task_type}={model}", elapsed_sec=0)
    return {"ok": True, "task_type": task_type, "model": model}


@app.delete("/admin/llm/select", summary="task별 LLM 매핑 제거 [#15]")
async def llm_select_remove(
    api_key:   str,
    task_type: str,
    role: str = Depends(get_role_from_request),
):
    """``task_type`` 매핑 제거. 기본 model로 fallback."""
    _require_feature(api_key, role, "admin.settings")
    from llm.selection import remove_model_for_task
    removed = remove_model_for_task(task_type)
    _write_audit(role, "/admin/llm/select#delete", query=task_type, elapsed_sec=0)
    return {"ok": True, "task_type": task_type, "removed": removed}


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

@app.get("/admin/proposals/", summary="자기진화 제안 목록 [P7-EVO]")
async def list_proposals(
    api_key: str,
    status:  str = "pending",
    role:    str = Depends(get_role_from_request),
):
    """admin 검토 대기 중인 자기진화 제안 목록."""
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.evo_analyzer import list_proposals as _list
        return {"proposals": _list(status), "status_filter": status}
    except Exception as e:
        return {"proposals": [], "error": str(e)}


@app.post("/admin/proposals/{proposal_id}/approve",
          summary="제안 승인 → 자동 실행 [P7-EVO]")
async def approve_proposal(
    proposal_id: str,
    api_key:     str,
    role:        str = Depends(get_role_from_request),
):
    """
    admin이 제안을 승인하면 즉시 자동 실행 + 결과 보고.
    실행 결과를 응답으로 반환.
    """
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.evo_analyzer import approve_and_execute
        report = approve_and_execute(proposal_id)
        _write_audit(role, "/admin/proposals/approve",
                     query=proposal_id,
                     answer=f"success={report.get('success')}")
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/proposals/{proposal_id}/reject",
          summary="제안 거부 [P7-EVO]")
async def reject_proposal_api(
    proposal_id: str,
    api_key:     str,
    reason:      str = "",
    role:        str = Depends(get_role_from_request),
):
    """[4-C] 제안 거부 + 사유 장기기억 저장."""
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.evo_analyzer import reject_proposal
        ok = reject_proposal(proposal_id, reason)
        _write_audit(role, "/admin/proposals/reject", query=proposal_id)
        return {"success": ok, "proposal_id": proposal_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RejectionRequest(BaseModel):
    proposal_id: str
    reason:      str

@app.post("/admin/memory/save-rejection", summary="거부 사유 장기기억 저장 [4-C]")
async def save_rejection_memory(
    data:    RejectionRequest,
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """[4-C] 거부 사유 → memory_store 장기기억 저장."""
    _require_feature(api_key, role, "admin.evolution")
    try:
        from core.memory import MemoryStore
        ms  = MemoryStore()
        key = f"rejection:{data.proposal_id[:12]}"
        ms.save_preference({
            "key":         key,
            "value":       data.reason,
            "type":        "rejection_reason",
            "proposal_id": data.proposal_id,
        })
        return {"ok": True, "saved_key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/admin/evo-reports/", summary="자기진화 실행 보고서 [P7-EVO]")
async def get_evo_reports(
    api_key: str,
    limit:   int = 20,
    role:    str = Depends(get_role_from_request),
):
    """자기진화 실행 결과 보고서 목록."""
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.evo_analyzer import list_reports
        return {"reports": list_reports(limit)}
    except Exception as e:
        return {"reports": [], "error": str(e)}


@app.post("/admin/proposals/generate/",
          summary="수동 제안 생성 [P7-EVO]")
async def generate_proposals(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.evo_analyzer import generate_proposals_from_signals
        from llm.router import RouterWrapper
        proposals = generate_proposals_from_signals(RouterWrapper("general"))
        return {"generated": len(proposals),
                "proposals": [{"id": p["proposal_id"],
                               "title": p["title"],
                               "type": p["type"]} for p in proposals]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@app.post("/admin/learn/topic/", summary="주제 학습 [P8-LEARN / 3-E 경로B]")
async def learn_topic_api(
    api_key:    str,
    topic:      str,
    use_web:    bool = True,
    role: str = Depends(get_role_from_request),
):
    """
    [경로 B / U-1 개선] 어드민 자기학습 → 웹검색 → URL본문fetch → LLM깊이처리 → 장기 지식.

    파이프라인:
      1. 웹 검색 (Tavily/DDG)
      2. 상위 2개 URL 본문 fetch
      3. LLM이 본문 + snippet 통합 → 구조화된 지식 생성
      4. wiki entity 저장 + vector 인덱싱
      5. domain 태그 자동 분류 + 지식 레벨 +5점
    """
    _require_feature(api_key, role, "admin.knowledge")
    if not topic:
        raise HTTPException(status_code=400, detail="topic 파라미터 필요")
    try:
        if use_web:
            from tools.web.web_searcher import (
                search_web, enrich_results_with_content,
                save_as_longterm,
                update_knowledge_level, classify_domain,
            )

            # ① 검색
            results = search_web(topic, max_results=5)
            if not results:
                return {"success": False, "message": "웹 검색 결과 없음"}

            # ② URL 본문 fetch (상위 2개)
            results = enrich_results_with_content(results, max_fetch=2)

            # ③ domain 자동 분류
            domain = classify_domain(topic, results)

            # ④ LLM 처리 — 컨텍스트 최소화 (한국어는 토큰 2~3배)
            # num_ctx=2048 기준: 입력 800자 이내가 안전 (#13: router 경유)
            from llm.router import RouterWrapper
            llm = RouterWrapper("extract")

            # snippet만 사용 (body 제외) — 짧고 정제된 내용
            snippet_ctx = "\n".join([
                f"{i}. {r['title']}: {r.get('snippet','')[:150]}"
                for i, r in enumerate(results[:3], 1)
                if r.get('snippet') or r.get('title')
            ])

            # 짧고 명확한 프롬프트
            knowledge_prompt = (
                f"'{topic}' 핵심 요약 (200자 이내):\n\n"
                f"{snippet_ctx[:500]}\n\n"
                f"요약:"
            )

            print(f"[LEARN] 프롬프트 길이: {len(knowledge_prompt)}자")
            knowledge = llm.call_gemma(
                knowledge_prompt, timeout=60, use_cache=False, max_tokens=300
            )

            # ⑤ LLM 0자 → snippet 기반 fallback
            if not knowledge or len(knowledge.strip()) < 10:
                print("[LEARN] LLM 0자 → fallback 사용")
                parts = []
                for r in results[:3]:
                    title = r.get('title', '')
                    snip = r.get('snippet', '') or r.get('body', '')[:200]
                    if title or snip:
                        parts.append(f"{title}: {snip[:150]}")
                knowledge = f"{topic} 요약:\n" + "\n".join(parts) if parts else f"{topic}: 웹 검색 결과 참조"

            # ⑥ wiki entity 저장 — 예외 완전 격리
            path = None
            try:
                path = save_as_longterm(
                    query=topic, results=results,
                    summary=knowledge, user_role="admin",
                    domain=domain,
                )
            except Exception as save_err:
                print(f"[LEARN] wiki 저장 실패 (무시): {save_err}")
                # 저장 실패해도 학습 내용은 반환

            # ⑥ 지식 레벨 +5점 (의도적 장기 학습)
            update_knowledge_level(topic, is_longterm=True)

            sources = [r["url"] for r in results if r.get("url")]
            fetched = sum(1 for r in results if r.get("body"))

            return {
                "success":      True,
                "topic":        topic,
                "domain":       domain,
                "knowledge":    knowledge[:300],
                "wiki_path":    str(path) if path else None,
                "sources":      sources[:3],
                "fetched_urls": fetched,
                "method":       "web_search + url_fetch + llm",
            }

        # use_web=False → 기존 LLM 자기학습
        from tools.self.self_learner import learn_topic
        result = learn_topic(topic)
        if not result:
            return {"success": False, "message": "학습 실패 또는 품질 미달"}
        return {"success": True, "topic": result["topic"],
                "quality": result["quality"], "sources": result["sources"],
                "proposal_id": result["proposal"].get("proposal_id", "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/learn/from-errors/", summary="오류 쿼리 자동 학습 [P8-LEARN]")
async def learn_from_errors_api(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.knowledge")
    try:
        from tools.self.self_learner import learn_from_errors
        results = learn_from_errors()
        return {"learned": len(results),
                "topics": [{"topic": r["topic"],
                            "quality": r["quality"]} for r in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/learn/error-queries/", summary="반복 오류 쿼리 [P8-LEARN]")
async def get_error_queries(
    api_key: str, min_count: int = 2,
    role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.importance_scorer import get_repeated_errors
        return {"error_queries": get_repeated_errors(min_count)}
    except Exception as e:
        return {"error_queries": [], "error": str(e)}


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

def _require_admin(api_key: str, role: str):
    """
    Admin API 접근 검증.
    api_key 검증 + role=admin 체크 (보안 유지)
    """
    verify_api_key(api_key)
    if role != "admin":
        raise HTTPException(status_code=403,
                            detail="admin 권한 필요 — admin 계정으로 로그인하세요")


def _require_feature(api_key: str, role: str, feature_id: str):
    """[W4-Q2] Validate api_key + consult PolicyEngine.can_use_feature.

    Same shape as _require_admin but consults the per-feature gate
    from W4-Q1 instead of the hardcoded ``role != "admin"`` check.
    For features whose default_allowed set is ``{"admin"}`` (every
    admin.* feature in the Q1 catalog), behaviour is identical to
    _require_admin — that equivalence is the safety net for Q2-a's
    rewrite of existing endpoints.

    Q2-b will add new admin.* features for the remaining endpoints
    (settings/llm/persona/...) and replace their _require_admin
    calls similarly.
    """
    verify_api_key(api_key)
    from core.policy_engine import default_engine
    d = default_engine.can_use_feature(role, feature_id)
    if not d.allowed:
        raise HTTPException(
            status_code=403,
            detail=f"권한이 부족합니다. ({feature_id})",
        )


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


@app.get("/admin/users", summary="사용자 목록 (W4 P2-A: real implementation)")
async def admin_users(
    api_key: str,
    pending: bool = False,
    role:    str  = Depends(get_role_from_request),
):
    """Return every user row, password hash omitted.

    Query params:
      pending — when truthy, restrict to active=0 rows so the admin UI
                can show a focused "approvals queue" without a second
                round-trip. Defaults to False (full list).

    Pre-W4 this endpoint silently returned an empty list because
    ``core.auth.list_users`` did not exist; the swallow-and-return shape
    is replaced with a real implementation. Any exception now surfaces
    as a 500 — better than masking schema drift behind an empty UI.
    """
    _require_feature(api_key, role, "admin.users")
    return {"users": _auth_list_users(only_pending=bool(pending))}


# W4 P2-A — admin approves a pending signup (active=0 → active=1 + role).
# api_key arrives as a query param to match the frontend `api()` helper,
# which auto-appends ?api_key=... to every admin call. Body holds only
# the operation-specific fields.
class AdminUserApproveRequest(BaseModel):
    username: str
    role:     str

@app.post("/admin/users/approve", summary="사용자 가입 승인 (W4 P2-A)")
async def admin_users_approve(
    data:    AdminUserApproveRequest,
    request: Request,
    api_key: str = "",
    role:    str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.users")
    if data.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"invalid role: {data.role}")

    ok = _auth_approve_user(data.username, data.role)
    ip = get_client_ip(request)
    if not ok:
        _write_audit(role, "/admin/users/approve", query=data.username,
                     security_event="approve_failed (not pending or unknown)",
                     ip_address=ip)
        raise HTTPException(
            status_code=404,
            detail="pending 상태의 사용자가 아닙니다. (이미 활성 또는 미존재)",
        )
    _write_audit(role, "/admin/users/approve", query=data.username,
                 security_event=f"approved role={data.role}", ip_address=ip)
    return {"ok": True, "username": data.username, "role": data.role}


# W4 P2-A — admin rejects a pending signup (DELETE the row).
class AdminUserRejectRequest(BaseModel):
    username: str

@app.post("/admin/users/reject", summary="사용자 가입 거부 (W4 P2-A)")
async def admin_users_reject(
    data:    AdminUserRejectRequest,
    request: Request,
    api_key: str = "",
    role:    str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.users")
    ok = _auth_reject_user(data.username)
    ip = get_client_ip(request)
    if not ok:
        _write_audit(role, "/admin/users/reject", query=data.username,
                     security_event="reject_failed (not pending or unknown)",
                     ip_address=ip)
        raise HTTPException(
            status_code=404,
            detail="pending 상태의 사용자가 아닙니다. (활성 사용자는 비활성화를 사용하세요)",
        )
    _write_audit(role, "/admin/users/reject", query=data.username,
                 security_event="rejected (row deleted)", ip_address=ip)
    return {"ok": True, "username": data.username}


# W4 P2-A — admin deactivates an active user (active=1 → active=0).
class AdminUserDeactivateRequest(BaseModel):
    username: str

@app.post("/admin/users/deactivate", summary="사용자 비활성화 (W4 P2-A)")
async def admin_users_deactivate(
    data:    AdminUserDeactivateRequest,
    request: Request,
    api_key: str = "",
    role:    str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.users")
    # Admin cannot deactivate themselves — that would be an instant
    # lockout. The feature gate above has already confirmed the caller
    # holds admin.users; we read the JWT subject to recover the username.
    try:
        from core.auth import verify_token
        caller_payload = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            caller_payload = verify_token(auth_header[7:].strip())
        caller_username = (caller_payload or {}).get("sub")
    except Exception:
        caller_username = None
    if caller_username and caller_username == data.username:
        raise HTTPException(
            status_code=400,
            detail="자기 자신을 비활성화할 수 없습니다.",
        )

    ok = _auth_deactivate_user(data.username)
    ip = get_client_ip(request)
    if not ok:
        _write_audit(role, "/admin/users/deactivate", query=data.username,
                     security_event="deactivate_failed (unknown user)",
                     ip_address=ip)
        raise HTTPException(status_code=404,
                            detail="존재하지 않는 사용자입니다.")
    _write_audit(role, "/admin/users/deactivate", query=data.username,
                 security_event="deactivated", ip_address=ip)
    return {"ok": True, "username": data.username}


# ─── W4 P2-B: password change + reset-token workflow ────────────

def _bearer_username(request: Request) -> Optional[str]:
    """Pull `sub` (username) out of the Bearer JWT, or None.

    The endpoints below need the caller's username to scope the
    operation to their own account. We use the JWT subject claim
    rather than a body field so the client cannot self-impersonate.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    payload = _auth_verify_token(auth_header[7:].strip())
    return (payload or {}).get("sub") if payload else None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

@app.post("/password/change",
          summary="비밀번호 변경 (로그인된 사용자 — W4 P2-B)")
async def password_change(
    data:    PasswordChangeRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Self-service password change. JWT-authenticated; the request
    body MUST NOT include username — the subject is taken from the
    JWT so an attacker holding only a stolen body can't pivot.

    Response codes:
      200 — password updated
      400 — new password fails the policy (rule shown verbatim)
      401 — JWT missing/invalid OR old_password didn't verify
            (same status so an attacker can't distinguish the two
             after the JWT slot is filled)
    """
    ip = get_client_ip(request)
    username = _bearer_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    # [W4-Q2-c] role-level feature gate. Default matrix allows
    # password.change_self for every role (admin/manager/employee/
    # external). Admins can revoke this on a per-role basis via
    # the matrix without disabling the entire endpoint.
    from core.policy_engine import default_engine as _pe
    _d = _pe.can_use_feature(role, "password.change_self")
    if not _d.allowed:
        raise HTTPException(
            status_code=403,
            detail="권한이 부족합니다. (password.change_self)",
        )

    result = _auth_change_password(username, data.old_password, data.new_password)
    if result == "ok":
        _write_audit("authenticated", "/password/change", query=username,
                     security_event="password_change_success", ip_address=ip)
        return {"ok": True}
    if result.startswith("policy:"):
        msg = result.split(":", 1)[1]
        _write_audit("authenticated", "/password/change", query=username,
                     security_event="password_change_rejected_policy",
                     ip_address=ip)
        raise HTTPException(status_code=400, detail=msg)
    # invalid_old / no_user → collapse to 401. The audit log still
    # distinguishes for the operator.
    _write_audit("authenticated", "/password/change", query=username,
                 security_event=f"password_change_failed_{result}",
                 ip_address=ip)
    raise HTTPException(
        status_code=401,
        detail="현재 비밀번호가 일치하지 않거나 계정이 비활성 상태입니다.",
    )


class AdminIssueResetTokenRequest(BaseModel):
    username: str

@app.post("/admin/users/issue-reset-token",
          summary="비밀번호 재설정 토큰 발급 (admin 전용 — W4 P2-B)")
async def admin_issue_reset_token(
    data:    AdminIssueResetTokenRequest,
    request: Request,
    api_key: str = "",
    role:    str = Depends(get_role_from_request),
):
    """Admin issues a one-shot reset token. Token is returned in
    plaintext exactly once — admin must relay it out-of-band (phone,
    in-person, internal chat). Server only stores SHA256(token).

    Returns 404 if the user is unknown or inactive — admins should not
    issue resets for pending or removed accounts (use approve/reject).
    """
    _require_feature(api_key, role, "admin.users")
    ip = get_client_ip(request)

    token = _auth_issue_reset_token(data.username)
    if token is None:
        _write_audit(role, "/admin/users/issue-reset-token",
                     query=data.username,
                     security_event="reset_token_issue_failed (unknown or inactive)",
                     ip_address=ip)
        raise HTTPException(
            status_code=404,
            detail="활성 사용자가 아닙니다.",
        )
    _write_audit(role, "/admin/users/issue-reset-token",
                 query=data.username,
                 security_event="reset_token_issued",
                 ip_address=ip)
    return {
        "ok": True,
        "username":           data.username,
        "token":              token,
        "expires_in_seconds": RESET_TOKEN_TTL_SEC,
    }


class PasswordResetConfirmRequest(BaseModel):
    username:     str
    token:        str
    new_password: str

@app.post("/password/reset/confirm",
          summary="비밀번호 재설정 (토큰 + 새 비번 — W4 P2-B)")
async def password_reset_confirm(
    data:    PasswordResetConfirmRequest,
    request: Request,
):
    """Public endpoint — the caller is anonymous and presents an
    admin-issued token. Rate-limited at the IP layer to keep token
    brute-force bounded.

    Response codes:
      200 — password reset
      400 — new_password fails the policy (rule shown verbatim)
      401 — token invalid / expired / already used / no such user
            (one unified message; the audit log distinguishes for
            the operator)
    """
    ip = get_client_ip(request)
    result = _auth_consume_reset_token(data.username, data.token,
                                       data.new_password)
    if result == "ok":
        _write_audit("anonymous", "/password/reset/confirm",
                     query=data.username,
                     security_event="password_reset_completed",
                     ip_address=ip)
        return {"ok": True}
    if result.startswith("policy:"):
        _write_audit("anonymous", "/password/reset/confirm",
                     query=data.username,
                     security_event="password_reset_rejected_policy",
                     ip_address=ip)
        raise HTTPException(status_code=400, detail=result.split(":", 1)[1])
    _write_audit("anonymous", "/password/reset/confirm",
                 query=data.username,
                 security_event=f"password_reset_failed_{result}",
                 ip_address=ip)
    raise HTTPException(
        status_code=401,
        detail="토큰이 유효하지 않거나 만료되었습니다.",
    )


# ─── W4 P3-1: user API keys (issue / list / revoke) ─────────────

class ApiKeyIssueRequest(BaseModel):
    # Optional operator-supplied note ("ci-deploy", "laptop-2026-05"
    # etc.) so a leaked key can be tied to a context. Plain string —
    # rendered as text in the admin UI.
    label: Optional[str] = None

@app.post("/api-keys/issue",
          summary="API 키 발급 (로그인된 사용자 자신용 — W4 P3-1)")
async def api_keys_issue(
    data:    ApiKeyIssueRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Issue a new long-lived API key for the JWT-authenticated user.

    The plaintext is returned **exactly once**. Only SHA256(token) is
    persisted, so the value cannot be recovered later — the user must
    capture it now. A revoked key cannot be unrevoked; issue a fresh
    one instead.

    Response codes:
      200 — {token, prefix, label?}
      401 — JWT missing/invalid
      404 — JWT subject does not correspond to an active user (race
            between token mint and account deactivation)
    """
    ip = get_client_ip(request)
    username = _bearer_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    # [W4-Q2-c] api_keys.issue_self default = admin/manager/employee
    # (external denied). The check applies to /list and /revoke too —
    # losing 'issue' implicitly revokes the operator's own key mgmt UI.
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "api_keys.issue_self").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (api_keys.issue_self)")

    pair = _api_key_issue(username, data.label)
    if pair is None:
        _write_audit("authenticated", "/api-keys/issue", query=username,
                     security_event="api_key_issue_failed (inactive)",
                     ip_address=ip)
        raise HTTPException(status_code=404, detail="활성 사용자가 아닙니다.")
    plain, prefix = pair
    _write_audit("authenticated", "/api-keys/issue", query=username,
                 security_event=f"api_key_issued prefix={prefix}",
                 ip_address=ip)
    return {"ok": True, "token": plain, "prefix": prefix,
            "label": data.label}


@app.get("/api-keys/list", summary="내 API 키 목록 (W4 P3-1)")
async def api_keys_list(
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """List the caller's keys (active + revoked).

    Plaintext is never returned. Each entry exposes the prefix (which
    is the revocation handle), label, timestamps, and a ``revoked``
    boolean. Sort: active first, then by created_at DESC.
    """
    username = _bearer_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "api_keys.issue_self").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (api_keys.issue_self)")
    return {"keys": _api_key_list(username)}


class ApiKeyRevokeRequest(BaseModel):
    key_prefix: str

@app.post("/api-keys/revoke",
          summary="API 키 회수 (로그인된 사용자 — 본인 키만 회수 가능, W4 P3-1)")
async def api_keys_revoke(
    data:    ApiKeyRevokeRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Revoke one of the caller's keys by its prefix.

    Scope is enforced in core.api_keys.revoke_api_key by the
    ``username = ?`` filter — a caller cannot revoke another user's
    key by guessing their prefix. Re-revoking an already-revoked key
    returns 404 (rowcount=0) rather than re-stamping the timestamp.
    """
    ip = get_client_ip(request)
    username = _bearer_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "api_keys.issue_self").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (api_keys.issue_self)")

    ok = _api_key_revoke(username, data.key_prefix)
    if not ok:
        _write_audit("authenticated", "/api-keys/revoke", query=username,
                     security_event=f"api_key_revoke_failed prefix={data.key_prefix}",
                     ip_address=ip)
        raise HTTPException(status_code=404,
                            detail="해당 키가 없거나 이미 회수되었습니다.")
    _write_audit("authenticated", "/api-keys/revoke", query=username,
                 security_event=f"api_key_revoked prefix={data.key_prefix}",
                 ip_address=ip)
    return {"ok": True, "prefix": data.key_prefix}


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


@app.get("/admin/patches", summary="Patch 이력 [P7]")
async def admin_patches(api_key: str, status: str = "all",
                        role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.patch.patch_generator import list_patches
        return {"patches": list_patches(status)}
    except Exception as e:
        return {"patches": [], "error": str(e)}


@app.post("/admin/patch/approve", summary="Patch 승인 [#48 phase 1]")
async def admin_patch_approve(request: Request, role: str = Depends(get_role_from_request)):
    """Approve + deploy a pending patch.

    #48 phase 1 contract:
      - 403 unless `JAMES_ENABLE_EVOLUTION=1` (operator opt-in).
      - Caller must include `approver_username` in the JSON body —
        the audit log records WHO approved each deployed patch.
      - Caller's resolved role must equal `JAMES_EVOLUTION_APPROVER_ROLE`
        (default "admin"). Other admin endpoints already enforce
        admin via `_require_admin`; this gate adds the explicit
        "approver-role" check so the env var stays load-bearing.
      - On success the patch JSON is updated in place with
        `approver_username` / `approver_role` / `approved_at` /
        `approval_method`, and the lifecycle is recorded in
        `james_patch_log.jsonl` (visible via /admin/audit).
    """
    body = await request.json()
    _require_feature(body.get("api_key",""), role, "admin.evolution")

    # #48 phase 1 — opt-in gate.
    from config import EVOLUTION_ENABLED, APPROVER_ROLE
    if not EVOLUTION_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="evolution_disabled: set JAMES_ENABLE_EVOLUTION=1 to enable",
        )
    if role != APPROVER_ROLE:
        raise HTTPException(
            status_code=403,
            detail=f"approver_role_mismatch: required {APPROVER_ROLE!r}, got {role!r}",
        )

    patch_id          = body.get("patch_id", "").strip()
    approver_username = (body.get("approver_username") or "").strip()
    approval_method   = (body.get("approval_method") or "api").strip()

    if not patch_id:
        raise HTTPException(status_code=400, detail="patch_id required")
    if not approver_username:
        raise HTTPException(status_code=400, detail="approver_username required (#48 audit)")

    try:
        from tools.patch.patch_generator import load_patch
        from tools.patch.patch_validator import validate_patch
        from tools.patch.patch_applier   import apply as patch_apply
        from tools.patch.approval        import record_approval, record_outcome

        patch = load_patch(patch_id)
        if not patch:
            raise HTTPException(status_code=404, detail="Patch 없음")

        passed, failures = validate_patch(patch)
        if not passed:
            return {"success": False, "failures": failures}

        # Record approver BEFORE apply — if apply crashes, the audit
        # log still shows who tried to deploy what. Restoring this
        # ordering is the entire reason this PR exists.
        rec_ok, rec = record_approval(
            patch_id          = patch_id,
            approver_username = approver_username,
            approver_role     = role,
            approval_method   = approval_method,
        )
        if not rec_ok:
            raise HTTPException(status_code=500, detail=f"approval_record_failed: {rec.get('error')}")

        # Re-load with approval fields baked in so apply() sees the
        # final patch shape (forward-compat — applier may grow to
        # honor approval metadata).
        patch = rec
        ok, msg = patch_apply(patch, validated=True)

        # If apply() itself failed, no bench gate to run — record and exit.
        if not ok:
            record_outcome(patch_id, "rolled_back", detail=f"apply failed: {msg}")
            return {
                "success":           False,
                "message":           msg,
                "outcome":           "rolled_back",
                "patch_id":          patch_id,
                "approver_username": approver_username,
                "approver_role":     role,
                "approval_method":   approval_method,
            }

        # #68 phase 2-A: bench eval gate. Re-runs STEP 7 against the
        # live server in a subprocess (asyncio.to_thread so the event
        # loop can serve the bench's incoming /query/ requests). On
        # regression, the gate auto-rolls-back inside run_bench_gate
        # and returns outcome_label='rolled_back'.
        from tools.patch.bench_gate import run_bench_gate
        gate = await run_bench_gate(patch_id, patch.get("target", ""))

        record_outcome(
            patch_id, gate.outcome_label,
            detail=gate.detail,
            before_metrics=gate.before_metrics,
            after_metrics=gate.after_metrics,
        )
        return {
            "success":           gate.passed,
            "message":           msg,
            "outcome":           gate.outcome_label,
            "before_metrics":    gate.before_metrics,
            "after_metrics":     gate.after_metrics,
            "patch_id":          patch_id,
            "approver_username": approver_username,
            "approver_role":     role,
            "approval_method":   approval_method,
        }
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/patch/audit", summary="Patch 라이프사이클 감사 조회 [#68 phase 2-C]")
async def admin_patch_audit(
    api_key:  str,
    since:    str = "",
    approver: str = "",
    outcome:  str = "",
    limit:    int = 200,
    role:     str = Depends(get_role_from_request),
):
    """Filtered, newest-first slice of `james_patch_log.jsonl`.

    Filters (all optional; combine for AND semantics):
      since:    ISO 8601 lower bound (e.g. "2026-05-08" or full datetime)
      approver: case-insensitive exact `approver_username` match
      outcome:  case-insensitive `outcome` match — `deployed` /
                `rolled_back` / `deployed_gate_skipped`
      limit:    max entries returned (default 200, hard cap 1000)

    See `tools/patch/audit_query.py` for filter semantics + rationale.
    Composes with `/admin/audit` (the broader, multi-source feed) —
    this endpoint is the patch-specific view.
    """
    _require_feature(api_key, role, "admin.evolution")
    from tools.patch.audit_query import query_patch_audit
    rows = query_patch_audit(
        since=since or None,
        approver=approver or None,
        outcome=outcome or None,
        limit=limit,
    )
    return {
        "filters": {
            "since":    since,
            "approver": approver,
            "outcome":  outcome,
            "limit":    limit,
        },
        "count": len(rows),
        "events": rows,
    }


@app.post("/admin/patch/reject", summary="Patch 거부 [P7]")
async def admin_patch_reject(request: Request, role: str = Depends(get_role_from_request)):
    body = await request.json()
    _require_feature(body.get("api_key",""), role, "admin.evolution")
    patch_id = body.get("patch_id","")
    from pathlib import Path
    pf = Path(f"./workspace/patches/{patch_id}.json")
    if pf.exists():
        d = json.loads(pf.read_text(encoding="utf-8"))
        d["status"] = "REJECTED"
        pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "patch_id": patch_id, "status": "REJECTED"}


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


@app.get("/admin/uploads/history/",
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

@app.get("/admin/artifacts/list", summary="데이터 아티팩트 — 관리자 전체 조회 (W7-A)")
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


@app.get("/admin/artifacts/{artifact_id}", summary="아티팩트 상세 — 관리자 (W7-A)")
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


@app.get("/artifacts/mine/list", summary="내 데이터 아티팩트 (W7-A)")
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


@app.get("/artifacts/mine/{artifact_id}", summary="내 아티팩트 상세 (W7-A)")
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


# ─── W8-A: workspace jobs (run / list / detail / download) ─────
# Sync execution — the handlers complete in seconds for typical wiki
# sizes. /jobs/run blocks until the row reaches done/failed. Scheduler
# (cron-driven) is W8-A2; this PR is pure on-demand execution.

class JobRunRequest(BaseModel):
    job_type:   str
    input_refs: list = []
    options:    Optional[dict] = None


@app.post("/jobs/run", summary="워크스페이스 job 실행 (W8-A)")
async def jobs_run(
    data:    JobRunRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """workspace.run_jobs feature gate. Owner is the JWT subject
    (no JWT → 401 — anonymous can't run jobs). Body has no owner
    field; the server is the source of truth."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.run_jobs").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.run_jobs)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    from core.workspace import register_job, execute_job, HANDLERS
    if data.job_type not in HANDLERS:
        raise HTTPException(status_code=400,
                            detail=f"unknown job_type: {data.job_type}")
    job_id = register_job(data.job_type, data.input_refs or [],
                          owner=owner, options=data.options)
    ip = get_client_ip(request)
    _write_audit(role, "/jobs/run", query=f"{data.job_type}/{job_id}",
                 security_event="job_started", ip_address=ip)
    row = execute_job(job_id)
    final_event = "job_done" if row["status"] == "done" else f"job_{row['status']}"
    _write_audit(role, "/jobs/run", query=f"{data.job_type}/{job_id}",
                 security_event=final_event, ip_address=ip)
    return row


# ─── W8-D: schedule a recurring job ────────────────────────────

class JobScheduleRequest(BaseModel):
    job_type:      str
    input_refs:    list = []
    options:       Optional[dict] = None
    schedule_cron: str   # "hourly" | "every:N" | "daily:HH:MM" | "weekly:DOW:HH:MM"


@app.post("/jobs/schedule",
          summary="워크스페이스 job 예약 (정기 실행, W8-D)")
async def jobs_schedule(
    data:    JobScheduleRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Insert a scheduled job. ``workspace.schedule`` feature gate
    (admin only by default — cron-driven jobs touch shared resources
    so the grant is intentionally narrow).

    The DSL is validated up front: an unrecognised spec returns 400
    rather than persisting a row that the scheduler would silently
    ignore. The first ``next_run_at`` is computed from the spec; the
    Scheduler updates it after each successful tick.
    """
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.schedule").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.schedule)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    from core.workspace import register_job, HANDLERS
    from core.scheduler import compute_next_run
    if data.job_type not in HANDLERS:
        raise HTTPException(status_code=400,
                            detail=f"unknown job_type: {data.job_type}")

    now = int(time.time())
    next_at = compute_next_run(data.schedule_cron, now)
    if next_at is None:
        raise HTTPException(
            status_code=400,
            detail=(f"unknown schedule spec: {data.schedule_cron!r}. "
                    "Use 'hourly' / 'every:N' / 'daily:HH:MM' / "
                    "'weekly:DOW:HH:MM'."),
        )

    job_id = register_job(
        data.job_type, data.input_refs or [],
        owner=owner, options=data.options,
        schedule_cron=data.schedule_cron, next_run_at=next_at,
    )
    ip = get_client_ip(request)
    _write_audit(role, "/jobs/schedule",
                 query=f"{data.job_type}/{job_id}",
                 security_event=f"scheduled cron={data.schedule_cron}",
                 ip_address=ip)
    return {
        "ok":            True,
        "job_id":        job_id,
        "schedule_cron": data.schedule_cron,
        "next_run_at":   next_at,
    }


# ─── W8-D follow-up: unschedule + scheduler status ─────────────

class JobUnscheduleRequest(BaseModel):
    job_id: str


@app.post("/jobs/unschedule",
          summary="정기 실행 해제 (W8-D follow-up)")
async def jobs_unschedule(
    data:    JobUnscheduleRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Converts a scheduled row back into a one-shot. Mirror of
    /jobs/schedule's authority surface — workspace.schedule
    (admin-only default). 404 when the job doesn't exist or is
    already a one-shot."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.schedule").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.schedule)")
    from core.scheduler import unschedule_job
    ok = unschedule_job(data.job_id)
    ip = get_client_ip(request)
    if not ok:
        _write_audit(role, "/jobs/unschedule", query=data.job_id,
                     security_event="unschedule_failed (unknown or one-shot)",
                     ip_address=ip)
        raise HTTPException(
            status_code=404,
            detail="해당 job 이 없거나 이미 정기실행이 아닙니다.",
        )
    _write_audit(role, "/jobs/unschedule", query=data.job_id,
                 security_event="unscheduled", ip_address=ip)
    return {"ok": True, "job_id": data.job_id}


@app.get("/admin/scheduler/status",
         summary="스케줄러 상태 + 다음 firing 목록 (W8-D follow-up)")
async def admin_scheduler_status(
    api_key: str,
    limit:   int = 20,
    role:    str = Depends(get_role_from_request),
):
    """Scheduler health snapshot.

    Returns the live ``default_scheduler`` state (is_running,
    poll_interval_sec, retention_days, last_retention) plus the next
    N scheduled rows sorted by ``next_run_at``. Operator can spot
    "scheduler stopped" (is_running=False), "retention never ran"
    (last_retention=0), or "this job is stuck" (next_run_at in the
    past) at a glance.

    Gated by admin.metrics (matches /admin/metrics / dashboard).
    """
    _require_feature(api_key, role, "admin.metrics")
    from core.scheduler import default_scheduler, list_upcoming_scheduled
    return {
        "is_running":         default_scheduler.is_running(),
        "poll_interval_sec":  default_scheduler.poll_interval_sec,
        "retention_days":     default_scheduler.retention_days,
        "last_retention_at":  default_scheduler._last_retention,
        "now":                int(time.time()),
        "upcoming":           list_upcoming_scheduled(limit=limit),
    }


@app.get("/jobs/list", summary="내 job 목록 (W8-A)")
async def jobs_list(
    request: Request,
    status:  str = "",
    limit:   int = 50,
    offset:  int = 0,
    role:    str = Depends(get_role_from_request),
):
    """Self-view — gated by workspace.view (lower bar than
    run_jobs; reading your own queue is universally useful)."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.view").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.view)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    from core.workspace import list_jobs, count_jobs
    s = status.strip() or None
    return {
        "items":  list_jobs(owner=owner, status=s, limit=limit, offset=offset),
        "total":  count_jobs(owner=owner, status=s),
        "status": s or "",
        "limit":  limit,
        "offset": offset,
    }


@app.get("/jobs/{job_id}", summary="내 job 상세 (W8-A)")
async def jobs_detail(
    job_id:  str,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.view").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.view)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    from core.workspace import get_job
    row = get_job(job_id, requester_username=owner)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return row


@app.get("/jobs/{job_id}/download", summary="job 결과 다운로드 (W8-A)")
async def jobs_download(
    job_id:  str,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Stream the produced file. Cross-owner access surfaces as 404
    (the row lookup returns None for non-owners; we don't leak the
    job_id space)."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.view").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.view)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    from core.workspace import get_job
    row = get_job(job_id, requester_username=owner)
    if row is None or not row.get("output_path"):
        raise HTTPException(status_code=404, detail="job result not found")
    try:
        from config import BASE_DIR
        full = os.path.join(BASE_DIR, row["output_path"])
    except ImportError:
        full = row["output_path"]
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="output file missing on disk")
    return FileResponse(full, filename=os.path.basename(full))


# ── admin-side mirrors (admin.data feature, sees every owner) ──

@app.get("/admin/jobs/list", summary="모든 job 목록 — admin (W8-A)")
async def admin_jobs_list(
    api_key: str,
    status:  str = "",
    limit:   int = 50,
    offset:  int = 0,
    role:    str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.data")
    from core.workspace import list_jobs, count_jobs
    s = status.strip() or None
    return {
        "items":  list_jobs(status=s, limit=limit, offset=offset),
        "total":  count_jobs(status=s),
        "status": s or "",
        "limit":  limit,
        "offset": offset,
    }


@app.get("/admin/jobs/{job_id}", summary="job 상세 — admin (W8-A)")
async def admin_jobs_detail(
    job_id:  str,
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.data")
    from core.workspace import get_job
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return row


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_llmwiki:app", host="127.0.0.1", port=8000, reload=True)
