"""
PROJECT JAMES - JWT 인증 모듈 (Phase 4 + W4 P1-A)

Phase 4 변경:
  [P4-AUTH-1] USER_DB → SQLite 영구화
              서버 재시작 후 계정 유지
              DB 파일: james_users.db (BASE_DIR 기준)

  [P4-AUTH-2] X-Role 개발용 헤더 → 운영 모드에서 비활성화 설정 추가

JWT_SECRET는 Phase 3.5에서 이미 환경변수화 완료 (os.environ.get)

W4 P1-A 변경 (2026-05-11):
  비밀번호 해시 SHA256(salt 없음, rainbow-table 취약) → bcrypt.
  password_hash 컬럼에 알고리즘 prefix(`bcrypt$...`)를 두고, prefix 가
  없는 64-char hex 는 legacy SHA256 으로 인식한다. 로그인 성공 시점에
  legacy → bcrypt 로 transparent rehash 가 일어나므로 운영 중단 없이
  점진 마이그레이션 된다. signup endpoint 와 비번 정책은 별도 PR(P1-B).
"""

import os
import re
import sqlite3
import hashlib
import hmac
import json
import time
import base64
import bcrypt
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from pathlib import Path

# .env 자동 로드 보장 (config 모듈이 import 시점에 .env 파싱하여
# os.environ에 주입). server_llmwiki는 config을 명시 import하지만,
# core.auth만 단독 import되는 경로(테스트, 마이그레이션 스크립트 등)
# 에서도 환경변수가 살아있도록 side-effect import.
try:
    import config  # noqa: F401
except Exception:
    pass

# ─── 설정 ────────────────────────────────────────────────────

JWT_SECRET = os.environ.get("JAMES_JWT_SECRET")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    # P0 보안 (v0.1.3.1 handover Item A) — fail-fast.
    # 이전엔 하드코드 fallback이라 secret 미설정 환경에서 모든 JWT 서명이
    # 동일 시크릿으로 이뤄져 위조 공격에 무방비였음. 더이상 silent.
    raise RuntimeError(
        "JAMES_JWT_SECRET must be set to a string of 32+ characters "
        "before importing core.auth. Generate one with:\n"
        "    python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
        "Then set it in .env or as an environment variable."
    )
JWT_ALGO   = "HS256"
JWT_EXPIRE = 3600 * 8   # 8h. SECURITY.md와 일치.

# 운영 모드 플래그 (환경변수로 제어)
# JAMES_DEV_MODE=0 이면 X-Role 헤더 비활성화
DEV_MODE = os.environ.get("JAMES_DEV_MODE", "1") == "1"

ALLOWED_ROLES = {"admin", "manager", "employee", "external"}

# ─── [P4-AUTH-1] SQLite USER DB ──────────────────────────────

try:
    from config import BASE_DIR
    _DB_PATH = os.path.join(BASE_DIR, "james_users.db")
except ImportError:
    _DB_PATH = "james_users.db"

def _hash_sha256_legacy(pw: str) -> str:
    """[LEGACY, W4 P1-A] Pre-W4 unsalted SHA256 hex digest.

    Kept only so verify_password() can authenticate accounts created
    before bcrypt migration. New hashes always go through hash_password().
    Do not call this from new code.
    """
    return hashlib.sha256(pw.encode()).hexdigest()


def hash_password(pw: str) -> str:
    """bcrypt with algorithm prefix.

    Format: ``bcrypt$<bcrypt-output>``. The prefix lets verify_password()
    distinguish from pre-W4 SHA256 hex (no prefix, 64-char) and from any
    future algorithm without ambiguity.
    """
    h = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())
    return "bcrypt$" + h.decode("utf-8")


def verify_password(pw: str, stored: str) -> bool:
    """Verify a password against a stored hash.

    Handles both the new ``bcrypt$...`` form and the legacy unsalted
    SHA256 hex (exactly 64 hex chars, no prefix). Returns False on any
    parse error rather than raising — callers treat that as
    authentication failure.
    """
    if not stored:
        return False
    if stored.startswith("bcrypt$"):
        try:
            return bcrypt.checkpw(pw.encode("utf-8"), stored[7:].encode("utf-8"))
        except Exception:
            return False
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored):
        return hmac.compare_digest(_hash_sha256_legacy(pw), stored)
    return False


