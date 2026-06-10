#!/usr/bin/env bash
# Phase E-min cross-model runner (gemma4 + llama) — Step 2a
# 3 components x 2 axes per model. Each run n=25.
set -u

ROOT="$(pwd)"
WORKSPACE_FULL="$ROOT/workspaces/cycle_gamma_rgb_full"
WORKSPACE_NEGREJ="$ROOT/workspaces/cycle_gamma_rgb_negrej"
OUTDIR="$ROOT/reports/cycle_gamma/phase-e"
mkdir -p "$OUTDIR"

MODEL="$1"           # e.g. gemma4:e4b  or  llama3.1:8b
TAG="$2"             # short slug for filenames: gemma4 / llama

run_one () {
  local knob="$1" axis="$2" ws="$3" setting="$4" slug="$5"
  local out="$OUTDIR/phase-e-$TAG-$axis-$slug.json"
  echo ">>> [$TAG] $knob / $axis -> $out"
  env "JAMES_WORKSPACE=$ws" "JAMES_$knob=1" \
    python scripts/external_bench_run.py --bench rgb --variant en \
    --mode james --model "$MODEL" \
    --setting-filter "$setting" --n-samples 25 \
    --out "$out" 2>&1
  echo "<<< [$TAG] $knob / $axis done (exit $?)"
}

for KNOB in DISABLE_RERANK DISABLE_TYPED_FILTER DISABLE_COGNITIVE_STAGES; do
  SLUG=$(echo "$KNOB" | tr 'A-Z' 'a-z' | sed 's/disable_//')
  run_one "$KNOB" noise  "$WORKSPACE_FULL"   noise_robustness   "$SLUG"
  run_one "$KNOB" negrej "$WORKSPACE_NEGREJ" negative_rejection "$SLUG"
done

echo "=== [$TAG] ALL DONE ==="
