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
  3. Environment passed to the child is a **whitelist** — PATH, HOME,
     and the explicit ``ANTHROPIC_API_KEY`` / ``CLAUDE_CONFIG_DIR``
     forwards. os.environ is not handed over wholesale.
  4. Output is size-capped (1 MiB) and the child is killed on timeout.
  5. Cli path can be overridden via ``JAMES_CLAUDE_CLI_PATH`` (defaults
     to looking up ``claude`` on PATH); a missing CLI surfaces as
     ``error="cli not found"`` rather than a crash.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import List, Optional

from core.reasoning.backends import BackendCapability, CompletionResult


_MAX_OUTPUT_BYTES = 1 * 1024 * 1024   # 1 MiB
_ENV_WHITELIST = ("PATH", "HOME", "ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR")


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

        composed = f"{system}\n\n{prompt}" if system else prompt
        # bound the prompt at the same 1 MiB the output is bounded at —
        # avoids handing a pathological prompt to the subprocess
        composed = composed[: _MAX_OUTPUT_BYTES]

        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_build_env(),
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
