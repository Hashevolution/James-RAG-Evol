"""JAMES_PLUGINS env-var loader for external backends.

Per ``docs/design/v0.3-llm-provider-contract.md`` §"Registration", the
plugin loader reads a comma-separated list of module paths from
``JAMES_PLUGINS`` and imports each at server startup. A plugin module
typically calls ``register_backend(...)`` at top level; this loader
just triggers the import so that registration side-effect fires.

Failures during plugin import are **fatal**. A plugin that silently
fails to load would leave the operator running an apparently-healthy
server that's missing the backend they configured — far worse than
loud failure at startup.

Tests:
  * empty / unset JAMES_PLUGINS → no-op, no error
  * single-module path → module imported, side-effect register fires
  * multi-module list → each module imported in order
  * non-existent module → raises RuntimeError with "JAMES_PLUGINS"
    prefix (operator-friendly attribution)
  * plugin that throws on import → wrapped RuntimeError surfaces the
    original error class / message
  * whitespace around commas tolerated
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.reasoning.backends import (  # noqa: E402
    _REGISTRY,
    _clear_for_tests,
    _load_plugins,
    register_backend,
)


class JamesPluginsLoaderTests(unittest.TestCase):

    def setUp(self):
        # Snapshot the live registry + JAMES_PLUGINS env so failures
        # mid-test don't pollute the next module to run.
        self._saved_registry = dict(_REGISTRY)
        self._saved_plugins = os.environ.get("JAMES_PLUGINS")
        # Work inside a fresh sys.path entry that we tear down after.
        self._plugin_dir = tempfile.mkdtemp(prefix="james_plugin_test_")
        sys.path.insert(0, self._plugin_dir)
        self._created_modules = []

    def tearDown(self):
        _clear_for_tests()
        for name, inst in self._saved_registry.items():
            register_backend(name, inst)
        if self._saved_plugins is None:
            os.environ.pop("JAMES_PLUGINS", None)
        else:
            os.environ["JAMES_PLUGINS"] = self._saved_plugins
        if self._plugin_dir in sys.path:
            sys.path.remove(self._plugin_dir)
        # Drop the test modules from sys.modules so a re-import next
        # test re-runs the registration side-effect.
        for mod in self._created_modules:
            sys.modules.pop(mod, None)
        try:
            import shutil
            shutil.rmtree(self._plugin_dir, ignore_errors=True)
        except Exception:
            pass

    def _write_plugin(self, name: str, body: str) -> None:
        """Write a Python module under the temp plugin dir + remember
        its dotted name so tearDown can pop it from sys.modules.
        """
        path = Path(self._plugin_dir) / f"{name}.py"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        self._created_modules.append(name)

    def test_empty_env_is_noop(self):
        os.environ.pop("JAMES_PLUGINS", None)
        _load_plugins()   # must not raise, must not register anything

    def test_whitespace_only_env_is_noop(self):
        os.environ["JAMES_PLUGINS"] = "   "
        _load_plugins()   # treat as effectively unset

    def test_single_plugin_imported_and_registers(self):
        self._write_plugin("james_test_plugin_one", """
            from core.reasoning.backends import (
                register_backend, CompletionResult,
            )

            class _Stub:
                backend_id = "test_plugin_one"
                def complete(self, prompt, *, system="", max_tokens=1024,
                             timeout=60.0, model=None, use_cache=True,
                             temperature=None, **opts):
                    return CompletionResult(
                        text="stub", backend_id=self.backend_id,
                    )

            register_backend("test_plugin_one", _Stub())
        """)
        os.environ["JAMES_PLUGINS"] = "james_test_plugin_one"
        _load_plugins()
        self.assertIn("test_plugin_one", _REGISTRY)

    def test_multiple_plugins_imported_in_order(self):
        for n in ("two_a", "two_b"):
            self._write_plugin(f"james_test_plugin_{n}", f"""
                from core.reasoning.backends import (
                    register_backend, CompletionResult,
                )

                class _Stub:
                    backend_id = "test_plugin_{n}"
                    def complete(self, prompt, *, system="", max_tokens=1024,
                                 timeout=60.0, model=None, use_cache=True,
                                 temperature=None, **opts):
                        return CompletionResult(
                            text="", backend_id=self.backend_id,
                        )

                register_backend("test_plugin_{n}", _Stub())
            """)
        os.environ["JAMES_PLUGINS"] = (
            "james_test_plugin_two_a,james_test_plugin_two_b"
        )
        _load_plugins()
        self.assertIn("test_plugin_two_a", _REGISTRY)
        self.assertIn("test_plugin_two_b", _REGISTRY)

    def test_whitespace_around_commas_tolerated(self):
        self._write_plugin("james_test_plugin_ws", """
            from core.reasoning.backends import (
                register_backend, CompletionResult,
            )

            class _Stub:
                backend_id = "test_plugin_ws"
                def complete(self, prompt, *, system="", max_tokens=1024,
                             timeout=60.0, model=None, use_cache=True,
                             temperature=None, **opts):
                    return CompletionResult(
                        text="", backend_id=self.backend_id,
                    )

            register_backend("test_plugin_ws", _Stub())
        """)
        # Pad with whitespace to mimic a sloppily-edited env file.
        os.environ["JAMES_PLUGINS"] = "  james_test_plugin_ws ,   "
        _load_plugins()
        self.assertIn("test_plugin_ws", _REGISTRY)

    def test_missing_module_is_fatal(self):
        os.environ["JAMES_PLUGINS"] = "definitely_does_not_exist_jp_99"
        with self.assertRaises(RuntimeError) as ctx:
            _load_plugins()
        self.assertIn("JAMES_PLUGINS", str(ctx.exception))
        self.assertIn("definitely_does_not_exist_jp_99", str(ctx.exception))

    def test_plugin_import_error_is_fatal(self):
        self._write_plugin("james_test_plugin_throws", """
            raise RuntimeError("plugin intentionally broken at import")
        """)
        os.environ["JAMES_PLUGINS"] = "james_test_plugin_throws"
        with self.assertRaises(RuntimeError) as ctx:
            _load_plugins()
        msg = str(ctx.exception)
        self.assertIn("JAMES_PLUGINS", msg)
        # Original error class + message must surface for debugging.
        self.assertIn("RuntimeError", msg)
        self.assertIn("intentionally broken", msg)

    def test_loader_does_not_register_if_plugin_skips_registration(self):
        """A plugin that imports cleanly but forgets to call
        register_backend is valid (it might register conditionally).
        The loader must not invent a registration on the plugin's
        behalf.
        """
        before = set(_REGISTRY)
        self._write_plugin("james_test_plugin_silent", """
            # Intentionally empty — no register_backend call.
            VALUE = 1
        """)
        os.environ["JAMES_PLUGINS"] = "james_test_plugin_silent"
        _load_plugins()
        after = set(_REGISTRY)
        self.assertEqual(
            before, after,
            "loader must not auto-register on the plugin's behalf — "
            "registration is the plugin's responsibility.",
        )


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
