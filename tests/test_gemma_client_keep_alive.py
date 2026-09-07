"""v0.6.1 design review (2026-07-01) — Ollama keep-alive wiring.

Ollama's server default unloads an idle model after ~5 minutes; the
next call then pays a full cold reload (``done_reason="load"``, tens
of seconds on 12B+ models). ``GemmaClient`` now sends
``keep_alive`` (default ``"30m"``, env ``JAMES_OLLAMA_KEEP_ALIVE``)
so the model stays resident across a working session.

Tested via ``_resolve_keep_alive`` directly (no HTTP dependency) plus
a request-body test with ``requests.post`` mocked out.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ResolveKeepAliveTests(unittest.TestCase):
    """Pins for ``core.gemma_client._resolve_keep_alive``."""

    def setUp(self):
        self._snapshot = os.environ.pop("JAMES_OLLAMA_KEEP_ALIVE", None)

    def tearDown(self):
        if self._snapshot is not None:
            os.environ["JAMES_OLLAMA_KEEP_ALIVE"] = self._snapshot
        else:
            os.environ.pop("JAMES_OLLAMA_KEEP_ALIVE", None)

    def test_default_when_env_unset(self):
        from core.gemma_client import _DEFAULT_KEEP_ALIVE, _resolve_keep_alive
        self.assertEqual(_resolve_keep_alive(), _DEFAULT_KEEP_ALIVE)
        self.assertEqual(_DEFAULT_KEEP_ALIVE, "30m")

    def test_env_override_honoured(self):
        from core.gemma_client import _resolve_keep_alive
        os.environ["JAMES_OLLAMA_KEEP_ALIVE"] = "2h"
        self.assertEqual(_resolve_keep_alive(), "2h")

    def test_opt_out_values_return_none(self):
        from core.gemma_client import _resolve_keep_alive
        for off in ("0", "off", "OFF", "none", "false", "", "  "):
            os.environ["JAMES_OLLAMA_KEEP_ALIVE"] = off
            self.assertIsNone(
                _resolve_keep_alive(),
                msg=f"env={off!r} should omit keep_alive",
            )

    def test_env_read_per_call_not_at_import(self):
        from core.gemma_client import _resolve_keep_alive
        os.environ["JAMES_OLLAMA_KEEP_ALIVE"] = "10m"
        self.assertEqual(_resolve_keep_alive(), "10m")
        os.environ["JAMES_OLLAMA_KEEP_ALIVE"] = "1h"
        self.assertEqual(_resolve_keep_alive(), "1h")


class CallGemmaKeepAliveBodyTests(unittest.TestCase):
    """The resolved keep-alive value must reach the Ollama request
    body (and be omitted entirely on opt-out)."""

    def setUp(self):
        self._snapshot = os.environ.pop("JAMES_OLLAMA_KEEP_ALIVE", None)

    def tearDown(self):
        if self._snapshot is not None:
            os.environ["JAMES_OLLAMA_KEEP_ALIVE"] = self._snapshot
        else:
            os.environ.pop("JAMES_OLLAMA_KEEP_ALIVE", None)

    def _call_and_capture_body(self):
        from core.gemma_client import GemmaClient

        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["body"] = json

            class _Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"response": "ok", "done_reason": "stop"}

            return _Resp()

        client = GemmaClient()
        with patch("core.gemma_client.client.requests.post",
                   side_effect=fake_post), \
             patch("core.model_resolver.installed_models",
                   return_value={"gemma3:4b"}):
            client.call_gemma("hello", model="gemma3:4b", use_cache=False)
        return captured["body"]

    def test_keep_alive_present_by_default(self):
        body = self._call_and_capture_body()
        self.assertEqual(body.get("keep_alive"), "30m")

    def test_keep_alive_env_value_forwarded(self):
        os.environ["JAMES_OLLAMA_KEEP_ALIVE"] = "45m"
        body = self._call_and_capture_body()
        self.assertEqual(body.get("keep_alive"), "45m")

    def test_keep_alive_omitted_on_opt_out(self):
        os.environ["JAMES_OLLAMA_KEEP_ALIVE"] = "off"
        body = self._call_and_capture_body()
        self.assertNotIn("keep_alive", body)


if __name__ == "__main__":
    unittest.main()
