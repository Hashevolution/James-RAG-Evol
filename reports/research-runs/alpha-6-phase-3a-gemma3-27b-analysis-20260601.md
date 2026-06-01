# α-6 Phase 3a Analysis — gemma3:27b (scale-ladder saturation probe)

> **Skeleton built pre-bench** (2026-06-01 PM, background `bhsl1zgqm` in
> flight). Numbers in *TBD italics* will be filled when the run lands.
> Honest framing per `memory/feedback_finding_size_honest_framing` —
> apply tier tags + don't reuse Phase 2 / 1b "amplifier" / "capability
> floor" framings.

---

## 0. Run metadata

| Field | Value |
|---|---|
| Date | 2026-06-01 |
| Workspace | `./workspaces/hotpot_eval` |
| Suite | `multihop_rag` |
| Fixture | `balanced-100` (25 per question_type) |
| Baseline | `3a961a3` (M_M e4b, path 0.404 / graded 0.343 / abst_f1 0.609) |
| Tier | M_XL only (`gemma3:27b`, think=OFF) |
| Cells | C_minus + C_rag-full (2 cells, no intermediates) |
| Wall-clock | C_minus ~1.5-2h, C_rag-full ~4-6h, total ~6-8h |
| GPU/CPU split | 48% CPU / 52% GPU (VRAM oversubscription on 17 GB model) |
| Timeout overrides | `JAMES_BENCH_TIMEOUT=600`, `JAMES_BENCH_SUBPROCESS_TIMEOUT=32400` (commit `be2fb64`) |
| Sibling tiers (already measured) | M_XS = `gemma3:1b`, M_S = `gemma3:4b`, M_M = `gemma4:e4b`, M_L = `gemma3:12b` |

---

## 1. 5-axis Δ table vs M_M baseline

| Cell | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ | Verdict |
|---|---:|---:|---:|---:|---:|---|
| C_minus | -0.404 | +0.047 | -0.351 | -227 | +13.65 | _observed_ |
| C_rag-basic | n/a | n/a | n/a | n/a | n/a | _missing_ |
| C_rag-graph | n/a | n/a | n/a | n/a | n/a | _missing_ |
| C_rag-full | -0.001 | -0.033 | -0.532 | -50 | +124.04 | _observed_ |
| C_rag-routed | n/a | n/a | n/a | n/a | n/a | _missing_ |

Baseline (for reference): path 0.404 / graded 0.343 / abst_f1 0.609 / token 1150 / latency 64.

---

## 2. Sector-progression Δ (cell-to-cell)

*Intentionally `_missing_` — Phase 3a endpoint-only.*

---

## 3. Predictions vs reality (auto-classified)

§3 prose:

Endpoint-only measurement; intermediates intentionally `_missing_`. The
two cells together give the intra-tier Δ = "what JAMES contributes on
top of pure 27b":

| Axis | Pure 27b | + JAMES (C_rag-full) | Δ (JAMES contribution) |
|---|---:|---:|---:|
| path_coverage | 0.000 | **0.403** | **+0.403** ← 5-point S4 universal candidate confirmed |
| graded_answer | 0.390 | 0.310 | **-0.080** (graph-bug confound; see §3 caveat) |
| abstention_f1 | 0.258 | 0.077 | **-0.181** ⚡ disruption (audit-clean, not artifact) |
| token_cost | 923 | 1100 | +177 |
| latency_cost | 77.65s | 188.04s | +110.4s (2.4× tax — lowest tax ratio across ladder) |

### Hypothesis check (predictions vs observed)

| Hypothesis | Predicted | Observed | Verdict |
|---|---|---|---|
| H1 — S4 citation tier-invariant extends to 27b | path Δ +0.40 ± 0.02 | **+0.403** | **✅ confirmed** — 5-point series 1b/4b/12b/27b/e4b all within +0.397~+0.419 |
| H2 — Pure 27b abst_f1 stays at gemma3-family floor | pure abst_f1 ≈ 0.00 | **0.258** | ❌ **refuted** — 27b emerges within-family abstention; gemma4-only hypothesis dead |
| H2-alt — Pure 27b emerges abst_f1 > 0.20 | pure abst_f1 > 0.20 | **0.258** | ✅ confirmed |
| H3 — JAMES on 27b enables abst_f1 like 12b | full abst_f1 +0.30 to +0.50 | **0.077** (Δ = -0.181) | ❌ **refuted** — opposite direction; disruption not enable |
| H3-alt — JAMES on 27b saturates above 12b | full abst_f1 +0.50 or higher | 0.077 | ❌ refuted |
| **H3-alt2 (surprise)** — JAMES on 27b regresses below 12b | full abst_f1 < +0.30 | **0.077** | ✅ **confirmed** — apply 4-step rule (done in §3.1) |

