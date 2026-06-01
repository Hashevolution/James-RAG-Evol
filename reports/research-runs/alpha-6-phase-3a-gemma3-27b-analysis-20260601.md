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

*Auto-filled by `alpha6_fill_phase1.py --tier M_XL` post-bench. Below
table is a placeholder structure.*

| Cell | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ | Verdict |
|---|---|---|---|---|---|---|
| C_minus | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | _observed_ |
| C_rag-basic | n/a | n/a | n/a | n/a | n/a | _missing_ |
| C_rag-graph | n/a | n/a | n/a | n/a | n/a | _missing_ |
| C_rag-full | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | _observed_ |
| C_rag-routed | n/a | n/a | n/a | n/a | n/a | _missing_ |

Baseline (for reference): path 0.404 / graded 0.343 / abst_f1 0.609 / token 1150 / latency 64.

---

## 2. Sector-progression Δ (cell-to-cell)

*Intentionally `_missing_` — Phase 3a endpoint-only.*

---

## 3. Predictions vs reality (auto-classified)

§3 prose (operator-fill post-bench):

Endpoint-only measurement; intermediates intentionally `_missing_`. The
two cells together give the intra-tier Δ = "what JAMES contributes on
top of pure 27b":

| Axis | Pure 27b | + JAMES (C_rag-full) | Δ (JAMES contribution) |
|---|---:|---:|---:|
| path_coverage | *TBD* | *TBD* | *TBD* |
| graded_answer | *TBD* | *TBD* | *TBD* |
| abstention_f1 | *TBD* | *TBD* | *TBD* |
| token_cost | *TBD* | *TBD* | *TBD* |
| latency_cost | *TBD* | *TBD* | *TBD* (~8× tax expected) |

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
> - Pure gemma3:27b (no JAMES): path *TBD* / graded *TBD* / abst_f1 *TBD* / latency *TBD*
> - JAMES full stack (= α-5 L1) on gemma3:27b: path *TBD* / graded *TBD* / abst_f1 *TBD* / latency *TBD*
> - Intra-tier Δ (the publishable column): path **TBD** / graded **TBD** / abst_f1 **TBD** / latency **TBD** (~8× tax expected)
>
> ⚠️ **Tone discipline (per memory `feedback_finding_size_honest_framing`)** — same as 12b doc §4. The observation is empirical numbers; mechanism candidates (saturation curve, instruction-following threshold, family-bound vs scale-bound) remain hypothesis territory. JAMES-specific value is the *measured tier position*, not the *discovered mechanism*.

---

## 5. Verdict per layer (post-bench fill)

| Layer | Design intent | Primary axes | Δ on primary (intra-tier 27b) | Regression check | Verdict |
|---|---|---|---|---|---|
| S1+S2+S3+S4 bundle | retrieval + multi-hop + fluency + citation | path + graded | path *TBD* / graded *TBD* | abst_f1 *TBD* | *TBD per data* |
| S4 Citation (extracted) | source surface | path primary | *TBD* (compare to +0.397~+0.420 from 1b/4b/12b/e4b) | quality flat | *TBD per data* |
| S5 Abstention | refusal grounding | abst_f1 primary | *TBD* | quality flat | *TBD per data* |
| S6 Cognitive | multi-step | graded primary | *TBD* | latency *TBD* | *TBD per data* |

### §5 prose (post-bench fill):

Tier-tagging per `memory/feedback_finding_size_honest_framing`:

| Finding | Tier | Note |
|---|---|---|
| S4 citation tier-invariant 5-point series | ⭐⭐⭐ if path Δ +0.40±0.02 → universal-law candidate matures | confirmation vs partial vs reversal per 27b data |
| JAMES S5 effect at 27b vs 12b | ⭐⭐ if positive Δ; ⭐ operational if saturated; bucket-(d) investigation if regression | apply 4-step rule before reframing if surprise |
| 27b operational routing data | ⭐ operational | numbers for routing rule, not knowledge |
| Anything ending in "amplifier" / "capability floor" / "REVERSES" | ❌ | superseded vocabulary; do not revive |
| Latency tax at 27b | ⭐ operational | 8× expected; if higher, "27b not production-feasible" itself is the finding |

The qualitative addition over the 12b doc — the **upper-bound** of the
scale ladder:
- Does the S5+S6 enable behaviour from 12b plateau, grow, or regress?
- Does S4 path Δ universal-law candidate survive a 27× model size
  span (1b → 27b) without noise blur?
- Does the latency tax stay at ~8× or get worse at the GPU/CPU split?

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

*Auto-template; operator fills numbers + bucket-tags after data lands.*

| Finding slug | Bucket | Tier | What |
|---|---|---|---|
| `s4-citation-tier-invariant-5-point-series` | (a) universal-law | ⭐⭐⭐ (if confirmed) | extends to 5th data point at 27b; *promotes from "candidate" to "validated within MultiHop-RAG fixture"* |
| `gemma3-27b-james-routing-data` | (c) operational | ⭐ | 27b + JAMES = *TBD*; routing rule input |
| TBD per surprise | TBD | TBD | apply 4-step rule before drafting |

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
