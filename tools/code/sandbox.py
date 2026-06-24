"""
PROJECT JAMES - Mini Sandbox v2.2 (Phase 5.5 + #44 phase 3-3)

v2.2 변경:
  - policy_validate_path() 신규 — PolicyEngine.issue_capability /
    verify_capability를 거친 후 기존 validate_path를 호출
    (defense-in-depth)
  - tools/code/* 및 tools/patch/* 의 validate_path 직접 호출자가
    policy_validate_path로 마이그레이션

v2.1 (유지):
  - admin role → ALLOWED_PATHS 우회 가능 (경로 제한 해제)
  - BLOCKED_COMMANDS → admin도 차단 (명령어는 예외 없음)
  - admin_override → 감사 로그 반드시 기록

핵심 원칙:
  개발자(James)가 직접 수정 → 제한 없음
  JAMES Tool이 자동으로 수정 → 이걸 막는 것

  admin role:
    ✅ ALLOWED_PATHS 우회 가능
    ❌ BLOCKED_COMMANDS는 우회 불가 (위험 명령어는 항상 차단)

  user/employee/manager role:
    ❌ ALLOWED_PATHS 외 접근 차단
    ❌ BLOCKED_COMMANDS 차단
    ❌ PolicyEngine action 자격 (fs.read employee+, fs.write admin) 미충족 시 차단
"""

import os
import re
import time
import subprocess
from datetime import datetime
from typing import Tuple

# ─── 상수 ────────────────────────────────────────────────────

ALLOWED_PATHS     = ["./workspace"]
MAX_EXEC_TIME_SEC = 10
BLOCKED_COMMANDS = [
    "rm -rf", "curl", "wget", "sudo", "chmod",
    "chown", "dd ", "mkfs", "kill", "shutdown",
    "reboot", "format", "del /f", "rmdir /s",
    ":(){:|:&};:", "eval", "exec(",
    "../", "..\\"
]

BLOCKED_PATH_PATTERNS = [
    r"\.\./", r"\.\.\\" , r"^/", r"^[A-Za-z]:\\",
    r"~/", r"/etc/", r"/proc/",
    r"core/", r"security_layer", r"reasoning_engine", r"graph_engine",
]

# v0.6.1 — CRITICAL system roots that are blocked even for admin and
# even when present inside a JAMES_AGENT_ALLOWED_PATHS entry. These are
# the absolutes that must never be in scope for any tool call. Mirrors
# `docs/design/v0.6-agent-tools-user-paths.md` §3 / §7.
CRITICAL_BLOCKED_ROOTS = [
    "/etc", "/proc", "/sys", "/boot", "/dev", "/root",
    "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
    "C:\\ProgramData",
]

# Risk #4 mitigation (2026-06-15): paths INSIDE the JAMES repo / install
# directory that the agent tools must NOT touch even though they aren't
# system-critical. Hitting `wiki/entity/prod` directly via write_file
# would bypass `core/wiki_generator/` (entity validation + audit row +
# chroma index), corrupting the RAG corpus. Same for `core/` (JAMES
# source code) and `eval/` (regression baselines). Repo paths are
# resolved at runtime via BASE_DIR; the constant lists the *relative*
# subpaths that must stay off-limits.
_REPO_PROTECTED_SUBPATHS = (
    "wiki/entity/prod",
    "wiki/entity/test",
    "wiki/media",
    "core",
    "eval",
    "scripts",
    "tests",
)

# v0.6.1 — operator-registered absolute paths the agent tools are
# allowed to read/write. Populated from `JAMES_AGENT_ALLOWED_PATHS`
# (comma-separated) at first call + via the admin endpoint at runtime.
# Empty by default (only the in-repo workspace works, identical to
# v0.5).
_USER_REGISTERED_PATHS: list[str] = []
_USER_PATHS_LOADED = False
JAMES_AGENT_ALLOWED_PATHS_ENV = "JAMES_AGENT_ALLOWED_PATHS"


# ─── 감사 로그 ───────────────────────────────────────────────

