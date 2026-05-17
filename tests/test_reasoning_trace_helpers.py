"""L1 — trace_synth_call helper that wraps an LLM call with one emit.

12 ``call_gemma`` sites in pipeline.py / modes.py / engine.py route
through this helper. STEP 7 must stay byte-identical (no answer
mutation, no prompt rewriting); the only observable change is one
audit_log row per LLM round-trip.

Tests:
  * happy path: text forwarded unchanged, one row emitted, fields
    populated correctly
  * RouterWrapper error string (`[Gemma 응답 없음]` etc.): text still
    forwarded, but row's `error` is non-empty and `blocked=1`
  * exception in llm_call: emitted as error row, then re-raised
  * empty / None text: forwarded as "", emitted as error row
  * trace_id ContextVar propagation: when set, appears in answer JSON
  * trace_id absent: helper still works, no trace_id key in row
  * extras: caller-supplied extras land in answer JSON alongside
    trace_id (without clobbering schema fields)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

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


def _rows(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM audit_log ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()


class TraceSynthCallTests(unittest.TestCase):
    """Each test points emit_trace_step at an isolated DB by patching
    audit_bridge's default path resolution at module import time.
    """

    def _run(self, llm_call, *, applied_rule="reasoning.synth.test",
             user_role="employee", extras=None, prompt="hello"):
        from core.reasoning.trace_helpers import trace_synth_call
        db = _fresh_db()
        # Patch the audit_bridge default path so emit_trace_step writes
        # to our isolated db. The helper does not accept a db_path
        # parameter (production code never specifies one).
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            text = trace_synth_call(
                llm_call, prompt,
                applied_rule=applied_rule,
                user_role=user_role,
                extras=extras,
            )
        return text, _rows(db)

    def test_happy_path_text_forwarded_unchanged(self):
        text, rows = self._run(lambda: "the answer is 42")
        self.assertEqual(text, "the answer is 42")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["endpoint"], "reason:synth")
        self.assertEqual(row["security_event"], "reasoning.synth.test")
        self.assertEqual(row["user_role"], "employee")
        self.assertFalse(row["blocked"])
        ans = json.loads(row["answer"])
        self.assertEqual(ans["output_summary"], "the answer is 42")

    def test_router_error_string_marked_error_but_text_forwarded(self):
        """Existing call sites check answer.startswith("[Gemma 응답 없음]")
        to decide retry — the helper must NOT swallow that string.
        Behaviour-preserving wrapping.
        """
        text, rows = self._run(lambda: "[Gemma 응답 없음] timeout")
        self.assertTrue(text.startswith("[Gemma 응답 없음]"))   # forwarded as-is
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])
        ans = json.loads(rows[0]["answer"])
        self.assertIn("error", ans)

    def test_exception_emits_error_row_then_reraises(self):
        from core.reasoning.trace_helpers import trace_synth_call
        db = _fresh_db()
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            with self.assertRaises(RuntimeError) as ctx:
                trace_synth_call(
                    lambda: (_ for _ in ()).throw(RuntimeError("ollama down")),
                    "p",
                    applied_rule="reasoning.synth.test",
                    user_role="admin",
                )
        self.assertIn("ollama down", str(ctx.exception))
        rows = _rows(db)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])
        ans = json.loads(rows[0]["answer"])
        self.assertIn("RuntimeError", ans["error"])
        self.assertIn("ollama down", ans["error"])

    def test_empty_text_marked_error(self):
        text, rows = self._run(lambda: "")
        self.assertEqual(text, "")
        self.assertTrue(rows[0]["blocked"])

    def test_none_return_handled_as_empty(self):
        text, rows = self._run(lambda: None)
        self.assertEqual(text, "")
        self.assertTrue(rows[0]["blocked"])

    def test_trace_id_propagation(self):
        from core.observability import current_trace_id
        token = current_trace_id.set("test-trace-xyz")
        try:
            text, rows = self._run(lambda: "ok")
        finally:
            current_trace_id.reset(token)
        ans = json.loads(rows[0]["answer"])
        self.assertEqual(ans.get("trace_id"), "test-trace-xyz")

    def test_no_trace_id_when_contextvar_unset(self):
        from core.observability import current_trace_id
        token = current_trace_id.set("")   # explicit empty
        try:
            text, rows = self._run(lambda: "ok")
        finally:
            current_trace_id.reset(token)
        ans = json.loads(rows[0]["answer"])
        self.assertNotIn("trace_id", ans)

    def test_extras_folded_in_alongside_trace_id(self):
        from core.observability import current_trace_id
        token = current_trace_id.set("trace-extras")
        try:
            text, rows = self._run(
                lambda: "ok",
                extras={"loop_idx": 2, "selected_model": "gemma2:2b"},
            )
        finally:
            current_trace_id.reset(token)
        ans = json.loads(rows[0]["answer"])
        self.assertEqual(ans.get("trace_id"), "trace-extras")
        self.assertEqual(ans.get("loop_idx"), 2)
        self.assertEqual(ans.get("selected_model"), "gemma2:2b")

    def test_inputs_hash_uses_prompt_arg_not_call_result(self):
        """The helper hashes the `prompt` argument so the row's
        inputs_hash is the input fingerprint (not the LLM output).
        Replay needs this to detect "same inputs, different outcome".
        """
        from core.reasoning.trace_schema import compute_inputs_hash
        expected = compute_inputs_hash("the prompt", system="")
        text, rows = self._run(lambda: "any response", prompt="the prompt")
        self.assertIn(expected, rows[0]["query"])

    def test_latency_recorded(self):
        import time
        def slow():
            time.sleep(0.02)
            return "done"
        text, rows = self._run(slow)
        # latency_ms / 1000 → elapsed_sec; allow generous lower bound
        self.assertGreaterEqual(rows[0]["elapsed_sec"], 0.015)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
