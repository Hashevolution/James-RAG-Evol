---
name: finding-jameses-s5-s6-capability-floor-not-crutch
description: [2026-06-01, bucket-(a)] this REVERSES the original tier-gated routing
metadata:
  type: project
---

# Finding — jameses-s5-s6-capability-floor-not-crutch (2026-06-01)

**Bucket**: (a)  
**Tags**: mechanism-candidate, universal-law

## Source entry (verbatim from `reports/research-runs/qvt-ablation-findings.md`)

- **bucket**: (a) architecture + universal-law candidate
- **cell context**: α-6 Phase 2, M_M vs M_S comparison
- **observation**: at gemma4:e4b (M_M production), JAMES S5+S6
  layers recover +0.129 abst_f1 + +0.054 graded from RAG damage.
  At gemma3:4b (M_S small), the same layers produce **0.000**
  abst_f1 recovery and **degrade** graded by 0.070. The layers are
  mechanically engaged in both cells but produce measurable
  improvement only above a model-capacity floor.
- **surprise**: this REVERSES the original tier-gated routing
  hypothesis (small models gain more). The smaller model gains
  *less* — or actively loses ground.
- **data pointer**: Phase 2 analysis
  `reports/research-runs/alpha-6-phase-2-analysis-20260601.md`
- **follow-up tag**: `mechanism-candidate` + `universal-law`
- **probe ideas**: Phase 3a gemma3 scale ladder (1b / 4b / 12b /
  27b) to localize the capability floor; cross-family at qwen / llama / deepseek
- **immediate impact on α-6**: publishable framing — JAMES
  abstention layers are a *capability amplifier*, NOT a
  *small-model crutch*. The routing policy at M_S becomes "S4
  citation only; skip S5+S6 to save the 8.4× latency tax."

## Promotion provenance

- Auto-drafted by `scripts/qvt_promote_findings.py` on the entry dated 2026-06-01.
- This is a DRAFT memo. Review before adding a line under MEMORY.md.
- If the finding was already resolved by a PR (e.g. `→ RESOLVED (#N)`),
  consider whether the memo should be archived as feedback rather than
  carried as an open mechanism candidate.