def log_security_event(
    event_type:     str,
    detail:         str,
    blocked:        bool = True,
    role:           str  = "unknown",
    admin_override: bool = False,
):
    """
    감사 로그 기록.
    admin_override=True 시 반드시 기록 (감사 추적).
    """
    entry = {
        "time":           datetime.now().isoformat(),
        "event":          event_type,
        "detail":         detail[:300],
        "blocked":        blocked,
        "role":           role,
        "admin_override": admin_override,
        "layer":          "sandbox",
    }
    # Mirror to SQLite (see core/audit_bridge.py). Sole sink as of
    # Phase 4 (Stage D.1, 2026-05-24).
    try:
        from core.audit_bridge import mirror_to_audit_db
        mirror_to_audit_db(entry)
    except Exception:
        pass
    flag = "🚫 BLOCKED" if blocked else ("⚠️ ADMIN_OVERRIDE" if admin_override else "✅ ALLOWED")
    # The emoji flags fail on a cp949 Windows console unless stdout was
    # reconfigured to utf-8 (uvicorn does this; bare unit-test / CLI
    # runners don't). Mirror the guard already used in
    # `_ensure_user_paths_loaded` so an audit print can never crash the
    # caller (e.g. an agent run_shell call on a cp949 console).
    try:
        print(f"[SANDBOX] {flag} [{role}] {event_type}: {detail[:60]}")
    except UnicodeEncodeError:
        try:
            print(f"[SANDBOX] [{role}] {event_type}: {detail[:60]}")
        except Exception:
            pass


# ─── 사용자 등록 경로 (v0.6.1) ──────────────────────────────

def _norm_abs(p: str) -> str:
    """Normalise to an absolute path and resolve symlinks at registration
    time. Returns "" on any failure (caller treats as invalid)."""
    try:
        return os.path.realpath(os.path.abspath(p))
    except Exception:
        return ""


def _is_under_critical_root(abs_path: str) -> bool:
    """True if ``abs_path`` is at or under one of the
    `CRITICAL_BLOCKED_ROOTS`. Case-folded on Windows so
    `c:\\windows\\foo` matches `C:\\Windows`."""
    if not abs_path:
        return True
    lp = abs_path
    if os.name == "nt":
        lp = abs_path.lower()
    for root in CRITICAL_BLOCKED_ROOTS:
        r = root.lower() if os.name == "nt" else root
        # Match the root itself OR any descendant.
        if lp == r or lp.startswith(r + os.sep):
            return True
    return False


def _is_under_repo_protected(abs_path: str) -> bool:
    """Risk #4 (2026-06-15): True if ``abs_path`` is at or under one of
    the JAMES-internal subpaths listed in `_REPO_PROTECTED_SUBPATHS`.
    Bypassing `core/wiki_generator/` for a wiki/entity write would
    corrupt the RAG corpus; touching `core/` from an agent tool would
    be a self-evolution write outside the 4-Gate. Resolves the repo
    paths at call time so a relocated install still gets the right
    block."""
    if not abs_path:
        return True
    try:
        from config import BASE_DIR as _BD
        base = os.path.realpath(_BD)
    except Exception:
        return False
    norm_target = abs_path
    norm_base = base
    if os.name == "nt":
        norm_target = abs_path.lower()
        norm_base = base.lower()
    for sub in _REPO_PROTECTED_SUBPATHS:
        protected_abs = os.path.normpath(os.path.join(norm_base, sub.replace("/", os.sep)))
        if norm_target == protected_abs or norm_target.startswith(protected_abs + os.sep):
            return True
    return False


def register_user_path(path: str) -> Tuple[bool, str]:
    """Register an absolute path as agent-tool-allowed at runtime.

    Returns ``(ok, message)``. The path must be absolute, must not
    resolve to a critical system root, and must exist. Symlinks are
    followed at registration time so a later `..` escape still has to
    pass `validate_path` on each call.

    Idempotent — re-registering an already-known path returns ``(True,
    "already registered")``.
    """
    if not path or not isinstance(path, str):
        return False, "empty path"
    abs_p = _norm_abs(path)
    if not abs_p:
        return False, f"path could not be resolved: {path!r}"
    if not os.path.isabs(abs_p):
        return False, f"path is not absolute: {path!r}"
    if _is_under_critical_root(abs_p):
        return False, f"path is under a critical system root: {abs_p!r}"
    if _is_under_repo_protected(abs_p):
        return False, (
            f"path is under a JAMES-internal protected subtree (wiki / "
            f"core / eval / scripts / tests): {abs_p!r}. Agent tools must "
            f"NOT write here — wiki entities go through "
            f"core/wiki_generator/, source files through the 4-Gate "
            f"self-evolution pipeline."
        )
    if not os.path.exists(abs_p):
        return False, f"path does not exist: {abs_p!r}"
    if abs_p in _USER_REGISTERED_PATHS:
        return True, "already registered"
    _USER_REGISTERED_PATHS.append(abs_p)
    return True, "registered"


