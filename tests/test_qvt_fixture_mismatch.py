"""QVT matrix — a Δ across two fixture versions is not a reading.

``fixture_version`` has been written into every ablation cell since the
schema existed, and was never read. The committed artifacts are the
reason that matters:

    baseline_2a31b20.json          fixture_version: step7-v5  (2026-05-28)
    qvt-ablation-cell-L1-M_CLOUD   fixture_version: step7-v7  (2026-06-03)
    qvt-ablation-cell-C_rag-…-M_M  fixture_version: step7-v7  (2026-06-03)

step7 moved v5 → v7 by *adding* queries (q13 meta inventory, then
q14/q15/q16 narrow-scope). A v7 cell minus a v5 baseline is therefore
partly a reading of the fixture change, not of the layer the row varies.
The renderer computed and presented those deltas with a Pareto verdict
attached.

Same silent-null family as #1123 (LRB reranker fallbacks), #1136
(AUTO_ROUTER with nowhere to route) and #1137 (cost axis absent from the
baseline): the artifact looked clean and the invalidating fact was not
in it.

Run:
  python -m unittest tests.test_qvt_fixture_mismatch
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_SCRIPT = REPO_ROOT / "scripts" / "qvt_ablation_matrix.py"
_BASELINE = REPO_ROOT / "eval" / "qvt" / "baseline_2a31b20.json"
_CELL_DIR = REPO_ROOT / "reports" / "research-runs" / "qvt-ablation-cells"


def _load():
    spec = importlib.util.spec_from_file_location("_qvt_matrix_fixture", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FixtureMismatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_same_version_is_comparable(self):
        self.assertIsNone(self.m._fixture_mismatch(
            {"fixture_version": "step7-v7"},
            {"fixture_version": "step7-v7"},
        ))

    def test_different_version_is_reported(self):
        gap = self.m._fixture_mismatch(
            {"fixture_version": "step7-v7"},
            {"fixture_version": "step7-v5"},
        )
        self.assertIsNotNone(gap)
        self.assertIn("step7-v5", gap)
        self.assertIn("step7-v7", gap)

    def test_unknown_version_is_not_a_mismatch(self):
        """Absence of the field is not evidence of a mismatch — pre-v3
        cells predate it, and guessing would be its own fabrication."""
        for cell, base in (
            ({}, {"fixture_version": "step7-v7"}),
            ({"fixture_version": "step7-v7"}, {}),
            ({"fixture_version": None}, {"fixture_version": "step7-v7"}),
            ({}, {}),
        ):
            with self.subTest(cell=cell, base=base):
                self.assertIsNone(self.m._fixture_mismatch(cell, base))


class CommittedArtifactTests(unittest.TestCase):
    """The live artifacts this guard was written for."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_committed_cells_are_detected_as_not_comparable(self):
        if not _BASELINE.is_file():
            self.skipTest("baseline_2a31b20.json no longer on disk")
        cells = sorted(_CELL_DIR.glob("*.json"))
        if not cells:
            self.skipTest("no committed ablation cells")
        baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
        detected = 0
        for p in cells:
            cell = json.loads(p.read_text(encoding="utf-8"))
            if self.m._fixture_mismatch(cell, baseline):
                detected += 1
        self.assertEqual(
            detected, len(cells),
            "every committed cell is step7-v7 against a step7-v5 baseline; "
            "if the baseline was re-captured on the current fixture this "
            "test should be updated rather than deleted",
        )

    def test_baseline_and_cells_disagree_on_fixture_version(self):
        """Pins the specific disagreement, so a future re-capture that
        resolves it fails loudly here instead of drifting."""
        if not _BASELINE.is_file():
            self.skipTest("baseline_2a31b20.json no longer on disk")
        baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(baseline.get("fixture_version"), "step7-v5")


class RenderGuardTests(unittest.TestCase):
    """The verdict column must refuse, not qualify."""

    @classmethod
    def setUpClass(cls):
        cls.src = _SCRIPT.read_text(encoding="utf-8")

    def test_verdict_is_replaced_not_annotated(self):
        self.assertIn('verdict = f"not comparable ({_fx_gap})"', self.src)
        self.assertIn('verdict_sc = f"not comparable ({_fx_sc})"', self.src)
        self.assertIn('verdict_qt = f"not comparable ({_fx_qt})"', self.src)

    def test_report_has_a_mismatch_section(self):
        self.assertIn("fixture mismatch", self.src)

    def test_gap_is_computed_over_row_and_sector_cells(self):
        """The row table renders its warning before the sector table is
        walked, so the gap list has to be built up front or the count
        under-reports."""
        self.assertIn("for c in (cells + sector_cells)", self.src)


if __name__ == "__main__":
    unittest.main()
