"""v0.6 — `core/reasoning/pipeline_synth/` package size lock-test.

CLAUDE.md rule #5: "no file in `core/` exceeds 20 KB. If your change
pushes a file over, split first." This test locks the 3 sub-files
of the post-split pipeline_synth package at < 20 KB each.

Also asserts the public + private import surface is preserved
exactly — the v0.6 split is a no-op for callers (the cycle γ Phase D2
test suite imports `_KOREAN_NO_DATA_TRIGGERS` / `_ENGLISH_NO_DATA_TRIGGERS`
/ `_abstention_triggers` / `_build_retry_prompt` directly from
`core.reasoning.pipeline_synth`; `core/reasoning/pipeline.py` imports
`generate_answer`).

Run:
  python -m unittest tests.test_v06_pipeline_synth_module_size
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "core" / "reasoning" / "pipeline_synth"

CAP_BYTES = 20 * 1024  # CLAUDE.md rule #5


class ModuleSizeCapTests(unittest.TestCase):
    def test_legacy_single_file_removed(self):
        legacy = REPO_ROOT / "core" / "reasoning" / "pipeline_synth.py"
        self.assertFalse(
            legacy.exists(),
            "legacy core/reasoning/pipeline_synth.py reappeared — "
            "both file and package can't coexist; revert and pick one",
        )

    def test_package_dir_exists(self):
        self.assertTrue(PACKAGE.is_dir())

    def test_canonical_subfiles_present(self):
        for name in ("__init__.py", "softener.py", "result.py",
                     "generator.py"):
            self.assertTrue(
                (PACKAGE / name).exists(),
                f"missing canonical sub-file: {name}",
            )

    def test_each_subfile_under_20kb(self):
        for path in PACKAGE.glob("*.py"):
            size = path.stat().st_size
            self.assertLess(
                size, CAP_BYTES,
                f"{path.name} is {size/1024:.1f} KB — exceeds CLAUDE.md "
                f"rule #5 20 KB cap. Split it before merging.",
            )


class PublicImportSurfaceTests(unittest.TestCase):
    def test_canonical_public_imports(self):
        from core.reasoning.pipeline_synth import (
            generate_answer,
            AnswerBlock,
        )
        self.assertTrue(callable(generate_answer))
        # AnswerBlock is a dataclass with 3 default-field constructor.
        ab = AnswerBlock()
        self.assertEqual(ab.answer, "")
        self.assertEqual(ab.web_results, [])
        self.assertEqual(ab.pending_save_proposal_id, "")

    def test_canonical_private_imports(self):
        # cycle γ Phase D2 test suite imports these directly —
        # any breakage here kills the bilingual softener guard.
        from core.reasoning.pipeline_synth import (  # noqa: F401
            _KOREAN_NO_DATA_TRIGGERS,
            _ENGLISH_NO_DATA_TRIGGERS,
            _abstention_triggers,
            _build_retry_prompt,
        )
        self.assertTrue(callable(_abstention_triggers))
        self.assertTrue(callable(_build_retry_prompt))

    def test_abstention_triggers_default_korean_only(self):
        from core.reasoning.pipeline_synth import (
            _abstention_triggers, _KOREAN_NO_DATA_TRIGGERS,
        )
        self.assertEqual(
            _abstention_triggers(bilingual=False),
            _KOREAN_NO_DATA_TRIGGERS,
        )

    def test_abstention_triggers_bilingual_adds_english(self):
        from core.reasoning.pipeline_synth import (
            _abstention_triggers,
            _KOREAN_NO_DATA_TRIGGERS,
            _ENGLISH_NO_DATA_TRIGGERS,
        )
        self.assertEqual(
            _abstention_triggers(bilingual=True),
            _KOREAN_NO_DATA_TRIGGERS + _ENGLISH_NO_DATA_TRIGGERS,
        )

    def test_build_retry_prompt_korean_path(self):
        from core.reasoning.pipeline_synth import _build_retry_prompt
        prompt = _build_retry_prompt(
            sys_prefix="", rule_text="rule",
            query="질문", is_korean=True, bilingual=True,
        )
        self.assertIn("질문: 질문", prompt)
        self.assertIn("답변:", prompt)

    def test_build_retry_prompt_english_path(self):
        from core.reasoning.pipeline_synth import _build_retry_prompt
        prompt = _build_retry_prompt(
            sys_prefix="", rule_text="rule",
            query="What is X?", is_korean=False, bilingual=True,
        )
        self.assertIn("Question: What is X?", prompt)
        self.assertIn("Answer:", prompt)


if __name__ == "__main__":
    unittest.main()
