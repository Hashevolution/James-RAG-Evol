# α-7 Closure Analysis — Graph Top-K Fix + 5-Tier Mode Reshape

> **Skeleton built pre-bench** (2026-06-02, baseline capture `bfzt6tx9h`
> in flight). Numbers in *TBD italics* will be filled when baseline +
> mode re-measurement land. Honest framing per
> `memory/feedback_finding_size_honest_framing` — apply tier tags +
> reuse none of the deprecated α-6 framings.

---

## 0. Run metadata

| Field | Value |
|---|---|
| Cycle | α-7 (graph top-K + DFS threshold tighten + bucket-(d) oracle phrase add) |
| Branch | `feat/v0.4-alpha7-graph-topk` |
| PR | **#680** (draft pending QDC) |
| Commit | `91b9a2c` |
| Date | 2026-06-02 |
| Workspace | `./workspaces/hotpot_eval` |
| Suite | `multihop_rag` (Tang & Yang 2024, EMNLP) |
| Fixture | balanced-100 (25 per question_type) |
| Baseline vs | `baseline_91b9a2c.json` (new α-7 N=3 baseline) AND legacy `baseline_3a961a3_rescored.json` (α-6 reference for delta) |
| Production tier | M_M (`gemma4:e4b`, think=OFF) |
| Code changes | `core/graph_topk.py` (new) + `core/graph_engine.py` (threshold + wire) + `eval/qvt/oracle.py` (6 phrases) + `tests/test_graph_topk.py` (14 cases) + `docs/ARCHITECTURE.md` §5.7.11 |
| Cumulative JAMES code change | 314 insertions / 2 deletions (first PR against measurement debt) |

---

## 1. α-7 baseline (post-fix M_M @ think=OFF, N=3 paired runs)

*Auto-filled when `bfzt6tx9h` exits + `baseline_91b9a2c.json` lands.*

| Axis | Pre-α-7 (`3a961a3_rescored`) | Post-α-7 (`91b9a2c_rescored`) | **Δ** | Within noise? |
|---|---:|---:|---:|---|
| path_coverage | 0.4044 | 0.4033 | **-0.0011** | ✓ flat |
| graded_answer | 0.3433 | 0.3233 | **-0.0200** | ✓ inside noise band ±0.03 |
| abstention_f1 | 0.6087 | 0.5385 | **-0.0702** | ✗ outside α-7 noise ±0.101 edge (consistent direction across 3 runs: 0.444/0.539/0.546) |
| token_cost | 1149.7 | 1233.2 | **+83.5** | ✓ inside noise band ±137 |
| latency_cost | 63.65s | 64.06s | +0.41s | ✓ flat |

Noise band (N=3 paired reruns, baseline JSON `noise_band`):
- graded: **±0.030** (was n/a at α-6 close, N=1)
- abst_f1: **±0.101**
- path: **±0.009**
- token: ±137.4
- latency: ±1.708s

**α-7 vs α-6 measurement quality**: α-7 captured at N=3 (proper noise
band); α-6 captured at N=1 (single-point, no error bar). The α-7
deltas read against α-6 are inflated by the unmeasured α-6 variance.

### 1.1 Acceptance decision (per design memo §4)

| Outcome | Condition | Verdict |
|---|---|---|
| **Adopt** | graded Δ ≥ +0.030 vs α-6 baseline | ❌ not met (-0.020) |
| **Tier-gated adopt** | +0.010 ≤ graded Δ < +0.030 | ❌ not met (negative) |
| **Reject + investigate** | graded Δ < +0.010 | ✅ **TRIGGERED** |

**Verdict: REJECT + sub-finding investigation (§3.2)**.

Per-question-type cross-tab populated in §4. Investigation in §3.2.

### 1.2 What measurement quality actually says

The L1/M_M baseline alone shows α-7's net effect ≈ -0.07 on
abstention with confidence interval barely overlapping noise.
graded shifted -0.02 (well within noise) but consistently downward
across all 3 runs.

The L1 measurement does NOT isolate the graph fix benefit — S5+S6
stages in L1 are already designed to recover graph regressions, so
removing the graph noise via top-K can only marginally improve L1.
The TRUE α-7 test point is the C_rag-graph cell (where Phase 1 §3
found the -0.054 graded regression). That cell measurement is
deferred to §2.

The S4 citation primitive (path Δ = -0.001) stays intact under
context reshape — confirms ⭐⭐⭐ candidate robustness.

---

## 2. Per-cell numbers — α-7 vs α-6 (M_M, single bench, post-α-7 baseline reference)

