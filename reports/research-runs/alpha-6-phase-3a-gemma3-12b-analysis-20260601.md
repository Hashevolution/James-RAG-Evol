# α-6 Phase 3a Analysis — gemma3:12b (scale-ladder midpoint)

> **Auto-filled at**: 2026-06-01T04:23:04.730082+00:00
> **Source**: cell JSONs in `C:\Project\James-RAG-Evol-v010\workspaces\hotpot_eval\reports\research-runs\qvt-ablation-cells`
> **Baseline**: `workspaces\hotpot_eval\eval\qvt\baseline_3a961a3_rescored.json`
> **Filled by**: `scripts/alpha6_fill_phase1.py`
> **Operator action**: fill §4 prose, §5 layer-intent verdicts,
>                     §6 next-phase decision, §7 findings.

---

## 0. Run metadata

| Field | Value |
|---|---|
| Date | 2026-06-01 |
| Workspace | `./workspaces/hotpot_eval` |
| Suite | `multihop_rag` |
| Fixture | `balanced-100` (25 per question_type) |
| Baseline | `3a961a3` (path 0.404 / graded 0.343 / abst_f1 0.609) |
| Tier | M_L only (`gemma3:12b`, think=OFF) |
| Cells | C_minus + C_rag-full (2 cells, no intermediates) |
| Wall-clock | C_minus ~7 min, C_rag-full ~58 min, total ~65 min |
| Sibling tiers | M_XS = `gemma3:1b` (Phase 3a step 1), M_S = `gemma3:4b` (Phase 2), M_M = `gemma4:e4b` (Phase 1), M_XL = `gemma3:27b` (Phase 3a step 3, queued) |

---

## 1. 5-axis Δ table vs baseline

| Cell | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ | Verdict |
|---|---|---|---|---|---|---|
| C_minus | -0.404 | -0.030 | -0.609 | -247 | -59.59 | _observed_ |
| C_rag-basic | n/a | n/a | n/a | n/a | n/a | _missing_ |
| C_rag-graph | n/a | n/a | n/a | n/a | n/a | _missing_ |
| C_rag-full | +0.006 | -0.010 | -0.234 | -236 | -28.78 | _observed_ |
| C_rag-routed | n/a | n/a | n/a | n/a | n/a | _missing_ |

Baseline (for reference): path 0.404 / graded 0.343 / abst_f1 0.609 / token 1150 / latency 64.

---

## 2. Sector-progression Δ (cell-to-cell)

| From → To | Sector added | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ |
|---|---|---|---|---|---|---|
| C_minus → C_rag-basic | + S1 RAG retrieval | _missing_ | _missing_ | _missing_ | _missing_ | _missing_ |
| C_rag-basic → C_rag-graph | + S2 graph + S3 preproc + S4 citation | _missing_ | _missing_ | _missing_ | _missing_ | _missing_ |
| C_rag-graph → C_rag-full | + S5 abstention + S6 cognitive | _missing_ | _missing_ | _missing_ | _missing_ | _missing_ |
| C_rag-full → C_rag-routed | + routing layers (= α-5 L5) | _missing_ | _missing_ | _missing_ | _missing_ | _missing_ |

---

## 3. Predictions vs reality (auto-classified)

Per-step predictions from #662 handover; each compared against the observed Δ.

| Step | Predicted | Observed | Match? |
|---|---|---|---|
| C_minus → C_rag-basic | + S1 RAG retrieval (quality ↑↑ predicted) | _missing_ | _missing_ |
| C_rag-basic → C_rag-graph | + S2 graph + S3 preproc + S4 citation (path ↑, graded ↑) | _missing_ | _missing_ |
| C_rag-graph → C_rag-full | + S5 abstention + S6 cognitive (abst_f1 ↑, latency ↑) | _missing_ | _missing_ |
| C_rag-full → C_rag-routed | + routing layers (= α-5 L5 verdict; inert/regress expected) | _missing_ | _missing_ |

§3 prose:

Endpoint-only measurement (C_minus + C_rag-full); intermediate sector
rows are intentionally `_missing_`. The two cells together give the
intra-tier Δ = "what JAMES contributes on top of pure 12b":

