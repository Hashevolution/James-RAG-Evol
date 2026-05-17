"""Phase 2 PR-5 — reflection loop unit tests.

ARCHITECTURE.md §5.7.1 Reflection Engine. Uses the Backend registry
(Phase 0 L0) so unit tests register a mock backend rather than hitting
the live Ollama. Pipeline integration smoke is covered by the existing
204-test reasoning slice — this file pins the reflect.py contract.

Coverage:
  * opt-in gate: JAMES_ENABLE_REFLECT unset → draft returned unchanged
  * force flag: bypasses env gate (for tests / debug)
  * short / empty draft → draft returned (nothing meaningful to reflect)
  * backend lookup miss → draft returned
  * critique returns 'NO_ISSUES' → skip revise, return draft
  * critique raises → draft returned, audit row emitted with error
  * critique error string → draft returned
  * revise raises → draft returned
  * revise empty / error → draft returned
  * happy path: revised text returned
  * runaway revision (> 2.5× draft) rejected → draft returned
  * KO / EN prompt template selection
  * trace_step rows emitted per pass (mocked audit DB)
  * singleton: get_reflection_loop returns the same instance
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


def _completion(text="", error=""):
    res = MagicMock()
    res.text = text
    res.error = error
    return res


# A long-enough draft so the < 30-char gate doesn't trip.
DRAFT_KO = (
    "RAG는 Retrieval-Augmented Generation 의 약자로, 검색을 통해 "
    "외부 지식을 LLM 응답에 결합하는 기법입니다."
)
DRAFT_EN = (
    "RAG stands for Retrieval-Augmented Generation, a technique that "
    "combines external knowledge retrieval with LLM responses."
)


class OptInGateTests(unittest.TestCase):
    """Default OFF — reflection must not call the backend without an
    explicit opt-in. Byte-identical to pre-PR-5 behaviour at the call
    site (synth path returns answer as-is).
    """

    def setUp(self):
        self._saved = os.environ.get("JAMES_ENABLE_REFLECT")
        os.environ.pop("JAMES_ENABLE_REFLECT", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_ENABLE_REFLECT", None)
        else:
            os.environ["JAMES_ENABLE_REFLECT"] = self._saved

    def test_disabled_default_returns_draft_no_backend_call(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out = r.reflect("Q?", DRAFT_KO)
        self.assertEqual(out, DRAFT_KO)
        fake.complete.assert_not_called()

    def test_force_bypasses_env_gate(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        # First call: critique. Second call: revise.
        fake.complete.side_effect = [
            _completion(text="누락된 부분 있음."),
            _completion(text="RAG 는 검색 증강 생성으로, 외부 지식을 결합합니다 (보강)."),
        ]
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out = r.reflect("RAG가 뭐야?", DRAFT_KO, force=True)
        self.assertIn("보강", out)
        self.assertEqual(fake.complete.call_count, 2)


class ShortDraftTests(unittest.TestCase):

    def setUp(self):
        os.environ["JAMES_ENABLE_REFLECT"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_REFLECT", None)

    def test_empty_draft_returns_unchanged(self):
        from core.reasoning.reflect import ReflectionLoop
        self.assertEqual(ReflectionLoop().reflect("Q?", ""), "")

    def test_short_draft_returns_unchanged(self):
        from core.reasoning.reflect import ReflectionLoop
        short = "Hi"
        self.assertEqual(ReflectionLoop().reflect("Q?", short), short)


class BackendFailureTests(unittest.TestCase):
    """Every failure mode falls back to the original draft."""

    def setUp(self):
        os.environ["JAMES_ENABLE_REFLECT"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_REFLECT", None)

    def test_backend_lookup_missing_returns_draft(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop(backend_id="definitely_not_registered")
        self.assertEqual(r.reflect("Q?", DRAFT_KO), DRAFT_KO)

    def test_critique_raises_returns_draft(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.side_effect = RuntimeError("ollama down")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            self.assertEqual(r.reflect("Q?", DRAFT_KO), DRAFT_KO)
        # critique call attempted; revise NOT called
        self.assertEqual(fake.complete.call_count, 1)

    def test_critique_error_string_returns_draft(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.return_value = _completion(error="backend error")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            self.assertEqual(r.reflect("Q?", DRAFT_KO), DRAFT_KO)
        self.assertEqual(fake.complete.call_count, 1)

    def test_critique_empty_text_returns_draft(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.return_value = _completion(text="")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            self.assertEqual(r.reflect("Q?", DRAFT_KO), DRAFT_KO)

    def test_no_issues_response_skips_revise_returns_draft(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.return_value = _completion(text="NO_ISSUES")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            self.assertEqual(r.reflect("Q?", DRAFT_KO), DRAFT_KO)
        # only critique ran; revise never called
        self.assertEqual(fake.complete.call_count, 1)

    def test_revise_raises_returns_draft(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.side_effect = [
            _completion(text="누락된 부분 있음."),
            RuntimeError("revise crash"),
        ]
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            self.assertEqual(r.reflect("Q?", DRAFT_KO), DRAFT_KO)
        self.assertEqual(fake.complete.call_count, 2)

    def test_revise_empty_text_returns_draft(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.side_effect = [
            _completion(text="problem."),
            _completion(text=""),
        ]
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            self.assertEqual(r.reflect("Q?", DRAFT_KO), DRAFT_KO)

    def test_runaway_revise_rejected(self):
        """Revised text > 2.5× draft length → likely the model elaborated
        instead of fixing. Keep the original."""
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        big = "X" * 1000   # 1000 chars vs ~100-char DRAFT_KO
        fake = MagicMock()
        fake.complete.side_effect = [
            _completion(text="needs more detail."),
            _completion(text=big),
        ]
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            self.assertEqual(r.reflect("Q?", DRAFT_KO), DRAFT_KO)


class HappyPathTests(unittest.TestCase):

    def setUp(self):
        os.environ["JAMES_ENABLE_REFLECT"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_REFLECT", None)

    def test_critique_plus_revise_returns_revised(self):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        revised = (
            "RAG 는 검색 증강 생성으로, 외부 지식을 결합합니다. "
            "관련 출처를 인용해 환각 위험을 낮춥니다."
        )
        fake.complete.side_effect = [
            _completion(text="2. 누락된 핵심: 출처 인용의 역할을 설명하지 않음."),
            _completion(text=revised),
        ]
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out = r.reflect("RAG가 뭐야?", DRAFT_KO)
        self.assertEqual(out, revised)
        self.assertEqual(fake.complete.call_count, 2)


class LanguageDetectionTests(unittest.TestCase):
    """KO / EN prompt template selection. Check the prompt that reaches
    the backend on the critique call (revise reuses the same heuristic).
    """

    def setUp(self):
        os.environ["JAMES_ENABLE_REFLECT"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_REFLECT", None)

    def _capture_first_prompt(self, query, draft):
        from core.reasoning.reflect import ReflectionLoop
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.return_value = _completion(text="NO_ISSUES")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            r.reflect(query, draft)
        return fake.complete.call_args.args[0]

    def test_korean_query_uses_korean_prompt(self):
        prompt = self._capture_first_prompt("RAG가 뭐야?", DRAFT_KO)
        self.assertIn("비판적으로 검토하라", prompt)
        self.assertNotIn("Critically review", prompt)

    def test_english_query_uses_english_prompt(self):
        prompt = self._capture_first_prompt(
            "What is RAG?", DRAFT_EN,
        )
        self.assertIn("Critically review", prompt)
        self.assertNotIn("비판적으로 검토하라", prompt)


class TraceEmissionTests(unittest.TestCase):
    """Each pass (critique / revise) emits one ``reason:reflect``
    audit row. Verify by pointing audit_bridge at a fresh DB.
    """

    def setUp(self):
        os.environ["JAMES_ENABLE_REFLECT"] = "1"

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_REFLECT", None)

    def _rows(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT * FROM audit_log "
                "WHERE endpoint LIKE 'reason:%' ORDER BY id ASC"
            ).fetchall()
        finally:
            conn.close()

    def test_two_rows_emitted_on_happy_path(self):
        from core.reasoning.reflect import ReflectionLoop
        db = _fresh_db()
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.side_effect = [
            _completion(text="needs an example."),
            _completion(text=DRAFT_EN + " For example, web search results can be retrieved."),
        ]
        with patch("core.reasoning.backends.get_backend", return_value=fake), \
             patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            r.reflect("What is RAG?", DRAFT_EN)
        rows = self._rows(db)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["endpoint"], "reason:reflect")
        self.assertEqual(rows[1]["endpoint"], "reason:reflect")
        self.assertEqual(rows[0]["security_event"], "reasoning.reflect.critique")
        self.assertEqual(rows[1]["security_event"], "reasoning.reflect.revised")

    def test_critique_failure_still_emits_row(self):
        from core.reasoning.reflect import ReflectionLoop
        db = _fresh_db()
        r = ReflectionLoop()
        fake = MagicMock()
        fake.complete.side_effect = RuntimeError("ollama down")
        with patch("core.reasoning.backends.get_backend", return_value=fake), \
             patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            r.reflect("Q?", DRAFT_EN)
        rows = self._rows(db)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])
        self.assertEqual(rows[0]["security_event"], "reasoning.reflect.critique")


class SingletonTests(unittest.TestCase):

    def test_get_reflection_loop_returns_same_instance(self):
        from core.reasoning.reflect import (
            get_reflection_loop, _clear_singleton_for_tests,
        )
        _clear_singleton_for_tests()
        a = get_reflection_loop()
        b = get_reflection_loop()
        self.assertIs(a, b)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
