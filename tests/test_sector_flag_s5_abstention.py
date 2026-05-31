"""Contract — `JAMES_DISABLE_ABSTENTION` env flag (α-6 sector S5).

Three invariants pinned (testing the env-gate expression directly
rather than running the full synth path which requires a live LLM):

  1. Flag unset (default) → the retry-no-info pass condition
     evaluates True for a "자료에 없음" prefix answer.
  2. Flag set to "1" → the retry-no-info pass condition evaluates
     False even for a "자료에 없음" prefix answer (the early
     refusal stands; no softening retry).
  3. Flag set to "1" with a non-refusal answer is a no-op — only
     refusal-prefix answers were touched by the retry pass anyway.

The full synth-side behavior (model call, retry prompt assembly)
is exercised by the live integration tests; this contract test
pins the gate logic directly.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _gate_condition(answer: str) -> bool:
    """Mirror the gate at core/reasoning/pipeline_synth.py:237-241."""
    _no_data = ("자료에 없음. 관련된", "답변 생성에 실패",
                "LLM 응답 생성 중 오류")
    _s5_disabled = os.environ.get("JAMES_DISABLE_ABSTENTION") == "1"
    return (not _s5_disabled and answer
            and any(answer.startswith(p) for p in _no_data))


class S5AbstentionFlagContract(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("JAMES_DISABLE_ABSTENTION", None)

    def tearDown(self) -> None:
        os.environ.pop("JAMES_DISABLE_ABSTENTION", None)

    def test_flag_unset_retry_triggers_on_refusal_prefix(self):
        self.assertTrue(_gate_condition(
            "자료에 없음. 관련된 정보를 찾을 수 없습니다."))
        self.assertTrue(_gate_condition("답변 생성에 실패했습니다."))

    def test_flag_set_skips_retry_on_refusal_prefix(self):
        with patch.dict(os.environ,
                        {"JAMES_DISABLE_ABSTENTION": "1"}, clear=False):
            self.assertFalse(_gate_condition(
                "자료에 없음. 관련된 정보를 찾을 수 없습니다."))
            self.assertFalse(_gate_condition("답변 생성에 실패했습니다."))

    def test_flag_set_irrelevant_for_normal_answers(self):
        # Both modes should evaluate False for normal substantive
        # answers — the retry was always refusal-prefix-only.
        normal = "The company is Amazon. Q3 revenue grew 12%."
        self.assertFalse(_gate_condition(normal))
        with patch.dict(os.environ,
                        {"JAMES_DISABLE_ABSTENTION": "1"}, clear=False):
            self.assertFalse(_gate_condition(normal))

    def test_flag_toggle_back_and_forth(self):
        prefix_ans = "자료에 없음. 관련된 자료가 없습니다."
        self.assertTrue(_gate_condition(prefix_ans))
        with patch.dict(os.environ,
                        {"JAMES_DISABLE_ABSTENTION": "1"}, clear=False):
            self.assertFalse(_gate_condition(prefix_ans))
        # Re-check after exiting patch context.
        self.assertTrue(_gate_condition(prefix_ans))


if __name__ == "__main__":
    unittest.main()
