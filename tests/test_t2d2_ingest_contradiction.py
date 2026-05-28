"""v0.4.1 PR-T2.D-2 contradiction dispatch contract tests.

Pins the three label-paths the dispatcher handles in this PR:

  - B_supersede → ``supersede_edge`` in-line, new_edge appended,
    new_rel dropped
  - ignore     → new_rel dropped, log entry only
  - A_invalidate → log + drop (cascade deferred to T2.D-2.b)

Plus the negative paths (no candidates → passthrough; defensive
crash recovery in _merge.py wiring).

Run:
  python -m unittest tests.test_t2d2_ingest_contradiction
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


def _v04_edge(target: str, predicate: str, *, valid_from: str = "2025-01-01T00:00:00Z",
              valid_to: str | None = None, sources_weight: float = 0.8,
              edge_id: str = "e_edge_existing") -> dict:
    """Build a v0.4-shaped existing edge for the classifier."""
    return {
        "id":      edge_id,
        "target":  target,
        "type":    predicate,
        "label":   predicate,
        "validity": {"from": valid_from, "to": valid_to},
        "status":   {"active": True},
        "mutation_type": "active",
        "sources": [
            {"doc_id": "old_doc", "ts": valid_from,
             "weight": sources_weight, "role": "legacy"},
        ],
    }


def _new_rel(target: str, predicate: str, *,
             confidence: float = 0.9) -> dict:
    """Build an ingestion-shape new relation."""
    return {
        "target":     target,
        "type":       predicate,
        "label":      predicate,
        "confidence": confidence,
        "sources":    [
            {"doc_id": "new_doc", "ts": "2026-05-28T00:00:00Z",
             "weight": confidence, "role": "extract"},
        ],
    }


# ---------------------------------------------------------------------------
# B_supersede path
# ---------------------------------------------------------------------------

class BSupersedePathTests(unittest.TestCase):
    """Rule 1: new_fact.valid_from > old_edge.validity.to (or now).
    Classifier returns B_supersede; supersede_edge applied."""

    def test_b_supersede_adds_new_edge_and_drops_new_rel(self):
        existing = [
            _v04_edge("Dario", "CEO_OF", valid_from="2024-01-01T00:00:00Z",
                      valid_to="2026-01-01T00:00:00Z"),
        ]
        new_rel = _new_rel("NewName", "CEO_OF")
        # valid_from on new_rel = ingest_ts; the classifier reads
        # new_fact.valid_from OR validity.from OR timestamp/ts.
        new_rel["valid_from"] = "2026-05-28T00:00:00Z"

        rels_to_merge, log = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="new_doc",
            ingest_ts="2026-05-28T00:00:00Z",
        )

        # new_rel was dropped from the merge list (supersede handled it).
        self.assertEqual(rels_to_merge, [])
        # existing_rels gained the new_edge AND mutated the old edge.
        self.assertEqual(len(existing), 2)
        # Old edge mutated in-place — status carries superseded_by.
        old_after = existing[0]
        new_edge = existing[1]
        self.assertEqual(old_after["status"].get("superseded_by"),
                         new_edge.get("id"))
        # Log entry shape.
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["label"], "B_supersede")
        self.assertEqual(log[0]["action"], "supersede_applied")
        self.assertEqual(log[0]["new_edge_id"], new_edge.get("id"))


# ---------------------------------------------------------------------------
# ignore path
# ---------------------------------------------------------------------------

class IgnorePathTests(unittest.TestCase):
    """Rule 3: keys match, new_fact.timestamp inside old_edge.validity,
    no confidence delta → ignore."""

    def test_ignore_drops_new_rel_no_supersede(self):
        existing = [
            _v04_edge("X", "RELATED_TO", valid_from="2024-01-01T00:00:00Z",
                      valid_to="2027-01-01T00:00:00Z", sources_weight=0.85),
        ]
        # Same target + same confidence + timestamp inside window
        # → classifier returns "ignore".
        new_rel = _new_rel("X", "RELATED_TO", confidence=0.85)
        new_rel["timestamp"] = "2026-01-01T00:00:00Z"

        rels_to_merge, log = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="dup_doc",
            ingest_ts="2026-01-01T00:00:00Z",
        )

        # new_rel was dropped.
        self.assertEqual(rels_to_merge, [])
        # No new edge appended (supersede did NOT run).
        self.assertEqual(len(existing), 1)
        # Log entry says ignore.
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["label"], "ignore")
        self.assertEqual(log[0]["action"], "drop_new_rel_ignored")


# ---------------------------------------------------------------------------
# A_invalidate path — deferred (logged only)
# ---------------------------------------------------------------------------

class AInvalidateDeferredPathTests(unittest.TestCase):
    """Rule 2: A_invalidate fires when new is higher-confidence AND
    timestamp ≤ old_edge.validity.from. T2.D-2 only LOGS — cascade
    deferred to T2.D-2.b (race with _merge.py write-after-read)."""

    def test_a_invalidate_logged_and_new_rel_dropped(self):
        existing = [
            _v04_edge("X", "RELATED_TO", valid_from="2026-01-01T00:00:00Z",
                      sources_weight=0.5),
        ]
        # Higher-confidence retroactive correction.
        new_rel = _new_rel("X", "RELATED_TO", confidence=0.95)
        new_rel["timestamp"] = "2025-06-01T00:00:00Z"

        rels_to_merge, log = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="correction_doc",
            ingest_ts="2025-06-01T00:00:00Z",
        )

        # new_rel was dropped on the assumption a future cascade
        # invalidates the wrong source.
        self.assertEqual(rels_to_merge, [])
        # No new edge — supersede did NOT run. T2.D-2.b will
        # call cascade after the merge completes.
        self.assertEqual(len(existing), 1)
        # Log carries the deferred marker.
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["label"], "A_invalidate")
        self.assertEqual(log[0]["action"], "a_invalidate_logged_deferred")


# ---------------------------------------------------------------------------
# No-candidate passthrough
# ---------------------------------------------------------------------------

class NoCandidatePassthroughTests(unittest.TestCase):

    def test_no_match_keeps_new_rel(self):
        """Empty existing → no candidates → passthrough.

        Note: production ``core.ontology.normalize_relation`` collapses
        many specific predicate labels (CEO_OF, BASED_IN, etc.) into
        the umbrella ``RELATED_TO``. So tests that want "different
        predicate, no match" need to either use predicates that
        survive normalization OR use an empty existing list. Using
        empty here keeps the test focused on the passthrough contract.
        """
        existing: list = []
        new_rel = _new_rel("Y", "BASED_IN")
        rels_to_merge, log = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="doc", ingest_ts="2026-05-28T00:00:00Z",
        )
        self.assertEqual(rels_to_merge, [new_rel])
        self.assertEqual(log, [])

    def test_legacy_existing_no_lifecycle_keeps_new_rel(self):
        """Existing edge without v0.4 lifecycle metadata → detector
        returns no candidate → passthrough."""
        existing = [{"target": "X", "type": "RELATED_TO"}]
        new_rel = _new_rel("X", "RELATED_TO")
        rels_to_merge, log = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="doc", ingest_ts="2026-05-28T00:00:00Z",
        )
        self.assertEqual(rels_to_merge, [new_rel])
        self.assertEqual(log, [])

    def test_empty_input_returns_empty(self):
        rels, log = dispatch_contradictions_for_merge(
            [], [],
            ingest_doc_id="doc", ingest_ts="2026-05-28T00:00:00Z",
        )
        self.assertEqual(rels, [])
        self.assertEqual(log, [])


# ---------------------------------------------------------------------------
# Audit emit callback
# ---------------------------------------------------------------------------

class AuditEmitTests(unittest.TestCase):

    def test_b_supersede_emits_audit_row(self):
        existing = [
            _v04_edge("Dario", "CEO_OF", valid_from="2024-01-01T00:00:00Z",
                      valid_to="2026-01-01T00:00:00Z"),
        ]
        new_rel = _new_rel("NewName", "CEO_OF")
        new_rel["valid_from"] = "2026-05-28T00:00:00Z"

        emit = MagicMock()
        dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="new_doc", ingest_ts="2026-05-28T00:00:00Z",
            audit_emit=emit,
        )

        emit.assert_called_once()
        payload = emit.call_args[0][0]
        self.assertEqual(payload["endpoint"], "lifecycle:ingest_contradiction")
        self.assertEqual(payload["mutation_type"], "superseded")
        self.assertIn("old_edge_id", payload)
        self.assertIn("new_edge_id", payload)

    def test_a_invalidate_emits_deferred_marker(self):
        existing = [
            _v04_edge("X", "RELATED_TO", valid_from="2026-01-01T00:00:00Z",
                      sources_weight=0.5),
        ]
        new_rel = _new_rel("X", "RELATED_TO", confidence=0.95)
        new_rel["timestamp"] = "2025-06-01T00:00:00Z"

        emit = MagicMock()
        dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="correction_doc",
            ingest_ts="2025-06-01T00:00:00Z",
            audit_emit=emit,
        )

        emit.assert_called_once()
        payload = emit.call_args[0][0]
        self.assertEqual(payload["mutation_type"], "invalidated_deferred")
        self.assertEqual(payload["note"], "cascade_remove deferred to T2.D-2.b")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class EdgeCaseTests(unittest.TestCase):

    def test_malformed_new_rels_skipped(self):
        """Empty existing → only structural shape of new_rels matters.
        Valid dicts pass through; non-dicts are skipped."""
        existing: list = []
        # Mix of None, str, valid dict
        rels, log = dispatch_contradictions_for_merge(
            [None, "not a dict", {"target": "Y", "type": "BASED_IN"}],  # type: ignore[list-item]
            existing,
            ingest_doc_id="doc", ingest_ts="2026-05-28T00:00:00Z",
        )
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["target"], "Y")

    def test_ingest_ts_parse_fallback_to_now(self):
        """Malformed ingest_ts → falls back to datetime.now(UTC)."""
        existing = [
            _v04_edge("Dario", "CEO_OF", valid_from="2024-01-01T00:00:00Z",
                      valid_to="2026-01-01T00:00:00Z"),
        ]
        new_rel = _new_rel("NewName", "CEO_OF")
        new_rel["valid_from"] = "2026-05-28T00:00:00Z"

        # ingest_ts is garbage → falls back to now(UTC) which is
        # 2026-05-28T... > 2026-01-01 valid_to → B_supersede still fires
        rels, log = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="doc", ingest_ts="not an iso date",
        )
        self.assertEqual(len(log), 1)
        # B_supersede should still fire because new valid_from is
        # strictly later than old validity.to.
        self.assertEqual(log[0]["label"], "B_supersede")


if __name__ == "__main__":
    unittest.main()
