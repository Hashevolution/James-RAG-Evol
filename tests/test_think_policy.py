"""Tests for `core/reasoning/think_policy.py` (A2 — A3-feed per-stage think policy).

Behaviour pinned:
- Flag OFF (default) → every stage returns None (no override, byte-identical
  to pre-A2 request shape).
- Flag ON → A3 safe-list stages return False; unknown stages return None.
- Model gate (`is_thinking_capable`) recognises gemma4:e4b only; other
  panel models in §16.2 (qwen2.5:7b / gemma3:12b / llama3.1:8b / gemma2:2b
  / deepseek-v2:16b) return False so the call site suppresses the `think`
  field on their request body (avoiding the HTTP 400 in §16.7).
"""
from __future__ import annotations

import importlib
import os
import unittest


class ThinkPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        # Always start from a known-clean env per test.
        self._prev = os.environ.pop("JAMES_GEMMA4_E4B_THINK_OFF", None)
        import core.reasoning.think_policy as tp
        self.tp = importlib.reload(tp)

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("JAMES_GEMMA4_E4B_THINK_OFF", None)
        else:
            os.environ["JAMES_GEMMA4_E4B_THINK_OFF"] = self._prev
        importlib.reload(self.tp)

    # ─── Flag gating ────────────────────────────────────────────

    def test_flag_off_default_returns_none_for_all_stages(self) -> None:
        for stage in ("planner", "reflect", "verify", "synth",
                      "query_rewriter", "unknown_stage"):
            with self.subTest(stage=stage):
                self.assertIsNone(self.tp.think_for_stage(stage))

    def test_flag_on_returns_false_for_safe_list_stages(self) -> None:
        os.environ["JAMES_GEMMA4_E4B_THINK_OFF"] = "1"
        tp = importlib.reload(self.tp)
        for stage in ("planner", "reflect", "verify", "synth",
                      "query_rewriter"):
            with self.subTest(stage=stage):
                self.assertIs(tp.think_for_stage(stage), False)

    def test_flag_on_returns_none_for_unknown_stage(self) -> None:
        os.environ["JAMES_GEMMA4_E4B_THINK_OFF"] = "1"
        tp = importlib.reload(self.tp)
        self.assertIsNone(tp.think_for_stage("unknown"))
        self.assertIsNone(tp.think_for_stage(""))

    def test_flag_accepts_truthy_string_variants(self) -> None:
        for raw in ("1", "true", "TRUE", "yes", "On"):
            os.environ["JAMES_GEMMA4_E4B_THINK_OFF"] = raw
            tp = importlib.reload(self.tp)
            with self.subTest(raw=raw):
                self.assertIs(tp.think_for_stage("planner"), False)

    def test_flag_rejects_falsy_string_variants(self) -> None:
        for raw in ("0", "false", "no", "off", "", "anything-else"):
            os.environ["JAMES_GEMMA4_E4B_THINK_OFF"] = raw
            tp = importlib.reload(self.tp)
            with self.subTest(raw=raw):
                self.assertIsNone(tp.think_for_stage("planner"))

    # ─── Model gating ───────────────────────────────────────────

    def test_thinking_capable_recognises_gemma4_e4b(self) -> None:
        self.assertTrue(self.tp.is_thinking_capable("gemma4:e4b"))
        # Family is matched by prefix, so future e4b variants land.
        self.assertTrue(self.tp.is_thinking_capable("gemma4:e4b-q4"))

    def test_thinking_capable_rejects_non_thinking_panel_models(self) -> None:
        # §16.2 panel — only gemma4:e4b declares the thinking capability.
        for tag in ("gemma3:12b", "gemma2:2b", "qwen2.5:7b",
                    "qwen2.5-coder:7b", "llama3.1:8b", "deepseek-v2:16b"):
            with self.subTest(tag=tag):
                self.assertFalse(self.tp.is_thinking_capable(tag))

    def test_thinking_capable_handles_empty_model(self) -> None:
        self.assertFalse(self.tp.is_thinking_capable(""))
        self.assertFalse(self.tp.is_thinking_capable(None))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
