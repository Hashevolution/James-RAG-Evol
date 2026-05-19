"""L1 — trace_synth_call helper that wraps an LLM call with one emit.

After Track 1 PR-A wiring (2026-05-19) every synth call site routes
through this helper → ``resolve_backend_for_stage`` → backend registry
rather than calling ``RouterWrapper.call_gemma`` directly. STEP 7 stays
byte-identical when the default backend (``ollama_local``) runs; the
only observable change is one audit_log row per LLM round-trip plus
the ability to swap a backend via env at the per-stage level.

Tests:
  * happy path: backend text forwarded unchanged, one row emitted
  * RouterWrapper-style error string (`[Gemma 응답 없음]` etc.) in the
    backend's CompletionResult.text: still forwarded as text, but
    row's `error` is non-empty and `blocked=1` (matches the existing
    `answer.startswith("[Gemma 응답 없음]")` retry checks at call sites)
  * backend returns CompletionResult(error="..."): emitted as error
    row, helper returns the empty string (post-Track-1 R1 contract —
    backends never raise; they signal failure via `error=`)
  * empty / no-text result: forwarded as "", emitted as error row
  * trace_id ContextVar propagation: when set, appears in answer JSON
  * trace_id absent: helper still works, no trace_id key in row
  * extras: caller-supplied extras land in answer JSON alongside
    trace_id (without clobbering schema fields)
  * registry-level failure (unknown stage / no backends registered):
    emits an unresolved-backend error row and returns ""
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from typing import Callable, Optional
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.reasoning.backends import (  # noqa: E402
    CompletionResult,
    _REGISTRY,
    _clear_for_tests,
    register_backend,
)


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


class _CallbackBackend:
    """Test backend whose .complete() invokes a Python callable and
    wraps the result. Lets each test express its scenario in one line
    (``lambda: "the answer"``) while still going through the same
    backend → CompletionResult → emit flow that production uses.
    """

    backend_id = "test_synth_backend"

    def __init__(self, callback: Callable[[], object]):
        self._cb = callback
        self.last_call_kwargs: Optional[dict] = None

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        timeout: float = 60.0,
        model=None,
        use_cache: bool = True,
        **opts,
    ) -> CompletionResult:
        self.last_call_kwargs = dict(
            prompt=prompt, system=system, max_tokens=max_tokens,
            timeout=timeout, model=model, use_cache=use_cache, **opts,
        )
        try:
            raw = self._cb()
        except Exception as e:
            # R1: backends signal failure via error=, not by raising.
            return CompletionResult(
                text="",
                backend_id=self.backend_id,
                error=f"{type(e).__name__}: {str(e)[:200]}",
            )
        text = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
        return CompletionResult(text=text, backend_id=self.backend_id)


class TraceSynthCallTests(unittest.TestCase):
    """Each test points emit_trace_step at an isolated DB and registers
    a callback-driven backend under the per-stage env override so the
    helper resolves it deterministically.
    """

    def setUp(self):
        # Stash the real registry so the test doesn't bleed into real
        # ollama_local; restore in tearDown.
        self._saved_registry = dict(_REGISTRY)
        _clear_for_tests()
        self._saved_synth_env = os.environ.get("JAMES_BACKEND_SYNTH")
        os.environ["JAMES_BACKEND_SYNTH"] = "test_synth_backend"

    def tearDown(self):
        _clear_for_tests()
        for name, inst in self._saved_registry.items():
            register_backend(name, inst)
        if self._saved_synth_env is None:
            os.environ.pop("JAMES_BACKEND_SYNTH", None)
        else:
            os.environ["JAMES_BACKEND_SYNTH"] = self._saved_synth_env

    def _run(self, callback, *, applied_rule="reasoning.synth.test",
             user_role="employee", extras=None, prompt="hello"):
        """Register a callback backend and call trace_synth_call. The
        callback's return value becomes the backend's text; exceptions
        raised inside the callback are converted to an error result
        (the production R1 contract — backends do not raise on the
        user-facing path).
        """
        from core.reasoning.trace_helpers import trace_synth_call
        backend = _CallbackBackend(callback)
        register_backend("test_synth_backend", backend)
        db = _fresh_db()
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            text = trace_synth_call(
                prompt,
                applied_rule=applied_rule,
                user_role=user_role,
                extras=extras,
            )
        return text, _rows(db), backend

    def test_happy_path_text_forwarded_unchanged(self):
        text, rows, _ = self._run(lambda: "the answer is 42")
        self.assertEqual(text, "the answer is 42")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["endpoint"], "reason:synth")
        self.assertEqual(row["security_event"], "reasoning.synth.test")
        self.assertEqual(row["user_role"], "employee")
        self.assertFalse(row["blocked"])
        ans = json.loads(row["answer"])
        self.assertEqual(ans["output_summary"], "the answer is 42")
        # backend_id is encoded as the prefix of the `query` column
        # (``"<backend_id>: <inputs_hash>"``) per audit_bridge's existing
        # convention — see emit_trace_step's serialization.
        self.assertTrue(row["query"].startswith("test_synth_backend:"))

    def test_router_error_string_marked_error_but_text_forwarded(self):
        """Existing call sites still check answer.startswith("[Gemma 응답 없음]")
        to decide retry — the helper must NOT swallow that string when
        the backend chooses to surface it as plain text. The same string
        on the CompletionResult.text path produces an error row.
        """
        text, rows, _ = self._run(lambda: "[Gemma 응답 없음] timeout")
        self.assertTrue(text.startswith("[Gemma 응답 없음]"))   # forwarded as-is
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])
        ans = json.loads(rows[0]["answer"])
        self.assertIn("error", ans)

    def test_backend_exception_becomes_error_row_and_empty_return(self):
        """R1 of the Provider contract: backends do not raise on the
        user path. The callback backend converts a raised exception to
        CompletionResult(error=..., text=""); the helper then emits
        the error row and returns "" rather than re-raising.

        Pre-Track-1 the helper itself re-raised; that was the lambda-based
        contract. With the named-backend contract, the helper trusts R1
        and the call sites' "if not answer: …" fallbacks pick up the
        empty return.
        """
        text, rows, _ = self._run(
            lambda: (_ for _ in ()).throw(RuntimeError("ollama down"))
        )
        self.assertEqual(text, "")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])
        ans = json.loads(rows[0]["answer"])
        self.assertIn("RuntimeError", ans["error"])
        self.assertIn("ollama down", ans["error"])

    def test_empty_text_marked_error(self):
        text, rows, _ = self._run(lambda: "")
        self.assertEqual(text, "")
        self.assertTrue(rows[0]["blocked"])

    def test_none_return_handled_as_empty(self):
        text, rows, _ = self._run(lambda: None)
        self.assertEqual(text, "")
        self.assertTrue(rows[0]["blocked"])

    def test_trace_id_propagation(self):
        from core.observability import current_trace_id
        token = current_trace_id.set("test-trace-xyz")
        try:
            text, rows, _ = self._run(lambda: "ok")
        finally:
            current_trace_id.reset(token)
        ans = json.loads(rows[0]["answer"])
        self.assertEqual(ans.get("trace_id"), "test-trace-xyz")

    def test_no_trace_id_when_contextvar_unset(self):
        from core.observability import current_trace_id
        token = current_trace_id.set("")   # explicit empty
        try:
            text, rows, _ = self._run(lambda: "ok")
        finally:
            current_trace_id.reset(token)
        ans = json.loads(rows[0]["answer"])
        self.assertNotIn("trace_id", ans)

    def test_extras_folded_in_alongside_trace_id(self):
        from core.observability import current_trace_id
        token = current_trace_id.set("trace-extras")
        try:
            text, rows, _ = self._run(
                lambda: "ok",
                extras={"loop_idx": 2, "selected_model": "gemma2:2b"},
            )
        finally:
            current_trace_id.reset(token)
        ans = json.loads(rows[0]["answer"])
        self.assertEqual(ans.get("trace_id"), "trace-extras")
        self.assertEqual(ans.get("loop_idx"), 2)
        self.assertEqual(ans.get("selected_model"), "gemma2:2b")

    def test_inputs_hash_uses_prompt_arg(self):
        """The helper hashes the `prompt` argument so the row's
        inputs_hash is the input fingerprint. Replay needs this to
        detect "same inputs, different outcome".
        """
        from core.reasoning.trace_schema import compute_inputs_hash
        expected = compute_inputs_hash("the prompt", system="")
        text, rows, _ = self._run(lambda: "any response", prompt="the prompt")
        self.assertIn(expected, rows[0]["query"])

    def test_latency_recorded(self):
        import time
        def slow():
            time.sleep(0.02)
            return "done"
        text, rows, _ = self._run(slow)
        # The callback backend doesn't set latency_ms explicitly; the
        # helper falls back to wall-clock measurement. Generous lower
        # bound because the helper rounds to integer milliseconds and
        # the audit_log column is REAL seconds.
        self.assertGreaterEqual(rows[0]["elapsed_sec"], 0.015)

    def test_kwargs_forwarded_to_backend(self):
        """The new signature accepts timeout / max_tokens / model /
        use_cache as keyword arguments and forwards them to the
        backend's .complete() — the call-site rewrite at PR-A relies
        on this being byte-equivalent to the old lambda kwargs.
        """
        from core.reasoning.trace_helpers import trace_synth_call
        backend = _CallbackBackend(lambda: "ok")
        register_backend("test_synth_backend", backend)
        db = _fresh_db()
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            trace_synth_call(
                "p",
                applied_rule="reasoning.synth.test",
                user_role="employee",
                timeout=120,
                max_tokens=400,
                model="gemma3:12b",
                use_cache=False,
            )
        kwargs = backend.last_call_kwargs
        self.assertEqual(kwargs["timeout"], 120)
        self.assertEqual(kwargs["max_tokens"], 400)
        self.assertEqual(kwargs["model"], "gemma3:12b")
        self.assertEqual(kwargs["use_cache"], False)

    def test_unresolved_backend_emits_error_row_returns_empty(self):
        """Stage typo / empty registry → helper does not raise; it
        emits one error row tagged backend_id='<unresolved>' and
        returns "" so the caller's existing "if not answer:" fallback
        kicks in. Matches R1 at the helper boundary.
        """
        from core.reasoning.trace_helpers import trace_synth_call
        # Clear the registry so any stage resolution lands on KeyError.
        _clear_for_tests()
        db = _fresh_db()
        with patch("core.audit_bridge._DEFAULT_AUDIT_DB", db):
            text = trace_synth_call(
                "p",
                applied_rule="reasoning.synth.test",
                user_role="employee",
            )
        self.assertEqual(text, "")
        rows = _rows(db)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["blocked"])
        ans = json.loads(rows[0]["answer"])
        self.assertTrue(rows[0]["query"].startswith("<unresolved>:"))
        self.assertIn("backend_resolution", ans["error"])


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
