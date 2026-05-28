"""[PR plan-1, 2026-05-09] core.model_resolver — fallback chain.

The resolver's job: never let `call_gemma(model=None)` hit Ollama with
a missing tag. The 4-step chain (requested → preference → any → none)
is exhaustively asserted here with a mocked installed-set so the tests
don't need a live Ollama.

Run:
    python -m unittest tests.test_model_resolver
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh_resolver():
    """Re-import the module so cache state doesn't bleed between tests."""
    import core.model_resolver as mr
    importlib.reload(mr)
    mr.invalidate_cache()
    return mr


class ResolveChainTests(unittest.TestCase):
    """The 4-step resolution chain."""

    def setUp(self):
        self.mr = _fresh_resolver()

    def test_requested_installed_wins(self):
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"gemma3:4b", "gemma3:1b"}):
            r = self.mr.resolve_for_mode("chat", requested="gemma3:1b")
        self.assertEqual(r.tag, "gemma3:1b")
        self.assertEqual(r.source, "requested")
        self.assertEqual(r.warning, "")

    def test_requested_missing_falls_to_preference(self):
        # User asked for gemma4:e4b (config default) but installed only
        # gemma3:4b → resolver returns gemma3:4b with a warning.
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"gemma3:4b"}):
            r = self.mr.resolve_for_mode("chat", requested="gemma4:e4b")
        self.assertEqual(r.tag, "gemma3:4b")
        self.assertEqual(r.source, "preference")
        self.assertIn("gemma4:e4b", r.warning)
        self.assertIn("gemma3:4b", r.warning)

    def test_preference_first_match_wins(self):
        # If gemma3:4b and gemma3:12b both installed, gemma3:4b should
        # win (higher in default preference list).
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"gemma3:12b", "gemma3:4b"}):
            r = self.mr.resolve_for_mode("chat", requested="")
        self.assertEqual(r.tag, "gemma3:4b")
        self.assertEqual(r.source, "preference")

    def test_no_preference_match_falls_to_any(self):
        # Installed model is something not on the preference list at
        # all — last-resort branch.
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"obscure-model:7b"}):
            r = self.mr.resolve_for_mode("chat", requested="")
        self.assertEqual(r.tag, "obscure-model:7b")
        self.assertEqual(r.source, "any")
        self.assertIn("last resort", r.warning)

    def test_nothing_installed_returns_none_with_install_command(self):
        with mock.patch.object(self.mr, "installed_models", return_value=set()):
            r = self.mr.resolve_for_mode("chat", requested="gemma3:4b")
        self.assertEqual(r.tag, "")
        self.assertEqual(r.source, "none")
        self.assertIn("ollama pull", r.warning)
        # Suggestion should be the head of the preference list.
        self.assertIn("gemma3:4b", r.warning)

    def test_fallback_chain_records_attempts(self):
        # The chain must include at least the requested + every
        # preference tag tried until success.
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"gemma3:1b"}):
            r = self.mr.resolve_for_mode("chat", requested="gemma4:e4b")
        # First entry: requested. Then preference list head until match.
        self.assertEqual(r.fallback_chain[0], "gemma4:e4b")
        self.assertIn("gemma3:1b", r.fallback_chain)


class CodingPreferenceTests(unittest.TestCase):
    """`mode='coding'` uses a different preference list."""

    def setUp(self):
        self.mr = _fresh_resolver()

    def test_coding_prefers_qwen_coder(self):
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"qwen2.5-coder:7b", "gemma3:4b"}):
            r = self.mr.resolve_for_mode("coding", requested="")
        self.assertEqual(r.tag, "qwen2.5-coder:7b")
        self.assertEqual(r.source, "preference")

    def test_coding_falls_back_to_deepseek(self):
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"deepseek-coder:6.7b"}):
            r = self.mr.resolve_for_mode("coding", requested="qwen2.5-coder:32b")
        self.assertEqual(r.tag, "deepseek-coder:6.7b")
        self.assertEqual(r.source, "preference")


class EnvOverrideTests(unittest.TestCase):
    """JAMES_MODEL_PREFERENCE_<MODE> env var rewrites the list."""

    def setUp(self):
        self.mr = _fresh_resolver()

    def test_chat_preference_via_env(self):
        with mock.patch.dict(os.environ,
                             {"JAMES_MODEL_PREFERENCE_CHAT":
                              "custom:1b,custom:4b"}):
            with mock.patch.object(self.mr, "installed_models",
                                   return_value={"custom:1b"}):
                r = self.mr.resolve_for_mode("chat", requested="")
            self.assertEqual(r.tag, "custom:1b")
            self.assertEqual(r.source, "preference")

    def test_unknown_mode_falls_back_to_chat_list(self):
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"gemma3:4b"}):
            r = self.mr.resolve_for_mode("retrieval", requested="")
        # Unknown mode → uses chat preference → gemma3:4b matches.
        self.assertEqual(r.tag, "gemma3:4b")


