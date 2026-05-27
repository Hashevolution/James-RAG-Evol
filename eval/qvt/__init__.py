"""QVT (Quality Verification Track) — non-saturating quality oracle.

Public API:

  from eval.qvt import score_three_axis, ThreeAxisResult

  result = score_three_axis(
      bench_results_path="reports/research-runs/step7-bench-*.json",
      fixture_path="eval/regression/step7_queries.json",
  )
  print(result.summary())

Design memo: docs/design/v0.4-qvt-alpha-non-saturating-oracle.md
"""
from eval.qvt.oracle import (  # noqa: F401
    AbstentionF1Axis,
    AbstentionQueryRow,
    GradedAnswerAxis,
    GradedAnswerQueryRow,
    PathCoverageAxis,
    PathCoverageQueryRow,
    ThreeAxisResult,
    detect_abstention,
    score_abstention_f1,
    score_graded_answer,
    score_path_coverage,
    score_three_axis,
)

__all__ = [
    "AbstentionF1Axis",
    "AbstentionQueryRow",
    "GradedAnswerAxis",
    "GradedAnswerQueryRow",
    "PathCoverageAxis",
    "PathCoverageQueryRow",
    "ThreeAxisResult",
    "detect_abstention",
    "score_abstention_f1",
    "score_graded_answer",
    "score_path_coverage",
    "score_three_axis",
]
