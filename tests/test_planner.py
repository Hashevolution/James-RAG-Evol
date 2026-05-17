"""Phase 2 PR-7 — planner unit tests.

ARCHITECTURE.md §5.7.1 Planner. Uses mocked backend so unit tests
don't hit live Ollama. Pipeline integration smoke is covered by
the reasoning-touching slice.

Coverage:
  * opt-in gate (JAMES_ENABLE_PLANNER) — default OFF returns trivial
  * force flag: bypasses env gate
  * empty / too-short query → trivial plan
  * backend lookup miss → trivial plan, "skipped: backend_lookup_failed"
  * backend.complete raises → trivial plan + error trace
  * backend returns error string / empty text → trivial plan
  * malformed JSON → trivial plan
  * runaway subtasks (> 5) → capped at MAX_SUBTASKS
  * KO vs EN prompt template selection
  * happy path: Plan(subtasks=[...], rationale="...") returned
  * trivial-detection: 1 subtask same as query → is_trivial() True
  * trace emit: stage="plan", applied_rule="reasoning.plan.decompose"
  * singleton
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,
    user_role    TEXT    NOT NULL,
    endpoint     TEXT    NOT NULL,
    query        TEXT,
    answer       TEXT,
    graph_paths  TEXT,
    blocked      INTEGER DEFAULT 0,
    security_event TEXT,
    elapsed_sec  REAL,
    ip_address   TEXT
)
"""


def _fresh_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    conn = sqlite3.connect(f.name)
    conn.execute(_AUDIT_SCHEMA)
    conn.commit()
    conn.close()
    return f.name


