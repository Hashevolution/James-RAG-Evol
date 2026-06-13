"""v0.6 — `core/lifecycle/replay_graph/` package size lock-test.

CLAUDE.md rule #5: "no file in `core/` exceeds 20 KB. If your change
pushes a file over, split first." This test locks the 4 sub-files
of the post-split replay_graph package at < 20 KB each.

Also asserts the public + private import surface is preserved exactly —
the v0.6 split is a no-op for callers (routes/admin.py + the T5 test
suite import ``reconstruct_graph_at``, ``view_from_snapshot``,
``GraphSnapshot`` directly from ``core.lifecycle.replay_graph``).

Run:
  python -m unittest tests.test_v06_replay_graph_module_size
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "core" / "lifecycle" / "replay_graph"

CAP_BYTES = 20 * 1024  # CLAUDE.md rule #5


class ModuleSizeCapTests(unittest.TestCase):
    def test_legacy_single_file_removed(self):
        # The pre-v0.6 single file MUST NOT exist alongside the
        # package — both can't coexist in Python and the legacy
        # file regrowing would break the rule #5 guarantee.
        legacy = REPO_ROOT / "core" / "lifecycle" / "replay_graph.py"
        self.assertFalse(
            legacy.exists(),
            "legacy core/lifecycle/replay_graph.py reappeared — both "
            "file and package can't coexist; revert and pick one",
        )

    def test_package_dir_exists(self):
        self.assertTrue(PACKAGE.is_dir())

    def test_canonical_subfiles_present(self):
        for name in ("__init__.py", "snapshot.py", "handlers.py",
                     "db_read.py", "primitives.py"):
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
    """Every symbol the pre-split file exposed MUST still be importable
    from `core.lifecycle.replay_graph`. Loss of any one is a contract
    break for existing callers (routes/admin.py, tests/test_t5_*)."""

    def test_canonical_public_imports(self):
        from core.lifecycle.replay_graph import (
            GraphSnapshot,
            reconstruct_graph_at,
            view_from_snapshot,
        )
        self.assertTrue(callable(reconstruct_graph_at))
        self.assertTrue(callable(view_from_snapshot))
        # GraphSnapshot is a dataclass — instances should be
        # constructible with the canonical 6 fields.
        from datetime import datetime
        snap = GraphSnapshot(
            edges={},
            supersede_chains={},
            invalidated_ids=frozenset(),
            replayed_at=datetime(2026, 1, 1),
            event_count=0,
        )
        self.assertEqual(snap.event_count, 0)
        self.assertEqual(snap.mounted_pack_ids, ())

    def test_canonical_private_imports(self):
        # Private symbols used by the in-tree test suite + dispatch.
        from core.lifecycle.replay_graph import (  # noqa: F401
            _HANDLERS,
            _empty_snapshot,
            _default_db_path,
            _read_lifecycle_events,
            _validity_contains,
            _h_supersede_edge_created,
            _h_supersede_chain_extended,
            _h_cascade_invalidate,
            _h_t1_expiration_cascade,
            _h_t2_dispatch_contradiction,
            _h_t2d_ingest_dispatch,
            _h_backfill_snapshot,
            handle_ontology_pack_mounted,
            handle_ontology_pack_unmounted,
            apply_pack_event,
        )

    def test_handlers_dict_taxonomy_invariant(self):
        # The sanity assert at module load time covers this, but make
        # it a unit-test failure too so a CI run names it clearly.
        from core.lifecycle.replay_graph import _HANDLERS
        from core.lifecycle.replay_audit import LIFECYCLE_EVENT_TYPES
        self.assertEqual(set(_HANDLERS), set(LIFECYCLE_EVENT_TYPES))


class SnapshotReconstructionContractTests(unittest.TestCase):
    """Smoke that the dispatch pipeline still folds events correctly
    after the split — uses an in-memory audit_log temp file."""

    def test_empty_db_returns_empty_snapshot(self):
        import sqlite3
        import tempfile
        from datetime import datetime
        from core.lifecycle.replay_graph import reconstruct_graph_at

        with tempfile.NamedTemporaryFile(
            suffix=".db", delete=False
        ) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE audit_log ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "timestamp TEXT, event_type TEXT, event_payload TEXT)"
            )
            conn.commit()
            conn.close()
            snap = reconstruct_graph_at(
                datetime(2026, 1, 1), audit_log_path=db_path,
            )
            self.assertEqual(snap.event_count, 0)
            self.assertEqual(snap.edges, {})
            self.assertEqual(snap.invalidated_ids, frozenset())
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
