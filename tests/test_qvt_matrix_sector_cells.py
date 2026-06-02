"""Contract — `scripts/qvt_ablation_matrix.py --sector-cells` extension.

Pins:
  1. `_SECTOR_CELL_ENVS` has the 6 standard α-6 cells (C_minus,
     C_rag-basic, C_rag-cited, C_rag-graph, C_rag-full, C_rag-routed).
  2. `_cell_env(row="L1", tier="M_M", sector_cell="C_minus")` overlays
     the sector flag dict on top of L1's row env. All 5 sector
     disable-flags + S3 ENABLE flags get set to disable values for
     C_minus.
  3. C_rag-graph keeps S3 (ENTITY_ANCHOR + QUERY_REWRITE) ON (because
     C_rag-graph is "+ graph + preprocessing").
  4. `_cell_output_path` produces `qvt-ablation-cell-C_minus-M_M.json`
     when sector_cell is set, vs `qvt-ablation-cell-L1-M_M.json` when
     row-only.
  5. Unknown sector_cell raises ValueError.
"""
from __future__ import annotations

import importlib.util
import os
import sys
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


class SectorCellsRegistryTests(unittest.TestCase):
    def test_seven_standard_sector_cells_exist(self):
        # α-8 Phase B added C_rag-ontology between C_rag-graph and C_rag-full.
        expected = {"C_minus", "C_rag-basic", "C_rag-cited",
                    "C_rag-graph", "C_rag-ontology", "C_rag-full",
                    "C_rag-routed"}
        self.assertEqual(set(m._SECTOR_CELL_ENVS.keys()), expected)

    def test_each_sector_cell_has_a_label(self):
        for cell in m._SECTOR_CELL_ENVS:
            self.assertIn(cell, m._SECTOR_CELL_LABELS)

    def test_c_rag_graph_disables_typed_filter(self):
        """C_rag-graph is the α-7 (pre-α-8) graph baseline — typed filter MUST be off."""
        self.assertEqual(
            m._SECTOR_CELL_ENVS["C_rag-graph"].get("JAMES_DISABLE_TYPED_FILTER"),
            "1",
        )

    def test_c_rag_ontology_does_not_set_disable_typed_filter(self):
        """C_rag-ontology is the α-8 cell — typed filter ON (flag intentionally absent)."""
        self.assertNotIn(
            "JAMES_DISABLE_TYPED_FILTER",
            m._SECTOR_CELL_ENVS["C_rag-ontology"],
        )


class CellEnvOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        # Clean any env leaks.
        for env in ("JAMES_DISABLE_RAG_RETRIEVAL", "JAMES_DISABLE_GRAPH",
                    "JAMES_DISABLE_SOURCES_FIELD", "JAMES_DISABLE_ABSTENTION",
                    "JAMES_DISABLE_COGNITIVE_STAGES",
                    "JAMES_ENABLE_ENTITY_ANCHOR", "JAMES_ENABLE_QUERY_REWRITE"):
            os.environ.pop(env, None)

    def test_c_minus_disables_all_sectors_including_s3(self):
        env = m._cell_env("L1", "M_M", sector_cell="C_minus")
        # S1, S2, S4, S5, S6 disable-flags all "1"
        for flag in ("JAMES_DISABLE_RAG_RETRIEVAL", "JAMES_DISABLE_GRAPH",
                     "JAMES_DISABLE_SOURCES_FIELD", "JAMES_DISABLE_ABSTENTION",
                     "JAMES_DISABLE_COGNITIVE_STAGES"):
            self.assertEqual(env[flag], "1",
                             f"C_minus must disable {flag}")
        # S3 also off (ENTITY_ANCHOR + QUERY_REWRITE explicitly set to "0")
        self.assertEqual(env["JAMES_ENABLE_ENTITY_ANCHOR"], "0")
        self.assertEqual(env["JAMES_ENABLE_QUERY_REWRITE"], "0")

    def test_c_rag_basic_disables_all_except_s1(self):
        env = m._cell_env("L1", "M_M", sector_cell="C_rag-basic")
        # S2, S4, S5, S6 disabled; S1 stays default (NO disable flag).
        self.assertNotIn("JAMES_DISABLE_RAG_RETRIEVAL", env)
        for flag in ("JAMES_DISABLE_GRAPH", "JAMES_DISABLE_SOURCES_FIELD",
                     "JAMES_DISABLE_ABSTENTION", "JAMES_DISABLE_COGNITIVE_STAGES"):
            self.assertEqual(env[flag], "1")
        # S3 off
        self.assertEqual(env["JAMES_ENABLE_ENTITY_ANCHOR"], "0")

    def test_c_rag_graph_keeps_s3_on(self):
        env = m._cell_env("L1", "M_M", sector_cell="C_rag-graph")
        # S3 must stay ON (L1 row default = "1")
        self.assertEqual(env["JAMES_ENABLE_ENTITY_ANCHOR"], "1")
        self.assertEqual(env["JAMES_ENABLE_QUERY_REWRITE"], "1")
        # S5 + S6 still disabled
        self.assertEqual(env["JAMES_DISABLE_ABSTENTION"], "1")
        self.assertEqual(env["JAMES_DISABLE_COGNITIVE_STAGES"], "1")
        # S1 + S2 + S4 NOT disabled
        self.assertNotIn("JAMES_DISABLE_RAG_RETRIEVAL", env)
        self.assertNotIn("JAMES_DISABLE_GRAPH", env)
        self.assertNotIn("JAMES_DISABLE_SOURCES_FIELD", env)

    def test_unknown_sector_cell_raises(self):
        with self.assertRaises(ValueError):
            m._cell_env("L1", "M_M", sector_cell="C_does_not_exist")

    def test_sector_cell_none_is_pure_row_env(self):
        env_with = m._cell_env("L1", "M_M", sector_cell=None)
        env_without = m._cell_env("L1", "M_M")
        # The two must produce identical envs (modulo unrelated OS vars).
        for key in m._ROW_ENVS["L1"]:
            self.assertEqual(env_with[key], env_without[key])


class CellOutputPathTests(unittest.TestCase):
    def test_row_only_path(self):
        with patch.object(m, "_resolve_output_dir",
                          return_value=Path("/tmp/cells")):
            p = m._cell_output_path("L1", "M_M")
            self.assertTrue(p.name.endswith("qvt-ablation-cell-L1-M_M.json"))

    def test_sector_cell_path(self):
        with patch.object(m, "_resolve_output_dir",
                          return_value=Path("/tmp/cells")):
            p = m._cell_output_path("L1", "M_M", sector_cell="C_minus")
            self.assertTrue(p.name.endswith(
                "qvt-ablation-cell-C_minus-M_M.json"))

    def test_sector_cell_with_sanity(self):
        with patch.object(m, "_resolve_output_dir",
                          return_value=Path("/tmp/cells")):
            p = m._cell_output_path("L1", "M_M",
                                    sanity_think_on=True,
                                    sector_cell="C_minus")
            self.assertTrue(p.name.endswith(
                "qvt-ablation-cell-C_minus-M_M-thinkON.json"))


if __name__ == "__main__":
    unittest.main()
