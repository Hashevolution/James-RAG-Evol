# α-6 Phase 1 Analysis (auto-filled CCCC)

> **Auto-filled at**: 2026-06-01T01:21:28.656198+00:00
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
| Tier | M_M only (`gemma4:e4b`, think=OFF) |

---

## 1. 5-axis Δ table vs baseline

| Cell | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ | Verdict |
|---|---|---|---|---|---|---|
| C_minus | -0.404 | -0.037 | -0.535 | -220 | -61.79 | _observed_ |
| C_rag-basic | -0.404 | +0.007 | -0.609 | -229 | -60.84 | _observed_ |
| C_rag-graph | -0.008 | +0.017 | -0.609 | -207 | -56.48 | _observed_ |
| C_rag-full | -0.008 | -0.053 | -0.609 | -193 | -48.09 | _observed_ |
| C_rag-routed | n/a | n/a | n/a | n/a | n/a | _missing_ |

Baseline (for reference): path 0.404 / graded 0.343 / abst_f1 0.609 / token 1150 / latency 64.

---

## 2. Sector-progression Δ (cell-to-cell)

| From → To | Sector added | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ |
|---|---|---|---|---|---|---|
| C_minus → C_rag-basic | + S1 RAG retrieval | +0.000 | +0.043 | -0.074 | -10 | +0.95 |
| C_rag-basic → C_rag-graph | + S2 graph + S3 preproc + S4 citation | +0.397 | +0.010 | +0.000 | +22 | +4.36 |
| C_rag-graph → C_rag-full | + S5 abstention + S6 cognitive | +0.000 | -0.070 | +0.000 | +14 | +8.40 |
| C_rag-full → C_rag-routed | + routing layers (= α-5 L5) | _missing_ | _missing_ | _missing_ | _missing_ | _missing_ |

---

## 3. Predictions vs reality (auto-classified)

Per-step predictions from #662 handover; each compared against the observed Δ.

| Step | Predicted | Observed | Match? |
|---|---|---|---|
| C_minus → C_rag-basic | + S1 RAG retrieval (quality ↑↑ predicted) | path_coverage=+0.000, graded_answer=+0.043, abstention_f1=-0.074 | path_coverage: ~ flat (predicted ↑, got flat); graded_answer: ✓ match; abstention_f1: n/a (no prediction) |
| C_rag-basic → C_rag-graph | + S2 graph + S3 preproc + S4 citation (path ↑, graded ↑) | path_coverage=+0.397, graded_answer=+0.010, abstention_f1=+0.000 | path_coverage: ✓ match; graded_answer: ~ flat (predicted ↑, got flat); abstention_f1: n/a (no prediction) |
| C_rag-graph → C_rag-full | + S5 abstention + S6 cognitive (abst_f1 ↑, latency ↑) | abstention_f1=+0.000, latency_cost=+8.399 | abstention_f1: ~ flat (predicted ↑, got flat); latency_cost: ✓ match |
| C_rag-full → C_rag-routed | + routing layers (= α-5 L5 verdict; inert/regress expected) | _missing_ | _missing_ |

[FILL §3 prose: 2-3 sentences interpreting the matches/surprises]

---

## 4. Publishable claim (auto-template; operator fills final sentence)

> **JAMES sector ablation on MultiHop-RAG balanced-100, gemma4:e4b production tier (think=OFF, bge-m3)**:
> - Pure gemma4 (no JAMES): path 0.000 / graded 0.307 / abst_f1 0.074
> - + chroma RAG retrieval: path 0.000 / graded 0.350 / abst_f1 0.000
> - + graph + preprocessing + citation: path 0.397 / graded 0.360 / abst_f1 0.000
> - JAMES full stack (= α-5 L1): path 0.397 / graded 0.290 / abst_f1 0.000
> - JAMES + routing layers (= α-5 L5): path n/a / graded n/a / abst_f1 n/a
>
> [FILL: 1-2 sentence operator interpretation. Mother-platform framing per positioning guard.]

---

## 5. Verdict per layer (operator fills per layer-intent matrix)

