"""Default LLM model name guard.

Real user 2026-05-08 hit a "0.03s 답변 생성 실패" bug because
config.GEMMA_MODEL defaulted to `gemma2:2b` while the project's
documented + actually-installed model is `gemma4:e4b`. Ollama
rejected the unknown model name immediately, the chat handler saw
an LLM error, and returned the fallback "죄송합니다".

eval/RESULTS.md documents `gemma4:e4b` as the bench fingerprint
model. The default in config.py must match that documented value
so a fresh clone + ollama-pull-as-documented works out of the box.

This file pins the default. JAMES_LLM_MODEL env var still overrides
freely (operators on different hardware can use a smaller model).

Run:
  python -m unittest tests.test_default_llm_model
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DefaultModelNameTests(unittest.TestCase):
    def test_config_default_matches_documented_results_md(self):
        # Config source-level: the literal default must match the
        # value documented in eval/RESULTS.md "Hardware fingerprint".
        config_path = Path(__file__).resolve().parent.parent / "config.py"
        config_src = config_path.read_text(encoding="utf-8")
        results_md = (Path(__file__).resolve().parent.parent
                      / "eval" / "RESULTS.md").read_text(encoding="utf-8")

        # Config side — extract the default fallback inside the env getter.
        import re
        m = re.search(
            r'GEMMA_MODEL\s*=\s*os\.environ\.get\(\s*["\']JAMES_LLM_MODEL["\']\s*,\s*["\']([^"\']+)["\']',
            config_src,
        )
        self.assertIsNotNone(m, "GEMMA_MODEL fallback default not found "
                             "in config.py — pattern broken or refactored")
        config_default = m.group(1)

        # RESULTS.md side — the model name must appear in the
        # Hardware fingerprint table line.
        self.assertIn(
            f"`{config_default}`",
            results_md,
            f"config default {config_default!r} not mentioned in "
            f"eval/RESULTS.md. The user's environment is calibrated "
            f"on the RESULTS.md value; drift between the two causes "
            f"a fresh setup to fail with 'gemma2:2b: model not found' "
            f"or similar Ollama errors."
        )


if __name__ == "__main__":
    unittest.main()
