---
name: finding-multihop-rag-lost-in-middle-at-gemma4-e4b
description: [2026-06-01, bucket-(b)] this matches the published Lost-in-the-Middle
metadata:
  type: project
---

# Finding — multihop-rag-lost-in-middle-at-gemma4-e4b (2026-06-01)

**Bucket**: (b)  
**Tags**: mechanism-candidate

## Source entry (verbatim from `reports/research-runs/qvt-ablation-findings.md`)

- **bucket**: (b) — model-context interaction (well-documented in
  Lost-in-the-Middle / Power-of-Noise literature)
- **cell context**: α-6 Phase 1, C_minus → C_rag-basic transition at
  gemma4:e4b production tier (M_M), MultiHop-RAG balanced-100
- **observation**: adding S1 RAG retrieval to pure gemma4:e4b
  degrades abst_f1 by 0.137 (0.558 → 0.421). Null-query refusal
  count drops from 12/25 (pure LLM) to 8/25 (with RAG context).
  Specifically, the LLM hallucinates ON 4 MORE null queries when
  given irrelevant retrieved context vs no context at all.
- **surprise**: this matches the published Lost-in-the-Middle
  (Liu et al. 2023) + Power-of-Noise (Cuconasu et al. 2024)
  findings. Worth documenting that gemma4:e4b reproduces the
  pattern at production scale on MultiHop-RAG balanced-100. NOT
  JAMES-specific.
- **data pointer**: `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/qvt-ablation-cell-C_minus-M_M.json` +
  `qvt-ablation-cell-C_rag-basic-M_M.json` + analysis at
  `reports/research-runs/alpha-6-phase-1-analysis-20260601.md`
- **follow-up tag**: `mechanism-candidate`
- **probe ideas**: tier-gated check (Phase 2 in flight); does smaller
  gemma3:4b see larger relative degradation?
- **immediate impact on α-6**: framing change — α-6's "does each
  sector help vs vanilla LLM" question reframes: "does each sector
  help vs the LLM-alone-with-no-context baseline?" RAG and graph
  are no longer assumed-positive contributors.

## Promotion provenance

- Auto-drafted by `scripts/qvt_promote_findings.py` on the entry dated 2026-06-01.
- This is a DRAFT memo. Review before adding a line under MEMORY.md.
- If the finding was already resolved by a PR (e.g. `→ RESOLVED (#N)`),
  consider whether the memo should be archived as feedback rather than
  carried as an open mechanism candidate.