# Backward-compat alias. External callers (and existing tests) imported
# `_hash_password`; the name is preserved but now produces a bcrypt hash.
# Anyone comparing the return value byte-for-byte against another call
# will break (bcrypt salts every output); they should switch to
# verify_password(). Tracked for cleanup once those callers migrate.
_hash_password = hash_password


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    """DB 초기화 + admin 계정 1개 (랜덤 또는 환경변수, 첫 부팅 한 번만)."""
    import secrets as _secrets

    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username      TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL,
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

        # P0 보안 (v0.1.3.1 handover Item B) — admin 1개만, 랜덤 또는 환경변수.
        # 이전엔 admin/manager1/employee1/guest 4계정 평문 비번이 소스에 박혀
        # git log에서 누구나 볼 수 있었음. 이제:
        #   1) 첫 부팅 시 admin 1개만 생성. manager/employee/external은 admin이
        #      가입 endpoint로 직접 만들도록.
        #   2) JAMES_INIT_ADMIN_PW 환경변수 우선. 없으면 16-byte URL-safe 랜덤.
        #   3) 새로 생성된 경우에만 콘솔에 비번 출력 (기존 admin 있으면 무동작).
        env_pw   = os.environ.get("JAMES_INIT_ADMIN_PW")
        admin_pw = env_pw or _secrets.token_urlsafe(16)
        cur = conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, role) "
            "VALUES (?, ?, ?)",
            ("admin", _hash_password(admin_pw), "admin"),
        )
        admin_created = cur.rowcount > 0
        conn.commit()

        print(f"[AUTH] SQLite USER_DB 초기화: {_DB_PATH}")
        if admin_created and not env_pw:
            print(f"[AUTH] Initial admin password (CHANGE IMMEDIATELY): {admin_pw}")
        elif admin_created and env_pw:
            print("[AUTH] admin created from JAMES_INIT_ADMIN_PW")
    finally:
        conn.close()

# 서버 시작 시 DB 초기화
_init_db()

# ─── 사용자 조회 / 관리 ──────────────────────────────────────

