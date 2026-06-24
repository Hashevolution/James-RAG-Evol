"""Adapter that spawns the ``claude`` CLI as a subprocess.

Opt-in only. Registration in ``core/reasoning/backends/__init__.py``
checks ``JAMES_ENABLE_CLAUDE_BACKEND=1`` so a stock JAMES install never
reaches an external CLI without explicit operator consent.

Security posture (L0 MVP):

  1. Prompt is delivered via **stdin**, never as a CLI argument. A
     prompt containing shell metacharacters (`;`, `|`, `$()`) cannot
     reach the subprocess argv.
  2. Argv is a fixed list — `[cli_path, "-p", "--output-format", "text"]`.
     No user-controlled string ever joins argv.
  3. Environment passed to the child is a **whitelist**. The whitelist
     splits into:
       * Cross-platform Claude-specific: ``PATH``, ``HOME``,
         ``ANTHROPIC_API_KEY``, ``CLAUDE_CONFIG_DIR``.
       * Windows essentials: ``SystemRoot``, ``APPDATA``,
         ``LOCALAPPDATA``, ``USERPROFILE``, ``TEMP``, ``TMP``.
         Without these the Node-based ``claude.CMD`` wrapper exits
         with returncode 1 + empty stderr on Windows (caught by S4
         smoke 2026-06-03). The list is conservative — only Windows
         baseline runtime vars, no app-specific secrets.
     ``os.environ`` is not handed over wholesale; secrets stashed in
     other env vars (``JAMES_API_KEY`` / ``AWS_*`` / ``GCP_*`` etc.)
     stay local.
  4. Default working directory is a **neutral temp dir**
     (``tempfile.gettempdir()``), NOT the project directory. Spawning
     ``claude -p`` inside the project loads the project ``CLAUDE.md``
     and puts the CLI into coding-agent mode, where it responds to
     the briefing instead of the prompt (caught by S4 smoke).
     Operators wanting a project-context call pass an explicit
     ``cwd=`` to ``complete``.
  5. Output is size-capped (1 MiB) and the child is killed on timeout.
  6. Cli path can be overridden via ``JAMES_CLAUDE_CLI_PATH`` (defaults
     to looking up ``claude`` on PATH); a missing CLI surfaces as
     ``error="cli not found"`` rather than a crash.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from typing import List, Optional

from core.reasoning.backends import BackendCapability, CompletionResult


_MAX_OUTPUT_BYTES = 1 * 1024 * 1024   # 1 MiB

# Cross-platform Claude-specific env passthrough.
_ENV_WHITELIST_CORE = ("PATH", "HOME", "ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR")

# Windows runtime essentials. Empirically required on Windows (S4 smoke
# 2026-06-03): without `SystemRoot` the Node-based `claude.CMD` wrapper
# exits with returncode 1 and empty stderr. The others (APPDATA et al.)
# are Claude's config / cache lookup paths. Cross-platform — these are
# Windows-only names, but reading them on POSIX is harmless (empty
# value → dropped by _build_env).
_ENV_WHITELIST_WINDOWS = (
    "SystemRoot", "APPDATA", "LOCALAPPDATA",
    "USERPROFILE", "TEMP", "TMP",
)

_ENV_WHITELIST = _ENV_WHITELIST_CORE + _ENV_WHITELIST_WINDOWS


def _resolve_cli_path() -> Optional[str]:
    """Honor JAMES_CLAUDE_CLI_PATH if set, otherwise look up ``claude``
    on PATH. Returns None if the binary is not findable — caller turns
    that into ``error="cli not found"``.
    """
    explicit = os.environ.get("JAMES_CLAUDE_CLI_PATH", "").strip()
    if explicit:
        return explicit if os.path.exists(explicit) else None
    return shutil.which("claude")


def _build_env() -> dict:
    """Whitelist os.environ. Empty values are dropped so the child does
    not inherit cleared sentinels.
    """
    return {
        k: os.environ[k]
        for k in _ENV_WHITELIST
        if os.environ.get(k)
    }


class ClaudeCodeCliBackend:
    """``claude -p`` non-interactive driver.

    The CLI's `-p` flag enters print mode: it reads the prompt from
    stdin (when no positional argument is given), runs one turn, prints
    the answer to stdout, exits. Output format is forced to ``text`` so
    the result is the bare answer string.
    """

    backend_id = "claude_code_cli"

    # D5.B capability declaration. Claude (Anthropic frontier) is
    # "large" tier — used by D5.C policy for heavy-synthesis routing
    # (the arm where the cost asymmetry favors the better model).
    # ``provider="cloud"`` because the CLI hits Anthropic's API surface
    # — operators have no control over weights, only over whether the
    # backend is registered (opt-in via JAMES_ENABLE_CLAUDE_BACKEND=1).
    capability = BackendCapability(tier="large", provider="cloud")

    def __init__(self, cli_path: Optional[str] = None) -> None:
        # Constructor-time path resolution is a snapshot; auto-registered
        # instances pin whatever the operator's environment had at boot.
        # Tests pass an explicit cli_path to override.
        self._explicit_cli = cli_path

    def _cli_path(self) -> Optional[str]:
        return self._explicit_cli or _resolve_cli_path()

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,   # advisory — claude CLI does not surface a flag
        timeout: float = 60.0,
        model: Optional[str] = None,
        temperature: Optional[float] = None,   # accepted per R4, ignored — CLI no flag
        cwd: Optional[str] = None,
        disallow_tools: bool = False,
        **opts,
    ) -> CompletionResult:
        t0 = time.time()
        path = self._cli_path()
        if not path:
            return CompletionResult(
                text="", backend_id=self.backend_id, model=model or "",
                latency_ms=0, error="cli not found",
            )

        argv: List[str] = [path, "-p", "--output-format", "text"]
        if model:
            # validated by the CLI itself — we don't try to enumerate
            # the model catalog client-side
            argv.extend(["--model", str(model)])
        if disallow_tools:
            # Make `claude -p` behave as a PURE text completer — disable
            # all of its own built-in tools (Read/Bash/Edit/…) so it does
            # NOT run agentic file ops in its sandboxed cwd. Callers that
            # dispatch tools themselves (agent tool-use loop) use this so
            # the model only emits text (a JSON tool call we parse).
            argv.extend(["--disallowedTools", "*"])

        composed = f"{system}\n\n{prompt}" if system else prompt
        # bound the prompt at the same 1 MiB the output is bounded at —
        # avoids handing a pathological prompt to the subprocess
        composed = composed[: _MAX_OUTPUT_BYTES]

        # Neutral cwd default (§"Security posture" #4): spawn in temp,
        # not the project dir, so `claude -p` doesn't pick up the
        # project CLAUDE.md and switch to coding-agent mode. Operators
        # wanting a project-context call pass `cwd=` explicitly.
        spawn_cwd = cwd if cwd is not None else tempfile.gettempdir()

        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_build_env(),
                cwd=spawn_cwd,
                # text mode with utf-8 to match JAMES's encoding convention
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, FileNotFoundError) as e:
            return CompletionResult(
                text="", backend_id=self.backend_id, model=model or "",
                latency_ms=int((time.time() - t0) * 1000),
                error=f"spawn failed: {type(e).__name__}: {str(e)[:120]}",
            )

        try:
            stdout, stderr = proc.communicate(input=composed, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.communicate(timeout=2.0)
            except Exception:
                pass
            return CompletionResult(
                text="", backend_id=self.backend_id, model=model or "",
                latency_ms=int((time.time() - t0) * 1000),
                error="timeout",
            )
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            return CompletionResult(
                text="", backend_id=self.backend_id, model=model or "",
                latency_ms=int((time.time() - t0) * 1000),
                error=f"communicate failed: {type(e).__name__}: {str(e)[:120]}",
            )

        latency_ms = int((time.time() - t0) * 1000)

        if proc.returncode != 0:
            err = (stderr or "")[:200].strip() or f"exit code {proc.returncode}"
            return CompletionResult(
                text="", backend_id=self.backend_id, model=model or "",
                latency_ms=latency_ms, error=err,
            )

        text = stdout or ""
        truncated = False
        if len(text.encode("utf-8", errors="replace")) > _MAX_OUTPUT_BYTES:
            # Cut by characters so we don't split a UTF-8 sequence; the
            # byte bound is a defense-in-depth check, not the primary cut.
            text = text[: _MAX_OUTPUT_BYTES]
            truncated = True

        return CompletionResult(
            text=text.rstrip("\n"),
            backend_id=self.backend_id,
            model=model or "",
            latency_ms=latency_ms,
            error="output truncated" if truncated else "",
        )


__all__ = ["ClaudeCodeCliBackend"]
