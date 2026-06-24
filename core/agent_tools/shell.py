"""run_shell agent tool (v0.6.1 Phase E).

The highest-risk surface in the agent-tools family: it lets the LLM run
an arbitrary shell command line in an operator-allowed folder. Every
defence the design memo (`docs/design/v0.6-agent-tools-user-paths.md`
§G-D / §4 / §7) demands is enforced here:

  1. **Default OFF.** ``run_shell`` refuses unless the operator sets
     ``JAMES_AGENT_ENABLE_SHELL=1``. Mirrors the AnthropicBackend
     ``JAMES_AGENT_ALLOW_CLOUD`` opt-in pattern — the riskiest tool can
     NOT fire on a stock install. The agent-chat endpoint also hides the
     tool from the LLM schema while disabled (no wasted loop iteration).
  2. **admin only.** The handler re-checks ``role == "admin"`` even
     though ``/agent/chat/`` already gates admin — defence in depth for
     direct ``dispatch()`` callers (scripts, tests).
  3. **cwd anchored to an allowed path.** ``cwd`` must pass the Phase 5.5
     sandbox ``validate_path`` — i.e. it must be the in-repo workspace
     or an operator-registered ``JAMES_AGENT_ALLOWED_PATHS`` folder.
     Critical system roots + JAMES-internal subtrees stay blocked.
  4. **command allow-list.** ``validate_command`` (sandbox
     ``BLOCKED_COMMANDS`` + danger patterns) PLUS a wider
     ``RUN_SHELL_EXTRA_BLOCKED`` list for the bigger PowerShell / bash
     surface (download-and-exec, service/registry/scheduler edits,
     encoded commands, disk tools…).
  5. **bounded.** explicit argv (no ``shell=True`` string splat), a hard
     ``SHELL_TIMEOUT_SEC`` subprocess timeout that actually kills the
     child (the dispatcher thread-join can't), and an output cap so the
     LLM context doesn't drown.
  6. **audited.** every run writes a sandbox ``log_security_event`` row
     on top of the dispatcher's pre/post audit rows.

Shell selection: ``powershell`` | ``pwsh`` | ``cmd`` | ``bash`` | ``sh``.
Default = ``powershell`` on Windows, ``bash`` elsewhere.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional

from core.agent_tools.registry import Tool, ToolError, register_tool

ENV_ENABLE_SHELL = "JAMES_AGENT_ENABLE_SHELL"

# Subprocess hard timeout. MUST stay below the dispatcher's
# MAX_TOOL_TIMEOUT_SEC (30) so subprocess.run kills the child before the
# dispatcher's thread-join fires (a joined-out daemon thread leaves the
# subprocess orphaned otherwise).
SHELL_TIMEOUT_SEC = 20

# Combined stdout+stderr cap (chars) returned to the LLM.
_OUTPUT_CAP = 4000

# Wider block-list for the shell surface, on TOP of the sandbox
# `BLOCKED_COMMANDS` + `validate_command` danger patterns. Case-folded
# substring match. Covers the PowerShell / bash idioms that the
# file-scoped tools never exposed: download-and-execute, service /
# registry / scheduler mutation, encoded commands, disk / ACL tools.
RUN_SHELL_EXTRA_BLOCKED = (
    # download + execute
    "invoke-expression", "iex ", "invoke-webrequest", "iwr ",
    "downloadstring", "downloadfile", "start-bitstransfer",
    "certutil", "bitsadmin", "scp ", "ftp ", "nc ", "ncat", "telnet",
    # process / service / scheduler
    "start-process", "new-service", "set-service", "stop-service",
    "schtasks", "sc create", "sc delete", "at ", "wmic",
    # registry
    "reg add", "reg delete", "set-itemproperty", "new-itemproperty",
    "remove-itemproperty", "new-item -path hk", "reg import",
    # destructive fs / disk
    "remove-item", "rd /s", "vssadmin", "bcdedit", "diskpart",
    "cipher /w", "fsutil", "takeown", "icacls", "attrib ",
    # defender / security posture
    "add-mppreference", "set-mppreference", "set-executionpolicy",
    "net user", "net localgroup", "new-localuser", "add-localgroupmember",
    # encoded / obfuscated
    "-encodedcommand", "-enc ", "frombase64string",
)


def shell_enabled() -> bool:
    """True when the operator has opted into ``run_shell``.

    DB-first via the unified LLM settings (so the admin UI checkbox can
    toggle it without a restart), falling back to the
    ``JAMES_AGENT_ENABLE_SHELL`` env var. Default OFF (highest-risk
    surface). Accepts 1/true/yes/on/enabled."""
    try:
        from core import llm_settings as ls
        return ls.get_bool("agent_enable_shell", ENV_ENABLE_SHELL, "0")
    except Exception:
        raw = (os.environ.get(ENV_ENABLE_SHELL) or "").strip().lower()
        return raw in ("1", "true", "yes", "on", "enabled")


def _resolve_argv(shell: str, command: str) -> List[str]:
    """Map a shell name to an explicit argv that runs ``command`` as a
    single argument (no shell=True string splat). Raises ``ToolError``
    for an unknown shell."""
    s = (shell or "").strip().lower()
    if not s:
        s = "powershell" if os.name == "nt" else "bash"
    if s in ("powershell", "ps", "ps1"):
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
    if s == "pwsh":
        return ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command]
    if s == "cmd":
        return ["cmd", "/c", command]
    if s == "bash":
        return ["bash", "-c", command]
    if s == "sh":
        return ["sh", "-c", command]
    raise ToolError(
        f"unknown shell {shell!r}; expected powershell|pwsh|cmd|bash|sh"
    )


def _h_run_shell(args: Dict[str, Any], role: str) -> Dict[str, Any]:
    # (1) global opt-in gate
    if not shell_enabled():
        raise ToolError(
            f"run_shell is disabled. The operator must set "
            f"{ENV_ENABLE_SHELL}=1 to enable shell execution (highest-risk "
            f"surface — default OFF)."
        )
    # (2) admin only — defence in depth for direct dispatch() callers
    if role != "admin":
        raise ToolError(f"run_shell requires admin role (got {role!r})")

    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ToolError("'command' (non-empty string) is required")
    cwd = args.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise ToolError(
            "'cwd' (string) is required — an operator-allowed folder the "
            "command runs in"
        )
    shell = args.get("shell") or ""
    if not isinstance(shell, str):
        raise ToolError("'shell' must be a string if provided")

    # (3) cwd must be inside an allowed path (workspace or registered).
    from tools.code.sandbox import (
        log_security_event,
        validate_command,
        validate_path,
    )
    ok, msg = validate_path(cwd, role=role)
    if not ok:
        raise ToolError(f"cwd rejected: {msg}")
    if not os.path.isdir(cwd):
        raise ToolError(f"cwd is not a directory: {cwd!r}")

    # (4) command must pass the sandbox allow-list + the wider shell list.
    cmd_ok, cmd_reason = validate_command(command)
    if not cmd_ok:
        log_security_event("RUN_SHELL_BLOCKED",
                           f"cmd={command[:60]}: {cmd_reason}",
                           blocked=True, role=role)
        raise ToolError(f"command blocked: {cmd_reason}")
    low = command.lower()
    for bad in RUN_SHELL_EXTRA_BLOCKED:
        if bad in low:
            log_security_event("RUN_SHELL_BLOCKED",
                               f"cmd={command[:60]}: extra-blocked {bad!r}",
                               blocked=True, role=role)
            raise ToolError(f"command blocked (shell-surface): {bad.strip()!r}")

    argv = _resolve_argv(shell, command)

    # (5) bounded execution.
    try:
        proc = subprocess.run(  # nosec B603 — argv list, no shell=True
            argv,
            cwd=os.path.normpath(cwd),
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        log_security_event("RUN_SHELL_TIMEOUT",
                           f"{SHELL_TIMEOUT_SEC}s shell={argv[0]}",
                           blocked=True, role=role)
        raise ToolError(f"command timed out after {SHELL_TIMEOUT_SEC}s")
    except FileNotFoundError:
        raise ToolError(f"shell interpreter not found: {argv[0]!r}")
    except OSError as e:
        raise ToolError(f"shell execution failed: {e}")

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined_len = len(stdout) + len(stderr)
    truncated = combined_len > _OUTPUT_CAP
    if truncated:
        # Keep most of the cap for stdout; leave a slice for stderr.
        stdout = stdout[: _OUTPUT_CAP - 500]
        stderr = stderr[:500]

    # (6) audit the run outcome.
    log_security_event("RUN_SHELL_EXEC",
                       f"exit={proc.returncode} shell={argv[0]} "
                       f"cwd={os.path.basename(os.path.normpath(cwd))}",
                       blocked=False, role=role, admin_override=True)

    return {
        "exit_code": proc.returncode,
        "shell": argv[0],
        "cwd": os.path.normpath(cwd),
        "stdout": stdout,
        "stderr": stderr,
        "truncated": truncated,
    }


register_tool(Tool(
    name="run_shell",
    description=(
        "Run a shell command line in an operator-allowed folder and "
        "return its exit code + stdout/stderr. DEFAULT DISABLED — only "
        "available when the operator has enabled shell execution. admin "
        "only. The 'cwd' must be inside an allowed folder; dangerous "
        "commands (download-and-execute, service/registry/disk edits, "
        "encoded commands) are blocked."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command line to run.",
            },
            "cwd": {
                "type": "string",
                "description": (
                    "Absolute path to an operator-allowed folder (or the "
                    "in-repo ./workspace) the command runs inside."
                ),
            },
            "shell": {
                "type": "string",
                "description": (
                    "Optional: powershell | pwsh | cmd | bash | sh. "
                    "Defaults to powershell on Windows, bash otherwise."
                ),
            },
        },
        "required": ["command", "cwd"],
    },
    handler=_h_run_shell,
    # Pin to the dispatcher cap so its thread-join sits ABOVE the
    # subprocess timeout (the subprocess timeout is what actually kills
    # the child).
    timeout_sec=30,
))