def _get_user(username: str) -> Optional[Dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()

def add_user(username: str, password: str, role: str) -> bool:
    if role not in ALLOWED_ROLES:
        return False
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO users (username, password_hash, role, active) VALUES (?, ?, ?, 1)",
            (username, _hash_password(password), role),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[AUTH] add_user 오류: {e}")
        return False
    finally:
        conn.close()

def deactivate_user(username: str) -> bool:
    conn = _get_conn()
    try:
        conn.execute("UPDATE users SET active = 0 WHERE username = ?", (username,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


# ─── W4 P2-A: admin user-management helpers ────────────────────

def list_users(only_pending: bool = False) -> list:
    """Return every user row as a list of dicts, password hash omitted.

    The password column is excluded by name (not by post-filter) so that
    a future schema change adding another sensitive column has to be
    opted into explicitly. Sort is (active desc, username asc) so
    pending rows surface together for admin review.
    """
    conn = _get_conn()
    try:
        sql = (
            "SELECT username, role, active, created_at FROM users"
        )
        if only_pending:
            sql += " WHERE active = 0"
        sql += " ORDER BY active ASC, username ASC"
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def approve_user(username: str, role: str) -> bool:
    """Activate a pending user and assign a role.

    Only operates on rows with ``active=0``. Calling on an already-active
    row returns False — admins should use ``change_role`` for that case
    (deliberately scoped: approval is an audit-significant event and
    must not be silently re-fired).
    """
    if role not in ALLOWED_ROLES:
        return False
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET active = 1, role = ? "
            "WHERE username = ? AND active = 0",
            (role, username),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def reject_user(username: str) -> bool:
    """Delete a pending user row.

    Only operates on ``active=0``. Refusing to delete active users
    prevents a misclick from wiping a real account; the active-account
    workflow is ``deactivate_user`` instead. DELETE (not flag) is used
    so the same username can be retried as a fresh signup.
    """
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM users WHERE username = ? AND active = 0",
            (username,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ─── W4 P1-B: self-service signup + policy validation ─────────

# Hard upper bound chosen to match bcrypt's native 72-byte input window.
# Above that, bcrypt silently truncates — two distinct longer passwords
# would hash to the same value. Rejecting >72 keeps the verifier
# semantically honest. Lower bound 8 mirrors OWASP minimum and the
# reset_password CLI's pre-existing policy.
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 72
USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 32
USERNAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")


def validate_password_policy(pw: str) -> Optional[str]:
    """Return None if the password is acceptable, else a user-visible
    Korean error message. Policy is deliberately public — the error
    text can be shown to anonymous callers without leaking anything.

    Rules:
      - 8..72 characters (72 = bcrypt input window, see constant above)
      - must contain at least one letter and at least one digit
        (case + symbols not required, sacrificing some entropy for
        usability and Korean-keyboard reality)
    """
    if not isinstance(pw, str):
        return "비밀번호는 문자열이어야 합니다."
    if len(pw) < PASSWORD_MIN_LEN:
        return f"비밀번호는 최소 {PASSWORD_MIN_LEN}자 이상이어야 합니다."
    if len(pw) > PASSWORD_MAX_LEN:
        return f"비밀번호는 최대 {PASSWORD_MAX_LEN}자까지 허용됩니다."
    has_alpha = any(c.isalpha() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    if not (has_alpha and has_digit):
        return "비밀번호는 영문과 숫자를 각각 한 글자 이상 포함해야 합니다."
    return None


def validate_username(name: str) -> Optional[str]:
    """Return None if the username is acceptable, else a Korean message.

    Lowercase is enforced (not just preferred) so ``Admin`` and ``admin``
    can never coexist — the schema has no case-insensitive PK and we'd
    rather fail at signup than discover the collision at login.
    """
    if not isinstance(name, str):
        return "사용자명은 문자열이어야 합니다."
    if len(name) < USERNAME_MIN_LEN or len(name) > USERNAME_MAX_LEN:
        return f"사용자명은 {USERNAME_MIN_LEN}~{USERNAME_MAX_LEN}자여야 합니다."
    if not USERNAME_PATTERN.match(name):
        return ("사용자명은 영문 소문자·숫자·하이픈(-)·언더스코어(_) "
                "만 사용할 수 있습니다.")
    return None


@dataclass(frozen=True)
class SignupResult:
    """Outcome of a signup attempt.

    The server collapses ``ok`` and ``duplicate`` into the same response
    body so an anonymous caller cannot probe which usernames exist.
    The status field exists for audit logging, not for the response.
    """
    status: str                # "ok" | "duplicate" | "policy"
    error:  Optional[str] = None   # populated only when status == "policy"


def signup(username: str, password: str) -> SignupResult:
    """Create a pending user row (active=0, role=external).

    - Validates username + password against the public policy.
    - Refuses duplicates by silently leaving the existing row alone
      (the caller will report success either way — see SignupResult).
    - Never raises; DB failures are logged and reported as policy errors
      so the endpoint can return a 400, not a 500.
    """
    pw_err = validate_password_policy(password)
    if pw_err is not None:
        return SignupResult(status="policy", error=pw_err)
    name_err = validate_username(username)
    if name_err is not None:
        return SignupResult(status="policy", error=name_err)

    conn = _get_conn()
    try:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            return SignupResult(status="duplicate")

        conn.execute(
            "INSERT INTO users (username, password_hash, role, active) "
            "VALUES (?, ?, ?, 0)",
            (username, hash_password(password), "external"),
        )
        conn.commit()
        return SignupResult(status="ok")
    except sqlite3.IntegrityError:
        # Race: another request inserted the same username between the
        # SELECT and the INSERT. Treat as duplicate (the safe answer).
        return SignupResult(status="duplicate")
    except Exception as e:
        print(f"[AUTH] signup DB 오류: {e}")
        return SignupResult(status="policy",
                            error="가입 처리 중 오류가 발생했습니다.")
    finally:
        conn.close()

# ─── JWT 구현 ────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))

def _sign(data: str) -> str:
    sig = hmac.new(JWT_SECRET.encode(), data.encode(), hashlib.sha256).digest()
    return _b64url_encode(sig)

def create_token(username: str, role: str) -> str:
    header  = _b64url_encode(json.dumps({"alg": JWT_ALGO, "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub":  username,
        "role": role,
        "iat":  int(time.time()),
        "exp":  int(time.time()) + JWT_EXPIRE,
    }).encode())
    sig = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{sig}"

def verify_token(token: str) -> Optional[Dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts

        expected = _sign(f"{header}.{payload}")
        if not hmac.compare_digest(sig, expected):
            print("[AUTH] 서명 검증 실패")
            return None

        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            print("[AUTH] 토큰 만료")
            return None

        role = data.get("role", "external")
        if role not in ALLOWED_ROLES:
            print(f"[AUTH] 허용되지 않은 role: {role}")
            return None

        return {"sub": data.get("sub"), "role": role}
    except Exception as e:
        print(f"[AUTH] 토큰 파싱 오류: {e}")
        return None

# ─── 인증 ────────────────────────────────────────────────────

def _rehash_to_bcrypt(username: str, password: str) -> None:
    """Replace a legacy SHA256 hash with bcrypt on a verified login.

    Best-effort: any DB error is logged but does not block the login
    (the user has already authenticated successfully). Re-running this
    on subsequent logins is harmless — verify_password() will see the
    bcrypt prefix and skip migration entirely.
    """
    new_hash = hash_password(password)
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (new_hash, username),
        )
        conn.commit()
        print(f"[AUTH] legacy SHA256 → bcrypt rehashed: {username}")
    except Exception as e:
        print(f"[AUTH] bcrypt 마이그레이션 실패 (로그인은 성공): {e}")
    finally:
        conn.close()


def authenticate(username: str, password: str) -> Optional[Dict]:
    """로그인 → SQLite 조회 → token 반환"""
    user = _get_user(username)
    if not user:
        print(f"[AUTH] 사용자 없음: {username}")
        return None
    if not user.get("active"):
        print(f"[AUTH] 비활성 계정: {username}")
        return None

    stored = user["password_hash"]
    if not verify_password(password, stored):
        print(f"[AUTH] 비밀번호 불일치: {username}")
        return None

    if not stored.startswith("bcrypt$"):
        _rehash_to_bcrypt(username, password)

    role  = user["role"]
    token = create_token(username, role)
    print(f"[AUTH] 로그인 성공: {username} (role={role})")
    return {"token": token, "role": role, "username": username}

def get_role_from_token(token: str) -> str:
    data = verify_token(token)
    if data is None:
        return "external"
    return data.get("role", "external")

def get_current_role(authorization: str = "") -> str:
    if not authorization.startswith("Bearer "):
        return "external"
    token = authorization[7:].strip()
    return get_role_from_token(token)
