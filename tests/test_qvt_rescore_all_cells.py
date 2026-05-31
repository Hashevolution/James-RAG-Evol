"""Contract — `scripts/qvt_rescore_all_cells.py` suite-parse + cell
classification.

These tests pin the suite-parser regex + the classifier logic against
the QQ bug fingerprint so a future refactor cannot silently mis-route
the wrapper away from cells that need rescoring.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "qvt_rescore_all_cells.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "qvt_rescore_all_cells", SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["qvt_rescore_all_cells"] = mod
    spec.loader.exec_module(mod)
    return mod


qra = _load_module()


class SuiteParserTests(unittest.TestCase):
    def test_step7_parsed_despite_digit(self):
        self.assertEqual(
            qra._cell_bench_suite("reports/bench_nogit_step7_20260507_194228.json"),
            "step7",
        )

    def test_multihop_rag_parsed(self):
        self.assertEqual(
            qra._cell_bench_suite("reports/bench_87ed176_multihop_rag_20260531_120746.json"),
            "multihop_rag",
        )

    def test_underscore_in_sha_handled(self):
        # sha is whatever is between bench_ and the next _. We assume
        # SHAs don't contain underscores (git short shas don't).
        self.assertEqual(
            qra._cell_bench_suite("bench_abc1234_step7_20260101_010101.json"),
            "step7",
        )

    def test_empty_returns_none(self):
        self.assertIsNone(qra._cell_bench_suite(""))

    def test_malformed_returns_none(self):
        self.assertIsNone(qra._cell_bench_suite("not_a_bench_file.txt"))


class ClassifyCellTests(unittest.TestCase):
    def _write_cell(self, tmpdir: Path, bench_output: str) -> Path:
        cell = tmpdir / "qvt-ablation-cell-L1-M_M.json"
        cell.write_text(
            json.dumps({"runs": [{"bench_output": bench_output}]}),
            encoding="utf-8",
        )
        return cell

    def test_ok_when_bench_suite_matches_expected(self):
        with tempfile.TemporaryDirectory() as td:
            cell = self._write_cell(
                Path(td),
                "reports/bench_x_multihop_rag_20260531_120746.json",
            )
            status, _ = qra._classify_cell(cell, "multihop_rag")
            self.assertEqual(status, "ok")

    def test_needs_when_bench_suite_is_stale_step7(self):
        # QQ bug fingerprint — cell points at a step7 bench while the
        # cycle is multihop_rag.
        with tempfile.TemporaryDirectory() as td:
            cell = self._write_cell(
                Path(td),
                "reports/bench_nogit_step7_20260507_194228.json",
            )
            status, _ = qra._classify_cell(cell, "multihop_rag")
            self.assertEqual(status, "needs")

    def test_empty_when_no_runs(self):
        with tempfile.TemporaryDirectory() as td:
            cell = Path(td) / "qvt-ablation-cell-X.json"
            cell.write_text(json.dumps({"runs": []}), encoding="utf-8")
            status, _ = qra._classify_cell(cell, "multihop_rag")
            self.assertEqual(status, "empty")

    def test_empty_when_runs_missing_bench(self):
        with tempfile.TemporaryDirectory() as td:
            cell = Path(td) / "qvt-ablation-cell-X.json"
            cell.write_text(json.dumps({"runs": [{}]}), encoding="utf-8")
            status, _ = qra._classify_cell(cell, "multihop_rag")
            self.assertEqual(status, "empty")


if __name__ == "__main__":
    unittest.main()
