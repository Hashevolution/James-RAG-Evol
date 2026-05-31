# α-6 Phase 1 Analysis — TEMPLATE

> **Copy this file** to `alpha-6-phase-1-analysis-<YYYYMMDD>.md`
> after the in-flight Phase 1 (task `ba3jwm9rt`) completes. Fill the
> placeholders marked `[FILL]` from `--render-report` output.
>
> **Phase 1 scope**: 3 new sector cells × gemma4:e4b production tier:
> - `C_minus` (pure LLM, no JAMES infrastructure)
> - `C_rag-basic` (+ S1 chroma RAG retrieval)
> - `C_rag-graph` (+ S2 graph + S3 preprocessing + S4 citation)
>
> Plus α-5 carryover (free, no rerun):
> - `C_rag-full` (= α-5 L1: full JAMES stack)
> - `C_rag-routed` (= α-5 L5: full JAMES + routing layers)
>
> **Total cells in Phase 1 reading**: 5 (3 new + 2 carryover).

---

## 0. Run metadata

| Field | Value |
|---|---|
| Date | [FILL] |
| Workspace | `workspaces/hotpot_eval/` |
| Suite | `multihop_rag` |
| Fixture | `balanced-100` (25 per question_type) |
| Baseline | `baseline_3a961a3_rescored.json` (path 0.404 / graded 0.343 / abst_f1 0.609) |
| Cells run (new this phase) | C_minus, C_rag-basic, C_rag-graph @ M_M |
| Cells carryover (from α-5) | C_rag-full (= L1), C_rag-routed (= L5) @ M_M |
| Total compute | ~3.3 h (3 new cells × ~66 min) |
| Tier | M_M only (gemma4:e4b, A2 think=OFF) |
| Task ID | `ba3jwm9rt` |

---

## 1. 5-axis Δ table vs baseline

Auto-rendered into the matrix report; copy here:

| Cell | path | graded | abst_f1 | token | latency | Verdict |
|---|---|---|---|---|---|---|
| C_minus | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| C_rag-basic | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| C_rag-graph | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| C_rag-full (= L1) | +0.015 | -0.017 | -0.018 | +74 | +2.3 | reject (n=1 floor) |
| C_rag-routed (= L5) | +0.008 | -0.027 | -0.091 | +55 | +4.7 | reject |

Baseline (for reference): path 0.404 / graded 0.343 / abst_f1 0.609 / token 1150 / latency 64.

---

## 2. Sector-progression Δ (the core narrative)

Cell-to-cell Δ. Each row tells what **the marginal sector added**.

| From → To | Sector added | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ |
|---|---|---|---|---|---|---|
| C_minus → C_rag-basic | + S1 RAG retrieval | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| C_rag-basic → C_rag-cited | + S4 citation | n/a — C_rag-cited skipped | | | | |
| C_rag-basic → C_rag-graph | + S2 graph + S3 preproc (+ S4 citation in this batch) | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| C_rag-graph → C_rag-full | + S5 abstention + S6 cognitive | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| C_rag-full → C_rag-routed | + routing layers | -0.007 | -0.010 | -0.091 | -19 | +2.4 |

**Note on C_rag-cited**: skipped this phase to keep compute to 3 cells (~3.3h). C_rag-graph already includes S4 (citation) so its Δ vs C_rag-basic conflates "graph + preproc + citation" together. A follow-up phase can run C_rag-cited alone to disambiguate S4 from S2.

---

## 3. Predictions vs reality

