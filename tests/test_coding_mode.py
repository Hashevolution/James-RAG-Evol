"""Coding mode handler — config + diagnostic guards (item #3).

User report 2026-05-08: "코딩 작업하고싶다 하면, 연결오류:
failed to fetch". The 'Failed to fetch' is browser-side — server
likely hung on the 32B qwen-coder cold-start, exceeding tunnel
timeout. v0.2.0 handle_coding caught the exception generically and
returned "코딩 답변 생성 중 오류가 발생했습니다." with no detail —
operator had no way to tell whether it was the LLM, the network,
or somewhere downstream.

This PR adds:

  (A) config.CODING_MODEL — `os.environ.get("JAMES_CODING_MODEL",
      "qwen2.5-coder:32b")`. Fixes a silent ImportError fallback in
      QwenCoderClient.__init__. Operators can swap to a lighter
      coder model via env.
  (B) log_stage events at each step (route / pick / done / error /
      fallback) so /trace/poll/ surfaces exactly where the call
      stopped. Operator-visible diagnostic.
  (C) Fallback message that names the actual exception classes
      instead of the generic "오류가 발생했습니다".

Coverage:
  - config.CODING_MODEL is defined and reads from env.
  - handle_coding emits log_stage at all four points: route /
    llm_pick / done / error.
  - Source-level: QwenCoderClient still tries `from config import
    CODING_MODEL` (back-compat with PR #18 import).

Run:
  python -m unittest tests.test_coding_mode
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ConfigCodingModelTests(unittest.TestCase):
    def setUp(self):
        self._orig = os.environ.get("JAMES_CODING_MODEL")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("JAMES_CODING_MODEL", None)
        else:
            os.environ["JAMES_CODING_MODEL"] = self._orig

    def test_config_exposes_coding_model(self):
        # config.CODING_MODEL must be importable.
        import config
        # Re-read the source to catch the hard-coded default literal.
        # v0.6.1 introduced a ``_llm_setting(...)`` wrapper for DB-first
        # resolution; the wrapper takes the historical env name and
        # default in the same positions, so we accept either the raw
        # ``os.environ.get(...)`` form or the wrapper form, as long as
        # both the env key and the documented default literal are
        # present on the CODING_MODEL line.
        src = (Path(__file__).resolve().parent.parent / "config.py").read_text(encoding="utf-8")
        self.assertRegex(
            src,
            r'CODING_MODEL\s*=\s*[^\n]*["\']JAMES_CODING_MODEL["\'][^\n]*["\']qwen2\.5-coder:32b["\']',
            "config.CODING_MODEL must reference JAMES_CODING_MODEL env "
            "with qwen2.5-coder:32b as the documented fallback default",
        )
        self.assertTrue(hasattr(config, "CODING_MODEL"),
                        "config module must export CODING_MODEL attribute")
        # Should be a non-empty string.
        self.assertIsInstance(config.CODING_MODEL, str)
        self.assertTrue(config.CODING_MODEL)


class HandleCodingDiagnosticTests(unittest.TestCase):
    """The handler must emit log_stage events that surface in
    /trace/poll/, so an operator hitting 'Failed to fetch' can see
    what actually happened (route attempt / model pick / generate
    error / fallback success-or-fail)."""

    @classmethod
    def setUpClass(cls):
        import core.reasoning.modes as modes_mod
        cls.src = inspect.getsource(modes_mod.handle_coding)

    def test_imports_log_stage(self):
        self.assertIn("from core.observability import log_stage", self.src,
                      "handle_coding must import log_stage for diagnostics")

    def test_logs_route_pick_done_phases(self):
        # Each of the four diagnostic events must appear.
        for stage_name in ("coding_route", "coding_llm_pick",
                           "coding_done", "coding_llm_error"):
            self.assertIn(f'log_stage("{stage_name}"', self.src,
                          f"missing log_stage('{stage_name}'...) — operator "
                          f"will not see this phase in /trace/poll/")

    def test_logs_fallback_success_and_error(self):
        # The fallback path must also be observable.
        for stage_name in ("coding_fallback_done", "coding_fallback_error"):
            self.assertIn(f'log_stage("{stage_name}"', self.src,
                          f"fallback path missing log_stage('{stage_name}')")

    def test_failure_message_names_exception_classes(self):
        # The catch-all answer must include the actual exception class
        # name so the user can tell qwen-cold-start vs Ollama-down vs
        # timeout etc. apart.
        self.assertIn("type(e).__name__", self.src,
                      "fallback failure message must include type(e).__name__ "
                      "(silent generic 오류 message hides the diagnostic)")
        self.assertIn("type(e2).__name__", self.src,
                      "double-failure path must also surface e2 class name")


class QwenCoderClientImportPathTests(unittest.TestCase):
    """QwenCoderClient still imports CODING_MODEL via try/except —
    after this PR the import succeeds and uses config's value
    instead of the hard-coded fallback."""

    def test_qwen_coder_imports_coding_model_from_config(self):
        src = (Path(__file__).resolve().parent.parent
               / "llm" / "providers" / "deepseek_client.py"
               ).read_text(encoding="utf-8")
        self.assertIn("from config import CODING_MODEL", src,
                      "QwenCoderClient must continue to import CODING_MODEL "
                      "from config (the import fallback in __init__ is "
                      "back-compat — should normally succeed now)")


if __name__ == "__main__":
    unittest.main()
