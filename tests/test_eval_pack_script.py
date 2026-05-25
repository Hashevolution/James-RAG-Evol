"""PROJECT JAMES — eval_pack.py CLI tests (PR-C9).

Verifies ``scripts/eval_pack.py`` returns exit 0 on the dogfood pack
and exit 1 on obvious failure modes. The script is the single source
of truth for the v0.3 pack eval gate — CI invokes it; a regression
here breaks the gate for every pack PR.

The tests use ``subprocess.run`` so we exercise the script as CI
would. argparse failure exits are also part of the contract — the
GitHub Actions log surfaces them, so we verify message text.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "eval_pack.py"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke the script. Default cwd is the project root.

    ``encoding="utf-8"`` is explicit because the script calls
    ``ensure_utf8_console()`` to emit UTF-8 on Windows where the
    default cp949 / cp1252 codec cannot represent the project's
    Korean strings; the test reader must match.
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd or PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


class HappyPathTests(unittest.TestCase):

    def test_general_pack_passes(self):
        result = _run("general")
        self.assertEqual(
            result.returncode, 0,
            f"eval_pack.py general failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn("PASS", result.stdout)
        self.assertIn("general v0.3.0", result.stdout)

    def test_all_flag_passes(self):
        result = _run("--all")
        self.assertEqual(
            result.returncode, 0,
            f"eval_pack.py --all failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        # The summary block lists each pack on its own line.
        self.assertIn("general: PASS", result.stdout)

    def test_manifest_only_skips_ruff(self):
        # --manifest-only is the lightweight check for pack authors
        # iterating on a pack.yaml without yet having Python code.
        result = _run("general", "--manifest-only")
        self.assertEqual(result.returncode, 0)
        self.assertIn("manifest parses", result.stdout)
        # The slot-import line should NOT appear under --manifest-only.
        self.assertNotIn("Protocol satisfied", result.stdout)
        self.assertNotIn("ruff check passes", result.stdout)


class FailureModeTests(unittest.TestCase):

    def test_missing_pack_returns_nonzero(self):
        result = _run("does-not-exist-pack-name-xyz")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", (result.stdout + result.stderr).lower())

    def test_no_args_errors_out(self):
        result = _run()
        self.assertNotEqual(result.returncode, 0)
        # argparse prints to stderr.
        self.assertIn("pack", result.stderr.lower())

    def test_mutually_exclusive_args_error(self):
        # --all + an explicit pack name is operator confusion; we want
        # a clear error message, not a silent precedence rule.
        result = _run("general", "--all")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mutually exclusive", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
