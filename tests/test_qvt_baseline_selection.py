"""QVT matrix — pick the newest baseline, not the alphabetically last.

``_read_baseline`` selected with::

    files = sorted(baseline_dir.glob("baseline_*.json"))
    # Most recent SHA — operator captures one baseline per release.
    latest = files[-1]

Baselines are named ``baseline_<git-sha>.json`` and git SHAs are hex.
Their lexicographic order carries no time information, so the comment
and the code disagreed: it picked the alphabetically greatest SHA.

It matters right now. The repo carries ``baseline_2a31b20.json`` and the
next capture is due. If that capture lands on a SHA sorting below an
existing one — ``1a2b3c4``, ``0ff9911``, anything starting with a low
digit — the fresh baseline is silently ignored and every Δ in the report
is measured against the stale one, with nothing in the output saying so.

Same family as the other guards in this directory (#1123 / #1136 /
#1137 / #1138): the artifact looked fine and the wrong input was
invisible.

Run:
  python -m unittest tests.test_qvt_baseline_selection
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_SCRIPT = REPO_ROOT / "scripts" / "qvt_ablation_matrix.py"


def _load():
    spec = importlib.util.spec_from_file_location("_qvt_matrix_baseline", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_baseline(dirpath: Path, sha: str, captured_at, **extra):
    payload = {
        "schema": "qvt-baseline-v2",
        "git_sha": sha,
        "fixture_version": "step7-v7",
        "aggregate": {},
    }
    if captured_at is not None:
        payload["captured_at"] = captured_at
    payload.update(extra)
    p = dirpath / f"baseline_{sha}.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class BaselineSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        ws = Path(self._tmp.name)
        (ws / "eval" / "qvt").mkdir(parents=True)
        self.qvt_dir = ws / "eval" / "qvt"
        self._prev_ws = os.environ.get("JAMES_WORKSPACE")
        os.environ["JAMES_WORKSPACE"] = str(ws)

    def tearDown(self):
        if self._prev_ws is None:
            os.environ.pop("JAMES_WORKSPACE", None)
        else:
            os.environ["JAMES_WORKSPACE"] = self._prev_ws
        self._tmp.cleanup()

    def test_newest_capture_wins_over_alphabetically_greater_sha(self):
        """The regression: an older SHA that sorts higher must lose."""
        _write_baseline(self.qvt_dir, "721e109", "2026-05-01T00:00:00+00:00")
        _write_baseline(self.qvt_dir, "0ff9911", "2026-09-22T00:00:00+00:00")
        picked = self.m._read_baseline()
        self.assertIsNotNone(picked)
        self.assertEqual(
            picked["git_sha"], "0ff9911",
            "the September capture must win over the May one, even though "
            "'0ff9911' sorts below '721e109'",
        )

    def test_alphabetical_order_would_have_picked_the_stale_one(self):
        """Pins the bug's shape so nobody 'simplifies' back to it."""
        _write_baseline(self.qvt_dir, "721e109", "2026-05-01T00:00:00+00:00")
        _write_baseline(self.qvt_dir, "0ff9911", "2026-09-22T00:00:00+00:00")
        names = sorted(p.name for p in self.qvt_dir.glob("baseline_*.json"))
        self.assertEqual(names[-1], "baseline_721e109.json")
        self.assertNotEqual(
            self.m._read_baseline()["git_sha"], "721e109",
            "selection must not follow filename order",
        )

    def test_single_baseline_is_returned(self):
        _write_baseline(self.qvt_dir, "abc1234", "2026-09-22T00:00:00+00:00")
        self.assertEqual(self.m._read_baseline()["git_sha"], "abc1234")

    def test_missing_captured_at_falls_back_to_mtime(self):
        """A pre-field baseline must still rank, not crash or vanish."""
        _write_baseline(self.qvt_dir, "aaa1111", None)
        picked = self.m._read_baseline()
        self.assertIsNotNone(picked)
        self.assertEqual(picked["git_sha"], "aaa1111")

    def test_unreadable_baseline_is_skipped_not_fatal(self):
        (self.qvt_dir / "baseline_bad9999.json").write_text(
            "{not json", encoding="utf-8")
        _write_baseline(self.qvt_dir, "aaa1111", "2026-09-22T00:00:00+00:00")
        picked = self.m._read_baseline()
        self.assertIsNotNone(picked)
        self.assertEqual(picked["git_sha"], "aaa1111")

    def test_no_baseline_returns_none(self):
        self.assertIsNone(self.m._read_baseline())

    def test_all_unreadable_returns_none(self):
        (self.qvt_dir / "baseline_bad9999.json").write_text(
            "{not json", encoding="utf-8")
        self.assertIsNone(self.m._read_baseline())


class SelectionIsReportedTests(unittest.TestCase):
    """Whichever baseline wins, the run must say which — and on what."""

    @classmethod
    def setUpClass(cls):
        cls.src = _SCRIPT.read_text(encoding="utf-8")

    def test_selection_line_names_schema_and_fixture(self):
        self.assertIn("captured {captured}, by {how}", self.src)
        self.assertIn("schema {payload.get('schema', 'unknown')}", self.src)
        self.assertIn(
            "fixture {payload.get('fixture_version', 'unknown')}", self.src)

    def test_ignored_baselines_are_named(self):
        self.assertIn("older baseline(s) ignored", self.src)


if __name__ == "__main__":
    unittest.main()