The "surprise" hypothesis fired — 27b is the **disruption** mode like
4b, not amplification. Despite 27b's higher native capability, JAMES
broke its refusal behaviour. Mode-vs-scale is non-monotonic within the
gemma3 family.

### 3.1 4-step rule audit on C_rag-full (post-result, before publishing)

Following the same 4-step protocol applied to 12b C_minus (which
caught 1 oracle phrase gap), audited 27b C_rag-full's 24 oracle-FN
answers using `scripts/research/audit_12b_null_query_refusal_shape.py`.

| Audit metric | Value |
|---|---|
| Oracle TP (refusal caught) | 1/25 |
| Oracle FN (refusal missed or hallucination) | 24/25 |
| Audit-found missed refusal patterns | **0/24** |
| True hallucinations in FN set | 24/24 (100%) |

Conclusion: **the 27b disruption is REAL**, not an oracle phrase
coverage artifact. The 24 FN answers are all genuine hallucinations.

### 3.2 Mechanism observation — Source-file injection commits the model

The 24 hallucination answers at 27b C_rag-full all share a pattern:
they start with `"Source files: multihop_0543_..., multihop_0212_...,
multihop_0188_..."` (JAMES's retrieved-source filename injection).

The model treats the presence of N source filenames as evidence
that "an answer must exist within these N sources" and produces
confident fabrications. Native abstention behaviour — which surfaces
at pure 27b with 4 TPs ("Source files: None provided",
"unable to answer", "without direct access to") — gets suppressed
when JAMES injects 41-161 source filenames.

The one surviving TP (null #3 id=54) explicitly rejected JAMES's
injected context: `"the provided documents do **not** contain
information about the band 'Used To Be Young'..."`. The other 3
native refusals from pure 27b became hallucinations once JAMES
context was added.

**Implication for α-7**: cutting the source surface from 41-161 to
~10 (top-K) is expected to reduce the "must answer" pressure. α-7
closure includes 5-tier mode re-measurement to test whether this
reshapes the 5-mode picture. See
[[feedback_james_mode_taxonomy_context_dependent]] +
[[feedback_graph_layer_top_k_debt]].

### 3.3 Graded caveat (carry-over)

The graded Δ = -0.080 at 27b is the largest graded regression
across the 5-tier ladder, consistent with the graph-bug-confound
flagged in Phase 1 §3. Larger model context space → more entities
surfaced → more reasoning interference. α-7 graph top-K fix should
reverse this regression at re-baseline.

### Hypotheses to compare against the observed (predictions per
`feedback_finding_size_honest_framing` — explicit + falsifiable):

| Hypothesis | Predicted Δ | What it would mean |
|---|---|---|
| **H1 — S4 citation tier-invariant extends to 27b** | path Δ +0.40 ± 0.02 | 5-point series confirms ⭐⭐⭐ universal-law candidate at JAMES architectural level |
| **H2 — Pure 27b abst_f1 stays at gemma3-family floor** | pure abst_f1 ≈ 0.00 (matching 1b/12b) | abstention is a gemma4-only baseline-capability (would confirm half of "family matters") |
| **H2-alt — Pure 27b emerges abst_f1 > 0** | pure abst_f1 > 0.20 | 27b reaches a metacognitive threshold gemma3:12b didn't — family-only hypothesis weaker |
| **H3 — JAMES on 27b enables abst_f1 like 12b** | full abst_f1 +0.30 to +0.50 | "enable" mode extends to 27b → operational routing rule: adopt full stack from 12b+ |
| **H3-alt — JAMES on 27b saturates above 12b** | full abst_f1 +0.50 or higher | saturation point identified; cost-benefit shifts toward 12b for production |
| **H3-alt2 — JAMES on 27b regresses below 12b** | full abst_f1 < +0.30 | non-monotonic behaviour within gemma3 — surprising; would need 4-step rule investigation |

⚠️ **Graded caveat — graph-bug noise**: same as 12b doc §3. Every
graded Δ here is measured on top of the current graph layer which
regresses graded at M_M (-0.053). The α-7 graph top-K fix
(`docs/design/v0.4-alpha-7-graph-topk.md`) is the next-cycle
dependency for clean graded re-baselining; until then, treat 27b
graded Δ as confounded.

---

## 4. Publishable claim (operator-fill post-bench)

> **JAMES sector endpoint ablation on MultiHop-RAG balanced-100, gemma3:27b ladder-saturation tier (think=OFF, bge-m3)**:
> - Pure gemma3:27b (no JAMES): path 0.000 / graded 0.390 / abst_f1 **0.258** / latency 77.65s
> - JAMES full stack (= α-5 L1) on gemma3:27b: path **0.403** / graded 0.310 / abst_f1 **0.077** / latency 188.04s
> - Intra-tier Δ (the publishable column): path **+0.403** / graded **-0.080** / abst_f1 **-0.181** / latency **+110.4s** (2.4× tax)
>
> Two findings to highlight:
> 1. **S4 citation universal candidate confirmed at 5 data points** (1b/4b/12b/27b/e4b path Δ all in +0.397~+0.419 — within noise across a 27× model size and 2 model families). Strongest non-trivial finding from α-6 cycle.
> 2. **27b disruption is real and audit-clean** (§3.1 audit found 0/24 oracle misses). JAMES's source-file context injection (41-161 filenames per query) suppresses 27b's native refusal behaviour. The disruption mechanism (§3.2) explains why 27b drops from 0.258 → 0.077 despite having more native abstention than gemma3:12b (which goes 0.000 → 0.375 in the opposite direction).
>
> ⚠️ **Tone discipline (per `memory/feedback_finding_size_honest_framing`)**: the 5-mode pattern (inert/disrupt/create/disrupt/amplify across 1b/4b/12b/27b/e4b) is **cycle-specific empirical**, not universal. It depends on α-6 cycle's context shape (full sector stack, 41-161 entity overload). α-7 graph top-K fix is expected to reshape this pattern (see [[feedback_james_mode_taxonomy_context_dependent]]). Universal-law candidate promotion requires α-7 5-tier remeasurement + Phase 3b cross-family verification.

---

## 5. Verdict per layer (post-bench fill)

| Layer | Design intent | Primary axes | Δ on primary (intra-tier 27b) | Regression check | Verdict |
|---|---|---|---|---|---|
| S1+S2+S3+S4 bundle | retrieval + multi-hop + fluency + citation | path + graded | path **+0.403** ✓✓, graded **-0.080** ✗ | abst_f1 **-0.181** ✗✗ | **mixed/regression** at this tier — path lead intact, but graded + abstention both regress |
| S4 Citation (extracted) | source surface | path primary | **+0.403** ✓✓✓ | quality flat | **strong-adopt (5-point universal-law candidate)** — within +0.397~+0.419 across 1b/4b/12b/27b/e4b |
| S5 Abstention | refusal grounding | abst_f1 primary | **-0.181** ✗✗ | quality protection failed: graded -0.080 too | **reject at this tier** — source-file context injection commits the model to answer; native refusal suppressed (§3.2 mechanism). α-7 top-K may reverse this |
| S6 Cognitive | multi-step | graded primary | graded -0.080 ✗ | latency **+110s (2.4× tax)** | **reject at this tier** — cognitive stages compound the source-injection commitment. Lowest tax ratio across ladder because raw inference dominates |

### §5 prose:

Tier-tagging per `memory/feedback_finding_size_honest_framing`:

| Finding | Tier | Status |
|---|---|---|
| **S4 citation tier-invariant 5-point series** | ⭐⭐⭐ candidate | **confirmed** — path Δ +0.397~+0.419 across 1b/4b/12b/27b/e4b. Cross-fixture sanity remains pre-requisite for `validated` promotion |
| JAMES S5 disruption mechanism (source-file injection commits model) | ⭐⭐ partial mechanism candidate | empirical at 27b; mechanism gated on α-7 top-K reshaping test |
| 5-mode JAMES taxonomy (inert/disrupt/create/disrupt/amplify) | ⭐⭐ partial, cycle-specific | not universal; depends on α-6 context shape. ⭐⭐⭐ candidate requires α-7+α-8 stability + cross-family in Phase 3b |
| 27b operational routing data | ⭐ operational | adopt: S4 citation only at 27b production; skip S5+S6 unless α-7 reverses disruption |
| Anything ending in "amplifier" / "capability floor" / "REVERSES" | ❌ | superseded vocabulary; do not revive |
| 27b latency tax 2.4× (lowest across ladder) | ⭐ operational | inference dominates over JAMES overhead at 27b; cost-efficiency angle vs other tiers |

### Qualitative additions over 1b / 4b / 12b docs

- **Upper-bound of gemma3 ladder**: S5+S6 disruption at high native
  capability (0.258 → 0.077) refutes the "amplifier" framing
  decisively. Even strong native abstention gets broken by
  source-file injection.
- **S4 5-point series**: the strongest single finding from α-6 cycle.
  Independent of native LLM capability profile, family, scale.
- **2.4× latency tax**: the cheapest JAMES tax ratio observed. This
  is because 27b raw inference is so slow (77.65s pure) that JAMES
  overhead (~110s) doesn't multiply as dramatically. At e4b (5.5×),
  the JAMES overhead matters more proportionally.

The 5-mode picture is the empirical map; the mechanism (source-file
injection committing the model) is observed at 27b but unconfirmed
elsewhere; α-7 + α-8 + Phase 3b will tell whether the pattern is
robust under context change and cross-family.

---

## 6. Next phase decision (post-bench fill)

Phase 3a closure trigger (per recovery curve doc §9 done-condition):

- [ ] **27b completes** (`bhsl1zgqm` background) — all cell JSONs land
- [ ] 27b row filled in recovery curve doc §1-§3, §6, §7
- [ ] S4 5-point series check in recovery curve §4
- [ ] Phase 3a closure PR submitted with all 5 analysis docs + recovery
      curve + 2 design memos + CLAUDE.md sync + ROADMAP
- [ ] Memory 3 entries saved (gated on closure PR landing):
  - `feedback_alpha6_findings_mostly_known_to_literature`
  - `project_alpha_7_ontology_track_pre_decision`
  - `feedback_graph_layer_top_k_debt`

Phase 3b (cross-family) decision (per design memo):

- If H1 confirmed → cross-fixture sanity becomes next priority over
  cross-family (universal-law candidate validation)
- If H1 partially confirmed (4-of-5 within band) → cross-family runs
  to check whether the wobble is family-specific
- If H1 reversed → 4-step rule investigation before any next cycle

α-7 (graph top-K) is the next cycle regardless of Phase 3b decision —
per 2026-06-01 strategy handover §4 sequencing rule.

---

## 7. Findings to promote (post-bench fill)

| Finding slug | Bucket | Tier | What |
|---|---|---|---|
| `s4-citation-tier-invariant-5-point-series` | (a) universal-law | ⭐⭐⭐ candidate | path Δ +0.397/+0.410/+0.410/+0.403/+0.419 across 1b/4b/12b/27b/e4b. Validated within MultiHop-RAG fixture; cross-fixture pending |
| `james-s5-source-injection-disrupts-native-refusal` | (b) mechanism candidate | ⭐⭐ partial | 27b pure abst_f1 0.258 → JAMES 0.077 (-0.181). 24 hallucination answers all start with "Source files: ..." injection. Mechanism: model commits to answer when N sources present. Reshaping pending α-7 top-K |
| `gemma3-27b-james-routing-data` | (c) operational | ⭐ | 27b production routing: S4 citation only; skip S5+S6 (-0.181 abst_f1) unless α-7 reverses disruption |
| `27b-latency-tax-lowest-in-ladder` | (c) operational | ⭐ | 2.4× tax (vs e4b 5.5×, 12b 8.6×, 4b 8.2×) — inference dominates JAMES overhead at this scale |

### Findings WITHDRAWN (carry-over from earlier docs):

| Withdrawn finding | Origin | Why withdrawn |
|---|---|---|
| "JAMES = capability amplifier" | Phase 2 #674 | 12b reversed; 27b will not revive |
| "Inverted-U capability floor" | Phase 3a 1b doc | superseded by 4-mode + recovery curve doc §5 |
| "Capability floor between 4b and e4b" | Phase 2 §6 + 1b §4 | 12b crossed it; floor is not a single position |
| "Only gemma4 family can use abstention layers" | speculation during 12b wait | 12b enabled abst_f1; refuted |

---

## 8. Cross-references

- α-6 design memo: `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md`
- α-6 cycle PR index: `reports/research-runs/alpha-6-cycle-pr-index.md`
- Phase 1 analysis (M_M): `reports/research-runs/alpha-6-phase-1-analysis-20260601.md`
- Phase 2 analysis (M_S): `reports/research-runs/alpha-6-phase-2-analysis-20260601.md`
- Phase 3a 1b: `reports/research-runs/alpha-6-phase-3a-gemma3-1b-analysis-20260601.md` (⚠️ post-12b reconciliation header)
- Phase 3a 12b: `reports/research-runs/alpha-6-phase-3a-gemma3-12b-analysis-20260601.md`
- Phase 3a recovery curve: `reports/research-runs/alpha-6-phase-3a-recovery-curve-20260601.md`
- α-7 design memo (next cycle): `docs/design/v0.4-alpha-7-graph-topk.md`
- α-8 design memo (cycle after): `docs/design/v0.4-alpha-8-ontology-typed-filter.md`
- Honest framing rule: `memory/feedback_finding_size_honest_framing.md`
- Matrix runner tier override (#677): `memory/feedback_matrix_runner_tier_model_override.md`
- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`
- Layer-intent matrix: `memory/mechanism_layer_intent_axis_alignment.md`
- 27b timeout overrides commit: `be2fb64`

---

## 9. Done condition

- [ ] Bench landed (background `bhsl1zgqm` exits 0)
- [ ] §1 / §3 / §4 / §5 / §7 filled with bench numbers
- [ ] Recovery curve doc §1-3 / §6 / §7 M_XL row populated
- [ ] §6 next-phase decision filled per actual H1/H2/H3 result
- [ ] Phase 3a closure PR submitted; this doc included
- [ ] Memory 3 entries saved (post-PR landing)
