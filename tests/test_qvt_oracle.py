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
    FiveAxisResult,
    LatencyCostAxis,
    PathCoverageAxis,
    ThreeAxisResult,
    TokenCostAxis,
    _percentile,
    detect_abstention,
    score_abstention_f1,
    score_five_axis,
    score_graded_answer,
    score_latency_cost,
    score_paper_aligned_accuracy,
    score_path_coverage,
    score_three_axis,
    score_token_cost,
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

    # α-5 §findings 2026-05-31 — source-side path scoring tests.

    def test_source_match_full_recall(self):
        """JAMES `sources` filenames slug-match all expected article titles."""
        bench = {"results": [{
            "id": 1, "status": "ok",
            "sources": [
                "multihop_0009_SBF-Trial-The-latest-updates-from-the-FTX-collapse-s-courtroom-drama.txt",
                "multihop_0010_SBF-s-trial-starts-soon-but-how-did-he-and-FTX-get-here.txt",
                "multihop_0175_The-FTX-trial-is-bigger-than-Sam-Bankman-Fried.txt",
            ],
        }]}
        fixture = {"queries": [{
            "id": 1, "category": "test",
            "expected_path": {"nodes": [
                "SBF Trial: The latest updates from the FTX collapse's courtroom drama",
                "SBF's trial starts soon, but how did he — and FTX — get here?",
                "The FTX trial is bigger than Sam Bankman-Fried",
            ], "min_recall": 1.0},
        }]}
        axis = score_path_coverage(bench, fixture)
        self.assertEqual(len(axis.per_query), 1)
        self.assertEqual(axis.per_query[0].hits, 3)
        self.assertEqual(axis.per_query[0].via_sources, 3)
        self.assertEqual(axis.per_query[0].via_graph, 0)
        self.assertAlmostEqual(axis.mean_recall, 1.0, places=4)

    def test_source_partial_match(self):
        """Top-3 sources contain only 2 of 3 expected articles."""
        bench = {"results": [{
            "id": 1, "status": "ok",
            "sources": [
                "multihop_0009_SBF-Trial-The-latest-updates-from-the-FTX-collapse-s-courtroom-drama.txt",
                "multihop_0010_SBF-s-trial-starts-soon-but-how-did-he-and-FTX-get-here.txt",
                "multihop_0999_Unrelated-article.txt",
            ],
        }]}
        fixture = {"queries": [{
            "id": 1, "category": "test",
            "expected_path": {"nodes": [
                "SBF Trial: The latest updates from the FTX collapse's courtroom drama",
                "SBF's trial starts soon, but how did he — and FTX — get here?",
                "The FTX trial is bigger than Sam Bankman-Fried",
            ], "min_recall": 1.0},
        }]}
        axis = score_path_coverage(bench, fixture)
        self.assertAlmostEqual(axis.per_query[0].recall, 2 / 3, places=4)

    def test_unified_credit_from_both_sides(self):
        """A hit from graph_paths AND a hit from sources both count, but
        a title matched on both sides is credited once (no double count)."""
        bench = {"results": [{
            "id": 1, "status": "ok",
            "graph_paths": [
                # A path that contains 'The FTX trial …' as a node — this
                # is a synthetic graph-entity match the way bench parses
                # path strings.
                "The FTX trial is bigger than Sam Bankman-Fried -[REL]→ Sam Bankman-Fried",
            ],
            "sources": [
                # Source filename also covers the same article.
                "multihop_0175_The-FTX-trial-is-bigger-than-Sam-Bankman-Fried.txt",
                # And a second article covered by sources only.
                "multihop_0010_SBF-s-trial-starts-soon-but-how-did-he-and-FTX-get-here.txt",
            ],
        }]}
        fixture = {"queries": [{
            "id": 1, "category": "test",
            "expected_path": {"nodes": [
                "The FTX trial is bigger than Sam Bankman-Fried",
                "SBF's trial starts soon, but how did he — and FTX — get here?",
            ], "min_recall": 1.0},
        }]}
        axis = score_path_coverage(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 2)
        # First article matched on both sides; second only via sources.
        # via_graph counts pre-dedup hits from graph side; via_sources
        # counts pre-dedup hits from sources side. Each hit is allowed
        # to appear in both counters.
        self.assertEqual(axis.per_query[0].via_graph, 1)
        self.assertEqual(axis.per_query[0].via_sources, 2)
        self.assertAlmostEqual(axis.per_query[0].recall, 1.0, places=4)

    def test_no_sources_no_graph_no_hits(self):
        bench = {"results": [{
            "id": 1, "status": "ok",
            "sources": [
                "multihop_0999_completely-unrelated-article.txt",
            ],
        }]}
        fixture = {"queries": [{
            "id": 1, "category": "test",
            "expected_path": {"nodes": ["The FTX trial is bigger than Sam Bankman-Fried"],
                              "min_recall": 1.0},
        }]}
        axis = score_path_coverage(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 0)
        self.assertEqual(axis.per_query[0].recall, 0.0)

    # 2026-06-02 — step7 bench-schema drift fix. Bench stops emitting
    # raw `graph_paths` (only `graph_paths_count`); oracle's slug-match
    # over sources fails on entity-name expected_path because sources
    # are PDF filenames. Before fix: pre-dedup union_hits = 0 even
    # though bench's own `path_metrics.hits = 1`. After fix: trust
    # bench's graph-side hit count as a floor.
    def test_bench_path_metrics_floor_when_graph_paths_dropped(self):
        bench = {"results": [{
            "id": 2, "status": "ok",
            # No raw graph_paths — only count + path_metrics.hits.
            "graph_paths_count": 19,
            "sources": [
                "08_MCP_(Model_Context_Protocol).pdf",
                "02_컨텍스트_엔지니어링.pdf",
            ],
            "path_metrics": {"expected_count": 1, "hits": 1, "path_recall": 1.0},
        }]}
        fixture = {"queries": [{
            "id": 2, "category": "retrieve",
            "expected_path": {"nodes": ["Anthropic"], "min_recall": 1.0},
        }]}
        axis = score_path_coverage(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 1)
        self.assertEqual(axis.per_query[0].via_graph, 1)
        self.assertAlmostEqual(axis.per_query[0].recall, 1.0, places=4)

    def test_bench_path_metrics_floor_caps_at_expected(self):
        """A noisy bench path_metrics.hits > expected_count must not push
        recall above 1.0."""
        bench = {"results": [{
            "id": 3, "status": "ok",
            "graph_paths_count": 50,
            "sources": ["unrelated.pdf"],
            "path_metrics": {"expected_count": 2, "hits": 99, "path_recall": 1.0},
        }]}
        fixture = {"queries": [{
            "id": 3, "category": "retrieve",
            "expected_path": {"nodes": ["NodeA", "NodeB"], "min_recall": 1.0},
        }]}
        axis = score_path_coverage(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 2)
        self.assertAlmostEqual(axis.per_query[0].recall, 1.0, places=4)

    def test_oracle_source_match_still_credits_when_bench_lower(self):
        """When oracle's source-side slug-match already finds the hit,
        the bench floor (which is graph-only) must NOT shrink credit."""
        bench = {"results": [{
            "id": 4, "status": "ok",
            "sources": [
                "multihop_0010_SBF-s-trial-starts-soon-but-how-did-he-and-FTX-get-here.txt",
            ],
            # Bench's path matcher saw zero (it's graph-only and the
            # answer came from the source citation).
            "path_metrics": {"expected_count": 1, "hits": 0, "path_recall": 0.0},
        }]}
        fixture = {"queries": [{
            "id": 4, "category": "test",
            "expected_path": {"nodes": [
                "SBF's trial starts soon, but how did he — and FTX — get here?",
            ], "min_recall": 1.0},
        }]}
        axis = score_path_coverage(bench, fixture)
        self.assertEqual(axis.per_query[0].hits, 1)
        self.assertEqual(axis.per_query[0].via_sources, 1)
        self.assertAlmostEqual(axis.per_query[0].recall, 1.0, places=4)


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