class CacheBehaviorTests(unittest.TestCase):
    """installed_models() is cached with a TTL; invalidate_cache
    refreshes immediately."""

    def setUp(self):
        self.mr = _fresh_resolver()

    def test_cache_hit_avoids_second_http_call(self):
        # First call hits the mocked URL, second call should NOT.
        with mock.patch("core.model_resolver.urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = (
                b'{"models": [{"name": "gemma3:4b"}]}'
            )
            self.mr.invalidate_cache()
            tags1 = self.mr.installed_models()
            tags2 = self.mr.installed_models()
            self.assertEqual(tags1, {"gemma3:4b"})
            self.assertEqual(tags2, {"gemma3:4b"})
            self.assertEqual(m.call_count, 1,
                "cache hit must skip the second HTTP call")

    def test_invalidate_forces_refresh(self):
        with mock.patch("core.model_resolver.urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = (
                b'{"models": [{"name": "gemma3:4b"}]}'
            )
            self.mr.invalidate_cache()
            self.mr.installed_models()
            self.mr.invalidate_cache()
            self.mr.installed_models()
            self.assertEqual(m.call_count, 2,
                "invalidate_cache() must force a fresh HTTP call")

    def test_ollama_unreachable_returns_empty_set(self):
        with mock.patch("core.model_resolver.urllib.request.urlopen",
                        side_effect=ConnectionRefusedError("ollama down")):
            self.mr.invalidate_cache()
            tags = self.mr.installed_models()
            self.assertEqual(tags, set(),
                "ollama down → empty set (resolver falls through to 'none' "
                "with a clear install command)")


class SnapshotTests(unittest.TestCase):
    """resolution_snapshot() returns the operator-facing observability blob."""

    def setUp(self):
        self.mr = _fresh_resolver()

    def test_snapshot_shape(self):
        with mock.patch.object(self.mr, "installed_models",
                               return_value={"gemma3:4b"}):
            snap = self.mr.resolution_snapshot()
        self.assertIn("chat", snap)
        self.assertIn("coding", snap)
        self.assertIn("installed", snap)
        self.assertIn("preference", snap)
        for k in ("tag", "source", "warning", "fallback_chain"):
            self.assertIn(k, snap["chat"])
            self.assertIn(k, snap["coding"])


class GemmaClientIntegrationTests(unittest.TestCase):
    """Source-level: gemma_client.call_gemma must call resolve_chat()
    when model=None. This is the actual production wiring point."""

    @classmethod
    def setUpClass(cls):
        import inspect
        from core import gemma_client
        cls.src = inspect.getsource(gemma_client)

    def test_call_gemma_imports_resolver(self):
        self.assertIn("from core.model_resolver import resolve_chat", self.src,
            "call_gemma must use the resolver — without this, model=None "
            "still 404s on missing config defaults")

    def test_call_gemma_raises_when_no_models(self):
        # When resolver returns empty tag, call_gemma must raise with
        # the friendly install command — not silently fall through to
        # Ollama and 404.
        idx = self.src.index("if model:")
        body = self.src[idx:idx + 800]
        self.assertIn("RuntimeError", body,
            "no-models case must raise RuntimeError so caller sees the "
            "install command, not a generic 404")

    def test_warning_logged_to_stdout(self):
        # When a fallback happens, [MODEL_RESOLVE] message must surface
        # so the operator can see what's actually being used.
        # Window enlarged to 1500 chars — PR plan-4 added defensive
        # resolution comments, pushing the print() further down.
        idx = self.src.index("if model:")
        body = self.src[idx:idx + 1500]
        self.assertIn("[MODEL_RESOLVE]", body)


class InvalidateHookTests(unittest.TestCase):
    """server_llmwiki: install/delete handlers invalidate the resolver
    cache so a freshly-installed model is usable on the next /query/."""

    @classmethod
    def setUpClass(cls):
        from tests._server_split_helpers import combined_server_source
        cls.src = combined_server_source()

    def test_install_thread_invalidates_cache(self):
        # _start_install_with_progress runs the pull in a background
        # thread; on success status, must call invalidate_cache so the
        # next call_gemma sees the new tag without 60s wait.
        idx = self.src.index("def _start_install_with_progress")
        # Bound at next def.
        nxt = self.src.index("\ndef ", idx + 1)
        body = self.src[idx:nxt]
        self.assertIn("invalidate_cache", body,
            "install thread must invalidate resolver cache on success")

    def test_delete_handler_invalidates_cache(self):
        idx = self.src.index('@app.delete("/admin/llm/delete"')
        nxt = self.src.index("\n@app.", idx + 10)
        body = self.src[idx:nxt]
        self.assertIn("invalidate_cache", body,
            "delete must invalidate resolver cache so the deleted model "
            "isn't used on the next /query/")

    def test_resolution_endpoint_registered(self):
        self.assertIn('@app.get("/admin/llm/resolution"', self.src,
            "/admin/llm/resolution must be registered for operator visibility")


if __name__ == "__main__":
    unittest.main()
