"""config.py .env loader — BOM tolerance + empty-env-var override.

Two real failure modes documented + guarded:

  (A) Notepad / VS Code default save = UTF-8 with BOM. Without
      `utf-8-sig`, the FIRST key parsed becomes '﻿JAMES_API_KEY'
      and the server fails with the unhelpful "JAMES_API_KEY must be
      set" — config.py thinks no key was loaded. Confirmed on a real
      user's machine 2026-05-08.

  (B) A parent process / Windows system env exports the key with
      empty value. `_k in os.environ` is True but the value is "".
      The old `if _k not in os.environ` check skipped the .env line,
      and the empty env value propagated as the API key — same
      "must be set" failure, different cause. v0.2.1 changes the
      check to `not os.environ.get(_k)` so empty-env-vars get
      overwritten by .env.

This file uses subprocess invocations to test the loading behavior
in a fresh interpreter (config.py runs at module import; we cannot
re-import it within one test process). The cost is ~1s per test
which is acceptable.

Run:
  python -m unittest tests.test_config_env_loading
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _run_config_in_subprocess(env_file_path: str, extra_env: dict | None = None) -> tuple[int, str, str]:
    """Spawn a fresh python that imports config from a tmpdir copy
    and prints API_KEY. Returns (returncode, stdout, stderr).

    Uses a copy of config.py + a custom .env in tmpdir so the real
    project .env / env state is never disturbed. Sets PYTHONPATH so
    the copy's import `os, sys` etc resolve normally."""
    # Create a tmpdir layout: <tmp>/config.py + <tmp>/.env
    src_config = (ROOT / "config.py").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "config.py").write_text(src_config, encoding="utf-8")
        # The user supplies the .env contents via env_file_path,
        # which is itself a path to a file we built in the test.
        import shutil
        shutil.copyfile(env_file_path, tdp / ".env")

        # Spawn fresh python — do NOT inherit the parent process's
        # JAMES_* env vars unless extra_env explicitly asks.
        clean_env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("JAMES_") and k != "TAVILY_API_KEY"
        }
        # JWT_SECRET is required by config.py — supply a stub.
        clean_env["JAMES_JWT_SECRET"] = "x" * 33
        if extra_env:
            clean_env.update(extra_env)

        # Print API_KEY repr from the freshly-loaded config.
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, r'%s'); import config; print(repr(config.API_KEY))" % str(tdp)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=clean_env,
            timeout=15,
        )
        return proc.returncode, proc.stdout, proc.stderr


class BomToleranceTests(unittest.TestCase):
    """Mode (A): .env saved with UTF-8 BOM must still load correctly."""

    def test_bom_prefixed_env_file_loads(self):
        with tempfile.NamedTemporaryFile(suffix=".env", delete=False) as f:
            # Write BOM + content as raw bytes — exactly what Notepad does.
            f.write(b"\xef\xbb\xbfJAMES_API_KEY=test_key_after_bom_42\n")
            f.write(b"OTHER_VAR=other_value\n")
            path = f.name
        try:
            code, out, err = _run_config_in_subprocess(path)
            self.assertEqual(code, 0,
                             f"config import failed despite valid (BOM'd) .env: "
                             f"\nstdout: {out}\nstderr: {err}")
            self.assertIn("test_key_after_bom_42", out,
                          "BOM-prefixed first-line key was not parsed correctly; "
                          "config.py should use utf-8-sig encoding")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_no_bom_still_loads(self):
        # Sanity: no-BOM file must still work after the fix.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".env", delete=False, encoding="utf-8"
        ) as f:
            f.write("JAMES_API_KEY=plain_no_bom_key_42\n")
            path = f.name
        try:
            code, out, err = _run_config_in_subprocess(path)
            self.assertEqual(code, 0, f"plain .env should still load: {err}")
            self.assertIn("plain_no_bom_key_42", out)
        finally:
            Path(path).unlink(missing_ok=True)


class EmptyEnvVarOverrideTests(unittest.TestCase):
    """Mode (B): pre-existing empty env var must NOT block .env load."""

    def test_empty_env_var_overridden_by_dotenv(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".env", delete=False, encoding="utf-8"
        ) as f:
            f.write("JAMES_API_KEY=fallback_from_dotenv_99\n")
            path = f.name
        try:
            # Spawn config with empty env var — .env should win.
            code, out, err = _run_config_in_subprocess(
                path, extra_env={"JAMES_API_KEY": ""}
            )
            self.assertEqual(code, 0,
                             f"empty env var blocked .env load: {err}")
            self.assertIn("fallback_from_dotenv_99", out,
                          "empty env var must be overridden by .env value; "
                          "the v0.2.0 'if _k not in os.environ' check was the bug")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_nonempty_env_var_takes_precedence(self):
        # Sanity: a NON-empty env var still wins over .env. Operators
        # rely on this for per-shell overrides.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".env", delete=False, encoding="utf-8"
        ) as f:
            f.write("JAMES_API_KEY=should_be_ignored\n")
            path = f.name
        try:
            code, out, err = _run_config_in_subprocess(
                path, extra_env={"JAMES_API_KEY": "shell_override_77"}
            )
            self.assertEqual(code, 0)
            self.assertIn("shell_override_77", out,
                          "non-empty shell env var must still override .env")
            self.assertNotIn("should_be_ignored", out)
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
