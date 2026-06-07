"""``eval.external`` — Cycle γ external-benchmark integration.

Cycle γ measures JAMES against 4 external academic benchmarks
(RGB / ALCE / MuSiQue / 2WikiMultiHopQA) to produce publication-grade
cross-bench evidence beyond the single MultiHop-RAG baseline used
through v0.4.2. Design memo:
``docs/design/v0.4-cycle-gamma-external-benchmark-integration.md``.

This package is the integration layer:

* Phase A.0 (this file + ``base.py``) — abstract ``ExternalBenchFixture``
  + unified ``ExternalQuery`` schema. Dependency-free.
* Phase A.1 — RGB loader.
* Phase A.2 — ALCE (ASQA + QAMPARI) loader.
* Phase A.3 — MuSiQue + 2WikiMultiHopQA loaders.
* Phase A.4 — per-bench scorers (RGB negative-rejection F1, ALCE
  NLI-based citation precision/recall, MuSiQue/2Wiki EM-F1 +
  support fact accuracy).
* Phase A.5 — unified ``external_bench_run.py`` runner.

The base class deliberately does **not** depend on the HuggingFace
``datasets`` library — that decision lives at Phase A.1 (per-loader)
so we can swap to raw HTTP downloads or an offline cache without
re-touching the abstract interface.

Self-eval trap rule applies (memory
``feedback_self_evaluation_trap``): JAMES does NOT write its own
fixtures or its own oracle for these benchmarks. Each loader pulls
the original published fixture; each scorer implements the
benchmark's official scoring formula (or a documented faithful
approximation).
"""
from eval.external.base import (
    ExternalBenchFixture,
    ExternalQuery,
)
from eval.external.scorer_base import (
    ExternalScorer,
    ScoreAxis,
)


__all__ = [
    "ExternalBenchFixture",
    "ExternalQuery",
    "ExternalScorer",
    "ScoreAxis",
]
