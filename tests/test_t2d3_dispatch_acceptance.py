"""v0.4.1 PR-T2.D-3 — end-to-end dispatch acceptance integration test.

Companion to step7-v6 q17 (CEO question). Constructs a synthetic
CEO-change scenario and verifies the T2.D-2 dispatch path
(``dispatch_contradictions_for_merge``) under flag-ON produces:

  - B_supersede label from the classifier
  - new edge appended to existing_rels with v0.4 lifecycle metadata
  - old edge mutated in place: ``status.superseded_by`` →
    ``status.active=False``, ``mutation_type=superseded``
  - audit row carries ``mutation_type=superseded`` + chain pointers
  - chain replay via ``walk_supersede_chain`` returns ordered
    [old → new]

This is the "exercises A/B routing end-to-end" deliverable from the
v0.4.1 entry memo §3 PR-T2.D row. Step7 q17 against the live wiki
measures whether the system answers CEO questions correctly; this
acceptance test measures whether the dispatch machinery would
correctly transition the CEO edge when an operator-seeded CEO_OF
edge meets a newer CEO observation.

T2.D-2.b carry-over: the A_invalidate code path is NOT exercised
here — the race-free B_supersede case is the v0.4.1 release gate
for T2.D. A_invalidate acceptance test lands in T2.D-2.b's PR.

Run:
  python -m pytest tests/test_t2d3_dispatch_acceptance.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lifecycle.ingest_contradiction import (  # noqa: E402
    dispatch_contradictions_for_merge,
)
from core.lifecycle.supersede_chain import (  # noqa: E402
    walk_supersede_chain,
)


def _seed_existing_ceo_edge(
    *,
    target: str = "Dario Amodei",
    valid_from: str = "2021-05-28T00:00:00Z",
    valid_to: str | None = "2026-05-28T00:00:00Z",
    sources_weight: float = 0.85,
    edge_id: str = "e_edge_anthropic_ceo_v1",
) -> dict:
    """Construct the seed Anthropic CEO_OF edge in v0.4 lifecycle
    shape. Mirrors what an operator-curated seed PR would write to
    ``wiki/entity/prod/org/anthropic.md``."""
    return {
        "id":             edge_id,
        "target":         target,
        "target_id":      "e_person_dario",
        "target_type":    "person",
        "type":           "CEO_OF",
        "label":          "CEO",
        "validity":       {"from": valid_from, "to": valid_to},
        "status":         {"active": True, "superseded_by": None,
                           "superseded_at": None},
        "mutation_type":  "active",
        "sources": [
            {"doc_id":     "founders_announcement_2021",
             "ts":         valid_from,
             "weight":     sources_weight,
             "role":       "primary",
             "valid_from": None,
             "valid_until": None},
        ],
        "confidence": sources_weight,
    }


def _new_ceo_observation(
    *,
    target: str = "New CEO",
    valid_from: str = "2026-05-28T00:00:00Z",
    confidence: float = 0.9,
) -> dict:
    """The new CEO observation that ingestion would receive (e.g.,
    from a press release). Ingestion shape — not v0.4 yet, the
    dispatch pipeline lifts it."""
    return {
        "target":     target,
        "target_id":  "e_person_new_ceo",
        "target_type": "person",
        "type":       "CEO_OF",
        "label":      "CEO",
        "valid_from": valid_from,
        "confidence": confidence,
        "sources": [
            {"doc_id":  "press_release_2026_q2",
             "ts":      valid_from,
             "weight":  confidence,
             "role":    "extract"},
        ],
    }


class BSupersedeAcceptanceTests(unittest.TestCase):
    """End-to-end: seed edge + new observation + dispatch → chain."""

    def setUp(self):
        self.audit = MagicMock()
        # Seed entity state — the operator-curated Anthropic CEO_OF
        # edge in v0.4 lifecycle shape. This is what T2.D-4 will
        # write to wiki/entity/prod/org/anthropic.md.
        self.existing_rels = [_seed_existing_ceo_edge()]

    def test_dispatch_routes_to_b_supersede(self):
        """new.valid_from > old.validity.to → classifier rule 1 →
        B_supersede → supersede_edge applied."""
        new_rel = _new_ceo_observation(
            target="New CEO",
            valid_from="2026-06-01T00:00:00Z",
        )

        rels_to_merge, log = dispatch_contradictions_for_merge(
            [new_rel], self.existing_rels,
            ingest_doc_id="press_release_2026_q2",
            ingest_ts="2026-06-01T00:00:00Z",
            audit_emit=self.audit,
        )

        # new_rel was consumed by the supersede path (not appended
        # as-is). existing_rels gained the new_edge.
        self.assertEqual(rels_to_merge, [])
        self.assertEqual(len(self.existing_rels), 2)
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["label"], "B_supersede")
        self.assertEqual(log[0]["action"], "supersede_applied")

    def test_old_edge_mutated_with_chain_link(self):
        """supersede_edge contract — old edge picks up
        status.superseded_by + mutation_type=superseded."""
        new_rel = _new_ceo_observation(valid_from="2026-06-01T00:00:00Z")

        dispatch_contradictions_for_merge(
            [new_rel], self.existing_rels,
            ingest_doc_id="press_release_2026_q2",
            ingest_ts="2026-06-01T00:00:00Z",
        )

        old = self.existing_rels[0]
        new_edge = self.existing_rels[1]
        self.assertEqual(
            old["status"]["superseded_by"], new_edge["id"],
            "old edge must point at the new edge",
        )
        self.assertFalse(old["status"]["active"])
        self.assertEqual(old["mutation_type"], "superseded")

    def test_new_edge_has_v04_lifecycle_metadata(self):
        """The new edge generated by supersede_edge gets fresh v0.4
        defaults applied — validity.from = supersede_ts, status.active
        = True, mutation_type = active."""
        new_rel = _new_ceo_observation(valid_from="2026-06-01T00:00:00Z")

        dispatch_contradictions_for_merge(
            [new_rel], self.existing_rels,
            ingest_doc_id="press_release_2026_q2",
            ingest_ts="2026-06-01T00:00:00Z",
        )

        new_edge = self.existing_rels[1]
        self.assertIn("validity", new_edge)
        self.assertIn("status", new_edge)
        self.assertTrue(new_edge["status"]["active"])
        self.assertIsNone(new_edge["status"]["superseded_by"])
        self.assertEqual(new_edge["mutation_type"], "active")

    def test_chain_walkable_old_to_new(self):
        """walk_supersede_chain (from PR-T7.A) returns the chain
        ordered old → new after dispatch."""
        new_rel = _new_ceo_observation(valid_from="2026-06-01T00:00:00Z")

        dispatch_contradictions_for_merge(
            [new_rel], self.existing_rels,
            ingest_doc_id="press_release_2026_q2",
            ingest_ts="2026-06-01T00:00:00Z",
        )

        old = self.existing_rels[0]
        edges_by_id = {er["id"]: er for er in self.existing_rels}
        chain = walk_supersede_chain(old, edges_by_id.get)

        # Chain length = 2 (old → new)
        self.assertEqual(len(chain), 2)
        # First link is the old edge
        self.assertEqual(chain[0]["id"], old["id"])
        # Second link is the new edge
        self.assertEqual(chain[1]["id"], self.existing_rels[1]["id"])

    def test_audit_row_carries_chain_pointers(self):
        """The audit emit callback receives a payload with
        mutation_type=superseded + old_edge_id + new_edge_id +
        superseded_at — enough for the T7 replay primitive to
        reconstruct the chain history from audit_log alone."""
        new_rel = _new_ceo_observation(valid_from="2026-06-01T00:00:00Z")

        dispatch_contradictions_for_merge(
            [new_rel], self.existing_rels,
            ingest_doc_id="press_release_2026_q2",
            ingest_ts="2026-06-01T00:00:00Z",
            audit_emit=self.audit,
        )

        self.audit.assert_called_once()
        payload = self.audit.call_args[0][0]
        self.assertEqual(payload["endpoint"],
                         "lifecycle:ingest_contradiction")
        self.assertEqual(payload["mutation_type"], "superseded")
        self.assertIn("old_edge_id", payload)
        self.assertIn("new_edge_id", payload)
        self.assertIn("superseded_at", payload)


class CEOQueryStillWorksWithFlagOffTests(unittest.TestCase):
    """Flag-OFF (default) must preserve byte-identical legacy
    behavior — the dispatcher is never invoked from _merge.py.

    Asserts the env-default contract by checking the env at
    import time."""

    def test_flag_default_is_off(self):
        """JAMES_T2D_INGEST_DISPATCH default OFF → production stays
        byte-identical to today. Setting this assertion explicitly so
        a CI environment that accidentally exports the flag surfaces
        the contract violation."""
        # Note: this test isn't a guarantee — it just records the
        # expected default. The actual _merge.py wiring reads the
        # env on EVERY merge call, not at import time.
        flag = os.environ.get("JAMES_T2D_INGEST_DISPATCH")
        # In CI the flag should be unset or explicitly "0". Tests
        # that need flag-ON set it locally.
        self.assertIn(flag, (None, "0"))


if __name__ == "__main__":
    unittest.main()
