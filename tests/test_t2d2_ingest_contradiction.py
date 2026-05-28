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
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lifecycle.ingest_contradiction import (  # noqa: E402
    PendingCascade,
    apply_pending_cascades,
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

        rels_to_merge, log, _pending = dispatch_contradictions_for_merge(
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

        rels_to_merge, log, _pending = dispatch_contradictions_for_merge(
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

class AInvalidatePendingCascadeTests(unittest.TestCase):
    """Rule 2: A_invalidate fires when new is higher-confidence AND
    timestamp ≤ old_edge.validity.from. T2.D-2.b: dispatcher captures
    a PendingCascade + KEEPS new_rel for the regular merge loop.
    Caller (``_merge.py``) runs ``apply_pending_cascades`` after
    writing the entity to avoid the write-after-read race."""

    def test_a_invalidate_records_pending_cascade(self):
        existing = [
            _v04_edge("X", "RELATED_TO", valid_from="2026-01-01T00:00:00Z",
                      sources_weight=0.5,
                      edge_id="e_edge_existing"),
        ]
        # Higher-confidence retroactive correction.
        new_rel = _new_rel("X", "RELATED_TO", confidence=0.95)
        new_rel["timestamp"] = "2025-06-01T00:00:00Z"

        rels_to_merge, log, pending = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="correction_doc",
            ingest_ts="2025-06-01T00:00:00Z",
        )

        # new_rel is KEPT — the regular merge loop adds it as a fresh
        # edge; the post-write cascade removes the wrong source.
        self.assertEqual(rels_to_merge, [new_rel])
        # No supersede edge appended.
        self.assertEqual(len(existing), 1)
        # Log carries the cascade-pending marker + bad_doc_id.
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["label"], "A_invalidate")
        self.assertEqual(log[0]["action"], "a_invalidate_cascade_pending")
        self.assertEqual(log[0]["bad_doc_id"], "old_doc")
        # Pending cascades list contains the cascade request.
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].bad_doc_id, "old_doc")
        self.assertEqual(pending[0].pattern, "divergent_validity")
        self.assertIn("audit_payload", pending[0].__dict__)
        self.assertEqual(
            pending[0].audit_payload["old_edge_id"],
            "e_edge_existing",
        )


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
        rels_to_merge, log, _pending = dispatch_contradictions_for_merge(
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
        rels_to_merge, log, _pending = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="doc", ingest_ts="2026-05-28T00:00:00Z",
        )
        self.assertEqual(rels_to_merge, [new_rel])
        self.assertEqual(log, [])

    def test_empty_input_returns_empty(self):
        rels, log, _pending = dispatch_contradictions_for_merge(
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

    def test_a_invalidate_emits_pending_cascade_audit(self):
        """T2.D-2.b — A_invalidate emits a regular ``invalidated``
        audit row carrying ``bad_doc_id`` + ``old_edge_id``. The
        ``apply_pending_cascades`` post-write helper then emits a
        second audit row (mutation_type=invalidated_applied) with
        the cascade counts. This test covers only the dispatcher's
        pre-cascade emit; apply_pending_cascades tests cover the rest."""
        existing = [
            _v04_edge("X", "RELATED_TO", valid_from="2026-01-01T00:00:00Z",
                      sources_weight=0.5, edge_id="e_edge_a"),
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
        self.assertEqual(payload["mutation_type"], "invalidated")
        self.assertEqual(payload["bad_doc_id"], "old_doc")
        self.assertEqual(payload["old_edge_id"], "e_edge_a")
        self.assertEqual(payload["endpoint"],
                         "lifecycle:ingest_contradiction")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class EdgeCaseTests(unittest.TestCase):

    def test_malformed_new_rels_skipped(self):
        """Empty existing → only structural shape of new_rels matters.
        Valid dicts pass through; non-dicts are skipped."""
        existing: list = []
        # Mix of None, str, valid dict
        rels, log, _pending = dispatch_contradictions_for_merge(
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
        rels, log, _pending = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="doc", ingest_ts="not an iso date",
        )
        self.assertEqual(len(log), 1)
        # B_supersede should still fire because new valid_from is
        # strictly later than old validity.to.
        self.assertEqual(log[0]["label"], "B_supersede")


# ---------------------------------------------------------------------------
# apply_pending_cascades — T2.D-2.b post-write cascade execution
# ---------------------------------------------------------------------------

class ApplyPendingCascadesTests(unittest.TestCase):
    """The helper that runs the cascade requests collected during
    dispatch. Caller MUST invoke this after writing back the in-memory
    entity state — otherwise A_invalidate cascades are silently
    dropped (the dispatcher just records them)."""

    def test_empty_list_returns_empty(self):
        result = apply_pending_cascades([], Path("/tmp/nope"))
        self.assertEqual(result, [])

    def test_calls_cascade_remove_per_request(self):
        """Each PendingCascade triggers one cascade_remove call.
        Mock the underlying function to keep the test filesystem-free."""
        cascades = [
            PendingCascade(
                bad_doc_id="bad_doc_1",
                pattern="divergent_validity",
                audit_payload={"endpoint": "lifecycle:ingest_contradiction",
                               "mutation_type": "invalidated",
                               "bad_doc_id": "bad_doc_1",
                               "old_edge_id": "e_edge_a"},
            ),
            PendingCascade(
                bad_doc_id="bad_doc_2",
                pattern="different_tail",
                audit_payload={"endpoint": "lifecycle:ingest_contradiction",
                               "mutation_type": "invalidated",
                               "bad_doc_id": "bad_doc_2",
                               "old_edge_id": "e_edge_b"},
            ),
        ]
        fake_counts = {
            "entities_scanned":     5,
            "entities_touched":     1,
            "relations_recomputed": 1,
            "relations_dropped":    0,
        }
        with patch(
            "core.lifecycle.ingest_contradiction.cascade_remove_doc_from_sources",
            return_value=fake_counts,
        ) as mock_cascade:
            results = apply_pending_cascades(cascades, Path("/fake/root"))
        self.assertEqual(mock_cascade.call_count, 2)
        # Per-cascade result includes bad_doc_id + counts.
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["bad_doc_id"], "bad_doc_1")
        self.assertEqual(results[0]["counts"], fake_counts)
        self.assertEqual(results[1]["bad_doc_id"], "bad_doc_2")

    def test_audit_emit_post_cascade(self):
        """Each cascade emission carries the audit payload from the
        pending cascade + a ``cascade_counts`` key + mutation_type
        promoted to ``invalidated_applied``."""
        pending = [PendingCascade(
            bad_doc_id="bad_doc_x",
            pattern="divergent_validity",
            audit_payload={"endpoint": "lifecycle:ingest_contradiction",
                           "mutation_type": "invalidated",
                           "bad_doc_id": "bad_doc_x",
                           "old_edge_id": "e_edge_x"},
        )]
        fake_counts = {
            "entities_scanned":     3,
            "entities_touched":     1,
            "relations_recomputed": 0,
            "relations_dropped":    1,
        }
        emit = MagicMock()
        with patch(
            "core.lifecycle.ingest_contradiction.cascade_remove_doc_from_sources",
            return_value=fake_counts,
        ):
            apply_pending_cascades(pending, Path("/fake/root"), audit_emit=emit)
        emit.assert_called_once()
        payload = emit.call_args[0][0]
        self.assertEqual(payload["mutation_type"], "invalidated_applied")
        self.assertEqual(payload["bad_doc_id"], "bad_doc_x")
        self.assertEqual(payload["cascade_counts"], fake_counts)
        self.assertEqual(payload["old_edge_id"], "e_edge_x")


# ---------------------------------------------------------------------------
# _pick_cascade_target — the bad_doc_id heuristic
# ---------------------------------------------------------------------------

class PickCascadeTargetTests(unittest.TestCase):
    """Test the lowest-weight-non-manual heuristic via the dispatcher
    (the helper is module-private; we exercise it through the public
    A_invalidate path)."""

    def test_skips_manual_sources(self):
        """Manual-role sources are NEVER picked as the cascade target —
        cascade_remove preserves them by design. The lowest-weight
        NON-MANUAL source is chosen.

        Existing best non-manual = strong_doc 0.9 → new_rel needs
        confidence > 0.9 to trigger classifier rule 2 (A_invalidate).
        Manual weight stays out of the best-source comparison because
        the classifier reads sources[].weight uniformly; the
        ``_pick_cascade_target`` heuristic is separate."""
        existing = [{
            "id": "e_edge_a",
            "target": "X", "type": "RELATED_TO",
            "validity": {"from": "2026-01-01T00:00:00Z", "to": None},
            "status": {"active": True},
            "mutation_type": "active",
            "sources": [
                {"doc_id": "manual_seed", "role": "manual",  "weight": 0.5},
                {"doc_id": "weak_doc",    "role": "extract", "weight": 0.3},
                {"doc_id": "strong_doc",  "role": "extract", "weight": 0.9},
            ],
        }]
        new_rel = _new_rel("X", "RELATED_TO", confidence=0.95)
        new_rel["timestamp"] = "2025-06-01T00:00:00Z"

        _rels, log, pending = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="correction_doc",
            ingest_ts="2025-06-01T00:00:00Z",
        )
        # Classifier should have routed to A_invalidate.
        self.assertEqual(log[0]["label"], "A_invalidate")
        # bad_doc_id should be the LOWEST-weight NON-MANUAL source.
        self.assertEqual(log[0]["bad_doc_id"], "weak_doc")
        self.assertEqual(pending[0].bad_doc_id, "weak_doc")

    def test_no_cascadeable_source_skips(self):
        """Existing edge has only manual sources → no cascade target →
        action = a_invalidate_no_cascade_target, new_rel kept anyway.

        Note: this test uses _v04_edge-style with manual=0.6 source
        so the classifier still picks A_invalidate (new 0.95 > best
        manual 0.6) — exercising the no-eligible-cascade-target path
        of ``_pick_cascade_target``."""
        existing = [{
            "id": "e_edge_a",
            "target": "X", "type": "RELATED_TO",
            "validity": {"from": "2026-01-01T00:00:00Z", "to": None},
            "status": {"active": True},
            "mutation_type": "active",
            "sources": [
                {"doc_id": "manual_seed", "role": "manual", "weight": 0.6},
            ],
        }]
        new_rel = _new_rel("X", "RELATED_TO", confidence=0.95)
        new_rel["timestamp"] = "2025-06-01T00:00:00Z"

        rels, log, pending = dispatch_contradictions_for_merge(
            [new_rel], existing,
            ingest_doc_id="correction_doc",
            ingest_ts="2025-06-01T00:00:00Z",
        )
        # Classifier still says A_invalidate (new > best).
        self.assertEqual(log[0]["label"], "A_invalidate")
        # But there's no eligible cascade source → no pending.
        self.assertEqual(rels, [new_rel])  # kept anyway
        self.assertEqual(len(pending), 0)
        self.assertEqual(log[0]["action"], "a_invalidate_no_cascade_target")


if __name__ == "__main__":
    unittest.main()