# ---------------------------------------------------------------------------
# Cost axes — Step 5 (5-axis extension for α-5 plan)
# ---------------------------------------------------------------------------

class PercentileHelperTests(unittest.TestCase):
    def test_p50_odd_length(self):
        # Nearest-rank: ceil(0.5 * 5) - 1 = 2 → element 3 (1-indexed) → 3.
        self.assertEqual(_percentile([1, 2, 3, 4, 5], 0.5), 3)

    def test_p95(self):
        # Nearest-rank: ceil(0.95 * 10) - 1 = 9 → last element → 10.
        self.assertEqual(_percentile(list(range(1, 11)), 0.95), 10)

    def test_empty_returns_zero(self):
        self.assertEqual(_percentile([], 0.5), 0.0)

    def test_zero_percentile_returns_min(self):
        self.assertEqual(_percentile([3.0, 1.0, 2.0], 0.0), 1.0)


class TokenCostAxisTests(unittest.TestCase):
    """answer_len is the token-cost proxy; failures / timeouts excluded."""

    def test_mean_and_p95_on_ok_rows_only(self):
        bench = {"results": [
            {"id": 1, "status": "ok", "elapsed": 1.0, "answer_len": 100},
            {"id": 2, "status": "ok", "elapsed": 2.0, "answer_len": 200},
            {"id": 3, "status": "ok", "elapsed": 3.0, "answer_len": 300},
            {"id": 4, "status": "timeout", "elapsed": 60.0},  # excluded
            {"id": 5, "status": "error", "elapsed": 5.0},     # excluded
        ]}
        axis = score_token_cost(bench)
        self.assertEqual(axis.n_queries, 3)
        self.assertEqual(axis.mean_chars, 200.0)
        # Nearest-rank p95 of {100, 200, 300} = 300.
        self.assertEqual(axis.p95_chars, 300.0)

    def test_falls_back_to_answer_preview_chars(self):
        # Older bench JSONs may omit answer_len but always have preview.
        bench = {"results": [
            {"id": 1, "status": "ok", "elapsed": 1.0,
             "answer_preview": "x" * 250},
        ]}
        axis = score_token_cost(bench)
        self.assertEqual(axis.mean_chars, 250.0)

    def test_empty_returns_zero_axis(self):
        axis = score_token_cost({"results": []})
        self.assertEqual(axis.n_queries, 0)
        self.assertEqual(axis.mean_chars, 0.0)


