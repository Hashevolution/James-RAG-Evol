"""v0.6 — `core/wiki_generator/_ingestion/` package size lock-test.

CLAUDE.md rule #5: "no file in `core/` exceeds 20 KB. If your change
pushes a file over, split first." This test locks the 4 sub-files
of the post-split ingestion package at < 20 KB each.

Also asserts the public import surface is preserved exactly — the v0.6
split is a no-op for callers (``core/wiki_generator/__init__.py``
imports ``WikiIngestionMixin`` from ``._ingestion``).

Run:
  python -m unittest tests.test_v06_ingestion_module_size
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "core" / "wiki_generator" / "_ingestion"

CAP_BYTES = 20 * 1024  # CLAUDE.md rule #5


class ModuleSizeCapTests(unittest.TestCase):
    def test_legacy_single_file_removed(self):
        legacy = REPO_ROOT / "core" / "wiki_generator" / "_ingestion.py"
        self.assertFalse(
            legacy.exists(),
            "legacy core/wiki_generator/_ingestion.py reappeared — "
            "both file and package can't coexist; revert and pick one",
        )

    def test_package_dir_exists(self):
        self.assertTrue(PACKAGE.is_dir())

    def test_canonical_subfiles_present(self):
        for name in ("__init__.py", "prompts.py", "safety.py",
                     "llm_extract.py", "mixin.py"):
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
    def test_canonical_public_import(self):
        from core.wiki_generator._ingestion import WikiIngestionMixin
        self.assertTrue(isinstance(WikiIngestionMixin, type))
        # The mixin still exposes the 3 canonical methods.
        for name in ("process_document_for_entities",
                     "_llm_extract_document_entities",
                     "_is_safe_extracted_entity"):
            self.assertTrue(
                hasattr(WikiIngestionMixin, name),
                f"WikiIngestionMixin missing canonical method: {name}",
            )

    def test_safety_filter_contract(self):
        from core.wiki_generator._ingestion import WikiIngestionMixin
        # Reject schema violations
        self.assertFalse(WikiIngestionMixin._is_safe_extracted_entity({}))
        self.assertFalse(
            WikiIngestionMixin._is_safe_extracted_entity(
                {"name": "X", "type": "person"}
            ),
            "single-char name should fail length floor",
        )
        self.assertFalse(
            WikiIngestionMixin._is_safe_extracted_entity(
                {"name": "Anthropic", "type": "vertical_type"}
            ),
            "unknown type should fail allowed-types check",
        )
        # Accept canonical sample
        self.assertTrue(
            WikiIngestionMixin._is_safe_extracted_entity(
                {"name": "Anthropic", "type": "org"}
            ),
        )

    def test_prompt_builder_lists_9_types(self):
        # Smoke that the prompt template still carries the 9-type
        # vocabulary (regression guard for the α-8 typed filter).
        from core.wiki_generator._ingestion.prompts import (
            build_extract_prompt,
        )
        prompt = build_extract_prompt("sample document text")
        for t in ("person", "org", "concept", "document",
                  "event", "date", "location", "quantity", "project"):
            self.assertIn(t, prompt, f"prompt missing type '{t}'")


if __name__ == "__main__":
    unittest.main()
