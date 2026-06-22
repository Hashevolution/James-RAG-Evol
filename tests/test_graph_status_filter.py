"""Live-traversal lifecycle-status filter (v0.6.1, Option A).

Pins that current-state graph traversal honors lifecycle status: a
relation deactivated by the cascade / T1 / T7 must NOT appear in the live
LLM context, while active relations are retained. Backed by the
measurement in scripts/research/cascade_consistency_probe.py (#1020).

Run: python -m unittest tests.test_graph_status_filter
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.graph_engine.constants import relation_is_live
from core.graph_engine.engine import GraphEngine


class RelationIsLiveTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("JAMES_DISABLE_STATUS_FILTER", None)

    def test_active_is_live(self):
        self.assertTrue(relation_is_live({"status": {"active": True}, "mutation_type": "active"}))

    def test_untagged_legacy_is_live(self):
        self.assertTrue(relation_is_live({"target": "X", "label": "관련"}))

    def test_deactivated_not_live(self):
        self.assertFalse(relation_is_live({"status": {"active": False}}))
        self.assertFalse(relation_is_live({"mutation_type": "invalidated"}))
        self.assertFalse(relation_is_live({"mutation_type": "superseded"}))
        self.assertFalse(relation_is_live({"mutation_type": "expired"}))

    def test_kill_switch_restores_legacy(self):
        os.environ["JAMES_DISABLE_STATUS_FILTER"] = "1"
        try:
            self.assertTrue(relation_is_live({"mutation_type": "invalidated"}))
        finally:
            os.environ.pop("JAMES_DISABLE_STATUS_FILTER", None)


class LiveContextExcludesDeadEdgeTests(unittest.TestCase):
    """The REAL live-context builder must drop a deactivated edge."""
    def setUp(self):
        os.environ.pop("JAMES_DISABLE_STATUS_FILTER", None)
        self.eng = object.__new__(GraphEngine)  # build_graph_context_str needs no __init__
        self.entity = {
            "name": "Alpha", "entity_type": "concept",
            "relations": [
                {"target": "Beta",  "label": "관련", "confidence": 0.9,
                 "status": {"active": True}, "mutation_type": "active"},
                {"target": "Gamma", "label": "포함", "confidence": 0.9,
                 "status": {"active": False}, "mutation_type": "invalidated"},
            ],
        }

    def test_dead_edge_excluded_active_kept(self):
        ctx = self.eng.build_graph_context_str([self.entity], [], 0.0)
        self.assertIn("Beta", ctx)       # active retained
        self.assertNotIn("Gamma", ctx)   # invalidated excluded

    def test_kill_switch_leaks_again(self):
        os.environ["JAMES_DISABLE_STATUS_FILTER"] = "1"
        try:
            ctx = self.eng.build_graph_context_str([self.entity], [], 0.0)
            self.assertIn("Gamma", ctx)  # legacy behavior: leaks
        finally:
            os.environ.pop("JAMES_DISABLE_STATUS_FILTER", None)


class ValidityWindowTests(unittest.TestCase):
    """v0.6.1 iter3 — relation_is_live honors the T1 validity window for
    current-state queries (the expiration sweep is batch, not per-query,
    so a time-expired-but-unswept edge would otherwise leak)."""
    def setUp(self):
        os.environ.pop("JAMES_DISABLE_STATUS_FILTER", None)
        from datetime import datetime, timezone
        self.at = datetime(2026, 6, 22, tzinfo=timezone.utc)

    def _rel(self, frm=None, to=None):
        r = {"target": "X", "label": "관련", "confidence": 0.9,
             "status": {"active": True}, "mutation_type": "active"}
        if frm or to:
            r["validity"] = {"from": frm, "to": to}
        return r

    def test_expired_to_in_past_not_live(self):
        self.assertFalse(relation_is_live(
            self._rel(to="2020-01-01T00:00:00Z"), at=self.at))

    def test_not_yet_valid_from_in_future_not_live(self):
        self.assertFalse(relation_is_live(
            self._rel(frm="2099-01-01T00:00:00Z"), at=self.at))

    def test_within_window_is_live(self):
        self.assertTrue(relation_is_live(
            self._rel(frm="2020-01-01T00:00:00Z", to="2099-01-01T00:00:00Z"),
            at=self.at))

    def test_no_validity_is_live(self):
        self.assertTrue(relation_is_live(self._rel(), at=self.at))

    def test_unparseable_validity_is_permissive(self):
        self.assertTrue(relation_is_live(self._rel(to="not-a-date"), at=self.at))

    def test_context_excludes_time_expired_edge(self):
        # real build_graph_context_str, real now: a 2020 to-date is expired.
        eng = object.__new__(GraphEngine)
        ent = {"name": "Omicron", "entity_type": "concept", "relations": [
            {"target": "Pi", "label": "관련", "confidence": 0.9,
             "status": {"active": True}, "mutation_type": "active"},
            {"target": "Rho", "label": "관련", "confidence": 0.9,
             "status": {"active": True}, "mutation_type": "active",
             "validity": {"from": "2019-01-01T00:00:00Z", "to": "2020-01-01T00:00:00Z"}},
        ]}
        ctx = eng.build_graph_context_str([ent], [], 0.0)
        self.assertIn("Pi", ctx)
        self.assertNotIn("Rho", ctx)


class GraphScoreExcludesDeadTests(unittest.TestCase):
    """v0.6.1 iter2 — a deactivated edge must not inflate compute_graph_score
    (which drives DFS halting + ranking)."""
    def setUp(self):
        os.environ.pop("JAMES_DISABLE_STATUS_FILTER", None)

    def test_dead_relation_excluded_from_score(self):
        from core.ontology import compute_graph_score
        active = {"target": "B", "label": "관련", "confidence": 0.9, "status": {"active": True}}
        dead = {"target": "C", "label": "관련", "confidence": 0.9,
                "status": {"active": False}, "mutation_type": "invalidated"}
        self.assertEqual(compute_graph_score([active]), compute_graph_score([active, dead]))

    def test_kill_switch_counts_dead(self):
        from core.ontology import compute_graph_score
        active = {"target": "B", "label": "관련", "confidence": 0.9, "status": {"active": True}}
        dead = {"target": "C", "label": "관련", "confidence": 0.9,
                "status": {"active": False}, "mutation_type": "invalidated"}
        os.environ["JAMES_DISABLE_STATUS_FILTER"] = "1"
        try:
            self.assertGreater(compute_graph_score([active, dead]),
                               compute_graph_score([active]))
        finally:
            os.environ.pop("JAMES_DISABLE_STATUS_FILTER", None)


if __name__ == "__main__":
    unittest.main()