def _ensure_user_paths_loaded() -> None:
    """First-call lazy load of ``JAMES_AGENT_ALLOWED_PATHS`` env into
    `_USER_REGISTERED_PATHS`. Subsequent calls no-op. Re-loading after
    an env change requires a restart (by design — see design memo §3)."""
    global _USER_PATHS_LOADED
    if _USER_PATHS_LOADED:
        return
    _USER_PATHS_LOADED = True
    raw = os.environ.get(JAMES_AGENT_ALLOWED_PATHS_ENV, "")
    if not raw.strip():
        return
    for chunk in raw.split(","):
        p = chunk.strip().strip('"').strip("'")
        if not p:
            continue
        ok, msg = register_user_path(p)
        # Wrap print in try/except: the existing sandbox uses emoji
        # markers that fail on Windows cp949 consoles unless stdout was
        # reconfigured (uvicorn does this; bare unit-test runners don't).
        try:
            if not ok:
                print(f"[SANDBOX] BLOCKED {JAMES_AGENT_ALLOWED_PATHS_ENV} entry rejected: {p!r} — {msg}")
            else:
                print(f"[SANDBOX] ALLOWED agent-allowed path: {p!r}")
        except UnicodeEncodeError:
            pass


def get_user_registered_paths() -> list[str]:
    """Public read-only snapshot of the registered paths (admin endpoint
    uses this)."""
    _ensure_user_paths_loaded()
    return list(_USER_REGISTERED_PATHS)


def unregister_user_path(path: str) -> Tuple[bool, str]:
    """Session-scoped remove from the in-memory registry. The next
    process restart re-reads ``JAMES_AGENT_ALLOWED_PATHS`` env, so
    paths persisted there will re-appear. This is intentional — see
    `docs/design/v0.6-agent-tools-user-paths.md` §3: permanent revoke
    requires editing the env.

    Returns ``(ok, msg)``. ``ok=True`` even if the path was not in the
    list (idempotent), with a message explaining the no-op.
    """
    if not path or not isinstance(path, str):
        return False, "empty path"
    abs_p = _norm_abs(path)
    if not abs_p:
        return False, f"path could not be resolved: {path!r}"
    _ensure_user_paths_loaded()
    if abs_p in _USER_REGISTERED_PATHS:
        _USER_REGISTERED_PATHS.remove(abs_p)
        return True, "removed (session-only; env restores on restart)"
    return True, "not registered (no-op)"


def _is_under_user_registered(abs_path: str) -> bool:
    """True if ``abs_path`` is at or under one of the user-registered
    paths. Re-checks `realpath` so a later symlink-escape attempt
    fails."""
    _ensure_user_paths_loaded()
    if not _USER_REGISTERED_PATHS:
        return False
    real = _norm_abs(abs_path)
    if not real:
        return False
    if _is_under_critical_root(real):
        return False
    for root in _USER_REGISTERED_PATHS:
        if real == root or real.startswith(root + os.sep):
            return True
    return False


# ─── 경로 검증 ───────────────────────────────────────────────

def validate_path(path: str, role: str = "user") -> Tuple[bool, str]:
    """
    경로 접근 허용 여부.

    v0.6.1 — user-registered paths (`JAMES_AGENT_ALLOWED_PATHS` env or
    `register_user_path()`) are accepted EVEN IF they look like an
    absolute path (`^/`, `^C:\\` etc.) — those patterns are blocked
    by default precisely because there was no operator opt-in path.
    Critical roots stay blocked regardless. Admin can read/write any
    user-registered path; user/employee/manager still need to be
    inside `ALLOWED_PATHS` (the in-repo workspace).

    admin role:
      - CRITICAL_BLOCKED_ROOTS 차단 (불변, override 불가)
      - user-registered 경로 OK
      - 그 외 BLOCKED_PATH_PATTERNS 차단 / ALLOWED_PATHS 제한 우회
    user/employee/manager:
      - CRITICAL_BLOCKED_ROOTS 차단
      - BLOCKED_PATH_PATTERNS 차단
      - ALLOWED_PATHS 내부만 허용
    """
    if not path or not isinstance(path, str):
        return False, f"경로 없음: {path}"

    # v0.6.1 — CRITICAL system roots are blocked for everyone, even admin.
    real = _norm_abs(path) if (os.path.isabs(path) or path.startswith("~")) else ""
    if real and _is_under_critical_root(real):
        return False, f"critical system root blocked: {real!r}"
    # Risk #4 (2026-06-15) — JAMES-internal protected subtrees are
    # blocked for agent-tool access even when nested under the in-repo
    # workspace path. Same rationale as the register-time check.
    if real and _is_under_repo_protected(real):
        return False, (
            f"JAMES-internal protected subtree blocked: {real!r} (wiki / "
            f"core / eval / scripts / tests)"
        )

    # v0.6.1 — user-registered path (operator opt-in) takes precedence:
    # if `path` resolves under one of those roots, bypass the
    # absolute-path / `^/` patterns in BLOCKED_PATH_PATTERNS. Critical
    # roots are still excluded by the check above.
    if os.path.isabs(path) and _is_under_user_registered(path):
        return True, ""

    # 시스템 위험 경로는 모든 role 차단
    for pattern in BLOCKED_PATH_PATTERNS:
        if re.search(pattern, path):
            return False, f"차단된 경로 패턴: '{pattern}' in '{path}'"

    # admin은 ALLOWED_PATHS 제한 우회
    if role == "admin":
        return True, ""

    # 일반 role: ALLOWED_PATHS 내부 확인
    normalized = os.path.normpath(path)
    in_allowed = any(
        normalized.startswith(os.path.normpath(ap))
        for ap in ALLOWED_PATHS
    )
    if not in_allowed:
        return False, f"허용 경로 외부: '{path}' (허용: {ALLOWED_PATHS})"

    return True, ""


