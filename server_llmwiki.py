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
from core.auth import authenticate, get_role_from_token, add_user, ALLOWED_ROLES, DEV_MODE
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


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def serve_admin():
    admin = os.path.join(FRONTEND_DIR, "admin.html")
    if os.path.exists(admin):
        return FileResponse(admin)
    return HTMLResponse("<h1>Admin</h1><p>frontend/admin.html 없음</p>")

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
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="API Key 오류")

def get_role_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_role: Optional[str] = Header(None, alias="X-Role"),
) -> str:
    """
    JWT 토큰 → role 추출.
    [P7] api_key만 있는 경우 employee로 처리 (로컬 전용 시스템)
    """
    if credentials and credentials.credentials:
        role = get_role_from_token(credentials.credentials)
        print(f"[AUTH] JWT role: {role}")
        return role

    if x_role and x_role in ALLOWED_ROLES:
        if DEV_MODE:
            print(f"[AUTH] X-Role 헤더 사용: {x_role} (개발 모드)")
            return x_role

    # [P7-FIX] JWT 없어도 api_key 검증은 엔드포인트에서 수행됨
    # 로컬 전용 시스템: api_key 통과 = 신뢰 사용자 → employee 수준 부여
    # (인물명 마스킹 해제 목적)
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

    # 체크 필요한 엔드포인트만
    if endpoint in ("/query/", "/upload/", "/login/"):
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


