"""v0.6 — Graph-RAG synthesis Step 2 driver smoke tests.

Validates the CLI shape + invocation composition of
``scripts/research/graph_rag_synth_step2_cross_model.py`` WITHOUT
launching the multi-hour measurement.

Coverage:

  * Default invocation argv: tiers=M_S,M_L / sector cells=basic+graph+
    ontology / suite=multihop_rag / n-runs=3
  * --dry-run prints the exact subprocess invocation + exits 0
  * --tiers M_S only launches M_S
  * Empty --tiers / empty --sector-cells returns exit code 2
  * JAMES_WORKSPACE is pinned to the synthesis-doc canonical path

The intent is to lock the driver's API surface so a future PR can't
silently change the Step 2 scope (e.g. drop typed-filter from the
cells, or substitute a different fixture) without an explicit
review of these tests.

Run:
  python -m unittest tests.test_v06_graph_rag_step2_driver
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "scripts" / "research" / "graph_rag_synth_step2_cross_model.py"


class DriverShapeTests(unittest.TestCase):
    def test_driver_file_exists(self):
        self.assertTrue(DRIVER.exists(),
                        f"driver script missing: {DRIVER}")

    def test_module_imports_cleanly(self):
        # The driver should import without invoking any subprocess.
        sys.path.insert(0, str(REPO_ROOT / "scripts" / "research"))
        try:
            import importlib
            mod = importlib.import_module("graph_rag_synth_step2_cross_model")
            self.assertTrue(callable(mod.main))
            self.assertTrue(callable(mod._build_subprocess_argv))
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts" / "research"))

    def test_default_scope_constants(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts" / "research"))
        try:
            import importlib
            mod = importlib.import_module("graph_rag_synth_step2_cross_model")
            # Lock the Step 2 scope so a future PR can't silently
            # widen / narrow it without reviewing this test.
            self.assertEqual(
                mod._STEP_2_SECTOR_CELLS,
                ("C_rag-basic", "C_rag-graph", "C_rag-ontology"),
            )
            self.assertEqual(mod._STEP_2_TIERS_DEFAULT, ("M_S", "M_L"))
            self.assertEqual(mod._STEP_2_SUITE, "multihop_rag")
            self.assertEqual(mod._STEP_2_N_RUNS, 3)
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts" / "research"))


class DriverArgvCompositionTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts" / "research"))
        import importlib
        self.mod = importlib.import_module(
            "graph_rag_synth_step2_cross_model"
        )

    def tearDown(self):
        try:
            sys.path.remove(str(REPO_ROOT / "scripts" / "research"))
        except ValueError:
            pass

    def test_default_argv_includes_pinned_scope(self):
        argv = self.mod._build_subprocess_argv(
            tiers=("M_S", "M_L"),
            sector_cells=("C_rag-basic", "C_rag-graph", "C_rag-ontology"),
            suite="multihop_rag",
            n_runs=3,
        )
        # The runner path must point at the canonical
        # qvt_ablation_matrix script.
        self.assertTrue(
            any("qvt_ablation_matrix.py" in str(a) for a in argv),
            f"missing qvt_ablation_matrix.py in argv: {argv}",
        )
        # The pinned-scope arguments must all appear.
        self.assertIn("--suite", argv)
        self.assertIn("multihop_rag", argv)
        self.assertIn("--tiers", argv)
        self.assertIn("M_S,M_L", argv)
        self.assertIn("--sector-cells", argv)
        self.assertIn("C_rag-basic,C_rag-graph,C_rag-ontology", argv)
        self.assertIn("--n-runs", argv)
        self.assertIn("3", argv)

    def test_single_tier_argv(self):
        argv = self.mod._build_subprocess_argv(
            tiers=("M_S",),
            sector_cells=("C_rag-graph",),
            suite="multihop_rag",
            n_runs=3,
        )
        self.assertIn("M_S", argv)
        self.assertIn("C_rag-graph", argv)

    def test_workspace_pinned_to_hotpot_eval(self):
        env = self.mod._build_env("workspaces/hotpot_eval")
        self.assertIn("JAMES_WORKSPACE", env)
        self.assertTrue(
            env["JAMES_WORKSPACE"].endswith("workspaces/hotpot_eval") or
            env["JAMES_WORKSPACE"].endswith("workspaces\\hotpot_eval"),
            f"unexpected JAMES_WORKSPACE: {env['JAMES_WORKSPACE']}",
        )


class DriverDryRunTests(unittest.TestCase):
    def _run_driver(self, args):
        return subprocess.run(
            [sys.executable, str(DRIVER), *args],
            capture_output=True, text=True,
        )

    def test_dry_run_succeeds(self):
        result = self._run_driver(["--dry-run"])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dry_run_prints_invocation(self):
        result = self._run_driver(["--dry-run"])
        self.assertIn("qvt_ablation_matrix.py", result.stdout)
        self.assertIn("--tiers", result.stdout)
        self.assertIn("M_S,M_L", result.stdout)
        self.assertIn("--sector-cells", result.stdout)
        self.assertIn("C_rag-basic,C_rag-graph,C_rag-ontology", result.stdout)
        self.assertIn("JAMES_WORKSPACE", result.stdout)

    def test_dry_run_with_single_tier(self):
        result = self._run_driver(["--dry-run", "--tiers", "M_S"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("M_S", result.stdout)
        self.assertNotIn("M_S,M_L", result.stdout)

    def test_empty_tiers_returns_2(self):
        result = self._run_driver(["--tiers", "", "--dry-run"])
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_empty_sector_cells_returns_2(self):
        result = self._run_driver(
            ["--sector-cells", "", "--dry-run"]
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
