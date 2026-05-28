"""v0.4.1 PR-T6.A — derived_from schema + migration contract tests.

Pins the v0.4.1 §3 PR-T6.A deliverables:

  - ``validate_edge_t6_derived_from`` shape checks (list of dicts,
    ``base_fact_id: str``, ``derivation`` in
    ``VALID_DERIVATION_TYPES``)
  - **Decision 3 LOCK** — cycle rejection at write time when
    ``edges_by_id`` is supplied
  - ``apply_t6_edge_defaults`` adds ``derived_from: []`` when absent,
    idempotent
  - ``scripts/migrate_v041_lifecycle.py`` migrates every entity's
    relations + is byte-stable on second run + the --verify mode
    catches a stale state

Run:
  python -m unittest tests.test_t6a_derived_from_schema
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lifecycle.schema import (  # noqa: E402
    T6_EDGE_FIELD_DERIVED_FROM,
    apply_t6_edge_defaults,
    validate_edge_t6_derived_from,
)


# ---------------------------------------------------------------------------
# validate_edge_t6_derived_from — shape checks
# ---------------------------------------------------------------------------

class ValidateShapeTests(unittest.TestCase):

    def test_missing_field_is_valid(self):
        """v0.3-equivalent — no derived_from key means no derivation
        dependency. The validator accepts this so unmigrated edges
        loaded from older snapshots pass."""
        validate_edge_t6_derived_from({"id": "e1"})

    def test_empty_list_is_valid(self):
        """The migration default."""
        validate_edge_t6_derived_from({"id": "e1", "derived_from": []})

    def test_valid_entry_passes(self):
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "e_base_a", "derivation": "transitive"},
                {"base_fact_id": "e_base_b", "derivation": "operator"},
                {"base_fact_id": "e_base_c", "derivation": "inferred"},
            ],
        }
        validate_edge_t6_derived_from(edge)

    def test_non_list_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be a list"):
            validate_edge_t6_derived_from({
                "id": "e1", "derived_from": "not a list"
            })

    def test_entry_must_be_dict(self):
        with self.assertRaisesRegex(ValueError, "must be a dict"):
            validate_edge_t6_derived_from({
                "id": "e1",
                "derived_from": ["not a dict"],
            })

    def test_missing_base_fact_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "base_fact_id must be a"):
            validate_edge_t6_derived_from({
                "id": "e1",
                "derived_from": [{"derivation": "transitive"}],
            })

    def test_empty_base_fact_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "base_fact_id must be a"):
            validate_edge_t6_derived_from({
                "id": "e1",
                "derived_from": [
                    {"base_fact_id": "", "derivation": "transitive"},
                ],
            })

    def test_invalid_derivation_value_rejected(self):
        with self.assertRaisesRegex(ValueError, "derivation must be one of"):
            validate_edge_t6_derived_from({
                "id": "e1",
                "derived_from": [
                    {"base_fact_id": "e_base", "derivation": "made-up"},
                ],
            })


# ---------------------------------------------------------------------------
# Decision 3 LOCK — cycle rejection
# ---------------------------------------------------------------------------

class CycleRejectionTests(unittest.TestCase):
    """Decision 3 LOCK (entry memo §2): a derivation chain that
    transitively includes the edge itself is rejected at write time."""

    def test_self_reference_rejected(self):
        """The smallest possible cycle — edge derives from itself."""
        edge = {
            "id": "e_self",
            "derived_from": [
                {"base_fact_id": "e_self", "derivation": "transitive"},
            ],
        }
        edges_by_id = {"e_self": edge}
        with self.assertRaisesRegex(ValueError, "derivation cycle"):
            validate_edge_t6_derived_from(edge, edges_by_id=edges_by_id)

    def test_two_hop_cycle_rejected(self):
        """e_a → e_b → e_a is a cycle through the chain."""
        e_a = {
            "id": "e_a",
            "derived_from": [
                {"base_fact_id": "e_b", "derivation": "transitive"},
            ],
        }
        e_b = {
            "id": "e_b",
            "derived_from": [
                {"base_fact_id": "e_a", "derivation": "transitive"},
            ],
        }
        edges_by_id = {"e_a": e_a, "e_b": e_b}
        with self.assertRaisesRegex(ValueError, "derivation cycle"):
            validate_edge_t6_derived_from(e_a, edges_by_id=edges_by_id)

    def test_acyclic_chain_passes(self):
        """e_a derives from e_b; e_b derives from e_c (no self loop)."""
        e_c = {"id": "e_c"}
        e_b = {
            "id": "e_b",
            "derived_from": [
                {"base_fact_id": "e_c", "derivation": "transitive"},
            ],
        }
        e_a = {
            "id": "e_a",
            "derived_from": [
                {"base_fact_id": "e_b", "derivation": "transitive"},
            ],
        }
        edges_by_id = {"e_a": e_a, "e_b": e_b, "e_c": e_c}
        validate_edge_t6_derived_from(e_a, edges_by_id=edges_by_id)

    def test_cycle_check_skipped_without_edges_by_id(self):
        """Caller can skip cycle check by passing edges_by_id=None
        (default). Single-edge validation only checks shape."""
        edge = {
            "id": "e_self",
            "derived_from": [
                {"base_fact_id": "e_self", "derivation": "transitive"},
            ],
        }
        validate_edge_t6_derived_from(edge)  # no edges_by_id → no cycle check

    def test_cycle_check_skipped_without_edge_id(self):
        """Edges without an id can't be cycle-checked (no stable
        endpoint to recognize). Shape still validates, cycle check
        is a no-op."""
        edge = {
            "derived_from": [
                {"base_fact_id": "e_some", "derivation": "transitive"},
            ],
        }
        validate_edge_t6_derived_from(edge, edges_by_id={"e_some": edge})

    def test_dangling_base_fact_id_silently_skipped(self):
        """If a base_fact_id doesn't exist in edges_by_id, treat as
        end-of-chain (lookup returns None). No cycle = no error.
        Validates only against shape + the cycle invariant."""
        edge = {
            "id": "e_a",
            "derived_from": [
                {"base_fact_id": "e_missing", "derivation": "transitive"},
            ],
        }
        edges_by_id = {"e_a": edge}  # e_missing absent
        validate_edge_t6_derived_from(edge, edges_by_id=edges_by_id)


# ---------------------------------------------------------------------------
# apply_t6_edge_defaults
# ---------------------------------------------------------------------------

class ApplyDefaultsTests(unittest.TestCase):

    def test_adds_empty_list_when_absent(self):
        out = apply_t6_edge_defaults({"id": "e1"})
        self.assertEqual(out.get(T6_EDGE_FIELD_DERIVED_FROM), [])

    def test_preserves_existing_derived_from(self):
        existing = [{"base_fact_id": "e_base", "derivation": "transitive"}]
        out = apply_t6_edge_defaults({"id": "e1", "derived_from": existing})
        self.assertEqual(out.get(T6_EDGE_FIELD_DERIVED_FROM), existing)

    def test_idempotent(self):
        """Re-running on an already-migrated edge yields the same dict."""
        once = apply_t6_edge_defaults({"id": "e1"})
        twice = apply_t6_edge_defaults(once)
        self.assertEqual(once, twice)

    def test_does_not_mutate_input(self):
        edge = {"id": "e1"}
        before = dict(edge)
        _ = apply_t6_edge_defaults(edge)
        self.assertEqual(edge, before)

    def test_rejects_non_dict(self):
        with self.assertRaisesRegex(ValueError, "must be a dict"):
            apply_t6_edge_defaults("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# migration script — integration via tempfile wiki
# ---------------------------------------------------------------------------

# Import inside tests so the script's top-level utils.console call
# doesn't fire at module load on every CI run.

class MigrationScriptTests(unittest.TestCase):
    """Build a tiny wiki under tmpdir, call migrate_wiki + verify."""

    def _make_entity(self, root: Path, name: str, relations: list) -> Path:
        ent_dir = root / "entity" / "prod" / "concept"
        ent_dir.mkdir(parents=True, exist_ok=True)
        path = ent_dir / f"{name}.md"
        import yaml
        fm = {
            "name": name,
            "entity_type": "concept",
            "relations": relations,
        }
        text = (
            "---\n"
            + yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                        sort_keys=True)
            + "---\n"
            + f"\n## Summary\n{name}\n"
        )
        path.write_text(text, encoding="utf-8")
        return path

    def test_dry_run_counts_changes(self):
        from scripts.migrate_v041_lifecycle import migrate_wiki
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            self._make_entity(root, "EntityA", [
                {"target": "X", "type": "RELATED_TO",
                 "sources": [{"doc_id": "d", "role": "extract"}]},
            ])
            stats = migrate_wiki(root, apply=False)
            self.assertEqual(stats["files_scanned"], 1)
            self.assertEqual(stats["files_changed"], 1)
            self.assertEqual(stats["relations_changed"], 1)
            # Dry-run does NOT write the change.
            text = (root / "entity" / "prod" / "concept" / "EntityA.md") \
                .read_text(encoding="utf-8")
            self.assertNotIn("derived_from", text)

    def test_apply_writes_field_and_is_idempotent(self):
        from scripts.migrate_v041_lifecycle import migrate_wiki
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            path = self._make_entity(root, "EntityB", [
                {"target": "X", "type": "RELATED_TO",
                 "sources": [{"doc_id": "d", "role": "extract"}]},
            ])
            # First apply — writes change.
            stats1 = migrate_wiki(root, apply=True)
            self.assertEqual(stats1["files_changed"], 1)
            text1 = path.read_text(encoding="utf-8")
            self.assertIn("derived_from", text1)
            # Second apply — idempotent (no change).
            stats2 = migrate_wiki(root, apply=True)
            self.assertEqual(stats2["files_changed"], 0)
            text2 = path.read_text(encoding="utf-8")
            self.assertEqual(text1, text2)

    def test_verify_after_apply_passes(self):
        from scripts.migrate_v041_lifecycle import migrate_wiki
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            self._make_entity(root, "EntityC", [
                {"target": "X", "type": "RELATED_TO"},
            ])
            migrate_wiki(root, apply=True)
            stats = migrate_wiki(root, verify=True)
            self.assertEqual(stats["verify_violations"], 0)

    def test_verify_before_apply_flags_violations(self):
        from scripts.migrate_v041_lifecycle import migrate_wiki
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            self._make_entity(root, "EntityD", [
                {"target": "X", "type": "RELATED_TO"},
            ])
            stats = migrate_wiki(root, verify=True)
            self.assertGreater(stats["verify_violations"], 0)


if __name__ == "__main__":
    unittest.main()
