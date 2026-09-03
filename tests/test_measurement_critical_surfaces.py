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
    "FIXTURES",                # v18.7 Phase 2 prereq — multi-fixture switch
    "ANSWERABLE_BY_FIXTURE",   # v18.7 — per-fixture answerable type list
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
    "_chat_prompt",            # v18.7 — chat fixture prompt template
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


# The paired fixture is a derivative of MultiHop-RAG, regenerated from
# an upstream download (`scripts/hotpot/download_multihop_rag.py` then
# `scripts/hotpot/build_fixture.py`), and `.gitignore:75` excludes
# `workspaces/hotpot_eval/eval/` as a "benchmark workspace cache
# (regeneratable from upstream fixture sources)".
#
# It therefore CANNOT exist on a CI runner: the build needs network
# access to a licensed dataset, unlike the LRB scenarios, which have
# stdlib-only deterministic builders and are rebuilt on demand by
# `tests/_lrb_fixtures.py`. Asserting its presence unconditionally made
# three of the five standing CI failures — a red that no PR could ever
# clear and that says nothing about the code under review.
#
# So the content locks below skip when the artifact is absent, and
# `FixturePathLockTest` keeps the part of the guard CI *can* enforce:
# that the harness still points at the path those locks describe. A
# rename would otherwise disarm the lock silently on exactly the runs
# where it is skipped.
#
# ⚠️ Consequence, stated rather than hidden: on CI the schema/count
# locks are INERT. They protect the operator machine, where the paired
# measurement actually runs and the fixture actually exists.
def _paired_fixture_path():
    """Return the harness's FIXTURE path (importing it if needed)."""
    _import_harness()
    from local_vs_cloud_paired import FIXTURE
    return FIXTURE


def _paired_fixture_present() -> bool:
    try:
        return _paired_fixture_path().exists()
    except Exception:                                  # pragma: no cover
        return False


_FIXTURE_SKIP_REASON = (
    "paired fixture workspaces/hotpot_eval/eval/multihop_rag_queries.json "
    "is absent (gitignored, regenerated from an upstream licensed "
    "download). Rebuild with scripts/hotpot/download_multihop_rag.py then "
    "scripts/hotpot/build_fixture.py to run the schema locks."
)


class FixturePathLockTest(unittest.TestCase):
    """Runs everywhere, including CI.

    The content locks below can only run where the fixture exists. This
    one pins the thing that is checkable without it — that the harness
    still reads the path they describe — so moving or renaming the
    fixture cannot silently pass on a runner that skips the rest.
    """

    def test_harness_fixture_path_is_the_locked_one(self):
        fixture = _paired_fixture_path()
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(
            fixture,
            root / "workspaces" / "hotpot_eval" / "eval"
                 / "multihop_rag_queries.json",
            "local_vs_cloud_paired.FIXTURE moved. The schema locks in "
            "FixtureLockTest describe the OLD path and skip when it is "
            "absent, so this rename would have disarmed them silently. "
            "Update both together, then re-run the paired measurement.",
        )

    def test_regeneration_path_still_exists(self):
        """The skip message tells an operator how to rebuild. If that
        script is gone the message is a dead end."""
        root = Path(__file__).resolve().parent.parent
        self.assertTrue(
            (root / "scripts" / "hotpot" / "build_fixture.py").is_file(),
            "scripts/hotpot/build_fixture.py is missing — the fixture "
            "can no longer be regenerated and the skip reason above "
            "points nowhere.",
        )


@unittest.skipUnless(_paired_fixture_present(), _FIXTURE_SKIP_REASON)
class FixtureLockTest(unittest.TestCase):
    """The fixture file is the input the harness compares against.
    A silent edit invalidates every Quality Delta Card produced on
    either side of the change. We don't pin the entire SHA here —
    additions to the fixture are legitimate (new questions surface as
    new measurement runs). Instead we lock the SCHEMA + counts so the
    paired path keeps reading what it expects.

    Skipped where the fixture is absent (CI) — see the note above.
    """

    @classmethod
    def setUpClass(cls):
        # Force the path-based import so the test class can run alone
        # (unittest.main without the earlier class running).
        _import_harness()

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


