"""Query-rewrite budget knob — and the invariant that it changes nothing.

`reports/research-runs/latency-decomposition-20260922.md` measured the
rewriter exhausting its 10 s budget on 65 of 78 queries: ~11 s/query
burned, the feature completing roughly one query in six, and
`baseline_6deca66.json` recording `JAMES_ENABLE_QUERY_REWRITE: '1'` for
a stage that mostly did not run.

The fix is a knob, not a new default. This repo's own invariant, stated
in `QueryRewriter.__init__`'s docstring for PR #461: *a research feature
ships with the experiment, not the wiring*. Whether 10 s is the wrong
number is for a paired run against `eval/qvt/baseline_6deca66.json` to
answer — so the job of these tests is to prove the knob exists **and
that with the env unset nothing moved**.

`resolve_timeout_s` is public on purpose: a run that silently used a
different budget than the one its artifact records is exactly the
failure mode this neighbourhood has been fixing (#1136 / #1137 / #1142).

Run:
  python -m unittest tests.test_query_rewrite_timeout_knob
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.retrieval import query_rewriter as qr  # noqa: E402

ENV = "JAMES_QUERY_REWRITE_TIMEOUT_S"


class _EnvGuard(unittest.TestCase):
    """Isolate the env var and the one-shot notice latch per test."""

    def setUp(self):
        self._prev = os.environ.get(ENV)
        os.environ.pop(ENV, None)
        qr._timeout_notice_emitted = False

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = self._prev
        qr._timeout_notice_emitted = False


class DefaultIsUnchangedTests(_EnvGuard):
    """The load-bearing half: this PR must be a no-op by default."""

    def test_env_unset_resolves_to_the_historical_default(self):
        self.assertEqual(qr.resolve_timeout_s(), 10.0)
        self.assertEqual(qr.DEFAULT_TIMEOUT_S, 10.0)

    def test_constructor_without_arguments_is_unchanged(self):
        self.assertEqual(qr.QueryRewriter()._timeout, qr.DEFAULT_TIMEOUT_S)

    def test_empty_and_whitespace_env_are_not_an_override(self):
        for raw in ("", "   ", "\t"):
            with self.subTest(raw=raw):
                os.environ[ENV] = raw
                self.assertEqual(qr.resolve_timeout_s(), 10.0)

    def test_no_notice_is_printed_when_nothing_is_overridden(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            qr.resolve_timeout_s()
        self.assertEqual(buf.getvalue(), "")


class OverrideTests(_EnvGuard):
    def test_env_override_is_honoured(self):
        os.environ[ENV] = "30"
        self.assertEqual(qr.resolve_timeout_s(), 30.0)
        self.assertEqual(qr.QueryRewriter()._timeout, 30.0)

    def test_float_values_work(self):
        os.environ[ENV] = "12.5"
        self.assertEqual(qr.resolve_timeout_s(), 12.5)

    def test_explicit_argument_beats_the_env(self):
        """A measurement arm that pins its own budget must not be
        silently re-pointed by whatever the operator left exported."""
        os.environ[ENV] = "30"
        self.assertEqual(qr.QueryRewriter(timeout=5.0)._timeout, 5.0)

    def test_override_announces_itself(self):
        os.environ[ENV] = "30"
        buf = io.StringIO()
        with redirect_stderr(buf):
            qr.resolve_timeout_s()
        out = buf.getvalue()
        self.assertIn("30.0", out)
        self.assertIn(ENV, out)


class MalformedInputTests(_EnvGuard):
    """Malformed values fall back — and say so. An operator who typed
    '30s' should not learn about it from a latency chart hours later."""

    def test_non_numeric_falls_back_and_reports(self):
        os.environ[ENV] = "30s"
        buf = io.StringIO()
        with redirect_stderr(buf):
            self.assertEqual(qr.resolve_timeout_s(), 10.0)
        self.assertIn("not a number", buf.getvalue())

    def test_non_positive_falls_back_and_reports(self):
        for raw in ("0", "-5"):
            with self.subTest(raw=raw):
                qr._timeout_notice_emitted = False
                os.environ[ENV] = raw
                buf = io.StringIO()
                with redirect_stderr(buf):
                    self.assertEqual(qr.resolve_timeout_s(), 10.0)
                self.assertIn("must be > 0", buf.getvalue())

    def test_notice_is_emitted_once_per_process(self):
        """A 20-query bench loop must not print 20 identical lines."""
        os.environ[ENV] = "30"
        buf = io.StringIO()
        with redirect_stderr(buf):
            for _ in range(5):
                qr.resolve_timeout_s()
        self.assertEqual(buf.getvalue().count(ENV), 1)


class MeasurementSurfaceTests(unittest.TestCase):
    """Pinned so a later refactor cannot make the budget invisible."""

    def test_resolver_is_public(self):
        self.assertTrue(hasattr(qr, "resolve_timeout_s"))
        self.assertFalse(qr.resolve_timeout_s.__name__.startswith("_"))

    def test_env_name_is_stable(self):
        self.assertEqual(qr._TIMEOUT_ENV, "JAMES_QUERY_REWRITE_TIMEOUT_S")


if __name__ == "__main__":
    unittest.main()
