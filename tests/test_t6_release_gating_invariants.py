"""v0.4.1 PR-T6.D — release-gating invariants for the T6 Causality Chain.

Four invariants the v0.4.1 entry memo §3 marked as "must hold before
v0.4.1 release":

  1. test_derived_invalidated_when_base_removed — cascade removes a
     doc, the base relation that used to depend on that doc loses its
     sources, the derived edge automatically transitions to
     status.active=False + mutation_type=invalidated. End-to-end via
     the real cascade_remove_doc_from_sources call site.

  2. test_partial_base_loss_preserves_derived — T6.C.b refinement:
     a derived edge with foundation alive + corroborator gone stays
     active. Confidence-decay-on-corroborator-loss is T3 territory;
     T6 binary stays binary.

  3. test_causality_chain_acyclic_rejected_at_write — Decision 3
     LOCK: a relation whose derived_from transitively points to
     itself fails validate_edge_t6_derived_from at write time.

  4. test_cascade_invalidate_emits_audit_row — every derived
     invalidation surfaces in audit_log with mutation_type=
     "invalidated_by_cascade" + chain pointers so the T7 replay
     primitive can reconstruct the history.

Unlike the unit tests in tests/test_t6c_causality_cascade.py, these
invariants run end-to-end against a real wiki fixture built on
tmpdir + actual cascade_remove_doc_from_sources(). A regression in
the integration surfaces here on every PR thereafter.

Run:
  python -m pytest tests/test_t6_release_gating_invariants.py -v
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

from core.cascade._delete import cascade_remove_doc_from_sources  # noqa: E402
from core.lifecycle.schema import (  # noqa: E402
    validate_edge_t6_derived_from,
)


# ---------------------------------------------------------------------------
# Fixture builders — real entity files on tmpdir
# ---------------------------------------------------------------------------

def _write_entity(root: Path, ent_type: str, name: str,
                  relations: list, *, etype: str = "concept") -> Path:
    """Write a v0.4-shaped entity file."""
    ent_dir = root / "entity" / "prod" / etype
    ent_dir.mkdir(parents=True, exist_ok=True)
    path = ent_dir / f"{name}.md"
    fm = {
        "entity_id":   f"e_{etype}_{name.lower()}",
        "entity_type": etype,
        "name":        name,
        "relations":   relations,
        "sources":     ["seed.md"],
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


# ---------------------------------------------------------------------------
# Invariant 1 — derived invalidated when base removed
# ---------------------------------------------------------------------------

class DerivedInvalidatedWhenBaseRemovedTests(unittest.TestCase):
    """Cascade-remove a doc → base relation drops (sources empty)
    → derived edge auto-invalidates via the T6.D propagation."""

    def test_derived_invalidated_when_base_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            # Base entity carrying a relation whose only source is
            # the doc we're about to remove.
            _write_entity(root, "concept", "Base", [{
                "id":      "e_base_rel",
                "target":  "BaseTarget",
                "type":    "RELATED_TO",
                "sources": [{
                    "doc_id": "doc_A", "role": "extract", "weight": 0.9,
                }],
            }])
            # Derived entity whose relation references e_base_rel as a
            # transitive (hard) base.
            _write_entity(root, "concept", "Derived", [{
                "id":           "e_derived_rel",
                "target":       "DerivedTarget",
                "type":         "RELATED_TO",
                "sources": [{
                    "doc_id": "doc_unrelated", "role": "extract",
                    "weight": 0.8,
                }],
                "derived_from": [
                    {"base_fact_id": "e_base_rel",
                     "derivation": "transitive"},
                ],
            }])
            entity_root = root / "entity"

            counts = cascade_remove_doc_from_sources("doc_A", entity_root)

            # Base relation dropped + derived invalidated.
            self.assertEqual(counts["relations_dropped"], 1)
            self.assertEqual(counts["derived_invalidated"], 1)

            derived_rels = _load_relations(
                root / "entity" / "prod" / "concept" / "Derived.md"
            )
            self.assertEqual(len(derived_rels), 1)
            self.assertEqual(
                derived_rels[0].get("mutation_type"), "invalidated"
            )
            self.assertFalse(
                derived_rels[0].get("status", {}).get("active", True)
            )


# ---------------------------------------------------------------------------
# Invariant 2 — partial base loss preserves derived (T6.C.b)
# ---------------------------------------------------------------------------

class PartialBaseLossPreservesDerivedTests(unittest.TestCase):
    """T6.C.b refinement: a derived edge with a foundational
    (transitive) base alive + a corroborative (operator) base lost
    stays active. The cascade-removed doc only affects the
    corroborator's base; the foundation chain is untouched."""

    def test_partial_base_loss_preserves_derived(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            # Two base relations: one from a doc that will SURVIVE,
            # one from a doc we'll remove. The derived edge references
            # the latter as an operator (corroborator) entry + the
            # former as a transitive (foundation).
            _write_entity(root, "concept", "Foundation", [{
                "id":      "e_foundation_rel",
                "target":  "X",
                "type":    "RELATED_TO",
                "sources": [{
                    "doc_id": "doc_survives", "role": "extract",
                    "weight": 0.95,
                }],
            }])
            _write_entity(root, "concept", "Corroborator", [{
                "id":      "e_corr_rel",
                "target":  "Y",
                "type":    "RELATED_TO",
                "sources": [{
                    "doc_id": "doc_remove", "role": "extract",
                    "weight": 0.6,
                }],
            }])
            _write_entity(root, "concept", "Derived", [{
                "id":           "e_derived_rel",
                "target":       "DerivedTarget",
                "type":         "RELATED_TO",
                "sources": [{
                    "doc_id": "doc_unrelated", "role": "extract",
                    "weight": 0.8,
                }],
                "derived_from": [
                    {"base_fact_id": "e_foundation_rel",
                     "derivation": "transitive"},
                    {"base_fact_id": "e_corr_rel",
                     "derivation": "operator"},
                ],
            }])
            entity_root = root / "entity"

            cascade_remove_doc_from_sources("doc_remove", entity_root)

            # Foundation alive → derived preserved (T6.C.b).
            derived_rels = _load_relations(
                root / "entity" / "prod" / "concept" / "Derived.md"
            )
            self.assertEqual(len(derived_rels), 1)
            # Derived's own mutation_type stays at v0.4 default
            # ("active") since the cascade only touched the corroborator
            # and T6.C.b preserves on partial loss.
            self.assertNotEqual(
                derived_rels[0].get("mutation_type"), "invalidated"
            )
            status = derived_rels[0].get("status", {})
            # Either absent (v0.4 default) or active=True; not
            # invalidated.
            self.assertNotEqual(status.get("active"), False)


# ---------------------------------------------------------------------------
# Invariant 3 — causality chain acyclic rejected at write
# ---------------------------------------------------------------------------

class CausalityChainAcyclicTests(unittest.TestCase):
    """Decision 3 LOCK — a relation whose derived_from transitively
    points to itself raises at validate_edge_t6_derived_from time
    (the write-side gate from T6.A)."""

    def test_self_reference_rejected_at_write(self):
        edge = {
            "id": "e_self",
            "derived_from": [
                {"base_fact_id": "e_self", "derivation": "transitive"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "derivation cycle"):
            validate_edge_t6_derived_from(
                edge, edges_by_id={"e_self": edge},
            )

    def test_two_hop_cycle_rejected_at_write(self):
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


# ---------------------------------------------------------------------------
# Invariant 4 — cascade invalidation emits audit row
# ---------------------------------------------------------------------------

class CascadeInvalidateAuditTests(unittest.TestCase):
    """Every T6 invalidation surfaces in audit_log with
    ``mutation_type="invalidated_by_cascade"`` + chain pointers
    so the T7 replay primitive can reconstruct the history."""

    def test_cascade_invalidate_emits_audit_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            _write_entity(root, "concept", "Base", [{
                "id":      "e_base_rel",
                "target":  "X",
                "type":    "RELATED_TO",
                "sources": [{
                    "doc_id": "doc_A", "role": "extract", "weight": 0.9,
                }],
            }])
            _write_entity(root, "concept", "Derived", [{
                "id":           "e_derived_rel",
                "target":       "Y",
                "type":         "RELATED_TO",
                "sources": [{
                    "doc_id": "doc_unrelated", "role": "extract",
                    "weight": 0.8,
                }],
                "derived_from": [
                    {"base_fact_id": "e_base_rel",
                     "derivation": "transitive"},
                ],
            }])
            entity_root = root / "entity"
            emit = MagicMock()

            cascade_remove_doc_from_sources(
                "doc_A", entity_root, audit_emit=emit,
            )

            emit.assert_called_once()
            payload = emit.call_args[0][0]
            self.assertEqual(
                payload["mutation_type"], "invalidated_by_cascade"
            )
            self.assertEqual(payload["base_fact_id"], "e_base_rel")
            self.assertEqual(payload["derived_edge_id"], "e_derived_rel")
            self.assertIn("entity_path", payload)


if __name__ == "__main__":
    unittest.main()
