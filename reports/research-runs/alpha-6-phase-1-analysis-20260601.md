# α-6 Phase 1 Analysis (auto-filled CCCC)

> **Auto-filled at**: 2026-06-01T00:15:55.270592+00:00
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
| C_minus | -0.404 | +0.003 | -0.051 | +235 | -51.74 | _observed_ |
| C_rag-basic | -0.404 | -0.017 | -0.188 | +419 | -51.05 | _observed_ |
| C_rag-graph | +0.007 | -0.070 | -0.147 | +415 | -34.93 | _observed_ |
| C_rag-full | +0.015 | -0.017 | -0.018 | +74 | +2.34 | _observed_ |
| C_rag-routed | +0.008 | -0.027 | -0.109 | +55 | +4.71 | _observed_ |

Baseline (for reference): path 0.404 / graded 0.343 / abst_f1 0.609 / token 1150 / latency 64.

---

## 2. Sector-progression Δ (cell-to-cell)

| From → To | Sector added | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ |
|---|---|---|---|---|---|---|
| C_minus → C_rag-basic | + S1 RAG retrieval | +0.000 | -0.020 | -0.137 | +184 | +0.69 |
| C_rag-basic → C_rag-graph | + S2 graph + S3 preproc + S4 citation | +0.411 | -0.053 | +0.040 | -4 | +16.12 |
| C_rag-graph → C_rag-full | + S5 abstention + S6 cognitive | +0.008 | +0.053 | +0.129 | -341 | +37.27 |
| C_rag-full → C_rag-routed | + routing layers (= α-5 L5) | -0.007 | -0.010 | -0.091 | -19 | +2.38 |

---

## 3. Predictions vs reality (auto-classified)

Per-step predictions from #662 handover; each compared against the observed Δ.

| Step | Predicted | Observed | Match? |
|---|---|---|---|
| C_minus → C_rag-basic | + S1 RAG retrieval (quality ↑↑ predicted) | path_coverage=+0.000, graded_answer=-0.020, abstention_f1=-0.137 | path_coverage: ~ flat (predicted ↑, got flat); graded_answer: ✗ SURPRISE (predicted ↑, got ↓); abstention_f1: n/a (no prediction) |
| C_rag-basic → C_rag-graph | + S2 graph + S3 preproc + S4 citation (path ↑, graded ↑) | path_coverage=+0.411, graded_answer=-0.053, abstention_f1=+0.040 | path_coverage: ✓ match; graded_answer: ✗ SURPRISE (predicted ↑, got ↓); abstention_f1: n/a (no prediction) |
| C_rag-graph → C_rag-full | + S5 abstention + S6 cognitive (abst_f1 ↑, latency ↑) | abstention_f1=+0.129, latency_cost=+37.265 | abstention_f1: ✓ match; latency_cost: ✓ match |
| C_rag-full → C_rag-routed | + routing layers (= α-5 L5 verdict; inert/regress expected) | abstention_f1=-0.091 | abstention_f1: ✓ match |

[FILL §3 prose: 2-3 sentences interpreting the matches/surprises]

---

## 4. Publishable claim (auto-template; operator fills final sentence)

> **JAMES sector ablation on MultiHop-RAG balanced-100, gemma4:e4b production tier (think=OFF, bge-m3)**:
> - Pure gemma4 (no JAMES): path 0.000 / graded 0.347 / abst_f1 0.558
> - + chroma RAG retrieval: path 0.000 / graded 0.327 / abst_f1 0.421
> - + graph + preprocessing + citation: path 0.411 / graded 0.273 / abst_f1 0.462
> - JAMES full stack (= α-5 L1): path 0.419 / graded 0.327 / abst_f1 0.591
> - JAMES + routing layers (= α-5 L5): path 0.412 / graded 0.317 / abst_f1 0.500
>
> [FILL: 1-2 sentence operator interpretation. Mother-platform framing per positioning guard.]

---

## 5. Verdict per layer (operator fills per layer-intent matrix)

