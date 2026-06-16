"""Lock test for measurement-critical surfaces.

Operator catch v0.6.1 v18.2 (2026-06-16) — after the v17 meta regex
false-positive nearly polluted a paired measurement, the operator
asked: "앞으로 LLM 모델이나 추론 레이어 추가시 측정이 수시로 방해되지
않도록 격리가 보장되는가?".

This file is half of the two-layer answer (the other half is
``scripts/research/pre_flight_check.py``):

  Layer 1 — LOCK TEST (this file). Captures the exact set of
            (module, symbol, value) tuples that ``local_vs_cloud_paired.py``
            consumes. ANY change to that surface — adding a backend
            import, renaming a constant, moving a function, changing
            the fixture path — flips this test red. The PR author then
            either (a) updates this lock-test alongside the change AND
            re-runs the paired measurement, or (b) routes the change
            away from the measurement surface.

  Layer 2 — PRE-FLIGHT CHECK (scripts/research/pre_flight_check.py).
            Runs each time the paired harness launches. Validates the
            live state (fixture SHA, regex sweep, backend registry,
            abstraction module) against the same baseline before any
            LLM call goes out.

Coverage philosophy: this test is INTENTIONALLY brittle. A green run
means the measurement surface is byte-stable at the symbol level; a
red run means the operator MUST inspect the diff before trusting any
upcoming Quality Delta Card produced by ``local_vs_cloud_paired.py``.
"""
from __future__ import annotations

import hashlib
import importlib
import inspect
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Symbols paired_local_vs_cloud actually imports. If the harness's
# import list grows (a new module dependency lands), this set MUST be
# updated in the SAME PR that introduces the dependency.
_HARNESS_IMPORTS_REQUIRED = {
    # stdlib — listed for sanity; their presence is OS-level not
    # JAMES-level so the lock doesn't actually enforce these
    ("argparse", None),
    ("json", None),
    ("os", None),
    ("random", None),
    ("re", None),
    ("statistics", None),
    ("sys", None),
    ("time", None),
    ("urllib.request", None),
    # JAMES surface — these MUST stay stable for the paired path
    # to be valid. The harness imports them on demand inside the
    # call_cloud_via_abstraction function; we replicate the import
    # here to assert they resolve.
    ("core.abstraction", "default_decider"),
    ("core.abstraction", "run_cloud_egress"),
    ("core.reasoning.backends.claude_code_cli", "ClaudeCodeCliBackend"),
    # diffusiongemma branch — opt-in path in call_local. Listed so
    # removing the file would flip this test red, signaling that the
    # harness's --local-backend diffusiongemma_local flag silently
    # broke.
    ("core.reasoning.backends.diffusiongemma_local", "DiffusionGemmaLocalBackend"),
}


# Symbols + constants the harness exports at module top level.
# Renaming / moving any of these is a measurement-surface change.
_HARNESS_TOP_LEVEL_REQUIRED = {
    "FIXTURE",
    "RAW",
    "DEFAULT_LOCAL_MODEL",
    "OLLAMA_URL",
    "ANSWERABLE",
    "MAX_ART_CHARS",
    "MAX_CTX_CHARS",
    "NUM_CTX",
    "CAVEAT_BLOCK",
    "call_local",
    "call_cloud_via_abstraction",
    "judge",
    "_majority",
    "select_queries",
    "run_one_query",
    "aggregate",
    "main",
}


# Baseline values the harness uses on every paired run. Changing
# these silently rotates the comparison's units — e.g. NUM_CTX = 4096
# would silently truncate evidence between two runs, polluting any
# Quality Delta Card built across the change. Lock-test catches the
# rotation BEFORE the next measurement.
_HARNESS_BASELINE_VALUES = {
    "DEFAULT_LOCAL_MODEL": "gemma3:4b",
    "OLLAMA_URL":          "http://127.0.0.1:11434/api/generate",
    "ANSWERABLE":          ("inference_query", "comparison_query", "temporal_query"),
    "MAX_ART_CHARS":       7500,
    "MAX_CTX_CHARS":       16000,
    "NUM_CTX":             8192,
}


