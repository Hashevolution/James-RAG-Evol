"""v0.6 — `core/reasoning/reflect/` package size lock-test.

CLAUDE.md rule #5: "no file in `core/` exceeds 20 KB. If your change
pushes a file over, split first." This test locks the 5 sub-files
of the post-split reflect package at < 20 KB each. A future PR that
appends to one of them past the cap fails fast.

Also asserts the public + private import surface is preserved
exactly — the v0.6 split is a no-op for callers, and renaming /
removing any of the re-exported symbols is a contract break.

Run:
  python -m unittest tests.test_v06_reflect_module_size
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "core" / "reasoning" / "reflect"

CAP_BYTES = 20 * 1024  # CLAUDE.md rule #5


class ModuleSizeCapTests(unittest.TestCase):
    def test_legacy_single_file_removed(self):
        # The pre-v0.6 single file MUST NOT exist alongside the
        # package — both can't coexist in Python and the legacy
        # file regrowing would break the rule #5 guarantee.
        legacy = REPO_ROOT / "core" / "reasoning" / "reflect.py"
        self.assertFalse(
            legacy.exists(),
            "legacy core/reasoning/reflect.py reappeared — both "
            "file and package can't coexist; revert and pick one",
        )

    def test_package_dir_exists(self):
        self.assertTrue(PACKAGE.is_dir())

    def test_canonical_subfiles_present(self):
        for name in ("__init__.py", "prompts.py", "meta_narration.py",
                     "issue_extractor.py", "loop.py"):
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
    """Every symbol the pre-split file exposed MUST still be importable
    from `core.reasoning.reflect`. Loss of any one is a contract
    break for existing callers (`core/reasoning/pipeline_synth.py`,
    research scripts, test suites)."""

    def test_canonical_public_imports(self):
        # Public API as called by pipeline_synth.py + research scripts.
        from core.reasoning.reflect import (  # noqa: F401 — importability contract
            ReflectionLoop, get_reflection_loop, DEFAULT_BACKEND_ID,
        )
        self.assertTrue(callable(get_reflection_loop))
        self.assertIsNotNone(DEFAULT_BACKEND_ID)

    def test_canonical_private_imports(self):
        # Private symbols the test suite imports directly.
        from core.reasoning.reflect import (  # noqa: F401
            _clear_singleton_for_tests,
            _enabled,
            _no_issues,
            _extract_issue_flag,
            _looks_like_meta_narration,
            _strip_meta_narration,
            _META_NARRATIVE_PATTERNS,
            _ISSUE_TYPE_PATTERNS,
        )

    def test_canonical_prompt_constants(self):
        from core.reasoning.reflect import (  # noqa: F401 — importability contract
            CRITIQUE_PROMPT_EN,
            CRITIQUE_PROMPT_KO,
            REVISE_PROMPT_EN,
            REVISE_PROMPT_KO,
            REVISE_PROMPT_V2_EN,
            REVISE_PROMPT_V2_KO,
            DEFAULT_CRITIQUE_TIMEOUT_S,
            DEFAULT_REVISE_TIMEOUT_S,
            DEFAULT_CRITIQUE_MAX_TOKENS,
            DEFAULT_REVISE_MAX_TOKENS,
            MAX_REVISE_RATIO,
        )
        # Smoke that the templates carry the load-bearing tokens.
        self.assertIn("Contradiction", CRITIQUE_PROMPT_EN)
        self.assertIn("모순", CRITIQUE_PROMPT_KO)
        self.assertIn("{issue_type}", REVISE_PROMPT_V2_EN)
        self.assertIn("{issue_type}", REVISE_PROMPT_V2_KO)
        # Caps haven't drifted.
        self.assertEqual(DEFAULT_CRITIQUE_MAX_TOKENS, 4096)
        self.assertEqual(DEFAULT_REVISE_MAX_TOKENS, 1024)
        self.assertEqual(MAX_REVISE_RATIO, 2.5)


class SingletonContractTests(unittest.TestCase):
    """The singleton lives in __init__ (not loop.py) to preserve the
    pre-split import path. Verify lazy construction + idempotent
    re-acquisition + test-side clear hook."""

    def test_singleton_is_lazy_and_cached(self):
        from core.reasoning.reflect import (
            get_reflection_loop, _clear_singleton_for_tests,
        )
        _clear_singleton_for_tests()
        a = get_reflection_loop()
        b = get_reflection_loop()
        self.assertIs(a, b)
        _clear_singleton_for_tests()
        c = get_reflection_loop()
        self.assertIsNot(a, c)


if __name__ == "__main__":
    unittest.main()
