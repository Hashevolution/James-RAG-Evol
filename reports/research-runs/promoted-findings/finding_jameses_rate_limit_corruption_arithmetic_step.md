---
name: finding-jameses-rate-limit-corruption-arithmetic-step
description: [2026-06-01, bucket-(a)] the corrupted scores looked plausible. They
metadata:
  type: project
---

# Finding — jameses-rate-limit-corruption-arithmetic-step (2026-06-01)

**Bucket**: (a)  
**Tags**: (the, is, lesson, mechanism-candidate, the

## Source entry (verbatim from `reports/research-runs/qvt-ablation-findings.md`)

- **bucket**: (a) measurement-side wiring + mechanism-candidate
- **cell context**: α-6 Phase 2 C_minus/M_S first run (corrupted)
- **observation**: server's per-IP rate limiter (30 req / 60 s)
  silently corrupted a cell whose model responded in sub-2s/query.
  70/100 queries got 429s; bench treated empty answers as
  abstentions; oracle computed apparent abst_f1 = 0.521 from what
  was actually rate-limit errors.
- **surprise**: the corrupted scores looked plausible. They
  fabricated "valid" abstention behavior. The catch was the
  **arithmetic step** of the 4-step rule: cell wall-clock 53s vs
  latency 1.71s × 100 = 171s expected. The math didn't add up.
- **data pointer**: post-mortem at
  `reports/research-runs/alpha-6-phase-2-rate-limit-corruption-postmortem-2026-06-01.md` (#671);
  fix at #672
- **follow-up tag**: `mechanism-candidate` (the lesson is the
  arithmetic step itself, not the specific bug)
- **probe ideas**: extend the 4-step rule's memory entry with the
  arithmetic step as a worked example
- **immediate impact on α-6**: cycle wrong-fix-averted count went
  from 7 to 8; the arithmetic step is the new fast catch for
  silent corruption. Future bench runs at sub-1s/query (Phase 3a
  gemma3:1b) would have corrupted entirely without this catch.

## Promotion provenance

- Auto-drafted by `scripts/qvt_promote_findings.py` on the entry dated 2026-06-01.
- This is a DRAFT memo. Review before adding a line under MEMORY.md.
- If the finding was already resolved by a PR (e.g. `→ RESOLVED (#N)`),
  consider whether the memo should be archived as feedback rather than
  carried as an open mechanism candidate.
