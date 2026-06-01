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

| Axis | Pre-α-7 (`3a961a3_rescored`) | Post-α-7 (`91b9a2c`) | **Δ** |
|---|---:|---:|---:|
| path_coverage | 0.404 | *TBD* | *TBD* |
| graded_answer | 0.343 | *TBD* | *TBD* |
| abstention_f1 | 0.609 | *TBD* | *TBD* |
| token_cost | 1150 | *TBD* | *TBD* |
| latency_cost | 64s | *TBD* | *TBD* |

Noise band (N=3 paired reruns, in baseline JSON `noise_band`):
- graded: ±*TBD* (was ±0.104 at α-6 close)
- abst_f1: ±*TBD* (was ±0.286)
- path: ±*TBD* (was ~0.0)

### 1.1 Acceptance decision (per design memo §4)

| Outcome | Condition | Verdict |
|---|---|---|
| **Adopt** | graded Δ ≥ +0.030 vs α-6 baseline | *pending* |
| **Tier-gated adopt** | +0.010 ≤ graded Δ < +0.030 | *pending* |
| **Reject + investigate** | graded Δ < +0.010 | *pending* |

Per-question-type cross-tab **mandatory** for any verdict other than reject — see §4.

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

The α-6 27b audit (`scripts/research/audit_12b_null_query_refusal_shape.py`)
identified that the graph layer's 41-161 entity surface (truncated
downstream to 10 but in DFS visit order) leaves the LLM looking at
the wrong 10 entities. α-7 sorts by `_dfs_score` before the cap so
the LLM sees the highest-ranked 10.

Two falsifiable predictions to compare against the bench:

| Prediction | If confirmed | If refuted |
|---|---|---|
| **graph_paths_count** drops from typical 41-161 to ≤ 10 per query | top-K filter wires through correctly | filter not engaged; check `expand_dynamic` return path |
| **graded Δ** recovers by at least +0.030 vs α-6 baseline | top-K is the dominant fix mechanism | other graph-layer issue beyond top-K; sub-finding investigation per design memo §8 decision 5 |

⚠️ **Build-before-claim discipline**: §1 and §2 tables empty until
bench runs. The PR description's Quality Delta Card uses the **filled**
table, not the prediction.

---

## 4. Per-question-type cross-tab (mandatory)

*Populate from baseline JSON's `per_type` aggregate.*

| Question type | graded Δ | abst_f1 Δ | path Δ | latency Δ | Notes |
|---|---:|---:|---:|---:|---|
| inference (n=25) | *TBD* | *TBD* | *TBD* | *TBD* | |
| comparison (n=25) | *TBD* | *TBD* | *TBD* | *TBD* | most affected by graph noise (multi-source) |
| temporal (n=25) | *TBD* | *TBD* | *TBD* | *TBD* | |
| null (n=25) | *TBD* | *TBD* | *TBD* | *TBD* | abstention quality probe; bucket-(d) phrases now active |

Per-type verdict per design memo §4.1 (cross-tab acceptance band).

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
