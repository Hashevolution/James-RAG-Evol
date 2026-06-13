"""v0.6 — `core/gemma_client/` package size lock-test.

CLAUDE.md rule #5: "no file in `core/` exceeds 20 KB. If your change
pushes a file over, split first." This test locks the 5 sub-files
of the post-split gemma_client package at < 20 KB each.

Also asserts the public + private import surface is preserved
exactly — the v0.6 split is a no-op for callers.

Run:
  python -m unittest tests.test_v06_gemma_client_module_size
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "core" / "gemma_client"

CAP_BYTES = 20 * 1024


class ModuleSizeCapTests(unittest.TestCase):
    def test_legacy_single_file_removed(self):
        legacy = REPO_ROOT / "core" / "gemma_client.py"
        self.assertFalse(
            legacy.exists(),
            "legacy core/gemma_client.py reappeared — both file "
            "and package can't coexist; revert and pick one",
        )

    def test_package_dir_exists(self):
        self.assertTrue(PACKAGE.is_dir())

    def test_canonical_subfiles_present(self):
        for name in ("__init__.py", "config.py", "errors.py",
                     "response_parser.py", "client.py"):
            self.assertTrue(
                (PACKAGE / name).exists(),
                f"missing canonical sub-file: {name}",
            )

    def test_each_subfile_under_20kb(self):
        for path in PACKAGE.glob("*.py"):
            size = path.stat().st_size
            self.assertLess(
                size, CAP_BYTES,
                f"{path.name} is {size/1024:.1f} KB — exceeds CLAUDE.md "
                f"rule #5 20 KB cap. Split it before merging.",
            )


class PublicImportSurfaceTests(unittest.TestCase):
    def test_canonical_public_imports(self):
        from core.gemma_client import (
            GemmaClient,
            ERROR_PREFIXES,
            is_cacheable_response,
            log_system_event,
        )
        self.assertTrue(callable(GemmaClient))
        self.assertIsInstance(ERROR_PREFIXES, tuple)
        self.assertTrue(callable(is_cacheable_response))
        self.assertTrue(callable(log_system_event))

    def test_canonical_private_imports(self):
        from core.gemma_client import (  # noqa: F401
            _DEFAULT_MAX_PROMPT_LEN,
            _resolve_max_prompt_len,
            recover_think_block,
            recover_vision_response,
        )

    def test_error_prefixes_content(self):
        from core.gemma_client import ERROR_PREFIXES
        # Lock the canonical 4 error prefixes — callers
        # (routes/evolution.py, scripts/recover_*) match against
        # these strings to detect Gemma error responses.
        expected = (
            "[Gemma 응답 없음]",
            "[Gemma 오류]",
            "[Gemma Vision 오류]",
            "[Gemma Vision 응답 없음]",
        )
        self.assertEqual(ERROR_PREFIXES, expected)

    def test_is_cacheable_response_contract(self):
        from core.gemma_client import is_cacheable_response
        self.assertTrue(is_cacheable_response("normal answer"))
        self.assertFalse(is_cacheable_response(""))
        self.assertFalse(is_cacheable_response(None))
        self.assertFalse(is_cacheable_response("[Gemma 응답 없음]"))
        self.assertFalse(is_cacheable_response("[Gemma 오류] timeout"))
        self.assertFalse(is_cacheable_response("ab"))  # < 5 chars

    def test_default_max_prompt_len_unchanged(self):
        from core.gemma_client import _DEFAULT_MAX_PROMPT_LEN
        self.assertEqual(_DEFAULT_MAX_PROMPT_LEN, 4000)


class ResponseParserContractTests(unittest.TestCase):
    """The 3-stage <think> recovery has byte-identical behaviour."""

    def test_stage1_strip_think_block(self):
        from core.gemma_client import recover_think_block
        self.assertEqual(
            recover_think_block("<think>hidden</think>visible answer"),
            "visible answer",
        )

    def test_stage1_with_done_thinking_marker(self):
        from core.gemma_client import recover_think_block
        # The post-processing tail skips past "...done thinking." /
        # "done thinking." markers — then .strip() removes leading
        # whitespace. So "visible answer...done thinking. answer body"
        # collapses to "answer body" (everything before the marker
        # is dropped, leading space stripped).
        result = recover_think_block(
            "<think>hidden</think>visible answer...done thinking. answer body"
        )
        self.assertEqual(result, "answer body")

    def test_empty_output_returns_canonical_fallback(self):
        from core.gemma_client import recover_think_block
        self.assertEqual(
            recover_think_block(""), "[Gemma 응답 없음]",
        )

    def test_vision_recovery_strips_think(self):
        from core.gemma_client import recover_vision_response
        self.assertEqual(
            recover_vision_response("<think>x</think>image description"),
            "image description",
        )

    def test_vision_empty_returns_canonical_fallback(self):
        from core.gemma_client import recover_vision_response
        self.assertEqual(
            recover_vision_response(""), "[Gemma Vision 응답 없음]",
        )


class GemmaClientInstanceContractTests(unittest.TestCase):
    def test_construction_with_defaults(self):
        from core.gemma_client import GemmaClient
        c = GemmaClient()
        self.assertEqual(c.cache_max_size, 100)
        self.assertEqual(c.cache_ttl, 600)
        self.assertEqual(c._last_done_reason, "")
        # All counters start at zero.
        self.assertEqual(c._cache_hits, 0)
        self.assertEqual(c._cache_misses, 0)
        self.assertEqual(c._cache_errors, 0)
        self.assertEqual(c._total_calls, 0)

    def test_get_cache_stats_shape(self):
        from core.gemma_client import GemmaClient
        c = GemmaClient()
        stats = c.get_cache_stats()
        # Lock the 8 canonical fields callers (admin dashboard,
        # diagnostic scripts) rely on.
        for key in ("hits", "misses", "errors", "total",
                    "hit_rate", "hit_rate_%", "cache_size", "ttl"):
            self.assertIn(key, stats, f"missing stat field: {key}")


if __name__ == "__main__":
    unittest.main()
