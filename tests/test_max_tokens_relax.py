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
        # [2026-08-26] gemma_client became a package (client / config /
        # errors / response_parser); inspect.getsource on a package
        # returns only __init__.py, so the num_predict and num_ctx
        # defaults — which live in client.py — became invisible and
        # these tests reported the caps as missing when they had only
        # moved. module_source walks the package.
        from core import gemma_client
        from tests._pipeline_src import module_source
        cls.src = module_source(gemma_client)

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
        # Context window default must be ≥8192 (else tokens clamp).
        # 2026-06-04: num_ctx became env-overridable
        # (JAMES_NUM_CTX, default "8192") for benchmark eval — the
        # default literal is the fallback string in os.environ.get.
        m = re.search(r'JAMES_NUM_CTX",\s*"(\d+)"', self.src)
        if m is None:
            # back-compat: plain literal form
            m = re.search(r'"num_ctx":\s*(\d+)', self.src)
        self.assertIsNotNone(m, "couldn't locate num_ctx default")
        ctx = int(m.group(1))
        self.assertGreaterEqual(ctx, 8192,
            f"num_ctx default {ctx} — must be ≥8192 to fit longer answers")


class CallSiteUnchangedTests(unittest.TestCase):
    """Pipeline + engine + modes still derive max_tokens from
    resolve_style (no literal). The bump should be invisible to call
    sites — they get more headroom for free."""

    def test_engine_still_uses_resolve_style(self):
        # Post engine split (chore PR): the actual style.max_tokens
        # reference lives in engine_synth.generate_rag_answer; the
        # engine method is now a thin delegator.
        import core.reasoning.engine_synth as engsynth
        src = inspect.getsource(engsynth.generate_rag_answer)
        self.assertIn("style.max_tokens", src)

    def test_pipeline_still_uses_resolve_style(self):
        from tests._pipeline_src import pipeline_source
        src = pipeline_source()
        self.assertIn("resolve_style", src)
        self.assertIn(".max_tokens", src)


if __name__ == "__main__":
    unittest.main()