# Modules whose surface the paired harness consumes via abstraction
# (cloud egress) or backend protocol. Each entry pins the symbol name
# + whether it's callable. If a refactor renames any of these the
# harness silently breaks until the maintainer updates the import.
_DOWNSTREAM_SURFACE = {
    ("core.abstraction",                                "default_decider", "callable"),
    ("core.abstraction",                                "run_cloud_egress", "callable"),
    ("core.reasoning.backends.claude_code_cli",         "ClaudeCodeCliBackend", "class"),
    ("core.reasoning.backends.diffusiongemma_local",    "DiffusionGemmaLocalBackend", "class"),
    ("core.reasoning.backends",                         "CompletionResult", "class"),
    ("core.reasoning.backends",                         "register_backend", "callable"),
    ("core.reasoning.backends",                         "get_backend", "callable"),
    ("core.reasoning.backends",                         "list_backends", "callable"),
    # v0.6.1 v18.4 — thinking-mode contract. Production code (5 cognitive
    # stage call sites) + paired harness both honor JAMES_GEMMA4_E4B_THINK_OFF
    # via these three symbols. Losing any of them resurrects the v18.3
    # "27/27 empty response" failure mode.
    ("core.reasoning.think_policy",                     "is_thinking_capable", "callable"),
    ("core.reasoning.think_policy",                     "_flag_active", "callable"),
    ("core.reasoning.think_policy",                     "think_for_stage", "callable"),
}