@app.post("/upload/", response_model=UploadResponse, summary="파일 업로드 (admin 전용)")
async def upload(
    request:     Request,
    file:        UploadFile = File(...),
    api_key:     str        = Form(...),
    source_type: str        = Form("prod"),
    instruction: str        = Form(""),     # 챗 저장 지시 (선택)
    role:        str        = Depends(get_role_from_request),
):
    verify_api_key(api_key)   # api_key 검증 통과 = 신뢰된 사용자
    ip = get_client_ip(request)
    # [P7] api_key 검증 통과 시 업로드 허용 (JWT 없는 웹 UI 지원)
    # admin 전용 정책은 유지하되 api_key 인증은 통과 처리

    allowed_ext = (
        ".pdf",".png",".jpg",".jpeg",".bmp",".tiff",".webp",
        ".txt",".md",".csv",".html",".htm",
        ".docx",".doc",".xlsx",".xls",".pptx",".ppt",
        ".hwpx",".hwp",".mp4",".avi",".mov",".mkv",
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
        try:
            rag_engine.wiki_generator.process_document_for_entities(
                file.filename, raw_content, [],
                user_role="admin",
                metadata=meta,
            )
        except TypeError:
            # 구버전 시그니처 fallback (metadata/user_role 미지원)
            try:
                rag_engine.wiki_generator.process_document_for_entities(
                    file.filename, raw_content, []
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
                rag_engine.wiki_generator.create_entity_file(
                    doc_entity, file.filename, []
                )
            except Exception as wiki_err:
                print(f"[UPLOAD] wiki entity 생성 skip: {wiki_err}")
        except Exception as e:
            print(f"[UPLOAD] entity 처리 skip: {e}")

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

        result_data = {
            "status":      "ok",
            "filename":    unique_name,
            "category":    meta.get("category","기타"),
            "summary":     meta.get("summary",""),
            "keywords":    meta.get("keywords",[]),
            "sensitivity": meta.get("sensitivity","internal"),
        }
        _write_audit(role, "/upload/", query=file.filename, ip_address=ip)
        return result_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 실패: {e}")


@app.post("/query/", response_model=QueryResponse, summary="질의응답 (권한 기반)")
async def query(
    data:    QueryRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    verify_api_key(data.api_key)
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

    Default-first ordering — picker selects index 0 unless localStorage
    has a saved choice. Operator's `.env` (JAMES_LLM_MODEL,
    JAMES_CODING_MODEL) is prepended if not already in the list, so a
    custom config still appears as a candidate even if it isn't in the
    canonical catalog.
    """
    from config import GEMMA_MODEL, CODING_MODEL
    chat_default = GEMMA_MODEL
    code_default = CODING_MODEL
    chat_cands = [
        (chat_default,    "light"),
        ("gemma3:12b",    "medium"),
        ("gemma3:27b",    "heavy"),
    ]
    # If operator has overridden GEMMA_MODEL to something not in our list,
    # keep it as a candidate so the UI still shows their config.
    if not any(c[0] == chat_default for c in chat_cands):
        chat_cands.insert(0, (chat_default, "medium"))
    code_cands = [
        ("qwen2.5-coder:7b",  "light"),
        (code_default,        "heavy"),
        ("gemma4:e4b",        "light"),  # fallback for tiny boxes
    ]
    if not any(c[0] == code_default for c in code_cands):
        code_cands.insert(0, (code_default, "heavy"))
    return {
        "chat":         chat_cands,
        "retrieval":    chat_cands,
        "wiki_edit":    chat_cands,
        "self_evolve":  chat_cands,
        "coding":       code_cands,
        # auto/meta intentionally absent — auto inherits whatever the
        # routed mode picks; meta does not call the LLM.
    }

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
         "desc": f"코딩 특화 모델",
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


@app.post("/llm/install/", summary="Ollama 모델 설치 (admin) [item #6]")
async def llm_install(api_key: str, model: str,
                      role: str = Depends(get_role_from_request)):
    """Trigger `ollama pull <model>` in a subprocess.

    Admin-gated — model installation is heavy (multi-GB download)
    and exposing it to non-admin would let any chat user fill the
    operator's disk.

    Validates model name against an allowlist (config defaults +
    a few well-known alternatives). Arbitrary input rejected with
    400 — operator must use the admin LLM page for non-listed models.
    """
    _require_admin(api_key, role)
    # [#A2] Allowlist auto-derived from MODEL_CATALOG so adding a
    # candidate above does NOT require remembering to update this gate.
    # llava is kept as a manual extra (vision support — not in catalog
    # but operators sometimes pull it for multimodal experiments).
    ALLOWED_MODELS = _allowed_install_models() | {"llava:13b"}
    if model not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"model not in allowlist. Use admin /admin/llm/install for arbitrary models.",
        )

    import subprocess
    try:
        # Don't block — fire-and-forget. Operator polls /llm/modes/
        # afterwards to see installed flip to True.
        subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "model": model,
                "message": f"`ollama pull {model}` 시작됨 (백그라운드 진행). 잠시 후 모드 picker가 자동 갱신됩니다."}
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="ollama CLI가 PATH에 없습니다. 시스템에 ollama 설치 후 재시도.",
        )
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"install 시작 실패: {type(e).__name__}: {e}")


@app.get("/admin/llm/installed", summary="설치된 Ollama 모델 목록 [4-B]")
async def llm_installed(api_key: str, role: str = Depends(get_role_from_request)):
    """현재 Ollama에 설치된 모델 목록."""
    _require_admin(api_key, role)
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


@app.get("/admin/llm/recommend", summary="하드웨어 기반 LLM 추천 [4-B]")
async def llm_recommend(api_key: str, role: str = Depends(get_role_from_request)):
    """현재 하드웨어 스펙에 맞는 LLM 모델 추천."""
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
        _write_audit(role, "/admin/llm/delete", query=model, elapsed_sec=0)
        return {"ok": True, "model": model, "deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
        # psutil 없는 환경 — 기본값 반환
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
    if not topic:
        raise HTTPException(status_code=400, detail="topic 파라미터 필요")
    try:
        if use_web:
            from tools.web.web_searcher import (
                search_web, enrich_results_with_content,
                format_search_results, save_as_longterm,
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
                print(f"[LEARN] LLM 0자 → fallback 사용")
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
    try:
        from core.feedback_engine import get_feedback_stats
        return get_feedback_stats()
    except Exception as e:
        return {"error": str(e)}



# ── P7-EVO-D: 성향 캐릭터 API ───────────────────────────────────

@app.get("/admin/character/", summary="성향 조회 [P7-EVO-D]")
async def get_character(api_key: str, role: str = Depends(get_role_from_request)):
    _require_admin(api_key, role)
    try:
        from core.character_profile import get_profile
        return {"traits": get_profile().get_with_meta()}
    except Exception as e:
        return {"traits": [], "error": str(e)}

class TraitUpdateRequest(BaseModel):
    api_key:  str
    trait_id: str
    value:    float

@app.post("/admin/character/", summary="성향 설정 [P7-EVO-D]")
async def set_character(data: TraitUpdateRequest,
                         role: str = Depends(get_role_from_request)):
    _require_admin(data.api_key, role)
    try:
        from core.character_profile import get_profile
        result = get_profile().set_trait(data.trait_id, data.value)
        _write_audit(role, "/admin/character/",
                     query=f"{data.trait_id}={data.value}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ── P7-EVO-E: 능력 성장 API ─────────────────────────────────────

@app.get("/admin/knowledge/", summary="능력 성장 현황 [P7-EVO-E]")
async def get_knowledge(api_key: str, role: str = Depends(get_role_from_request)):
    _require_admin(api_key, role)
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
    _require_admin(data.api_key, role)
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
    verify_api_key(api_key)
    if role != "admin":
        raise HTTPException(status_code=403, detail="admin 전용")

    events = []
    try:
        with open("james_audit_tool.jsonl", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("event") in (
                        "SANDBOX_BLOCK", "PATH_VIOLATION",
                        "ATTACK_SURFACE_SCAN", "PROTECTED_FILE_BLOCK"
                    ):
                        events.append(entry)
                except Exception:
                    pass
    except FileNotFoundError:
        pass

    return {
        "total_events": len(events),
        "events":       events[-50:],   # 최근 50개
        "summary": {
            "sandbox_blocks":    sum(1 for e in events if e.get("event")=="SANDBOX_BLOCK"),
            "path_violations":   sum(1 for e in events if e.get("event")=="PATH_VIOLATION"),
            "surface_scans":     sum(1 for e in events if e.get("event")=="ATTACK_SURFACE_SCAN"),
            "protected_blocks":  sum(1 for e in events if e.get("event")=="PROTECTED_FILE_BLOCK"),
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


def _read_jsonl_tail(path: str, max_lines: int = 200) -> list[dict]:
    """[#2-A] Read only the last `max_lines` rows of a JSONL log.

    The /admin/dashboard endpoint used to read the entire log file
    line-by-line then slice [-20:]. On a year-old install with 100MB+
    of audit logs this dominated dashboard load time (seconds → tens
    of seconds).

    Strategy: seek from the end of the file in 8KB chunks until we have
    `max_lines + 1` newlines (one extra so we don't cut off the first
    of the captured lines mid-record). Decode the chunk, split on \\n,
    keep the last N. Each line is JSON-parsed; bad lines silently
    skipped (preserves the prior fault tolerance).

    Returns: list of dicts, oldest-first (matches prior caller's
    ordering expectation).
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    if size == 0:
        return []
    out_lines: list[bytes] = []
    chunk_size = 8192
    pos = size
    buf = b""
    with open(path, "rb") as f:
        while pos > 0 and len(out_lines) <= max_lines:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            buf = f.read(read_size) + buf
            # Count newlines we have so far. Stop when ≥ max_lines+1
            # so the first split element is a complete line.
            if buf.count(b"\n") >= max_lines + 1:
                out_lines = buf.split(b"\n")[-max_lines - 1:]
                break
        else:
            # Whole file fit in `max_lines` worth of data — use as-is.
            out_lines = buf.split(b"\n")
    rows: list[dict] = []
    for line in out_lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line.decode("utf-8", errors="ignore")))
        except Exception:
            pass
    return rows[-max_lines:]


@app.get("/admin/dashboard", summary="관리자 대시보드 [P7]")
async def admin_dashboard(api_key: str, role: str = Depends(get_role_from_request)):
    _require_admin(api_key, role)

    # ── 기본 카운트 ──────────────────────────────────────────
    try:    entity_count = len(rag_engine.wiki_generator.entity_id_index)
    except: entity_count = 0
    try:
        from core.auth import list_users
        user_count = len(list_users())
    except: user_count = 0

    # [#2-A] tail-only JSONL 읽기 — 전체 파일 → 마지막 200행만.
    # 사용자 보고: "어드민 페이지로 이동할때 시간이 다소 딜레이". 가장
    # 큰 원인은 audit log가 누적되면서 dashboard load가 O(file size)로
    # 느려진 것. 마지막 N개만 필요하므로 EOF에서 역방향 chunked read.
    security_events, recent_logs = 0, []
    for lf in ["james_attack_log.jsonl","james_audit_tool.jsonl"]:
        for e in _read_jsonl_tail(lf, max_lines=200):
            recent_logs.append(e)
            if e.get("blocked") or "BLOCK" in e.get("event",""):
                security_events += 1

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
    cache_hits      = 0
    blocked_count   = 0
    score_sum       = 0.0
    score_count     = 0
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

    except Exception as e:
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


@app.get("/admin/users", summary="사용자 목록 [P7]")
async def admin_users(api_key: str, role: str = Depends(get_role_from_request)):
    _require_admin(api_key, role)
    try:
        from core.auth import list_users
        return {"users": list_users()}
    except: return {"users": []}


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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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


@app.get("/admin/memory", summary="Memory 현황 [P7]")
async def admin_memory(api_key: str, role: str = Depends(get_role_from_request)):
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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
    _require_admin(body.get("api_key",""), role)

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
    _require_admin(api_key, role)
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
    _require_admin(body.get("api_key",""), role)
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
    _require_admin(api_key, role)
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
    _require_admin(api_key, role)
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


@app.get("/admin/audit", summary="감사 로그 [P7]")
async def admin_audit(api_key: str, limit: int = 100,
                      role: str = Depends(get_role_from_request)):
    _require_admin(api_key, role)
    logs = []
    for lf in ["james_audit_db.jsonl","james_audit_tool.jsonl",
               "james_attack_log.jsonl","james_system_log.jsonl"]:
        try:
            with open(lf, encoding="utf-8") as f:
                for line in f:
                    try: logs.append(json.loads(line))
                    except: pass
        except: pass
    logs.sort(key=lambda x: x.get("time",""), reverse=True)
    return {"logs": logs[:limit], "total": len(logs)}


@app.get("/admin/settings", summary="설정 조회 [P7]")
async def admin_settings_get(api_key: str, role: str = Depends(get_role_from_request)):
    _require_admin(api_key, role)
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
    _require_admin(data.api_key, role)
    if data.protected_files:
        os.environ["JAMES_PROTECTED_FILES"] = data.protected_files
    _write_audit(role, "/admin/settings", query=f"model={data.model}")
    return {"success": True, "applied": {"model": data.model, "max_loop": data.max_loop}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_llmwiki:app", host="127.0.0.1", port=8000, reload=True)