class LatencyCostAxisTests(unittest.TestCase):
    def test_mean_and_p95_seconds(self):
        bench = {"results": [
            {"id": 1, "status": "ok", "elapsed": 2.0, "answer_len": 100},
            {"id": 2, "status": "ok", "elapsed": 4.0, "answer_len": 100},
            {"id": 3, "status": "ok", "elapsed": 6.0, "answer_len": 100},
        ]}
        axis = score_latency_cost(bench)
        self.assertEqual(axis.n_queries, 3)
        self.assertEqual(axis.mean_s, 4.0)
        self.assertEqual(axis.p95_s, 6.0)

    def test_timeout_rows_skipped(self):
        bench = {"results": [
            {"id": 1, "status": "ok", "elapsed": 2.0, "answer_len": 100},
            {"id": 2, "status": "timeout", "elapsed": 120.0},
        ]}
        axis = score_latency_cost(bench)
        # Timeout row would skew mean → ensure it's excluded.
        self.assertEqual(axis.n_queries, 1)
        self.assertEqual(axis.mean_s, 2.0)

    def test_empty_returns_zero_axis(self):
        axis = score_latency_cost({"results": []})
        self.assertEqual(axis.n_queries, 0)


class FiveAxisResultTests(unittest.TestCase):
    """The 5-axis integration object — quality 3-axis + cost 2-axis."""

    def _minimal_bench(self) -> dict:
        return {
            "git_sha": "abc1234",
            "suite": "multihop_rag",
            "results": [
                {"id": 1, "status": "ok", "elapsed": 1.5, "answer_len": 120,
                 "answer_preview": "Foo bar.", "blocked": False,
                 "graph_paths_count": 3},
                {"id": 2, "status": "ok", "elapsed": 3.0, "answer_len": 240,
                 "answer_preview": "정보가 없습니다.", "blocked": False,
                 "graph_paths_count": 0},
            ],
        }

    def _minimal_fixture(self) -> dict:
        return {
            "version": "multihop-rag-test",
            "queries": [
                {"id": 1, "category": "test", "text": "Q1",
                 "gold_signals": [{"term": "Foo", "aliases": []}],
                 "abstention_truth": "present"},
                {"id": 2, "category": "test", "text": "Q2",
                 "gold_signals": [{"term": "Bar", "aliases": []}],
                 "abstention_truth": "absent"},
            ],
        }

    def test_score_five_axis_returns_correct_type(self):
        result = score_five_axis(self._minimal_bench(), self._minimal_fixture())
        self.assertIsInstance(result, FiveAxisResult)
        self.assertIsInstance(result.three_axis, ThreeAxisResult)
        self.assertIsInstance(result.token_cost, TokenCostAxis)
        self.assertIsInstance(result.latency_cost, LatencyCostAxis)

    def test_quality_axes_delegate_to_three_axis(self):
        result = score_five_axis(self._minimal_bench(), self._minimal_fixture())
        # Proxy properties must return the underlying axes.
        self.assertIs(result.path_coverage, result.three_axis.path_coverage)
        self.assertIs(result.graded_answer, result.three_axis.graded_answer)
        self.assertIs(result.abstention, result.three_axis.abstention)

    def test_to_dict_contains_all_five_axes(self):
        result = score_five_axis(self._minimal_bench(), self._minimal_fixture())
        d = result.to_dict()
        for key in ("path_coverage", "graded_answer", "abstention",
                    "token_cost", "latency_cost"):
            self.assertIn(key, d)
        # JSON-serializable.
        json.dumps(d)

    def test_summary_contains_cost_axes(self):
        result = score_five_axis(self._minimal_bench(), self._minimal_fixture())
        s = result.summary()
        self.assertIn("token_cost", s)
        self.assertIn("latency", s)

    def test_metadata_proxies(self):
        result = score_five_axis(self._minimal_bench(), self._minimal_fixture())
        self.assertEqual(result.git_sha, "abc1234")
        self.assertEqual(result.suite, "multihop_rag")
        self.assertEqual(result.fixture_version, "multihop-rag-test")
        self.assertEqual(result.n_queries, 2)


