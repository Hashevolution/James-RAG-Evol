"""QVT baseline capture — a timed-out LLM must not become a measurement.

`core/reasoning/pipeline.py` treats a synth failure as a no-data trigger
and `pipeline_synth/softener.py` softens it into an abstention. For a
live answer that is right: the user gets a decline, not a stack trace.
For a *baseline* it is ruinous — the LLM call that timed out is scored as
the system correctly declining. It lands in `abstention_f1` as a true
abstention and in `graded_answer` as an absent answer, and nothing
downstream can tell it apart from a semantic one.

Observed 2026-09-22 on a real capture attempt: 9 of 17 queries came back
"답변 생성에 실패했습니다." with 54 `gemma.timeout` events in the audit
log, 175–303 s per query against a 90 s per-call timeout. The capture
would have written that as the canonical 5-axis baseline that every
future Quality Delta Card is paired against — it only hard-fails when
bench produces no file at all, not when the answers are empty.

The second guard is provenance. `_BASELINE_ENV` pins six flags, which
was the complete set of controls in 2026-05. Mode-aware routing landed
afterwards (#969–#990) and picks the model *outside* that set: at
2a31b20 `resolve_for_mode` had no "retrieval" key and the capture ran
the config default `gemma4:e4b`; today it resolves to `gemma3:12b`. The
baseline JSON recorded the old env dict as though it were complete.

Run:
  python -m unittest tests.test_qvt_capture_integrity
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_SCRIPT = REPO_ROOT / "scripts" / "qvt_capture_baseline.py"


def _load():
    spec = importlib.util.spec_from_file_location("_qvt_capture", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bench(tmp: Path, rows) -> Path:
    p = tmp / "bench_test.json"
    p.write_text(json.dumps({"suite": "step7", "results": rows}),
                 encoding="utf-8")
    return p


class AnswerHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_generation_failures_are_counted(self):
        """The exact shape seen in the aborted 2026-09-22 capture."""
        p = _bench(self.tmp, [
            {"id": "q1", "answer_preview": "답변 생성에 실패했습니다.", "blocked": False},
            {"id": "q2", "answer_preview": "RAG는 검색 증강 생성으로…", "blocked": False},
            {"id": "q3", "answer_preview": "LLM 응답 생성 중 오류", "blocked": False},
        ])
        h = self.m._answer_health(p)
        self.assertEqual(h["total"], 3)
        self.assertEqual(h["failed"], 2)
        self.assertTrue(any("q1" in e for e in h["examples"]))

    def test_semantic_abstention_is_not_a_failure(self):
        """'자료에 없음' is a measurement — the whole point of the
        abstention axis. Counting it as breakage would make the guard
        refuse every healthy run."""
        p = _bench(self.tmp, [
            {"id": "q1", "answer_preview": "자료에 없음. 관련된 문서를 찾지 못했습니다.",
             "blocked": False},
        ])
        h = self.m._answer_health(p)
        self.assertEqual(h["failed"], 0)

    def test_blocked_rows_are_excluded(self):
        """step7 ships security fixtures that are supposed to be refused."""
        p = _bench(self.tmp, [
            {"id": "sec1", "answer_preview": "자료에 없음. 보안 정책에 따라 차단",
             "blocked": True},
            {"id": "sec2", "answer_preview": "답변 생성에 실패했습니다.", "blocked": True},
            {"id": "q1", "answer_preview": "정상 답변", "blocked": False},
        ])
        h = self.m._answer_health(p)
        self.assertEqual(h["total"], 1, "blocked rows must not be considered")
        self.assertEqual(h["failed"], 0)

    def test_backend_error_prefixes_count_as_failures(self):
        p = _bench(self.tmp, [
            {"id": "q1", "answer_preview": "[Gemma 응답 없음]", "blocked": False},
        ])
        self.assertEqual(self.m._answer_health(p)["failed"], 1)

    def test_leading_whitespace_does_not_hide_a_failure(self):
        p = _bench(self.tmp, [
            {"id": "q1", "answer_preview": "   답변 생성에 실패했습니다.",
             "blocked": False},
        ])
        self.assertEqual(self.m._answer_health(p)["failed"], 1)

    def test_unreadable_bench_reports_error_without_raising(self):
        p = self.tmp / "broken.json"
        p.write_text("{not json", encoding="utf-8")
        h = self.m._answer_health(p)
        self.assertIsNotNone(h["error"])
        self.assertEqual(h["failed"], 0)

    def test_prefix_list_reuses_the_repo_vocabulary(self):
        prefixes = self.m._infrastructure_failure_prefixes()
        self.assertIn("답변 생성에 실패", prefixes)
        self.assertIn("LLM 응답 생성 중 오류", prefixes)
        self.assertNotIn(
            "자료에 없음. 관련된", prefixes,
            "a semantic abstention must never be on the failure list",
        )


class ResolvedModelProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_resolved_models_names_what_routing_picks(self):
        snap = self.m._resolved_models()
        self.assertIsNone(snap.get("error"), snap.get("error"))
        self.assertIn("retrieval", snap)
        self.assertIsInstance(snap["retrieval"]["tag"], str)
        self.assertIn("config_default", snap)

    def test_kill_switch_state_is_recorded(self):
        self.assertIn("mode_aware_routing_disabled", self.m._resolved_models())


class BaselineModelPinTests(unittest.TestCase):
    """Operator decision 2026-09-22 — option 1: hold the model fixed so
    the re-captured baseline stays comparable to the one it replaces.

    Three vars, and all three matter. Any one missing and the pin is
    silently bypassed:
      JAMES_LLM_MODEL                   the model
      JAMES_DISABLE_MODE_AWARE_ROUTING  else routing overrides it
      JAMES_SETTINGS_USE_DB             else a DB row silently wins
    """

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_all_three_pin_vars_present(self):
        env = self.m._BASELINE_ENV
        self.assertEqual(env.get("JAMES_LLM_MODEL"), "gemma4:e4b")
        self.assertEqual(env.get("JAMES_DISABLE_MODE_AWARE_ROUTING"), "1")
        self.assertEqual(
            env.get("JAMES_SETTINGS_USE_DB"), "0",
            "config._llm_setting is DB-first — without this an admin-UI "
            "edit silently redefines the baseline",
        )

    def test_original_six_flags_are_untouched(self):
        env = self.m._BASELINE_ENV
        for k, v in (
            ("JAMES_ENABLE_ENTITY_ANCHOR", "1"),
            ("JAMES_EMBEDDING_MODEL", "BAAI/bge-m3"),
            ("JAMES_ENABLE_QUERY_REWRITE", "1"),
            ("JAMES_AUTO_ROUTER", "0"),
            ("JAMES_ADAPTIVE_BUDGET", "0"),
            ("JAMES_SCOPE_ROUTING", "0"),
        ):
            self.assertEqual(env.get(k), v, f"{k} must keep its v0.4.0 value")

    def test_effective_model_is_the_pin_without_presetting_environ(self):
        """The regression that shipped in #1142 and was caught by the
        2026-09-22 artifact.

        `_resolved_models` originally read `os.environ`. `_BASELINE_ENV`
        is applied to the *spawned server*, never to the runner, so the
        pin was invisible and the written baseline recorded
        effective=gemma3:12b for a run Ollama confirms was served by
        gemma4:e4b throughout.

        The #1142 test did not catch it because it set `os.environ` from
        `_BASELINE_ENV` first — it reproduced the bug's own assumption
        instead of the runner's real conditions. This one deliberately
        does NOT preset anything: the function must derive the answer
        from `_BASELINE_ENV` itself.
        """
        snap = self.m._resolved_models()
        self.assertTrue(
            snap["mode_aware_routing_disabled"],
            "must read the kill-switch from _BASELINE_ENV, not os.environ",
        )
        self.assertEqual(snap["effective"]["tag"], "gemma4:e4b")
        self.assertIn("GEMMA_MODEL", snap["effective"]["source"])
        self.assertEqual(snap["probe"], "baseline-env")

    def test_both_the_pin_and_the_routing_answer_are_recorded(self):
        """Both are recorded on purpose: a reader should see the gap
        between the pinned baseline and live production routing without
        having to already know about it.

        The *values* are deliberately not asserted. `resolve_for_mode`
        consults the installed model catalogue, so on a host without
        Ollama it returns an empty tag — an earlier revision of this
        test asserted "gemma3:12b" and went red in CI for describing
        this machine rather than the contract.
        """
        snap = self.m._resolved_models()
        # From _BASELINE_ENV, so this one IS environment-independent.
        self.assertEqual(snap["effective"]["tag"], "gemma4:e4b")
        self.assertIn("retrieval", snap)
        self.assertIn("tag", snap["retrieval"])
        self.assertIsNot(
            snap["effective"], snap["retrieval"],
            "the pinned model and the routing answer must be separate "
            "entries, not the same object",
        )

    def test_effective_follows_routing_when_the_pin_is_absent(self):
        """Without the kill-switch in the applied env, the effective
        model is whatever the preference list tops."""
        pinless = {k: v for k, v in self.m._BASELINE_ENV.items()
                   if k != "JAMES_DISABLE_MODE_AWARE_ROUTING"}
        prev = dict(self.m._BASELINE_ENV)
        try:
            self.m._BASELINE_ENV.clear()
            self.m._BASELINE_ENV.update(pinless)
            snap = self.m._resolved_models()
            self.assertFalse(snap["mode_aware_routing_disabled"])
            self.assertEqual(
                snap["effective"]["tag"], snap["retrieval"]["tag"])
        finally:
            self.m._BASELINE_ENV.clear()
            self.m._BASELINE_ENV.update(prev)


class PayloadShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = _SCRIPT.read_text(encoding="utf-8")

    def test_schema_is_v4(self):
        """Bumped from v3 when host_state was added (2026-09-24). This
        test was updated, not deleted: the bump is intentional, and the
        new payload keys it implies are pinned below."""
        self.assertIn('"schema": "qvt-baseline-v4"', self.src)

    def test_payload_carries_host_state(self):
        """Without this the 2026-09-22 capture's ~2.4x slowdown against
        09-24 is known to exist and impossible to explain."""
        self.assertIn('"host_state": host_state_by_run', self.src)

    def test_host_state_is_recorded_even_when_a_run_aborts(self):
        """Appended in the ``finally`` block — a run that fails is
        exactly the run whose host conditions you need."""
        body = self.src.split("def _run_single_bench", 1)[1].split("\ndef ", 1)[0]
        finally_block = body.split("finally:", 1)[1]
        self.assertIn("host_log.append(host)", finally_block)

    def test_gpu_is_sampled_during_the_bench_not_snapshotted(self):
        self.assertIn("host_state.GpuSampler(", self.src)
        self.assertIn('host["gpu_during_bench"] = gpu.summary()', self.src)

    def test_banner_shows_the_pin_and_the_rewrite_budget(self):
        """The banner used to hard-code six flags and kept announcing
        'the environment' after #1142 and #1146 joined it."""
        self.assertIn("shown = {k: server_env.get(k) for k in _BASELINE_ENV}",
                      self.src)
        self.assertIn('shown["JAMES_QUERY_REWRITE_TIMEOUT_S"]', self.src)
        self.assertNotIn("AUTO_ROUTER=0 ADAPTIVE_BUDGET=0 SCOPE_ROUTING=0) ===",
                         self.src)

    def test_payload_carries_provenance_and_health(self):
        self.assertIn('"resolved_models": _resolved_models()', self.src)
        self.assertIn('"answer_health": health_by_run', self.src)

    def test_capture_aborts_instead_of_writing(self):
        self.assertIn("return 6", self.src)
        self.assertIn("infrastructure failures, not measurements", self.src)


if __name__ == "__main__":
    unittest.main()