def _rows(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM audit_log "
            "WHERE endpoint = 'reason:plan' ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()


def _completion(text="", error=""):
    res = MagicMock()
    res.text = text
    res.error = error
    return res


LONG_KO = "비트코인 ETF 가 미국 시장에 미친 영향을 종합적으로 분석해줘"
LONG_EN = "Analyze the impact of Bitcoin ETF approvals on the US market"


class OptInGateTests(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.pop("JAMES_ENABLE_PLANNER", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_ENABLE_PLANNER", None)
        else:
            os.environ["JAMES_ENABLE_PLANNER"] = self._saved

    def test_disabled_default_returns_trivial_plan(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            plan = Planner().plan(LONG_KO)
        self.assertEqual(plan.subtasks, [LONG_KO])
        self.assertTrue(plan.is_trivial())
        fake.complete.assert_not_called()

    def test_force_bypasses_env_gate(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"subtasks": ["1단계", "2단계", "3단계"], "rationale": "분해함"}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            plan = Planner().plan(LONG_KO, force=True)
        self.assertEqual(plan.subtasks, ["1단계", "2단계", "3단계"])
        self.assertFalse(plan.is_trivial())
        fake.complete.assert_called_once()


class ShortQueryTests(unittest.TestCase):

    def setUp(self):
        os.environ["JAMES_ENABLE_PLANNER"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_PLANNER", None)

    def test_empty_query_trivial(self):
        from core.reasoning.planner import Planner
        plan = Planner().plan("")
        self.assertTrue(plan.is_trivial())

    def test_short_query_trivial_no_backend_call(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            plan = Planner().plan("RAG?")   # 4 chars, below MIN_QUERY_LEN
        self.assertTrue(plan.is_trivial())
        fake.complete.assert_not_called()


class BackendFailureTests(unittest.TestCase):

    def setUp(self):
        os.environ["JAMES_ENABLE_PLANNER"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_PLANNER", None)

    def test_backend_lookup_miss_trivial(self):
        from core.reasoning.planner import Planner
        p = Planner(backend_id="definitely_not_registered")
        plan = p.plan(LONG_KO)
        self.assertTrue(plan.is_trivial())

    def test_backend_raises_trivial(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.side_effect = RuntimeError("ollama down")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            plan = Planner().plan(LONG_KO)
        self.assertTrue(plan.is_trivial())

    def test_backend_error_string_trivial(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.return_value = _completion(error="backend error")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            plan = Planner().plan(LONG_KO)
        self.assertTrue(plan.is_trivial())

    def test_empty_text_trivial(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.return_value = _completion(text="")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            plan = Planner().plan(LONG_KO)
        self.assertTrue(plan.is_trivial())

    def test_malformed_json_trivial(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.return_value = _completion(text="not json at all")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            plan = Planner().plan(LONG_KO)
        self.assertTrue(plan.is_trivial())

    def test_missing_subtasks_key_trivial(self):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rationale": "no subtasks"}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            plan = Planner().plan(LONG_KO)
        self.assertTrue(plan.is_trivial())


class JsonParseTests(unittest.TestCase):

    def setUp(self):
        os.environ["JAMES_ENABLE_PLANNER"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_PLANNER", None)

    def _plan_with_text(self, llm_text, query=LONG_KO):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.return_value = _completion(text=llm_text)
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            return Planner().plan(query)

    def test_pure_json_three_subtasks(self):
        plan = self._plan_with_text(
            '{"subtasks": ["A", "B", "C"], "rationale": "분해"}'
        )
        self.assertEqual(plan.subtasks, ["A", "B", "C"])
        self.assertEqual(plan.rationale, "분해")

    def test_json_with_leading_prose(self):
        plan = self._plan_with_text(
            '여기 분해 결과:\n{"subtasks": ["X", "Y"], "rationale": "r"}'
        )
        self.assertEqual(plan.subtasks, ["X", "Y"])

    def test_runaway_subtasks_capped_at_max(self):
        from core.reasoning.planner import MAX_SUBTASKS
        subs = [f"step{i}" for i in range(MAX_SUBTASKS + 5)]
        text = (
            '{"subtasks": ['
            + ", ".join(f'"{s}"' for s in subs)
            + '], "rationale": "many"}'
        )
        plan = self._plan_with_text(text)
        self.assertEqual(len(plan.subtasks), MAX_SUBTASKS)

    def test_non_string_subtasks_filtered(self):
        plan = self._plan_with_text(
            '{"subtasks": ["valid", 123, "also valid", null, ""], "rationale": ""}'
        )
        self.assertEqual(plan.subtasks, ["valid", "also valid"])


class LanguageDetectionTests(unittest.TestCase):

    def setUp(self):
        os.environ["JAMES_ENABLE_PLANNER"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_PLANNER", None)

    def _capture_prompt(self, query):
        from core.reasoning.planner import Planner
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"subtasks": ["s"], "rationale": ""}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            Planner().plan(query)
        return fake.complete.call_args.args[0]

    def test_korean_query_uses_korean_prompt(self):
        prompt = self._capture_prompt(LONG_KO)
        self.assertIn("하위 작업", prompt)
        self.assertNotIn("Decompose the question", prompt)

    def test_english_query_uses_english_prompt(self):
        prompt = self._capture_prompt(LONG_EN)
        self.assertIn("Decompose the question", prompt)


class TraceEmissionTests(unittest.TestCase):

    def setUp(self):
        os.environ["JAMES_ENABLE_PLANNER"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_PLANNER", None)

    def test_happy_path_emits_plan_row(self):
        from core.reasoning.planner import Planner
        db = _fresh_db()
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"subtasks": ["A", "B"], "rationale": "r"}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake), \
             patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            Planner().plan(LONG_KO)
        rows = _rows(db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["security_event"],
                         "reasoning.plan.decompose")
        self.assertEqual(rows[0]["endpoint"], "reason:plan")
        self.assertFalse(rows[0]["blocked"])

    def test_backend_raise_still_emits_row_blocked(self):
        from core.reasoning.planner import Planner
        db = _fresh_db()
        fake = MagicMock()
        fake.complete.side_effect = RuntimeError("oom")
        with patch("core.reasoning.backends.get_backend", return_value=fake), \
             patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            Planner().plan(LONG_KO)
        rows = _rows(db)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])


class TrivialDetectionTests(unittest.TestCase):

    def test_empty_subtasks_is_trivial(self):
        from core.reasoning.planner import Plan
        self.assertTrue(Plan("q", []).is_trivial())

    def test_single_subtask_matching_query_is_trivial(self):
        from core.reasoning.planner import Plan
        self.assertTrue(Plan("question?", ["question?"]).is_trivial())

    def test_single_subtask_different_from_query_still_trivial(self):
        from core.reasoning.planner import Plan
        # 1 subtask total → trivial regardless of content (no real
        # decomposition happened)
        self.assertTrue(Plan("q", ["something else"]).is_trivial())

    def test_two_or_more_subtasks_not_trivial(self):
        from core.reasoning.planner import Plan
        self.assertFalse(Plan("q", ["a", "b"]).is_trivial())


class SingletonTests(unittest.TestCase):

    def test_get_planner_returns_same_instance(self):
        from core.reasoning.planner import (
            get_planner, _clear_singleton_for_tests,
        )
        _clear_singleton_for_tests()
        a = get_planner()
        b = get_planner()
        self.assertIs(a, b)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
