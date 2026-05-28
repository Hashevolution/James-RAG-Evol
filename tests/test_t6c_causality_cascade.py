"""v0.4.1 PR-T6.C + T6.C.b — derivation-aware invalidation cascade tests.

Pins the foundational-vs-corroborative semantics (entry memo §2
Decision 4, refined 2026-05-28 in T6.C.b):

  - ``transitive`` / ``inferred`` = hard deps (structural chain links)
    → ANY-trigger: loss of any one breaks the derivation.
  - ``operator`` = soft deps (corroborative evidence)
    → contributes only when no hard dep supports the edge; when
       hard deps are present and alive, operator loss only WEAKENS,
       doesn't invalidate.

Combined: invalidate iff (any hard dep base empty) OR
                          (no hard deps AND all operator bases empty)

T6.C.b corrects the original T6.C edge case where one transitive
+ one operator with operator gone invalidated incorrectly.

Run:
  python -m unittest tests.test_t6c_causality_cascade
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lifecycle.causality import (  # noqa: E402
    invalidate_derived_facts,
    should_invalidate_edge,
)


# ---------------------------------------------------------------------------
# should_invalidate_edge — pure function, no I/O
# ---------------------------------------------------------------------------

class ShouldInvalidateEdgeTests(unittest.TestCase):
    """The C-semantics decision evaluator."""

    def test_transitive_any_trigger(self):
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "transitive"},
                {"base_fact_id": "b2", "derivation": "transitive"},
            ],
        }
        # b1 empty → invalidate (transitive ANY-trigger)
        self.assertTrue(should_invalidate_edge(edge, {"b1"}))

    def test_inferred_any_trigger(self):
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "inferred"},
            ],
        }
        self.assertTrue(should_invalidate_edge(edge, {"b1"}))

    def test_operator_single_entry_all_trigger(self):
        """One operator entry only — its base empty means 'all
        operator entries empty' (trivially)."""
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "operator"},
            ],
        }
        self.assertTrue(should_invalidate_edge(edge, {"b1"}))

    def test_operator_multi_entry_partial_loss_preserves(self):
        """Two operator entries, one empty, other alive → keep."""
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "operator"},
                {"base_fact_id": "b2", "derivation": "operator"},
            ],
        }
        self.assertFalse(should_invalidate_edge(edge, {"b1"}))

    def test_operator_multi_entry_all_empty_invalidates(self):
        """Both operator bases empty → invalidate."""
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "operator"},
                {"base_fact_id": "b2", "derivation": "operator"},
            ],
        }
        self.assertTrue(should_invalidate_edge(edge, {"b1", "b2"}))

    def test_mixed_transitive_overrides_operator_partial(self):
        """Mixed: 1 transitive + 2 operator. transitive empty →
        invalidate (transitive ANY-trigger fires regardless of
        operator-state)."""
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "transitive"},
                {"base_fact_id": "b2", "derivation": "operator"},
                {"base_fact_id": "b3", "derivation": "operator"},
            ],
        }
        self.assertTrue(should_invalidate_edge(edge, {"b1"}))

    def test_mixed_operator_partial_with_transitive_alive(self):
        """Mixed: transitive alive, one operator empty → keep
        (transitive intact, operator partial)."""
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "transitive"},
                {"base_fact_id": "b2", "derivation": "operator"},
                {"base_fact_id": "b3", "derivation": "operator"},
            ],
        }
        self.assertFalse(should_invalidate_edge(edge, {"b2"}))

    def test_empty_derived_from_no_invalidation(self):
        edge = {"id": "e_derived", "derived_from": []}
        self.assertFalse(should_invalidate_edge(edge, {"b1"}))

    def test_missing_derived_from_no_invalidation(self):
        edge = {"id": "e_derived"}
        self.assertFalse(should_invalidate_edge(edge, {"b1"}))

    def test_unknown_derivation_type_ignored(self):
        """Schema validator would reject unknown derivation values,
        but defensively the cascade evaluator just skips them rather
        than firing."""
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "mystery"},
            ],
        }
        self.assertFalse(should_invalidate_edge(edge, {"b1"}))

    def test_empty_bases_set_no_invalidation(self):
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "transitive"},
            ],
        }
        self.assertFalse(should_invalidate_edge(edge, set()))

    def test_t6cb_corroborator_loss_with_foundation_preserves(self):
        """T6.C.b refinement: ONE transitive (foundation) + ONE operator
        (corroborator). The operator base goes empty; foundation alive.

        Original T6.C: invalidate (operator-all-empty trivially fires
        with one operator entry).
        T6.C.b: preserve (foundation intact; lost corroborator only
        weakens the derivation, doesn't break it).

        Mirrors the "캘리포니아는 미국이다" + "어른 X가 봤다" example:
        losing the corroborator (X's testimony) while the chain link
        survives = derivation weakens but holds.
        """
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b_foundation",
                 "derivation": "transitive"},
                {"base_fact_id": "b_corroborator",
                 "derivation": "operator"},
            ],
        }
        # Only the corroborator empty → preserve.
        self.assertFalse(
            should_invalidate_edge(edge, {"b_corroborator"})
        )

    def test_t6cb_all_corroborators_lost_with_foundation_preserves(self):
        """T6.C.b refinement: 1 transitive + 3 operator. ALL operator
        bases go empty; foundation alive → preserve. The foundation
        still supports the derivation alone."""
        edge = {
            "id": "e_derived",
            "derived_from": [
                {"base_fact_id": "b_foundation",
                 "derivation": "transitive"},
                {"base_fact_id": "b_corr1", "derivation": "operator"},
                {"base_fact_id": "b_corr2", "derivation": "operator"},
                {"base_fact_id": "b_corr3", "derivation": "operator"},
            ],
        }
        # All operators empty, foundation alive → preserve.
        self.assertFalse(
            should_invalidate_edge(
                edge, {"b_corr1", "b_corr2", "b_corr3"},
            ),
        )
        # Now the foundation is also lost → invalidate (Rule 1).
        self.assertTrue(
            should_invalidate_edge(
                edge,
                {"b_foundation", "b_corr1", "b_corr2", "b_corr3"},
            ),
        )

    def test_t6cb_operator_only_edge_still_collapses_when_all_gone(self):
        """Rule 2 boundary: operator-only edge (no hard deps) with
        ALL operator bases empty → invalidate. The "lone corroborator
        collapse" case — no foundation to fall back on."""
        edge = {
            "id": "e_corr_only",
            "derived_from": [
                {"base_fact_id": "b1", "derivation": "operator"},
                {"base_fact_id": "b2", "derivation": "operator"},
            ],
        }
        self.assertTrue(should_invalidate_edge(edge, {"b1", "b2"}))
        # Partial loss still preserves.
        self.assertFalse(should_invalidate_edge(edge, {"b1"}))