# ---------------------------------------------------------------------------
# score_paper_aligned_accuracy (P1 — MultiHop-RAG paper metric 근사)
# ---------------------------------------------------------------------------

class PaperAlignedAccuracyTests(unittest.TestCase):
    """Binary exact-match approximation against the MultiHop-RAG paper
    metric. answerable = gold_signals match (primary=signal[0],
    strict=all); null = abstain."""

    def _fixture(self):
        return {
            "version": "test",
            "queries": [
                {"id": 1, "question_type": "inference_query",
                 "abstention_truth": "present",
                 "gold_signals": [{"term": "Sam Bankman-Fried", "aliases": ["SBF"]},
                                  {"term": "FTX", "aliases": []}]},
                {"id": 2, "question_type": "comparison_query",
                 "abstention_truth": "present",
                 "gold_signals": [{"term": "Yes", "aliases": []}]},
                {"id": 3, "question_type": "null_query",
                 "abstention_truth": "absent",
                 "gold_signals": [{"term": "irrelevant", "aliases": []}]},
            ],
        }

    def _bench(self, answers):
        # answers: {id: answer_text}
        return {
            "results": [
                {"id": qid, "status": "ok", "blocked": False,
                 "answer_preview": ans, "answer_len": len(ans)}
                for qid, ans in answers.items()
            ]
        }

    def test_primary_hit_counts_first_signal_only(self):
        # id1: only SBF (primary) hit, FTX missing → primary correct, strict wrong
        bench = self._bench({
            1: "The person is Sam Bankman-Fried.",
            2: "Yes, both increased.",
            3: "There is insufficient information to answer.",
        })
        axis = score_paper_aligned_accuracy(bench, self._fixture())
        # id1 primary hit (SBF), id2 primary hit (Yes), id3 null abstain → 3/3 primary
        self.assertEqual(axis.correct_primary, 3)
        self.assertEqual(axis.accuracy_primary, 1.0)
        # strict: id1 missing FTX → not all_hit. id2 single signal hit = all_hit.
        # id3 abstain = correct for both.  → id2 + id3 = 2/3 strict
        self.assertEqual(axis.correct_strict, 2)

    def test_alias_match_counts(self):
        bench = self._bench({
            1: "It was SBF and FTX both.",   # alias SBF + FTX → all hit
            2: "No.",                          # 'Yes' not present → miss
            3: "There is insufficient information to answer.",  # abstain → correct
        })
        axis = score_paper_aligned_accuracy(bench, self._fixture())
        # id1 primary(SBF alias) + strict(FTX too) ; id2 miss ; id3 correct
        self.assertEqual(axis.correct_primary, 2)   # id1 + id3
        self.assertEqual(axis.correct_strict, 2)    # id1 (all) + id3

    def test_null_query_must_abstain(self):
        # id3 null query but system hallucinated an answer → wrong
        bench = self._bench({
            1: "Sam Bankman-Fried, FTX.",
            2: "Yes.",
            3: "The answer is definitely Paris.",   # not abstain → wrong
        })
        axis = score_paper_aligned_accuracy(bench, self._fixture())
        self.assertEqual(axis.n_null, 1)
        # id3 should be incorrect (didn't abstain)
        null_row = [r for r in axis.per_query if r.id == 3][0]
        self.assertFalse(null_row.correct)
        self.assertEqual(null_row.rule, "miss")

    def test_by_question_type_breakdown(self):
        bench = self._bench({
            1: "Sam Bankman-Fried FTX",
            2: "Yes",
            3: "insufficient information",
        })
        axis = score_paper_aligned_accuracy(bench, self._fixture())
        bt = axis.by_question_type
        self.assertEqual(bt["inference_query"]["accuracy_primary"], 1.0)
        self.assertEqual(bt["null_query"]["accuracy_primary"], 1.0)
        self.assertEqual(int(bt["comparison_query"]["n"]), 1)

    def test_counts_partition(self):
        bench = self._bench({1: "x", 2: "y", 3: "z"})
        axis = score_paper_aligned_accuracy(bench, self._fixture())
        self.assertEqual(axis.n_queries, 3)
        self.assertEqual(axis.n_answerable, 2)
        self.assertEqual(axis.n_null, 1)

    def test_real_fixture_smoke(self):
        # Runs against the real multihop fixture + a trivial all-miss bench;
        # just ensures no crash + sane partition (75 answerable / 25 null).
        mh = _ROOT / "workspaces" / "hotpot_eval" / "eval" / "multihop_rag_queries.json"
        if not mh.exists():
            self.skipTest("multihop fixture not present")
        fixture = json.loads(mh.read_text(encoding="utf-8"))
        bench = {"results": [{"id": q["id"], "status": "ok", "blocked": False,
                              "answer_preview": "", "answer_len": 0}
                             for q in fixture["queries"]]}
        axis = score_paper_aligned_accuracy(bench, fixture)
        self.assertEqual(axis.n_answerable, 75)
        self.assertEqual(axis.n_null, 25)
        # empty answers → null queries abstain (correct), answerable all miss
        self.assertEqual(axis.correct_primary, 25)  # only the 25 null abstains


if __name__ == "__main__":
    unittest.main()
