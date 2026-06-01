# α-6 Cycle PR Index — Live (2026-06-01 PM)

> α-5 closed with `reports/research-runs/alpha-5-cycle-pr-index.md`
> (#655). α-6 cycle continues — this is the live navigable index
> for α-6 PRs landed so far. Update as each PR lands.
>
> **Cycle range (live)**: PR #663 → #677+ (extends α-5's 1-655)
> **Total project PRs to date (α-6)**: 17+ landed PRs + 9 commits on
> closure branch pending PR
> **α-5 PRs**: 47 (#608 → #654, plus #655 = cycle close)
> **α-6 prep + Engineering pre PRs**: 11 (#657-#661 + #662-#666)
> **α-6 Phase 1 closure**: 4 (#667 → #670)
> **α-6 Phase 2 closure**: 5 (#671-#676)
> **α-6 Phase 3a tier extension**: 1 (#677)
> **α-6 Phase 3a closure (pending PR)**: 10 commits on
> `feat/v0.4-alpha6-phase-3a-closure` branch — see §K

---

## Quick stats

| Category | Count |
|---|---|
| **Total α-6 cycle PRs landed** | 17 (#663 → #677) |
| **Closure branch commits pending PR** | 10 (Phase 3a closure consolidation) |
| Sector flag features (S1-S6) | 5 (#657-#661) |
| Matrix runner + renderer extensions | 3 (#663, #664, #677 tier extension) |
| Phase 1 closure (template + auto-fill + analysis + findings) | 4 (#665, #667, #668, #669) |
| Phase 2 closure (rate-limit + tier-parametrized fill + analysis) | 5 (#671-#676) |
| Phase 2 entry doc | 1 (#666) |
| Phase 1 design + handover | 3 (#646, #647, #650) |
| Memory layer-intent + CLAUDE.md rule 2 | 1 (#652) |
| **Wrong-fix-averted in cycle** | **9** (was 7 at Phase 1 close; +1 at Phase 2 rate-limit; +1 at Phase 3a tier override) |
| Cumulative JAMES code change against α-5+α-6 measurement debt | **0 lines** |

---

## A. α-5 carryover — finished section (see #655 for full index)

α-5 cycle (#608 → #654) closed cleanly with cycle index #655. The
following α-5 outputs carry forward as α-6 inputs:

| α-5 output | α-6 use |
|---|---|
| Cell `L1/M_M` (corrected baseline) | C_rag-full alias in Phase 1 |
| Cell `L5/M_M` (full stack) | C_rag-routed alias in Phase 1 |
| Cell `L1/M_M-thinkON` sanity | not used yet in α-6 |
| `baseline_3a961a3_rescored.json` | baseline for Phase 1 / 2 Δ |
| Workspace `workspaces/hotpot_eval/` | shared with α-6 |
| Methodology (4-step rule, layer-intent matrix, position guard) | applied throughout α-6 |

7 of 7 wrong-fix-averted in α-5 cycle (memory `feedback_oracle_phrase_artifacts`).

---

## B. α-6 design + handover (#646-#647, #650, #662)

| PR | Title | Topic |
|---|---|---|
| #646 | α-6 design memo (BBB) | 10 sectors, multi-LLM matrix design |
| #647 | α-6 local-first phasing (CCC) | 9 local Ollama models inventoried |
| #650 | α-6 engineering pre — 5-PR sequence plan (FFF) | sector flag PR roadmap |
| #662 | next session entry — α-6 Phase 1 ready (VVV) | 52-PR pause-point handover |

---

## C. α-6 Engineering pre — 5 sector flags (#657-#661)

| PR | Sector | Flag |
|---|---|---|
| #657 | S4 Citation | `JAMES_DISABLE_SOURCES_FIELD` |
| #658 | S2 Graph | `JAMES_DISABLE_GRAPH` |
| #659 | S1 RAG Retrieval | `JAMES_DISABLE_RAG_RETRIEVAL` |
| #660 | S5 Abstention | `JAMES_DISABLE_ABSTENTION` |
| #661 | S6 Cognitive Stages | `JAMES_DISABLE_COGNITIVE_STAGES` |

21/21 sector flag contract tests green. Disable-polarity (default OFF =
sector ON = production byte-identical).

---

## D. α-6 Matrix runner + renderer (#663-#664)

| PR | Title | What |
|---|---|---|
| #663 | matrix runner --sector-cells extension | wire 5 sector flags into cell envs; 6 sector cells in `_SECTOR_CELL_ENVS` (C_minus / C_rag-basic / C_rag-cited / C_rag-graph / C_rag-full / C_rag-routed); --sector-cells CLI flag mutually exclusive with --rows; output filename `qvt-ablation-cell-{sector_cell}-{tier}.json`; schema v3 with `sector_cell` + `sector_cell_label` |
| #664 | renderer --render-report picks up sector cells | new "α-6 sector-cells" table + "Sector-progression Δ" table (cell-to-cell); α-5 L1/L5 auto-aliased into C_rag-full/C_rag-routed for the progression |

---

## E. α-6 Phase 1 (#665, #667-#669)

| PR | Title | What |
|---|---|---|
| #665 | Phase 1 analysis TEMPLATE (XXX) | 8-section operator-fill format with predictions-vs-reality framework |
| #667 | alpha6_fill_phase1.py — Phase 1 closure auto-fill (CCCC) | reads cell JSONs + baseline, fills §0-§4 + auto-classifies §3 match/surprise |
| #668 | Phase 1 analysis filled — operator commentary + Phase 2 decision | §5 per-layer verdicts (S5+S6 = ADOPT; S2/S3 graph = MIXED), §6 next phase (M_S launch), §7 findings list |
| #669 | 4 Phase 1 findings logged + memory drafts promoted (FFFF) | 4 mechanism candidates auto-drafted via #633 promotion script |

### Phase 1 verdict (M_M = gemma4:e4b production tier)

**JAMES infrastructure does NOT dramatically improve answer quality vs the
bare LLM on MultiHop-RAG.** Citations (path 0 → 0.42) = JAMES's unique
structural lead. S5 + S6 recover quality damage S1 + S2 cause. Latency
tax: 5.5× over pure LLM.

| Cell | path | graded | abst_f1 | latency |
|---|---|---|---|---|
| C_minus (pure LLM) | 0.0 | 0.347 | 0.558 | 11.9s |
| C_rag-basic (+S1 RAG) | 0.0 | 0.327 | 0.421 | 12.6s |
| C_rag-graph (+S2+S3+S4) | 0.411 | 0.273 | 0.462 | 28.7s |
| C_rag-full (=L1, +S5+S6) | 0.419 | 0.327 | 0.591 | 66.0s |

---

## F. α-6 Phase 2 (#666 entry, launch in flight)

| PR | Title | What |
|---|---|---|
| #666 | Phase 2 entry — tier-gated check at gemma3:4b (YYY) | trigger matrix, launch command, expected compute (~75 min on smaller model), reading rules |

**Phase 2 background task**: `b7z1i104c` (in flight).
**Partial Phase 2 verdict so far** (C_minus + C_rag-basic at M_S):
- gemma3:4b alone: TP=25 FP=46 (over-refuses, abst_f1 0.521)
- gemma3:4b + RAG: TP=0 FN=25 (NEVER refuses, abst_f1 0.000)
- Smaller model exhibits 2-mode behavior: refuse-everything without context,
  trust-everything with context. Tier-gated routing strongly hinted.

⚠️ Missing cell — `C_rag-full / M_S` (= `L1 / M_S`) NOT in α-5 carryover.
Operator action: launch `L1/M_S` alone post-Phase 2 to complete the
tier-gated comparison. ~5 min compute on gemma3:4b.

---

## G. Memory drafts staged (`reports/research-runs/promoted-findings/`)

From PR #669 (FFFF):

- `finding_multihop_rag_lost_in_middle_at_gemma4_e4b.md` (bucket-b,
  general literature reproduction)
- `finding_jameses_s5_s6_recover_rag_damage.md` (bucket-a, mechanism
  + universal-law candidate)
- `finding_jameses_graph_too_many_entities_surfaced.md` (bucket-a,
  optimization candidate; ~1 day code fix)
- `finding_multihop_rag_citation_axis_jameses_only.md` (bucket-a,
  structural; JAMES's one-axis lead)

Operator action: review each draft, move accepted into
`~/.claude/projects/.../memory/`, add MEMORY.md index lines.

---

## H. Live α-6 cycle deliverables (in flight)

| Track | Status |
|---|---|
| Phase 2 launch (M_S sector cells) | **running** (task `b7z1i104c`) |
| Phase 2 follow-up: `L1/M_S` for full-stack/M_S baseline | pending (after Phase 2 task completes) |
| Phase 3a (gemma3 scale ladder) | gated on Phase 2 verdict |
| Phase 3b (cross-family) | gated on Phase 3a verdict |
| AUTO_ROUTER multi-tier engineering | gated on Phase 4+ decision |
| Engineering candidate: graph top-K filtering | ✅ Phase 1/2/3a all confirmed graded regression; α-7 cycle design memo landed `docs/design/v0.4-alpha-7-graph-topk.md` |
| Engineering candidate: ontology typed-filter | ✅ promoted from "v0.5+ pilot" to **α-8 cycle** (post-α-7 closure); design memo landed `docs/design/v0.4-alpha-8-ontology-typed-filter.md` with integration plan vs existing 4 entity types |

---

## K. Phase 3a closure branch (pending PR — `feat/v0.4-alpha6-phase-3a-closure`)

10 commits accumulated against α-6 cycle measurement debt while
Phase 3a 27b runs in background. Single closure PR planned post-27b
finish. Commit list:

| # | Commit | Theme |
|---|---|---|
| 1 | `ac9670d` | feat — Phase 3a 1b analysis + alpha6_fill_phase1.py M_XS/M_XL choices |
| 2 | `492b28e` | docs — Phase 3a 12b analysis (honest framing applied) |
| 3 | `be2fb64` | fix — bench + matrix subprocess timeout env overrides (for 27b GPU/CPU split) |
| 4 | `85beb6e` | docs — recovery curve skeleton + 1b doc reconciliation header |
| 5 | `0528f27` | docs — CLAUDE.md sync to v0.4.1 + α-6 measurement cycle |
| 6 | `6ac76dd` | docs — α-7 + α-8 design memo drafts (no code change) |
| 7 | `7250699` | docs — ROADMAP α-6/α-7/α-8 + sequencing rule |
| 8 | `4a5a60c` | docs — Phase 3a 27b analysis skeleton (pre-bench placeholders) |
| 9 | `f9938a0` | docs — 4-step rule audit on 12b abst_f1=0 → reshape "dip" to "plateau" |
| 10 | `<pending>` | docs — α-7 bucket-(d) oracle phrase gap sub-finding |

Closure PR will additionally include: 27b numbers (post-bench),
recovery curve M_XL row + S4 5-point series confirmation, closure
PR description with consolidated narrative.

---

## I. After-cycle follow-up tracks (still gated)

| Track | Trigger |
|---|---|
| DOI bump (Vehicle A/C separation per #655 SSS) | T3 ship + mid-June joint piece framing |
| Joint piece preprint (Vehicle C, multi-author) | 6/6+ Ali resume + framing confirmation |
| MultiHop-RAG paper baseline reproduction (#651 EEE) | independent; ~5 h, runnable in parallel |
| α-6 cycle closure PR | post Phase 3 completion |

---

## J. References

- α-5 cycle PR index: `reports/research-runs/alpha-5-cycle-pr-index.md` (#655)
- Phase 1 analysis: `reports/research-runs/alpha-6-phase-1-analysis-20260601.md`
- Phase 2 analysis: `reports/research-runs/alpha-6-phase-2-analysis-20260601.md`
- Phase 3a 1b analysis (⚠️ reconciliation header): `reports/research-runs/alpha-6-phase-3a-gemma3-1b-analysis-20260601.md`
- Phase 3a 12b analysis (honest framing): `reports/research-runs/alpha-6-phase-3a-gemma3-12b-analysis-20260601.md`
- Phase 3a 27b analysis (skeleton): `reports/research-runs/alpha-6-phase-3a-gemma3-27b-analysis-20260601.md`
- Phase 3a recovery curve: `reports/research-runs/alpha-6-phase-3a-recovery-curve-20260601.md`
- Phase 2 entry: `docs/handovers/v0.4-alpha-6-phase-2-entry.md`
- Phase 3a entry: `docs/handovers/v0.4-next-session-entry-2026-06-01-PM.md`
- α-7 design memo (next cycle): `docs/design/v0.4-alpha-7-graph-topk.md`
- α-8 design memo (cycle after): `docs/design/v0.4-alpha-8-ontology-typed-filter.md`
- α-7 bucket-(d) sub-finding: `reports/research-runs/alpha-7-bucket-d-oracle-phrase-gap.md`
- 4-step rule audit script: `scripts/research/audit_12b_null_query_refusal_shape.py`
- Findings log: `reports/research-runs/qvt-ablation-findings.md`
- α-6 design memo: `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md`
- α-6 engineering pre plan: `docs/design/v0.4-alpha-6-engineering-pre-pr-sequence.md`
- Honest framing rule: `memory/feedback_finding_size_honest_framing.md`
- Matrix runner tier override (9th wrong-fix): `memory/feedback_matrix_runner_tier_model_override.md`
- Layer-intent mechanism: `memory/mechanism_layer_intent_axis_alignment.md`
- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`
- Position guard: `memory/feedback_jameses_positioning_replayable_rag.md`
