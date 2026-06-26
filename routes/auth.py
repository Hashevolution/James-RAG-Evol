"""Auth + upload + admin-user-mgmt routes.

Extracted from server_llmwiki.py per docs/design/v0.4.x-server-split.md
PR-A.1. 13 endpoints + 6 Pydantic models moved verbatim — handler body
byte-identical (only \`@app.<m>\` → \`@router.<m>\`, plus a 2-line
\`get_rag_engine() / get_file_processor()\` shim inside /upload/ which
is the only handler in this set that touches DI singletons).

URL invariant: \`python scripts/audit_endpoint_paths.py origin/main\`
must report 0-diff against the pre-PR-A.1 baseline.
"""
from __future__ import annotations

import os
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel
from typing import Optional

from config import MAX_UPLOAD_BYTES, UPLOAD_DIR
from core.http_heartbeat import stream_json_with_heartbeat
from core.api_keys import (
    issue_api_key as _api_key_issue,
    list_api_keys as _api_key_list,
    revoke_api_key as _api_key_revoke,
)
from core.auth import (
    ALLOWED_ROLES,
    approve_user as _auth_approve_user,
    authenticate,
    deactivate_user as _auth_deactivate_user,
    list_users as _auth_list_users,
    reject_user as _auth_reject_user,
    signup as _auth_signup,
)
from core.auth_reset import (
    RESET_TOKEN_TTL_SEC,
    change_password as _auth_change_password,
    consume_reset_token as _auth_consume_reset_token,
    issue_reset_token as _auth_issue_reset_token,
)
from core.policy_engine import default_engine
from routes._deps import get_file_processor, get_rag_engine
from routes._helpers import (
    _bearer_username,
    _require_feature,
    _write_audit,
    get_client_ip,
    get_role_from_request,
)

router = APIRouter()


# ─── Pydantic models ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    api_key:  str = ""   # 선택적

class LoginResponse(BaseModel):
    token:        str   # 기존 필드 유지
    access_token: str   # admin.js 호환용 (동일 값)
    role:         str
    username:     str

class SignupRequest(BaseModel):
    username: str
    password: str

class SignupResponse(BaseModel):
    ok:      bool
    # Identical message for success and duplicate (enumeration defense).
    # Policy-violation responses populate this with the specific reason
    # and return HTTP 400 instead of 200.
    message: str

class UploadResponse(BaseModel):
    status:      str
    filename:    str
    category:    str
    summary:     str
    keywords:    list
    sensitivity: str = "internal"

class AdminUserApproveRequest(BaseModel):
    username: str
    role:     str

class AdminUserRejectRequest(BaseModel):
    username: str

class AdminUserDeactivateRequest(BaseModel):
    username: str

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

class AdminIssueResetTokenRequest(BaseModel):
    username: str

class PasswordResetConfirmRequest(BaseModel):
    username:     str
    token:        str
    new_password: str

class ApiKeyIssueRequest(BaseModel):
    # Optional operator-supplied note ("ci-deploy", "laptop-2026-05"
    # etc.) so a leaked key can be tied to a context. Plain string —
    # rendered as text in the admin UI.
    label: Optional[str] = None

class ApiKeyRevokeRequest(BaseModel):
    key_prefix: str


# ─── Module-level constants ────────────────────────────────────────

_SIGNUP_ACCEPTED_MSG = "가입 요청이 접수되었습니다. 관리자 승인 후 사용 가능합니다."

# ─── Endpoints ─────────────────────────────────────────────────────

@router.post("/login/", response_model=LoginResponse, summary="로그인 (JWT 발급)")
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

@router.post("/signup/", response_model=SignupResponse,
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

@router.post("/upload/", response_model=UploadResponse, summary="파일 업로드 (admin 전용)")
async def upload(
    request:     Request,
    file:        UploadFile = File(...),
    api_key:     str        = Form(...),
    source_type: str        = Form("prod"),
    instruction: str        = Form(""),     # 챗 저장 지시 (선택)
    role:        str        = Depends(get_role_from_request),
):
    # v0.4.x server-split PR-A.1 — singletons fetched via DI getters
    # (set_*-registered in server_llmwiki.py boot). Handler body
    # byte-identical past this 3-line shim.
    rag_engine = get_rag_engine()
    file_processor = get_file_processor()
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

    # Run the slow ingest (vision OCR / entity extraction, ~30-60s) in a
    # worker thread + heartbeat the connection so a mobile/Tailscale tunnel
    # does not drop the upload mid-process (which left the composer chip
    # stuck even though the server finished). Validation/size/auth errors
    # already raised above with proper status before streaming starts.
    def _work():
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
            # Phase D — extraction sidecar 경로. 물리 파일 옆에 `<uuid>_<file>
            # .extraction.json` 으로 저장 → 재업로드 시 modify cascade 가 이
            # 파일을 읽어 old/new triple diff 를 한다.
            extraction_sidecar = os.path.join(
                UPLOAD_DIR, unique_name + ".extraction.json",
            )
            try:
                created_entity_ids = list(
                    rag_engine.wiki_generator.process_document_for_entities(
                        file.filename, raw_content, [],
                        user_role="admin",
                        metadata=meta,
                        extraction_sidecar_path=extraction_sidecar,
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
    return await stream_json_with_heartbeat(_work)

@router.get("/admin/users", summary="사용자 목록 (W4 P2-A: real implementation)")
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

@router.post("/admin/users/approve", summary="사용자 가입 승인 (W4 P2-A)")
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

@router.post("/admin/users/reject", summary="사용자 가입 거부 (W4 P2-A)")
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

@router.post("/admin/users/deactivate", summary="사용자 비활성화 (W4 P2-A)")
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

@router.post("/password/change",
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

@router.post("/admin/users/issue-reset-token",
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

@router.post("/password/reset/confirm",
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

@router.post("/api-keys/issue",
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

@router.get("/api-keys/list", summary="내 API 키 목록 (W4 P3-1)")
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

@router.post("/api-keys/revoke",
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
