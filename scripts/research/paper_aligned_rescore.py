"""Re-score existing multihop_rag bench JSONs with the paper-aligned
binary accuracy metric (MultiHop-RAG, arXiv:2401.15391 Table 6).

No new measurement — reads bench JSONs already on disk and applies
`eval.qvt.oracle.score_paper_aligned_accuracy`. Prints a comparison
table against the paper's published baselines.

Usage:
  python scripts/research/paper_aligned_rescore.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from eval.qvt.oracle import score_paper_aligned_accuracy  # noqa: E402

FIXTURE = ROOT / "workspaces" / "hotpot_eval" / "eval" / "multihop_rag_queries.json"

# Paper Table 6 (retrieved chunks) — the comparable league for a
# JAMES + local model run is the open-model row, not GPT-4.
PAPER_BASELINE = {
    "GPT-4 (paper, retrieved)":        0.56,
    "Claude-2.1 (paper, retrieved)":   0.52,
    "Google-PaLM (paper, retrieved)":  0.47,
    "ChatGPT/3.5 (paper, retrieved)":  0.44,
    "Mixtral-8x7B (paper, retrieved)": 0.32,
    "Llama-2-70b (paper, retrieved)":  0.28,
}

# JAMES bench JSONs to rescore. (label, path-relative-to-reports)
# Paths from this cycle's measurements + α-8 closure baselines.
JAMES_RUNS = [
    ("JAMES+gemma4:e4b ontology (α-8 run1)",
     "bench_b3c4562_multihop_rag_20260603_022251.json"),
    ("JAMES+gemma4:e4b ontology (α-8 run2)",
     "bench_b3c4562_multihop_rag_20260603_030944.json"),
    ("JAMES+gemma4:e4b ontology (α-8 run3)",
     "bench_b3c4562_multihop_rag_20260603_035644.json"),
    ("JAMES+Claude(Opus) ontology (Stage4 run1, 99/100 valid)",
     "bench_4a6c7b9_multihop_rag_20260604_042155.json"),
    ("Claude(Opus) RAW no-JAMES (Stage4b, learning-leak suspect)",
     "bench_4a6c7b9_multihop_rag_20260604_081922.json"),
]


def main() -> int:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reports = ROOT / "reports"

    print(f"fixture: {FIXTURE.name} ({len(fixture['queries'])} queries)")
    print("metric: paper-aligned binary accuracy [strict, primary] band")
    print("=" * 78)

    results = []
    for label, fname in JAMES_RUNS:
        path = reports / fname
        if not path.exists():
            print(f"[skip] {label}: {fname} not found")
            continue
        bench = json.loads(path.read_text(encoding="utf-8"))
        axis = score_paper_aligned_accuracy(bench, fixture)
        results.append((label, axis))

    # ── Overall comparison table ──
    print(f"\n{'System':<58s} {'primary':>8s} {'strict':>8s}")
    print("-" * 78)
    # Paper baselines first (sorted desc)
    for name, acc in sorted(PAPER_BASELINE.items(), key=lambda x: -x[1]):
        print(f"{name:<58s} {acc:>8.2f} {'—':>8s}")
    print("-" * 78)
    for label, axis in results:
        print(f"{label:<58s} {axis.accuracy_primary:>8.3f} "
              f"{axis.accuracy_strict:>8.3f}")

    # ── Per-question-type breakdown for JAMES runs ──
    print(f"\n{'='*78}\nPer-question-type (primary metric):")
    for label, axis in results:
        print(f"\n{label}")
        print(f"  n_answerable={axis.n_answerable} n_null={axis.n_null} "
              f"correct_primary={axis.correct_primary} "
              f"correct_strict={axis.correct_strict}")
        for qt, d in axis.by_question_type.items():
            print(f"  {qt:18s} primary={d['accuracy_primary']:.3f} "
                  f"strict={d['accuracy_strict']:.3f} (n={int(d['n'])})")

    print(f"\n{'='*78}")
    print("CAVEAT: metric is an approximation of the paper's exact-match")
    print("(paper doesn't publish matching logic); JAMES gold_signals are")
    print("multi-term vs paper single-answer; model/corpus-size differ.")
    print("Use [strict, primary] band as positional signal, not exact rank.")
    print("Fair league for JAMES+small-local = Mixtral 0.32 / Llama-70b 0.28.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
