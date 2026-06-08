# Phase B Option B — Cross-bench operator guide

**Purpose**: Step-by-step operator instructions to download ALCE /
MuSiQue / 2WikiMultiHopQA fixtures so the cycle γ runner can drive
those benches end-to-end like RGB.

**Date**: 2026-06-08
**Status**: operator-gated. Each bench has different license /
download method. Allocate ~30-60 min for setup; ~10-30 min per
bench for first smoke.

---

## 1. Why operator-gated

ALCE / MuSiQue / 2Wiki are licensed datasets distributed through
different channels (Princeton-NLP GitHub script / StonyBrookNLP
GitHub zip / Dropbox link). Auto-download from the cycle γ loader
would couple the loader to fragile external scripts; the loader
intentionally requires pre-populated fixtures (`FileNotFoundError`
when missing) so corpus provenance is operator-controlled.

Per cycle γ Phase A handover §4 Option B + Phase C handover §8:
this is the operator step that unblocks Phase B Option B.

---

## 2. Each bench — download + place

### 2.1 ALCE (ASQA / QAMPARI / ELI5)

**Upstream**: https://github.com/princeton-nlp/ALCE
**License**: MIT (per Princeton-NLP repo)
**Total size**: ~1-2 GB after download
**Loader expects**: `eval/external/_fixtures/alce/<variant>_eval_*.json`

Setup:

```bash
# In a scratch dir (not in this repo)
cd /tmp
git clone https://github.com/princeton-nlp/ALCE
cd ALCE
bash download_data.sh

# Copy the eval JSONs into the JAMES cache dir
mkdir -p <JAMES_REPO>/eval/external/_fixtures/alce
cp data/asqa_eval_gtr_top100.json <JAMES_REPO>/eval/external/_fixtures/alce/
cp data/qampari_eval_gtr_top100.json <JAMES_REPO>/eval/external/_fixtures/alce/
cp data/eli5_eval_bm25_top100.json <JAMES_REPO>/eval/external/_fixtures/alce/
```

Verify:

```bash
cd <JAMES_REPO>
python -c "from eval.external.runner import build_loader; \
  L = build_loader('alce', variant='asqa'); \
  print('ALCE-ASQA queries:', len(L.iter_queries(n_samples=5)))"
```

Expected: prints `ALCE-ASQA queries: 5` (or whatever number, no
FileNotFoundError).

### 2.2 MuSiQue

**Upstream**: https://github.com/StonyBrookNLP/musique
**License**: CC-BY 4.0
**Total size**: ~600 MB after unpack
**Loader expects**: `eval/external/_fixtures/musique/musique_<variant>_v1.0_<split>.jsonl`

Setup:

```bash
# Download the MuSiQue v1.0 zip from the StonyBrookNLP repo's
# README link (currently Google Drive — operator must accept the
# Google Drive download UI manually):
# https://github.com/StonyBrookNLP/musique#data-release

# After download to /tmp/musique_v1.0.zip:
cd /tmp
unzip musique_v1.0.zip -d musique_v1.0

mkdir -p <JAMES_REPO>/eval/external/_fixtures/musique
# Copy the dev splits (ans + full variants):
cp musique_v1.0/data/musique_ans_v1.0_dev.jsonl \
   <JAMES_REPO>/eval/external/_fixtures/musique/
cp musique_v1.0/data/musique_full_v1.0_dev.jsonl \
   <JAMES_REPO>/eval/external/_fixtures/musique/
```

Verify:

```bash
cd <JAMES_REPO>
python -c "from eval.external.runner import build_loader; \
  L = build_loader('musique', variant='ans', split='dev'); \
  print('MuSiQue-ans queries:', len(L.iter_queries(n_samples=5)))"
```

### 2.3 2WikiMultiHopQA

**Upstream**: https://github.com/Alab-NII/2wikimultihop
**License**: Apache-2.0
**Total size**: ~400 MB after unpack
**Loader expects**: `eval/external/_fixtures/2wiki/<split>.json`

Setup:

```bash
# Download data.zip from the Alab-NII repo's README link
# (currently Dropbox — operator must accept the Dropbox download
# manually):
# https://github.com/Alab-NII/2wikimultihop#dataset

# After download to /tmp/2wiki_data.zip:
cd /tmp
unzip 2wiki_data.zip -d 2wiki_data

mkdir -p <JAMES_REPO>/eval/external/_fixtures/2wiki
# Copy the dev split:
cp 2wiki_data/dev.json <JAMES_REPO>/eval/external/_fixtures/2wiki/
```

Verify:

```bash
cd <JAMES_REPO>
python -c "from eval.external.runner import build_loader; \
  L = build_loader('2wiki', split='dev'); \
  print('2Wiki dev queries:', len(L.iter_queries(n_samples=5)))"
```

---

## 3. Once all three fixtures are present

Run the closed-corpus baseline on each bench (mirrors the Phase
B/C RGB-en pattern):

