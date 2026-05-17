"""[#A2 phase 2] Server-side selected_model wiring — 2026-05-09.

Phase 1 (PR #113) added the secondary model picker UI; selection
persisted to localStorage but actual /query/ calls still used each
mode's default tag. Phase 2 plumbs the user's choice through:

    chat.js → QueryRequest.selected_model
            → /query/ handler → rag_engine.query(selected_model=...)
            → core.model_catalog.resolve_model(mode, requested) — validation
            → mode handler → call_gemma(model=picked_model)

Tests are pure source-text + import-shape assertions so they run without
the Ollama server.

Run:
    python -m unittest tests.test_a2_phase2_selected_model
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class ModelCatalogModuleTests(unittest.TestCase):
    """The new core.model_catalog module — single source of truth."""

    def test_module_importable(self):
        import core.model_catalog as mc
        self.assertTrue(callable(mc.model_catalog))
        self.assertTrue(callable(mc.is_valid_for_mode))
        self.assertTrue(callable(mc.resolve_model))

    def test_catalog_covers_required_modes(self):
        from core.model_catalog import model_catalog
        cat = model_catalog()
        for mode in ("chat", "retrieval", "coding", "wiki_edit", "self_evolve"):
            self.assertIn(mode, cat,
                          f"mode {mode} missing from catalog")
            self.assertGreaterEqual(len(cat[mode]), 2,
                f"mode {mode} should expose ≥2 candidates")

    def test_is_valid_for_mode_accepts_listed_tag(self):
        from core.model_catalog import model_catalog, is_valid_for_mode
        cat = model_catalog()
        for mode, cands in cat.items():
            tag, _ = cands[0]
            self.assertTrue(is_valid_for_mode(mode, tag),
                            f"first candidate '{tag}' should be valid for {mode}")

    def test_is_valid_rejects_unknown_tag(self):
        from core.model_catalog import is_valid_for_mode
        self.assertFalse(is_valid_for_mode("chat", "rm-rf-slash"))
        self.assertFalse(is_valid_for_mode("chat", ""))
        self.assertFalse(is_valid_for_mode("", "gemma3:12b"))
        self.assertFalse(is_valid_for_mode("nonexistent_mode", "gemma3:12b"))

    def test_resolve_returns_tag_when_valid(self):
        from core.model_catalog import model_catalog, resolve_model
        tag, _ = model_catalog()["chat"][0]
        self.assertEqual(resolve_model("chat", tag), tag)

    def test_resolve_returns_none_when_invalid(self):
        from core.model_catalog import resolve_model
        # Untrusted/unknown tags must NOT be echoed — silent fallback.
        self.assertIsNone(resolve_model("chat", "; rm -rf /"))
        self.assertIsNone(resolve_model("chat", "evil-model:latest"))
        self.assertIsNone(resolve_model("chat", ""))


class ServerSchemaTests(unittest.TestCase):
    """QueryRequest must accept the new field; /query/ must forward it."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.srv = srv
        cls.src = inspect.getsource(srv)

    def test_query_request_has_selected_model_field(self):
        m = re.search(
            r"class QueryRequest\(BaseModel\):(.+?)(?=\nclass |\n@app\.|\nasync def )",
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m, "QueryRequest class block not found")
        body = m.group(1)
        self.assertIn("selected_model", body,
                      "QueryRequest must declare selected_model field")
        self.assertTrue(re.search(r'selected_model\s*:\s*str\s*=\s*""', body),
                        "selected_model must default to '' (back-compat)")

    def test_query_handler_forwards_selected_model(self):
        idx = self.src.index('@app.post("/query/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        self.assertIn("selected_model", body,
                      "/query/ must forward data.selected_model to rag_engine.query")
        self.assertIn("data.selected_model", body)

    def test_query_request_default_model_is_empty_string(self):
        from server_llmwiki import QueryRequest
        m = QueryRequest(api_key="x", question="hello")
        self.assertEqual(m.selected_model, "")

    def test_legacy_model_catalog_function_still_callable(self):
        # PR #113 test (test_model_catalog_per_mode) checks for
        # `def _model_catalog` in source. Our refactor delegates to
        # core.model_catalog but must keep the function name.
        self.assertIn("def _model_catalog", self.src)
        self.assertTrue(callable(getattr(self.srv, "_model_catalog", None)))
        # And it must still return the same shape.
        cat = self.srv._model_catalog()
        self.assertIn("chat", cat)
        self.assertIn("coding", cat)


class EngineWiringTests(unittest.TestCase):
    """engine.query must accept selected_model and validate it."""

    @classmethod
    def setUpClass(cls):
        import core.reasoning.engine as eng
        cls.eng = eng
        cls.src = inspect.getsource(eng)

    def test_query_signature_has_selected_model(self):
        m = re.search(
            r"def\s+query\s*\([\s\S]*?selected_model\s*:\s*str\s*=\s*['\"]{2}",
            self.src,
        )
        self.assertIsNotNone(m,
            "engine.query must declare selected_model: str = '' kwarg")

    def test_engine_validates_via_catalog_resolve(self):
        # The trust boundary — anything not in catalog must be rejected.
        self.assertIn("from core.model_catalog import resolve_model", self.src,
                      "engine must import resolve_model for validation")
        self.assertIn("resolve_model(mode,", self.src,
                      "engine must call resolve_model(mode, ...) AFTER mode is determined")

    def test_engine_passes_picked_to_handlers(self):
        # All non-meta handlers + retrieval pipeline must receive picked_model.
        self.assertIn("selected_model=picked_model", self.src,
                      "validated picked_model must propagate to handlers")
        # Count: chat, wiki_edit, self_evolve, coding, retrieval pipeline = 5.
        self.assertGreaterEqual(self.src.count("selected_model=picked_model"), 5,
            "all of (chat, wiki_edit, self_evolve, coding, retrieval) must "
            "receive selected_model=picked_model")

    def test_generate_answer_accepts_selected_model(self):
        # The internal RAG-answer helper must thread it to call_gemma.
        m = re.search(r"def\s+_generate_answer\s*\(.*?\)", self.src, re.DOTALL)
        self.assertIsNotNone(m)
        sig = m.group(0)
        self.assertIn("selected_model", sig,
                      "_generate_answer must accept selected_model kwarg")


