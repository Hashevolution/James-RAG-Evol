"""QVT ablation matrix — layer-prerequisite capture (cell JSON v5).

CLAUDE.md rule #2 ends with a clause that is easy to read past:

    "Layer measurement prerequisites must also be confirmed — e.g.,
    AUTO_ROUTER PRs require multi-tier backend registration evidence
    (otherwise the layer is no-op and the PR's number is 'not in
    evidence,' not 'no effect')."

Until cell JSON v5 the matrix recorded that ``JAMES_AUTO_ROUTER=1`` was
set, and nothing about whether the router had anywhere to route to. On a
single-backend fleet ``core/reasoning/router.py::_legacy_backend_id``
resolves every escalation to the same backend — the router emits audit
rows and changes no answer. An L2/L5 cell measured there produces a
clean-looking null that reads as "this layer does nothing".

α-5's post-closure self-audit already hit this once
(``feedback_oracle_phrase_artifacts``: AUTO_ROUTER scored as a null in a
single-backend environment). These tests keep the second occurrence from
being silent, in the same spirit as the LRB reranker fallback counter
(#1123): make the artifact carry the fact that something did not happen.

Run:
  python -m unittest tests.test_qvt_layer_evidence
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_SCRIPT = REPO_ROOT / "scripts" / "qvt_ablation_matrix.py"


def _load_matrix_module():
    spec = importlib.util.spec_from_file_location("_qvt_matrix_under_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RouterEvidenceTests(unittest.TestCase):
    """`_router_evidence` is tri-state on purpose."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load_matrix_module()

    def _snap(self, by_tier):
        return {
            "registered": sorted({n for names in by_tier.values() for n in names}),
            "by_tier": by_tier,
            "probe": "runner-process",
            "error": None,
        }

    def test_router_off_claims_nothing(self):
        """Flag off → `None`. Not True, not False — the row makes no
        claim about a layer it did not enable."""
        ev = self.m._router_evidence(
            {"JAMES_AUTO_ROUTER": "0"},
            self._snap({"small": ["ollama_local"], "medium": [], "large": [], "cloud": []}),
        )
        self.assertFalse(ev["enabled"])
        self.assertIsNone(ev["in_evidence"])

    def test_single_populated_tier_is_not_in_evidence(self):
        """The case this file exists for: flag on, one tier, so every
        escalation resolves to the same backend."""
        ev = self.m._router_evidence(
            {"JAMES_AUTO_ROUTER": "1"},
            self._snap({"small": ["ollama_local"], "medium": [], "large": [], "cloud": []}),
        )
        self.assertTrue(ev["enabled"])
        self.assertIs(ev["in_evidence"], False)
        self.assertIn("NOT IN EVIDENCE", ev["reason"])
        self.assertEqual(ev["populated_tiers"], ["small"])

    def test_two_populated_tiers_is_in_evidence(self):
        ev = self.m._router_evidence(
            {"JAMES_AUTO_ROUTER": "1"},
            self._snap({
                "small": ["ollama_local"], "medium": [], "large": [],
                "cloud": ["claude_code_cli"],
            }),
        )
        self.assertIs(ev["in_evidence"], True)
        self.assertIn("escalation can change", ev["reason"])

    def test_truthy_flag_spellings_all_count_as_on(self):
        for raw in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(raw=raw):
                ev = self.m._router_evidence(
                    {"JAMES_AUTO_ROUTER": raw},
                    self._snap({"small": ["x"], "medium": [], "large": [], "cloud": []}),
                )
                self.assertTrue(ev["enabled"], f"{raw!r} should read as ON")

    def test_probe_failure_does_not_assert(self):
        """A broken registry probe must not be reported as evidence
        either way — silence is the honest answer."""
        ev = self.m._router_evidence(
            {"JAMES_AUTO_ROUTER": "1"},
            {"registered": None, "by_tier": None, "probe": "runner-process",
             "error": "ImportError: boom"},
        )
        self.assertIsNone(ev["in_evidence"])
        self.assertIn("probe failed", ev["reason"])

    def test_real_registry_snapshot_has_expected_shape(self):
        snap = self.m._backend_registry_snapshot()
        self.assertEqual(snap["probe"], "runner-process")
        self.assertIsNone(snap["error"], f"registry probe failed: {snap['error']}")
        self.assertIsInstance(snap["registered"], list)
        self.assertEqual(set(snap["by_tier"]), set(self.m._ROUTER_TIERS))

    def test_matrix_rows_that_enable_the_router_are_classified(self):
        """L2 and L5 are the rows with AUTO_ROUTER=1; whatever this
        machine's registry looks like, those rows must get a verdict and
        the rest must claim nothing."""
        snap = self.m._backend_registry_snapshot()
        for row, env in self.m._ROW_ENVS.items():
            ev = self.m._router_evidence(env, snap)
            with self.subTest(row=row):
                if env.get("JAMES_AUTO_ROUTER") == "1":
                    self.assertTrue(ev["enabled"])
                    self.assertIn(ev["in_evidence"], (True, False))
                else:
                    self.assertIsNone(ev["in_evidence"])


class CellSchemaTests(unittest.TestCase):
    """The evidence has to reach the artifact, not just the console."""

    @classmethod
    def setUpClass(cls):
        cls.src = _SCRIPT.read_text(encoding="utf-8")

    def test_cell_schema_is_v5(self):
        self.assertIn('"schema": "qvt-ablation-cell-v5"', self.src)

    def test_payload_carries_registry_and_evidence(self):
        self.assertIn('"backend_registry": _registry_snap', self.src)
        self.assertIn('"layer_evidence": {"auto_router": _router_ev}', self.src)

    def test_report_marks_cells_without_router_evidence(self):
        self.assertIn("router not in evidence", self.src)
        self.assertIn("AUTO_ROUTER not in evidence", self.src)

    def test_stdout_is_forced_to_utf8(self):
        """cp949 consoles killed `--help` with UnicodeEncodeError before
        it printed a single option (em dashes in the help text). A
        measurement tool the operator cannot read is not usable."""
        self.assertIn('reconfigure(encoding="utf-8")', self.src)


class HelpRunsTests(unittest.TestCase):
    """End-to-end: the CLI must be readable on this machine's console."""

    def test_help_does_not_crash(self):
        import subprocess
        env = dict(os.environ)
        # Force the failing condition rather than relying on the test
        # host's locale: without the reconfigure, this env crashes.
        env["PYTHONIOENCODING"] = "cp949"
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "--help"],
            capture_output=True, cwd=str(REPO_ROOT), env=env, timeout=180,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"--help exited {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:400]}",
        )
        self.assertIn(b"ablation matrix", proc.stdout.lower())


if __name__ == "__main__":
    unittest.main()
