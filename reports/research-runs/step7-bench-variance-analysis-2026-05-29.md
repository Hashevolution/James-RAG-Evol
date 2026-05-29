# step7-bench baseline variance analysis (M4)

**Date**: 2026-05-29
**Trigger**: handover `docs/handovers/v0.4.x-session-2026-05-29-collaboration-checkpoint.md` §5 M4
**Author**: solo (Hashevolution)
**Status**: complete — see §6 Decision + §7 Recommended follow-up

## 1. Question

handover §5 M4 phrasing:

> step7-bench baseline 3-run variance analysis — pending. 3 baseline runs on 2026-05-28 same day. v0.4.1 lifecycle semantics changes (derived_from, cascade) may have shifted baselines. Risk: PR #399 cap-fix bench validation reproducibility questioned.

Two sub-questions:

- **Q1**: Are the 5/28 baseline 3 runs internally consistent (measurement noise within tolerable variance, no systematic regression)?
- **Q2**: Did v0.4.1 lifecycle commits (T6.A → T6.E cascade integration) shift the step7 baseline away from PR #399's cap-fix validation point?

## 2. Data inventory

| Label | File | git_sha | Capture time |
|---|---|---|---|
| `ref527` | `reports/research-runs/step7-bench-20260527_231211.json` | `f2c088f` | 2026-05-27 23:12 |
| `run1` | `reports/research-runs/step7-bench-baseline-run1-20260528_113557.json` | `2a31b20` | 2026-05-28 11:35 |
| `run2` | `reports/research-runs/step7-bench-baseline-run2-20260528_115715.json` | `2a31b20` | 2026-05-28 11:57 |
| `run3` | `reports/research-runs/step7-bench-baseline-run3-20260528_121845.json` | `2a31b20` | 2026-05-28 12:18 |

Suite: `step7` (16 queries), timeout cap = 120s per query.

## 3. 5/28 3-run variance (same sha `2a31b20`)

Pure measurement noise — the three runs are the same code on the same fixture.

| Run | total_seconds | ok | timeout | path_recall mean |
|---|---|---|---|---|
| run1 | 1333.4 | 14/16 | 2 (q1, q10) | 1.0 (4/4 full) |
| run2 | 1247.4 | 15/16 | 1 (q10) | 1.0 (5/5 full) |
| run3 | 1277.9 | 16/16 | 0 | 1.0 (5/5 full) |
| **mean** | **1286.2** | — | — | 1.0 across all runs |
| **stdev** | **43.5** | — | — | — |
| **range** | **86.0** | — | — | — |
| **CV** | **3.4%** | — | — | — |

### Status flip pattern (q1, q10)

Two queries flip between `timeout` (120.0s) and `ok` across the 3 runs. Per-run elapsed:

- **q1 (retrieve)**: 120.0 / 95.7 / 113.1 — all within or at the 120s boundary, status flip is the boundary effect, not a regression
- **q10 (negative)**: 120.0 / 120.0 / 98.7 — same boundary effect

Both queries are **boundary cases** sitting near the 120s timeout cap. Measurement noise on the order of ±15s is enough to flip status. This is not a systematic regression — it is the timeout cap itself catching a query that runs close to the limit.

### Highest-variance queries (excluding timeout flips)

| id | category | run1/2/3 elapsed | stdev | note |
|---|---|---|---|---|
| q3 | relation | 111.3 / 66.5 / 61.7 | 27.4s | widest spread (run1 ~1.8× run3) |
| q1 | retrieve | (boundary, see above) | 12.5s | |
| q10 | negative | (boundary, see above) | 12.3s | |
| q8 | dedup | 90.2 / 111.0 / 97.1 | 10.6s | |

### Lowest-variance queries (deterministic paths)

| id | category | run1/2/3 elapsed | stdev | note |
|---|---|---|---|---|
| q12 | security | 0.0 / 0.0 / 0.0 | 0.0 | immediate block path |
| q14 | narrow | 67.0 / 67.0 / 67.9 | 0.5 | deterministic narrow path |
| q15 | narrow | 56.7 / 57.4 / 56.6 | 0.4 | deterministic narrow path |
| q7 | compare | 110.1 / 107.1 / 105.4 | 2.4 | low-variance answer path |

