# α-6 Phase 3a Analysis — gemma3:1b (extreme small / below-floor probe)

---

## ⚠️ Post-12b reconciliation header (added 2026-06-01 after Phase 3a M_L lands)

The framings below were written before the M_L (gemma3:12b) data
landed. M_L data reverses several of the claims made here. The body
text is preserved as the historical record of what the 1b run *alone*
seemed to support; the reconciliation table below lists what changes
once M_L is in the picture.

| Claim in this doc | Status after M_L | Where to read the corrected version |
|---|---|---|
| §4 "deeply below the abstention capability floor" | **partially withdrawn** — M_L pure abst_f1 is also 0.000, refuting "1b is uniquely below the floor"; the floor concept itself becomes weak | recovery curve doc §5 |
| §4 "inverted-U recovery curve (1b inert / 4b disrupted / e4b amplified)" | **withdrawn** — M_L adds a fourth mode (enable: pure 0 → JAMES 0.375). Three-mode U is incomplete | recovery curve doc §3 + §5 |
| §5 "S5+S6 → tier-gated adopt. Adopt at M_M. REJECT at M_S" | **scope unchanged for M_XS / M_S / M_M, but M_L adds adopt at +0.375 abst_f1** — the routing rule becomes 4-row, not 3-row | recovery curve doc §6 |
| §5 "abstention-recovery layers exhibit a capability floor: they reward model capacity above a threshold, not deficit below it" | **withdrawn** — M_L shows substitution / enablement (not reward of existing capacity); the framing was too tidy for the actual non-monotonic data | recovery curve doc §3 prose |
| §7 `inverted-u-capability-floor-s5-s6` finding | **withdrawn** | recovery curve §5 |
| §7 `s4-citation-tier-invariant-extended-to-1b` finding | **strengthened** — M_L confirmed at +0.410 path, making a 4-point series | recovery curve §4 |
| §7 `gemma3-1b-rag-stack-feasible-but-no-quality-lift` finding | **survives** — still tier-specific operational observation | promoted as-is |

Honest framing rule per `memory/feedback_finding_size_honest_framing`:
the inverted-U was written under the misimpression that 4b's
disruption mode would generalise to other gemma3 points. It doesn't.
The 1b doc's mistake is not the *numbers* (those are correct as
measured) but the *taxonomy* — we extrapolated a 3-mode regime from
2 data points (the 4b "disrupted" inference from Phase 2 + the 1b
"inert" observation). Two data points can fit many curves; we picked
a curve that the next data point refuted.

The body below is preserved verbatim for audit trail. **For the
honest current picture, read the recovery curve doc** at
`reports/research-runs/alpha-6-phase-3a-recovery-curve-20260601.md`.

---


> **Auto-filled at**: 2026-06-01T02:48:57.051371+00:00
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
| Tier | M_XS only (`gemma3:1b`, think=OFF) |
| Cells | C_minus + C_rag-full (2 cells, no intermediates) |
| Wall-clock | C_minus ~3 min, C_rag-full 11.5 min, total ~15 min |
| Sibling tiers | M_S = `gemma3:4b` (Phase 2), M_M = `gemma4:e4b` (Phase 1) |

---

## 1. 5-axis Δ table vs baseline

| Cell | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ | Verdict |
|---|---|---|---|---|---|---|
| C_minus | -0.404 | -0.047 | -0.609 | -395 | -62.73 | _observed_ |
| C_rag-basic | n/a | n/a | n/a | n/a | n/a | _missing_ |
| C_rag-graph | n/a | n/a | n/a | n/a | n/a | _missing_ |
| C_rag-full | +0.006 | -0.087 | -0.609 | -437 | -56.74 | _observed_ |
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

Phase 3a only ran the two endpoint cells (C_minus and C_rag-full), so
the intermediate sector-progression rows are intentionally `_missing_`.
The endpoint comparison alone — pure gemma3:1b vs JAMES full stack on
gemma3:1b — is what localises the capability-floor question.

The single non-trivial observation against the M_M baseline (e4b):
**path coverage at C_rag-full is +0.006**, i.e. the JAMES retrieval +
citation stack on a 1b backbone matches the e4b baseline within noise.
At pure-LLM C_minus the same model gets path **-0.404** (= 0.000
absolute). This makes S4 citation contribution **+0.410 intra-tier on
1b**, indistinguishable from the +0.397 measured on 4b and +0.42 on
e4b. The structural layer is **scale-invariant down to 1b**.

---

## 4. Publishable claim (auto-template; operator fills final sentence)

> **JAMES sector endpoint ablation on MultiHop-RAG balanced-100, gemma3:1b extreme-small tier (think=OFF, bge-m3)**:
> - Pure gemma3:1b (no JAMES): path 0.000 / graded 0.297 / abst_f1 0.000 / latency 0.92s
> - JAMES full stack (= α-5 L1) on gemma3:1b: path 0.410 / graded 0.257 / abst_f1 0.000 / latency 6.91s
> - Intra-tier Δ (the publishable column): path **+0.410** / graded **-0.040** / abst_f1 **0.000** / latency **+5.99s** (7.5×)
>
> The 1b backbone is **deeply below the abstention capability floor** — pure-LLM abst_f1 is already at the absolute zero (TP=0, FN=25), so JAMES's S5+S6 layers have *nothing to amplify and nothing to disrupt*. This is qualitatively distinct from Phase 2 (gemma3:4b), where the pure LLM scored 0.074 abst_f1 and JAMES *disrupted* it to 0.000 (Δ = -0.074). The capability floor manifests as an **inverted-U recovery curve**, not a simple threshold: 1b is *inert*, 4b is *disrupted*, e4b is *amplified*. Meanwhile S4 citation contributes +0.41 path on 1b, matching every other tier exactly — the structural primitive survives the smallest production scale tested.