class ChatFixtureSurface(unittest.TestCase):
    """v0.6.1 v18.7 Phase 2 prereq (2026-06-16) — chat-mode fixture.

    The chat fixture is operator-authored (not derived from a public
    benchmark), so there is no upstream alarm if a UX cycle silently
    edits it. The lock-tests below freeze the surface the harness
    consumes — file location, sub-class counts, factual_chat
    gold_signals coverage, multi_turn prior_turns coverage. Adding
    new chat queries is allowed; removing sub-classes or breaking
    the gold_signals / prior_turns contract trips the test.
    """

    @classmethod
    def setUpClass(cls):
        _import_harness()

    def test_chat_fixture_registered_in_harness(self):
        from local_vs_cloud_paired import FIXTURES
        self.assertIn(
            "chat", FIXTURES,
            "harness FIXTURES dict missing 'chat' entry — the "
            "--fixture chat CLI will fail. Phase 2 prereq broken.",
        )

    def test_chat_fixture_file_exists(self):
        from local_vs_cloud_paired import FIXTURES
        chat_path = FIXTURES["chat"]
        self.assertTrue(
            chat_path.exists(),
            f"chat fixture file missing: {chat_path}. "
            f"--fixture chat will raise FileNotFoundError.",
        )

    def test_chat_fixture_subclasses_complete(self):
        """All 4 chat sub-classes must carry ≥ 3 rows so the default
        run (n_per_type=3) can build the paired sample."""
        import json as _json
        from local_vs_cloud_paired import FIXTURES
        data = _json.loads(FIXTURES["chat"].read_text(encoding="utf-8"))
        for t in ("small_talk", "factual_chat",
                  "open_question", "multi_turn"):
            with self.subTest(sub_class=t):
                rows = [q for q in data.get("queries", [])
                        if q.get("question_type") == t]
                self.assertGreaterEqual(
                    len(rows), 3,
                    f"chat sub-class {t!r} only has {len(rows)} rows "
                    f"— paired default needs 3.",
                )

    def test_chat_fixture_factual_have_gold_signals(self):
        """factual_chat is the only chat sub-class where the gold-
        grounded check applies (per v18.6 judge bias). Every record
        must carry gold_signals."""
        import json as _json
        from local_vs_cloud_paired import FIXTURES
        data = _json.loads(FIXTURES["chat"].read_text(encoding="utf-8"))
        factuals = [q for q in data.get("queries", [])
                    if q.get("question_type") == "factual_chat"]
        for q in factuals:
            with self.subTest(id=q.get("id")):
                self.assertTrue(
                    bool(q.get("gold_signals")),
                    f"factual_chat id={q.get('id')} missing "
                    f"gold_signals — gold-grounded recheck cannot "
                    f"score this row.",
                )

    def test_chat_fixture_multiturn_have_prior_turns(self):
        """multi_turn queries must carry prior_turns; the chat prompt
        template treats their absence as a single-turn query, which
        defeats the sub-class's purpose."""
        import json as _json
        from local_vs_cloud_paired import FIXTURES
        data = _json.loads(FIXTURES["chat"].read_text(encoding="utf-8"))
        multis = [q for q in data.get("queries", [])
                  if q.get("question_type") == "multi_turn"]
        for q in multis:
            with self.subTest(id=q.get("id")):
                self.assertTrue(
                    bool(q.get("prior_turns")),
                    f"multi_turn id={q.get('id')} missing prior_turns "
                    f"— sub-class becomes single-turn.",
                )

    def test_chat_prompt_template_emits_prior_turns(self):
        """Smoke: _chat_prompt() must include prior_turns in the
        emitted prompt body so both sides see the same context."""
        from local_vs_cloud_paired import _chat_prompt
        q = {
            "text": "그거 다시 한 줄로 정리해 줘.",
            "prior_turns": [
                {"role": "user", "text": "광합성이 뭐야?"},
                {"role": "assistant", "text": "식물이 빛으로 양분을 만드는 과정."},
            ],
        }
        body = _chat_prompt(q)
        self.assertIn("광합성이 뭐야?", body,
                      "_chat_prompt drops the user prior_turn body")
        self.assertIn("식물이 빛으로 양분을 만드는 과정.", body,
                      "_chat_prompt drops the assistant prior_turn body")
        self.assertIn("그거 다시 한 줄로 정리해 줘.", body,
                      "_chat_prompt drops the current query body")


