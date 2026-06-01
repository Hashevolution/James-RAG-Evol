---
name: finding-tier-conditional-rag-helps-small-hurts-large
description: [2026-06-01, bucket-(b)] Lost-in-the-Middle is conditional on model capacity.
metadata:
  type: project
---

# Finding — tier-conditional-rag-helps-small-hurts-large (2026-06-01)

**Bucket**: (b)  
**Tags**: mechanism-candidate

## Source entry (verbatim from `reports/research-runs/qvt-ablation-findings.md`)

- **bucket**: (b) model-context interaction
- **cell context**: α-6 Phase 1 + 2, C_minus → C_rag-basic transition
  at both M_M and M_S tiers
- **observation**: adding RAG retrieval to pure LLM yields **opposite**
  Δ on graded by tier:
  - M_M (gemma4:e4b): graded **-0.020** (Lost in the Middle)
  - M_S (gemma3:4b): graded **+0.043** (RAG compensates for
    weaker parametric knowledge)
- **surprise**: Lost-in-the-Middle is conditional on model capacity.
  Below the capability threshold, RAG context is genuinely
  informative; above it, RAG context becomes a distractor.
- **data pointer**: Phase 1 analysis (M_M) + Phase 2 analysis (M_S)
- **follow-up tag**: `mechanism-candidate`
- **probe ideas**: Phase 3a scale ladder to find the inversion
  point; Phase 3b cross-family to test family-specific inversion
- **immediate impact on α-6**: routing policy must be tier-aware.
  M_S → keep RAG on; M_M → RAG ON only with abstention layer to
  recover damage.

## Promotion provenance

- Auto-drafted by `scripts/qvt_promote_findings.py` on the entry dated 2026-06-01.
- This is a DRAFT memo. Review before adding a line under MEMORY.md.
- If the finding was already resolved by a PR (e.g. `→ RESOLVED (#N)`),
  consider whether the memo should be archived as feedback rather than
  carried as an open mechanism candidate.
