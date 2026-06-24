"""Agent-tool path permission endpoints (v0.6.1, Phase B).

Operator-facing admin surface for the user-registered paths that
`tools/code/sandbox.py::validate_path` accepts. See
`docs/design/v0.6-agent-tools-user-paths.md` for the trust contract.

Endpoints (admin-only, audit-logged):

  * `GET  /admin/agent/allowed-paths` → list registered paths + env
  * `POST /admin/agent/allowed-paths` `{"path": "/abs/path"}` → register

Paths are session-scoped (in-memory). Restart of the JAMES process
re-reads `JAMES_AGENT_ALLOWED_PATHS` env; the design memo §3 explains
why no runtime-remove endpoint ships in Phase B.
"""
from __future__ import annotations

import os
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routes._helpers import (
    _bearer_username,
    _require_admin,
    _write_audit,
    get_role_from_request,
)

router = APIRouter()


class RegisterPathRequest(BaseModel):
    api_key: str
    path: str


@router.get(
    "/admin/agent/allowed-paths",
    summary="에이전트 도구 허용 경로 조회 [v0.6.1 Phase B]",
)
async def list_allowed_paths(
    api_key: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Return the current list of user-registered absolute paths the
    agent tools may read/write, plus the env that seeded them."""
    _require_admin(api_key, role)

    from tools.code.sandbox import (
        JAMES_AGENT_ALLOWED_PATHS_ENV,
        get_user_registered_paths,
    )

    paths = get_user_registered_paths()
    env_value = os.environ.get(JAMES_AGENT_ALLOWED_PATHS_ENV, "")

    return {
        "registered_paths": paths,
        "count": len(paths),
        "env_name": JAMES_AGENT_ALLOWED_PATHS_ENV,
        "env_value": env_value,
    }


@router.post(
    "/admin/agent/allowed-paths",
    summary="에이전트 도구 허용 경로 등록 [v0.6.1 Phase B]",
)
async def register_allowed_path(
    body: RegisterPathRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Register an absolute path as agent-tool-allowed for this server
    process. Critical-system roots (`/etc/`, `C:\\Windows\\`, …) are
    rejected at the sandbox layer; admin cannot override that block."""
    _require_admin(body.api_key, role)
    username = _bearer_username(request) or "admin"

    from tools.code.sandbox import register_user_path

    ok, msg = register_user_path(body.path)
    _write_audit(
        role,
        "/admin/agent/allowed-paths",
        query=f"register:{body.path}",
        answer=f"ok={ok}; {msg}",
    )
    if not ok:
        # Surface the specific reason so the admin can correct it
        # (path doesn't exist / under critical root / etc.).
        raise HTTPException(status_code=400, detail=msg)

    return {
        "registered": True,
        "path": body.path,
        "message": msg,
        "by": username,
    }


class UnregisterPathRequest(BaseModel):
    api_key: str
    path: str


@router.post(
    "/admin/agent/allowed-paths/remove",
    summary="에이전트 도구 허용 경로 제거 (세션 스코프) [v0.6.1 Phase D-1]",
)
async def unregister_allowed_path(
    body: UnregisterPathRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Session-scoped remove from the in-memory registry.

    **Not a permanent revoke.** Restarting the JAMES process re-reads
    `JAMES_AGENT_ALLOWED_PATHS` env, so paths persisted there will
    re-appear. To revoke permanently: edit the env and restart. See
    `docs/design/v0.6-agent-tools-user-paths.md` §3.

    Idempotent: removing a non-registered path returns 200 with a
    no-op message rather than 404 — the UI's "X" button is meant to
    be tap-and-forget.
    """
    _require_admin(body.api_key, role)
    username = _bearer_username(request) or "admin"

    from tools.code.sandbox import unregister_user_path

    ok, msg = unregister_user_path(body.path)
    _write_audit(
        role,
        "/admin/agent/allowed-paths/remove",
        query=f"unregister:{body.path}",
        answer=f"ok={ok}; {msg}",
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "removed": True,
        "path": body.path,
        "message": msg,
        "by": username,
        "session_scoped": True,
    }


# ─── Directory browser (v0.6.1 UX overhaul) ──────────────────────────
# Server-side filesystem picker: the operator navigates the JAMES host's
# folders from the admin UI and registers one with the POST endpoint
# above (no need to hand-type an absolute path). Read-only listing,
# admin-only. Non-registerable folders (critical roots / JAMES-internal
# subtrees) are flagged so the UI can disable the "select" button.

_BROWSE_CAP = 1000


def _registerable(abs_path: str) -> bool:
    """A folder is registerable if it is NOT under a critical system
    root or a JAMES-internal protected subtree (same gates
    ``register_user_path`` enforces)."""
    from tools.code.sandbox import (
        _is_under_critical_root,
        _is_under_repo_protected,
    )
    return not (_is_under_critical_root(abs_path)
                or _is_under_repo_protected(abs_path))


def _list_roots() -> list:
    """Top-level entry points for the picker: drive letters on Windows,
    ``/`` + home on POSIX."""
    out = []
    if os.name == "nt":
        for c in string.ascii_uppercase:
            d = f"{c}:\\"
            if os.path.exists(d):
                out.append({"name": d, "path": d, "registerable": True})
    else:
        out.append({"name": "/", "path": "/", "registerable": False})
    home = os.path.expanduser("~")
    if os.path.isdir(home):
        out.append({"name": f"~ ({home})", "path": home,
                    "registerable": _registerable(home)})
    return out


@router.get(
    "/admin/agent/browse",
    summary="에이전트 폴더 브라우저 (서버 파일시스템) [v0.6.1]",
)
async def browse_dirs(
    api_key: str,
    request: Request,
    path: str = "",
    role: str = Depends(get_role_from_request),
):
    """List the immediate sub-directories of ``path`` on the JAMES host
    so the admin UI can offer a folder picker. Empty ``path`` returns the
    roots (drives / home). Files are omitted — only directories."""
    _require_admin(api_key, role)

    from tools.code.sandbox import _norm_abs

    if not path.strip():
        return {
            "current": "",
            "parent": None,
            "sep": os.sep,
            "registerable": False,
            "entries": _list_roots(),
        }

    abs_p = _norm_abs(path)
    if not abs_p or not os.path.isdir(abs_p):
        raise HTTPException(status_code=404, detail=f"not a directory: {path!r}")

    entries = []
    try:
        for name in sorted(os.listdir(abs_p), key=str.lower):
            full = os.path.join(abs_p, name)
            try:
                if not os.path.isdir(full):
                    continue
            except OSError:
                continue
            entries.append({
                "name": name,
                "path": full,
                "registerable": _registerable(_norm_abs(full)),
            })
            if len(entries) >= _BROWSE_CAP:
                break
    except OSError as e:
        raise HTTPException(status_code=403, detail=f"listdir failed: {e}")

    parent = os.path.dirname(abs_p)
    if parent == abs_p:          # already at a filesystem root
        parent = ""
    return {
        "current": abs_p,
        "parent": parent,
        "sep": os.sep,
        "registerable": _registerable(abs_p),
        "entries": entries,
    }


# ─── Agent LLM settings (backend + model) ────────────────────────────

class AgentLLMSettingsRequest(BaseModel):
    api_key: str
    backend: Optional[str] = None
    ollama_model: Optional[str] = None
    anthropic_model: Optional[str] = None
    enable_shell: Optional[bool] = None


@router.get(
    "/admin/agent/llm-settings",
    summary="에이전트 LLM 백엔드/모델 설정 조회 [v0.6.1]",
)
async def get_agent_llm_settings(
    api_key: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Return the agent's current backend + model selection plus the
    list of installed Ollama models the UI dropdown offers."""
    _require_admin(api_key, role)

    from core import llm_settings as ls
    from core.agent_tools import shell_enabled
    try:
        from routes.llm import _list_installed_ollama_models
        installed = sorted(_list_installed_ollama_models())
    except Exception:
        installed = []

    allow_cloud = (os.environ.get("JAMES_AGENT_ALLOW_CLOUD") or "").strip().lower() \
        in ("1", "true", "yes", "on", "enabled")
    anthropic_key_present = bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())
    # claude_cli backend (Max-plan login, no API key) — is the `claude`
    # CLI reachable?
    import shutil
    claude_cli_present = bool(
        (os.environ.get("JAMES_CLAUDE_CLI_PATH") or "").strip()
        or shutil.which("claude"))

    return {
        "backend": ls.get("agent_backend"),
        "ollama_model": ls.get("agent_ollama_model"),
        "anthropic_model": ls.get("agent_anthropic_model"),
        "installed_ollama_models": installed,
        # Suggested Claude model ids for the UI dropdown (the cloud
        # backend can use any valid Anthropic model id; these are the
        # current family). See `core/agent_tools/backends.py`.
        "claude_models": [
            "claude-opus-4-8",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-fable-5",
        ],
        "shell_enabled": shell_enabled(),
        # Cloud-egress gate status so the UI can tell the operator exactly
        # what to set before the cloud backends will work.
        "allow_cloud": allow_cloud,
        "anthropic_key_present": anthropic_key_present,
        "claude_cli_present": claude_cli_present,
    }


@router.post(
    "/admin/agent/llm-settings",
    summary="에이전트 LLM 백엔드/모델 설정 저장 [v0.6.1]",
)
async def set_agent_llm_settings(
    body: AgentLLMSettingsRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Persist the agent backend / model selection to the unified LLM
    settings repository (DB-first). Validation errors (unknown enum
    value etc.) surface as 400."""
    _require_admin(body.api_key, role)
    username = _bearer_username(request) or "admin"

    from core import llm_settings as ls

    changed = {}
    try:
        if body.backend is not None:
            ls.set("agent_backend", body.backend, by=username)
            changed["agent_backend"] = body.backend
        if body.ollama_model is not None and body.ollama_model.strip():
            ls.set("agent_ollama_model", body.ollama_model.strip(), by=username)
            changed["agent_ollama_model"] = body.ollama_model.strip()
        if body.anthropic_model is not None and body.anthropic_model.strip():
            ls.set("agent_anthropic_model", body.anthropic_model.strip(), by=username)
            changed["agent_anthropic_model"] = body.anthropic_model.strip()
        if body.enable_shell is not None:
            ls.set("agent_enable_shell", "1" if body.enable_shell else "0", by=username)
            changed["agent_enable_shell"] = "1" if body.enable_shell else "0"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _write_audit(
        role,
        "/admin/agent/llm-settings",
        query=f"set:{list(changed.keys())}",
        answer="ok",
    )
    return {"ok": True, "changed": changed, "by": username}
