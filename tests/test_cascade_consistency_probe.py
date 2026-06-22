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
        from scripts.research import cascade_consistency_probe as probe
        rc = probe.main()
        self.assertEqual(rc, 0)
        report = ROOT / "reports" / "research-runs" / "cascade-consistency-probe.json"
        self.assertTrue(report.exists())
        data = json.loads(report.read_text(encoding="utf-8"))
        filt = data["metrics"]["filtered_fix"]
        # the proposed status-aware filter: zero leakage, no active loss.
        self.assertEqual(filt["invalidated_leakage"], 0)
        self.assertEqual(filt["active_dropped"], 0)
        self.assertEqual(filt["active_retention"], 1.0)

    def test_filter_predicate_excludes_deactivated(self):
        from scripts.research.cascade_consistency_probe import _is_active
        self.assertTrue(_is_active({"status": {"active": True}, "mutation_type": "active"}))
        self.assertFalse(_is_active({"status": {"active": False}, "mutation_type": "invalidated"}))
        self.assertFalse(_is_active({"mutation_type": "superseded"}))
        self.assertFalse(_is_active({"mutation_type": "expired"}))
        self.assertTrue(_is_active({}))  # untagged legacy edge = active


if __name__ == "__main__":
    unittest.main()
