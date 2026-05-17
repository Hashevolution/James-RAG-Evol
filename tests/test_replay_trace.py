"""L2 — replay_trace round-trip + trace_id isolation.

ARCHITECTURE.md §5.7.2 trace-replay invariant: the full reasoning trace
must be reconstructable from audit_log rows alone. This test pins that
contract — emit_trace_step writes rows, replay() reads them back, and
the dataclass field shape survives the round-trip.
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


def _emit_with_trace_id(db: str, trace_id: str, **step_kwargs):
    """Helper: emit one TraceStep with extras={"trace_id": trace_id}.
    Mirrors what trace_helpers.trace_synth_call does in production.
    """
    from core.reasoning.trace_schema import TraceStep, emit_trace_step
    step = TraceStep(**step_kwargs)
    extras = {"trace_id": trace_id} if trace_id else None
    emit_trace_step(step, db_path=db, extras=extras)


class ReplayRoundTripTests(unittest.TestCase):

    def test_empty_db_returns_empty_list(self):
        from scripts.replay_trace import replay
        db = _fresh_db()
        self.assertEqual(replay("any-id", db_path=db), [])

    def test_no_matching_trace_id_returns_empty_list(self):
        from scripts.replay_trace import replay
        db = _fresh_db()
        _emit_with_trace_id(
            db, "trace-A",
            stage="reflect", backend_id="ollama_local",
            parent_step_id="", inputs_hash="aaaa",
            output_summary="ok", applied_rule="reasoning.reflect.test",
        )
        self.assertEqual(replay("trace-B", db_path=db), [])

    def test_single_step_round_trip(self):
        from scripts.replay_trace import replay
        db = _fresh_db()
        _emit_with_trace_id(
            db, "trace-x",
            stage="synth", backend_id="ollama_local",
            parent_step_id="", inputs_hash="hash01",
            output_summary="hello world",
            applied_rule="reasoning.synth.chat",
            latency_ms=42,
        )
        steps = replay("trace-x", db_path=db)
        self.assertEqual(len(steps), 1)
        s = steps[0]
        self.assertEqual(s["stage"], "synth")
        self.assertEqual(s["backend_id"], "ollama_local")
        self.assertEqual(s["inputs_hash"], "hash01")
        self.assertEqual(s["output_summary"], "hello world")
        self.assertEqual(s["applied_rule"], "reasoning.synth.chat")
        self.assertEqual(s["latency_ms"], 42)
        self.assertFalse(s["blocked"])
        # extra columns merged from the row
        self.assertIn("timestamp", s)
        self.assertEqual(s["user_role"], "system")

    def test_multiple_steps_chronological(self):
        from scripts.replay_trace import replay
        db = _fresh_db()
        for stage, summary in [
            ("plan",    "decomposed 3 subtasks"),
            ("retrieve", "8 docs"),
            ("rerank",   "top 3 reranked"),
            ("synth",    "final answer"),
        ]:
            _emit_with_trace_id(
                db, "trace-multi",
                stage=stage, backend_id="ollama_local",
                parent_step_id="", inputs_hash=f"h-{stage}",
                output_summary=summary,
                applied_rule=f"reasoning.{stage}.test",
            )
        steps = replay("trace-multi", db_path=db)
        self.assertEqual([s["stage"] for s in steps],
                         ["plan", "retrieve", "rerank", "synth"])

    def test_isolation_between_traces(self):
        from scripts.replay_trace import replay
        db = _fresh_db()
        for tid in ("trace-A", "trace-B", "trace-A", "trace-C"):
            _emit_with_trace_id(
                db, tid,
                stage="synth", backend_id="ollama_local",
                parent_step_id="", inputs_hash=f"h-{tid}",
                output_summary="ok",
                applied_rule="reasoning.synth.test",
            )
        a_steps = replay("trace-A", db_path=db)
        b_steps = replay("trace-B", db_path=db)
        c_steps = replay("trace-C", db_path=db)
        self.assertEqual(len(a_steps), 2)
        self.assertEqual(len(b_steps), 1)
        self.assertEqual(len(c_steps), 1)

    def test_error_row_marked_blocked(self):
        from scripts.replay_trace import replay
        db = _fresh_db()
        _emit_with_trace_id(
            db, "trace-err",
            stage="synth", backend_id="ollama_local",
            parent_step_id="", inputs_hash="hf",
            output_summary="", applied_rule="reasoning.synth.chat",
            error="timeout",
        )
        steps = replay("trace-err", db_path=db)
        self.assertEqual(len(steps), 1)
        self.assertTrue(steps[0]["blocked"])
        self.assertEqual(steps[0]["error"], "timeout")

    def test_include_extras_surfaces_non_schema_fields(self):
        from scripts.replay_trace import replay
        db = _fresh_db()
        # Inject a row directly with custom fields in the answer JSON
        # (trace_helpers.py supports caller-supplied extras via the
        # same path).
        from core.reasoning.trace_schema import TraceStep, emit_trace_step
        step = TraceStep(
            stage="reflect", backend_id="ollama_local",
            parent_step_id="", inputs_hash="hh",
            output_summary="revised draft",
            applied_rule="reasoning.reflect.revised",
        )
        emit_trace_step(step, db_path=db, extras={
            "trace_id":   "trace-extras",
            "loop_idx":   2,
            "model":      "gemma2:2b",
        })
        steps = replay("trace-extras", db_path=db, include_extras=True)
        self.assertEqual(len(steps), 1)
        self.assertIn("extras", steps[0])
        self.assertEqual(steps[0]["extras"]["loop_idx"], 2)
        self.assertEqual(steps[0]["extras"]["model"], "gemma2:2b")
        # trace_id is the correlation key — it surfaces via extras since
        # it is not a schema field
        self.assertEqual(steps[0]["extras"]["trace_id"], "trace-extras")

    def test_extras_omitted_by_default(self):
        from scripts.replay_trace import replay
        db = _fresh_db()
        _emit_with_trace_id(
            db, "trace-no-extras",
            stage="synth", backend_id="ollama_local",
            parent_step_id="", inputs_hash="h",
            output_summary="ok", applied_rule="reasoning.synth.chat",
        )
        steps = replay("trace-no-extras", db_path=db)
        self.assertNotIn("extras", steps[0])

    def test_non_reason_rows_ignored(self):
        """audit_log carries tool: / attack: / system: rows alongside
        reason:* — replay() must only return reasoning rows.
        """
        from scripts.replay_trace import replay
        from core.audit_bridge import mirror_to_audit_db
        db = _fresh_db()
        # one reason row with trace-mix
        _emit_with_trace_id(
            db, "trace-mix",
            stage="synth", backend_id="ollama_local",
            parent_step_id="", inputs_hash="h",
            output_summary="ok", applied_rule="reasoning.synth.chat",
        )
        # one tool row that ALSO mentions "trace_id" in its payload
        mirror_to_audit_db({
            "role": "admin", "layer": "router", "event": "TOOL_EXECUTED",
            "tool_used": "web_search",
            "trace_id": "trace-mix",   # deliberate noise
        }, db_path=db)
        steps = replay("trace-mix", db_path=db)
        # only the reasoning row comes back
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["stage"], "synth")


class RecentTraceListingTests(unittest.TestCase):

    def test_empty_db_returns_empty(self):
        from scripts.replay_trace import list_recent_trace_ids
        db = _fresh_db()
        self.assertEqual(list_recent_trace_ids(db_path=db), [])

    def test_buckets_by_trace_id_with_counts(self):
        from scripts.replay_trace import list_recent_trace_ids
        db = _fresh_db()
        for tid, count in [("trace-A", 3), ("trace-B", 1), ("trace-C", 2)]:
            for _ in range(count):
                _emit_with_trace_id(
                    db, tid,
                    stage="synth", backend_id="ollama_local",
                    parent_step_id="", inputs_hash="h",
                    output_summary="ok",
                    applied_rule="reasoning.synth.test",
                )
        buckets = list_recent_trace_ids(db_path=db)
        by_tid = {b["trace_id"]: b for b in buckets}
        self.assertEqual(by_tid["trace-A"]["step_count"], 3)
        self.assertEqual(by_tid["trace-B"]["step_count"], 1)
        self.assertEqual(by_tid["trace-C"]["step_count"], 2)

    def test_limit_applied(self):
        from scripts.replay_trace import list_recent_trace_ids
        db = _fresh_db()
        for i in range(5):
            _emit_with_trace_id(
                db, f"trace-{i}",
                stage="synth", backend_id="ollama_local",
                parent_step_id="", inputs_hash="h",
                output_summary="ok",
                applied_rule="reasoning.synth.test",
            )
        self.assertEqual(len(list_recent_trace_ids(limit=2, db_path=db)), 2)


class CliEntryPointTests(unittest.TestCase):
    """End-to-end via _main; ensures exit codes + --json flag work."""

    def test_main_exits_1_when_trace_not_found(self):
        from scripts.replay_trace import _main
        db = _fresh_db()
        rc = _main(["nonexistent-trace", "--db", db])
        self.assertEqual(rc, 1)

    def test_main_exits_0_when_trace_found(self):
        from scripts.replay_trace import _main
        db = _fresh_db()
        _emit_with_trace_id(
            db, "trace-cli",
            stage="synth", backend_id="ollama_local",
            parent_step_id="", inputs_hash="h",
            output_summary="ok",
            applied_rule="reasoning.synth.test",
        )
        rc = _main(["trace-cli", "--db", db])
        self.assertEqual(rc, 0)

    def test_main_recent_exits_0_when_empty(self):
        from scripts.replay_trace import _main
        db = _fresh_db()
        rc = _main(["--recent", "--db", db])
        self.assertEqual(rc, 0)

    def test_json_output_parses(self):
        from scripts.replay_trace import _main
        import io
        db = _fresh_db()
        _emit_with_trace_id(
            db, "trace-json",
            stage="synth", backend_id="ollama_local",
            parent_step_id="", inputs_hash="h",
            output_summary="ok",
            applied_rule="reasoning.synth.test",
        )
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _main(["trace-json", "--json", "--db", db])
        payload = json.loads(buf.getvalue())
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["stage"], "synth")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
