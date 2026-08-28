"""Lock-test for the cascade reasoning-consistency probe.

Pins the measurement finding's *stable* half: the status-aware filter
(the proposed traversal fix) removes ALL leakage of lifecycle-deactivated
relations with FULL active-relation retention. The CURRENT-arm leakage
(today's traversal ignores status) is recorded by the probe but not
hard-asserted here — once a real traversal status-filter lands, the
CURRENT arm will stop leaking, and that is the intended outcome, not a
test break.

Run: python -m unittest tests.test_cascade_consistency_probe
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class CascadeProbeTests(unittest.TestCase):
    def test_probe_runs_and_filter_is_clean(self):
        # [2026-08-26] Was writing to the committed report under
        # reports/research-runs/, so every test run dirtied the working
        # tree — and the committed copy is the record of a past
        # measurement (it still holds the pre-fix numbers, leakage=3,
        # 1/4 consistent, generated on Windows), not a scratch file for
        # a test to overwrite. Write to a temp path instead.
        import tempfile
        from pathlib import Path as _P
        from scripts.research import cascade_consistency_probe as probe
        with tempfile.TemporaryDirectory() as td:
            report = _P(td) / "probe.json"
            rc = probe.main(out_path=report)
            self.assertEqual(rc, 0)
            self.assertTrue(report.exists())
            data = json.loads(report.read_text(encoding="utf-8"))
            filt = data["metrics"]["filtered_fix"]
            # status-aware filter: zero leakage, no active loss.
            self.assertEqual(filt["invalidated_leakage"], 0)
            self.assertEqual(filt["active_dropped"], 0)
            self.assertEqual(filt["active_retention"], 1.0)

    def test_probe_does_not_touch_the_committed_report(self):
        """Guard for the above: the default path still works, but a test
        must never be the thing that rewrites a tracked measurement."""
        import inspect
        from scripts.research import cascade_consistency_probe as probe
        sig = inspect.signature(probe.main)
        self.assertIn("out_path", sig.parameters,
            "probe.main must accept out_path so tests can redirect it")
        self.assertIsNone(sig.parameters["out_path"].default,
            "out_path must default to None (→ the committed report) so "
            "running the script by hand is unchanged")

    def test_filter_predicate_excludes_deactivated(self):
        from scripts.research.cascade_consistency_probe import _is_active
        self.assertTrue(_is_active({"status": {"active": True}, "mutation_type": "active"}))
        self.assertFalse(_is_active({"status": {"active": False}, "mutation_type": "invalidated"}))
        self.assertFalse(_is_active({"mutation_type": "superseded"}))
        self.assertFalse(_is_active({"mutation_type": "expired"}))
        self.assertTrue(_is_active({}))  # untagged legacy edge = active


if __name__ == "__main__":
    unittest.main()