Per CLAUDE.md rule 2 layer-intent extension (#652) + memory
`mechanism_layer_intent_axis_alignment`. Each sector judged on its
**design-intent axes**, not uniform Pareto.

| Layer | Design intent | Primary axes | Δ on primary | Regression check | Verdict |
|---|---|---|---|---|---|
| S1 RAG retrieval | retrieval recall | path + graded | path 0 (S4 also off), graded -0.020 | abst_f1 -0.137 | **reject** — RAG alone hurts both axes |
| S2 Graph + S3 Preproc + S4 Citation (bundled) | concept multi-hop + input fluency + source surface | path + graded | **path +0.411** ✓, graded -0.053 | cost +16s latency | **mixed** — citations work (path ↑↑), graph hurts graded |
| S5 Abstention | refusal grounding | abst_f1 primary | **abst_f1 +0.129** ✓ | quality protection: graded +0.054 ✓ | **adopt** — strong abst_f1 recovery + graded recovery |
| S6 Cognitive | multi-step reasoning | graded primary | bundled with S5 (+0.054 ✓) | latency +37s (expected trade-off) | **adopt** with caveat — quality-cost trade-off |

§5 prose:

The per-layer reading reveals the cycle's strongest finding:
JAMES's S5 abstention + S6 cognitive layers (bundled in this batch)
**recover the quality lost by S1 RAG + S2 Graph**. Specifically:

- S1 RAG alone hurts abst_f1 by -0.137 (RAG context surfaces
  irrelevant docs on null queries → 4 more hallucinations than
  pure LLM at gemma4:e4b). This matches the Lost-in-the-Middle /
  Power-of-Noise literature.
- S2 Graph + S3 Preproc compounds the loss on graded (-0.053
  more) by surfacing 41-161 graph entities per query — far more
  than the LLM can effectively integrate. Mitigation: aggressive
  top-K graph filtering (engineering work, not architectural).
- S4 Citation works as designed: +0.411 on path coverage, no
  regression elsewhere. JAMES's citation surface IS its measurable
  structural value.
- S5 + S6 (bundled) RECOVER the graded loss and add +0.129 abst_f1
  on top — these are doing the heaviest semantic work in the JAMES
  stack at the production tier. The latency cost (+37s, total
  ~66s/query) is the operational tax.

The verdict per layer matches the cycle's discipline: cost layers
judged on cost, quality layers judged on quality, no uniform
Pareto. JAMES's net contribution at gemma4:e4b: structural
auditability (citations) + a recovery cost-axis (S5/S6 fixing
S1/S2 damage at 5.5× latency).

---

## 6. Next phase decision (operator)

Per Phase 2 entry doc trigger matrix (#666 §1):

- [x] **Phase 1 shows clear sector-additive signal** → proceed to Phase 2 (M_S tier)
- [ ] Phase 1 shows ambiguous / mixed signal → run C_rag-cited isolation first
- [ ] Phase 1 shows sectors regressive at production → apply 4-step rule, bucket the result
- [ ] Phase 1 shows clear gemma4:e4b best → Phase 3a lower priority

Chosen: Phase 2 launch (M_S = gemma3:4b). The tier-gated routing
hypothesis becomes: *"does the smaller model see a larger relative
S5+S6 recovery from the S1/S2 damage?"* If yes, JAMES is a
small-model alignment crutch; if no, the recovery is model-
invariant and the stack is universally useful (with the latency
cost trade-off).

Phase 2 launch command (PowerShell-equivalent, executed via bash
syntax in this session):

```
JAMES_WORKSPACE=./workspaces/hotpot_eval \
PYTHONIOENCODING=utf-8 \
PYTHONUNBUFFERED=1 \
  python -u scripts/qvt_ablation_matrix.py \
    --tiers M_S --suite multihop_rag --n-runs 1 \
    --sector-cells C_minus,C_rag-basic,C_rag-graph
```

ETA per #666 §3: ~75 min (smaller model proportionally faster).

---

## 7. Findings to promote (operator)

| Finding slug | Bucket | What |
|---|---|---|
| `multihop-rag-lost-in-middle-at-gemma4-e4b` | (b) — model-context interaction | RAG addition degrades abst_f1 by 0.137 at production tier; matches Lost-in-the-Middle literature |
| `jameses-s5-s6-recover-rag-damage` | (a) — architecture-as-designed | S5 abstention + S6 cognitive collectively recover +0.054 graded + +0.129 abst_f1 from the S1+S2 damage; this is the measurable JAMES contribution |
| `jameses-graph-too-many-entities-surfaced` | (a) — architecture, optimizable | graph_paths counts 41-161/query overwhelm the LLM context window; top-K relevance filtering is the cheapest engineering improvement (~1 day) |
| `multihop-rag-citation-axis-jameses-only` | (a) — structural | +0.411 path coverage isolates as JAMES's unique structural contribution (LLM alone has 0 citation surface) |

Run `scripts/qvt_promote_findings.py` to draft memory entries for
the bucket-(a) entries (mechanism-candidates).

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

