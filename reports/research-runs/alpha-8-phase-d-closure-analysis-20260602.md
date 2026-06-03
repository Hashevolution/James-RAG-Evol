# α-8 Phase D Closure Analysis — Ontology Typed-Filter

> **REVISED 2026-06-03 04:00** — Phase C n=3 paired confirm complete
> (`bzah80yd7`, 4.7h). n=1 verdict (⭐⭐ adopt) was noise-inflated; n=3
> medians collapse to noise band. **Revised verdict: ⭐ operational only**
> per §4.1 tree. Code retained (no regression, real latency improvement,
> direction-correct aggregate). ARCHITECTURE.md §5.7.12 entry deferred.
> n=1 over-claim → n=3 catch = process-correctness lesson in
> [[feedback_n1_verdict_inflation_n3_caught]]. Honest framing per
> `memory/feedback_finding_size_honest_framing`.

---

## 0. Run metadata

| Field | Value |
|---|---|
| Cycle | α-8 (ontology +5 horizontal types + typed filter R1-R5) |
| Branches | `feat/v0.4-alpha8-phase-a-ontology-horizontal-types` (#688) + `feat/v0.4-alpha8-phase-b-typed-filter-overlay` (#689) |
| PRs landed | #688 (`fcf343d`) + #689 (`6d6698e`) |
| Phase C measurement commit | `c2b0dc2` |
| Date | 2026-06-02 (Phase A+B+C all single day) |
| Production tier | M_M (`gemma4:e4b`, think=OFF) |
| Code changes | `core/ontology.py` (+5 types, +6 relations) + `core/graph_typed_filter.py` (new module 10.7 KB) + `core/pipeline_context.py` (typed-prefix overlay) + `scripts/qvt_ablation_matrix.py` (C_rag-ontology cell) + 137 tests pass |
| Default behaviour | `JAMES_DISABLE_TYPED_FILTER` unset → filter ACTIVE in `/query/` |

---

## 1. Phase C step7 measurement (sanity, regression-free check)

**Captured 2026-06-02 19:15-20:11**, M_M, n_runs=3 paired. Sector cells:
- `C_rag-graph` = α-7 baseline reproduction (`JAMES_DISABLE_TYPED_FILTER=1` forced)
- `C_rag-ontology` = α-8 default (typed filter ON)

| Axis | C_rag-graph | C_rag-ontology | **Δ** | Noise band | Within noise? |
|---|---:|---:|---:|---:|---|
| path_coverage | 0.000 | 0.000 | 0.000 | — | ⚠️ measurement bug — see §3 |
| graded_answer | 0.650 | 0.633 | **−0.017** | 0.083–0.117 | ✓ inside |
| abstention_f1 | 0.500 | 0.500 | **0.000** | 0.00–0.07 | ✓ flat |
| token_cost (chars) | 1383.85 | 1372.9 | −11.0 | 17 / 237 | ✓ flat |
| latency (s) | 27.78 | 27.40 | **−0.38** | 0.57 / 0.09 | ✗ real micro-improvement |

**Step7 verdict per design memo §4 tree**: `graded Δ ≤ +0.010 AND abst_f1
unchanged` → **⭐ operational only on step7**. But step7 ≠ α-8 acceptance
test (next section).

### 1.1 What step7 null does NOT mean

step7-v7 fixture has 20 queries; only ~3 have `abstention_truth = absent`
(true null queries where the right answer is refusal). The α-8 mechanism
— typed filter prepending `[Date]: (none found in graph)` rows when a
date-asking query has no date entities — operates ONLY on null queries
with a query-relevant type slot. Step7 doesn't have enough null queries
of the right shape to surface this signal.

**This is exactly the lesson from α-5 v7 fixture construct validity
(사용자 catch, memory `alpha_5_multihop_rag_reset`): a null effect on the
wrong fixture ≠ rejection.**

### 1.2 What step7 null DOES confirm

- **No regression**: graded Δ within noise, abst flat. Typed filter is
  safe to leave ON as default in production.
- **No latency tax**: −0.38s is a real micro-improvement (own noise 0.09),
  proving the intent-classifier + grouping overhead is negligible.
- **No token bloat**: −11 chars flat. Typed filter is a *re-format* of
  the same entity set, not an additive context expansion (per design
  memo §1.4 expectation).

---

## 2. Phase C multihop_rag measurement (α-8 acceptance test)

**TBD** — n=1 launch 2026-06-02 21:04, ETA ~00:35 same night.

Workspace: `JAMES_WORKSPACE=workspaces/hotpot_eval` (cell JSONs separated
from step7 to avoid path collision). Cells: same `C_rag-graph` vs
`C_rag-ontology` overlay, fixture = `multihop_rag_queries.json` (100
queries, balanced 25 per question_type per α-5 fixture).

### 2.1 Acceptance metrics (R1-R5)

Per design memo §2.4:

| Test | Measure | Pass condition |
|---|---|---|
| **R1** null query refusal | `scripts/research/audit_12b_null_query_refusal_shape.py` on post-α-8 baseline | null_query abst_f1 ≥ α-6 baseline level (0.609) |
| **R2** empty-type signal in context | grep `(none found in graph for this query)` in served answers | ≥ 50% of null queries see the marker |
| **R3** non-relevant types omitted | type-classifier output vs final type slots | classifier ranking ↑ → slot inclusion ↑ |
| **R4** intent rank order preserved | per-question-type cross-tab | temporal queries see [Date] first, spatial see [Location] first |
| **R5** cap ≤ 10 slots | manual cell inspection (10 samples) | no answer has > 10 type rows |

### 2.2 Δ table — n=1 (provisional) vs n=3 paired (actual verdict)

**n=1 single-shot (2026-06-02, DIRECTIONAL ONLY — superseded by n=3)**:

| Axis | graph | ontology | Δ (n=1) | What it looked like |
|---|---:|---:|---:|---|
| graded_answer | 0.290 | 0.327 | +0.037 | ⭐⭐ adopt threshold (= mirage) |
| abstention_f1 | 0.487 | 0.622 | +0.137 | strong R1 evidence (= mirage) |

**n=3 paired (2026-06-03 04:00, THE VERDICT)**:

| Axis | graph median | ontology median | **Δ** | noise band | Inside/Outside |
|---|---:|---:|---:|---:|---|
| path_coverage | 0.408 | 0.408 | **0.000** | ±0.005 | flat |
| **graded_answer** | 0.300 | 0.307 | **+0.007** | ±0.060 | **inside (< +0.010 ⭐⭐ threshold)** |
| **abstention_f1** | 0.455 | 0.513 | **+0.058** | **±0.418** | **inside (1/7 of noise)** |
| token_cost (chars) | 1600 | 1592 | −8.6 | ±75.6 | flat |
| **latency (s)** | 28.44 | 28.06 | **−0.38** | ±0.32 | **OUTSIDE −** (real) |

**Confusion matrix aggregate** (300 queries × 3 runs each):
```
graph    (filter OFF):  TP=27  FP=20  FN=48  TN=205
ontology (filter ON):   TP=33  FP=11  FN=42  TN=214
                       ΔTP=+6 ΔFP=-9 ΔFN=-6 ΔTN=+9
```

- **12.5% FN reduction** (48→42), NOT the 31% claimed at n=1
- 9 fewer over-refusals (FP: 20→11) — n=1 reported +3 over-refusal,
  n=3 reverses to −9
- 4 direction-correct (TP↑ FP↓ FN↓ TN↑)
- **per-run variance reduction sub-finding**: graph abst_f1 spans
  0.216–0.634 (range 0.418); ontology spans 0.500–0.636 (range 0.136).
  Typed filter ALSO reduces run-to-run noise. Genuine secondary effect
  not captured by median Δ.

R1 audit (`scripts/research/audit_12b_null_query_refusal_shape.py`)
on n=1 data found 5 ontology refusal answers with absence-language
tied to typed filter output. Example:

> "We cannot determine the first letter of the city **because the
> provided context does not contain any details regarding Ryan
> McInerney**..."

**For n=3 these answers remain descriptive evidence of mechanism but
NOT statistical proof.** Per-run hallucination counts (15 / 12 / 21 in
graph; 16 / 11 / 15 in ontology) show the same query can produce
opposite verdicts across runs. Aggregate direction (FN 48→42) supports
"typed filter does what design says" — magnitude statement requires
larger N.

### 2.3 Per-question-type cross-tab (mandatory per design memo §4)

Typed filter effects should vary by question type:
- **temporal questions** ("when did X happen?") → date+event filter should help
- **spatial questions** ("where is Y?") → location filter should help
- **identity questions** ("who founded Z?") → person+org filter should help
- **comparison questions** → less filter benefit expected

| question_type | C_rag-graph graded | C_rag-ontology graded | Δgraded | C_rag-graph abst_f1 | C_rag-ontology abst_f1 | Δabst |
|---|---:|---:|---:|---:|---:|---:|
| inference | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| comparison | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| temporal | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| null_query | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |

---

## 3. Measurement-side findings (separate from α-8 verdict)

Phase C step7 measurement surfaced **two distinct path_coverage measurement
bugs** in the QVT framework. Neither blocks α-8 closure (graded/abst_f1
parsers normal), but both affect path_recall Δ trust going forward.

### Bug 1 (oracle.py, step7) — fixed in this cycle

`eval/qvt/oracle.py:score_path_coverage` L313 fallback condition was
`if not graph_slugs and not source_slugs` — meant to catch legacy bench
JSONs that emit only `path_metrics`. Bench schema drift (raw `graph_paths`
list dropped, only `graph_paths_count` emitted post-α-7) made
`graph_slugs` always empty; `source_slugs` populated with PDF filenames
that don't slug-match entity-name expected_path → fallback never triggered.

**Fix**: PR `fix/v0.4-path-coverage-oracle-fallback` (commit `b3c4562`).
Replaced "BOTH empty" condition with "trust bench's `path_metrics.hits`
as graph-side floor when it exceeds oracle's re-derived `via_graph`."
50 tests pass (47 existing + 3 new). Re-scoring the Phase C step7 cell
recovers `mean_recall = 0.8182` from 0.000 (matches bench self-report 0.833).

### Bug 2 (bench.py, multihop) — deferred follow-up

Last 35 multihop_rag runs all report `path_recall_aggregate.mean = 0.0`.
Bench's own slug normalizer fails to match news article titles ("The FTX
trial is bigger than Sam Bankman-Fried") against graph node slugs. This
is bench-side, not oracle — fix requires bench.py path matcher widening
(fuzzy / token overlap / substring fallback) OR fixture expected_path
normalization. Not in α-8 scope; tracked as task #4 follow-up.

### Implication for §1 (step7) and §2 (multihop)

- §1 step7 path_coverage Δ row now reads as 0/0 only because the cells
  were scored before the oracle fix landed. Re-rendering with
  `--render-report` against the fixed oracle would recover non-zero
  numbers. (Not in this analysis — defer to post-multihop.)
- §2 multihop path_coverage Δ will likely also read 0/0 due to bug 2;
  graded_answer and abstention_f1 remain the load-bearing α-8 verdict
  signals.

---

## 4. Verdict: ⭐ operational only (n=3 paired confirmed; n=1 verdict was noise-inflated)

Per design memo §4.1 verdict tree (acceptance baseline = α-7 → α-6 since
α-7 was REJECT):

| Multihop graded Δ (n=3 median) | Verdict | Outcome |
|---|---|---|
| ≥ +0.030 | ⭐⭐ adopt | (not reached at n=3) |
| +0.010 to +0.030 | tier-gated adopt | (not reached at n=3) |
| **< +0.010** | **⭐ operational only** ← **HIT (+0.007)** | Code retained, default ON, ARCHITECTURE.md entry deferred |

**Verdict landed: ⭐ operational only.** Reasoning:

1. **n=3 paired graded Δ = +0.007** — below +0.010 threshold per §4.1
   tree. n=1's +0.037 was single-run noise lining up favorably.
2. **abst_f1 Δ +0.058 inside 0.418 noise band** — statistically
   indistinguishable from zero at this fixture/model/N. Per-run
   abst_f1 spread 0.216–0.634 on baseline shows the metric is
   too noisy to support magnitude claims at n=3.
3. **R1 mechanism remains descriptive evidence only** — the 5 specific
   ontology refusal answers WITH absence-language tied to typed filter
   output DID exist. They are real. But per-run hallucination counts
   reverse direction (15/12/21 vs 16/11/15) — the SAME query produces
   opposite verdicts across runs. n=3 cannot promote mechanism
   evidence to "consistent statistical claim."
4. **Aggregate direction is correct** (4/4 axes design-intent-aligned)
   + **variance reduction sub-finding** is genuine — these justify
   keeping the code ON, NOT a publishable claim.

**ARCHITECTURE.md §5.7.12 entry deferred** until stronger evidence:
- Possible paths: 5-tier remeasurement (does effect scale with model
  size?), R1-targeted null-only fixture (where mechanism should
  saturate), or larger N (n=5+) at M_M.
- Until then: typed filter is operational, not publishable.

**Joint piece spine framing (Robin 2026-06-02 DM)** — α-8 is NOT
added to the spine. D3 cross-family + S4 scale remain Robin's central
claim; α-8 doesn't contribute statistically robust evidence at this
verdict tier. See [[feedback_dm_collab_response_eagerness_trap]].

### 4.1 Honest framing reminders

- **Ceiling = ⭐⭐ partial regardless of magnitude** (per design memo §1.3) —
  typed filter is a decades-old technique. JAMES contribution = numbers +
  routing rule + empirical position. Headline framing "ontology fixes RAG"
  is forbidden.
- **Self-broadcast forbidden** — closure tone "validated 1 architectural
  fix" not "discovered new mechanism."
- **Mother platform horizontal-only** — 5 new types all pass §2.3
  boundary test. No vertical drift; v0.5 domain pack mechanism still
  blocked per rule #1.

---

## 5. Closure actions (post-multihop)

When multihop cells land:

1. Fill §2 Δ table from `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/qvt-ablation-cell-C_rag-{graph,ontology}-M_M.json`.
2. Run `scripts/research/audit_12b_null_query_refusal_shape.py` against
   each cell's bench JSON → fill §2.1 R1 row.
3. Manual sample 10 served answers for R2/R5 grep + R4 ordering check.
4. Update `memory/project_alpha_8_phase_c_step7_null.md` → rename to
   `project_alpha_8_closure_state.md` with full Δ table.
5. Write `docs/ARCHITECTURE.md §5.7.N` typed filter section IF verdict
   is ⭐⭐ or higher (skip for ⭐).
6. Open closure PR with:
   - This analysis (filled)
   - ARCHITECTURE.md update (if applicable)
   - PR description includes Quality Delta Card (5-axis) + per-question-type
     cross-tab + R1-R5 acceptance result + verdict tier
   - Quality delta: exempt label = NONE (this is the load-bearing α-8 PR
     that establishes the Δ, not a circular fix-side PR)

---

## 6. Cycle ledger

- α-5 wrong-fix-averted: 7
- α-6 wrong-fix-averted: 2
- α-7 wrong-fix-averted: 1 (top-K rejected at 5-tier)
- α-8 wrong-fix-averted: 0 so far (architectural fix landed successfully)
- α-8 separate measurement bugs surfaced: 2 (bug 1 fixed, bug 2 deferred)
- **Cumulative wrong-fix-averted**: 10

**α-8 cycle = no regression + 11th wrong-fix-averted catch.** Code
lands clean (no measurement regression, real latency improvement,
aggregate direction-correct). But n=1 verdict claim was wrong-overclaim
caught by n=3 paired confirm — exactly the process the n=3 rule exists
to enforce. See [[feedback_n1_verdict_inflation_n3_caught]] for the
process-correctness lesson. α-8 is the first α-cycle since α-4 where
**code lands without regression**; the verdict itself is ⭐, not the
⭐⭐ claimed at n=1.

---

## 7. Next-cycle handoff (if α-8 ⭐ or ⭐⭐)

- Phase 3b proper cross-family measurement (5 families × n=3 ≈ 45h) runs
  on α-8 baseline per 2026-06-02 Option C decision.
- v0.5 first domain pack candidate = enterprise internal knowledge
  ontology (horizontal moat). α-8's `since:` extension hook in `ENTITY_TYPES`
  is the integration point.
- Bug 2 (bench.py multihop slug matcher) follow-up cycle.

---

## Korean handover snippet

이번 cycle (α-8) Phase A+B+C+D 단일 day. step7 = null effect (regression
0, latency 미세 개선 −0.38s, fixture-design-bound). **Multihop n=1 보였던
⭐⭐ adopt (graded Δ +0.037, abst_f1 Δ +0.137, "31% hallucination 방지")**
이 **n=3 paired confirm 에서 noise band 안으로 collapse**:
- graded Δ +0.007 (noise ±0.060, ⭐⭐ 임계 +0.010 미달)
- abst_f1 Δ +0.058 (noise ±0.418, 1/7 수준)
- aggregate confusion matrix: FN 48→42 (12.5% reduction, 31% 아님), TP
  27→33, FP 20→11, TN 205→214 — 4축 direction 일치하나 per-run variance
  거대 (graph abst_f1 0.216–0.634 spread)

**Revised verdict: ⭐ operational only**. typed filter 코드 유지 (regression
없음 + latency 진짜 개선 + ontology variance reduction sub-finding) but
ARCHITECTURE.md §5.7.12 등재 deferred. Robin spine framing 에 α-8 추가 안
함 (보류 결정 retrospectively 옳음).

별도 발견: path_coverage 측정 bug 2개 (oracle.py L313 fallback 조건 = fix
commit `b3c4562` 준비됨; bench.py multihop slug matcher = 별도 follow-up).

**Process lesson**: n=1 single-shot 이 ⭐⭐ 임계 통과한 듯 보였으나 n=3
paired 가 catch — honest framing rule 의 실증 1차. 11번째 wrong-fix-averted
(over-claim 잡음 카테고리). 다음 세션 가능 작업: Bug 2 fix + Track 2c
poison_01 retest (운영 verification only, NOT spine 3rd axis) + 5-tier
remeasurement (선택 — α-8 effect scale-dependent 인지) 또는 R1-targeted
null-only fixture (선택 — mechanism saturate signal 측정).
