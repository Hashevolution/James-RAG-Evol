"""
PROJECT JAMES - Tool Router v2.2 (Phase 5.5 + #44 phase 3-2)

역할:
  1. PolicyEngine 통한 capability-token 발급/검증 (chokepoint)
  2. PROTECTED_FILES 체크 (환경변수로 관리, defense-in-depth)
  3. admin role → PROTECTED_FILES 우회 허용 + 감사 로그
  4. Tool 존재 / 권한 확인
  5. Tool 실행 위임

PROTECTED_FILES 관리:
  .env 또는 환경변수 JAMES_PROTECTED_FILES 수정으로 제어
  하드코딩 금지 — Phase 6 전환 시 목록에서 제거만 하면 됨

#44 phase 3-2:
  모든 execute_tool 호출은 PolicyEngine.issue_capability() 통과 필수.
  실패 시 CAPABILITY_DENIED 로그 + 즉시 차단. 토큰 ID는 감사 로그에 기록.

절대 금지:
  ❌ admin_override 감사 로그 누락
  ❌ PROTECTED_FILES 하드코딩
  ❌ shell_exec 구현 (Phase 6 이후)
  ❌ PolicyEngine 우회 — capability 미발급 호출은 거부
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

from core.policy_engine import default_engine, Capability

AUDIT_LOG_PATH = "james_audit_tool.jsonl"

# ─── PROTECTED_FILES (환경변수로 관리) ───────────────────────

PROTECTED_FILES: list = os.environ.get(
    "JAMES_PROTECTED_FILES",
    "core/graph_engine.py,"
    "core/security_layer.py,"
    "core/ontology.py,"
    "core/auth.py,"
    "core/reasoning_engine.py,"
    "core/graph_rag_engine.py,"
    "core/memory_loom.py,"
    "core/memory_trust.py,"
    "core/gemma_client.py,"
    "core/retrieval_engine.py"
).split(",")

PROTECTED_FILES = [f.strip() for f in PROTECTED_FILES if f.strip()]


def _log_tool_event(
    event:          str,
    action_name:    str,
    target:         str,
    role:           str,
    blocked:        bool,
    protected_block:bool = False,
    admin_override: bool = False,
    sandbox_block:  bool = False,
    cap_denied:     bool = False,
    cap_token_id:   Optional[str] = None,
    cap_action:     Optional[str] = None,
    exec_time_sec:  float = 0.0,
):
    """
    확장 감사 로그.
    브리핑 스펙: tool_used + protected_block + admin_override 필수 기록.
    Phase 3-2 추가: cap_denied / cap_token_id / cap_action.
    """
    entry = {
        "time":            datetime.now().isoformat(),
        "event":           event,
        "tool_used":       action_name,
        "target_file":     target,
        "role":            role,
        "blocked":         blocked,
        "protected_block": protected_block,
        "admin_override":  admin_override,
        "sandbox_block":   sandbox_block,
        "cap_denied":      cap_denied,
        "cap_token_id":    cap_token_id,
        "cap_action":      cap_action,
        "exec_time_sec":   exec_time_sec,
        "layer":           "router",
    }
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

    if blocked:
        reason = (
            "CAPABILITY"  if cap_denied      else
            "PROTECTED"   if protected_block else
            "SANDBOX"     if sandbox_block   else
            "DENIED"
        )
        print(f"[ROUTER] 🚫 BLOCK({reason}) [{role}] {action_name} → {target[:40]}")
    elif admin_override:
        print(f"[ROUTER] ⚠️  ADMIN_OVERRIDE [{role}] {action_name} → {target[:40]}")
    else:
        print(f"[ROUTER] ✅ ALLOW [{role}] {action_name} → {target[:40]}")


def _is_protected(target: str) -> bool:
    """target 경로가 PROTECTED_FILES 목록에 해당하는지 확인."""
    if not target:
        return False
    for protected in PROTECTED_FILES:
        # 경로 끝부분 매칭 (절대/상대 경로 모두 처리)
        if target.endswith(protected.strip()):
            return True
        if protected.strip() in target:
            return True
    return False


# Phase 3-2 (#44): tool name → canonical capability action.
# Read-only file/directory inspection maps to fs.read; mutation maps to
# fs.write; subprocess execution maps to shell.exec. Anything not in
# this table falls through to "tool.invoke" — admin-only by default.
_TOOL_TO_ACTION: Dict[str, str] = {
    "read_file":      "fs.read",
    "list_files":     "fs.read",
    "code_reader":    "fs.read",
    "code_analyzer":  "fs.read",
    "code_editor":    "fs.write",
    "write_file":     "fs.write",
    "patch_apply":    "fs.write",
    "patch_generate": "fs.write",
    "execute_command": "shell.exec",
    "shell_exec":     "shell.exec",
}


def _action_for_tool(tool_name: str) -> str:
    """Map a registered tool name to its canonical capability action.

    Unknown tools fall back to "tool.invoke", which `can_call_tool`
    treats as admin-only — fail-closed for any tool the policy table
    has not been told about.
    """
    return _TOOL_TO_ACTION.get(tool_name, "tool.invoke")


def _scope_for_target(target: str) -> str:
    """Pick a capability scope from the call's target path.

    Phase 3-2 keeps this deliberately permissive: an empty target
    becomes "*" (unbounded) so the legacy `tools/router.py` admin
    surface area is preserved bit-for-bit. The scope is still verified
    against the issued capability, so a future tightening (e.g.
    require explicit scope for fs.write) is a one-line change here.
    """
    return target if target else "*"


def execute_tool(action: dict, context: dict) -> dict:
    """
    Tool 실행 라우터.

    Args:
        action:  {"name": "read_file", "input": {"path": "...", ...}}
        context: {"user_role": "admin", "allow_fs": False, "allow_shell": False}

    Returns:
        {"success": bool, "result": Any, ...}

    Phase 3-2 (#44): the first gate is now PolicyEngine.issue_capability().
    A denied issuance returns CAPABILITY_DENIED before any other check
    runs. Subsequent verify_capability() asserts action+scope match.
    PROTECTED_FILES + tool.authorize() remain as defense-in-depth.
    """
    import time
    t_start     = time.time()
    action_name = action.get("name", "unknown")
    target      = action.get("input", {}).get("path", "")
    role        = context.get("user_role", "external")
    is_admin    = (role == "admin")

    # 0. Capability 발급 (PolicyEngine chokepoint)
    cap_action = _action_for_tool(action_name)
    cap_scope  = _scope_for_target(target)
    cap = default_engine.issue_capability(role, cap_action, cap_scope)
    if cap is None:
        _log_tool_event(
            "CAPABILITY_DENIED", action_name, target, role,
            blocked=True, cap_denied=True, cap_action=cap_action,
        )
        return {"success": False, "result": None, "error": "CAPABILITY_DENIED",
                "tool_used": action_name}

    # 0b. 즉시 verify (action+scope sanity, audit trail에 token_id 기록)
    verify = default_engine.verify_capability(cap, cap_action, cap_scope)
    if not verify.allowed:
        _log_tool_event(
            "CAPABILITY_INVALID", action_name, target, role,
            blocked=True, cap_denied=True,
            cap_action=cap_action, cap_token_id=cap.token_id,
        )
        return {"success": False, "result": None,
                "error": f"CAPABILITY_INVALID:{verify.reason}",
                "tool_used": action_name}

    # 1. PROTECTED_FILES 체크 (defense-in-depth)
    protected = _is_protected(target)
    if protected:
        if not is_admin:
            # admin 아닌 경우 → 차단
            _log_tool_event(
                "PROTECTED_BLOCK", action_name, target, role,
                blocked=True, protected_block=True,
                cap_action=cap_action, cap_token_id=cap.token_id,
            )
            return {"success": False, "result": None, "error": "PROTECTED",
                    "tool_used": action_name}
        else:
            # admin → 우회 허용 (반드시 감사 로그)
            _log_tool_event(
                "ADMIN_OVERRIDE", action_name, target, role,
                blocked=False, protected_block=True, admin_override=True,
                cap_action=cap_action, cap_token_id=cap.token_id,
            )

    # 2. Tool 존재 확인
    from tools.registry import TOOLS
    tool = TOOLS.get(action_name)
    if not tool:
        _log_tool_event("UNKNOWN_TOOL", action_name, target, role, blocked=True,
                        cap_action=cap_action, cap_token_id=cap.token_id)
        return {"success": False, "result": None, "error": "UNKNOWN_TOOL",
                "tool_used": action_name}

    # 3. Tool 권한 확인 (BaseTool.authorize — defense-in-depth)
    if not tool.authorize(context):
        from core.security_layer import log_system_event
        log_system_event("tool_denied", f"tool={action_name} role={role}", role=role)
        _log_tool_event("TOOL_DENIED", action_name, target, role, blocked=True,
                        cap_action=cap_action, cap_token_id=cap.token_id)
        return {"success": False, "result": None, "error": "DENIED",
                "tool_used": action_name}

    # 4. Tool 실행
    try:
        result = tool.execute(action["input"])
    except Exception as e:
        elapsed = round(time.time() - t_start, 3)
        _log_tool_event("TOOL_ERROR", action_name, target, role,
                        blocked=False, exec_time_sec=elapsed,
                        cap_action=cap_action, cap_token_id=cap.token_id)
        return {"success": False, "result": None, "error": str(e),
                "tool_used": action_name}

    elapsed = round(time.time() - t_start, 3)
    _log_tool_event(
        "TOOL_EXECUTED", action_name, target, role,
        blocked=False,
        admin_override=is_admin and protected,
        cap_action=cap_action, cap_token_id=cap.token_id,
        exec_time_sec=elapsed,
    )
    return result


def get_protected_files() -> list:
    """현재 PROTECTED_FILES 목록 반환 (설정 확인용)."""
    return list(PROTECTED_FILES)


# ─── 자가 테스트 ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Router v2.2 자가 테스트 ===\n")
    print(f"PROTECTED_FILES ({len(PROTECTED_FILES)}개):")
    for f in PROTECTED_FILES:
        print(f"  • {f}")
    print()

    # protected 탐지 테스트
    tests = [
        ("core/security_layer.py",   True),
        ("core/graph_engine.py",     True),
        ("./workspace/app.py",       False),
        ("tools/router.py",          False),
        ("core/auth.py",             True),
    ]
    passed = 0
    for path, expect in tests:
        result = _is_protected(path)
        ok = result == expect
        passed += int(ok)
        print(f"  {'✅' if ok else '❌'} {path:35s} protected={result} (기대={expect})")

    print(f"\n  결과: {passed}/{len(tests)} PASS\n")

    # tool name → action 매핑 테스트
    print("--- _action_for_tool 매핑 ---")
    map_tests = [
        ("read_file",      "fs.read"),
        ("code_analyzer",  "fs.read"),
        ("code_editor",    "fs.write"),
        ("execute_command","shell.exec"),
        ("unknown_tool",   "tool.invoke"),
    ]
    for name, expect in map_tests:
        got = _action_for_tool(name)
        ok = got == expect
        print(f"  {'✅' if ok else '❌'} {name:20s} → {got} (기대={expect})")
