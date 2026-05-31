"""Contract — `core.observability._trace_root()` honours JAMES_WORKSPACE.

Before this fix (D11, 2026-05-31), `_trace_root()` always returned
`<repo_root>/reports/trace`, ignoring `JAMES_WORKSPACE`. A
benchmark workspace (`JAMES_WORKSPACE=./workspaces/hotpot_eval`)
would still write traces into the production tree — a small but
real isolation leak.

Three guarantees pinned here:

  1. With `JAMES_WORKSPACE` unset, `_trace_root()` falls back to
     `<project_root>/reports/trace` (legacy behaviour preserved).
  2. With `JAMES_WORKSPACE=<path>`, `_trace_root()` returns
     `<path>/reports/trace` (resolved absolute).
  3. The `set_trace_root()` test seam still wins over both
     branches — a tmpdir override is unconditional.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.observability import _trace_root, set_trace_root  # noqa: E402


class TraceRootWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        set_trace_root(None)  # reset any override leaked from prior tests

    def tearDown(self) -> None:
        set_trace_root(None)

    def test_default_when_workspace_unset(self) -> None:
        with patch.dict("os.environ", {"JAMES_WORKSPACE": ""}, clear=False):
            root = _trace_root()
        expected = Path(__file__).resolve().parent.parent / "reports" / "trace"
        self.assertEqual(root, expected)

    def test_default_when_workspace_unset_truly_absent(self) -> None:
        import os
        env = dict(os.environ)
        env.pop("JAMES_WORKSPACE", None)
        with patch.dict("os.environ", env, clear=True):
            root = _trace_root()
        expected = Path(__file__).resolve().parent.parent / "reports" / "trace"
        self.assertEqual(root, expected)

    def test_workspace_set_routes_to_workspace_subtree(self) -> None:
        ws = Path("/tmp/test_workspace_xyz")
        with patch.dict("os.environ", {"JAMES_WORKSPACE": str(ws)}, clear=False):
            root = _trace_root()
        self.assertEqual(root, ws.resolve() / "reports" / "trace")

    def test_workspace_whitespace_treated_as_unset(self) -> None:
        with patch.dict("os.environ", {"JAMES_WORKSPACE": "   "}, clear=False):
            root = _trace_root()
        expected = Path(__file__).resolve().parent.parent / "reports" / "trace"
        self.assertEqual(root, expected)

    def test_set_trace_root_override_wins_over_workspace(self) -> None:
        override = Path("/tmp/test_override_abc")
        set_trace_root(override)
        try:
            with patch.dict("os.environ", {"JAMES_WORKSPACE": "/tmp/some/ws"}, clear=False):
                root = _trace_root()
        finally:
            set_trace_root(None)
        self.assertEqual(root, override)


if __name__ == "__main__":
    unittest.main()
