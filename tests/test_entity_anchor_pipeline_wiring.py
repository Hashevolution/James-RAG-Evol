"""F9.3 — pipeline STEP 0.5a entity anchor wiring contract tests.

Pins the flag-gated wiring between ``apply_entity_anchor_expansion``
(``core/reasoning/pipeline_query_expansion.py``) and the
``EntityAnchorExpander`` module that lands at F9.2:

  * ``JAMES_ENABLE_ENTITY_ANCHOR`` flag OFF → expander NEVER called,
    returned ``query_for_rewriter`` is byte-identical to the input
    ``safe_query``, no trace step emitted
  * Flag ON + expander hit → query_for_rewriter carries the
    anchor-augmented form, trace step emitted with the right
    ``applied_rule`` + ``anchors_added`` in extras
  * Flag ON + expander miss → query_for_rewriter falls back to
    safe_query unchanged, no trace step emitted (hit=False signals
    no useful work to record)
  * Flag ON + expander raises → fallback to safe_query, error logged
    via ``engine._log``, pipeline does not abort

Companion to:
  * ``test_entity_anchor_expander.py`` — the F9.2 module-level
    contract tests
  * ``test_query_rewriter_audit.py`` — the F9.1/F9.2 audit script
    A/B harness tests
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.reasoning.pipeline_query_expansion import (  # noqa: E402
    apply_entity_anchor_expansion,
)
from core.retrieval.entity_anchor_expander import (  # noqa: E402
    ENV_FLAG,
    entity_anchor_enabled,
)


# ─── Env flag isolation ──────────────────────────────────────────────


class EntityAnchorFlagTests(unittest.TestCase):
    """``entity_anchor_enabled()`` env flag in isolation."""

    def setUp(self):
        self._saved = os.environ.get(ENV_FLAG)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_FLAG, None)
        else:
            os.environ[ENV_FLAG] = self._saved

    def test_unset_returns_false(self):
        os.environ.pop(ENV_FLAG, None)
        self.assertFalse(entity_anchor_enabled())

    def test_explicit_1_returns_true(self):
        os.environ[ENV_FLAG] = "1"
        self.assertTrue(entity_anchor_enabled())

    def test_truthy_string_other_than_1_returns_false(self):
        """Strict ``== "1"`` check matches the rewriter's pattern —
        ``true`` / ``on`` / ``yes`` do NOT enable the flag. Pins the
        contract so operators don't accidentally enable F9.3 with
        the wrong env value."""
        for val in ("0", "true", "yes", "on", "True", " 1 ", ""):
            os.environ[ENV_FLAG] = val
            self.assertFalse(
                entity_anchor_enabled(),
                f"value {val!r} should NOT enable the flag",
            )

    def test_env_flag_constant_matches_documented_name(self):
        """If this changes operators will mysteriously see no
        effect when they set the documented env var. Pinning the
        constant guards the documentation contract."""
        self.assertEqual(ENV_FLAG, "JAMES_ENABLE_ENTITY_ANCHOR")


# ─── apply_entity_anchor_expansion wiring ────────────────────────────


def _make_engine() -> MagicMock:
    """Minimal mock engine — only the methods the helper calls."""
    engine = MagicMock()
    engine._log    = MagicMock()
    engine._elapsed = MagicMock()
    return engine


class WiringFlagOffTests(unittest.TestCase):
    """Flag-OFF byte-identical invariant — the core regression guard."""

    def setUp(self):
        self._saved = os.environ.pop(ENV_FLAG, None)

    def tearDown(self):
        if self._saved is not None:
            os.environ[ENV_FLAG] = self._saved

    def test_flag_off_returns_safe_query_unchanged(self):
        engine = _make_engine()
        with patch(
            "core.retrieval.entity_anchor_expander.get_entity_anchor_expander"
        ) as mock_get:
            result = apply_entity_anchor_expansion(
                engine, "David Soria Parra가 누구야?", "user",
            )
        # Expander never called
        mock_get.assert_not_called()
        # Returned tuple = (query unchanged, [], False)
        self.assertEqual(result[0], "David Soria Parra가 누구야?")
        self.assertEqual(result[1], [])
        self.assertFalse(result[2])

    def test_flag_off_does_not_emit_trace(self):
        engine = _make_engine()
        with patch(
            "core.reasoning.trace_schema.emit_trace_step"
        ) as mock_emit:
            apply_entity_anchor_expansion(
                engine, "팔란티어의 CEO?", "user",
            )
        mock_emit.assert_not_called()

    def test_flag_off_no_elapsed_recorded(self):
        """``engine._elapsed`` is the timing breadcrumb the operator
        greps for in stdout. Under flag OFF the entire STEP 0.5a
        block is skipped — no timing row should fire."""
        engine = _make_engine()
        apply_entity_anchor_expansion(
            engine, "팔란티어의 CEO?", "user",
        )
        # Only fires inside the `if entity_anchor_enabled():` branch
        engine._elapsed.assert_not_called()


class WiringFlagOnHitTests(unittest.TestCase):
    """Flag-ON path — entity matched, anchor injected, trace emitted."""

    def setUp(self):
        self._saved = os.environ.get(ENV_FLAG)
        os.environ[ENV_FLAG] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_FLAG, None)
        else:
            os.environ[ENV_FLAG] = self._saved

    def test_hit_replaces_query_with_expanded(self):
        engine = _make_engine()
        with patch(
            "core.retrieval.entity_anchor_expander.get_entity_anchor_expander"
        ) as mock_get, patch(
            "core.reasoning.trace_schema.emit_trace_step"
        ):
            mock_get.return_value.expand.return_value = (
                "David Soria Parra가 누구야? (관련: MCP)",
                ["MCP"],
                True,
            )
            result = apply_entity_anchor_expansion(
                engine, "David Soria Parra가 누구야?", "user",
            )

        # The expander was called with the original safe_query
        mock_get.return_value.expand.assert_called_once_with(
            "David Soria Parra가 누구야?",
        )
        # Returned tuple carries the expanded form
        self.assertIn("(관련: MCP)", result[0])
        self.assertEqual(result[1], ["MCP"])
        self.assertTrue(result[2])

    def test_hit_emits_trace_with_correct_applied_rule(self):
        engine = _make_engine()
        with patch(
            "core.retrieval.entity_anchor_expander.get_entity_anchor_expander"
        ) as mock_get, patch(
            "core.reasoning.trace_schema.emit_trace_step"
        ) as mock_emit:
            mock_get.return_value.expand.return_value = (
                "팔란티어의 CEO? (관련: Alex Karp)",
                ["Alex Karp"],
                True,
            )
            apply_entity_anchor_expansion(
                engine, "팔란티어의 CEO?", "user",
            )

        mock_emit.assert_called_once()
        # First positional arg is the TraceStep dataclass — verify
        # its applied_rule is the F9.3 identifier so audit_log grep
        # works for the operator.
        trace_step = mock_emit.call_args[0][0]
        self.assertEqual(
            trace_step.applied_rule,
            "reasoning.retrieve.entity_anchor_expand",
        )
        # Stage is the existing "retrieve" stage (no schema change
        # required — F9.3 reuses the rewriter's stage convention).
        self.assertEqual(trace_step.stage, "retrieve")
        self.assertEqual(trace_step.backend_id, "graph_local")

    def test_hit_trace_extras_carry_anchor_list(self):
        engine = _make_engine()
        with patch(
            "core.retrieval.entity_anchor_expander.get_entity_anchor_expander"
        ) as mock_get, patch(
            "core.reasoning.trace_schema.emit_trace_step"
        ) as mock_emit:
            mock_get.return_value.expand.return_value = (
                "팔란티어? (관련: Alex Karp, Peter Thiel)",
                ["Alex Karp", "Peter Thiel"],
                True,
            )
            apply_entity_anchor_expansion(
                engine, "팔란티어?", "user",
            )

        extras = mock_emit.call_args[1]["extras"]
        self.assertEqual(extras["anchors_added"], ["Alex Karp", "Peter Thiel"])
        self.assertEqual(extras["anchor_count"], 2)
        self.assertEqual(extras["original_query"], "팔란티어?")
        self.assertIn("(관련:", extras["expanded_query"])


class WiringFlagOnMissTests(unittest.TestCase):
    """Flag-ON but no entity matched — fall through to safe_query."""

    def setUp(self):
        self._saved = os.environ.get(ENV_FLAG)
        os.environ[ENV_FLAG] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_FLAG, None)
        else:
            os.environ[ENV_FLAG] = self._saved

    def test_no_hit_returns_safe_query_unchanged(self):
        engine = _make_engine()
        with patch(
            "core.retrieval.entity_anchor_expander.get_entity_anchor_expander"
        ) as mock_get, patch(
            "core.reasoning.trace_schema.emit_trace_step"
        ):
            mock_get.return_value.expand.return_value = (
                "Foobar Baz는?", [], False,
            )
            result = apply_entity_anchor_expansion(
                engine, "Foobar Baz는?", "user",
            )

        self.assertEqual(result[0], "Foobar Baz는?")
        self.assertEqual(result[1], [])
        self.assertFalse(result[2])

    def test_no_hit_does_not_emit_trace(self):
        engine = _make_engine()
        with patch(
            "core.retrieval.entity_anchor_expander.get_entity_anchor_expander"
        ) as mock_get, patch(
            "core.reasoning.trace_schema.emit_trace_step"
        ) as mock_emit:
            mock_get.return_value.expand.return_value = (
                "Foobar?", [], False,
            )
            apply_entity_anchor_expansion(engine, "Foobar?", "user")

        # No hit → no useful work to record → no trace row
        mock_emit.assert_not_called()


class WiringFlagOnErrorTests(unittest.TestCase):
    """Flag-ON but expander raises — fall back to safe_query, log it."""

    def setUp(self):
        self._saved = os.environ.get(ENV_FLAG)
        os.environ[ENV_FLAG] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_FLAG, None)
        else:
            os.environ[ENV_FLAG] = self._saved

    def test_expander_exception_falls_back_to_safe_query(self):
        engine = _make_engine()
        with patch(
            "core.retrieval.entity_anchor_expander.get_entity_anchor_expander"
        ) as mock_get:
            mock_get.return_value.expand.side_effect = RuntimeError("xyz")
            result = apply_entity_anchor_expansion(
                engine, "David Soria Parra가 누구야?", "user",
            )

        # safe_query returned unchanged
        self.assertEqual(result[0], "David Soria Parra가 누구야?")
        self.assertEqual(result[1], [])
        self.assertFalse(result[2])
        # error went through engine._log under the "entity_anchor_expand" tag
        engine._log.assert_called_once()
        self.assertEqual(engine._log.call_args[0][0], "entity_anchor_expand")

    def test_expander_exception_does_not_emit_trace(self):
        engine = _make_engine()
        with patch(
            "core.retrieval.entity_anchor_expander.get_entity_anchor_expander"
        ) as mock_get, patch(
            "core.reasoning.trace_schema.emit_trace_step"
        ) as mock_emit:
            mock_get.return_value.expand.side_effect = RuntimeError("xyz")
            apply_entity_anchor_expansion(engine, "anything", "user")

        mock_emit.assert_not_called()


# ─── pipeline.py source contract ─────────────────────────────────────


class PipelineSourceContractTests(unittest.TestCase):
    """Structural smoke — pipeline.py invokes the helper at STEP 0.5a.

    Mirrors the existing structural-grep pattern (see
    ``tests/_pipeline_src.pipeline_source``). Catches regressions
    like someone deleting the helper call by accident.
    """

    def test_pipeline_imports_helper(self):
        from tests._pipeline_src import pipeline_source
        src = pipeline_source()
        self.assertIn(
            "from core.reasoning.pipeline_query_expansion import",
            src,
        )
        self.assertIn("apply_entity_anchor_expansion", src)

    def test_pipeline_step_0_5a_marker_present(self):
        """A grep-friendly marker that the F9.3 STEP 0.5a block
        exists. The exact comment string is the operator's grep
        target — pinning it here forces a deliberate update if it
        ever changes."""
        from tests._pipeline_src import pipeline_source
        src = pipeline_source()
        self.assertIn("STEP 0.5a", src)
        self.assertIn("entity anchor expansion", src)


if __name__ == "__main__":
    unittest.main()
