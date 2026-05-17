"""L0 — Frozen TraceStep dataclass + audit_bridge emit round-trip.

ARCHITECTURE.md §5.7.2 Reasoning backends + trace schema: every backend
writes one row of a fixed shape to the existing audit_log table. These
tests pin the shape so a future backend (Phase 1 PR-1 reranker, Phase
2 PR-5/-6 reflect/verify) can never silently drift the schema.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import sys
import tempfile
import unittest

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


class TraceStepDataclassTests(unittest.TestCase):
    """The 6 required fields exactly match the ARCHITECTURE.md
    §5.7.2 paragraph. Adding a field is a contract change."""

    def test_six_required_fields_present(self):
        from core.reasoning.trace_schema import TraceStep
        names = {f.name for f in dataclasses.fields(TraceStep)}
        # 6 from the architecture paragraph + 2 observability extras
        # (latency_ms, error) that don't appear in the contract.
        for required in ("stage", "parent_step_id", "backend_id",
                         "inputs_hash", "output_summary", "applied_rule"):
            self.assertIn(required, names,
                          f"required schema field {required!r} missing")

    def test_is_frozen(self):
        from core.reasoning.trace_schema import TraceStep
        s = TraceStep(stage="reflect", backend_id="ollama_local",
                      parent_step_id="", inputs_hash="abc",
                      output_summary="ok", applied_rule="reasoning.reflect")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            s.stage = "verify"   # type: ignore[misc]

    def test_unknown_stage_rejected(self):
        from core.reasoning.trace_schema import TraceStep
        with self.assertRaises(ValueError) as ctx:
            TraceStep(stage="hallucinate",
                      backend_id="ollama_local",
                      parent_step_id="", inputs_hash="x",
                      output_summary="y",
                      applied_rule="reasoning.x")
        self.assertIn("unknown reasoning stage", str(ctx.exception))

    def test_applied_rule_required_nonempty(self):
        from core.reasoning.trace_schema import TraceStep
        with self.assertRaises(ValueError):
            TraceStep(stage="reflect", backend_id="ollama_local",
                      parent_step_id="", inputs_hash="x",
                      output_summary="y", applied_rule="")

    def test_all_seven_stages_accepted(self):
        from core.reasoning.trace_schema import TraceStep, ALLOWED_STAGES
        # explicit list — if a future PR adds a stage, this test must
        # update too (i.e., adding a stage requires a deliberate edit
        # here, matching the "registry only" architecture rule).
        self.assertEqual(
            ALLOWED_STAGES,
            frozenset({"plan", "retrieve", "rerank", "reflect",
                       "verify", "tool", "synth"}),
        )
        for st in ALLOWED_STAGES:
            TraceStep(stage=st, backend_id="ollama_local",
                      parent_step_id="", inputs_hash="x",
                      output_summary="y",
                      applied_rule=f"reasoning.{st}")


class HelperFunctionTests(unittest.TestCase):

    def test_inputs_hash_deterministic_and_16_chars(self):
        from core.reasoning.trace_schema import compute_inputs_hash
        a = compute_inputs_hash("hello world", system="be helpful")
        b = compute_inputs_hash("hello world", system="be helpful")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 16)

    def test_inputs_hash_changes_with_system_or_prompt(self):
        from core.reasoning.trace_schema import compute_inputs_hash
        base = compute_inputs_hash("x", system="s")
        self.assertNotEqual(base, compute_inputs_hash("x", system="t"))
        self.assertNotEqual(base, compute_inputs_hash("y", system="s"))

    def test_truncate_summary(self):
        from core.reasoning.trace_schema import truncate_summary
        self.assertEqual(truncate_summary("abc", limit=10), "abc")
        self.assertEqual(truncate_summary("a" * 250), "a" * 200)
        self.assertEqual(truncate_summary(None), "")


class EmitRoundTripTests(unittest.TestCase):
    """emit_trace_step → mirror_to_audit_db → audit_log row.
    Pin the column mapping so L1's wiring step (and L2's replay tool)
    can rely on it.
    """

    def _emit(self, step_kwargs, **emit_kwargs):
        from core.reasoning.trace_schema import TraceStep, emit_trace_step
        db = _fresh_db()
        step = TraceStep(**step_kwargs)
        ok = emit_trace_step(step, db_path=db, **emit_kwargs)
        self.assertTrue(ok, "emit_trace_step returned False")
        rows = _rows(db)
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_endpoint_prefix_is_reason_stage(self):
        row = self._emit(dict(
            stage="reflect", backend_id="ollama_local",
            parent_step_id="root", inputs_hash="abcd0123",
            output_summary="revised", applied_rule="reasoning.reflect.revised",
            latency_ms=42,
        ))
        self.assertEqual(row["endpoint"], "reason:reflect")
        self.assertEqual(row["security_event"], "reasoning.reflect.revised")
        # backend_id + inputs_hash packed into searchable query column
        self.assertEqual(row["query"], "ollama_local: abcd0123")
        # latency_ms → elapsed_sec
        self.assertAlmostEqual(row["elapsed_sec"], 0.042, places=4)

    def test_answer_blob_has_parent_and_summary(self):
        row = self._emit(dict(
            stage="verify", backend_id="claude_code_cli",
            parent_step_id="step-42", inputs_hash="ffff",
            output_summary="answer looks correct",
            applied_rule="reasoning.verify.fact_checker",
        ))
        ans = json.loads(row["answer"])
        self.assertEqual(ans["parent_step_id"], "step-42")
        self.assertEqual(ans["output_summary"], "answer looks correct")
        self.assertNotIn("error", ans)
        self.assertFalse(row["blocked"])

    def test_error_marks_blocked_and_appears_in_answer(self):
        row = self._emit(dict(
            stage="synth", backend_id="ollama_local",
            parent_step_id="", inputs_hash="abc",
            output_summary="", applied_rule="reasoning.synth",
            error="timeout",
        ))
        self.assertTrue(row["blocked"])
        ans = json.loads(row["answer"])
        self.assertEqual(ans["error"], "timeout")

    def test_extras_folded_in_without_clobbering_schema(self):
        # Use a non-empty parent_step_id so we can prove the original
        # value survives (audit_bridge._resolve_answer drops empty
        # strings; the schema field still wins when present).
        row = self._emit(
            dict(stage="plan", backend_id="ollama_local",
                 parent_step_id="root", inputs_hash="x",
                 output_summary="3 subtasks",
                 applied_rule="reasoning.plan"),
            extras={"subtasks": ["a", "b", "c"],
                    # reserved field — must be ignored, not clobber column
                    "endpoint": "evil",
                    # schema field — must be ignored
                    "parent_step_id": "FORGED"},
        )
        # endpoint column stays the synthesized one
        self.assertEqual(row["endpoint"], "reason:plan")
        ans = json.loads(row["answer"])
        self.assertEqual(ans["parent_step_id"], "root")   # original wins
        self.assertEqual(ans["subtasks"], ["a", "b", "c"])

    def test_empty_parent_step_id_dropped_from_answer(self):
        """Replay-tool contract: an absent parent_step_id field means
        the step has no parent (root). audit_bridge._resolve_answer
        drops empty strings, so the row carries no parent_step_id key
        when the step is root.
        """
        row = self._emit(dict(
            stage="plan", backend_id="ollama_local",
            parent_step_id="", inputs_hash="x",
            output_summary="root subtask",
            applied_rule="reasoning.plan",
        ))
        ans = json.loads(row["answer"])
        self.assertNotIn("parent_step_id", ans)
        self.assertEqual(ans["output_summary"], "root subtask")

    def test_user_role_default_is_system(self):
        row = self._emit(dict(
            stage="rerank", backend_id="ollama_local",
            parent_step_id="", inputs_hash="x",
            output_summary="reordered", applied_rule="reasoning.rerank",
        ))
        self.assertEqual(row["user_role"], "system")

    def test_user_role_caller_supplied(self):
        row = self._emit(dict(
            stage="tool", backend_id="ollama_local",
            parent_step_id="", inputs_hash="x",
            output_summary="", applied_rule="reasoning.tool.web_search",
        ), user_role="employee")
        self.assertEqual(row["user_role"], "employee")

    def test_orchestrator_backend_id_default(self):
        """Orchestrator-level steps (no LLM call) emit with empty
        backend_id; the bridge query column shows 'orchestrator' so
        replay can distinguish from a real backend named ''.
        """
        row = self._emit(dict(
            stage="plan", backend_id="", parent_step_id="",
            inputs_hash="x", output_summary="",
            applied_rule="reasoning.plan",
        ))
        self.assertIn("orchestrator", row["query"])


class TraceStepToDictTests(unittest.TestCase):

    def test_round_trip(self):
        from core.reasoning.trace_schema import (
            TraceStep, trace_step_to_dict,
        )
        s = TraceStep(stage="verify", backend_id="ollama_local",
                      parent_step_id="p1", inputs_hash="abcd",
                      output_summary="ok",
                      applied_rule="reasoning.verify",
                      latency_ms=100, error="")
        d = trace_step_to_dict(s)
        self.assertEqual(d["stage"], "verify")
        self.assertEqual(d["latency_ms"], 100)
        # Replay tool will rebuild a TraceStep from this dict — must work.
        s2 = TraceStep(**d)
        self.assertEqual(s, s2)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
