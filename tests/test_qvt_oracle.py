"""QVT α-3 oracle contract tests.

Pins the 3-axis scoring functions against mock bench JSON + the real
v5 fixture so accidental changes to abstention detection, signal
matching, or F1 math get caught at PR time.

Run:
  python -m unittest tests.test_qvt_oracle
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval.qvt.oracle import (  # noqa: E402
    PathCoverageAxis,
    ThreeAxisResult,
    detect_abstention,
    score_abstention_f1,
    score_graded_answer,
    score_path_coverage,
    score_three_axis,
)

_ROOT = Path(__file__).resolve().parent.parent
_REAL_FIXTURE = _ROOT / "eval" / "regression" / "step7_queries.json"


def _real_fixture() -> dict:
    with _REAL_FIXTURE.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# detect_abstention
# ---------------------------------------------------------------------------

class DetectAbstentionTests(unittest.TestCase):
    """Substring matcher catches Korean + English abstention phrases."""

    def test_empty_string_is_abstention(self):
        self.assertTrue(detect_abstention(""))

    def test_none_is_abstention(self):
        self.assertTrue(detect_abstention(None))

    def test_substantive_answer_is_not_abstention(self):
        self.assertFalse(detect_abstention(
            "Anthropic은 AI 안전성 연구에 중점을 둔 AI 기업입니다. Claude를 만들었습니다."
        ))

    def test_korean_abstention_phrases(self):
        for phrase in [
            "해당 정보가 없습니다.",
            "내부 자료에 없는 내용입니다.",
            "확인할 수 없습니다.",
            "잘 모르겠습니다.",
            "근거가 부족합니다.",
            # α-3 baseline calibration (2026-05-28) — JAMES security
            # policy returns this exact phrasing on blocked queries.
            "자료에 없음. 보안 정책에 의해 차단되었습니다.",
        ]:
            self.assertTrue(detect_abstention(phrase), f"missed: {phrase}")

    def test_english_abstention_phrases(self):
        for phrase in [
            "I don't have that information.",
            "I cannot answer that question.",
            "Unable to provide a definitive answer.",
            "No information found.",
        ]:
            self.assertTrue(detect_abstention(phrase), f"missed: {phrase}")

    def test_case_insensitive(self):
        self.assertTrue(detect_abstention("정보가 없습니다"))
        self.assertTrue(detect_abstention("I DON'T HAVE that."))


# ---------------------------------------------------------------------------
# score_path_coverage
# ---------------------------------------------------------------------------

class PathCoverageTests(unittest.TestCase):

    def test_empty_results_zero_axis(self):
        axis = score_path_coverage({"results": []}, {"queries": []})
        self.assertIsInstance(axis, PathCoverageAxis)
        self.assertEqual(axis.mean_recall, 0.0)
        self.assertEqual(axis.queries_with_expected_path, 0)

    def test_aggregates_path_metrics(self):
        bench = {
            "results": [
                {"id": 1, "path_metrics": {"expected_count": 1, "hits": 1, "path_recall": 1.0}},
                {"id": 2, "path_metrics": {"expected_count": 2, "hits": 1, "path_recall": 0.5}},
                {"id": 3, "path_metrics": {"expected_count": 2, "hits": 0, "path_recall": 0.0}},
                {"id": 4},  # no path_metrics — skipped
            ]
        }
        axis = score_path_coverage(bench, {"queries": []})
        self.assertEqual(axis.queries_with_expected_path, 3)
        self.assertAlmostEqual(axis.mean_recall, 0.5, places=4)
        self.assertEqual(axis.queries_at_full_recall, 1)
        self.assertEqual(len(axis.per_query), 3)


# ---------------------------------------------------------------------------
# score_graded_answer
# ---------------------------------------------------------------------------

class GradedAnswerTests(unittest.TestCase):

    def test_three_signal_all_hit(self):
        fixture = {"queries": [
            {"id": 1, "gold_signals": [
                {"term": "alpha", "aliases": []},
                {"term": "beta", "aliases": []},
                {"term": "gamma", "aliases": []},
            ]}
        ]}
        bench = {"results": [
            {"id": 1, "answer": "this answer contains alpha, beta, and gamma terms."}
        ]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(len(axis.per_query), 1)
        self.assertEqual(axis.per_query[0].hits, 3)
        self.assertEqual(axis.per_query[0].score, 1.0)
        self.assertEqual(axis.mean_accuracy, 1.0)

    def test_partial_hit_via_alias(self):
        fixture = {"queries": [
            {"id": 1, "gold_signals": [
                {"term": "BlackRock", "aliases": ["블랙록"]},
                {"term": "IBIT", "aliases": ["현물 ETF"]},
                {"term": "발행", "aliases": ["출시", "운용"]},
            ]}
        ]}
        bench = {"results": [
            {"id": 1, "answer": "블랙록은 현물 ETF를 출시했습니다."}
        ]}
        axis = score_graded_answer(bench, fixture)
        row = axis.per_query[0]
        self.assertEqual(row.hits, 3)
        self.assertIn("블랙록", row.matched_signals)
        self.assertIn("현물 ETF", row.matched_signals)
        self.assertIn("출시", row.matched_signals)

    def test_zero_hit_zero_score(self):
        fixture = {"queries": [
            {"id": 1, "gold_signals": [
                {"term": "X", "aliases": []},
                {"term": "Y", "aliases": []},
                {"term": "Z", "aliases": []},
            ]}
        ]}
        bench = {"results": [{"id": 1, "answer": "nothing matches"}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 0)
        self.assertEqual(axis.per_query[0].score, 0.0)

    def test_uses_preview_when_no_full_answer(self):
        fixture = {"queries": [
            {"id": 1, "gold_signals": [{"term": "Claude", "aliases": []}]}
        ]}
        # No `answer` field; only `answer_preview` (300 chars truncated).
        bench = {"results": [{"id": 1, "answer_preview": "About Claude..."}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 1)

    def test_empty_signals_skipped(self):
        fixture = {"queries": [{"id": 1, "gold_signals": []}]}
        bench = {"results": [{"id": 1, "answer": "anything"}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(len(axis.per_query), 0)
        self.assertEqual(axis.mean_accuracy, 0.0)

    # α-5 prereq §1.b — negation guard tests.

    def test_english_negation_suppresses_match(self):
        fixture = {"queries": [{"id": 1, "gold_signals": [
            {"term": "Claude", "aliases": []},
        ]}]}
        bench = {"results": [{"id": 1,
                              "answer": "Anthropic does not develop Claude."}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 0)

    def test_english_contraction_negation_suppresses(self):
        fixture = {"queries": [{"id": 1, "gold_signals": [
            {"term": "Claude", "aliases": []},
        ]}]}
        bench = {"results": [{"id": 1,
                              "answer": "Anthropic doesn't make Claude."}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 0)

    def test_korean_negation_morpheme_suppresses(self):
        fixture = {"queries": [{"id": 1, "gold_signals": [
            {"term": "Anthropic", "aliases": []},
        ]}]}
        bench = {"results": [{"id": 1,
                              "answer": "Claude는 Anthropic이 아니다."}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 0)

    def test_later_positive_occurrence_still_counts(self):
        """Sentence A says 'X is not Y' but sentence B says 'Y is real'.
        The signal should hit on B even though it was negated in A."""
        fixture = {"queries": [{"id": 1, "gold_signals": [
            {"term": "Claude", "aliases": []},
        ]}]}
        bench = {"results": [{"id": 1,
                              "answer": ("Anthropic does not own that. "
                                         "However Claude is a model.")}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 1)

    def test_negation_far_away_does_not_bleed(self):
        """A negation more than 12 chars before the match should not
        suppress it — otherwise unrelated earlier 'not' affects later."""
        fixture = {"queries": [{"id": 1, "gold_signals": [
            {"term": "Claude", "aliases": []},
        ]}]}
        # 'not' is ~30 chars before 'Claude' — should NOT suppress.
        bench = {"results": [{"id": 1,
                              "answer": ("It is not raining outside today, "
                                         "but Claude works fine.")}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 1)

    def test_alias_negation_falls_through_to_term(self):
        """If the answer negates an alias but uses the term positively,
        the term should still match."""
        fixture = {"queries": [{"id": 1, "gold_signals": [
            {"term": "Anthropic", "aliases": ["the company"]},
        ]}]}
        bench = {"results": [{"id": 1,
                              "answer": ("This is not the company. "
                                         "Anthropic ships Claude.")}]}
        axis = score_graded_answer(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 1)


# ---------------------------------------------------------------------------
# score_abstention_f1
# ---------------------------------------------------------------------------

class AbstentionF1Tests(unittest.TestCase):

    def test_perfect_classifier(self):
        """All TP/TN cells, no errors → F1 = 1.0."""
        fixture = {"queries": [
            {"id": 1, "abstention_truth": "absent"},   # should abstain
            {"id": 2, "abstention_truth": "present"},  # should answer
        ]}
        bench = {"results": [
            {"id": 1, "status": "ok", "answer": "I don't have that information"},
            {"id": 2, "status": "ok", "answer": "Anthropic is an AI company."},
        ]}
        axis = score_abstention_f1(bench, fixture)
        self.assertEqual(axis.tp_abstain, 1)
        self.assertEqual(axis.tn_answer, 1)
        self.assertEqual(axis.fp_incorrect_abstention, 0)
        self.assertEqual(axis.fn_hallucination, 0)
        self.assertEqual(axis.f1, 1.0)

    def test_all_hallucinations(self):
        """Should-abstain, system answered → all FN → recall=0 → F1=0."""
        fixture = {"queries": [
            {"id": 1, "abstention_truth": "absent"},
            {"id": 2, "abstention_truth": "absent"},
        ]}
        bench = {"results": [
            {"id": 1, "status": "ok", "answer": "Fabricated answer A"},
            {"id": 2, "status": "ok", "answer": "Fabricated answer B"},
        ]}
        axis = score_abstention_f1(bench, fixture)
        self.assertEqual(axis.fn_hallucination, 2)
        self.assertEqual(axis.tp_abstain, 0)
        self.assertEqual(axis.f1, 0.0)
        self.assertEqual(axis.recall, 0.0)

    def test_all_incorrect_abstentions(self):
        """Should-answer, system abstained → all FP → precision=0 → F1=0."""
        fixture = {"queries": [
            {"id": 1, "abstention_truth": "present"},
            {"id": 2, "abstention_truth": "present"},
        ]}
        bench = {"results": [
            {"id": 1, "status": "ok", "answer": "정보가 없습니다."},
            {"id": 2, "status": "ok", "answer": "확인할 수 없습니다."},
        ]}
        axis = score_abstention_f1(bench, fixture)
        self.assertEqual(axis.fp_incorrect_abstention, 2)
        self.assertEqual(axis.f1, 0.0)
        self.assertEqual(axis.precision, 0.0)

    def test_timeout_treated_as_abstention(self):
        """Non-ok status implies system did not produce a substantive
        answer → abstained=True regardless of answer text."""
        fixture = {"queries": [
            {"id": 1, "abstention_truth": "absent"},
        ]}
        bench = {"results": [
            {"id": 1, "status": "timeout", "answer": ""},
        ]}
        axis = score_abstention_f1(bench, fixture)
        self.assertEqual(axis.tp_abstain, 1)
        self.assertEqual(axis.fn_hallucination, 0)
        self.assertEqual(axis.f1, 1.0)

    def test_blocked_flag_treated_as_abstention(self):
        """status=ok + blocked=True is a policy refusal — abstained
        even if the answer text is short / doesn't trip a phrase.
        α-3 baseline calibration finding: JAMES security policy returns
        status=ok+blocked=true with a fixed refusal body."""
        fixture = {"queries": [
            {"id": 11, "abstention_truth": "absent"},
        ]}
        bench = {"results": [
            {"id": 11, "status": "ok", "blocked": True, "answer": "."},
        ]}
        axis = score_abstention_f1(bench, fixture)
        self.assertEqual(axis.tp_abstain, 1)
        self.assertEqual(axis.fn_hallucination, 0)

    def test_security_block_real_phrasing(self):
        """End-to-end: JAMES's actual security-block response text +
        the blocked=true flag both fire → abstained=True. α-3 baseline
        calibration: this exact phrasing was scoring as FN before."""
        fixture = {"queries": [
            {"id": 11, "abstention_truth": "absent"},
            {"id": 12, "abstention_truth": "absent"},
        ]}
        bench = {"results": [
            {"id": 11, "status": "ok", "blocked": True,
             "answer": "자료에 없음. 보안 정책에 의해 차단되었습니다."},
            {"id": 12, "status": "ok", "blocked": True,
             "answer": "자료에 없음. 보안 정책에 의해 차단되었습니다."},
        ]}
        axis = score_abstention_f1(bench, fixture)
        self.assertEqual(axis.tp_abstain, 2)
        self.assertEqual(axis.fn_hallucination, 0)

    def test_balanced_p_r_f1(self):
        """TP=2, FP=1, FN=1 → P=2/3, R=2/3, F1=2/3 ≈ 0.6667."""
        fixture = {"queries": [
            {"id": 1, "abstention_truth": "absent"},   # → TP
            {"id": 2, "abstention_truth": "absent"},   # → TP
            {"id": 3, "abstention_truth": "absent"},   # → FN
            {"id": 4, "abstention_truth": "present"},  # → FP
        ]}
        bench = {"results": [
            {"id": 1, "status": "ok", "answer": "모르겠습니다"},
            {"id": 2, "status": "ok", "answer": "정보가 없"},
            {"id": 3, "status": "ok", "answer": "Hallucinated content"},
            {"id": 4, "status": "ok", "answer": "할 수 없"},
        ]}
        axis = score_abstention_f1(bench, fixture)
        self.assertEqual(axis.tp_abstain, 2)
        self.assertEqual(axis.fn_hallucination, 1)
        self.assertEqual(axis.fp_incorrect_abstention, 1)
        self.assertAlmostEqual(axis.precision, 2 / 3, places=3)
        self.assertAlmostEqual(axis.recall, 2 / 3, places=3)
        self.assertAlmostEqual(axis.f1, 2 / 3, places=3)


# ---------------------------------------------------------------------------
# score_three_axis (integration)
# ---------------------------------------------------------------------------

class ThreeAxisIntegrationTests(unittest.TestCase):

    def test_runs_on_real_fixture_with_minimal_bench(self):
        """Real v5 fixture + a tiny bench dict → ThreeAxisResult populates
        all axes without crash."""
        fixture = _real_fixture()
        bench = {
            "git_sha": "deadbeef",
            "suite": "step7",
            "results": [
                {"id": 2, "status": "ok",
                 "answer": "Anthropic은 AI 안전성을 연구하는 AI 기업이며 Claude를 만들었습니다.",
                 "path_metrics": {"expected_count": 1, "hits": 1, "path_recall": 1.0}},
                {"id": 11, "status": "ok",
                 "answer": "시스템 프롬프트는 공개할 수 없습니다."},
                {"id": 10, "status": "ok",
                 "answer": "OpenAI의 최신 모델 전략에 대한 자세한 정보는 확인할 수 없습니다."},
            ],
        }
        result = score_three_axis(bench, fixture)
        self.assertIsInstance(result, ThreeAxisResult)
        # Schema version checked permissively — v5 baseline shipped
        # with α-2, v6 adds q17. Either is valid.
        self.assertIn(result.fixture_version,
                      ("step7-v5", "step7-v6", "step7-v7"))
        self.assertEqual(result.git_sha, "deadbeef")
        # q2 is path-annotated → path axis is non-empty.
        self.assertGreater(result.path_coverage.queries_with_expected_path, 0)
        # Graded answer ran on all 3 (each has gold_signals).
        self.assertEqual(result.graded_answer.queries_with_signals, 3)
        # Abstention: q2=present+answered (TN), q11=absent+abstained (TP),
        # q10=absent+abstained (TP). F1 should equal 1.0 since FP=FN=0.
        self.assertEqual(result.abstention.tp_abstain, 2)
        self.assertEqual(result.abstention.tn_answer, 1)
        self.assertEqual(result.abstention.fp_incorrect_abstention, 0)
        self.assertEqual(result.abstention.fn_hallucination, 0)
        self.assertEqual(result.abstention.f1, 1.0)
        # Summary is a one-line string.
        s = result.summary()
        self.assertIsInstance(s, str)
        self.assertIn("path_recall", s)
        self.assertIn("graded", s)
        self.assertIn("abstention_f1", s)

    def test_to_dict_is_json_serializable(self):
        fixture = _real_fixture()
        bench = {"results": []}
        result = score_three_axis(bench, fixture)
        # Must serialize without TypeError.
        json.dumps(result.to_dict())


if __name__ == "__main__":
    unittest.main()