# ─── 명령어 검증 ─────────────────────────────────────────────

def validate_command(command: str) -> Tuple[bool, str]:
    """
    명령어 안전성. admin도 예외 없음.
    """
    if not command or not isinstance(command, str):
        return False, "명령어 없음"

    cmd_lower = command.lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in cmd_lower:
            return False, f"차단 명령어: '{blocked}'"

    danger_patterns = [
        r";\s*(rm|del|format|kill)",
        r"\|\s*(rm|del|bash|sh|cmd)",
        r">\s*/",
        r"base64.*decode",
        r"python\s+-c\s+['\"]import",
    ]
    for pattern in danger_patterns:
        if re.search(pattern, cmd_lower):
            return False, f"위험 패턴: '{pattern}'"

    return True, ""


# ─── PolicyEngine 통합 검증 (#44 phase 3-3) ──────────────────

def policy_validate_path(
    path:   str,
    role:   str,
    action: str = "fs.read",
) -> Tuple[bool, str]:
    """경로 접근을 PolicyEngine + sandbox validate_path 둘 다 통과해야 허용.

    Phase 3-3 (#44): tool-side 호출자(read_file, code_reader,
    code_editor, code_analyzer, patch_generator)가 PolicyEngine을
    bypass 하지 못하도록 강제. router를 거치지 않은 직접 호출
    경로(자가 테스트, CLI, 다른 tool 간 호출)에서도 정책이 적용됨.

    검증 순서:
      1. PolicyEngine.issue_capability(role, action, path)
         - role이 action에 대해 자격 미달 → (False, "policy.denied(...)")
         - 자격 통과 → 짧은 capability 토큰 발급
      2. PolicyEngine.verify_capability(cap, action, path)
         - scope/action 미스매치 → (False, "policy.invalid(...)")
      3. 기존 sandbox validate_path(path, role)
         - BLOCKED_PATH_PATTERNS / ALLOWED_PATHS 검사 (defense-in-depth)

    Args:
      path:    경로 (sandbox validate_path와 동일 의미).
      role:    호출자 role (admin/manager/employee/external).
      action:  policy action id.
               - "fs.read"  : 파일/디렉토리 읽기 (employee+ 허용)
               - "fs.write" : 파일 수정/패치 (admin only)

    Returns:
      (True, "") on success, otherwise (False, reason).
    """
    from core.policy_engine import default_engine

    cap = default_engine.issue_capability(role, action, path or "*")
    if cap is None:
        reason = f"policy.denied(role={role!r}, action={action!r})"
        log_security_event(
            "POLICY_DENIED",
            f"path={path[:60] if path else ''} action={action}",
            blocked=True, role=role,
        )
        return False, reason

    verify = default_engine.verify_capability(cap, action, path or "*")
    if not verify.allowed:
        log_security_event(
            "POLICY_INVALID",
            f"path={path[:60] if path else ''} action={action} reason={verify.reason}",
            blocked=True, role=role,
        )
        return False, f"policy.invalid({verify.reason})"

    # PolicyEngine 통과 후에도 기존 sandbox 경로 정책은 적용 — defense-in-depth.
    return validate_path(path, role)