### Q1 answer

Yes — the 5/28 3 runs are internally consistent. 3.4% CV on total seconds, path_recall identical at 1.0, status flips confined to boundary queries at the 120s cap. No systematic regression evidence.

## 4. 5/27 → 5/28 (ref `f2c088f` → baseline `2a31b20`)

### Commit window

7 commits landed between the two captures (oldest → newest):

| sha | PR | substance |
|---|---|---|
| `038751f` | #548 | docs(positioning) — Replayable RAG framing in README + ARCHITECTURE |
| `4ddc81a` | #549 | docs(retrieval) — F9.4 q15 entity-anchor closure result + bench audit |
| `c236a5c` | #550 | docs(qvt) — α design memo (non-saturating quality oracle) |
| `7804afa` | #551 | feat(eval) — QVT α-2 step7 fixture v4 → v5 (`gold_signals` + `abstention_truth`) |
| `d5a1c5a` | #552 | feat(eval) — QVT α-3 3-axis oracle module + baseline capture wrapper |
| `3d03c33` | #553 | chore(qvt) — α-4 PR template + CLAUDE.md rule 2 + ARCHITECTURE.md §5.7.10 |
| `2a31b20` | #554 | chore(release) — v0.4.0 post-mint DOI badges |

Code-impactful in this window:
- **#551 step7 fixture v4 → v5** — added `gold_signals` and `abstention_truth` fields per query. The fixture text and query count (16) are unchanged; the added fields are read by the QVT oracle, not by the bench runner. Bench latency should be unaffected.
- **#552 QVT oracle module** — new module under `eval/qvt/`. Not in the bench code path.
- Rest are docs / PR template / DOI badges — no code-path impact.

### Latency delta

| Metric | ref527 (`f2c088f`) | 5/28 mean (`2a31b20`) | Δ |
|---|---|---|---|
| total_seconds | 1323.1 | 1286.2 | **-36.9s (-2.8%)** |
| ok count | 15/16 | mean 15/16 | unchanged |
| path_recall mean | 1.0 | 1.0 | unchanged |

Per-query Δ (5/28 mean minus 5/27 ref, sorted by absolute):

| id | category | ref527 | 5/28 mean | Δ | note |
|---|---|---|---|---|---|
| q8 | dedup | 73.2 | 99.4 | **+26.2 (+35.8%)** | largest individual increase |
| q5 | multi-hop | 115.5 | 100.2 | -15.3 (-13.2%) | largest individual decrease |
| q3 | relation | 91.1 | 79.8 | -11.3 (-12.4%) | high-variance query (see §3) |
| q1 | retrieve | 120.0 | 109.6 | -10.4 | boundary, ref527 was timeout |
| q6 | multi-hop | 94.2 | 85.6 | -8.6 (-9.1%) | |
| q16 | narrow | 82.4 | 74.1 | -8.3 (-10.1%) | |
| q9 | lang-mix | 106.4 | 98.6 | -7.8 (-7.3%) | |
| q11 | security | 0.0 | 5.0 | +5.0 | ref527 was 0; small absolute |
| ... | rest | <±4s individually |

### Q2 answer (partial)

The 5/27 → 5/28 window contains **no T6 cascade commits**. T6.A through T6.E (the v0.4.1 lifecycle semantics work the M4 risk wording is about) all landed **after** the 5/28 baseline capture sha (`2a31b20`).

The -2.8% total delta in this window is attributable to QVT α-1/α-2/α-3/α-4 + docs PRs only. The fixture file additions (`gold_signals` / `abstention_truth`) are read by the oracle, not the bench runner, and the per-query latency delta pattern (some up, some down) is consistent with measurement noise plus minor runtime variation, not a step change.

**The Q2 question as worded in M4 cannot be answered from the existing data** — there is no post-T6 step7 baseline capture. See §5.

## 5. Critical finding — baseline sha is pre-T6

T6 PR landing sequence (verified via `git log --grep="T6\." 2a31b20..main`):

