"""Observability — trace_id ContextVar + log_stage JSONL — #47 phase 1.

Coverage:
  - `start_trace()` issues a non-empty id, sets ContextVar
  - `get_trace_id()` returns "" outside a tracked context
  - `log_stage()` is a no-op when no trace is active (defensive)
  - `log_stage()` writes one JSONL line per call, with trace_id + stage
    + ts_ns + arbitrary fields, using the date-partitioned per-trace
    file path
  - `read_trace()` round-trips the lines back as dicts
  - non-JSON-serialisable field values are coerced via `default=str`
    (a stale `repr()` must never crash the request path)
  - Source-level contracts:
      * server_llmwiki.py /query/ calls `start_trace()` + `log_stage("auth")`
        + `log_stage("complete")`, and the response carries `trace_id`
      * pipeline.py emits `retrieve` / `graph` / `answer` stages

Run:
  python -m unittest tests.test_observability
  python tests/test_observability.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TraceContextTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a fresh trace root + a fresh ContextVar copy.
        # ContextVar leaks across tests within one process otherwise.
        from core.observability import set_trace_root, current_trace_id
        self._tmp = tempfile.TemporaryDirectory()
        set_trace_root(Path(self._tmp.name))
        # Reset the var to default so a previous test's start_trace
        # doesn't leak into this one (set returns a Token but we
        # don't bother — empty default is the documented neutral state).
        current_trace_id.set("")

    def tearDown(self):
        from core.observability import set_trace_root
        set_trace_root(None)
        self._tmp.cleanup()

    def test_start_trace_returns_nonempty_id(self):
        from core.observability import start_trace, get_trace_id
        tid = start_trace()
        self.assertTrue(tid)
        self.assertEqual(get_trace_id(), tid)

    def test_get_trace_id_default_is_empty(self):
        from core.observability import get_trace_id
        self.assertEqual(get_trace_id(), "")

    def test_log_stage_no_op_outside_trace(self):
        from core.observability import log_stage
        # No active trace — log_stage must not raise and must not write.
        log_stage("retrieve", top_k=8)
        # Verify nothing landed in the trace root.
        root = Path(self._tmp.name)
        files = list(root.rglob("*.jsonl"))
        self.assertEqual(files, [])

    def test_log_stage_writes_jsonl_for_active_trace(self):
        from core.observability import start_trace, log_stage, read_trace
        tid = start_trace()
        log_stage("retrieve", top_k=8, top_vector_score=0.82)
        log_stage("graph", entities_extracted=3, paths_walked=15)

        # File partitioned by today's date.
        day = datetime.now().strftime("%Y-%m-%d")
        path = Path(self._tmp.name) / day / f"{tid}.jsonl"
        self.assertTrue(path.exists(), f"trace file not created at {path}")

        rows = read_trace(tid)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["stage"], "retrieve")
        self.assertEqual(rows[0]["top_k"], 8)
        self.assertEqual(rows[0]["top_vector_score"], 0.82)
        self.assertEqual(rows[1]["stage"], "graph")
        self.assertEqual(rows[1]["paths_walked"], 15)
        # Every row carries trace_id + ts_ns
        for row in rows:
            self.assertEqual(row["trace_id"], tid)
            self.assertIn("ts_ns", row)
            self.assertIsInstance(row["ts_ns"], int)

    def test_log_stage_coerces_non_json_values(self):
        # A future caller passing a Path / Decimal / dataclass must not
        # crash the request — log_stage uses default=str.
        from core.observability import start_trace, log_stage, read_trace
        from pathlib import Path as _P
        tid = start_trace()
        log_stage("custom", a_path=_P("/tmp/foo.txt"), a_set={1, 2, 3})
        rows = read_trace(tid)
        self.assertEqual(len(rows), 1)
        # Path coerces to its str form; set coerces to its repr form.
        # We don't pin exact strings (platform-dependent) — just that
        # it serialised without exception and round-tripped as text.
        self.assertIsInstance(rows[0]["a_path"], str)
        self.assertIsInstance(rows[0]["a_set"], str)


class EdgeContractTests(unittest.TestCase):
    """Source-level: the API edge + pipeline must call into observability.

    Same pattern as test_policy_quarantine.py / test_query_include_contexts.py.
    A future refactor that drops the trace_id wiring needs a conscious decision.
    """

    def test_query_endpoint_starts_trace(self):
        import server_llmwiki as srv
        import inspect
        src = inspect.getsource(srv)
        self.assertIn("start_trace()", src,
                      "/query/ must issue a trace_id at edge — see #47 phase 1")
        self.assertIn('log_stage("auth"', src,
                      "/query/ must log auth stage")
        self.assertIn('log_stage("complete"', src,
                      "/query/ must log complete stage at request end")
        self.assertIn('"trace_id":      trace_id', src,
                      "/query/ response must carry trace_id so users can quote it")

    def test_pipeline_emits_three_core_stages(self):
        import core.reasoning.pipeline as pipeline_mod
        import inspect
        src = inspect.getsource(pipeline_mod)
        # Whitespace-insensitive substring: the stage name appears
        # inside a log_stage() call. This is the chokepoint — a future
        # refactor that swaps log_stage() for a different observability
        # primitive will fail here and a reviewer will consciously
        # update the contract.
        normalized = " ".join(src.split())
        for stage in ("retrieve", "graph", "answer"):
            self.assertIn(f'log_stage( "{stage}",', normalized,
                          f"pipeline.py must emit log_stage({stage!r}, ...)")
        self.assertIn("from core.observability import log_stage", src,
                      "pipeline.py must import log_stage")


class TraceFileLayoutTests(unittest.TestCase):
    """The reports/trace/<YYYY-MM-DD>/<trace_id>.jsonl path is part of
    the contract — a phase-2 reader (`/admin/trace/{id}` endpoint) and
    operators looking at disk both depend on it."""

    def setUp(self):
        from core.observability import set_trace_root, current_trace_id
        self._tmp = tempfile.TemporaryDirectory()
        set_trace_root(Path(self._tmp.name))
        current_trace_id.set("")

    def tearDown(self):
        from core.observability import set_trace_root
        set_trace_root(None)
        self._tmp.cleanup()

    def test_date_partitioned_directory(self):
        from core.observability import start_trace, log_stage
        tid = start_trace()
        log_stage("smoke")
        day = datetime.now().strftime("%Y-%m-%d")
        path = Path(self._tmp.name) / day
        self.assertTrue(path.is_dir(),
                        f"date-partition dir not created: {path}")
        contents = list(path.glob("*.jsonl"))
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0].name, f"{tid}.jsonl")

    def test_jsonl_one_object_per_line(self):
        from core.observability import start_trace, log_stage
        tid = start_trace()
        log_stage("a", x=1)
        log_stage("b", y=2)
        log_stage("c", z=3)
        day = datetime.now().strftime("%Y-%m-%d")
        path = Path(self._tmp.name) / day / f"{tid}.jsonl"
        with path.open("r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(len(lines), 3)
        for line in lines:
            obj = json.loads(line)
            self.assertEqual(obj["trace_id"], tid)


class StdoutMirrorTests(unittest.TestCase):
    """JAMES_TRACE_STDOUT toggle — mirrors per-trace JSONL lines to
    stdout for the operator workflow. v2 default is ON (single-user
    operator setup is the dominant case); set =0/false/no to silence.
    The JSONL file write must never be affected by the mirror state."""

    def setUp(self):
        from core.observability import set_trace_root, current_trace_id
        self._tmp = tempfile.TemporaryDirectory()
        set_trace_root(Path(self._tmp.name))
        current_trace_id.set("")
        self._orig_env = os.environ.get("JAMES_TRACE_STDOUT")

    def tearDown(self):
        from core.observability import set_trace_root
        set_trace_root(None)
        self._tmp.cleanup()
        if self._orig_env is None:
            os.environ.pop("JAMES_TRACE_STDOUT", None)
        else:
            os.environ["JAMES_TRACE_STDOUT"] = self._orig_env

    def _capture_stdout(self, fn):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn()
        return buf.getvalue()

    def test_stdout_mirrors_by_default(self):
        # v2: env unset → mirror ON (operator workflow default).
        from core.observability import start_trace, log_stage
        os.environ.pop("JAMES_TRACE_STDOUT", None)
        captured = {}
        def run():
            captured["tid"] = start_trace()
            log_stage("retrieve", top_k=8)
        out = self._capture_stdout(run)
        self.assertIn("[trace ", out,
                      "v2 default must mirror to stdout when env unset")
        self.assertIn(captured["tid"][:8], out)

    def test_stdout_silent_when_explicitly_off(self):
        from core.observability import start_trace, log_stage
        for val in ("0", "false", "FALSE", "no"):
            os.environ["JAMES_TRACE_STDOUT"] = val
            def run():
                start_trace()
                log_stage("smoke")
            out = self._capture_stdout(run)
            self.assertEqual(out, "",
                             f"JAMES_TRACE_STDOUT={val!r} must silence mirror")

    def test_stdout_silent_when_empty_string(self):
        # Explicit empty string also silences — distinguishes "operator
        # set this to empty on purpose" from "env unset" (the latter
        # uses the default-on path).
        from core.observability import start_trace, log_stage
        os.environ["JAMES_TRACE_STDOUT"] = ""
        def run():
            start_trace()
            log_stage("smoke")
        out = self._capture_stdout(run)
        self.assertEqual(out, "",
                         "empty-string env must silence mirror")

    def test_stdout_mirrors_when_explicitly_on(self):
        from core.observability import start_trace, log_stage
        captured = {}
        for val in ("1", "true", "TRUE", "yes", "anything"):
            os.environ["JAMES_TRACE_STDOUT"] = val
            def run():
                captured["tid"] = start_trace()
                log_stage("retrieve", top_k=8, top_vector_score=0.82)
            out = self._capture_stdout(run)
            self.assertIn("[trace ", out, f"value {val!r} should enable mirror")
            self.assertIn(captured["tid"][:8], out)
            self.assertIn('"stage": "retrieve"', out)
            self.assertIn('"top_k": 8', out)

    def test_jsonl_still_written_when_mirror_silenced(self):
        # The mirror state must not affect JSONL file writes — silencing
        # the console must NOT silence the file (and vice versa).
        from core.observability import start_trace, log_stage, read_trace
        os.environ["JAMES_TRACE_STDOUT"] = "0"
        def run():
            tid = start_trace()
            log_stage("retrieve", top_k=8)
            return tid
        tid = None
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            tid = run()
        # Stdout silenced
        self.assertEqual(buf.getvalue(), "")
        # JSONL still written
        rows = read_trace(tid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stage"], "retrieve")
        self.assertEqual(rows[0]["top_k"], 8)


if __name__ == "__main__":
    unittest.main()