class WikiEditFixtureSurface(unittest.TestCase):
    """v0.6.1 v18.7 Phase wiki_edit-a prereq (2026-06-20) — wiki_edit-mode
    fixture. Mirrors ``ChatFixtureSurface``.

    The wiki_edit fixture is operator-authored (not derived from a
    public benchmark), so there is no upstream alarm if a UX cycle
    silently edits it. The lock-tests below freeze the surface the
    harness consumes — file location, sub-class counts, factual_edit
    gold_signals coverage, every-row-has-original_doc contract, and
    that ``_wiki_edit_prompt`` actually folds the doc + instruction
    into the prompt body.
    """

    @classmethod
    def setUpClass(cls):
        _import_harness()

    def test_wiki_edit_fixture_registered_in_harness(self):
        from local_vs_cloud_paired import FIXTURES
        self.assertIn(
            "wiki_edit", FIXTURES,
            "harness FIXTURES dict missing 'wiki_edit' entry — the "
            "--fixture wiki_edit CLI will fail. Phase wiki_edit-a "
            "prereq broken.",
        )

    def test_wiki_edit_fixture_file_exists(self):
        from local_vs_cloud_paired import FIXTURES
        path = FIXTURES["wiki_edit"]
        self.assertTrue(
            path.exists(),
            f"wiki_edit fixture file missing: {path}. "
            f"--fixture wiki_edit will raise FileNotFoundError.",
        )

    def test_wiki_edit_fixture_subclasses_complete(self):
        """All 4 wiki_edit sub-classes must carry ≥ 3 rows so the
        default run (n_per_type=3) can build the paired sample."""
        import json as _json
        from local_vs_cloud_paired import FIXTURES
        data = _json.loads(FIXTURES["wiki_edit"].read_text(encoding="utf-8"))
        for t in ("factual_edit", "format_edit", "summarize", "reword"):
            with self.subTest(sub_class=t):
                rows = [q for q in data.get("queries", [])
                        if q.get("question_type") == t]
                self.assertGreaterEqual(
                    len(rows), 3,
                    f"wiki_edit sub-class {t!r} only has {len(rows)} "
                    f"rows — paired default needs 3.",
                )

    def test_wiki_edit_factual_have_gold_signals(self):
        """factual_edit is the deterministic sub-class — every row
        must carry gold_signals so gold-grounded recheck applies."""
        import json as _json
        from local_vs_cloud_paired import FIXTURES
        data = _json.loads(FIXTURES["wiki_edit"].read_text(encoding="utf-8"))
        factuals = [q for q in data.get("queries", [])
                    if q.get("question_type") == "factual_edit"]
        for q in factuals:
            with self.subTest(id=q.get("id")):
                self.assertTrue(
                    bool(q.get("gold_signals")),
                    f"factual_edit id={q.get('id')} missing "
                    f"gold_signals — gold-grounded recheck cannot "
                    f"score this row.",
                )

    def test_wiki_edit_every_row_has_original_doc(self):
        """Every wiki_edit row MUST carry a non-empty original_doc;
        the prompt template needs it as the edit target."""
        import json as _json
        from local_vs_cloud_paired import FIXTURES
        data = _json.loads(FIXTURES["wiki_edit"].read_text(encoding="utf-8"))
        for q in data.get("queries", []):
            with self.subTest(id=q.get("id")):
                doc = (q.get("original_doc") or "").strip()
                self.assertTrue(
                    bool(doc),
                    f"wiki_edit id={q.get('id')} missing original_doc "
                    f"— prompt would have an empty edit target.",
                )

    def test_wiki_edit_prompt_template_emits_doc(self):
        """Smoke: ``_wiki_edit_prompt()`` must include the original_doc
        body AND the edit instruction so both sides see the same edit
        task."""
        from local_vs_cloud_paired import _wiki_edit_prompt
        q = {
            "text": "본문의 '2023년' 부분을 '2024년' 으로 정정해 주세요.",
            "original_doc": "[Wiki] 광합성 연구\n2023년 발견.",
        }
        body = _wiki_edit_prompt(q)
        self.assertIn("[Wiki] 광합성 연구", body,
                      "_wiki_edit_prompt drops the original_doc body")
        self.assertIn("2023년 발견.", body,
                      "_wiki_edit_prompt drops the original_doc body")
        self.assertIn("'2024년' 으로 정정", body,
                      "_wiki_edit_prompt drops the edit instruction")