| PR | sha | merge time |
|---|---|---|
| T6.A `derived_from` schema | `3dab696` | 2026-05-28 PM |
| T6.B derivation extraction | `3ae22e5` | 2026-05-28 PM |
| T6.C `invalidate_derived_facts` | `74c56b2` | 2026-05-28 PM |
| T6.C.b refinement | `48a8010` | 2026-05-28 PM |
| T6.D cascade integration | `149d296` | 2026-05-28 PM |
| T6.E closure docs | `7fa24d2` | 2026-05-28 18:01 |

The 3 baseline runs were captured at 11:35, 11:57, 12:18 — all **before** any T6 PR landed. The baseline `2a31b20` is v0.4.0 closure + QVT α track + DOI bump, no lifecycle T6 changes.

**Implication for M4**:
- The M4 risk wording ("v0.4.1 lifecycle changes may have shifted baselines") cannot be directly verified or refuted from the captured baseline. The baseline does not contain the changes whose effect M4 is asking about.
- PR #399 cap-fix bench claim reproducibility against `2a31b20` is verifiable (and the §3 variance is normal). Against post-T6 main (`a23d7ef` at session end) it remains untested.

## 6. Decision

| sub-question | answer |
|---|---|
| Q1 (3-run variance internal consistency at `2a31b20`) | ✅ **Pass.** 3.4% CV on total, status flips confined to 120s-boundary queries, path_recall identical. |
| Q2 (v0.4.1 lifecycle T6 effect on baseline) | ⏭️ **Not yet measurable.** Captured baseline is pre-T6. The lifecycle effect requires a separate post-T6 capture run. |
| PR #399 cap-fix bench claim at `2a31b20` | ✅ **Reproducibility intact at the captured sha.** Same-day 3-run variance is well within the ±30% band the original claim cites. |
| PR #399 cap-fix bench claim at current main (`a23d7ef`, post-T6) | ⚠️ **Untested.** Requires the follow-up in §7. |

## 7. Recommended follow-up

A separate operator-run task — not blocking, but recommended before any future bench claim that references "v0.4.1 baseline":

1. **Capture 3-run baseline against current main HEAD** (`a23d7ef` or later) — same suite (`step7`), same per-query timeout (120s), same Ollama model + cap config as the 5/28 baseline. Estimated wall time: ~3 × 22min = ~66 min.
2. **Repeat §3-§4 analysis** with `2a31b20` as the new pre-reference and post-T6 sha as the new baseline. If the per-query Δ pattern stays inside ±15% (consistent with the §4 variance band), v0.4.1 lifecycle changes are confirmed bench-neutral. If a single query shows a large step change (e.g. q17 CEO acceptance added in step7 v6 per `tests/test_t2d3_dispatch_acceptance.py`), investigate that query specifically.
3. **Update handover §5 M4** from "Critical (pending)" to either "Resolved (lifecycle-neutral)" or "Critical (specific query regression identified)" based on (2)'s result.

This follow-up is operator-run because the wall-time budget (~1h Ollama inference) is the gating cost, not analysis time.

## 8. Out of scope

- v0.4-end QVT ablation matrix (18 cells × N=3) is a separate operator-run task (ROADMAP v0.4.1 OOS). Not blocked by this analysis.
- The 158.3s figure cited in PR #399's STEP 7 bench line is from a specific measurement context (single-mode mini-bench, not the full suite). This analysis covers the full-suite baseline, which is the framework PR #399's claim sits inside, not a literal reproduction of the single number.

## 9. Related

- handover doc `docs/handovers/v0.4.x-session-2026-05-29-collaboration-checkpoint.md` §5 M4, §6 Tier 1.3, §7 risk matrix
- launch-tracker `reports/promo-assets/launch-tracker.md` (5/28 baseline capture rows pending status update via §7 follow-up)
- ROADMAP `ROADMAP.md` v0.4.1 OOS section ("v0.4-end QVT ablation matrix")
- PR #399 cap-fix landing reference (handover §2 Phase R-line + V3'.a/.b/.c/.d sweep results)
- QVT baseline `eval/qvt/baseline_2a31b20.json` (same sha as this analysis's 5/28 baseline)
