"""Shared auth + audit helpers extracted from server_llmwiki.py.

These helpers were defined inline in server_llmwiki.py before the v0.4.x
server-split cycle (docs/design/v0.4.x-server-split.md, Stage 0). They
move here so routes/<domain>.py can import them without circular
dependency back into the server module.

server_llmwiki.py re-imports them for back-compat — any handler still
inline in the server module continues to use the same names.

Invariant: function signatures + behaviour byte-identical to the
pre-split definitions. The 24 `_write_audit` emit sites elsewhere in
the codebase must not see any timing or field shift.
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import API_KEY, BASE_DIR
from core.api_keys import verify_api_key as _api_key_verify
from core.auth import (
    ALLOWED_ROLES,
    DEV_MODE,
    get_role_from_token,
    verify_token as _auth_verify_token,
)
from core.policy_engine import default_engine

# Single source of truth for the bearer scheme. Both server_llmwiki.py
# and routes/<domain>.py import it from here so Depends(bearer_scheme)
# always references the same callable instance.
bearer_scheme = HTTPBearer(auto_error=False)

_AUDIT_DB = os.path.join(BASE_DIR, "james_audit.db")


# ─── Audit ──────────────────────────────────────────────────────────

def _write_audit(
    user_role: str,
    endpoint:  str,
    query:     str   = "",
    answer:    str   = "",
    graph_paths: list = None,
    blocked:   bool  = False,
    security_event: str = "",
    elapsed_sec: float = 0.0,
    ip_address: str  = "",
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


# ─── Request introspection ──────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Resolve the request's client IP for rate-limit + audit.

    **v0.6 Phase 1 P1.2 security fix**: this helper previously
    blindly trusted ``X-Forwarded-For`` from any client, letting
    attackers bypass the per-IP rate limiter and spoof audit
    `ip_address` rows. As of v0.6 the
    :class:`core.security.forwarded.TrustedForwardedHeadersMiddleware`
    runs first on every request and rewrites
    ``request.client.host`` to the *true* client IP (the right-most
    untrusted hop from ``X-Forwarded-For``) — but ONLY when the
    immediate ASGI peer is in the operator-configured
    ``JAMES_TRUSTED_PROXIES`` list.

    With the middleware wired (production reverse-proxy
    deployments), ``request.client.host`` is already correct and
    this helper is a thin pass-through. With the middleware bypassed
    (single-process dev, untrusted peer), the helper returns the
    direct peer — which is the safe semantic.

    See ``docs/deployment/v0.6-https-production.md`` for the
    operator-side wire-in.
    """
    return request.client.host if request.client else "unknown"


def _bearer_username(request: Request) -> Optional[str]:
    """Pull `sub` (username) out of the Bearer JWT, or None.

    Used to scope per-account operations to the JWT subject rather than
    a body field so the client cannot self-impersonate.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    payload = _auth_verify_token(auth_header[7:].strip())
    return (payload or {}).get("sub") if payload else None


# ─── API key + role resolution ──────────────────────────────────────

def verify_api_key(api_key: str):
    """Accept either the system API_KEY or a per-user ``jms_...`` key.

    Raises 403 if neither matches. Only validates the credential;
    role-based authorization continues to consult
    ``get_role_from_request`` (system key → external, user key → owner
    role).
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
    without raising on miss.
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
        # admin endpoints. Role here is currently NOT consumed
        # (get_role_from_request only honors source == "user").
        # [default-deny fallback 2026-05-18] employee → external.
        return {"source": "system", "username": "system", "role": "external"}
    return None


def get_role_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_role: Optional[str] = Header(None, alias="X-Role"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """JWT > user API key > X-Role (dev) > default external.

    [W4 P3-2] User API keys (``jms_...``) now surface the owner's
    role to authorization gates. The system key remains external
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

    # [default-deny fallback 2026-05-18] external (not employee) so the
    # internal_rag gate fires correctly for anonymous callers — see the
    # historical note in PR-O5 (cycle 12, #292).
    return "external"


# ─── Admin / feature gates ──────────────────────────────────────────

def _require_admin(api_key: str, role: str):
    """Admin API 접근 검증. api_key 검증 + role=admin 체크."""
    verify_api_key(api_key)
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="admin 권한 필요 — admin 계정으로 로그인하세요",
        )


def _require_feature(api_key: str, role: str, feature_id: str):
    """[W4-Q2] api_key + per-feature gate (consults PolicyEngine).

    For features whose default_allowed is ``{"admin"}``, behaviour is
    identical to ``_require_admin``. New admin.* features land here
    instead so the policy matrix is the single source of truth.
    """
    verify_api_key(api_key)
    d = default_engine.can_use_feature(role, feature_id)
    if not d.allowed:
        raise HTTPException(
            status_code=403,
            detail=f"권한이 부족합니다. ({feature_id})",
        )