class MetaFixtureSurface(unittest.TestCase):
    """v0.6.1 v18.7 Phase meta-a prereq (2026-06-21) — meta-mode
    (inventory narrative) fixture. Mirrors ``WikiEditFixtureSurface``.

    Operator-authored synthetic distributions, so a UX cycle could
    silently break it with no upstream alarm. Lock the surface the
    harness consumes — registration, sub-class counts, gold_signals +
    distribution coverage, and that ``_meta_prompt`` mirrors
    handle_meta's narrative prompt (counts folded in + exact-citation
    directive)."""

    @classmethod
    def setUpClass(cls):
        _import_harness()

    def test_meta_fixture_registered(self):
        from local_vs_cloud_paired import FIXTURES
        self.assertIn("meta", FIXTURES,
                      "harness FIXTURES dict missing 'meta' — "
                      "--fixture meta CLI will fail.")

    def test_meta_fixture_file_exists(self):
        from local_vs_cloud_paired import FIXTURES
        self.assertTrue(FIXTURES["meta"].exists(),
                        f"meta fixture missing: {FIXTURES['meta']}")

    def test_meta_subclasses_complete(self):
        import json as _json
        from local_vs_cloud_paired import FIXTURES
        data = _json.loads(FIXTURES["meta"].read_text(encoding="utf-8"))
        for t in ("small_corpus", "medium_corpus", "large_corpus"):
            with self.subTest(sub_class=t):
                rows = [q for q in data.get("queries", [])
                        if q.get("question_type") == t]
                self.assertGreaterEqual(
                    len(rows), 3,
                    f"meta sub-class {t!r} only has {len(rows)} rows.")

    def test_meta_every_row_has_gold_and_distribution(self):
        import json as _json
        from local_vs_cloud_paired import FIXTURES
        data = _json.loads(FIXTURES["meta"].read_text(encoding="utf-8"))
        for q in data.get("queries", []):
            with self.subTest(id=q.get("id")):
                self.assertTrue(bool(q.get("gold_signals")),
                                f"meta id={q.get('id')} missing gold_signals")
                self.assertTrue(
                    bool((q.get("distribution") or {}).get("total")),
                    f"meta id={q.get('id')} missing distribution.total")

    def test_meta_prompt_template_emits_counts_and_directive(self):
        """``_meta_prompt`` must fold the distribution counts in AND
        carry the exact-citation directive (mirrors the production
        _render_llm_narrative prompt)."""
        from local_vs_cloud_paired import _meta_prompt
        q = {
            "distribution": {
                "total": 313,
                "by_type": [["개념", 120]],
                "by_theme": [["AI", 90]],
                "hubs": [["PALANTIR", 27]],
                "recent": ["OPENAI"],
            },
        }
        body = _meta_prompt(q)
        self.assertIn("313", body, "_meta_prompt drops the total count")
        self.assertIn("개념 120개", body, "_meta_prompt drops the type summary")
        self.assertIn("숫자는 정확히 인용", body,
                      "_meta_prompt drops the exact-citation directive")


class RoutingPhase4Surface(unittest.TestCase):
    """v0.6.1 v18.7 Phase 4 (2026-06-20) — privacy + cost cap primitives.

    Phase 4 ships ``core/routing/`` as plumb-first: populated, not
    yet consumed by ``engine.py`` or the cloud egress branch. The
    lock-tests below freeze the public surface (4 callables + 3
    namedtuple shapes) so a future Phase 5 wire — or any other PR
    that re-touches routing primitives — catches accidental renames
    and tuple-field changes before merge. The Phase 5 consumer site
    in `local_vs_cloud_paired.py` will rely on the exact symbols
    locked here.
    """

    def test_core_routing_public_surface(self):
        """``core.routing.__all__`` must export the 7 Phase-4
        public symbols. Adding new ones is allowed; renaming or
        removing any of these breaks the Phase 5 wire."""
        import core.routing as routing_pkg
        required = {
            "PrivacyCheck",
            "detect_pii",
            "check_query_privacy",
            "CostStatus",
            "CostBudget",
            "default_budget",
            "check_cap",
        }
        missing = required - set(getattr(routing_pkg, "__all__", []))
        self.assertFalse(
            missing,
            f"core.routing.__all__ missing Phase 4 symbols: {missing}",
        )
        for sym in required:
            with self.subTest(symbol=sym):
                self.assertTrue(
                    hasattr(routing_pkg, sym),
                    f"core.routing.{sym} not importable",
                )

    def test_privacy_check_namedtuple_shape(self):
        from core.routing import PrivacyCheck
        self.assertEqual(
            PrivacyCheck._fields,
            ("force_local", "reasons", "matched"),
            "PrivacyCheck tuple shape changed — Phase 5 consumer "
            "unpacks (force_local, reasons, matched) positionally",
        )

    def test_cost_status_namedtuple_shape(self):
        from core.routing import CostStatus
        self.assertEqual(
            CostStatus._fields,
            ("under_cap", "used_tokens", "used_usd_est",
             "cap_usd", "month", "reasons"),
            "CostStatus tuple shape changed — Phase 5 consumer "
            "depends on the 6-field layout",
        )

    def test_detect_pii_callable_no_raise_on_empty(self):
        """Surface invariant: detect_pii('') must not raise — the
        Phase 5 consumer may call it on an empty intent slot."""
        from core.routing import detect_pii
        self.assertEqual(detect_pii(""), [])

    def test_check_cap_no_cap_short_circuit(self):
        """Surface invariant: check_cap with cap_usd=0 always
        returns under_cap=True. Phase 5 must be able to treat the
        no-cap branch as a pass-through."""
        from core.routing import CostBudget, check_cap
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            b = CostBudget(os.path.join(d, ".cost.json"), cap_usd=0.0)
            self.assertTrue(check_cap(0, budget=b).under_cap)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