class ModesHandlerWiringTests(unittest.TestCase):
    """Mode handlers must accept selected_model and pass to call_gemma."""

    @classmethod
    def setUpClass(cls):
        import core.reasoning.modes as md
        cls.md = md

    def _handler_body(self, name: str) -> str:
        # ``inspect.getsource`` on the function itself follows
        # ``__code__.co_filename`` — works identically whether the
        # handler lives in the original monolithic modes.py or in
        # one of the v0.3.x split submodules (modes/chat.py etc.).
        # We trim trailing whitespace just in case the file ends
        # right after the function for cleaner regex anchoring.
        return inspect.getsource(getattr(self.md, name)).rstrip()

    def test_chat_handler_accepts_and_uses_selected_model(self):
        body = self._handler_body("handle_chat")
        self.assertRegex(body, r"selected_model\s*:\s*str\s*=\s*[\"']{2}",
                         "handle_chat must declare selected_model kwarg")
        self.assertIn("model=selected_model or None", body,
                      "handle_chat's call_gemma must pass model=selected_model or None")

    def test_wiki_edit_handler_accepts_and_uses_selected_model(self):
        body = self._handler_body("handle_wiki_edit")
        self.assertIn("selected_model", body)
        self.assertIn("model=selected_model or None", body)

    def test_self_evolve_handler_accepts_and_uses_selected_model(self):
        body = self._handler_body("handle_self_evolve")
        self.assertIn("selected_model", body)
        # Multiple call_gemma sites — at least one must use the user pick.
        self.assertGreaterEqual(body.count("model=selected_model or None"), 2,
            "self_evolve has ≥3 call_gemma sites; at least 2 should respect the pick")

    def test_coding_handler_bypasses_router_when_picked(self):
        body = self._handler_body("handle_coding")
        self.assertRegex(body, r"selected_model\s*:\s*str\s*=\s*[\"']{2}")
        # Decision: when user explicitly picks, bypass smart router and
        # call the chosen model directly.
        self.assertIn("if selected_model:", body,
                      "handle_coding must branch on selected_model — explicit pick "
                      "bypasses smart router")
        self.assertIn("model=selected_model", body)


class PipelineWiringTests(unittest.TestCase):
    """run_retrieval_pipeline must thread selected_model through."""

    @classmethod
    def setUpClass(cls):
        from tests._pipeline_src import pipeline_source
        cls.src = pipeline_source()

    def test_pipeline_signature_has_selected_model(self):
        m = re.search(
            r"def\s+run_retrieval_pipeline\([\s\S]*?selected_model\s*:\s*str\s*=\s*['\"]{2}",
            self.src,
        )
        self.assertIsNotNone(m,
            "run_retrieval_pipeline must accept selected_model kwarg")

    def test_pipeline_threads_to_generate_answer(self):
        # _generate_answer must receive it (the main RAG path).
        self.assertIn("selected_model=selected_model", self.src,
                      "_generate_answer call must receive selected_model=selected_model")
        # At least 2 call sites (with-context + retry/fallback paths).
        self.assertGreaterEqual(self.src.count("selected_model=selected_model"), 2)

    def test_pipeline_threads_to_user_facing_call_gemma(self):
        # The user-facing fallback + retry call_gemma sites must respect pick.
        # At least 2 sites in pipeline.py use `model=selected_model or None`.
        self.assertGreaterEqual(
            self.src.count("model=selected_model or None"), 2,
            "user-facing call_gemma sites in pipeline.py must use the pick")


class FrontendChatJsTests(unittest.TestCase):
    """chat.js must include selected_model in the /query/ POST body."""

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_query_body_carries_selected_model(self):
        # Body of fetch('/query/'). Find the POST block and assert.
        idx = self.js.index("fetch(`${API}/query/`")
        body_block = self.js[idx:idx + 2000]
        self.assertIn("selected_model", body_block,
                      "POST /query/ body must carry selected_model")
        self.assertIn("selectedModel", body_block,
                      "value must come from existing selectedModel variable")


class SecurityTrustBoundaryTests(unittest.TestCase):
    """End-to-end: the engine must NOT echo arbitrary tags to call_gemma.
    This is a contract test — the catalog acts as the allowlist."""

    def test_resolve_drops_arbitrary_tag(self):
        from core.model_catalog import resolve_model
        # A malicious client could try this. The catalog rejection is
        # the only thing standing between an attacker-controlled string
        # and Ollama's HTTP endpoint.
        bad_inputs = [
            "; rm -rf /",
            "../../etc/passwd",
            "model:latest; curl evil.com",
            "x" * 1000,
            "\nmodel: evil",
        ]
        for bad in bad_inputs:
            self.assertIsNone(resolve_model("chat", bad),
                              f"malicious input should be rejected: {bad!r}")
            self.assertIsNone(resolve_model("coding", bad),
                              f"malicious input should be rejected: {bad!r}")


if __name__ == "__main__":
    unittest.main()
