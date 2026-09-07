"""Cycle γ Phase B smoke #2 — env-configurable Gemma prompt cap.

The cap default is pinned here so a future refactor cannot regress it
silently. The env-var override path is the cycle γ wiring; tested via
``_resolve_max_prompt_len`` directly so no HTTP / Ollama dependency
is needed.

History of the pinned value:
  * 4000 — historical Phase-4 default, kept byte-identical through
    cycle γ (only the env override was added).
  * 16000 — v0.6.1 design review (2026-07-01). Once
    ``JAMES_SYNTH_CONTEXT_CHARS`` moved to 8000, the 4000 cap became
    a double-truncation defect: the synth stage assembled an
    8000-char evidence block and this cap silently chopped the final
    prompt (evidence tail + instruction section) to 4000 on every
    stock install that didn't copy `.env.example` (which already set
    16000). The default now equals the `.env.example` value; the
    consistency test below pins cap ≥ synth-context + headroom so the
    two defaults cannot drift apart again.

Self-eval trap note (memory ``feedback_self_evaluation_trap``):
this test exercises the cap-resolution helper, not the cap *value*
as a quality claim.
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
        # Pin the default explicitly so a future refactor cannot
        # silently lower / raise it (16000 = `.env.example` value,
        # see module docstring for the 4000 → 16000 history).
        self.assertEqual(_DEFAULT_MAX_PROMPT_LEN, 16000)

    def test_default_cap_covers_synth_context_default(self):
        """Anti-double-truncation invariant (v0.6.1 design review).

        The synth stage builds a context of JAMES_SYNTH_CONTEXT_CHARS
        (default 8000, engine_synth.py) and then hands the assembled
        prompt to GemmaClient, which applies this cap. If the cap
        default ever drops to (or below) the synth-context default,
        stock installs silently lose retrieved evidence + the
        instruction tail again. Require 1.5× headroom for question +
        instruction sections.
        """
        from core.gemma_client import _DEFAULT_MAX_PROMPT_LEN
        synth_default = 8000  # engine_synth.py JAMES_SYNTH_CONTEXT_CHARS
        self.assertGreaterEqual(
            _DEFAULT_MAX_PROMPT_LEN, int(synth_default * 1.5),
            "prompt cap default must leave headroom above the synth "
            "context default — see 2026-07-01 double-truncation fix",
        )

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
