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
        # always restore a normal registry for downstream tests
        _reimport_backends()

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
        """SECURITY: only PATH / HOME / ANTHROPIC_API_KEY /
        CLAUDE_CONFIG_DIR pass through. A secret stashed in some other
        env var must NOT reach the child.
        """
        b = self._backend()
        proc = self._mock_popen()
        secret_env = {
            "JAMES_API_KEY": "leak-me",
            "AWS_SECRET_ACCESS_KEY": "also-leak",
            "ANTHROPIC_API_KEY": "ok-to-forward",
            "PATH": os.environ.get("PATH", ""),
        }
        with patch.dict(os.environ, secret_env, clear=False), \
             patch("subprocess.Popen", return_value=proc) as p:
            b.complete("x")
        env_passed = p.call_args.kwargs.get("env", {})
        self.assertIn("ANTHROPIC_API_KEY", env_passed)
        self.assertIn("PATH", env_passed)
        self.assertNotIn("JAMES_API_KEY", env_passed)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env_passed)

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


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
