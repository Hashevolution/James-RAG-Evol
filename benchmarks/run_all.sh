#!/usr/bin/env bash
#
# benchmarks/run_all.sh — single-command reproduction entry point.
#
# Goal: a fresh clone reproduces the project's PUBLISHED, DETERMINISTIC
# benchmark numbers (RAB v0.1.1 + LRB v0.2.x) in well under 15 minutes,
# with no LLM call and no hidden preprocessing.
#
#   git clone https://github.com/Hashevolution/James-RAG-Evol.git
#   cd James-RAG-Evol
#   python -m pip install -r requirements.txt
#   bash benchmarks/run_all.sh
#
# Tiers (honest split — see benchmarks/REPRODUCIBILITY.md §3):
#   (default)     CORE — RAB (3 SUTs) + LRB Phase B. Deterministic, no LLM,
#                 byte-identical across machines. ~1-2 min.
#   --full        CORE + LRB S3 publication-scale (1000 docs, deterministic
#                 retrieval scoring, no LLM). ~3-6 min.
#   --with-llm    CORE + RAGAS suite. Requires a running Ollama + the server.
#                 LLM-judge metrics are BAND-checked, not point-identical
#                 (see eval/ragas/baseline.json tolerance). Adds ~90 min.
#
# This script only ORCHESTRATES the committed runners; it adds no new
# measurement logic. Every command it calls is documented in README.md
# "Reproduce in 60 seconds".
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WITH_LLM=0
FULL=0
for arg in "$@"; do
  case "$arg" in
    --with-llm) WITH_LLM=1 ;;
    --full)     FULL=1 ;;
    -h|--help)
      sed -n '2,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown arg: $arg (try --help)" >&2; exit 2 ;;
  esac
done

PY="${PYTHON:-python}"

hr()   { printf '%.0s=' {1..70}; printf '\n'; }
note() { printf '\n>>> %s\n' "$1"; }

note "JAMES reproduction harness — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "repo: $REPO_ROOT"
echo "python: $($PY --version 2>&1)"
echo "git sha: $(git rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
echo "tiers: core$([ $FULL -eq 1 ] && echo ' +full')$([ $WITH_LLM -eq 1 ] && echo ' +with-llm')"

# ---------------------------------------------------------------------------
hr; note "RAB v0.1.1 — Replayable-Audit Benchmark (scenario S1, deterministic)"
echo "Expected gap structure (NOT a JAMES-wins claim — see SPEC §6.5):"
echo "  reference  AC/RF/PC = 1.000 / 1.000 / 1.000"
echo "  baseline0  AC/RF/PC = 0.275 / 0.000 / 0.000   (vanilla default logging)"
echo "  james      AC/RF/PC = 1.000 / 1.000 / 1.000   (audit-native)"
echo
for sut in reference baseline0 james; do
  $PY scripts/research/rab_run.py --sut "$sut"
  echo
done

# ---------------------------------------------------------------------------
hr; note "LRB Phase B — Lifecycle Retrieval Benchmark (S1+S2 time-travel, token-mode)"
echo "Expected: R@1 V < N < J on S2, JAMES - Naive gap > +0.10 (deterministic)."
echo "Building scenario fixtures (gitignored — regenerated deterministically)..."
$PY scripts/research/build_lrb_scenario_s1.py
$PY scripts/research/build_lrb_scenario_s2.py
echo
PYTHONPATH=. $PY scripts/research/lrb_run_phase_b.py --scenarios S1,S2

# ---------------------------------------------------------------------------
if [ $FULL -eq 1 ]; then
  hr; note "LRB S3 — publication-scale (1000 docs / ~5.6k events / 1000 queries)"
  $PY scripts/research/build_lrb_scenario_s3.py --scale publication
  $PY scripts/research/lrb_run_s3.py --scale publication
fi

# ---------------------------------------------------------------------------
if [ $WITH_LLM -eq 1 ]; then
  hr; note "RAGAS suite (LLM-judge; band-checked, not point-identical)"
  echo "Requires Ollama running (model: gemma4:e4b) + JAMES server. See"
  echo "benchmarks/REPRODUCIBILITY.md §4 for the LLM prerequisites."
  $PY eval/ragas/run_ragas.py --check
fi

# ---------------------------------------------------------------------------
hr; note "DONE."
echo "Compare your output against benchmarks/README.md '#expected-output'."
echo "Reproduced something different? Open a reproduction-report issue —"
echo "see benchmarks/REPRODUCTION_PROGRAM.md."
