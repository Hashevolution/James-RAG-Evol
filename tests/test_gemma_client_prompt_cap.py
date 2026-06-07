"""Cycle γ Phase B smoke #2 — env-configurable Gemma prompt cap.

The cap default (4000) is the historical Phase-4 behaviour and is
pinned here so a future refactor cannot regress it silently. The
env-var override path is the cycle γ wiring; tested via
``_resolve_max_prompt_len`` directly so no HTTP / Ollama dependency
is needed.

Self-eval trap note (memory ``feedback_self_evaluation_trap``):
this test exercises the cap-resolution helper, not the cap *value*
as a quality claim. The publishable claim is "byte-identical default,
configurable for measurement runs" — not "4000 is the right cap".
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ResolveMaxPromptLenTests(unittest.TestCase):
    """Pins for ``core.gemma_client._resolve_max_prompt_len``."""

    def setUp(self):
        # Snapshot + clear the env var so each test starts from a
        # known baseline regardless of how the suite is invoked.
        self._snapshot = os.environ.pop("JAMES_GEMMA_MAX_PROMPT_CHARS",
                                          None)

    def tearDown(self):
        if self._snapshot is not None:
            os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = self._snapshot
        else:
            os.environ.pop("JAMES_GEMMA_MAX_PROMPT_CHARS", None)

    def test_default_when_env_unset(self):
        from core.gemma_client import (
            _DEFAULT_MAX_PROMPT_LEN, _resolve_max_prompt_len,
        )
        self.assertEqual(_resolve_max_prompt_len(), _DEFAULT_MAX_PROMPT_LEN)
        # Pin the historical default explicitly so a future refactor
        # cannot silently lower / raise it.
        self.assertEqual(_DEFAULT_MAX_PROMPT_LEN, 4000)

    def test_env_override_honoured(self):
        from core.gemma_client import _resolve_max_prompt_len
        os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = "200000"
        self.assertEqual(_resolve_max_prompt_len(), 200000)

    def test_env_override_picks_smaller_too(self):
        from core.gemma_client import _resolve_max_prompt_len
        os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = "500"
        self.assertEqual(_resolve_max_prompt_len(), 500)

    def test_invalid_env_falls_back_to_default(self):
        from core.gemma_client import (
            _DEFAULT_MAX_PROMPT_LEN, _resolve_max_prompt_len,
        )
        for bad in ("", "notanint", "0", "-100", "3.14"):
            os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = bad
            self.assertEqual(
                _resolve_max_prompt_len(),
                _DEFAULT_MAX_PROMPT_LEN,
                msg=f"env={bad!r} should fall back",
            )

    def test_env_read_per_call_not_at_import(self):
        """A measurement script may set the env var *after* importing
        gemma_client — the cap must reflect the most recent value, not
        the value at import time."""
        from core.gemma_client import _resolve_max_prompt_len
        os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = "10000"
        self.assertEqual(_resolve_max_prompt_len(), 10000)
        os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = "50000"
        self.assertEqual(_resolve_max_prompt_len(), 50000)


if __name__ == "__main__":
    unittest.main()
