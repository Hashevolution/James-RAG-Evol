---
name: finding-jameses-s5-s6-recover-rag-damage
description: [2026-06-01, bucket-(a)] this is the measurable JAMES contribution at
metadata:
  type: project
---

# Finding — jameses-s5-s6-recover-rag-damage (2026-06-01)

**Bucket**: (a)  
**Tags**: mechanism-candidate, universal-law

## Source entry (verbatim from `reports/research-runs/qvt-ablation-findings.md`)

- **bucket**: (a) — architecture-as-designed; mechanism candidate
- **cell context**: α-6 Phase 1, C_rag-graph → C_rag-full transition
  at gemma4:e4b production tier (M_M)
- **observation**: enabling S5 abstention + S6 cognitive stages
  on top of S1+S2+S3+S4 recovers graded_answer by +0.054 (0.273 →
  0.327) AND abst_f1 by +0.129 (0.462 → 0.591). The recovery
  brings abst_f1 ABOVE the pure-LLM baseline (0.591 vs 0.558).
- **surprise**: this is the measurable JAMES contribution at
  production tier. S5+S6 are doing the heaviest semantic work in
  the stack — exactly the "abstention softener" mechanism the
  layer was designed for. Latency tax: +37s/query (~5.5× total
  over pure LLM).
- **data pointer**: same as above + α-5 L1 cell as C_rag-full
- **follow-up tag**: `mechanism-candidate` + `universal-law`
  (preliminary — Phase 2/3 confirms or restricts to gemma4)
- **probe ideas**:
  1. Phase 2 (M_S = gemma3:4b) tier-gated check
  2. Phase 3a (gemma3 scale ladder) — does recovery magnitude
     scale with model size?
  3. Phase 3b (cross-family qwen/llama/deepseek) — is the recovery
     JAMES-architecture-specific or universal RAG mitigation?
- **immediate impact on α-6**: this is the publishable JAMES
  contribution at production tier on MultiHop-RAG. Phase 2 tests
  whether the pattern is model-invariant.

## Promotion provenance

- Auto-drafted by `scripts/qvt_promote_findings.py` on the entry dated 2026-06-01.
- This is a DRAFT memo. Review before adding a line under MEMORY.md.
- If the finding was already resolved by a PR (e.g. `→ RESOLVED (#N)`),
  consider whether the memo should be archived as feedback rather than
  carried as an open mechanism candidate.
