"""Latency decomposition — the arithmetic, and the two judgment calls.

`scripts/research/latency_decomposition.py` turned "queries feel slow"
into "32% of wall clock is spent on LLM calls that produced nothing, and
retrieval is 1%". A number that load-bearing needs its method pinned,
because two choices in it are judgment, not arithmetic:

  1. **Blocked episodes are dropped.** step7 ships security fixtures that
     are *supposed* to be refused. Counting them would make a healthy run
     look fast and a refusal look like a failure.
  2. **A gap is attributed to the LATER event.** Audit rows are written
     *after* the operation they describe, so the time before
     `system:WARN:gemma.timeout` is the timed-out call — not the stage
     that happened to precede it. Flip this and the 32% lands on whatever
     ran before the failure instead.

Run:
  python -m unittest tests.test_latency_decomposition
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_SCRIPT = REPO_ROOT / "scripts" / "research" / "latency_decomposition.py"


def _load():
    spec = importlib.util.spec_from_file_location("_latency_decomp", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db(path: Path, rows):
    """rows: (timestamp, endpoint, blocked)"""
    con = sqlite3.connect(path)
    con.execute(
        "create table audit_log (id integer primary key autoincrement, "
        "timestamp text, user_role text, endpoint text, query text, "
        "answer text, graph_paths text, blocked int, security_event text, "
        "elapsed_sec real, ip_address text)"
    )
    for ts, ep, blocked in rows:
        con.execute(
            "insert into audit_log (timestamp, endpoint, blocked, elapsed_sec) "
            "values (?,?,?,?)", (ts, ep, blocked, 0.0))
    con.commit()
    con.close()


def _t(sec: int) -> str:
    return "2026-09-22T10:00:{:02d}".format(sec)


class DecompositionArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "audit.db"

    def tearDown(self):
        self._tmp.cleanup()

    def test_single_episode_splits_wall_clock(self):
        # 0s start, 10s timeout, 40s synth, 41s done  -> wall 41s
        _db(self.path, [
            (_t(0), "system:INFO:llm_router.route", 0),
            (_t(10), "system:WARN:gemma.timeout", 0),
            (_t(40), "reason:synth", 0),
            (_t(41), "/query/", 0),
        ])
        eps = self.m.load_episodes(self.path, "2026-09-22", "2026-09-23")
        d = self.m.decompose(eps)
        self.assertEqual(d["n_queries"], 1)
        self.assertAlmostEqual(d["wall_mean_s"], 41.0)
        self.assertAlmostEqual(d["timeout_s"], 10.0)
        self.assertAlmostEqual(d["timeout_share"], 10.0 / 41.0)
        self.assertAlmostEqual(d["floor_s"], 31.0)

    def test_gap_is_attributed_to_the_later_event(self):
        """The 30 s between the timeout row and reason:synth belongs to
        synth, not to the timeout. Flipping this moves the headline."""
        _db(self.path, [
            (_t(0), "system:INFO:llm_router.route", 0),
            (_t(10), "system:WARN:gemma.timeout", 0),
            (_t(40), "reason:synth", 0),
            (_t(41), "/query/", 0),
        ])
        d = self.m.decompose(
            self.m.load_episodes(self.path, "2026-09-22", "2026-09-23"))
        self.assertAlmostEqual(sum(d["cost"]["reason:synth"]), 30.0)
        self.assertAlmostEqual(sum(d["cost"]["system:WARN:gemma.timeout"]), 10.0)

    def test_blocked_episodes_are_excluded(self):
        _db(self.path, [
            (_t(0), "system:INFO:llm_router.route", 0),
            (_t(5), "/query/", 1),                      # blocked: dropped
            (_t(6), "system:INFO:llm_router.route", 0),
            (_t(26), "reason:synth", 0),
            (_t(27), "/query/", 0),                     # answerable: kept
        ])
        eps = self.m.load_episodes(self.path, "2026-09-22", "2026-09-23")
        self.assertEqual(len(eps), 1)
        self.assertEqual(self.m.decompose(eps)["n_queries"], 1)

    def test_stage_after_timeout_is_counted(self):
        _db(self.path, [
            (_t(0), "system:INFO:llm_router.route", 0),
            (_t(10), "system:WARN:gemma.timeout", 0),
            (_t(10), "reason:retrieve", 0),             # right after a timeout
            (_t(20), "reason:synth", 0),                # not after a timeout
            (_t(21), "/query/", 0),
        ])
        d = self.m.decompose(
            self.m.load_episodes(self.path, "2026-09-22", "2026-09-23"))
        self.assertEqual(d["after_timeout"]["reason:retrieve"], 1)
        self.assertEqual(d["after_timeout"].get("reason:synth", 0), 0)
        self.assertEqual(d["stage_seen"]["reason:synth"], 1)

    def test_clean_and_dirty_queries_are_separated(self):
        _db(self.path, [
            (_t(0), "reason:synth", 0), (_t(20), "/query/", 0),       # clean
            (_t(30), "system:WARN:gemma.timeout", 0),
            (_t(40), "reason:synth", 0), (_t(50), "/query/", 0),      # dirty
        ])
        d = self.m.decompose(
            self.m.load_episodes(self.path, "2026-09-22", "2026-09-23"))
        self.assertEqual(d["clean_n"], 1)
        self.assertEqual(d["dirty_n"], 1)

    def test_implausible_gap_is_excluded_not_attributed(self):
        """Idle time between harness runs must not become a stage cost."""
        _db(self.path, [
            (_t(0), "system:INFO:llm_router.route", 0),
            ("2026-09-22T12:00:00", "reason:synth", 0),   # 2 h later
            ("2026-09-22T12:00:05", "/query/", 0),
        ])
        d = self.m.decompose(
            self.m.load_episodes(self.path, "2026-09-22", "2026-09-23"))
        self.assertEqual(sum(d["cost"].get("reason:synth", [])), 0.0)

    def test_window_filters_rows(self):
        _db(self.path, [
            ("2026-09-01T10:00:00", "reason:synth", 0),
            ("2026-09-01T10:00:10", "/query/", 0),
            (_t(0), "reason:synth", 0),
            (_t(20), "/query/", 0),
        ])
        eps = self.m.load_episodes(self.path, "2026-09-22", "2026-09-23")
        self.assertEqual(len(eps), 1)


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "audit.db"
        _db(self.path, [
            (_t(0), "system:INFO:llm_router.route", 0),
            (_t(10), "system:WARN:gemma.timeout", 0),
            (_t(40), "reason:synth", 0),
            (_t(41), "/query/", 0),
        ])
        self.d = self.m.decompose(
            self.m.load_episodes(self.path, "2026-09-22", "2026-09-23"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_text_render_names_the_timeout_share(self):
        txt = self.m.render_text(self.d)
        self.assertIn("TIMEOUT SHARE", txt)
        self.assertIn("floor if nothing timed out", txt)

    def test_markdown_render_is_a_table(self):
        md = self.m.render_markdown(self.d, "a", "b")
        self.assertIn("| stage | n | total s |", md)
        self.assertIn("`reason:synth`", md)

    def test_missing_db_exits_nonzero(self):
        rc = self.m.main(["--db", str(self.path.parent / "nope.db"),
                          "--since", "2026-09-22"])
        self.assertEqual(rc, 2)

    def test_empty_window_exits_nonzero(self):
        rc = self.m.main(["--db", str(self.path), "--since", "2030-01-01"])
        self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main()