# ---------------------------------------------------------------------------
# invalidate_derived_facts — file-walking integration
# ---------------------------------------------------------------------------


def _write_entity(root: Path, name: str, relations: list) -> Path:
    """Write a minimal entity .md file with the given relations."""
    ent_dir = root / "entity" / "prod" / "concept"
    ent_dir.mkdir(parents=True, exist_ok=True)
    path = ent_dir / f"{name}.md"
    fm = {
        "entity_id":   f"e_concept_{name.lower()}",
        "entity_type": "concept",
        "name":        name,
        "relations":   relations,
    }
    text = (
        "---\n"
        + yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                    sort_keys=True)
        + "---\n\n"
        + f"## Summary\n{name}\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


def _load_relations(path: Path) -> list:
    text = path.read_text(encoding="utf-8")
    fm_text = text.split("---", 2)[1]
    return yaml.safe_load(fm_text).get("relations", [])


class InvalidateDerivedFactsTests(unittest.TestCase):

    def test_invalidates_directly_derived_edge(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            _write_entity(root, "A", [
                {
                    "id":        "e_a_derived",
                    "target":    "X",
                    "type":      "BASED_IN",
                    "sources":   [{"doc_id": "d1", "role": "extract",
                                   "weight": 0.8}],
                    "derived_from": [
                        {"base_fact_id": "e_base_x",
                         "derivation": "transitive"},
                    ],
                },
            ])
            entity_root = root / "entity"
            invalidated = invalidate_derived_facts(
                "e_base_x", entity_root,
            )
            self.assertEqual(invalidated, ["e_a_derived"])
            # Edge mutated on disk.
            rels = _load_relations(
                root / "entity" / "prod" / "concept" / "A.md"
            )
            self.assertEqual(rels[0]["mutation_type"], "invalidated")
            self.assertFalse(rels[0]["status"]["active"])
            # Sources preserved (T7 replay friendly).
            self.assertEqual(len(rels[0]["sources"]), 1)

    def test_preserves_when_no_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            _write_entity(root, "B", [
                {
                    "id":        "e_b_derived",
                    "target":    "Y",
                    "type":      "RELATED_TO",
                    "derived_from": [
                        {"base_fact_id": "e_other",
                         "derivation": "transitive"},
                    ],
                },
            ])
            entity_root = root / "entity"
            invalidated = invalidate_derived_facts(
                "e_base_x", entity_root,  # different from e_other
            )
            self.assertEqual(invalidated, [])

    def test_additional_empty_bases_enables_all_trigger(self):
        """Operator multi-entry: invalidate only when caller passes
        ``additional_empty_bases`` covering all entries."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            _write_entity(root, "C", [
                {
                    "id":     "e_c_derived",
                    "target": "Z",
                    "type":   "RELATED_TO",
                    "derived_from": [
                        {"base_fact_id": "e_op1",
                         "derivation": "operator"},
                        {"base_fact_id": "e_op2",
                         "derivation": "operator"},
                    ],
                },
            ])
            entity_root = root / "entity"

            # Call with only e_op1 → operator partial loss → preserved
            partial = invalidate_derived_facts("e_op1", entity_root)
            self.assertEqual(partial, [])

            # Call with both via additional_empty_bases → all-trigger fires
            full = invalidate_derived_facts(
                "e_op1", entity_root,
                additional_empty_bases={"e_op2"},
            )
            self.assertEqual(full, ["e_c_derived"])

    def test_audit_row_per_invalidation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            _write_entity(root, "D", [
                {
                    "id":     "e_d_derived",
                    "target": "X",
                    "type":   "RELATED_TO",
                    "derived_from": [
                        {"base_fact_id": "e_base_x",
                         "derivation": "inferred"},
                    ],
                },
            ])
            entity_root = root / "entity"
            emit = MagicMock()
            invalidate_derived_facts(
                "e_base_x", entity_root, audit_emit=emit,
            )
            emit.assert_called_once()
            payload = emit.call_args[0][0]
            self.assertEqual(payload["mutation_type"],
                             "invalidated_by_cascade")
            self.assertEqual(payload["base_fact_id"], "e_base_x")
            self.assertEqual(payload["derived_edge_id"], "e_d_derived")
            self.assertIn("entity_path", payload)

    def test_walks_multiple_entities(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            _write_entity(root, "EA", [{
                "id": "e_a1", "target": "X", "type": "RELATED_TO",
                "derived_from": [{"base_fact_id": "e_base",
                                  "derivation": "transitive"}],
            }])
            _write_entity(root, "EB", [{
                "id": "e_b1", "target": "Y", "type": "RELATED_TO",
                "derived_from": [{"base_fact_id": "e_base",
                                  "derivation": "transitive"}],
            }])
            _write_entity(root, "EC", [{
                "id": "e_c1", "target": "Z", "type": "RELATED_TO",
                # No matching base → preserved
                "derived_from": [{"base_fact_id": "e_other",
                                  "derivation": "transitive"}],
            }])
            entity_root = root / "entity"
            invalidated = invalidate_derived_facts("e_base", entity_root)
            self.assertEqual(sorted(invalidated), ["e_a1", "e_b1"])

    def test_rejects_empty_base_fact_id(self):
        with self.assertRaisesRegex(ValueError, "must be non-empty"):
            invalidate_derived_facts("", Path("/fake"))

    def test_no_entity_dir_returns_empty(self):
        """If entity_root doesn't exist, no walk → no invalidations,
        no crash."""
        result = invalidate_derived_facts(
            "e_base", Path("/this/path/definitely/does/not/exist"),
        )
        self.assertEqual(result, [])

    def test_status_dict_synthesized_when_missing(self):
        """Edge without an existing status dict → cascade synthesizes
        one with active=False."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            _write_entity(root, "EE", [{
                "id": "e_e1", "target": "X", "type": "RELATED_TO",
                "derived_from": [{"base_fact_id": "e_base",
                                  "derivation": "transitive"}],
                # no status field
            }])
            entity_root = root / "entity"
            invalidated = invalidate_derived_facts("e_base", entity_root)
            self.assertEqual(invalidated, ["e_e1"])
            rels = _load_relations(
                root / "entity" / "prod" / "concept" / "EE.md"
            )
            self.assertIn("status", rels[0])
            self.assertFalse(rels[0]["status"]["active"])


if __name__ == "__main__":
    unittest.main()