Predictions from the next-session handover (#662) §"Expected publishable Δ":

| Comparison | Predicted | Observed | Match? |
|---|---|---|---|
| C_minus vs C_rag-basic | quality ↑↑ (retrieval helps) | [FILL] | [FILL] |
| C_rag-basic vs C_rag-graph (incl. S4) | path ↑ (citation), graded ↑ (graph multi-hop) | [FILL] | [FILL] |
| C_rag-graph vs C_rag-full | abst_f1 ↑ (abstention helps null queries), latency ↑ | [FILL] | [FILL] |
| C_rag-full vs C_rag-routed (= α-5 L5 verdict) | inert / mildly regressive | -0.091 abst_f1 (REJECT) ✓ | already in evidence |

[FILL: interpretation prose, 2-3 sentences. Highlight any
surprise — the cycle's discipline is "measure first, frame second."]

---

## 4. Publishable claim (Phase 1)

> **JAMES sector ablation on MultiHop-RAG balanced-100, gemma4:e4b
> production tier (think=OFF, bge-m3)**:
> - Pure gemma4 (no JAMES): path [FILL] / graded [FILL] / abst_f1 [FILL]
> - + chroma RAG retrieval: path [FILL] / graded [FILL] / abst_f1 [FILL]
> - + graph + preprocessing + citation: path [FILL] / graded [FILL] / abst_f1 [FILL]
> - JAMES full stack (= α-5 L1): path 0.419 / graded 0.327 / abst_f1 0.591
> - JAMES + routing layers (= α-5 L5): path 0.412 / graded 0.317 / abst_f1 0.500
>
> [FILL: 1-2 sentence interpretation framing the "does each sector
> add value" answer cleanly. Apply position guard — mother-platform
> framing, not Replayable RAG.]

---

## 5. Verdict per layer (per-layer intent matrix)

Per CLAUDE.md rule 2 layer-intent extension (#652) + memory
`mechanism_layer_intent_axis_alignment`. Each sector judged on its
**design-intent axes**, not uniform Pareto.

| Layer | Design intent | Primary axes | Δ on primary axes | Regression-check axes | Δ on regression axes | Verdict |
|---|---|---|---|---|---|---|
| S1 RAG retrieval | retrieval recall | path + graded | [FILL] | abst_f1 noise check | [FILL] | [FILL] |
| S2 Graph | concept multi-hop | path + graded | [FILL] | cost noise check | [FILL] | [FILL] |
| S3 Preproc | input fluency | path + graded | [FILL] | cost noise check | [FILL] | [FILL] |
| S4 Citation | source surface | path primary | [FILL] | quality flat | [FILL] | [FILL] |
| S5 Abstention | refusal grounding | abst_f1 primary | [FILL] | quality protection | [FILL] | [FILL] |
| S6 Cognitive | multi-step | graded primary | [FILL] | latency cost expected | [FILL] | [FILL] |

[FILL: per-layer reasoning — apply the design-intent matrix, not
uniform 5-axis Pareto. A cost-increase on S6 (cognitive) is
expected; a graded gain redeems it. A quality regression on S5
(abstention) is the bucket-(a) layer-intent mismatch case.]

---

## 6. Next phase decision

| Trigger | Action |
|---|---|
| Phase 1 shows clear sector-additive signal | proceed to Phase 2 (tier-gated check at M_S = gemma3:4b) |
| Phase 1 shows ambiguous / mixed signal | C_rag-cited isolation run first (~110 min) to disambiguate S4 alone |
| Phase 1 shows sectors regressive at production | bucket the result — measurement issue (apply 4-step rule) before changing JAMES |
| Phase 1 shows clear gemma4:e4b best | Phase 3a (gemma3 scale ladder) gains lower priority |

[FILL: which trigger fired + the chosen next action.]

---

## 7. Findings to promote (mechanism candidates)

If any per-cell row shows a surprising Δ direction, log it in
`reports/research-runs/qvt-ablation-findings.md` with bucket tag
and let `scripts/qvt_promote_findings.py` (PR #633) draft a
memory entry.

[FILL: list of finding slugs + bucket attribution, or "no
mechanism candidates surfaced."]

---

## 8. Cross-references

- α-6 design memo: `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md`
- α-6 engineering pre PR sequence: `docs/design/v0.4-alpha-6-engineering-pre-pr-sequence.md`
- Layer-intent matrix: `memory/mechanism_layer_intent_axis_alignment.md`
- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`
- Position guard: `memory/feedback_jameses_positioning_replayable_rag.md` §"정정 2026-05-31"
- α-5 closure (carryover cells): `reports/promo-assets/v0.4-qvt-ablation-matrix-20260531T065209.md` + ROADMAP §v0.4.x
- Predictions source: `docs/handovers/v0.4-next-session-entry-2026-06-01.md` §"Expected publishable Δ predictions"
- Sector flag PRs: #657 (S4) #658 (S2) #659 (S1) #660 (S5) #661 (S6)
- Renderer PR: #664 (sector cells + progression table)
- Matrix runner sector cells: #663
