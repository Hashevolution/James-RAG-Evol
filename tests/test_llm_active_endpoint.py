"""v0.4 Sprint 2 #3a — `/llm/active` endpoint registration + wiring.

Anchor for the always-visible chat model indicator chip. Three
guarantees pinned here so a refactor that drops the endpoint or
breaks the chip wiring fails CI rather than producing a silently
empty chip:

  1. ``GET /llm/active`` is registered on the FastAPI app.
  2. The endpoint returns the resolve_chat() subset shape
     ``{tag, source, warning}`` (delegating to
     ``core.model_resolver.resolve_chat``).
  3. ``chat.js`` calls the endpoint and ``index.html`` has the chip
     element + tag span the call populates.

The endpoint is api-key-gated (NOT admin-gated) on purpose — every
authenticated chat user needs visibility into which model is
serving them, not just operators. The admin variant
``/admin/llm/resolution`` stays admin-only and exposes the fuller
payload (fallback_chain + preference + installed).
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


REPO = Path(__file__).resolve().parent.parent


class LlmActiveEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Importing the FastAPI app is expensive but only happens
        # once for this class — the resolver / vector store init
        # are cached in module globals.
        from server_llmwiki import app  # noqa: E402
        cls.app = app

    def test_endpoint_registered(self):
        paths = {r.path for r in self.app.routes if hasattr(r, "path")}
        self.assertIn(
            "/llm/active", paths,
            "GET /llm/active is the chat-indicator endpoint added in "
            "v0.4 Sprint 2 #3a. Removing it breaks the header chip. "
            "If you intentionally renamed it, update "
            "frontend/static/chat.js loadActiveModelChip() and this test.",
        )

    def test_endpoint_returns_resolve_chat_subset(self):
        """Call the underlying handler directly with a stubbed
        api_key check + a stubbed resolve_chat so the test stays
        hermetic (no Ollama HTTP needed).

        Verifies the response shape exactly matches the contract
        the chat.js chip relies on: {tag, source, warning}.
        Adding fields would not break the chip but DROPPING any of
        the three would render the chip as 'undefined'."""
        import asyncio
        from unittest.mock import patch
        from core.model_resolver import ResolvedModel
        import server_llmwiki as srv

        fake = ResolvedModel(
            tag="gemma3:4b",
            source="preference",
            fallback_chain=["gemma4:e4b", "gemma3:4b"],
            warning="requested model 'gemma4:e4b' not installed; "
                    "using 'gemma3:4b' from preference list",
        )

        with patch.object(srv, "verify_api_key", lambda _k: None), \
             patch("core.model_resolver.resolve_chat", return_value=fake):
            result = asyncio.run(srv.llm_active(api_key="ignored", _role="admin"))

        self.assertEqual(set(result.keys()), {"tag", "source", "warning"},
            "Response shape must be exactly {tag, source, warning}. "
            "Adding fields here would silently grow the public surface; "
            "the admin variant /admin/llm/resolution carries the "
            "richer payload.")
        self.assertEqual(result["tag"], "gemma3:4b")
        self.assertEqual(result["source"], "preference")
        self.assertIn("preference list", result["warning"])


class ChipWiringTests(unittest.TestCase):
    """Front-end side: ensure the chip element + JS fetch wiring
    survives refactors. Pure file-content checks — fast and run-once."""

    @classmethod
    def setUpClass(cls):
        cls.index_html = (REPO / "frontend" / "index.html").read_text(
            encoding="utf-8")
        cls.chat_js = (REPO / "frontend" / "static" / "chat.js").read_text(
            encoding="utf-8")

    def test_index_html_has_model_chip(self):
        self.assertIn('id="model-chip"', self.index_html,
            "index.html must contain the #model-chip anchor populated "
            "by chat.js loadActiveModelChip().")
        self.assertIn('id="model-chip-tag"', self.index_html,
            "The chip's tag <span> id is the populated surface — "
            "removing it makes the chip render empty.")

    def test_chat_js_calls_llm_active(self):
        self.assertTrue(
            re.search(r"/llm/active\?api_key=", self.chat_js),
            "chat.js must call GET /llm/active to populate the chip.",
        )
        self.assertIn("loadActiveModelChip", self.chat_js,
            "Function loadActiveModelChip should exist; "
            "DOMContentLoaded + onLangChange call it.")


if __name__ == "__main__":
    unittest.main()
