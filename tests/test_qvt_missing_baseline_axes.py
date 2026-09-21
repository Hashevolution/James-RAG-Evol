"""QVT matrix — "never compared" must not render as "flat".

The 5-axis Pareto verdict rule (CLAUDE.md rule #2, via
``scripts/qvt_ablation_matrix.py::_classify_five_axis_delta``) reads a
cell as **adopt** when quality improved and cost stayed flat. Cost-flat
was being produced two different ways:

  1. the cost axes were compared and came out inside the noise band, and
  2. the cost axes were never compared at all.

The renderer collapsed both into ``deltas[axis] = 0.0``::

    if med[axis] is None or base_med[axis] is None:
        deltas[axis] = 0.0

The baseline actually on disk is ``qvt-baseline-v1`` (2026-05-28), which
carries only path_coverage / graded_answer / abstention_f1 — no
``token_cost``, no ``latency_cost``. So every cell rendered against it
took branch 2 and was scored as if its cost had been checked. A cell
that doubled token cost would classify as **adopt**.

That is the same silent-null family as the LRB reranker fallback
(#1123) and the AUTO_ROUTER prerequisite (``test_qvt_layer_evidence``):
something did not happen, and the artifact did not say so.

Run:
  python -m unittest tests.test_qvt_missing_baseline_axes
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_SCRIPT = REPO_ROOT / "scripts" / "qvt_ablation_matrix.py"

_QUALITY = ("path_coverage", "graded_answer", "abstention_f1")
_COST = ("token_cost", "latency_cost")


def _load():
    spec = importlib.util.spec_from_file_location("_qvt_matrix_axes", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DeltaAvailabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_missing_baseline_axis_is_none_not_zero(self):
        """The regression this file exists for."""
        med = {ax: 1.0 for ax in _QUALITY + _COST}
        base = {ax: 0.5 for ax in _QUALITY}          # 3-axis baseline
        base.update({ax: None for ax in _COST})
        deltas, unavailable = self.m._deltas_vs_baseline(med, base)
        for ax in _COST:
            with self.subTest(axis=ax):
                self.assertIsNone(deltas[ax], f"{ax} must be None, not 0.0")
                self.assertIn(ax, unavailable)
        for ax in _QUALITY:
            self.assertAlmostEqual(deltas[ax], 0.5)
            self.assertNotIn(ax, unavailable)

    def test_missing_cell_axis_also_abstains(self):
        """Symmetric: a cell that lacks an axis is equally uncomparable."""
        med = {ax: 1.0 for ax in _QUALITY}
        med.update({ax: None for ax in _COST})
        base = {ax: 0.5 for ax in _QUALITY + _COST}
        deltas, unavailable = self.m._deltas_vs_baseline(med, base)
        self.assertEqual(unavailable, set(_COST))
        self.assertIsNone(deltas["token_cost"])

    def test_fully_comparable_axes_produce_numbers(self):
        med = {ax: 1.25 for ax in _QUALITY + _COST}
        base = {ax: 1.00 for ax in _QUALITY + _COST}
        deltas, unavailable = self.m._deltas_vs_baseline(med, base)
        self.assertEqual(unavailable, set())
        self.assertAlmostEqual(deltas["latency_cost"], 0.25)

    def test_fmt_delta_renders_na(self):
        self.assertEqual(self.m._fmt_delta(None, "+.3f"), "n/a")
        self.assertEqual(self.m._fmt_delta(0.5, "+.3f"), "+0.500")


class VerdictAbstentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def _bands(self, q=0.10, c=0.0):
        b = {ax: q for ax in _QUALITY}
        b.update({ax: c for ax in _COST})
        return b

    def test_quality_up_with_uncomparable_cost_is_not_adopt(self):
        """Before the fix this returned "adopt" — a Pareto verdict
        resting on a cost comparison that never ran."""
        deltas = {"path_coverage": 0.0, "graded_answer": 0.20,
                  "abstention_f1": 0.0, "token_cost": None,
                  "latency_cost": None}
        verdict = self.m._classify_five_axis_delta(
            deltas, self._bands(), set(_COST))
        self.assertNotEqual(verdict, "adopt")
        self.assertIn("cost not in baseline", verdict)
        self.assertIn("quality-positive", verdict)

    def test_quality_down_with_uncomparable_cost_still_rejects(self):
        """Abstaining on cost must not soften a quality regression."""
        deltas = {"path_coverage": -0.30, "graded_answer": 0.0,
                  "abstention_f1": 0.0, "token_cost": None,
                  "latency_cost": None}
        verdict = self.m._classify_five_axis_delta(
            deltas, self._bands(), set(_COST))
        self.assertIn("reject", verdict)

    def test_quality_flat_with_uncomparable_cost_is_not_zero(self):
        deltas = {ax: 0.0 for ax in _QUALITY}
        deltas.update({ax: None for ax in _COST})
        verdict = self.m._classify_five_axis_delta(
            deltas, self._bands(), set(_COST))
        self.assertNotEqual(verdict, "zero")
        self.assertIn("cost not in baseline", verdict)

    def test_full_five_axis_verdicts_unchanged(self):
        """The fix must not disturb the normal path — when every axis is
        comparable the original verdict table still applies."""
        band = self._bands(q=0.05, c=1.0)
        cases = [
            ({"path_coverage": 0.2, "graded_answer": 0.0, "abstention_f1": 0.0,
              "token_cost": -50.0, "latency_cost": 0.0}, "strong-adopt"),
            ({"path_coverage": 0.2, "graded_answer": 0.0, "abstention_f1": 0.0,
              "token_cost": 0.0, "latency_cost": 0.0}, "adopt"),
            ({"path_coverage": 0.0, "graded_answer": 0.0, "abstention_f1": 0.0,
              "token_cost": -50.0, "latency_cost": 0.0}, "efficiency-adopt"),
            ({"path_coverage": 0.2, "graded_answer": 0.0, "abstention_f1": 0.0,
              "token_cost": 50.0, "latency_cost": 0.0}, "tier-gated"),
            ({"path_coverage": -0.2, "graded_answer": 0.0, "abstention_f1": 0.0,
              "token_cost": -50.0, "latency_cost": 0.0}, "reject"),
            ({"path_coverage": 0.0, "graded_answer": 0.0, "abstention_f1": 0.0,
              "token_cost": 0.0, "latency_cost": 0.0}, "zero"),
        ]
        for deltas, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    self.m._classify_five_axis_delta(deltas, band, set()),
                    expected,
                )

    def test_unavailable_arg_is_optional(self):
        """Back-compat: the third parameter defaults, so any caller that
        predates it keeps working."""
        band = self._bands(q=0.05, c=1.0)
        deltas = {"path_coverage": 0.2, "graded_answer": 0.0,
                  "abstention_f1": 0.0, "token_cost": 0.0,
                  "latency_cost": 0.0}
        self.assertEqual(
            self.m._classify_five_axis_delta(deltas, band), "adopt")


class OnDiskBaselineTests(unittest.TestCase):
    """The live artifact is the reason this guard exists."""

    def test_committed_baseline_is_three_axis(self):
        import json
        p = REPO_ROOT / "eval" / "qvt" / "baseline_2a31b20.json"
        if not p.is_file():          # re-captured / moved: guard is moot
            self.skipTest("baseline_2a31b20.json no longer on disk")
        agg = json.loads(p.read_text(encoding="utf-8")).get("aggregate", {})
        for ax in _QUALITY:
            self.assertIn(ax, agg)
        missing = [ax for ax in _COST if ax not in agg]
        self.assertEqual(
            sorted(missing), sorted(_COST),
            "baseline now carries cost axes — if it was re-captured as "
            "qvt-baseline-v2, update this test and the report's "
            "'axes not comparable' section may no longer trigger",
        )


if __name__ == "__main__":
    unittest.main()
