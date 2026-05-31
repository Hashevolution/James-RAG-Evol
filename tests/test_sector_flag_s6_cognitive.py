"""Contract — `JAMES_DISABLE_COGNITIVE_STAGES` env flag (α-6 sector S6).

Master kill-switch that forces ALL cognitive stages
(planner / reflect / verify / fact_check) to OFF regardless of their
per-stage env flags.

Four invariants pinned (one per stage):
  1. planner `_enabled()` returns False when S6 disabled, even if
     JAMES_ENABLE_PLANNER=1.
  2. reflect `_enabled()` same.
  3. verify `_enabled()` returns False when S6 disabled, even though
     verify's per-stage default is ON (JAMES_DISABLE_VERIFY != "1").
  4. fact_check is gated through verify._enabled() (chain pattern),
     so it inherits the S6 master gate automatically.

The S6 flag is the C_rag-graph cell's natural exclusion (no
cognitive stages on top of the graph layer).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import the private gates so the test pins the actual gate
# expression, not a re-implementation.
from core.reasoning.planner import _enabled as planner_enabled  # noqa: E402
from core.reasoning.reflect import _enabled as reflect_enabled  # noqa: E402
from core.reasoning.verify import (  # noqa: E402
    _enabled as verify_enabled,
    _fact_check_enabled,
)


class S6CognitiveFlagContract(unittest.TestCase):
    def setUp(self) -> None:
        for env in ("JAMES_DISABLE_COGNITIVE_STAGES",
                    "JAMES_ENABLE_PLANNER",
                    "JAMES_ENABLE_REFLECT",
                    "JAMES_DISABLE_VERIFY",
                    "JAMES_ENABLE_FACT_CHECK"):
            os.environ.pop(env, None)

    def tearDown(self) -> None:
        for env in ("JAMES_DISABLE_COGNITIVE_STAGES",
                    "JAMES_ENABLE_PLANNER",
                    "JAMES_ENABLE_REFLECT",
                    "JAMES_DISABLE_VERIFY",
                    "JAMES_ENABLE_FACT_CHECK"):
            os.environ.pop(env, None)

    def test_planner_off_when_master_disabled(self):
        with patch.dict(os.environ,
                        {"JAMES_ENABLE_PLANNER": "1",
                         "JAMES_DISABLE_COGNITIVE_STAGES": "1"}):
            self.assertFalse(planner_enabled())

    def test_planner_on_when_master_unset(self):
        with patch.dict(os.environ, {"JAMES_ENABLE_PLANNER": "1"}):
            self.assertTrue(planner_enabled())

    def test_reflect_off_when_master_disabled(self):
        with patch.dict(os.environ,
                        {"JAMES_ENABLE_REFLECT": "1",
                         "JAMES_DISABLE_COGNITIVE_STAGES": "1"}):
            self.assertFalse(reflect_enabled())

    def test_reflect_on_when_master_unset(self):
        with patch.dict(os.environ, {"JAMES_ENABLE_REFLECT": "1"}):
            self.assertTrue(reflect_enabled())

    def test_verify_off_when_master_disabled(self):
        # verify's default is ON (DISABLE_VERIFY != "1"); master
        # still forces it OFF.
        with patch.dict(os.environ,
                        {"JAMES_DISABLE_COGNITIVE_STAGES": "1"}):
            self.assertFalse(verify_enabled())

    def test_verify_on_by_default_when_master_unset(self):
        self.assertTrue(verify_enabled())

    def test_fact_check_inherits_master_gate_via_verify(self):
        # fact_check chains through verify._enabled() so master
        # disable cascades.
        with patch.dict(os.environ,
                        {"JAMES_ENABLE_FACT_CHECK": "1",
                         "JAMES_DISABLE_COGNITIVE_STAGES": "1"}):
            self.assertFalse(_fact_check_enabled())


if __name__ == "__main__":
    unittest.main()