| Axis | Pure 12b | + JAMES (C_rag-full) | Δ (JAMES contribution) |
|---|---:|---:|---:|
| path_coverage | 0.000 | 0.410 | **+0.410** |
| graded_answer | 0.313 | 0.333 | +0.020 |
| abstention_f1 | 0.000 | 0.375 | **+0.375** |
| token_cost | 903 | 913 | +10 |
| latency_cost | 4.1s | 34.9s | +30.8s (8.6×) |

The single observation that **changes** the Phase 2 / Phase 3a-1b
narrative: pure gemma3:12b also produces abst_f1 = 0.000 (same as
1b, lower than 4b's 0.074), yet with JAMES on top it reaches 0.375.
The 1b analysis doc's "inverted-U capability floor" framing
(1b inert / 4b disrupted / e4b amplified) does **not** accommodate
this fourth mode; 12b shows JAMES *substituting for* a missing
native capability rather than amplifying an existing one.

⚠️ **Graded caveat — graph-bug noise**: every graded Δ in α-6 is
measured on top of the current graph layer (which Phase 1 §3 flagged
as `graded -0.053 net regressor due to entity overload`). The "+0.020
graded Δ at 12b" therefore cannot be cleanly attributed to JAMES
contribution vs absence of the regressor's bite at 12b's larger
context. Closure-doc reconciliation: route the publishable graded
claims through the post-graph-fix re-baseline planned in next cycle.

### 3.1 4-step rule audit on `abst_f1 = 0.000` (added post-27b C_minus)

The pure-12b abst_f1 = 0.000 read as a "dip" below 4b (0.074) in the
first draft of this doc. After the 27b C_minus result landed at 0.258
(2026-06-01 PM), the dip story stopped being intuitive — it would have
required a non-monotonic explanation across the gemma3 ladder. Applied
the 4-step rule (per `memory/feedback_oracle_phrase_artifacts`) to
verify the dip before publishing it.

Audit script:
`scripts/research/audit_12b_null_query_refusal_shape.py`
Source bench: `reports/bench_ac9670d_multihop_rag_20260601_115524.json`

Audit result over all 25 null queries:

| Answer category | Count | Notes |
|---|---:|---|
| True hallucination (no refusal indicator) | **24/25** (96%) | Roche, iPhone 13 Pro Max, Sygic+Switzerland, Egypt+Thutmose, etc. — confident fabrications |
| Refusal-shape (oracle missed) | **1/25** (4%) | id=58: `"The data provided doesn't explicitly link a specific Zimbabwean finance minister..."` — clear refusal phrasing not in current `_ABSTENTION_PHRASES` |

**Verdict**: the 12b abst_f1 = 0 is **96% real**. Oracle-corrected
upper bound = ~0.077 (TP=1, FN=24), which is essentially the same as
4b's 0.074. **Reshape framing from "12b dip" to "12b plateau with 4b"
(no improvement despite 3× scale)**. The recovery curve doc §5
withdrawn-claims registry tracks this reshape.

Bucket-(d) sub-finding logged for α-7 or later: oracle phrase list
should narrowly add `doesn't [explicitly] link` and `data [provided]
doesn't` to catch gemma3:12b-style conversational refusals without
FP-flooding partial-answer rows.

---

## 4. Publishable claim (auto-template; operator fills final sentence)

> **JAMES sector endpoint ablation on MultiHop-RAG balanced-100, gemma3:12b ladder-midpoint tier (think=OFF, bge-m3)**:
> - Pure gemma3:12b (no JAMES): path 0.000 / graded 0.313 / abst_f1 0.000 / latency 4.06s
> - JAMES full stack (= α-5 L1) on gemma3:12b: path 0.410 / graded 0.333 / abst_f1 0.375 / latency 34.87s
> - Intra-tier Δ (the publishable column): path **+0.410** / graded **+0.020** / abst_f1 **+0.375** / latency **+30.8s** (8.6×)
>
> ⚠️ **Tone discipline (per memory `feedback_finding_size_honest_framing`)**: framing this result as "JAMES enables abstention in a model that doesn't natively support it" is one possible read; the more honest read is "structured S5 prompts (evidence-grounding + refusal gates) elicit abstention behaviour in a model whose pure inference doesn't produce it on this fixture." The former sounds like JAMES discovered a mechanism; the latter is what was measured. Mechanism candidates (instruction-following capacity threshold? metacognitive ability scaling?) remain hypothesis territory.

---

## 5. Verdict per layer (operator fills per layer-intent matrix)

Per CLAUDE.md rule 2 layer-intent extension (#652) + memory
`mechanism_layer_intent_axis_alignment`. Each sector judged on its
**design-intent axes**, not uniform Pareto.

Phase 3a runs only the C_minus / C_rag-full endpoints, so individual
sectors cannot be decomposed.

| Layer | Design intent | Primary axes | Δ on primary (intra-tier 12b) | Regression check | Verdict |
|---|---|---|---|---|---|
| S1+S2+S3+S4 bundle | retrieval + multi-hop + fluency + citation | path + graded | path **+0.410** ✓✓, graded +0.020 (noise band: graph-bug confound) | abst_f1 +0.375 (joint with S5+S6) | **adopt** — path lead consistent with 1b / 4b / e4b within noise |
| S4 Citation (extracted) | source surface | path primary | **+0.410** | quality flat | **strong-adopt** — path Δ +0.41 matches every measured tier so far |
| S5 Abstention | refusal grounding | abst_f1 primary | **+0.375** ✓ | quality flat | **adopt at this tier only** — substitutes for missing native abstention. Effect *opposite* to 4b (-0.074 disrupt) on same family |
| S6 Cognitive | multi-step | graded primary | graded +0.020 (within noise band) | latency +30.8s | **inconclusive at this tier** — graded delta inside the QVT noise band ±0.104; latency tax is real |

§5 prose — honest tier-tagging per
`memory/feedback_finding_size_honest_framing`:

| Finding | Tier | Note |
|---|---|---|
| Path Δ tier-invariant (+0.41 at 1b/4b/12b) | ⭐⭐⭐ **genuinely novel** | extends to a 4th data point. Universal-law candidate strengthens. Independent of model native capabilities |
| S5 abst_f1 contribution sign flip between 4b (-0.074) and 12b (+0.375) | ⭐⭐ **partial** | known mechanism family (prompt-following capacity threshold; chain-of-thought / Self-RAG analogues). JAMES-specific = the *empirical threshold position* in the gemma3 ladder |
| Routing rule data — operational | ⭐ **operational** | numbers for tier-conditional toggle, not knowledge |
| ~~"JAMES amplifier"~~ ~~"capability floor"~~ ~~"gemma3 vs gemma4 family"~~ | ❌ | 1b-doc framings reversed by this data; closure must reconcile |
| 12b graded +0.020 | ⚪ **inside noise band** | QVT graded noise band ±0.104. Cannot claim improvement. Plus graph-bug confound |

The qualitative addition over the 1b doc: a fourth recovery mode —
**enable** (pure 0 → JAMES 0.375). The previously-claimed 3-mode
taxonomy (inert/disrupt/amplify) doesn't fit. Rather than chasing
a tighter taxonomy, the honest claim is: **JAMES S5's effect is
non-monotonic in pure-model abstention; the mapping is empirical
per tier and cannot be projected from model-size alone**.

---

## 6. Next phase decision (operator)

Per Phase 2 entry doc trigger matrix (#666 §1):

Phase 3a-specific (gemma3 scale ladder probe):

- [x] **12b confirms data point above the 4b "disrupt" threshold but still within gemma3 family** — proceed with 27b (M_XL) to add the highest ladder point per operator decision
- [x] **1b-doc 'inverted-U' framing reversed by 12b enablement** — closure must reconcile both docs; the 4-mode taxonomy (inert/disrupt/enable/amplify) is itself partial — honest claim is empirical non-monotonicity
- [x] **Graph-bug graded confound flagged** — α-7 graph top-K fix becomes the next-cycle dependency for clean graded re-baselining
- [ ] 12b alone shows sufficient signal → could stop here without 27b; declined per operator decision (richer comparison data desired)

§6 action: continue ladder with 27b (M_XL, ~60-90 min compute,
launched in parallel). After 27b lands: write recovery curve doc
across 5 tiers (1b/4b/12b/e4b/27b) + reconcile 1b-doc framing +
Phase 3a closure PR (single PR, standalone closure per operator
decision). Graph-fix becomes next-cycle (post-Phase 3a closure).

---

## 7. Findings to promote (operator)

| Finding slug | Bucket | Tier | What |
|---|---|---|---|
| `s4-citation-tier-invariant-4-point-series` | (a) universal-law | ⭐⭐⭐ | path Δ +0.397 (4b) / +0.410 (1b) / +0.410 (12b) / +0.419 (e4b) — 4 data points within noise. Independent of model native capability. Strongest non-trivial finding from α-6 cycle |
| `james-s5-effect-non-monotonic-in-pure-abstention` | (b) model-context interaction | ⭐⭐ | S5+S6 abst_f1 contribution Δ: 1b 0.000 / 4b -0.074 / 12b +0.375 / e4b +0.033. Sign flips between 4b and 12b in same family. Mechanism candidate = instruction-following capacity threshold; JAMES-specific = the threshold position |
| `gemma3-12b-pure-abstention-plateau-with-4b` | (b) model-context | ⭐ | 4-step rule audit (§3.1): raw 0.000 → oracle-corrected ~0.077 ≈ 4b's 0.074. 12b shows no within-family abstention improvement over 4b despite 3× scale. Reshaped from earlier "dip" finding |
| `gemma3-12b-james-routing-data` | (c) operational | ⭐ | 12b + JAMES = path 0.41 / graded 0.33 / abst_f1 0.375 / 35s latency. Operational routing input, not a knowledge claim |
| `graph-layer-bug-confounds-all-graded-deltas` | (d) measurement debt | ⭐⭐ | every α-6 graded Δ depends on the current graph layer which regresses graded at M_M (-0.053 per Phase 1 §3). Resolves on α-7 graph top-K fix → re-baseline |
| `oracle-misses-doesnt-link-pattern` | (d) measurement debt | ⭐ | 4-step rule found 1 missed refusal pattern at 12b. Narrow add to `_ABSTENTION_PHRASES` for α-7 sub-finding (would shift 12b pure abst_f1 from 0.000 → 0.077; framing-significant, magnitude-small) |

⚠️ **Findings withdrawn vs prior phase docs**:

| Withdrawn finding | Origin | Why withdrawn |
|---|---|---|
| "JAMES = capability amplifier, not small-model crutch" | Phase 2 closure (#674) | 12b shows S5 substitutes for absent capability (= small-model crutch direction), not amplifier. The framing was overclaim |
| "Inverted-U capability floor (1b inert / 4b disrupt / e4b amplify)" | Phase 3a 1b doc (commit `ac9670d`) | 12b enables a 4th mode (enable). The 3-mode U was incomplete; even a 4-mode taxonomy fits only 4 data points |
| "Capability floor between 4b and e4b" | Phase 2 §6 + Phase 3a 1b §4 | reframed as empirical non-monotonicity per tier, not a single threshold |

Run `scripts/qvt_promote_findings.py` to draft memory entries —
**but defer the ⭐⭐⭐ promotion until 27b lands** so the S4
tier-invariant series gets its 5th data point before promotion.

---

## 8. Cross-references

- α-6 design memo: `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md`
- Phase 1 template: `reports/research-runs/alpha-6-phase-1-analysis-TEMPLATE.md` (#665)
- Phase 2 entry: `docs/handovers/v0.4-alpha-6-phase-2-entry.md` (#666)
- Layer-intent matrix: `memory/mechanism_layer_intent_axis_alignment.md`
- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`
- Position guard: `memory/feedback_jameses_positioning_replayable_rag.md`
- Matrix runner sector cells: PR #663
- Renderer sector cells + progression: PR #664
- This auto-fill script: `scripts/alpha6_fill_phase1.py` (#667)