def _import_harness():
    """Pull the paired harness as a module without running main().

    The harness lives at scripts/research/local_vs_cloud_paired.py.
    importlib can load it by path so we stay decoupled from any
    sys.path manipulation main() may want to do at run time.
    """
    repo_root = Path(__file__).resolve().parent.parent
    harness_path = repo_root / "scripts" / "research" / "local_vs_cloud_paired.py"
    spec = importlib.util.spec_from_file_location(
        "local_vs_cloud_paired", harness_path,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["local_vs_cloud_paired"] = mod
    spec.loader.exec_module(mod)
    return mod


class MeasurementSurfaceLockTest(unittest.TestCase):
    """Every assertion here is a deliberate brittle check. Failures
    are not "fix the test" prompts — they are "audit your change,
    re-run the paired baseline, then update this file" prompts.
    """

    def test_harness_module_loads(self):
        """The paired harness must load without side effects (no
        network, no model spinup). This is a smoke for the import
        itself, before the per-symbol checks below."""
        mod = _import_harness()
        self.assertTrue(hasattr(mod, "main"))

    def test_harness_top_level_symbols_present(self):
        """Every constant + function the paired path depends on must
        be a module-level attribute. Renaming flips this red."""
        mod = _import_harness()
        for sym in _HARNESS_TOP_LEVEL_REQUIRED:
            with self.subTest(symbol=sym):
                self.assertTrue(
                    hasattr(mod, sym),
                    f"measurement harness lost top-level symbol "
                    f"{sym!r} — paired path will break silently. "
                    f"Either restore the symbol or update this "
                    f"lock-test and re-run the paired baseline.",
                )

    def test_harness_baseline_values_unchanged(self):
        """Constants the harness uses across every paired run must
        match the recorded baseline. Drift = silent unit rotation
        between two Quality Delta Cards. Catching the drift here
        forces a deliberate paired re-baseline before promotion."""
        mod = _import_harness()
        for name, expected in _HARNESS_BASELINE_VALUES.items():
            with self.subTest(constant=name):
                actual = getattr(mod, name, None)
                self.assertEqual(
                    actual, expected,
                    f"measurement baseline drift: {name} changed "
                    f"from {expected!r} → {actual!r}. Any paired "
                    f"comparison spanning this change must be "
                    f"re-baselined. Update the expected value "
                    f"alongside a fresh n=3 paired run.",
                )

    def test_downstream_surface_intact(self):
        """JAMES modules the paired harness depends on (abstraction
        + backend registry + backend classes) must still expose the
        symbols by the name + kind the harness uses.

        Failure here means a refactor moved a symbol; either revert
        the move, give the harness an updated import, or fork the
        harness behind a feature flag. NEVER edit just the test."""
        for module_path, symbol, kind in _DOWNSTREAM_SURFACE:
            with self.subTest(module=module_path, symbol=symbol, kind=kind):
                try:
                    mod = importlib.import_module(module_path)
                except ImportError as e:
                    self.fail(
                        f"measurement-critical module {module_path!r} "
                        f"failed to import: {e}",
                    )
                attr = getattr(mod, symbol, None)
                self.assertIsNotNone(
                    attr,
                    f"{module_path}.{symbol} disappeared. Paired "
                    f"harness's call_cloud_via_abstraction will "
                    f"raise on the next run.",
                )
                if kind == "callable":
                    self.assertTrue(
                        callable(attr),
                        f"{module_path}.{symbol} is no longer callable "
                        f"(replaced with non-function value)",
                    )
                elif kind == "class":
                    self.assertTrue(
                        inspect.isclass(attr),
                        f"{module_path}.{symbol} is no longer a class",
                    )

    def test_call_local_honors_thinking_contract(self):
        """v0.6.1 v18.4 (2026-06-16) — harness's call_local must
        consult ``think_policy`` for thinking-capable models. Without
        this, gemma4:e4b produces 27/27 empty responses (the v18.3
        Path A baseline failure mode).

        We don't run the actual HTTP call here — instead, we inspect
        the harness source for the import + the conditional. A refactor
        that removes the integration trips this test before any
        operator reaches the empty-response cliff again.
        """
        harness_path = (
            Path(__file__).resolve().parent.parent
            / "scripts" / "research" / "local_vs_cloud_paired.py"
        )
        src = harness_path.read_text(encoding="utf-8")
        self.assertIn(
            "from core.reasoning.think_policy",
            src,
            "call_local stopped importing think_policy — the harness "
            "is back on the bypass path that produced 27/27 empty "
            "responses in v18.3. Restore the import or update the "
            "lock-test alongside a deliberate measurement-baseline "
            "change.",
        )
        self.assertIn(
            "is_thinking_capable(model)",
            src,
            "call_local stopped gating on is_thinking_capable — the "
            "harness no longer detects gemma4 family.",
        )
        self.assertIn(
            "\"think\"",
            src,
            "call_local stopped forwarding the think field to Ollama. "
            "gemma4:e4b will absorb num_predict on hidden thinking "
            "tokens again.",
        )

    def test_call_local_signature_stable(self):
        """call_local accepts the exact kwargs run_one_query passes
        + the new --local-backend dispatch parameter. If the harness's
        own parameter list changes, the dispatch breaks silently and
        the paired runs measure unintended values."""
        mod = _import_harness()
        sig = inspect.signature(mod.call_local)
        params = sig.parameters
        required = {"prompt", "model", "timeout", "local_backend"}
        missing = required - set(params)
        self.assertFalse(
            missing,
            f"call_local missing measurement-critical kwargs: {missing}. "
            f"The harness's run_one_query call site will fail with "
            f"TypeError on the next paired run.",
        )
        # local_backend MUST default to "ollama" so a stock paired run
        # keeps producing measurements against the historical baseline.
        self.assertEqual(
            params["local_backend"].default, "ollama",
            "call_local(local_backend=...) default changed away from "
            "'ollama'. Existing paired baselines are no longer "
            "reproducible without --local-backend explicit on the CLI.",
        )

    def test_judge_signature_stable(self):
        """judge(question, ctx, ans_a, ans_b, timeout) — Direction α
        evidence-grounded grader. Argument-order rotation here flips
        which candidate gets which verdict label. The blind A/B
        guard upstream cancels the bias, but mis-counting verdicts
        is still a regression."""
        mod = _import_harness()
        sig = inspect.signature(mod.judge)
        params = list(sig.parameters)
        expected_prefix = ["question", "evidence", "ans_a", "ans_b"]
        self.assertEqual(
            params[:4], expected_prefix,
            f"judge signature drifted: {params[:4]!r} vs expected "
            f"{expected_prefix!r}. Verdict labeling changed shape — "
            f"any paired card produced after this change is "
            f"non-comparable to prior cards without manual remap.",
        )

    def test_diffusiongemma_default_off(self):
        """The DiffusionGemma backend is opt-in. Activation default
        flip is a measurement-baseline change that needs an explicit
        Quality Delta Card per CLAUDE.md rule #2. This test makes
        the flip impossible to land accidentally."""
        # Snapshot the actual env value before clearing — the test
        # must not depend on the operator's interactive shell state.
        prior = os.environ.pop("JAMES_ENABLE_DIFFUSIONGEMMA", None)
        try:
            # Re-import the backend registry with the env cleared.
            # Already-imported registry caches the previous state, so
            # we inspect the file source directly: it must require the
            # env literal "1" for registration.
            import core.reasoning.backends as backends
            src = Path(backends.__file__).read_text(encoding="utf-8")
            self.assertIn(
                'JAMES_ENABLE_DIFFUSIONGEMMA',
                src,
                "registry no longer mentions JAMES_ENABLE_DIFFUSIONGEMMA — "
                "did someone remove the opt-in gate?",
            )
            self.assertIn(
                'JAMES_ENABLE_DIFFUSIONGEMMA") == "1"',
                src,
                "DiffusionGemma opt-in gate weakened. The env value "
                "MUST equal the literal '1' so accidental "
                "truthy strings (e.g. 'true', 'yes') do not flip the "
                "default and shift the measurement baseline.",
            )
        finally:
            if prior is not None:
                os.environ["JAMES_ENABLE_DIFFUSIONGEMMA"] = prior


class FixtureLockTest(unittest.TestCase):
    """The fixture file is the input the harness compares against.
    A silent edit invalidates every Quality Delta Card produced on
    either side of the change. We don't pin the entire SHA here —
    additions to the fixture are legitimate (new questions surface as
    new measurement runs). Instead we lock the SCHEMA + counts so the
    paired path keeps reading what it expects.
    """

    @classmethod
    def setUpClass(cls):
        # Force the path-based import so the test class can run alone
        # (unittest.main without the earlier class running).
        _import_harness()

    def test_fixture_exists(self):
        from local_vs_cloud_paired import FIXTURE
        self.assertTrue(
            FIXTURE.exists(),
            f"paired fixture missing: {FIXTURE}. The harness will "
            f"fail before producing any row.",
        )

    def test_fixture_has_answerable_rows(self):
        """Each answerable question_type must have ≥ n_per_type × 3
        rows so the default run (n_per_type=3) is reproducible."""
        import json as _json
        from local_vs_cloud_paired import FIXTURE, ANSWERABLE
        data = _json.loads(FIXTURE.read_text(encoding="utf-8"))
        queries = data.get("queries", [])
        for t in ANSWERABLE:
            with self.subTest(question_type=t):
                rows = [q for q in queries if q.get("question_type") == t]
                self.assertGreaterEqual(
                    len(rows), 9,
                    f"answerable question_type {t!r} only has "
                    f"{len(rows)} rows — paired default needs 9.",
                )

    def test_fixture_query_records_have_required_fields(self):
        """Every query record must carry id + text + question_type so
        the harness's select_queries can shape rows."""
        import json as _json
        from local_vs_cloud_paired import FIXTURE
        data = _json.loads(FIXTURE.read_text(encoding="utf-8"))
        for i, q in enumerate(data.get("queries", [])[:50]):
            with self.subTest(index=i):
                for field in ("id", "text", "question_type"):
                    self.assertIn(
                        field, q,
                        f"query #{i} missing field {field!r} — "
                        f"paired harness will fail on this record.",
                    )


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
