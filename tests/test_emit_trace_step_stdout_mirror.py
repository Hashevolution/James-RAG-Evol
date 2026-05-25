"""v0.4 Sprint 3 BL-1 — emit_trace_step stdout mirror contract.

Before BL-1, the cognitive layer's planner / reflect / verify
stages wrote rows to the audit_log table only — there was no
stdout signal, so an operator debugging a live run had to query
the SQLite DB to see what each stage did. The synth path mirrored
some events via observability.emit_step but the four reasoning
stages went silent.

BL-1 added a stdout mirror inside emit_trace_step itself so every
caller (synth + reflect + verify + planner + retrieve + ...) gets
the same single-line `[reason:<stage>] …` console signal under the
JAMES_TRACE_STDOUT convention (default ON; "0"/"false"/"no" off).

This test pins three guarantees:

  1. With JAMES_TRACE_STDOUT unset (default), emit_trace_step
     prints a `[reason:<stage>]` line to stdout.
  2. With JAMES_TRACE_STDOUT=0 / false / no, no print happens.
  3. The audit_log DB mirror is unaffected — stdout is additive,
     not a replacement.

Pinning prevents a refactor that silences the mirror (or makes it
opt-in only) from regressing the operator debugging surface.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.reasoning.trace_schema import (  # noqa: E402
    TraceStep,
    emit_trace_step,
)


class TraceStepStdoutMirrorTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._orig_env = os.environ.get("JAMES_TRACE_STDOUT")

    @classmethod
    def tearDownClass(cls):
        if cls._orig_env is None:
            os.environ.pop("JAMES_TRACE_STDOUT", None)
        else:
            os.environ["JAMES_TRACE_STDOUT"] = cls._orig_env

    def _emit_capture(self, step: TraceStep, extras=None) -> str:
        """Run emit_trace_step with the audit-log mirror stubbed out
        (returns True without touching SQLite) and capture stdout.

        The audit_bridge.mirror_to_audit_db patch keeps the test
        hermetic — no SQLite write, no DB schema dependency."""
        buf = io.StringIO()
        with patch("core.audit_bridge.mirror_to_audit_db", return_value=True), \
             redirect_stdout(buf):
            ok = emit_trace_step(step, extras=extras)
        return buf.getvalue(), ok

    def test_default_on_prints_stage_marker(self):
        """JAMES_TRACE_STDOUT unset → mirror prints (default ON)."""
        os.environ.pop("JAMES_TRACE_STDOUT", None)
        step = TraceStep(
            stage="reflect",
            backend_id="ollama_local",
            parent_step_id="",
            inputs_hash="abcdef0123456789",
            output_summary="Critique returned 3 issues.",
            applied_rule="reflect.loop",
            latency_ms=420,
        )
        out, ok = self._emit_capture(step)
        self.assertTrue(ok, "audit mirror return should propagate")
        self.assertIn("[reason:reflect]", out,
            "Default ON behaviour: stdout must carry the stage marker. "
            "JAMES_TRACE_STDOUT semantics match observability.emit_step.")
        self.assertIn("reflect.loop", out, "applied_rule should appear")
        self.assertIn("ollama_local", out, "backend_id should appear")
        self.assertIn("420ms", out, "latency_ms should appear")

    def test_off_with_zero_silences(self):
        os.environ["JAMES_TRACE_STDOUT"] = "0"
        step = TraceStep(
            stage="verify",
            backend_id="ollama_local",
            parent_step_id="",
            inputs_hash="0000000000000000",
            output_summary="",
            applied_rule="verify.fact_check",
            latency_ms=100,
        )
        out, _ok = self._emit_capture(step)
        self.assertEqual(out, "",
            "JAMES_TRACE_STDOUT=0 must silence the mirror — operator's "
            "preferred CI / log-pipeline setup relies on this.")

    def test_off_with_false_and_no_silences(self):
        """Both 'false' and 'no' should silence — matches the
        observability.emit_step convention. Empty string also off."""
        for val in ("false", "FALSE", "no", "NO", ""):
            with self.subTest(val=val):
                os.environ["JAMES_TRACE_STDOUT"] = val
                step = TraceStep(
                    stage="plan",
                    backend_id="ollama_local",
                    parent_step_id="",
                    inputs_hash="1111111111111111",
                    output_summary="",
                    applied_rule="plan.decompose",
                    latency_ms=50,
                )
                out, _ok = self._emit_capture(step)
                self.assertEqual(out, "",
                    f"JAMES_TRACE_STDOUT={val!r} must silence mirror")

    def test_error_field_surfaced(self):
        """When a stage records an error, the mirror should make it
        visible in the same line — saves an operator from grepping
        the audit_log to see why a stage failed."""
        os.environ["JAMES_TRACE_STDOUT"] = "1"
        step = TraceStep(
            stage="verify",
            backend_id="ollama_local",
            parent_step_id="",
            inputs_hash="2222222222222222",
            output_summary="",
            applied_rule="verify.fact_check",
            latency_ms=999,
            error="backend reported error string",
        )
        out, _ok = self._emit_capture(step)
        self.assertIn("[reason:verify]", out)
        self.assertIn("err=backend reported error string", out,
            "Error text should appear inline (truncated to 60 chars).")

    def test_trace_id_in_extras_surfaces(self):
        """The synth path passes the Axis-3 trace_id via extras;
        the mirror should include the short prefix so the operator
        can correlate stdout lines back to a single request."""
        os.environ["JAMES_TRACE_STDOUT"] = "1"
        step = TraceStep(
            stage="synth",
            backend_id="ollama_local",
            parent_step_id="",
            inputs_hash="3333333333333333",
            output_summary="",
            applied_rule="reasoning.synth.rag",
            latency_ms=1200,
        )
        out, _ok = self._emit_capture(step, extras={
            "trace_id": "deadbeefcafebabe0011223344556677",
        })
        self.assertIn("[trace deadbeef]", out,
            "Short trace_id prefix (8 chars) should appear so the "
            "operator can grep one request across multiple stages.")

    def test_audit_mirror_runs_regardless_of_stdout_setting(self):
        """stdout silence must NOT skip the audit DB mirror — the two
        observability layers are independent. Pinning here so a
        future short-circuit ("skip emit if stdout off") doesn't
        accidentally drop the DB row too."""
        os.environ["JAMES_TRACE_STDOUT"] = "0"
        step = TraceStep(
            stage="retrieve",
            backend_id="vector_store",
            parent_step_id="",
            inputs_hash="4444444444444444",
            output_summary="",
            applied_rule="retrieve.dense",
            latency_ms=10,
        )
        with patch("core.audit_bridge.mirror_to_audit_db",
                   return_value=True) as mock_mirror:
            ok = emit_trace_step(step)
        self.assertTrue(ok)
        self.assertEqual(mock_mirror.call_count, 1,
            "audit_log mirror must run once regardless of stdout setting")


if __name__ == "__main__":
    unittest.main()
