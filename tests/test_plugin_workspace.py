"""PROJECT JAMES — Workspace root resolver tests (PR-C6).

Covers ``core/plugins/workspace.py``:
  - ``JAMES_WORKSPACE`` unset / empty → BASE_DIR (byte-identical default)
  - Absolute env value → used as-is, must exist as a directory
  - Relative env value → resolved against BASE_DIR (not process CWD)
  - Non-existent path → PluginLoadError (no silent creation)
  - File-instead-of-directory → PluginLoadError
  - ``workspace_path`` convenience wrapper

A regression here re-introduces a silent path-resolution fallback the
design memo explicitly forbids (operator must see the error).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.plugins.errors import PluginLoadError  # noqa: E402
from core.plugins.workspace import (  # noqa: E402
    BASE_DIR,
    get_workspace_root,
    workspace_path,
)


class DefaultBehaviorTests(unittest.TestCase):
    """Env unset / empty must be byte-identical to the pre-PR-C6 codepath.

    This is the contract the design memo states: "the default is 'the
    current directory', which is byte-identical to today." A regression
    here means an operator who never set the env var sees their data
    moved — exactly the silent failure mode this PR was designed to avoid.
    """

    def test_unset_env_returns_base_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            result = get_workspace_root(env={}, base_dir=anchor)
            self.assertEqual(result, anchor)

    def test_empty_env_returns_base_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            result = get_workspace_root(
                env={"JAMES_WORKSPACE": ""}, base_dir=anchor
            )
            self.assertEqual(result, anchor)

    def test_whitespace_only_env_returns_base_dir(self):
        # "   " is operator intent ambiguous. Treat it as empty (the
        # safe default) rather than as a literal directory named "   ".
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            result = get_workspace_root(
                env={"JAMES_WORKSPACE": "   "}, base_dir=anchor
            )
            self.assertEqual(result, anchor)

    def test_default_anchor_is_repo_root(self):
        # Defensive: BASE_DIR resolution must land on the repo root,
        # not somewhere inside core/plugins/. The marker we look for
        # is config.py — present at the repo root in every JAMES checkout.
        self.assertTrue(
            (BASE_DIR / "config.py").is_file(),
            f"BASE_DIR={BASE_DIR} does not contain config.py — "
            f"resolver derivation broke",
        )


class AbsolutePathTests(unittest.TestCase):

    def test_absolute_existing_dir_used_as_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp).resolve()
            result = get_workspace_root(
                env={"JAMES_WORKSPACE": str(target)},
            )
            self.assertEqual(result, target)

    def test_absolute_path_with_surrounding_whitespace_is_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp).resolve()
            result = get_workspace_root(
                env={"JAMES_WORKSPACE": f"  {target}  "},
            )
            self.assertEqual(result, target)


class RelativePathTests(unittest.TestCase):
    """Relative paths anchor on BASE_DIR, not on the process CWD.

    A systemd service started from / is a real production scenario;
    silently resolving relative to "/" would be a catastrophic loss
    of operator-visible data location.
    """

    def test_relative_path_anchors_on_base_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            (anchor / "subdir").mkdir()
            result = get_workspace_root(
                env={"JAMES_WORKSPACE": "subdir"},
                base_dir=anchor,
            )
            self.assertEqual(result, anchor / "subdir")

    def test_nested_relative_path_anchors_on_base_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            (anchor / "a" / "b" / "c").mkdir(parents=True)
            result = get_workspace_root(
                env={"JAMES_WORKSPACE": "a/b/c"},
                base_dir=anchor,
            )
            self.assertEqual(result, anchor / "a" / "b" / "c")


class FailureModeTests(unittest.TestCase):
    """Non-existent / wrong-type paths must fail loud at startup.

    Silent auto-creation is rejected here because a typo in
    ``JAMES_WORKSPACE=`` would otherwise materialize a phantom data
    root containing no prior JAMES state — looks like a fresh install,
    operator panics, real data appears lost.
    """

    def test_nonexistent_absolute_path_raises(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"does not exist"
        ):
            get_workspace_root(
                env={"JAMES_WORKSPACE": "/no/such/workspace/here/xyz"},
            )

    def test_nonexistent_relative_path_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            with self.assertRaisesRegex(
                PluginLoadError, r"does not exist"
            ):
                get_workspace_root(
                    env={"JAMES_WORKSPACE": "missing-subdir"},
                    base_dir=anchor,
                )

    def test_path_pointing_at_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "regular-file.txt"
            file_path.write_text("not a directory", encoding="utf-8")
            with self.assertRaisesRegex(
                PluginLoadError, r"is not a directory"
            ):
                get_workspace_root(
                    env={"JAMES_WORKSPACE": str(file_path)},
                )

    def test_error_message_names_env_value_for_log_grep(self):
        # Operator log-grep expects the raw env value to appear in the
        # error message, not just the resolved path. A typo in the env
        # var shows up exactly once in logs — that's the line to fix.
        with self.assertRaisesRegex(
            PluginLoadError, r"typo-dir-name"
        ):
            get_workspace_root(
                env={"JAMES_WORKSPACE": "/no/such/typo-dir-name"},
            )


class WorkspacePathWrapperTests(unittest.TestCase):

    def test_workspace_path_joins_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            # workspace_path() uses get_workspace_root() internally;
            # we drive it via env to land on a known root.
            result = workspace_path(
                "wiki", "entity", "prod",
                env={"JAMES_WORKSPACE": str(anchor)},
            )
            self.assertEqual(result, anchor / "wiki" / "entity" / "prod")

    def test_workspace_path_with_no_parts_is_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            result = workspace_path(
                env={"JAMES_WORKSPACE": str(anchor)},
            )
            self.assertEqual(result, anchor)


class EnvIsolationTests(unittest.TestCase):
    """Tests must never mutate ``os.environ`` — verify by sentinel."""

    def test_passing_dict_does_not_touch_os_environ(self):
        import os
        sentinel_key = "JAMES_WORKSPACE_TEST_SENTINEL_XYZ"
        self.assertNotIn(sentinel_key, os.environ)
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp).resolve()
            get_workspace_root(
                env={"JAMES_WORKSPACE": str(anchor), sentinel_key: "x"},
                base_dir=anchor,
            )
        self.assertNotIn(sentinel_key, os.environ)


if __name__ == "__main__":
    unittest.main()
