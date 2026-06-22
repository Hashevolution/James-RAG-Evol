"""LOCK: time-travel reconstruct stays isolated from the live filter.

The v0.6.1 live-consistency triad (#1021/#1023/#1024) made the *current-
state* query path honor lifecycle status + validity via a now-based
filter (`relation_is_live`) in `expand_dynamic` / `build_graph_context_str`
/ `compute_graph_score`. The `reconstruct_*_at` time-travel path must NOT
use any of those — it is a pure event-replay (LOCK 4) that projects a
*historical* snapshot, where a now-expired edge may still be valid. If
reconstruct routed through the now-based filter, a historically-valid-
then-expired edge would be wrongly dropped from a past snapshot.

iter4 of the measurement/fix loop verified (by source absence) that
core/lifecycle/* references none of those live functions. This test pins
that isolation so a future refactor can't silently break time-travel.

Run: python -m unittest tests.test_reconstruct_isolation
"""
from __future__ import annotations

import glob
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The live, now-based functions reconstruct must never call.
_LIVE_FNS = (
    "relation_is_live",
    "expand_dynamic",
    "build_graph_context_str",
    "compute_graph_score",
)


class ReconstructIsolationTests(unittest.TestCase):
    def test_lifecycle_replay_does_not_use_live_now_filter(self):
        offenders = []
        for f in glob.glob(str(ROOT / "core" / "lifecycle" / "**" / "*.py"),
                           recursive=True):
            src = Path(f).read_text(encoding="utf-8")
            for fn in _LIVE_FNS:
                if fn in src:
                    offenders.append((os.path.relpath(f, ROOT), fn))
        self.assertEqual(
            offenders, [],
            "reconstruct/time-travel must stay isolated from the live "
            f"now-based filter, found: {offenders}")

    def test_reconstruct_is_pure_event_replay(self):
        # The primitive must not import the graph engine (its pure-replay
        # contract reads only the audit_log).
        src = (ROOT / "core" / "lifecycle" / "replay_graph" /
               "primitives.py").read_text(encoding="utf-8")
        self.assertNotIn("graph_engine", src)
        self.assertIn("reconstruct_graph_at", src)


if __name__ == "__main__":
    unittest.main()
