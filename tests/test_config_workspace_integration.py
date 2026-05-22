"""[Track C PR-C6.b] config.py honors JAMES_WORKSPACE.

The four derived directory constants (RAW_DIR / WIKI_DIR / UPLOAD_DIR /
CHROMA_DIR) must resolve under the workspace root computed by
core.plugins.workspace.get_workspace_root(), so multi-instance hosting
(one JAMES process per workspace) can isolate per-tenant data without
forking the path-handling code.

The unit tests for the resolver itself live in test_plugin_workspace.py.
This file is the integration sibling: it verifies that **config.py
actually consumes the resolver**, so a regression that silently
re-anchors a directory to BASE_DIR would fail here.

Tests spawn a fresh interpreter per case because config.py runs at
module-import time — `importlib.reload` would replay its side effects
(.env load, logging config) against shared module state, which is
worse than the cost of subprocesses.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SNIPPET = (
    "import json, config; "
    "print(json.dumps({"
    "'BASE_DIR': config.BASE_DIR, "
    "'RAW_DIR': config.RAW_DIR, "
    "'WIKI_DIR': config.WIKI_DIR, "
    "'UPLOAD_DIR': config.UPLOAD_DIR, "
    "'CHROMA_DIR': config.CHROMA_DIR}))"
)


def _dirs_with_env(env_overrides: dict) -> dict:
    """Spawn a fresh interpreter that imports config, return the dirs.

    config.py prints a `[CONFIG] .env loaded:` line if a .env file
    exists in cwd. We take the *last* line of stdout as the JSON
    payload to be robust against that and against any future logging.
    """
    env = {**os.environ, **env_overrides, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.check_output(
        [sys.executable, "-c", _SNIPPET],
        cwd=str(ROOT), env=env,
    )
    text = out.decode("utf-8", errors="replace").strip()
    return json.loads(text.splitlines()[-1])


class UnsetWorkspaceTests(unittest.TestCase):
    def test_unset_dirs_anchor_to_base_dir(self):
        """JAMES_WORKSPACE explicitly empty → data dirs under BASE_DIR."""
        dirs = _dirs_with_env({"JAMES_WORKSPACE": ""})
        base = dirs["BASE_DIR"]
        # Resolver returns BASE_DIR for empty env; data dirs anchor to it.
        # workspace.BASE_DIR uses Path.resolve() so directly compare paths.
        for key, sub in (
            ("RAW_DIR", "raw"),
            ("WIKI_DIR", "wiki"),
            ("UPLOAD_DIR", "uploads"),
            ("CHROMA_DIR", "chroma_db"),
        ):
            # Both anchor to project root — compare via realpath to absorb
            # any symlink / case-normalization difference between
            # os.path.abspath (config.BASE_DIR) and Path.resolve()
            # (workspace.BASE_DIR).
            self.assertEqual(
                os.path.realpath(dirs[key]),
                os.path.realpath(os.path.join(base, sub)),
                f"{key} should sit under BASE_DIR when JAMES_WORKSPACE is empty",
            )


class SetWorkspaceTests(unittest.TestCase):
    def test_env_redirects_data_dirs_to_workspace(self):
        """JAMES_WORKSPACE=<tmp> → all four data dirs live under tmp."""
        # Resolver refuses non-existent dirs (loud failure on operator typo);
        # use a real temp directory.
        with tempfile.TemporaryDirectory() as tmp:
            workspace = str(Path(tmp).resolve())
            dirs = _dirs_with_env({"JAMES_WORKSPACE": tmp})
            for key, sub in (
                ("RAW_DIR", "raw"),
                ("WIKI_DIR", "wiki"),
                ("UPLOAD_DIR", "uploads"),
                ("CHROMA_DIR", "chroma_db"),
            ):
                self.assertEqual(
                    os.path.realpath(dirs[key]),
                    os.path.realpath(os.path.join(workspace, sub)),
                    f"{key} should sit under JAMES_WORKSPACE",
                )
            # BASE_DIR (project root) is independent of workspace.
            self.assertEqual(
                os.path.realpath(dirs["BASE_DIR"]),
                os.path.realpath(str(ROOT)),
                "BASE_DIR (project root) should NOT track JAMES_WORKSPACE",
            )

    def test_bad_workspace_path_fails_loud(self):
        """JAMES_WORKSPACE=<missing> → config import raises (no silent fallback)."""
        env = {
            **os.environ,
            "JAMES_WORKSPACE": "definitely-not-a-dir-pr-c6b-sentinel-zzz",
            "PYTHONIOENCODING": "utf-8",
        }
        proc = subprocess.run(
            [sys.executable, "-c", _SNIPPET],
            cwd=str(ROOT), env=env,
            capture_output=True,
        )
        self.assertNotEqual(
            proc.returncode, 0,
            "config import must fail when JAMES_WORKSPACE points to a "
            "non-existent path — silent fallback would mask operator typos",
        )
        # PluginLoadError should surface by name in the traceback so
        # operators can grep one line.
        self.assertIn(
            b"PluginLoadError", proc.stderr,
            f"expected PluginLoadError in stderr, got: {proc.stderr!r}",
        )


if __name__ == "__main__":
    unittest.main()
