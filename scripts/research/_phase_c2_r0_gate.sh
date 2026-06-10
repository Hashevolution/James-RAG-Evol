#!/usr/bin/env bash
# Cycle γ Phase C.2 — R0 cell-validity gate (pre-registration §5).
# Runs R0 (full JAMES, no knob) on MuSiQue-ans n=25 for all 3 models.
# If R0 f1 <= 0.05 on ALL 3 models => wiring suspicion, stop + diagnose
# before spending the knob runs.
set -u

ROOT="$(pwd)"
WS="$ROOT/workspaces/cycle_gamma_musique_ans"
OUTDIR="$ROOT/reports/cycle_gamma/phase-c2"
mkdir -p "$OUTDIR"
N=25

for spec in "mixtral:8x7b mxtral" "gemma4:e4b gemma4" "llama3.1:8b llama"; do
  set -- $spec
  MODEL="$1"; TAG="$2"
  OUT="$OUTDIR/musique-ans-$TAG-R0.json"
  echo ">>> R0 [$TAG] $MODEL -> $OUT"
  env "JAMES_WORKSPACE=$WS" \
    python scripts/external_bench_run.py --bench musique --variant ans \
    --mode james --model "$MODEL" --n-samples "$N" \
    --out "$OUT" 2>&1 | tail -8
  echo "<<< R0 [$TAG] done (exit ${PIPESTATUS[0]})"
done

echo "=== R0 GATE DONE ==="