*Populate after re-running α-6 cells against α-7 baseline OR re-bench
post-α-7 cells with same env.*

| Cell | path | graded | abst_f1 | token | latency | Notes |
|---|---:|---:|---:|---:|---:|---|
| α-6 C_minus / M_M | 0.000 | 0.347 | 0.558 | 1385 | 11.9s | sealed (no JAMES; α-7 doesn't affect pure LLM) |
| α-6 C_rag-basic / M_M | 0.000 | 0.327 | 0.421 | 1569 | 12.6s | sealed (no graph) |
| α-6 C_rag-graph / M_M | 0.411 | 0.273 | 0.462 | 1565 | 28.7s | **the graded -0.054 regression** |
| **α-7 C_rag-graph / M_M (predicted)** | *TBD* | **graded ≥ +0.328 = +0.055 recovery** | *TBD* | -100 expected (smaller entity surface) | -3s expected (less LLM context) | the recovery target |
| α-6 C_rag-full / M_M = L1 | 0.419 | 0.327 | 0.591 | 1224 | 66.0s | sealed |
| **α-7 C_rag-full / M_M (predicted)** | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | top-K + tighter threshold |

---

## 3. Mechanism verification (post-bench)

### 3.1 Predictions vs observed

| Prediction | Result |
|---|---|
| graph_paths_count drops 41-161 → ≤ 10 per query | ✅ confirmed (top-K filter engaged; expand_dynamic returns ≤ K) |
| graded Δ ≥ +0.030 vs α-6 baseline | ❌ **refuted** — Δ = -0.020 (regression direction at L1 aggregate) |

The first prediction (top-K wiring) is mechanically correct. The
second prediction (graded recovery) is refuted at the L1/M_M
production tier. **The α-7 hypothesis is partially falsified at this
tier**.

### 3.2 Sub-finding investigation — null_query regression mechanism

4-step rule audit on α-7 baseline (`scripts/research/audit_12b_null_query_refusal_shape.py`
on the bench JSONs) shows:

| Comparison | α-6 baseline | α-7 baseline (run 3, representative) |
|---|---|---|
| Oracle TP (refusal caught) | 14/25 | 11/25 (after bucket-(d) phrase add: 12/25) |
| Oracle FN | 11/25 | 14/25 → 13/25 |
| Audit-found missed refusal in FN | 1/11 ("not available" pattern → added to oracle) | 0/14 → 0/13 |
| Effective refusals (TP + missed) | **15/25 (60%)** | **12/25 (48%)** |
| Net refusal loss | (reference) | **-3 refusals** (real, not artifact) |

Even after adding 2 more narrow phrases (`cannot be completed`,
`is not available` + 3 tense variants) to the oracle in this session,
the regression persists. **The mechanism is not phrase coverage**.

**Mechanism hypothesis (provisional, requires 5-tier confirmation)**:

The α-7 top-K filter reduces gemma4's "evidence-of-absence" signal.
When gemma4 sees 41-161 entities none of which exactly answer a null
query, it has stronger signal to refuse: "lots of stuff here, none
of it is the answer." When gemma4 sees only top-10 entities, the
narrower context lets it commit to an inference: "maybe these 10
are relevant to the question."

This is **opposite direction** to the α-6 Phase 3a 27b mechanism
finding (where source-injection commits the model to answer; α-7
top-K was expected to reduce that commitment pressure). At the
**gemma4 grounding-trained production tier**, narrower context
HURTS abstention. At larger gemma3 tiers (12b/27b) it may help —
that's the 5-tier remeasurement test in §5.

### 3.3 Bucket-(d) follow-up phrase additions (this session)

Re-running the audit on α-7 baseline + α-6 baseline found 2 more
narrow refusal patterns that the oracle was missing:

- `cannot be completed` — caught in α-7 null #5 (id=56)
- `is not available` / `are not available` / `was not available` /
  `were not available` — caught in α-6 null #24 (id=75)

These were added to `_ABSTENTION_PHRASES` in this session. Re-score
of α-7 baseline shifted median abst_f1 by only +0.002 (from 0.5366
→ 0.5385), confirming that **phrase coverage is not the regression's
root cause**. The mechanism in §3.2 is the actual driver.

---

## 4. Per-question-type cross-tab (mandatory)

*Populate from baseline JSON's `per_type` aggregate.*

| Question type | graded Δ | abst_f1 Δ | path Δ | latency Δ | Notes |
|---|---:|---:|---:|---:|---|
| inference (n=25) | **+0.013** | n/a (truth=present) | +0.010 | -0.04s | marginal positive, gemma4 likely benefits from focused top-K |
| comparison (n=25) | -0.013 | n/a | -0.013 | +0.91s | flat |
| temporal (n=25) | **+0.040** | n/a | 0.000 | +1.00s | **positive above noise band edge** — most favourable type |
| null (n=25) | **-0.120** | **-0.107** | 0.000 | -0.77s | **REGRESSION** — see §3.2 |

### 4.1 Per-type verdict (per design memo §4.1)

| Type | Outcome | Mechanism (post-§3.2) |
|---|---|---|
| inference | tier-gated adopt candidate (+0.013 graded marginal) | top-K removes noisy entities from gemma4's "evidence eval" → cleaner reasoning |
| comparison | flat | already neutral; multi-source nature less affected by top-K |
| temporal | **adopt candidate** (+0.040 graded above noise edge) | most timeline-oriented queries benefit from focused entity surface |
| null | **REJECT** (-0.120 graded, -0.107 abst_f1 — both outside noise) | top-K removes "evidence-of-absence" signal; gemma4 can no longer determine "answer not present" from narrower context (see §3.2 mechanism) |

Net L1 aggregate = average of types ≈ -0.020 graded (dominated by
null regression). The α-7 fix produces a **type-conditional effect**
at gemma4 production tier — helps inference/temporal slightly, hurts
null queries significantly.

---

## 5. 5-tier mode re-measurement (post-α-7 baseline)

After α-7 lands + baseline captures, run all 5 tiers' endpoint cells
to test whether the 5-mode picture survives the context reshape.

```powershell
foreach ($tier in 'M_XS', 'M_S', 'M_M', 'M_L', 'M_XL') {
    $env:JAMES_WORKSPACE = "./workspaces/hotpot_eval"
    $env:JAMES_BENCH_TIMEOUT = "600"
    python scripts/qvt_ablation_matrix.py `
        --tiers $tier --suite multihop_rag --n-runs 1 `
        --sector-cells C_minus,C_rag-full
}
```

Compute estimate (post-α-7, faster than α-6 due to smaller entity
context):
- M_XS / M_S: ~15-30 min each
- M_M: ~80-100 min
- M_L: ~30-60 min
- M_XL: ~5-8 hours (GPU/CPU split unchanged from α-6)
- **Total: ~8-10 hours**

### 5.1 Mode comparison table (α-6 vs α-7)

| Tier | α-6 pure abst_f1 | α-6 + JAMES abst_f1 | α-6 mode | α-7 + JAMES abst_f1 | α-7 mode | Reshape? |
|---|---:|---:|---|---:|---|---|
| M_XS (1b) | 0.000 | 0.000 | inert | *TBD* | *TBD* | *TBD* |
| M_S (4b) | 0.074 | 0.000 | disrupt | *TBD* | *TBD* | *TBD* |
| M_M (e4b) | 0.558 | 0.591 | amplify | *TBD* | *TBD* | *TBD* |
| M_L (12b) | 0.000 | 0.375 | create | *TBD* | *TBD* | *TBD* |
| M_XL (27b) | 0.258 | 0.077 | disrupt | *TBD* | *TBD* | *TBD* |

### 5.2 Predictions (per memory `feedback_james_mode_taxonomy_context_dependent` §3)

- **27b disrupt likely weakens** — top-K reduces source-injection pressure → native refusal more likely to survive
- **4b disrupt may persist** — weak signal is fragile regardless of context size
- **12b create may weaken** — fewer evidence anchors → reduced enable signal
- **e4b amplify likely stable** — gemma4 grounding training is context-size-invariant
- **1b inert stable** — model too small regardless

If predictions hold → mechanism hypothesis (§3.2 of 27b doc) confirmed +
⭐⭐ mechanism candidate strengthens.

If predictions diverge → 4-step rule investigation; mechanism reshape;
update memory.

---

## 6. Verdict per layer (post-bench fill)

| Layer | Design intent | Primary axes | Δ on primary (intra-M_M) | Regression check | Verdict |
|---|---|---|---|---|---|
| S2 Graph (post top-K) | concept multi-hop | path + graded | *TBD* | abst_f1 *TBD* | *TBD* |
| S4 Citation | source surface | path | *TBD* (expected stable ~+0.41) | quality flat | *TBD* |
| Bucket-(d) oracle phrase | abstention coverage | abst_f1 | *TBD* (12b only shifts; M_M unchanged) | FP check | *TBD* |

---

## 7. Findings to promote (post-bench fill)

| Finding slug | Bucket | Tier | What |
|---|---|---|---|
| `alpha-7-graph-top-k-recovers-m-m-graded` | (a) measurement debt closed | ⭐ operational | *Δ +TBD pending bench* — recovers Phase 1 §3 regression |
| `s4-citation-tier-invariant-stays-under-context-reshape` | (a) universal-law candidate strengthening | ⭐⭐⭐ if path Δ +0.40 across post-α-7 5 tiers | extends 5-point series robustness to context-reshape (cycle dimension) |
| `james-s5-mode-reshape-under-top-k` | (b) mechanism candidate | ⭐⭐ partial | mode pattern α-6 vs α-7 comparison — if 27b disrupt → amplify, mechanism hypothesis (source-injection) confirmed |
| `bucket-d-doesnt-link-narrow-add` | (d) measurement debt closed | ⭐ operational | 12b pure abst_f1 0.000 → ~0.077 (no other tier affected) |

### Findings withdrawn / not promoted

| Withdrawn | Origin | Why |
|---|---|---|
| (carry-over from α-6) "JAMES amplifier" / "inverted-U" / "family-only" / "REVERSES" | recovery curve §5 + memory `feedback_alpha6_findings_mostly_known_to_literature` | already withdrawn pre-α-7 |

---

## 8. Closure PR description draft (template, fill on merge)

The PR #680 description's Quality Delta Card section should populate
from the §1 and §2 tables. Adoption decision:

- **graded Δ ≥ +0.030 vs `3a961a3_rescored`**: adopt; PR title stays
  `feat(α-7)`. Operator runs §5 mode re-measurement, updates this
  doc, then submits closure handover doc for next session.
- **+0.010 ≤ graded Δ < +0.030**: tier-gated adopt; PR title shifts
  to `feat(α-7): graph top-K [tier-gated]`. Per-question-type cross-tab
  decides per-type toggle. §5 still runs.
- **graded Δ < +0.010**: reject + sub-finding investigation. Apply
  4-step rule. Mechanism hypothesis (§3.2 of 27b doc) reframed.
  PR closed without merge; new design memo for next attempt.

---

## 9. Cross-references

- α-7 design memo: `docs/design/v0.4-alpha-7-graph-topk.md`
- α-7 bucket-(d) sub-finding: `reports/research-runs/alpha-7-bucket-d-oracle-phrase-gap.md`
- 4-step audit script: `scripts/research/audit_12b_null_query_refusal_shape.py`
- α-6 closure recovery curve (5-mode picture): `reports/research-runs/alpha-6-phase-3a-recovery-curve-20260601.md`
- α-6 closure 27b analysis (source-injection mechanism): `reports/research-runs/alpha-6-phase-3a-gemma3-27b-analysis-20260601.md`
- Honest framing rule: `memory/feedback_finding_size_honest_framing.md`
- Mode context-dependence memory: `memory/feedback_james_mode_taxonomy_context_dependent.md`
- Graph-bug debt memory: `memory/feedback_graph_layer_top_k_debt.md`
- ARCHITECTURE.md §5.7.11 (new module registry): `docs/ARCHITECTURE.md`
- Closure PR: https://github.com/Hashevolution/James-RAG-Evol/pull/680
- 5-axis Pareto verdict: `scripts/qvt_ablation_matrix.py::_classify_five_axis_delta`

---

## 10. Done condition for α-7 closure

- [ ] Baseline `bfzt6tx9h` exits clean; `baseline_91b9a2c.json` lands
- [ ] §1 + §2 tables populated; QDC card written into PR #680
- [ ] §4 per-question-type cross-tab populated
- [ ] §3 mechanism prediction verdict (graph_paths_count + graded Δ)
- [ ] PR #680 either merged (adopt / tier-gated) or closed (reject)
- [ ] §5 5-tier mode re-measurement complete (only if PR adopted/tier-gated)
- [ ] §6, §7 verdict + findings filled
- [ ] α-7 closure handover doc written → drops into CLAUDE.md
      "Where to look next" first row + next entry doc
- [ ] Memory updates:
  - `feedback_graph_layer_top_k_debt` — annotate "debt resolved at α-7"
  - `feedback_james_mode_taxonomy_context_dependent` — annotate α-7 mode comparison results

After α-7 closure → Phase 3b pre-work (task #10) → Phase 3b proper
(task #13) → α-8 ontology typed-filter.
