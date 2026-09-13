# LRB v0.2.3b — 3-model LLM-grounded S3 **publication** results on the S3.2 fixture (2026-09-13)

Runner: `scripts/research/lrb_run_v023b_s3_cross_model.py
--scale publication --modes llm-grounded --models gemma4:e4b,gemma3:12b,mixtral:8x7b`
(run id `20260912T121519Z`). Prereg: `docs/research/lrb-v023b-s3-cross-model-preregistration-2026-06-12.md`
(config unchanged; verdict matrix §2 applied as written).
Supersedes `lrb-v023b-3model-llm-grounded-publication-20260910.md` (the same
cells on the pre-S3.2 fixture `662fc2b7…`, kept as the record of the
project-lead ceiling that S3.2 removed — `docs/research/lrb-v023-s3-publication-scale-results-2026-09-12-s32.md`).

| | |
|---|---|
| Fixture | `eval/external/_fixtures/lrb/scenario_S3_publication.json`, **S3.2**, sha `cc98e141a4b4…` (330/330 unique project titles, 0 ambiguous query texts) |
| Scale | 1000 initial docs / 5620 events / 1000 queries |
| Cells | 3 SUTs × 3 local rerankers = **9**, n=1000 each, errors 0, **rerank fallbacks 0 / 9000 rows** (#1123 accounting) |
| Wall clock | 2026-09-12 21:14 → 09-13 19:48 KST = **22 h 34 min** (gemma4 ≈ 50 min per cell, gemma3:12b ≈ 70 min, mixtral 4.9–6.2 h) |
| Code | generator/fixture at `e2c59b1` (#1122); runner at `2549266` (#1123, fallback flags); the claude CLI changes (#1124, #1126) do not touch the Ollama path |
| Log | `reports/research-runs/_v023b_publication_3model_s32_20260912.log` (gitignored, `EXIT=0`) |
| 4th leg | `claude-haiku-4-5` **in progress** on the same fixture with quota-aware retry (#1126); reported separately when it lands |

## 1. Gap table (R@1 = the fact that is correct *for the queried valid_time*, at rank 1)

| reranker | vanilla | naive-supersede | **james** | V<N<J | **J−N** | J−V |
|---|---|---|---|---|---|---|
| gemma4:e4b   | 0.554 | 0.819 | **0.989** | ✅ | **+0.170** | +0.435 |
| gemma3:12b   | 0.634 | 0.813 | **0.991** | ✅ | **+0.178** | +0.357 |
| mixtral:8x7b | 0.550 | 0.754 | **0.893** | ✅ | **+0.139** | +0.343 |
| *(ref) token-mode, same fixture (S3.2, 2026-09-12)* | *0.566* | *0.827* | *0.984* | *✅* | *+0.157* | *+0.418* |

Temporal accuracy (gold in the top-10 at the queried valid_time): james
**0.995–1.000**, naive-supersede **0.827–0.831**, vanilla 0.977–0.984. Per
window, V / N / J:

| window | n | gemma4:e4b | gemma3:12b | mixtral:8x7b |
|---|---|---|---|---|
| qt=52 / vt=0 (early)    | 100 | 1.000 / **0.250** / 1.000 | 0.940 / **0.210** / 0.970 | 0.970 / **0.230** / 0.950 |
| qt=52 / vt=17 (mid)     | 200 | 0.920 / **0.520** / 1.000 | 0.915 / **0.530** / 1.000 | 0.925 / **0.540** / 1.000 |
| qt=52 / vt=52 (current) | 700 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |

## 2. Pre-registered verdict (prereg §2)

| Leg | S3 pub R@1 V<N<J | J−N > +0.10 | Verdict |
|---|---|---|---|
| 1 gemma4:e4b (4B)          | ✅ | ✅ +0.170 | leg-clear |
| 2 gemma3:12b (12B)         | ✅ | ✅ +0.178 | leg-clear |
| 3 mixtral:8x7b (47B)       | ✅ | ✅ +0.139 | leg-clear |
| 4 claude-haiku-4-5 (cloud) | in progress | in progress | — |

**3/3 local legs clear** on the S3.2 fixture; the 4/4 row waits for the
cloud leg. Composite as it stands: **⭐⭐⭐ pattern + gap, cross-model (3
local rerankers) at publication scale**. Honest tier for magnitudes:
⭐⭐ scenario-sensitive between S2 (hand-curated) and S3 (synthetic) —
unchanged — while the earlier *within-S3* caveat is gone with the ceiling.

## 3. What changed against the pre-S3.2 run (2026-09-10, same cells)

| reranker | J pre-S3.2 | **J S3.2** | Δ J | J−N pre | **J−N S3.2** | Δ gap |
|---|---|---|---|---|---|---|
| gemma4:e4b   | 0.848 | **0.989** | +0.141 | +0.134 | **+0.170** | +0.036 |
| gemma3:12b   | 0.849 | **0.991** | +0.142 | +0.142 | **+0.178** | +0.036 |
| mixtral:8x7b | 0.784 | **0.893** | +0.109 | +0.127 | **+0.139** | +0.012 |

Exactly what the 2026-09-10 report §4 predicted: the project-lead ceiling
had held N and J to the same 0.256 on 19.1 % of queries, so removing it
raises J and *widens* J−N — it never inflated the gap. `current-project-lead`
is now 0.99–1.00 for N and J under every reranker (V 0.34–0.61: stale v1
leads still win rank 1 on superseded projects, the vanilla mechanism).

## 4. Findings

1. **V<N<J holds 3/3 at N=1000 under LLM reranking on an artefact-free
   fixture; J−N = +0.139 … +0.178.** Token mode on the same fixture gives
   +0.157. Combined with S2 (5/5 legs on the repaired fixture, 2026-09-12)
   the ordering and gap structure now reproduce across scenario × scale ×
   reranker × mode with no known oracle ceiling underneath.
2. **Backbone size still does not widen the gap.** mixtral 47B has the
   smallest gap (+0.139) and the lowest james R@1 (0.893); the two gemma
   cells are within 0.002 of each other. mixtral's misses are the
   historical director windows (0.38 / 0.65) and historical-mid-project-lead
   (0.48) — genuine reranker misses that V and N share in proportion, not
   a fixture property (the guard passes; token mode scores 1.00 / 1.00 /
   0.85 there).
3. **The two-axis story is unchanged.** naive-supersede buys current-fact
   R@1 by deleting history (temporal accuracy 0.21–0.25 at vt=0, 0.52–0.54
   at vt=17); james keeps both axes; vanilla keeps history but lets stale
   facts win rank 1.
4. **Hygiene.** 0 fallbacks in 9000 rows; no row near the 60 s timeout.
   mixtral cells ran 4.9–6.2 h (17.7–22.2 s per query) against 4.7 h /
   16.8–17.2 s on 2026-09-10 — the claude cloud leg was running on the
   same machine for most of this run, so the mixtral latency axis carries
   contention; compare it only within this run.

## 5. Per-category R@1 (V / N / J)

| category | n | gemma4:e4b | gemma3:12b | mixtral:8x7b | token-mode |
|---|---|---|---|---|---|
| current-contract            | 125 | 0.10 / 1.00 / 1.00 | 0.04 / 1.00 / 1.00 | 0.02 / 0.96 / 0.96 | 0.00 / 1.00 / 1.00 |
| current-director            | 125 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.98 / 0.91 / 0.91 | 1.00 / 1.00 / 1.00 |
| current-policy              | 125 | 0.00 / 0.98 / 0.98 | 0.46 / 1.00 / 1.00 | 0.00 / 1.00 / 1.00 | 0.00 / 0.98 / 0.98 |
| **current-project-lead**    | 125 | 0.34 / **1.00** / **1.00** | 0.44 / **1.00** / **1.00** | 0.61 / **1.00** / **1.00** | 0.34 / 0.99 / 0.99 |
| historical-early-contract   |  50 | 0.96 / 0.00 / 1.00 | 1.00 / 0.00 / 1.00 | 0.96 / 0.00 / 0.98 | 1.00 / 0.00 / 1.00 |
| historical-early-director   |  50 | 0.52 / 0.50 / 1.00 | 0.42 / 0.40 / 0.92 | 0.28 / 0.04 / 0.38 | 0.50 / 0.50 / 1.00 |
| historical-mid-director     |  66 | 0.58 / 0.68 / 0.91 | 0.67 / 0.53 / 0.95 | 0.35 / 0.29 / 0.65 | 0.76 / 0.76 / 1.00 |
| historical-mid-policy       |  68 | 0.46 / 0.35 / 0.97 | 0.59 / 0.41 / 1.00 | 0.56 / 0.41 / 0.97 | 0.59 / 0.38 / 0.97 |
| **historical-mid-project-lead** | 66 | 0.47 / 0.42 / **1.00** | 0.56 / 0.45 / **0.97** | 0.39 / 0.32 / **0.48** | 0.52 / 0.45 / 0.85 |
| never-stale-budget          | 200 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

No category is held at an SUT-independent value any more; no category has
R@10 = 0 for all SUTs (naive-supersede `historical-early-contract` 0.00 is
the delete-history mechanism).

## 6. Honest caveats

- Three local rerankers; the cloud leg is running and is not claimed.
- Magnitudes remain scenario-sensitive (S2 hand-curated 0.76–1.00 vs S3
  synthetic 0.89–0.99 for james); compare within a scenario.
- LLM reranking is stochastic (~10 pp band, PR #819); one run of 1000
  queries per cell. The gaps clear the band on the primary axis; nothing
  finer is claimed.
- Per-cell `result.json` committed (with `rerank_fallbacks`); `bench.jsonl`
  and the log gitignored.

## 7. One-line

On the artefact-free S3.2 fixture at N=1000, three local LLM rerankers
keep V<N<J with J−N +0.139 … +0.178 and james temporal accuracy ≥ 0.995,
0 silent fallbacks in 9000 rows; the +0.11 … +0.14 rise in JAMES R@1 over
the 2026-09-10 run is the removed project-title ceiling, and the gap
widened with it, as predicted.
