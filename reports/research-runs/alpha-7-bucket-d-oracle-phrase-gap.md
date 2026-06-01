# α-7 Bucket-(d) Sub-Finding — Oracle Phrase Coverage Gap

> **Status**: pre-PR draft. Targets α-7 cycle as a sub-finding (one
> phrase addition to `_ABSTENTION_PHRASES`). Cycle-scoped because
> it accompanies the graph top-K fix at the measurement-side
> hygiene layer.
> **Trigger**: α-6 Phase 3a cross-tier audit (2026-06-01 PM) using
> `scripts/research/audit_12b_null_query_refusal_shape.py` across 4
> gemma3 scales.

---

## 0. TL;DR

Audited 100 null queries (25 each at 1b/4b/12b/27b C_minus) for
refusal-shape answers the oracle classifies as FN. Result: **1
missed pattern across 100 answers (1%)** — gemma3:12b's
`"data ... doesn't explicitly link"` formulation.

This is **far below** α-5's #619 add scale (10 phrases for
gemma4:e4b grounding refusals) — the gemma3 family does not have
a different refusal vocabulary; it mostly just doesn't refuse at
all (at 1b/4b/12b scale) or refuses with already-covered phrases
(at 27b).

**Recommended action**: narrow phrase add (2 patterns) as
sub-commit within α-7 PR. Magnitude-small, framing-significant
(12b "dip" → "plateau" reframe).

---

## 1. Audit method

Script: `scripts/research/audit_12b_null_query_refusal_shape.py`

For each tier's C_minus bench JSON:
1. Load oracle's `_ABSTENTION_PHRASES` set (eval/qvt/oracle.py)
2. Split 25 null queries into oracle-TP (refusal detected) vs
   oracle-FN (no refusal detected)
3. Apply a wider refusal-shape regex panel to the oracle-FN set
4. Report any patterns the oracle would benefit from adding

Limitation: audit operates on `answer_preview` (truncated to ~1000-
2000 chars). The oracle scores the full answer text. The 4b cell
shows TP=2 in aggregate vs TP=1 in audit — small discrepancy
attributable to truncated preview. Qualitative conclusions unchanged.

---

## 2. Cross-tier audit results

| Tier | Oracle TP | Oracle FN | Audit-found missed | Notes |
|---|---:|---:|---:|---|
| M_XS (1b) | 0 | 25 | **0** | model too small to attempt refusal; 25/25 true hallucinations |
| M_S (4b) | 1 (audit) / 2 (cell) | 24 / 23 | **0** | weak refusal attempts when present use already-covered phrases (e.g. "None of the provided") |
| M_L (12b) | 0 | 25 | **1** | id=58 uses `"data ... doesn't explicitly link"` — not in oracle |
| M_XL (27b) | 4 | 21 | **0** | 4 TPs use covered phrases (`without direct access to`, `unable to answer`, `Source files: None provided`). 21 FN are all genuine hallucinations |

**Total**: 1 missed pattern / 100 audited answers = 1% phrase gap.

---

## 3. Patterns to add (narrow scope)

Per α-5 #619 lesson — narrow phrases that appear ONLY in unhedged
refusal positions, never in partial-answer rows:

| Pattern (regex) | Caught at | Justification narrow? |
|---|---|---|
| `\b(data|information)\s+(provided\s+)?doesn'?t\s+(explicitly\s+)?link` | M_L id=58 | ✅ "data doesn't link" only appears as unhedged refusal; partial-answer rows say "data shows X" not "data doesn't link" |
| `\b(data|information)\s+(provided\s+)?does\s+not\s+(explicitly\s+)?link` | (variant of above) | ✅ same |

⚠️ **Patterns explicitly rejected** (would FP-flood partial-answer
rows):
- ❌ `doesn't (have|contain|cover)` — too broad; appears in partial
  answers like "the article doesn't have the exact figure but says X"
- ❌ `not (clear|specific|certain)` — too broad; soft hedges
- ❌ `unclear|ambiguous` — appears in genuinely confident answers
  like "Apple's stance is unclear here, but the article reports..."

The added patterns must contain "link" specifically — a low-frequency
verb in this corpus that only appears in refusal contexts.

---

## 4. Implementation sketch

```python
# eval/qvt/oracle.py — append to _ABSTENTION_PHRASES tuple:
    # α-7 sub-finding 2026-06-01 — gemma3:12b refusal style.
    # Caught 1/100 audited null-query answers across gemma3 ladder.
    # Narrow on purpose (only "doesn't link" with data/information
    # subject) — broader patterns FP-flood per α-5 #619 lesson.
    "data doesn't link",
    "data does not link",
    "data doesn't explicitly link",
    "data does not explicitly link",
    "information doesn't link",
    "information does not link",
```

Or alternatively as a regex pattern in `detect_abstention()` for
broader coverage of `doesn't ... link` variants.

---

## 5. Quality Delta (re-score on the bench JSONs)

Re-score impact (oracle phrase add only, no re-bench):

| Tier | Current oracle abst_f1 | After phrase add | Δ |
|---|---:|---:|---:|
| M_XS (1b) | 0.000 | 0.000 | 0 |
| M_S (4b) | 0.074 | 0.074 | 0 |
| M_L (12b) | 0.000 | ~0.077 | **+0.077** |
| M_XL (27b) | 0.258 | 0.258 | 0 |

Only 12b shifts. The reframe ("dip" → "plateau") was already
made in the recovery curve doc §5 + 12b doc §3.1 ahead of the
phrase add (publish-the-honest-number-first discipline).

---

## 6. Scope decision

Two options:

**Option A — Bundle into α-7 PR** (recommended)
- One commit "fix(α-7): oracle phrase coverage gap (gemma3:12b refusal style)"
- Lives alongside the graph top-K fix; same cycle, same re-baseline
- Pro: one closure cycle, less PR overhead
- Con: muddies α-7's "graph fix" theme

**Option B — Standalone bucket-(d) PR**
- One small PR before α-7 cycle proper
- Pro: clean separation of concerns
- Con: requires its own PR + review

Recommendation: **Option A**. The 12b plateau finding's publishable
framing already incorporates this; bundling keeps closure simple.

---

## 7. References

- Source script: `scripts/research/audit_12b_null_query_refusal_shape.py`
- Source bench files:
  - 1b: `reports/bench_52c13cf_multihop_rag_20260601_113431.json`
  - 4b: `reports/bench_5a783c6_multihop_rag_20260601_095355.json`
  - 12b: `reports/bench_ac9670d_multihop_rag_20260601_115524.json`
  - 27b: `reports/bench_4a5a60c_multihop_rag_20260601_154320.json`
- Recovery curve doc §3.1 (reframe): `reports/research-runs/alpha-6-phase-3a-recovery-curve-20260601.md`
- 12b doc §3.1 (audit appendix): `reports/research-runs/alpha-6-phase-3a-gemma3-12b-analysis-20260601.md`
- Oracle phrase list: `eval/qvt/oracle.py:_ABSTENTION_PHRASES`
- α-5 #619 precedent (narrow phrase add): commit history
- α-7 design memo: `docs/design/v0.4-alpha-7-graph-topk.md`