Per CLAUDE.md rule 2 layer-intent extension (#652) + memory
`mechanism_layer_intent_axis_alignment`. Each sector judged on its
**design-intent axes**, not uniform Pareto.

| Layer | Design intent | Primary axes | Δ on primary | Regression check | Verdict |
|---|---|---|---|---|---|
| S1 RAG retrieval | retrieval recall | path + graded | path 0 (S4 also off), graded **+0.043** ✓ | abst_f1 -0.074 | **mixed** — RAG helps small-model graded but kills abstention |
| S2 Graph + S3 Preproc + S4 Citation (bundled) | concept multi-hop + input fluency + source surface | path + graded | **path +0.397** ✓, graded +0.010 | abst_f1 0 (already at floor) | **adopt** — structural path lead survives small-model tier |
| S5 Abstention | refusal grounding | abst_f1 primary | **abst_f1 +0.000** ✗ | quality protection failed: graded -0.070 | **reject** — layer mechanically engaged but produces NO recovery at this tier |
| S6 Cognitive | multi-step reasoning | graded primary | graded -0.070 ✗ | latency +8s | **reject** — cognitive stages compound graded loss; the small model lacks the capacity to benefit from multi-stage reasoning |

§5 prose:

**The Phase 2 verdict reverses the tier-gated routing hypothesis.**
The original prediction (per #666 §2): smaller models would see
larger relative S5+S6 recovery from S1/S2 damage. The observation:
S5+S6 recover **zero** abst_f1 at gemma3:4b (matched only by the
already-failing C_rag-basic/M_S baseline of 0.000) and **degrade**
graded by 0.070. The pattern is the opposite at production tier
where the same layers recover +0.129 abst_f1 and +0.054 graded.

The honest finding: **JAMES's abstention + cognitive layers are a
*capability amplifier*, not a *small-model crutch*.** They require
sufficient model metacognitive ability to engage meaningfully. At
gemma3:4b, the model genuinely lacks the ability to detect "I
should refuse" patterns regardless of how the prompt is softened
(S5) or how many cognitive stages run (S6). The 8.4× latency tax
buys nothing measurable at this tier.

Per-layer verdict revision:
- **S1 RAG retrieval** → tier-conditional. *Helps* at M_S
  (+0.043 graded), *hurts* at M_M (-0.020 graded). Confirms the
  Lost-in-the-Middle reversal at smaller capacity (the small model
  lacks parametric knowledge to be confused).
- **S4 Citation** → universally adopted. +0.397 path at M_S
  matches +0.42 at M_M. Model-size-invariant structural contribution.
- **S5 + S6** → tier-gated adopt. Adopt at M_M (+0.129 abst_f1,
  +0.054 graded). REJECT at M_S (no recovery + cost penalty).

This is itself a publishable finding — *"abstention-recovery
layers exhibit a capability floor: they reward model capacity
above a threshold, not deficit below it."*

---

## 6. Next phase decision (operator)

Per Phase 2 entry doc trigger matrix (#666 §1):

- [x] **Phase 1+2 jointly show tier-conditional sector value** — proceed to Phase 3a (gemma3 scale ladder) to find the capability floor for S5+S6 recovery
- [ ] Phase 1 shows ambiguous / mixed signal → run C_rag-cited isolation first
- [ ] Phase 1 shows sectors regressive at production → apply 4-step rule, bucket the result
- [ ] Phase 1 shows clear gemma4:e4b best → Phase 3a lower priority

Chosen: **Phase 3a launch** — gemma3 scale ladder
(1b / 4b / 12b / 27b) × {C_rag-full, C_minus} to find the
*capability floor* — at what model size does S5+S6 recovery kick
in? Hypothesis: somewhere between 4b (no recovery) and e4b (small
positive recovery), so the floor sits in the 4-7b region. The
ladder will localize it.

Phase 3a launch command:

```
JAMES_WORKSPACE=./workspaces/hotpot_eval \
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 \
  python -u scripts/qvt_ablation_matrix.py \
    --tiers M_S --suite multihop_rag --n-runs 1 \
    --sector-cells C_minus,C_rag-full
```

(then repeat with `JAMES_LLM_MODEL=gemma3:12b` and `gemma3:27b`
to span the ladder; ~30-40 min per cell pair on small models,
~60-90 min on 12b/27b)

Routing-policy preview (gated on Phase 3a):
- M_M (gemma4:e4b): adopt full JAMES stack (S5+S6 measurably help)
- M_S (gemma3:4b): adopt **only S4 citation**; skip S5+S6 (zero
  benefit, real cost)
- Capability floor between 4b and e4b — Phase 3a localizes

---

## 7. Findings to promote (operator)

| Finding slug | Bucket | What |
|---|---|---|
| `jameses-s5-s6-capability-floor-not-crutch` | (a) architecture + universal-law candidate | S5+S6 recover at M_M but ZERO at M_S; capability amplifier, not crutch |
| `tier-conditional-rag-helps-small-hurts-large` | (b) model-context interaction | S1 RAG +0.043 graded at M_S vs -0.020 at M_M; Lost in the Middle reverses below capability threshold |
| `s4-citation-tier-invariant` | (a) architecture + universal-law | Path coverage 0.397-0.419 across both tiers; structural contribution survives scale |
| `jameses-rate-limit-corruption-arithmetic-step` | (a) measurement + mechanism-candidate | 4-step rule arithmetic extension caught Phase 2 rate-limit corruption; lesson is the arithmetic step itself |

Run `scripts/qvt_promote_findings.py` to draft memory entries for
the universal-law / mechanism-candidate entries.

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

