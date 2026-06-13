"""v0.6 — `core/wiki_generator/_frontmatter/` package size lock-test.

CLAUDE.md rule #5: "no file in `core/` exceeds 20 KB. If your change
pushes a file over, split first." This test locks the 4 sub-files
of the post-split frontmatter package at < 20 KB each.

Also asserts the public import surface is preserved exactly — the v0.6
split is a no-op for callers (``core/wiki_generator/__init__.py``
imports ``WikiFrontmatterMixin`` from ``._frontmatter``).

Run:
  python -m unittest tests.test_v06_frontmatter_module_size
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "core" / "wiki_generator" / "_frontmatter"

CAP_BYTES = 20 * 1024  # CLAUDE.md rule #5


class ModuleSizeCapTests(unittest.TestCase):
    def test_legacy_single_file_removed(self):
        legacy = REPO_ROOT / "core" / "wiki_generator" / "_frontmatter.py"
        self.assertFalse(
            legacy.exists(),
            "legacy core/wiki_generator/_frontmatter.py reappeared — "
            "both file and package can't coexist; revert and pick one",
        )

    def test_package_dir_exists(self):
        self.assertTrue(PACKAGE.is_dir())

    def test_canonical_subfiles_present(self):
        for name in ("__init__.py", "init_state.py", "id_gen.py",
                     "read.py", "create.py"):
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
        from core.wiki_generator._frontmatter import WikiFrontmatterMixin
        self.assertTrue(isinstance(WikiFrontmatterMixin, type))

    def test_mixin_carries_all_canonical_methods(self):
        from core.wiki_generator._frontmatter import WikiFrontmatterMixin
        # Methods the merge / ingestion / index_ops mixins call via
        # ``self`` — losing any of these breaks the package.
        for name in (
            "__init__",
            "_create_index_template",
            "_build_entity_id_index",
            "refresh_entity_map",
            "_register_entity_id",
            "_build_overlap_snapshot",
            "_generate_entity_id",
            "_normalize_name",
            "_find_existing_entity_id",
            "_read_frontmatter",
            "create_entity_file",
            "_default_sensitivity",
            "find_duplicate_entities",
        ):
            self.assertTrue(
                hasattr(WikiFrontmatterMixin, name),
                f"WikiFrontmatterMixin missing canonical method: {name}",
            )

    def test_top_level_wiki_generator_still_constructs(self):
        # End-to-end smoke that the MRO composition + WikiGenerator
        # façade still works post-split.
        from core.wiki_generator import WikiGenerator
        # Construction touches every sub-mixin's __init__ path.
        wg = WikiGenerator(source_type="test")
        self.assertEqual(wg.source_type, "test")
        self.assertTrue(hasattr(wg, "entity_id_index"))
        self.assertTrue(hasattr(wg, "wiki_base_path"))

    def test_id_gen_contract(self):
        from core.wiki_generator._frontmatter import WikiFrontmatterMixin
        # _generate_entity_id is deterministic + carries the
        # e_<type>_<8hex> shape graph_rag_engine regex expects.
        import re
        wf = WikiFrontmatterMixin.__new__(WikiFrontmatterMixin)
        eid = wf._generate_entity_id("Anthropic", "org")
        self.assertTrue(re.fullmatch(r"e_org_[0-9a-f]{8}", eid), eid)
        # Same input → same id.
        self.assertEqual(eid, wf._generate_entity_id("Anthropic", "org"))


if __name__ == "__main__":
    unittest.main()