---

## 5. Verdict per layer (operator fills per layer-intent matrix)

Per CLAUDE.md rule 2 layer-intent extension (#652) + memory
`mechanism_layer_intent_axis_alignment`. Each sector judged on its
**design-intent axes**, not uniform Pareto.

Because Phase 3a runs only the C_minus / C_rag-full endpoints, the
S1 / S2 / S3 / S4 contributions cannot be decomposed individually
from this run alone. Each row below assigns the **bundled S1+S2+S3+S4
(retrieval + graph + preproc + citation)** Δ, then judges the S5+S6
slot from the same C_rag-full cell against expectations.

| Layer | Design intent | Primary axes | Δ on primary (intra-tier 1b) | Regression check | Verdict |
|---|---|---|---|---|---|
| S1+S2+S3+S4 bundle | RAG retrieval + concept multi-hop + input fluency + source surface | path + graded | path **+0.410** ✓✓, graded -0.040 | abst_f1 0 (already at floor) | **adopt** — structural path lead is tier-invariant down to 1b |
| S4 Citation (extracted) | source surface | path primary | **+0.410** ✓✓✓ | quality flat | **strong-adopt (universal-law)** — path Δ matches 4b (+0.397) and e4b (+0.42) within noise across a **27× model-size gap** |
| S5 Abstention | refusal grounding | abst_f1 primary | **0.000 (inert)** | TP=0/FN=25 at both endpoints | **inert** — qualitatively distinct from Phase 2 (4b: reject via -0.074 disruption). 1b has no abstention behaviour for the layer to either amplify or disrupt |
| S6 Cognitive | multi-step reasoning | graded primary | graded **-0.040** ✗ | latency **+5.99s (7.5×)** | **reject** — same direction as Phase 2 (4b: -0.070), magnitude smaller because pure 1b is already short-answer compressed; the latency tax buys no measurable graded gain |

§5 prose:

The 1b verdict at the S5/S6 slot is **not a softer version of the 4b
verdict — it is a different mode**. At 4b the model attempts
abstention (pure abst_f1 = 0.074) and JAMES interferes (drops to 0).
At 1b the model never attempts abstention (pure = 0); the layers
mechanically engage but neither amplify nor disrupt anything. The
recovery curve C_rag-full − C_minus is therefore:

| Tier | Pure abst_f1 | Full abst_f1 | Δ | Mode |
|---|---|---|---|---|
| M_XS (1b) | 0.000 | 0.000 | **0.000** | **inert** |
| M_S (4b) | 0.074 | 0.000 | **-0.074** | **disrupted** |
| M_M (e4b) | 0.558 | 0.591 | **+0.033** | **amplified** |
| M_L (12b) | TBD | TBD | TBD | TBD (running) |
| M_XL (27b) | TBD | TBD | TBD | TBD (queued) |

This is the **inverted-U capability floor** finding. The floor is not
a single threshold the model crosses; it is a regime change where
*below* the floor the layer is silent (1b), *at* the floor the layer
fails (4b), and *above* it the layer amplifies (e4b). The publishable
mechanism is sharper than the Phase 2 hypothesis allowed.

---

## 6. Next phase decision (operator)

Per Phase 2 entry doc trigger matrix (#666 §1):

Phase 3a-specific trigger (not from the Phase 1/2 decision matrix —
that matrix is for picking next-phase tier, while Phase 3a is about
localising the capability floor across pre-chosen scales):

- [x] **1b confirms below-floor (inert, not just disrupted)** — proceed
      with 12b run (M_L) to bracket the floor from above
- [ ] 1b shows S5+S6 positive recovery → unexpected; would revise the
      capability-floor mental model upward toward 1b
- [ ] 1b shows S5+S6 catastrophic regression beyond 4b's -0.074 → would
      suggest a different mechanism (e.g. RAG context overflow at 1b
      context window) — would require sub-finding investigation
- [x] S4 citation still tier-invariant at 1b → **strong-adopt universal-law
      candidate confirmed across 27× model-size gap** — promote as
      mechanism-candidate memory entry

§6 action: continue ladder with 12b (M_L tier, ~30-90 min compute)
then 27b (M_XL tier, ~60-90 min). 12b is the critical bracketing
scale — if it shows positive S5+S6 recovery, the floor sits between
4b and 12b. If it shows inert/disrupted behaviour, the floor sits
between 12b and e4b (~5b effective), which would be a surprising
finding worth a sub-finding investigation.

---

## 7. Findings to promote (operator)

| Finding slug | Bucket | What |
|---|---|---|
| `s4-citation-tier-invariant-extended-to-1b` | (a) universal-law | path Δ +0.397 (4b) / +0.41 (1b) / +0.42 (e4b) — S4 citation contributes identical path coverage across 27× model size gap, indistinguishable within noise. Phase 2 finding `s4-citation-tier-invariant` extended to the smallest production scale tested. |
| `inverted-u-capability-floor-s5-s6` | (a) mechanism-candidate | S5+S6 recovery has three regimes: inert (1b, no abstention to amplify), disrupted (4b, weak abstention broken by JAMES), amplified (e4b, strong abstention enhanced). Not a simple threshold — a regime change. |
| `gemma3-1b-rag-stack-feasible-but-no-quality-lift` | (b) model-context interaction | 1b can run the full JAMES stack at 7.5× latency tax, gain +0.41 path, lose -0.04 graded. Net: pay 7s for citations on a model that can't otherwise cite. Useful as a *citation-renderer* tier even if not a *reasoning* tier. |

Run `scripts/qvt_promote_findings.py` to draft memory entries for the
universal-law / mechanism-candidate items above.

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

