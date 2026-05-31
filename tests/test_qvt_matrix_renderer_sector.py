"""Contract — `--render-report` picks up α-6 sector cells.

Three invariants pinned (without invoking the live renderer, which
requires a baseline JSON + cell directory; we test the helpers
directly):

  1. `_cell_output_path("L1", "M_M", sector_cell="C_minus")`
     resolves to `qvt-ablation-cell-C_minus-M_M.json`.
  2. The renderer's sector-cells loop discovers files matching the
     sector cell naming convention.
  3. The pairwise progression list covers every adjacent step of the
     6 standard sector cells (5 transitions: minus→basic→cited→
     graph→full→routed).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "qvt_ablation_matrix.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "qvt_ablation_matrix", SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["qvt_ablation_matrix"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load_module()


class RendererSectorCellPathTests(unittest.TestCase):
    def test_sector_path_resolves_to_C_filename(self):
        with patch.object(m, "_resolve_output_dir",
                          return_value=Path("/tmp/cells")):
            p = m._cell_output_path("L1", "M_M", sector_cell="C_minus")
            self.assertEqual(p.name, "qvt-ablation-cell-C_minus-M_M.json")

    def test_row_path_stays_at_L_filename(self):
        with patch.object(m, "_resolve_output_dir",
                          return_value=Path("/tmp/cells")):
            p = m._cell_output_path("L1", "M_M")
            self.assertEqual(p.name, "qvt-ablation-cell-L1-M_M.json")


class RendererSectorCellDiscoveryTests(unittest.TestCase):
    """Pin the renderer's sector cell discovery loop reads C_*.json
    files in the cell output dir.
    """

    def test_renderer_discovers_sector_cells_alongside_row_cells(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            cell_dir = tdp / "cells"
            cell_dir.mkdir()
            # Make 1 row cell + 1 sector cell
            (cell_dir / "qvt-ablation-cell-L1-M_M.json").write_text(
                json.dumps({"schema": "qvt-ablation-cell-v2",
                            "row": "L1", "row_label": "baseline (production)",
                            "tier": "M_M", "model": "gemma4:e4b",
                            "aggregate": {
                                "path_coverage": {"median": 0.4},
                                "graded_answer": {"median": 0.3},
                                "abstention_f1": {"median": 0.6},
                                "token_cost": {"median": 1200},
                                "latency_cost": {"median": 65},
                            },
                            "sector_cell": None}),
                encoding="utf-8",
            )
            (cell_dir / "qvt-ablation-cell-C_minus-M_M.json").write_text(
                json.dumps({"schema": "qvt-ablation-cell-v3",
                            "row": "L1", "row_label": "baseline (production)",
                            "tier": "M_M", "model": "gemma4:e4b",
                            "aggregate": {
                                "path_coverage": {"median": 0.0},
                                "graded_answer": {"median": 0.1},
                                "abstention_f1": {"median": 0.2},
                                "token_cost": {"median": 800},
                                "latency_cost": {"median": 40},
                            },
                            "sector_cell": "C_minus",
                            "sector_cell_label": "pure LLM (no JAMES)"}),
                encoding="utf-8",
            )
            # Fake baseline
            ws = tdp / "workspace"
            qvt = ws / "eval" / "qvt"
            qvt.mkdir(parents=True)
            (qvt / "baseline_test.json").write_text(
                json.dumps({"git_sha": "test",
                            "captured_at": "2026-01-01T00:00:00Z",
                            "aggregate": {
                                "path_coverage": {"median": 0.4, "noise_band": 0.02},
                                "graded_answer": {"median": 0.3, "noise_band": 0.02},
                                "abstention_f1": {"median": 0.6, "noise_band": 0.05},
                                "token_cost": {"median": 1150, "noise_band": 50},
                                "latency_cost": {"median": 64, "noise_band": 5},
                            }}),
                encoding="utf-8",
            )
            with patch.object(m, "_resolve_output_dir",
                              return_value=cell_dir):
                with patch.object(m, "_read_baseline",
                                  return_value=json.loads(
                                      (qvt / "baseline_test.json").read_text(encoding="utf-8"))):
                    out = tdp / "report.md"
                    rc = m._render_report(out)
                    self.assertEqual(rc, 0)
                    body = out.read_text(encoding="utf-8")
                    self.assertIn("α-6 sector-cells", body)
                    self.assertIn("C_minus", body)
                    self.assertIn("Sector-progression", body)


class ProgressionTaxonomyTests(unittest.TestCase):
    def test_progression_covers_5_adjacent_transitions(self):
        # Each transition references two cells that exist in
        # _SECTOR_CELL_ENVS so the renderer's sc_by_id lookups can
        # potentially succeed.
        _expected = {
            ("C_minus", "C_rag-basic"),
            ("C_rag-basic", "C_rag-cited"),
            ("C_rag-cited", "C_rag-graph"),
            ("C_rag-graph", "C_rag-full"),
            ("C_rag-full", "C_rag-routed"),
        }
        # Pull progression from the renderer's literal — we can't
        # import it without invoking render; instead read the source
        # to check the literal hasn't drifted.
        src = SCRIPT.read_text(encoding="utf-8")
        for pair in _expected:
            self.assertIn(f'("{pair[0]}", "{pair[1]}"', src,
                          f"progression must include {pair}")


if __name__ == "__main__":
    unittest.main()
