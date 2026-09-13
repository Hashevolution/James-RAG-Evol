# LRB v0.2.3b — 3-model LLM-grounded S3 **publication** results (2026-09-10)

> **Update 2026-09-12**: the §4 ceiling was removed by the S3.2 generator fix (`docs/research/lrb-v023-s3-publication-scale-results-2026-09-12-s32.md`; token-mode publication now V/N/J 0.566 / 0.827 / 0.984). Every number in this report is on the **pre-S3.2** fixture (sha `662fc2b7…`); the LLM-grounded re-run on the S3.2 fixture is `lrb-v023b-3model-llm-grounded-publication-s32-20260913.md` (3 local legs: J 0.989 / 0.991 / 0.893, J−N +0.170 / +0.178 / +0.139, 0 fallbacks).

Runner: `scripts/research/lrb_run_v023b_s3_cross_model.py
--scale publication --modes llm-grounded --models gemma4:e4b,gemma3:12b,mixtral:8x7b`
(run id `20260910T064642Z`).
Prereg: `docs/research/lrb-v023b-s3-cross-model-preregistration-2026-06-12.md`
(config unchanged since; verdict matrix §2 applies as written).
Predecessor: `lrb-v023b-3model-llm-grounded-smoke-20260621.md` (same runner,
`--scale smoke`, N=100).
Roadmap: Phase 5 item 2 of `docs/handovers/v0.6.2-restart-roadmap-2026-09-03.md`
— the last of the three Phase 5 measurement items (#1118/#1119 Graph-RAG
Step 2 cross-model, #1120 D-alce cross-NLI).

| | |
|---|---|
| Fixture | `eval/external/_fixtures/lrb/scenario_S3_publication.json`, sha `662fc2b7…` — byte-identical to the fixture behind the published token-mode 0.502 / 0.721 / 0.845 (`README.md`, `SUMMARY.md`; reproduced from the committed generator on 2026-09-03, `lrb-s3-collision-check-20260903.md` §2) |
| Scale | S3 publication: 1000 initial docs / 5620 events / 1000 queries (100 departments) |
| Cells | 3 SUTs × 3 local rerankers × 1 mode = **9**, n=1000 each, errors 0 |
| Wall clock | 2026-09-10 15:46 → 2026-09-11 12:10 KST = **20 h 24 min** (gemma4 ≈ 50 min per cell, gemma3:12b 70–85 min, mixtral ≈ 4.7 h) |
| Run rules | `PYTHONPATH` set, no `nohup`, no `timeout`, no server — Ollama only (roadmap §Phase 5) |
| Log | `reports/research-runs/_v023b_publication_3model_20260910_1546.log` (gitignored; ends `EXIT=0`) |
| 4th leg | `claude-haiku-4-5` **not run** — needs `JAMES_ENABLE_CLAUDE_BACKEND` + the cloud CLI; same exclusion as the smoke run |

## 1. Gap table (R@1 = the fact that is correct *for the queried valid_time*, at rank 1)

| reranker | vanilla | naive-supersede | **james** | V<N<J | **J−N** | J−V |
|---|---|---|---|---|---|---|
| gemma4:e4b   | 0.502 | 0.714 | **0.848** | ✅ | **+0.134** | +0.346 |
| gemma3:12b   | 0.595 | 0.707 | **0.849** | ✅ | **+0.142** | +0.254 |
| mixtral:8x7b | 0.479 | 0.657 | **0.784** | ✅ | **+0.127** | +0.305 |
| *(ref) token-mode, same fixture (2026-06-12)* | *0.502* | *0.721* | *0.845* | *✅* | *+0.124* | *+0.343* |

Temporal accuracy (gold in the top-10 at the queried valid_time): james
**0.994–1.000**, naive-supersede **0.827–0.830**, vanilla 0.977–0.985.
Per time-travel window, V / N / J:

| window | n | gemma4:e4b | gemma3:12b | mixtral:8x7b |
|---|---|---|---|---|
| qt=52 / vt=0 (early)    | 100 | 1.000 / **0.250** / 1.000 | 0.940 / **0.210** / 0.970 | 0.970 / **0.230** / 0.950 |
| qt=52 / vt=17 (mid)     | 200 | 0.925 / **0.520** / 1.000 | 0.915 / **0.530** / 1.000 | 0.925 / **0.540** / 1.000 |
| qt=52 / vt=52 (current) | 700 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | 1.000 / 0.999 / 0.999 |

Cost axes: token_cost 308–335 chars/query and latency are the same across
the three SUTs *within* a reranker (gemma4 3.0 s, gemma3:12b 4.2–5.1 s,
mixtral 16.8–17.2 s). The SUT mechanism adds no cost; the reranker is the
cost.

## 2. Pre-registered verdict (prereg §2)

| Leg | S3 pub R@1 V<N<J | J−N > +0.10 | Verdict |
|---|---|---|---|
| 1 gemma4:e4b (4B)          | ✅ | ✅ +0.134 | leg-clear |
| 2 gemma3:12b (12B)         | ✅ | ✅ +0.142 | leg-clear |
| 3 mixtral:8x7b (47B)       | ✅ | ✅ +0.127 | leg-clear |
| 4 claude-haiku-4-5 (cloud) | not run | not run | **not attempted** |

Every leg that was run is clear: **3/3 local legs; the 4th leg was not
attempted.** The prereg composite row for "3/4" reads "⭐⭐ partial-tier +
1 model artifact finding", but that row describes a *failing* model — here
nothing failed, one leg was never measured, so there is no artifact to
attribute. The honest composite is therefore **⭐⭐⭐ pattern + gap,
cross-model (3 local rerankers) at publication scale, cloud leg open**.
The 4/4 "PUBLICATION-TIER" row is *not* claimed. The secondary condition
(J−N > +0.10 at every leg) is met 3/3.

## 3. Findings

1. **V<N<J holds 3/3 at N=1000 under LLM reranking; J−N = +0.127 …
   +0.142.** With the smoke run (3/3 at N=100) and the token-mode ladder
   (4/4 scale points), the ordering now reproduces across scale ×
   reranker × mode. (The S2 llm-grounded legs in prereg §4 were measured
   2026-06-11 on the pre-#1089 S2 fixture and have not been re-run; the
   S3 claim does not rest on them.)

2. **Backbone size still does not widen the gap.** mixtral 47B has the
   smallest gap (+0.127) and the lowest james R@1 (0.784); the two gemma
   cells are within 0.001 of each other on james. Same shape as the smoke
   finding — the lift is the validity-window mechanism, not the model.

3. **The two-axis story is exact at publication scale.** naive-supersede
   buys its current-fact R@1 by deleting history: temporal accuracy
   0.21–0.25 at vt=0 and 0.52–0.54 at vt=17. james keeps both axes (highest
   R@1 *and* temporal accuracy 0.994–1.000). vanilla keeps history but
   lets stale facts win rank 1 (V R@1 0.48–0.60).

4. **The gap narrowed vs the smoke run (+0.21 / +0.22 / +0.14 → +0.134 /
   +0.142 / +0.127) and james R@1 fell (0.95 / 0.98 / 0.85 → 0.848 / 0.849
   / 0.784).** Both movements have a single cause — a fixture property,
   §4 — not the reranker and not the SUT.

## 4. Self-catch: the S3 publication fixture caps project-lead R@1 at 0.288 for *every* SUT

Per-category R@1 (V / N / J). The smoke report did not tabulate this; the
rule since S3.1 (`feedback_s31_self_correction_artifact_pattern`) is that
no magnitude statement is made before it is.

| category | n | gemma4:e4b | gemma3:12b | mixtral:8x7b | token-mode |
|---|---|---|---|---|---|
| current-contract            | 125 | 0.07 / 1.00 / 1.00 | 0.06 / 1.00 / 1.00 | 0.14 / 1.00 / 1.00 | 0.00 / 1.00 / 1.00 |
| current-director            | 125 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.97 / 0.91 / 0.91 | 1.00 / 1.00 / 1.00 |
| current-policy              | 125 | 0.00 / 0.98 / 0.98 | 0.46 / 1.00 / 1.00 | 0.00 / 1.00 / 1.00 | 0.00 / 0.98 / 0.98 |
| **current-project-lead**    | 125 | 0.08 / **0.256** / **0.256** | 0.26 / **0.256** / **0.256** | 0.06 / **0.256** / **0.256** | 0.06 / **0.256** / **0.256** |
| historical-early-contract   |  50 | 0.94 / 0.00 / 1.00 | 1.00 / 0.00 / 1.00 | 0.94 / 0.00 / 1.00 | 1.00 / 0.00 / 1.00 |
| historical-early-director   |  50 | 0.52 / 0.50 / 1.00 | 0.42 / 0.40 / 0.92 | 0.28 / 0.04 / 0.38 | 0.50 / 0.50 / 1.00 |
| historical-mid-director     |  66 | 0.58 / 0.68 / 0.91 | 0.70 / 0.53 / 0.95 | 0.35 / 0.29 / 0.65 | 0.76 / 0.76 / 1.00 |
| historical-mid-policy       |  68 | 0.46 / 0.35 / 0.97 | 0.59 / 0.41 / 1.00 | 0.56 / 0.41 / 0.97 | 0.59 / 0.38 / 0.97 |
| **historical-mid-project-lead** | 66 | 0.24 / 0.24 / **0.27** | 0.26 / 0.26 / **0.23** | 0.17 / 0.18 / **0.15** | 0.06 / 0.24 / **0.14** |
| never-stale-budget          | 200 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

Two categories — 191 of 1000 queries, 19.1 % — sit at ≈0.26 for **every**
SUT, every reranker and the token scorer, with an *identical* 0.256
(32/125) for N and J in all four current-project-lead columns. Identical
numbers across four unrelated scorers are the signature of an oracle
ceiling, not of retrieval behaviour, and the fixture confirms it:

- `make_project` (`scripts/research/build_lrb_scenario_s3.py:237`) builds
  the title from `PROJECT_VERBS[(dept_idx + prj_idx) % 20]` and
  `PROJECT_NOUNS[(dept_idx*7 + prj_idx*3) % 20]`. Both indices are
  periodic in `dept_idx` with period 20, so at 100 departments every
  `(prj_idx, dept_idx mod 20)` title recurs **five times**. (The comment
  above the function promises "400 unique project titles per dept"; the
  arithmetic delivers 60 per corpus.) Measured on the fixture: 330
  project docs, **70 unique titles** — 50 titles shared by 5 base
  projects, 10 by 6–7 (the 30 new-project ingests reuse the vocabulary).
- The project-lead query is `Who leads {ptitle}?` / `Who led {ptitle} 35
  weeks ago?` — no department. So the 125 current-project-lead queries
  have **18 distinct texts**, each carrying **5 distinct golds** (7 queries
  per text). Identical input cannot produce gold-specific output, so **no
  system — deterministic or stochastic — can exceed 0.288** (36/125: per
  text, the most frequent gold) on that category, or **0.273** (18/66) on
  historical-mid-project-lead. Every other category has a ceiling of
  1.000 (all queries that share a text share one gold).
- The ceiling is a function of department count. Smoke (10 depts): every
  title unique, james 0.83–1.00 on these categories. Dev (30 depts): 10
  titles collide 2×. Publication (100 depts): 50 collide 5×. This is why
  the token-mode ladder's magnitude falls 0.930 → 0.913 → 0.845 while
  R@10 stays 1.0 — the 2026-06-12 results doc §3 tabulated R@10, which
  cannot see it — and why its follow-up "S3.2 vocabulary diversification
  (… project-lead …)" was filed low-priority: the R@10 ceiling was
  checked, the R@1 ceiling was not.

**What this does and does not change.**

- The pre-registered verdict is unchanged and, if anything, conservative:
  the ceiling holds N and J to the same value, so it *compresses* J−N
  (19.1 % of queries on which the james mechanism cannot show) rather
  than inflating it.
- The published token-mode figure 0.845 (README / SUMMARY / preprint §4.6)
  carries the same ceiling — byte-identical fixture. **No published number
  is edited here.**
- The correct fix is generator-side (S3.2: make each project title unique
  per department, or put the department in the query) — not a metric
  reinterpretation, the same rule as S3.1 (#825) and the S2 repair
  (#1089). Unlike S3.1, the affected figure is already published and
  cited, so the fix changes a published number and is an **operator
  decision** (close handover §6 #7). A guard `len(unique project titles)
  == n_projects` in `tests/test_lrb_s3_generator.py` would make the next
  density change fail loudly; it is benchmark-side too and is listed with
  the decision rather than taken.

Post-hoc and exploratory — **not a verdict input** — overall R@1
recomputed on the 809 unambiguous queries:

| reranker | V | N | J | J−N |
|---|---|---|---|---|
| gemma4:e4b   | 0.588 | 0.823 | 0.986 | +0.163 |
| gemma3:12b   | 0.675 | 0.813 | 0.991 | +0.178 |
| mixtral:8x7b | 0.569 | 0.758 | 0.917 | +0.159 |
| token-mode   | 0.606 | 0.832 | 0.994 | +0.162 |

The two project-lead categories account for 93 % / 95 % / 69 % of the
james rank-1 misses (gemma4 / gemma3:12b / mixtral). The remaining mixtral
misses are genuine reranker misses on the historical director windows
(0.38 / 0.65) — the backbone finding of §3-2.

## 5. Cross-scale × cross-model table (prereg §4 rows, filled)

| Scenario × Mode × Model | V R@1 | N R@1 | J R@1 | V<N<J | Honest tier |
|---|---|---|---|---|---|
| S2 token (v0.2.1, repaired #1089) | 0.250 | 0.588 | 0.763 | yes | ⭐⭐⭐; decision #2 on the published 0.713 still open |
| S3 pub token (v0.2.3) | 0.502 | 0.721 | 0.845 | yes | ⭐⭐⭐ pattern / ⭐⭐ magnitude (§4 ceiling) |
| S2 llm-gr gemma4 (v0.2.1) | 0.488 | 0.563 | 0.725 | yes | ⭐⭐⭐ as measured 2026-06-11; pre-repair S2 fixture, not re-run |
| S2 llm-gr gemma3:12b | 0.400 | 0.613 | 0.775 | yes | same |
| S2 llm-gr mxtral | 0.375 | 0.625 | 0.838 | yes | same |
| S2 llm-gr claude | 0.613 | 0.775 | 0.975 | yes | same |
| **S3 pub llm-gr gemma4** | **0.502** | **0.714** | **0.848** | **yes** | ⭐⭐⭐ pattern + gap / ⭐⭐ magnitude (§4 ceiling) |
| **S3 pub llm-gr gemma3:12b** | **0.595** | **0.707** | **0.849** | **yes** | same |
| **S3 pub llm-gr mxtral** | **0.479** | **0.657** | **0.784** | **yes** | same |
| S3 pub llm-gr claude | — | — | — | — | not run (cloud backend) |

## 6. Honest caveats

- Three local rerankers only; the cloud leg is open. The 4/4 row of the
  prereg matrix is not claimed.
- Absolute magnitudes are held down by the §4 ceiling on 19.1 % of
  queries. Compare cells *within* this fixture; do not read 0.848 against
  the smoke 0.95 or the S2 0.76 as a JAMES change.
- LLM reranking is stochastic (~10 pp band, PR #819); each cell is one run
  of 1000 queries. The gaps (+0.127 … +0.142) clear the band on the
  primary axis; nothing finer is claimed.
- Per-cell `result.json` committed; per-row `bench.jsonl` and the run log
  are gitignored, as for every earlier LRB run.

## 7. One-line

At publication scale (N=1000) and under three distinct LLM rerankers, the
JAMES validity-window mechanism keeps the R@1 ordering V<N<J (3/3) with
J−N +0.13 … +0.14 and temporal accuracy ≥ 0.994 — and the absolute
magnitudes are held down not by JAMES but by a fixture ceiling on
project-lead queries that the published token-mode figure shares
(generator fix = operator decision).
