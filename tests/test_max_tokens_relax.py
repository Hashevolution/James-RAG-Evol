"""Relaxed answer length cap (item #A8-5, 2026-05-09).

User feedback: "가능한 대화 글자수가 중간에 짤리지 않고 최대한 다
나올수 있도록 글자수 제한을 풀어줘".

Changes:
  - core/response_style.py: NATURAL_PRESET.max_tokens 2000 → 8192
  - core/gemma_client.py: num_predict default 2000 → 8192,
                          num_ctx 4096 → 8192

Run:
  python -m unittest tests.test_max_tokens_relax
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ResponseStyleCapTests(unittest.TestCase):
    def test_natural_preset_max_tokens_at_least_4096(self):
        from core.response_style import NATURAL_PRESET
        self.assertGreaterEqual(NATURAL_PRESET.max_tokens, 4096,
            f"max_tokens {NATURAL_PRESET.max_tokens} too small — "
            f"user wants long-form answers; ≥4096 required")

    def test_natural_preset_max_tokens_not_unbounded(self):
        # We deliberately keep a hard ceiling as a runaway-LLM defense.
        # Anything > 32768 is suspicious for the 8K-context default model.
        from core.response_style import NATURAL_PRESET
        self.assertLessEqual(NATURAL_PRESET.max_tokens, 32768,
            "keep a runaway-LLM ceiling — don't go fully unbounded")


class GemmaClientDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core import gemma_client
        cls.src = inspect.getsource(gemma_client)

    def test_num_predict_fallback_increased(self):
        # The fallback (when caller passes 0) must be ≥ 4096.
        m = re.search(
            r'"num_predict":\s*max_tokens\s+if\s+max_tokens\s*>\s*0\s+else\s+(\d+)',
            self.src,
        )
        self.assertIsNotNone(m, "couldn't locate num_predict default literal")
        fallback = int(m.group(1))
        self.assertGreaterEqual(fallback, 4096,
            f"num_predict fallback {fallback} — must be ≥4096")

    def test_num_ctx_increased(self):
        # Context window must be at least as large as the default
        # max_tokens, otherwise tokens get clamped.
        m = re.search(r'"num_ctx":\s*(\d+)', self.src)
        self.assertIsNotNone(m, "couldn't locate num_ctx literal")
        ctx = int(m.group(1))
        self.assertGreaterEqual(ctx, 8192,
            f"num_ctx {ctx} — must be ≥8192 to fit the longer answers")


class CallSiteUnchangedTests(unittest.TestCase):
    """Pipeline + engine + modes still derive max_tokens from
    resolve_style (no literal). The bump should be invisible to call
    sites — they get more headroom for free."""

    def test_engine_still_uses_resolve_style(self):
        import core.reasoning.engine as eng
        src = inspect.getsource(eng.ReasoningEngine._generate_answer)
        self.assertIn("style.max_tokens", src)

    def test_pipeline_still_uses_resolve_style(self):
        from tests._pipeline_src import pipeline_source
        src = pipeline_source()
        self.assertIn("resolve_style", src)
        self.assertIn(".max_tokens", src)


if __name__ == "__main__":
    unittest.main()
