"""`core/reasoning/verify/` package size lock-test + import surface.

CLAUDE.md rule #5: "no file in `core/` exceeds 20 KB. If your change
pushes a file over, split first." The single-file `core/reasoning/
verify.py` had reached **20,008 B** — 472 B under the cap — which is
what forced this split before the echo-corroboration fix could add a
line. Same shape as `tests/test_v06_reflect_module_size.py`.

The import-surface tests matter more than usual here: the split is
supposed to be a **no-op for callers**, and the pre-split module
exposed several private names that live code and tests import directly
(`core/reasoning/pipeline_synth/generator.py`,
`tests/test_i18n_language_detection.py`, the verify test slice).
`_is_korean` was missed on the first pass and the i18n test caught it.

Run:
  python -m pytest tests/test_v062_verify_module_size.py -q
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

PACKAGE = REPO_ROOT / "core" / "reasoning" / "verify"
CAP_BYTES = 20 * 1024  # CLAUDE.md rule #5


class ModuleSizeCapTests(unittest.TestCase):
    def test_legacy_single_file_removed(self):
        """Both cannot coexist in Python, and the legacy file regrowing
        would void the rule #5 guarantee this split bought."""
        legacy = REPO_ROOT / "core" / "reasoning" / "verify.py"
        self.assertFalse(
            legacy.exists(),
            "legacy core/reasoning/verify.py reappeared — file and "
            "package can't coexist; revert and pick one",
        )

    def test_canonical_subfiles_present(self):
        for name in ("__init__.py", "prompts.py", "gates.py",
                     "security_flags.py", "parsing.py", "verifier.py"):
            self.assertTrue((PACKAGE / name).exists(),
                            f"missing canonical sub-file: {name}")

    def test_each_subfile_under_20kb(self):
        for path in PACKAGE.glob("*.py"):
            size = path.stat().st_size
            self.assertLess(
                size, CAP_BYTES,
                f"{path.name} is {size / 1024:.1f} KB — exceeds the "
                f"CLAUDE.md rule #5 20 KB cap. Split it before merging.",
            )


class PublicImportSurfaceTests(unittest.TestCase):
    def test_public_api(self):
        from core.reasoning.verify import (  # noqa: F401
            Verifier, VerifyResult, get_verifier, DEFAULT_BACKEND_ID,
        )
        self.assertTrue(callable(get_verifier))
        self.assertIsNotNone(DEFAULT_BACKEND_ID)

    def test_private_names_live_code_and_tests_import(self):
        from core.reasoning.verify import (  # noqa: F401
            _BLOCK_MSG_EN,
            _BLOCK_MSG_KO,
            _build_security_flags,
            _clear_singleton_for_tests,
            _enabled,
            _fact_check_enabled,
            _is_korean,
            _JSON_OBJ_RE,
            _parse_fact_check,
        )

    def test_constants_have_not_drifted(self):
        from core.reasoning.verify import (
            ANNOTATE_THRESHOLD, DEFAULT_FACT_CHECK_MAX_TOKENS,
            DEFAULT_FACT_CHECK_TIMEOUT_S, FACT_CHECK_PROMPT_EN,
            FACT_CHECK_PROMPT_KO, MIN_ANSWER_LEN_FOR_VERIFY,
        )
        self.assertEqual(MIN_ANSWER_LEN_FOR_VERIFY, 30)
        self.assertEqual(ANNOTATE_THRESHOLD, 2)
        self.assertEqual(DEFAULT_FACT_CHECK_TIMEOUT_S, 30.0)
        self.assertEqual(DEFAULT_FACT_CHECK_MAX_TOKENS, 4096)
        for tmpl in (FACT_CHECK_PROMPT_KO, FACT_CHECK_PROMPT_EN):
            for ph in ("{query}", "{answer}", "{context}"):
                self.assertIn(ph, tmpl)

    def test_singleton_is_lazy_and_idempotent(self):
        from core.reasoning.verify import (
            Verifier, _clear_singleton_for_tests, get_verifier,
        )
        _clear_singleton_for_tests()
        first = get_verifier()
        self.assertIsInstance(first, Verifier)
        self.assertIs(first, get_verifier())
        _clear_singleton_for_tests()
        self.assertIsNot(first, get_verifier())


if __name__ == "__main__":
    unittest.main()
