"""L0 — Backend registry + claude_code_cli subprocess adapter.

ARCHITECTURE.md §5.7.2: 미들웨어는 모델 SDK 직접 import 금지, 새 백엔드
는 registry 만 확장. opt-in for the external CLI.

Tests:
  * registry round-trip + Protocol enforcement
  * ollama_local always registered (no env)
  * claude_code_cli NOT registered without JAMES_ENABLE_CLAUDE_BACKEND
  * claude_code_cli registered WITH the opt-in env
  * subprocess success / non-zero exit / timeout / missing CLI paths
  * stdin delivery — a prompt with shell metacharacters never reaches argv
  * env whitelist — non-whitelisted env vars do not leak to the child
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _reimport_backends(env_overrides=None):
    """Re-import core.reasoning.backends with a fresh registry under the
    given env. Returns the freshly loaded module.
    """
    import core.reasoning.backends as mod
    # ensure the submodules cached in sys.modules don't carry stale
    # auto-register state into the new import
    for name in list(sys.modules):
        if name.startswith("core.reasoning.backends"):
            del sys.modules[name]
    with patch.dict(os.environ, env_overrides or {}, clear=False):
        mod = importlib.import_module("core.reasoning.backends")
    return mod


# Snapshot the ORIGINAL module objects at test-module import so
# tearDown can put them back. Re-importing in tearDown (the previous
# strategy) left a *new* module object in sys.modules — any other test
# module that bound ``CompletionResult`` (or a backend class) at
# pytest-collection time then failed ``isinstance`` checks against
# instances created from the fresh module (observed as the
# order-dependent test_backend_conformance R1 failure when this file
# ran first). Restoring the originals keeps class identity stable
# across the whole session.
import core.reasoning.backends as _orig_backends_pkg  # noqa: E402
_ORIG_BACKEND_MODULES = {
    name: module
    for name, module in sys.modules.items()
    if name.startswith("core.reasoning.backends")
}


def _restore_backends():
    """Reinstate the original core.reasoning.backends module objects
    (and the parent-package attribute) captured at import time."""
    for name in list(sys.modules):
        if name.startswith("core.reasoning.backends"):
            del sys.modules[name]
    sys.modules.update(_ORIG_BACKEND_MODULES)
    import core.reasoning as _parent
    _parent.backends = _ORIG_BACKEND_MODULES["core.reasoning.backends"]


class RegistryProtocolTests(unittest.TestCase):

    def test_ollama_local_always_registered(self):
        from core.reasoning import backends
        self.assertIn("ollama_local", backends.list_backends())

    def test_get_backend_unknown_raises_keyerror(self):
        from core.reasoning import backends
        with self.assertRaises(KeyError) as ctx:
            backends.get_backend("definitely_not_a_backend")
        self.assertIn("no backend registered", str(ctx.exception))

    def test_register_backend_rejects_non_protocol(self):
        from core.reasoning import backends
        class NotABackend:
            pass
        with self.assertRaises(TypeError):
            backends.register_backend("broken", NotABackend())

    def test_register_backend_idempotent_with_same_instance(self):
        from core.reasoning import backends
        b = backends.get_backend("ollama_local")
        backends.register_backend("ollama_local", b)   # must not raise
        self.assertIs(backends.get_backend("ollama_local"), b)

    def test_register_backend_rejects_different_instance_same_name(self):
        from core.reasoning import backends
        from core.reasoning.backends.ollama_local import OllamaLocalBackend
        with self.assertRaises(ValueError):
            backends.register_backend("ollama_local", OllamaLocalBackend())


class OptInGateTests(unittest.TestCase):
    """JAMES_ENABLE_CLAUDE_BACKEND=1 controls auto-registration of the
    external CLI backend. Default (env unset) → NOT registered.
    """

    def setUp(self):
        # snapshot relevant env vars
        self._saved = {k: os.environ.get(k) for k in
                       ("JAMES_ENABLE_CLAUDE_BACKEND",
                        "JAMES_CLAUDE_CLI_PATH")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        # always restore the ORIGINAL registry module for downstream
        # tests (a re-import would break cross-module class identity)
        _restore_backends()

    def test_claude_backend_absent_when_env_unset(self):
        os.environ.pop("JAMES_ENABLE_CLAUDE_BACKEND", None)
        mod = _reimport_backends()
        self.assertNotIn("claude_code_cli", mod.list_backends())

    def test_claude_backend_present_when_opted_in(self):
        mod = _reimport_backends({"JAMES_ENABLE_CLAUDE_BACKEND": "1"})
        self.assertIn("claude_code_cli", mod.list_backends())

    def test_claude_backend_absent_when_env_is_zero(self):
        mod = _reimport_backends({"JAMES_ENABLE_CLAUDE_BACKEND": "0"})
        self.assertNotIn("claude_code_cli", mod.list_backends())


class ClaudeCliSubprocessTests(unittest.TestCase):
    """Mock subprocess.Popen to exercise the adapter without an actual
    claude CLI on the test machine.
    """

    def _backend(self, cli_path="/fake/claude"):
        from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend
        return ClaudeCodeCliBackend(cli_path=cli_path)

    def _mock_popen(self, stdout="hello world\n", stderr="", returncode=0):
        proc = MagicMock()
        proc.communicate.return_value = (stdout, stderr)
        proc.returncode = returncode
        return proc

    def test_missing_cli_returns_error_not_raise(self):
        from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend
        # explicit non-existent path
        b = ClaudeCodeCliBackend(cli_path="/nope/never/exists")
        # since we passed cli_path explicitly, _cli_path returns it as-is
        # and the subprocess.Popen call will fail FileNotFoundError →
        # caught and turned into error="spawn failed: ..."
        with patch("subprocess.Popen", side_effect=FileNotFoundError("no such file")):
            res = b.complete("hi")
        self.assertEqual(res.text, "")
        self.assertTrue(res.error.startswith("spawn failed"))
        self.assertEqual(res.backend_id, "claude_code_cli")

    def test_resolved_cli_path_none_returns_cli_not_found(self):
        from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend
        b = ClaudeCodeCliBackend(cli_path=None)
        # patch the resolver to return None (the realistic case on a
        # machine without claude installed)
        with patch("core.reasoning.backends.claude_code_cli._resolve_cli_path",
                   return_value=None):
            res = b.complete("hi")
        self.assertEqual(res.text, "")
        self.assertEqual(res.error, "cli not found")

    def test_happy_path_returns_text(self):
        b = self._backend()
        proc = self._mock_popen(stdout="42\n")
        with patch("subprocess.Popen", return_value=proc):
            res = b.complete("what is the answer", system="be brief")
        self.assertEqual(res.text, "42")   # rstrip("\n") applied
        self.assertEqual(res.error, "")
        self.assertGreaterEqual(res.latency_ms, 0)

    def test_non_zero_exit_returns_error(self):
        b = self._backend()
        proc = self._mock_popen(stdout="", stderr="auth failed", returncode=2)
        with patch("subprocess.Popen", return_value=proc):
            res = b.complete("x")
        self.assertEqual(res.text, "")
        self.assertIn("auth failed", res.error)

    def test_timeout_kills_and_reports(self):
        import subprocess as sp
        b = self._backend()
        proc = MagicMock()
        proc.communicate.side_effect = sp.TimeoutExpired(cmd="claude", timeout=1.0)
        with patch("subprocess.Popen", return_value=proc):
            res = b.complete("slow prompt", timeout=0.001)
        self.assertEqual(res.error, "timeout")
        proc.kill.assert_called_once()

    def test_prompt_with_shell_metachars_never_in_argv(self):
        """SECURITY: a prompt containing `;`, `|`, `$()` etc. must reach
        the subprocess via stdin, never via argv. If argv ever contains
        the prompt the test fails — that would be a shell-injection
        vector even with shell=False.
        """
        b = self._backend()
        evil = "; rm -rf / && echo pwned $(whoami) `id`"
        proc = self._mock_popen()
        with patch("subprocess.Popen", return_value=proc) as p:
            b.complete(evil)
        # argv is the first positional arg to Popen
        argv = p.call_args.args[0]
        joined = " ".join(argv)
        for fragment in ("rm -rf", "pwned", "whoami", "$(", "`id`"):
            self.assertNotIn(fragment, joined,
                             f"prompt fragment {fragment!r} leaked into argv")
        # stdin must carry the evil prompt verbatim instead
        kwargs = p.call_args.kwargs
        self.assertTrue(kwargs.get("stdin"))
        stdin_arg = proc.communicate.call_args.kwargs.get("input", "")
        self.assertIn(evil, stdin_arg)

    def test_env_whitelist_does_not_leak_secrets(self):
        """SECURITY: only the whitelist passes through. A secret stashed
        in some other env var (`JAMES_API_KEY`, `AWS_*`, `GCP_*`) must
        NOT reach the child. The whitelist is documented in the
        module docstring §"Security posture" #3.
        """
        b = self._backend()
        proc = self._mock_popen()
        secret_env = {
            "JAMES_API_KEY": "leak-me",
            "AWS_SECRET_ACCESS_KEY": "also-leak",
            "GCP_CREDENTIALS_JSON": "also-also-leak",
            "ANTHROPIC_API_KEY": "ok-to-forward",
            "PATH": os.environ.get("PATH", ""),
        }
        with patch.dict(os.environ, secret_env, clear=False), \
             patch("subprocess.Popen", return_value=proc) as p:
            b.complete("x")
        env_passed = p.call_args.kwargs.get("env", {})
        self.assertIn("ANTHROPIC_API_KEY", env_passed)
        self.assertIn("PATH", env_passed)
        for leaked in ("JAMES_API_KEY", "AWS_SECRET_ACCESS_KEY",
                       "GCP_CREDENTIALS_JSON"):
            self.assertNotIn(leaked, env_passed,
                             f"{leaked!r} leaked through whitelist")

    def test_env_whitelist_includes_windows_essentials(self):
        """S5c — Windows runtime essentials are forwarded so claude.CMD
        wrapper actually runs. Without `SystemRoot` on Windows the Node
        wrapper exits with returncode 1 + empty stderr (caught by S4
        smoke 2026-06-03). The list (SystemRoot, APPDATA, LOCALAPPDATA,
        USERPROFILE, TEMP, TMP) is a Windows baseline runtime set, not
        app-specific secrets.
        """
        b = self._backend()
        proc = self._mock_popen()
        windows_env = {
            "SystemRoot": "C:\\Windows",
            "APPDATA": "C:\\Users\\test\\AppData\\Roaming",
            "LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local",
            "USERPROFILE": "C:\\Users\\test",
            "TEMP": "C:\\Users\\test\\AppData\\Local\\Temp",
            "TMP": "C:\\Users\\test\\AppData\\Local\\Temp",
            "PATH": os.environ.get("PATH", ""),
        }
        with patch.dict(os.environ, windows_env, clear=False), \
             patch("subprocess.Popen", return_value=proc) as p:
            b.complete("x")
        env_passed = p.call_args.kwargs.get("env", {})
        for required in ("SystemRoot", "APPDATA", "LOCALAPPDATA",
                         "USERPROFILE", "TEMP", "TMP"):
            self.assertIn(required, env_passed,
                          f"Windows essential {required!r} not forwarded")

    def test_default_cwd_is_neutral_not_project(self):
        """S5c — default cwd is `tempfile.gettempdir()`, NOT the project
        directory. Spawning `claude -p` inside the project loads the
        project CLAUDE.md and puts the CLI into coding-agent mode
        (responds to the briefing, not the prompt). Caught by S4 smoke
        2026-06-03.
        """
        import tempfile
        b = self._backend()
        proc = self._mock_popen()
        with patch("subprocess.Popen", return_value=proc) as p:
            b.complete("x")
        cwd_passed = p.call_args.kwargs.get("cwd")
        self.assertEqual(cwd_passed, tempfile.gettempdir())
        # And cwd is definitely NOT the project root or current dir
        self.assertNotEqual(cwd_passed, os.getcwd())

    def test_explicit_cwd_kwarg_overrides_default(self):
        """Operators wanting a project-context call pass `cwd=` explicitly.
        Default neutral cwd is the safe default; explicit override is
        the documented escape hatch."""
        b = self._backend()
        proc = self._mock_popen()
        custom = "C:\\some\\other\\path" if os.name == "nt" else "/some/other/path"
        with patch("subprocess.Popen", return_value=proc) as p:
            b.complete("x", cwd=custom)
        cwd_passed = p.call_args.kwargs.get("cwd")
        self.assertEqual(cwd_passed, custom)

    def test_model_flag_passed_to_argv(self):
        """User-selected model string DOES appear in argv (after the
        --model flag) — this is the only field that can. CLI validates
        the value itself, so we don't enumerate the catalog here.
        """
        b = self._backend()
        proc = self._mock_popen()
        with patch("subprocess.Popen", return_value=proc) as p:
            b.complete("x", model="claude-sonnet-4-6")
        argv = p.call_args.args[0]
        self.assertIn("--model", argv)
        self.assertIn("claude-sonnet-4-6", argv)


class OllamaLocalAdapterTests(unittest.TestCase):
    """ollama_local wraps RouterWrapper.call_gemma. Verify the wrapper
    forwards arguments and surfaces error strings as `error`.
    """

    def test_complete_returns_router_text(self):
        from core.reasoning.backends.ollama_local import OllamaLocalBackend
        b = OllamaLocalBackend()
        fake_router = MagicMock()
        fake_router.call_gemma.return_value = "hello"
        b._router = fake_router
        res = b.complete("hi", system="be helpful", max_tokens=128)
        self.assertEqual(res.text, "hello")
        self.assertEqual(res.error, "")
        fake_router.call_gemma.assert_called_once()
        called_prompt = fake_router.call_gemma.call_args.args[0]
        self.assertIn("be helpful", called_prompt)
        self.assertIn("hi", called_prompt)

    def test_complete_marks_router_error_string(self):
        from core.reasoning.backends.ollama_local import OllamaLocalBackend
        b = OllamaLocalBackend()
        fake_router = MagicMock()
        fake_router.call_gemma.return_value = "[Gemma 응답 없음]"
        b._router = fake_router
        res = b.complete("hi")
        self.assertEqual(res.text, "[Gemma 응답 없음]")
        self.assertNotEqual(res.error, "")

    def test_complete_router_exception_returns_error_not_raise(self):
        from core.reasoning.backends.ollama_local import OllamaLocalBackend
        b = OllamaLocalBackend()
        fake_router = MagicMock()
        fake_router.call_gemma.side_effect = RuntimeError("ollama down")
        b._router = fake_router
        res = b.complete("hi")
        self.assertEqual(res.text, "")
        self.assertIn("RuntimeError", res.error)


class DefaultBackendResolutionTests(unittest.TestCase):
    """[JAMES_REASONING_BACKEND wiring 2026-05-18]

    The 4 cognitive stages (query_rewriter, planner, reflect, verify)
    used to hardcode ``DEFAULT_BACKEND_ID = "ollama_local"``. After
    this PR they call ``get_default_backend_id()`` at import time,
    which reads ``JAMES_REASONING_BACKEND``. These tests pin:

      * env unset → "ollama_local" (backwards compat)
      * env set to a registered backend → that name
      * env set to an unknown / unregistered name → warning + fallback
        to "ollama_local" (so a typo doesn't take the pipeline down)
    """

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("JAMES_REASONING_BACKEND",
                        "JAMES_ENABLE_CLAUDE_BACKEND",
                        "JAMES_CLAUDE_CLI_PATH")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _restore_backends()

    def test_env_unset_returns_ollama_local(self):
        os.environ.pop("JAMES_REASONING_BACKEND", None)
        mod = _reimport_backends()
        self.assertEqual(mod.get_default_backend_id(), "ollama_local")

    def test_env_empty_string_returns_ollama_local(self):
        # Whitespace-only env should be treated as unset — operators
        # who clear with `set JAMES_REASONING_BACKEND=` shouldn't get
        # unexpected behavior. We set the env directly (not via
        # _reimport_backends's patch.dict) because the helper reads
        # the env at CALL time, after the patch.dict scope ends.
        os.environ["JAMES_REASONING_BACKEND"] = "   "
        mod = _reimport_backends()
        self.assertEqual(mod.get_default_backend_id(), "ollama_local")

    def test_env_set_to_registered_backend_honored(self):
        os.environ["JAMES_REASONING_BACKEND"] = "claude_code_cli"
        os.environ["JAMES_ENABLE_CLAUDE_BACKEND"] = "1"
        mod = _reimport_backends()
        self.assertEqual(mod.get_default_backend_id(), "claude_code_cli")

    def test_env_set_to_unknown_falls_back(self):
        # A typo or a half-configured backend (e.g. claude requested
        # without JAMES_ENABLE_CLAUDE_BACKEND=1) must not break the
        # pipeline. Print and fall back.
        os.environ["JAMES_REASONING_BACKEND"] = "rm-rf-slash"
        mod = _reimport_backends()
        self.assertEqual(mod.get_default_backend_id(), "ollama_local")

    def test_env_set_to_claude_without_optin_falls_back(self):
        # The most likely operator confusion: enable JAMES_REASONING_BACKEND
        # but forget JAMES_ENABLE_CLAUDE_BACKEND=1. Must not break.
        os.environ["JAMES_REASONING_BACKEND"] = "claude_code_cli"
        os.environ.pop("JAMES_ENABLE_CLAUDE_BACKEND", None)
        mod = _reimport_backends()
        # claude_code_cli is NOT in registry → fallback
        self.assertNotIn("claude_code_cli", mod.list_backends())
        self.assertEqual(mod.get_default_backend_id(), "ollama_local")

    def test_stage_modules_consume_helper(self):
        """The 4 stage modules must call get_default_backend_id() at
        import time. Source-level assertion so the wiring can't be
        accidentally reverted to a hardcoded string in a future PR.
        """
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        stage_files = [
            root / "core" / "retrieval" / "query_rewriter.py",
            root / "core" / "reasoning" / "planner.py",
            # reflect.py became the reflect/ package in the v0.6
            # module-size splits (#900-#904); the backend wiring
            # lives in prompts.py.
            root / "core" / "reasoning" / "reflect" / "prompts.py",
            root / "core" / "reasoning" / "verify.py",
        ]
        for f in stage_files:
            with self.subTest(stage=f.name):
                src = f.read_text(encoding="utf-8")
                self.assertIn(
                    "get_default_backend_id",
                    src,
                    f"{f.name} must consume "
                    f"get_default_backend_id() — a hardcoded "
                    f"'ollama_local' string defeats the env-driven "
                    f"backend swap. Re-thread through the helper.",
                )
                self.assertNotIn(
                    'DEFAULT_BACKEND_ID = "ollama_local"',
                    src,
                    f"{f.name} still has the old hardcoded default. "
                    f"Replace with DEFAULT_BACKEND_ID = _get_default_backend().",
                )


class StageBackendResolutionTests(unittest.TestCase):
    """[Track 1 PR-A, 2026-05-19]

    ``resolve_backend_for_stage(stage)`` layers per-stage overrides on
    top of the global ``JAMES_REASONING_BACKEND``:

      1. ``JAMES_BACKEND_<STAGE>`` env (e.g. JAMES_BACKEND_SYNTH)
      2. ``JAMES_REASONING_BACKEND`` env (global)
      3. ``"ollama_local"`` (hardcoded default)

    These tests pin every transition the docs design promises.
    """

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("JAMES_REASONING_BACKEND",
                        "JAMES_BACKEND_SYNTH",
                        "JAMES_BACKEND_RETRIEVE",
                        "JAMES_ENABLE_CLAUDE_BACKEND")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _restore_backends()

    def test_unknown_stage_raises(self):
        # Stage typo at the call site should fail loudly during dev
        # — silent fallthrough would silently bypass the override.
        from core.reasoning import backends
        with self.assertRaises(ValueError):
            backends.resolve_backend_for_stage("snyth")

    def test_no_env_returns_ollama_local(self):
        for k in ("JAMES_REASONING_BACKEND", "JAMES_BACKEND_SYNTH"):
            os.environ.pop(k, None)
        mod = _reimport_backends()
        self.assertEqual(mod.resolve_backend_for_stage("synth"), "ollama_local")

    def test_per_stage_env_overrides_global(self):
        os.environ["JAMES_REASONING_BACKEND"] = "claude_code_cli"
        os.environ["JAMES_BACKEND_SYNTH"] = "ollama_local"
        os.environ["JAMES_ENABLE_CLAUDE_BACKEND"] = "1"
        mod = _reimport_backends()
        # Global says claude, but per-stage synth pins ollama_local.
        self.assertEqual(mod.resolve_backend_for_stage("synth"),
                         "ollama_local")
        # Other stages still follow the global.
        self.assertEqual(mod.resolve_backend_for_stage("verify"),
                         "claude_code_cli")

    def test_per_stage_typo_falls_through_to_global(self):
        # Per-stage typo (or claude requested without opt-in) must not
        # break the rest of the pipeline — fall through to global, not
        # raise.
        os.environ["JAMES_REASONING_BACKEND"] = "ollama_local"
        os.environ["JAMES_BACKEND_SYNTH"] = "rm-rf-slash"
        os.environ.pop("JAMES_ENABLE_CLAUDE_BACKEND", None)
        mod = _reimport_backends()
        self.assertEqual(mod.resolve_backend_for_stage("synth"),
                         "ollama_local")

    def test_per_stage_falls_through_to_global_when_global_set(self):
        # Stage env unset → uses JAMES_REASONING_BACKEND directly.
        os.environ.pop("JAMES_BACKEND_SYNTH", None)
        os.environ["JAMES_REASONING_BACKEND"] = "claude_code_cli"
        os.environ["JAMES_ENABLE_CLAUDE_BACKEND"] = "1"
        mod = _reimport_backends()
        self.assertEqual(mod.resolve_backend_for_stage("synth"),
                         "claude_code_cli")


class SynthCallSitesUseBackendHelperTests(unittest.TestCase):
    """Architectural assertion: every synth call site must reach the
    LLM through ``trace_synth_call`` rather than the legacy
    ``engine.llm.call_gemma`` pattern. A future refactor that re-adds
    a direct ``call_gemma`` invocation in the middleware should fail
    here, not in production.
    """

    def test_no_direct_call_gemma_in_middleware(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        middleware_files = [
            root / "core" / "reasoning" / "engine_synth.py",
            # pipeline_synth.py became the pipeline_synth/ package in
            # the v0.6 module-size splits (#900-#904) — scan every
            # module in it so a re-added direct call can't hide.
            *sorted((root / "core" / "reasoning" / "pipeline_synth").glob("*.py")),
            root / "core" / "reasoning" / "modes" / "chat.py",
            root / "core" / "reasoning" / "modes" / "coding.py",
            root / "core" / "reasoning" / "modes" / "self_evolve.py",
            root / "core" / "reasoning" / "modes" / "wiki_edit.py",
        ]
        for f in middleware_files:
            with self.subTest(file=f.name):
                src = f.read_text(encoding="utf-8")
                self.assertNotIn(
                    "engine.llm.call_gemma",
                    src,
                    f"{f.name} still calls engine.llm.call_gemma "
                    f"directly. After Track 1 PR-A, every synth call "
                    f"site must route through trace_synth_call → "
                    f"get_backend(...).complete(...).",
                )


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