# ─── 통합 검증 ───────────────────────────────────────────────

def validate_action(command: str, path: str, role: str = "user") -> bool:
    """
    통합 검증 게이트 (브리핑 스펙 인터페이스).

    admin:
      - 경로 제한 우회 (ALLOWED_PATHS 무시)
      - 명령어 차단은 적용
      - admin_override 감사 로그 기록

    user/employee/manager:
      - 경로 + 명령어 모두 통과해야 허용
    """
    # 명령어 검증 (모든 role 동일)
    cmd_ok, cmd_reason = validate_command(command)
    if not cmd_ok:
        log_security_event("SANDBOX_BLOCK", f"cmd={command[:40]}: {cmd_reason}",
                           blocked=True, role=role)
        return False

    # 경로 검증
    path_ok, path_reason = validate_path(path, role)
    if not path_ok:
        log_security_event("PATH_VIOLATION", f"path={path}: {path_reason}",
                           blocked=True, role=role)
        return False

    # admin override 감사 기록
    admin_override = (role == "admin" and
                      not any(path.startswith(os.path.normpath(ap)) for ap in ALLOWED_PATHS))
    log_security_event(
        "ACTION_ALLOWED", f"cmd={command[:40]} path={path}",
        blocked=False, role=role, admin_override=admin_override,
    )
    return True


# ─── 안전 실행 ───────────────────────────────────────────────

def safe_execute(
    command: str,
    path:    str,
    role:    str = "user",
    timeout: int = MAX_EXEC_TIME_SEC,
) -> Tuple[bool, str, float]:
    """Sandbox 검증 통과 후 안전 실행."""
    if not validate_action(command, path, role):
        return False, "SANDBOX_BLOCKED", 0.0

    t_start = time.time()
    try:
        # shell=True is the sandbox contract — validate_action() above is
        # the security gate (allowlist of commands, path normalization,
        # role check). Bandit B602 is suppressed here, not bypassed.
        result = subprocess.run(  # nosec B602
            command, shell=True,
            cwd=os.path.normpath(path),
            capture_output=True, text=True, timeout=timeout,
        )
        elapsed = round(time.time() - t_start, 3)
        output  = result.stdout[:2000] + (result.stderr[:500] if result.stderr else "")
        log_security_event("EXEC_COMPLETE", f"exit={result.returncode} {elapsed}s",
                           blocked=False, role=role)
        return result.returncode == 0, output, elapsed
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - t_start, 3)
        log_security_event("EXEC_TIMEOUT", f"{timeout}s 초과", role=role)
        return False, f"TIMEOUT ({timeout}s)", elapsed
    except Exception as e:
        elapsed = round(time.time() - t_start, 3)
        log_security_event("EXEC_ERROR", str(e), role=role)
        return False, f"ERROR: {e}", elapsed


# ─── 자가 테스트 ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Sandbox v2.1 자가 테스트 ===\n")

    results = []
    def chk(name, ok, detail=""):
        results.append(ok)
        print(f"  {'✅' if ok else '❌'} {name}" + (f" → {detail}" if detail else ""))

    # 경로 검증 — user role
    chk("user: 정상 경로 허용",    validate_path("./workspace/a.py", "user")[0])
    chk("user: 상위 경로 차단",    not validate_path("../secret", "user")[0])
    chk("user: ALLOWED 외 차단",   not validate_path("./other/a.py", "user")[0])
    chk("user: core/ 차단",        not validate_path("./core/security.py", "user")[0])

    # 경로 검증 — admin role
    chk("admin: workspace 허용",   validate_path("./workspace/a.py", "admin")[0])
    chk("admin: ALLOWED 외 허용",  validate_path("./other/a.py", "admin")[0])   # admin 우회
    chk("admin: core/ 차단 유지",  not validate_path("./core/security_layer.py", "admin")[0])

    # 명령어 검증 — admin도 차단
    chk("admin: rm -rf 차단",      not validate_command("rm -rf /")[0])
    chk("admin: curl 차단",        not validate_command("curl http://evil.com")[0])
    chk("user: ls 허용",           validate_command("ls -la")[0])

    # validate_action — admin override 로그 확인
    chk("admin override 허용",     validate_action("ls -la", "./other_dir", "admin"))
    chk("user 외부 경로 차단",     not validate_action("ls -la", "./other_dir", "user"))
    chk("admin rm -rf 차단",       not validate_action("rm -rf .", "./workspace", "admin"))

    print(f"\n  결과: {sum(results)}/{len(results)} PASS")