```bash
# ALCE-ASQA closed-corpus baseline (n=25)
python scripts/external_bench_run.py --bench alce --variant asqa \
  --mode closed-corpus --model gemma4:e4b \
  --n-samples 25 --progress-every 5 \
  --out reports/cycle_gamma/alce-asqa-baseline-20260608.json

# MuSiQue-ans closed-corpus baseline (n=25)
python scripts/external_bench_run.py --bench musique --variant ans \
  --split dev --mode closed-corpus --model gemma4:e4b \
  --n-samples 25 --progress-every 5 \
  --out reports/cycle_gamma/musique-ans-baseline-20260608.json

# 2Wiki dev closed-corpus baseline (n=25)
python scripts/external_bench_run.py --bench 2wiki --split dev \
  --mode closed-corpus --model gemma4:e4b \
  --n-samples 25 --progress-every 5 \
  --out reports/cycle_gamma/2wiki-baseline-20260608.json
```

Each run produces a result JSON in `reports/cycle_gamma/`
(gitignored). The runner's existing comparison tool
(`scripts/research/cycle_gamma_rgb_compare.py`) can pairwise-
compare ANY two result JSONs from the same bench, so the same
pattern that built the RGB-en comparison tables (Phase C) works
out of the box.

---

## 4. JAMES-engine extension (for the "true signal" hypothesis test)

The cycle γ §C handover §8 noted that if "JAMES emits a benchmark-
level latent abstention signal" is to extend beyond RGB-en, the
identical-per-query overlap pattern (mxtral ≡ llama JAMES set)
should reproduce on at least one of ALCE / MuSiQue / 2Wiki.

To test this hypothesis, run JAMES-engine mode for each bench on
mxtral + llama (the two models that achieved full absorption on
RGB-en):

```bash
# Workspace setup PER BENCH
# Each bench has different doc structure. Adapt the cycle γ corpus
# builder (scripts/research/cycle_gamma_rgb_corpus_build.py) for
# the new bench, or write a one-off ingest script.

# Then run JAMES-engine per model:
JAMES_WORKSPACE=./workspaces/cycle_gamma_alce_full \
  python scripts/external_bench_run.py --bench alce --variant asqa \
  --mode james --model mixtral:8x7b --n-samples 25 \
  --out reports/cycle_gamma/alce-asqa-james-mixtral-20260608.json

# Repeat for llama3.1:8b + per-query overlap analysis.
```

**Note**: Cycle γ Phase A's corpus builder was specifically for
RGB-en. Adapting it to ALCE / MuSiQue / 2Wiki is a small (~30
min) extension — each bench has different positive/distractor
structure but the same `add_documents_with_meta` pattern. If
operator wants this work done as code, it's a separate small PR
in a future session.

---

## 5. Honest-framing constraints (apply BEFORE claim-finalization)

Per `memory/feedback_finding_size_honest_framing.md` +
`memory/feedback_eval_cycle_vs_collab_arc_separation.md`:

1. **Per-bench n=25 ≠ universal-law evidence.** Even if all three
   benches show the same per-query identical-set pattern, the
   claim stays at ⭐⭐ confirmed (cross-bench reproducibility).
   ⭐⭐⭐ universal-law requires 20+ benches × 20+ models per the
   AbstentionBench precedent.
2. **Prior art holds.** AbstentionBench / RAG-as-scaffolding /
   Schapire / KD literature already cover the broad mechanism.
   Cross-bench reproduction adds empirical density but does NOT
   make the broad framing novel.
3. **NOT joint piece content.** Cycle γ Phase B+C+D (and any
   cross-bench extension) is JAMES-internal evaluation arc. Joint
   piece is on a separate research track. Per
   `memory/feedback_eval_cycle_vs_collab_arc_separation.md`.

---

## 6. Operator decision points

After fixtures are downloaded:

| Question | Decision |
|---|---|
| Run all 3 closed-corpus baselines first? | Recommended — quick (~5-10 min per bench at gemma4:e4b ~2s/q). Establishes "raw model on each bench" baseline before JAMES-engine work. |
| Adapt corpus builder for each bench? | Only if JAMES-engine mode is the goal. For closed-corpus only, no workspace needed. |
| Run JAMES mxtral on all 3 benches? | Significant compute (~30 min per bench at mxtral ~36s/q). Operator decides. |
| Run Phase D ablation matrix on cross-bench JAMES results? | Even larger compute. Defer until single-bench cross-model evidence justifies. |

---

## 7. If something goes wrong

| Symptom | Fix |
|---|---|
| `FileNotFoundError: ALCE asqa fixture not at ...` | Re-check Step 2.1 cp commands. Path must be `eval/external/_fixtures/alce/asqa_eval_gtr_top100.json`. |
| MuSiQue download blocked (Google Drive 403) | Try a different network or the alternative HuggingFace mirror if listed in the upstream repo |
| 2Wiki Dropbox link expired | Check the upstream README — they sometimes update mirror URLs |
| Loader prints `validate_queries` errors | Fixture file might have been corrupted during copy. Re-download. |
| Cycle γ runner crashes mid-bench | Check existing loader cache; `--n-samples` is bounded so retry should work with a smaller n |
