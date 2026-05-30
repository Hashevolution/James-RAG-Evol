"""step7 v5 fixture schema invariants — QVT α-2 contract test.

v5 (2026-05-28) adds `gold_signals` (3 atomic claims per query) and
`abstention_truth` ("present" / "absent") to every query, plus
`min_recall` to the 5 queries already carrying `expected_path.nodes`.

This test pins the schema so any future fixture edit that drops or
malforms the new fields is caught at PR time before it reaches the
QVT oracle.

Run:
  python -m unittest tests.test_step7_v5_schema
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "eval" / "regression" / "step7_queries.json"
)


def _load_fixture() -> dict:
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


class FixtureVersionTests(unittest.TestCase):
    """v5+ schema version + description carry the QVT α-2 contract.
    v6 (T2.D-3, 2026-05-28) adds q17 CEO question for dispatch
    acceptance baseline. v7 (α-5 prereq §5.2/5.3, 2026-05-30) adds
    8 expected_path annotations + 3 hard queries (q18/q19/q20) so
    the path-coverage axis is not saturated at the baseline."""

    def test_version_at_least_v5(self):
        data = _load_fixture()
        # Accept v5, v6, or v7 — all retain v5 invariants.
        self.assertIn(
            data["version"], ("step7-v5", "step7-v6", "step7-v7"),
            "version must be 'step7-v5'/'v6'/'v7' (later bumps "
            "should keep the QVT α-2 invariants below or add an "
            "explicit schema migration)",
        )

    def test_queries_count_min(self):
        """v5 = 16 queries; v6 = 17 queries (q17 CEO acceptance);
        v7 = 20 queries (q18/q19/q20 hard fixtures). Lower bound is v5."""
        data = _load_fixture()
        self.assertGreaterEqual(len(data["queries"]), 16)


class GoldSignalsTests(unittest.TestCase):
    """Every query has 3 atomic gold_signals; the design memo §2.2
    pins 3 claims per query as the granularity contract."""

    def test_every_query_has_gold_signals(self):
        data = _load_fixture()
        for q in data["queries"]:
            self.assertIn(
                "gold_signals", q,
                f"q{q['id']} missing gold_signals (QVT α-2 invariant)",
            )

    def test_three_signals_per_query(self):
        data = _load_fixture()
        for q in data["queries"]:
            n = len(q["gold_signals"])
            self.assertEqual(
                n, 3,
                f"q{q['id']} has {n} gold_signals; design memo §2.2 "
                f"pins 3 atomic claims per query. Adjust granularity "
                f"with explicit memo edit + bump to v6.",
            )

    def test_signal_shape(self):
        data = _load_fixture()
        for q in data["queries"]:
            for i, sig in enumerate(q["gold_signals"]):
                self.assertIn(
                    "term", sig,
                    f"q{q['id']}.gold_signals[{i}] missing 'term'",
                )
                self.assertIsInstance(
                    sig["term"], str,
                    f"q{q['id']}.gold_signals[{i}].term must be str",
                )
                self.assertTrue(
                    sig["term"].strip(),
                    f"q{q['id']}.gold_signals[{i}].term must be non-empty",
                )
                if "aliases" in sig:
                    self.assertIsInstance(
                        sig["aliases"], list,
                        f"q{q['id']}.gold_signals[{i}].aliases must be list",
                    )
                    for j, a in enumerate(sig["aliases"]):
                        self.assertIsInstance(
                            a, str,
                            f"q{q['id']}.gold_signals[{i}].aliases[{j}] "
                            f"must be str",
                        )


class AbstentionTruthTests(unittest.TestCase):
    """Every query has abstention_truth ∈ {present, absent}."""

    _ALLOWED = frozenset({"present", "absent"})

    def test_every_query_has_abstention_truth(self):
        data = _load_fixture()
        for q in data["queries"]:
            self.assertIn(
                "abstention_truth", q,
                f"q{q['id']} missing abstention_truth (QVT α-2 invariant)",
            )

    def test_abstention_truth_value_in_allowed_set(self):
        data = _load_fixture()
        for q in data["queries"]:
            self.assertIn(
                q["abstention_truth"], self._ALLOWED,
                f"q{q['id']}.abstention_truth={q['abstention_truth']!r} "
                f"must be one of {sorted(self._ALLOWED)}",
            )

    def test_security_queries_are_absent(self):
        """Security queries (q11, q12) should be flagged abstain-required
        so the abstention F1 metric correctly rewards refusal responses."""
        data = _load_fixture()
        for q in data["queries"]:
            if q["category"] == "security":
                self.assertEqual(
                    q["abstention_truth"], "absent",
                    f"q{q['id']} (security) should mark abstention_truth="
                    f"'absent' so refusal responses score as correct",
                )


class ExpectedPathTests(unittest.TestCase):
    """The 5 path-annotated queries (v4 carry-over) gain min_recall;
    v5 schema does NOT yet add expected_path.edges (deferred until the
    wiki graph gains semantic relation types beyond generic RELATED_TO)."""

    _PATH_QUERIES = frozenset({1, 2, 3, 4, 15})

    def test_min_recall_on_path_queries(self):
        data = _load_fixture()
        for q in data["queries"]:
            if q["id"] in self._PATH_QUERIES:
                self.assertIn(
                    "expected_path", q,
                    f"q{q['id']} expected to carry expected_path (v4 GT)",
                )
                ep = q["expected_path"]
                self.assertIn(
                    "nodes", ep,
                    f"q{q['id']}.expected_path missing nodes",
                )
                self.assertIn(
                    "min_recall", ep,
                    f"q{q['id']}.expected_path missing min_recall (v5)",
                )
                self.assertIsInstance(ep["min_recall"], (int, float))
                self.assertGreaterEqual(ep["min_recall"], 0.0)
                self.assertLessEqual(ep["min_recall"], 1.0)

    def test_edges_deferred_not_required(self):
        """Negative assertion: schema validator does not require
        expected_path.edges yet. Re-enable as a positive assertion
        when the wiki graph gains semantic relation types."""
        data = _load_fixture()
        for q in data["queries"]:
            ep = q.get("expected_path")
            if ep is None:
                continue


class AggregateCountsTests(unittest.TestCase):
    """Distribution sanity checks — protect against accidental wholesale
    flips (e.g. someone marking all queries 'absent')."""

    def test_present_majority(self):
        data = _load_fixture()
        n_present = sum(
            1 for q in data["queries"] if q["abstention_truth"] == "present"
        )
        # 2026-05-28 v6 baseline = 12 present / 5 absent (17 total).
        # 2026-05-30 v7 adds 3 hard `present` queries (q18/q19/q20) →
        # 15 present / 5 absent (20 total). Band widened to absorb v7
        # while still catching wholesale flips.
        self.assertGreaterEqual(n_present, 8)
        self.assertLessEqual(n_present, 17)


if __name__ == "__main__":
    unittest.main()
