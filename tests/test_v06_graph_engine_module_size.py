"""v0.6 — `core/graph_engine/` package size lock-test.

CLAUDE.md rule #5: "no file in `core/` exceeds 20 KB. If your change
pushes a file over, split first." This test locks the 3 sub-files
of the post-split graph_engine package at < 20 KB each.

Also asserts the public + private import surface is preserved
exactly — the v0.6 split is a no-op for callers (the A5D test suite
imports `_doc_outgoing_hop_valid` directly; reasoning engine imports
`GraphEngine`).

Run:
  python -m unittest tests.test_v06_graph_engine_module_size
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "core" / "graph_engine"

CAP_BYTES = 20 * 1024  # CLAUDE.md rule #5


class ModuleSizeCapTests(unittest.TestCase):
    def test_legacy_single_file_removed(self):
        legacy = REPO_ROOT / "core" / "graph_engine.py"
        self.assertFalse(
            legacy.exists(),
            "legacy core/graph_engine.py reappeared — both file "
            "and package can't coexist; revert and pick one",
        )

    def test_package_dir_exists(self):
        self.assertTrue(PACKAGE.is_dir())

    def test_canonical_subfiles_present(self):
        for name in ("__init__.py", "constants.py", "doc_hop_rule.py",
                     "engine.py"):
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
        from core.graph_engine import (
            GraphEngine,
            CONFIDENCE_THRESHOLD,
            MAX_DEPTH,
            DFS_SCORE_THRESHOLD,
            DEPTH_DECAY,
        )
        self.assertTrue(isinstance(GraphEngine, type))
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.6)
        self.assertEqual(MAX_DEPTH, 4)
        self.assertEqual(DFS_SCORE_THRESHOLD, 0.05)
        self.assertEqual(DEPTH_DECAY, 0.7)

    def test_a5d_private_import_preserved(self):
        # tests/test_a5d_doc_source_gate.py does
        # `from core import graph_engine as ge` then
        # `ge._doc_outgoing_hop_valid(...)` — preserving this private
        # is load-bearing for the A5D regression guard.
        from core import graph_engine as ge
        self.assertTrue(callable(ge._doc_outgoing_hop_valid))

    def test_doc_hop_rule_contract(self):
        from core.graph_engine import _doc_outgoing_hop_valid
        # Non-document source → always True (rule doesn't apply)
        self.assertTrue(_doc_outgoing_hop_valid(
            {"entity_type": "concept", "name": "X"},
            {"sources": []},
        ))
        # Document source, target sources contain the doc name stem → True
        self.assertTrue(_doc_outgoing_hop_valid(
            {"entity_type": "document", "name": "PLTR_03_test"},
            {"sources": ["PLTR_03_test.pdf"]},
        ))
        # Document source, target sources do NOT contain doc name → False
        self.assertFalse(_doc_outgoing_hop_valid(
            {"entity_type": "document", "name": "PLTR_03_test"},
            {"sources": ["09_MorganStanley_other.pdf"]},
        ))

    def test_a5d_source_text_reachable(self):
        # tests/test_a5d_doc_source_gate.py line 203 does
        # `inspect.getsource(ge.GraphEngine.expand_dynamic)` — make
        # sure the method is still discoverable on the re-exported
        # class.
        import inspect
        from core.graph_engine import GraphEngine
        src = inspect.getsource(GraphEngine.expand_dynamic)
        self.assertIn("_doc_outgoing_hop_valid", src)


if __name__ == "__main__":
    unittest.main()
