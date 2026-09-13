# LRB v0.2.3b — claude cloud leg at S3 publication on the S3.2 fixture, and the 4-leg composite (2026-09-14)

Runner: `scripts/research/lrb_run_v023b_s3_cross_model.py --scale publication
--modes llm-grounded --models claude-haiku-4-5 --timeout 120` (run id
`20260912T213537Z`, started 2026-09-13 06:35 KST, finished 09-14 03:05 KST =
**20 h 30 min**). Code: #1124 (neutral cwd, tiny system prompt) + #1126
(quota-aware retry). Prereg: `docs/research/lrb-v023b-s3-cross-model-preregistration-2026-06-12.md`.
Companion: `lrb-v023b-3model-llm-grounded-publication-s32-20260913.md` (the
three local legs, same fixture).

Two earlier attempts at this leg (2026-09-12 afternoon and night) are
discarded: the Max-plan usage window ran out mid-cell and 763 / 1000, then
876 / 1000 · 1000 / 1000 · 281 / 1000 rows silently fell back to token
order (`lrb-v021-s2-llm-grounded-repaired-fixture-20260912.md` §2, #1123,
#1124, #1126). This third run is the clean one.

## 1. The three cells

| SUT | R@1 | R@5 | R@10 | temporal acc. | fallbacks | quota wait | elapsed | latency mean (net of wait) | rows = token top-10 |
|---|---|---|---|---|---|---|---|---|---|
| vanilla | **0.852** | 0.988 | 0.988 | 0.988 | **0** | 0 s | 6.73 h | 24.2 s | 509 / 1000 |
| naive-supersede | 0.833 | 0.833 | 0.833 | 0.833 | **0** | 0 s | 6.61 h | 23.8 s | 748 / 1000 |
| **james** | **0.990** | 1.000 | 1.000 | **1.000** | **0** | 6,600 s (11 × 10 min) | 7.15 h | 25.7 s (19.1 s) | 719 / 1000 |

J − N **+0.157**, J − V **+0.138**. Per window (V / N / J temporal accuracy):
vt=0 1.000 / 0.250 / 1.000; vt=17 0.940 / 0.540 / 1.000; vt=52 1.000 /
1.000 / 1.000 — the same two-axis shape as every other leg. The james
cell's `latency_s` includes the eleven 10-minute waits on the affected
rows (`rerank_quota_wait_s` = 6600); net of waits its mean is 19.1 s.

## 2. The 4-leg composite at S3 publication (S3.2 fixture `cc98e141…`, n=1000)

| SUT | token | gemma4:e4b (4B) | gemma3:12b (12B) | mixtral:8x7b (47B) | claude-haiku-4-5 |
|---|---|---|---|---|---|
| vanilla | 0.566 | 0.554 | 0.634 | 0.550 | **0.852** |
| naive-supersede | 0.827 | 0.819 | 0.813 | 0.754 | 0.833 |
| **JAMES** | **0.984** | **0.989** | **0.991** | **0.893** | **0.990** |
| V<N<J | ✓ | ✓ | ✓ | ✓ | **✗ (V > N by 0.019)** |
| J − N | +0.157 | +0.170 | +0.178 | +0.139 | +0.157 |
| J − V | +0.418 | +0.435 | +0.357 | +0.343 | +0.138 |

Fallbacks: 0 in all 12,000 LLM-grounded rows (9,000 local + 3,000 claude).

## 3. Pre-registered verdict (prereg §2)

| Leg | S3 pub R@1 V<N<J | J − N > +0.10 | Verdict |
|---|---|---|---|
| 1 gemma4:e4b | ✅ | ✅ +0.170 | leg-clear |
| 2 gemma3:12b | ✅ | ✅ +0.178 | leg-clear |
| 3 mixtral:8x7b | ✅ | ✅ +0.139 | leg-clear |
| 4 claude-haiku-4-5 | **✗** (0.852 / 0.833 / 0.990) | ✅ +0.157 | **not clear on the strict ordering** |

**Composite, applied as written: 3/4 legs clear → ⭐⭐ partial-tier
cross-model + 1 model attribution finding.** The 4/4 PUBLICATION-TIER row
is not claimed. The secondary condition (J − N > +0.10 on every leg) is
met 4/4.

What the failing half is, and is not:

- **It is the ordering of the two baselines**, V vs N, not the JAMES
  contribution. J > N and J > V hold on every leg with J − N between
  +0.139 and +0.178; the sign and size of the validity-window
  contribution are unchanged.
- **Attribution (fixture text × reader strength).** Every S3 superseding
  document states its supersession in its body — `Supersedes <old id>`
  (260 / 260 SUPERSEDE events; S2: **0 / 48**). A strong reader uses that
  sentence to rank the current version first among the stale versions
  Vanilla retains: Vanilla's current-state categories go to **1.00 /
  1.00 / 1.00** (contract / director / policy) under claude, against
  0.00–0.46 under the local rerankers. Naive cannot benefit — its R@1 is
  capped by its deleted history at exactly its R@10 (0.833). At S2, where
  the v2 bodies carry no such sentence, the claude leg keeps V < N
  (0.525 / 0.775 / 1.000).
- **Size.** V − N = 0.019 (19 queries of 1000), inside the ≈10 pp
  reranker band (PR #819): at this leg V and N are indistinguishable,
  not reversed with confidence.
- **Not taken here**: an S3.3 variant with the supersession sentence
  removed would separate reader strength from fixture wording; it is a
  benchmark-side change and is listed as future work (preprint §7), not
  executed.

## 4. Per-category R@1 (V / N / J), claude leg

| category | n | claude | (token, for reference) |
|---|---|---|---|
| current-contract | 125 | **1.00** / 1.00 / 1.00 | 0.00 / 1.00 / 1.00 |
| current-director | 125 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| current-policy | 125 | **1.00** / 1.00 / 1.00 | 0.00 / 0.98 / 0.98 |
| current-project-lead | 125 | 0.43 / 1.00 / 1.00 | 0.34 / 0.99 / 0.99 |
| historical-early-contract | 50 | 1.00 / 0.00 / 1.00 | 1.00 / 0.00 / 1.00 |
| historical-early-director | 50 | **1.00** / 0.50 / 1.00 | 0.50 / 0.50 / 1.00 |
| historical-mid-director | 66 | 0.74 / 0.76 / **1.00** | 0.76 / 0.76 / 1.00 |
| historical-mid-policy | 68 | 0.59 / 0.41 / **1.00** | 0.59 / 0.38 / 0.97 |
| historical-mid-project-lead | 66 | 0.52 / 0.45 / 0.85 | 0.52 / 0.45 / 0.85 |
| never-stale-budget | 200 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

`current-project-lead` V 0.43: a superseded project's v1 and v2 share the
title and both are retained, and the reader picks v1 about half the time —
the one current-state category where the supersession sentence does not
rescue Vanilla fully. JAMES 0.85 on `historical-mid-project-lead` is the
same 56 / 66 as token mode (v1 and v2 of a superseded project share a
title; both are in the top 10), recorded as a JAMES imperfection.

## 5. Cross-scale × cross-model summary (feeds preprint §4.7)

| scenario × mode | V R@1 | N R@1 | J R@1 | J − N | V<N<J |
|---|---|---|---|---|---|
| S2 token (repaired) | 0.2500 | 0.5875 | 0.7625 | +0.1750 | ✓ |
| S2 llm-gr gemma4 / gemma3:12b / mixtral / claude | 0.4750 / 0.4500 / 0.3625 / 0.5250 | 0.7375 / 0.7250 / 0.6875 / 0.7750 | 0.9000 / 0.9000 / 0.8625 / 1.0000 | +0.1625 / +0.1750 / +0.1750 / +0.2250 | ✓ ✓ ✓ ✓ |
| S3 pub token (S3.2) | 0.566 | 0.827 | 0.984 | +0.157 | ✓ |
| S3 pub llm-gr gemma4 / gemma3:12b / mixtral / claude | 0.554 / 0.634 / 0.550 / 0.852 | 0.819 / 0.813 / 0.754 / 0.833 | 0.989 / 0.991 / 0.893 / 0.990 | +0.170 / +0.178 / +0.139 / +0.157 | ✓ ✓ ✓ **✗** |

Ten LLM-grounded cells across two scenarios and four rerankers: J > N and
J > V on all ten; strict V < N < J on nine; J − N from +0.139 to +0.225.

## 6. Honest caveats

- ⭐⭐ partial at S3 publication by the pre-registered matrix; ⭐⭐⭐ at S2
  (5/5). Magnitudes stay scenario-sensitive (S2 hand-curated vs S3
  synthetic).
- The claude cells cost ≈ 3,000 CLI calls at ≈ 20 s each plus 1.8 h of
  usage-window waits; the leg shares the operator's Max-plan quota with
  the working session, which is why the first two attempts failed.
- One run of 1000 queries per cell; LLM reranking carries the ≈10 pp band.
- Per-cell `result.json` committed (`rerank_fallbacks`, `rerank_quota_wait_s`);
  `bench.jsonl` and the log gitignored.

## 7. One-line

The cloud leg lands clean (0 fallbacks, 1.8 h of quota waits) with JAMES at
0.990 and +0.157 over Naive; the strict V < N < J ordering breaks on this
one leg because the S3 documents announce their own supersession and a
strong reader uses it to rescue Vanilla — a baseline-ordering finding,
recorded as ⭐⭐ partial per the pre-registration, not a change to the
validity-window claim.
