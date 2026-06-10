#!/usr/bin/env bash
# Cycle γ Phase C.2 — MuSiQue paired ablation runner (GAIN half).
# Pre-registered design: docs/research/cycle-gamma-phase-c2-preregistration-2026-06-10.md
#   - cells: R0 (full JAMES) + DISABLE_RERANK + DISABLE_COGNITIVE_STAGES
#   - typed_filter EXCLUDED (home turf = adversarial, separate track)
#   - n=25 first-N slice — corpus build MUST have used --max-rows 25
#
# Usage:  bash scripts/research/_phase_c2_musique_ablation.sh <model> <tag>
#   e.g.  bash scripts/research/_phase_c2_musique_ablation.sh mixtral:8x7b mxtral
set -u

ROOT="$(pwd)"
WORKSPACE="$ROOT/workspaces/cycle_gamma_musique_ans"
OUTDIR="$ROOT/reports/cycle_gamma/phase-c2"
mkdir -p "$OUTDIR"

MODEL="$1"           # e.g. mixtral:8x7b / gemma4:e4b / llama3.1:8b
TAG="$2"             # short slug for filenames: mxtral / gemma4 / llama
N=25

run_one () {
  local label="$1"; shift
  local out="$OUTDIR/musique-ans-$TAG-$label.json"
  echo ">>> [$TAG] $label -> $out"
  env "JAMES_WORKSPACE=$WORKSPACE" "$@" \
    python scripts/external_bench_run.py --bench musique --variant ans \
    --mode james --model "$MODEL" --n-samples "$N" \
    --out "$out" 2>&1
  echo "<<< [$TAG] $label done (exit $?)"
}

# R0 baseline first — §5 cell-validity gate (R0 f1 <= 0.05 on all
# models => wiring suspicion, stop and diagnose before knobs).
run_one R0
run_one rerank          JAMES_DISABLE_RERANK=1
run_one cognitive_stages JAMES_DISABLE_COGNITIVE_STAGES=1

echo "=== [$TAG] PHASE C.2 DONE ==="
