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


class PayloadShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = _SCRIPT.read_text(encoding="utf-8")

    def test_schema_is_v3(self):
        self.assertIn('"schema": "qvt-baseline-v3"', self.src)

    def test_payload_carries_provenance_and_health(self):
        self.assertIn('"resolved_models": _resolved_models()', self.src)
        self.assertIn('"answer_health": health_by_run', self.src)

    def test_capture_aborts_instead_of_writing(self):
        self.assertIn("return 6", self.src)
        self.assertIn("infrastructure failures, not measurements", self.src)


if __name__ == "__main__":
    unittest.main()
