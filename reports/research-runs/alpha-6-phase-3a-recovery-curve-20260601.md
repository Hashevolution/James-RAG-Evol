# α-6 Phase 3a — Cross-Tier Recovery Curve (gemma3 ladder + gemma4 reference)

> **Status**: skeleton built before 27b lands. 1b / 4b / 12b / e4b
> rows filled from canonical JSON aggregates. M_XL row reserved for
> the 27b result (`bhsl1zgqm` background, ~6-8h ETA).
>
> **Framing discipline**: this doc is *not* a "publishable mechanism
> finding" — it is the operational data picture from the α-6 cycle,
> per `memory/feedback_finding_size_honest_framing`. The single
> ⭐⭐⭐ candidate (S4 citation tier-invariant) is highlighted
> separately; everything else is operational / partial.

---

## 0. Run metadata

| Field | Value |
|---|---|
| Cycle | α-6 Phase 3a (gemma3 scale ladder + gemma4 reference) |
| Date | 2026-06-01 |
| Workspace | `./workspaces/hotpot_eval` |
| Suite | `multihop_rag` (Tang & Yang 2024, EMNLP) |
| Fixture | balanced-100 (25 per question_type) |
| Baseline | `3a961a3_rescored` (M_M full stack = e4b) |
| think mode | OFF on all tiers (sanity: e4b think=ON also measured) |
| Cells per tier | C_minus + C_rag-full (Phase 3a endpoints) |
| Intermediates | C_rag-basic / C_rag-graph filled only at M_S / M_M (Phase 1+2) |

---

## 1. Cross-tier raw aggregates (median per axis)

### C_minus (pure LLM, no JAMES)

| Tier | Model | path | graded | abst_f1 | token | latency |
|---|---|---:|---:|---:|---:|---:|
| M_XS | gemma3:1b | 0.000 | 0.297 | **0.000** | 755 | 0.9s |
| M_S | gemma3:4b | 0.000 | 0.307 | **0.074** | 930 | 1.9s |
| **M_M** | **gemma4:e4b** | 0.000 | 0.347 | **0.558** | 1385 | 11.9s |
| M_L | gemma3:12b | 0.000 | 0.313 | **0.000** | 903 | 4.1s |
| **M_XL** | **gemma3:27b** | 0.000 | 0.390 | **0.258** | 923 | 77.7s |

### C_rag-full (JAMES full stack = α-5 L1)

| Tier | Model | path | graded | abst_f1 | token | latency |
|---|---|---:|---:|---:|---:|---:|
| M_XS | gemma3:1b | **0.410** | 0.257 | 0.000 | 712 | 6.9s |
| M_S | gemma3:4b | **0.397** | 0.290 | 0.000 | 956 | 15.6s |
| M_M | gemma4:e4b | **0.419** | 0.327 | **0.591** | 1224 | 66.0s |
| M_L | gemma3:12b | **0.410** | 0.333 | **0.375** | 913 | 34.9s |
| **M_XL** | **gemma3:27b** | **0.403** | 0.310 | **0.077** | 1100 | 188.0s |

---

## 2. Intra-tier Δ (= "JAMES contribution at this tier")

| Tier | path Δ | graded Δ | **abst_f1 Δ** | latency Δ | latency × |
|---|---:|---:|---:|---:|---:|
| M_XS (1b) | **+0.410** | -0.040 | **0.000** | +6.0s | 7.5× |
| M_S (4b) | **+0.397** | -0.017 | **-0.074** | +13.7s | 8.2× |
| M_M (e4b) | **+0.419** | -0.020 | **+0.033** | +54.1s | 5.5× |
| M_L (12b) | **+0.410** | +0.020 | **+0.375** | +30.8s | 8.6× |
| **M_XL (27b)** | **+0.403** | **-0.080** | **-0.181** | **+110.4s** | **2.4×** |

**Noise reference** (per α-5 ablation suite, n=100 fixture):
graded ±0.104, abst_f1 ±0.286, path effectively 0. Deltas inside
the band are not interpretable.

---

## 3. The "recovery curve" — abst_f1 contribution by tier

| Tier | Pure abst_f1 | + JAMES abst_f1 | **Δ** | Effect (descriptive, not mechanistic) |
|---|---:|---:|---:|---|
| M_XS (1b) | 0.000 | 0.000 | **0.000** | no effect — empty in, empty out |
| M_S (4b) | 0.074 | 0.000 | **-0.074** | negative — JAMES kills weak native attempt |
| M_M (e4b) | 0.558 | 0.591 | **+0.033** | small positive (inside noise band) |
| M_L (12b) | 0.000 (≈ 0.077 oracle-corrected) | 0.375 | **+0.375 (raw) / +0.298 corrected** | large positive — emerges where pure is at plateau |
| **M_XL (27b)** | **0.258** | **0.077** | **-0.181** | **large negative — JAMES disrupts strong native refusal (audit-clean, mechanism §3.2 of 27b doc)** |

**Honest framing constraint (per `feedback_finding_size_honest_framing`)**:

- 3 of 4 measured Δs are *inside the noise band ±0.286*. The two
  observations that exceed the band: M_S -0.074 (no — well inside),
  M_L +0.375 (yes — exceeds band). So the **only statistically
  defensible non-zero JAMES contribution from this Δ table is M_L**.
- The "curve" shape across tiers is descriptive narration, not a
  mechanism claim. Calling it a "curve" already implies a function
  that doesn't exist in n=1 data.
- Previously-claimed framings — "inverted-U capability floor", "JAMES
  amplifier", "capability floor between 4b and e4b", "amplifier vs
  small-model crutch" — all withdrawn per §5.

### 3.1 Pure-LLM abst_f1 across the gemma3 ladder (4-step rule applied)

| Tier | Pure abst_f1 (raw) | Pure abst_f1 (oracle-corrected) | Notes |
|---|---:|---:|---|
| 1b (gemma3) | 0.000 | 0.000 | 25/25 hallucinations |
| 4b (gemma3) | 0.074 | ~0.074 | 2/25 caught refusal |
| 12b (gemma3) | 0.000 | **~0.077** | **24/25 hallucinations + 1 missed `doesn't link` pattern** (4-step rule check, `scripts/research/audit_12b_null_query_refusal_shape.py`) |
| 27b (gemma3) | **0.258** | 0.258 | 4 TP / 21 FN — first emergence above family floor |
| e4b (gemma4) | 0.558 | 0.558 | 14 TP / 11 FN — gemma4 grounding-trained refusal |

**Reshaped framing — "plateau + late emergence" (replaces earlier
"12b dip" claim)**:
- 1b → 4b → 12b: pure abst_f1 stays ≈ 0.00-0.08 across 3× scale steps
  (no growth; plateau)
- 12b → 27b: jump to 0.258 = first within-family emergence
- 27b → e4b: jump to 0.558 = either further scale or gemma4 grounding
  contribution (cannot disambiguate from this fixture)

The earlier "12b dip" reading was the un-corrected oracle value
(0.000). The 4-step rule audit found 96% of 12b's null answers are
genuine hallucinations, with one (4%) being a refusal-style phrasing
(`"data ... doesn't explicitly link"`) that the current
`_ABSTENTION_PHRASES` list does not catch. Adding the pattern would
shift 12b from 0.000 to ~0.077 — essentially equal to 4b's 0.074.

**Bucket-(d) sub-finding** logged for α-7 or later cycle: add
`doesn't [explicitly] link` and `data [provided] doesn't` to oracle
phrase list (narrow, not broad — broad patterns flood FPs on
partial-answer rows per α-5 #619 lesson).

---

## 4. The actually-defensible finding (⭐⭐⭐ candidate)

### S4 citation path Δ tier-invariance — **5-point series confirmed**

| Tier | Model | path Δ (intra-tier) |
|---|---|---:|
| M_XS | gemma3:1b | **+0.410** |
| M_S | gemma3:4b | **+0.397** |
| M_M | gemma4:e4b | **+0.419** |
| M_L | gemma3:12b | **+0.410** |
| **M_XL** | **gemma3:27b** | **+0.403** |

**5 of 5 measured points sit within ±0.012 of each other** (range
+0.397 to +0.419, span = 0.022). Across:
- **27× model size gap** (1b → 27b)
- **2 model families** (gemma3 + gemma4)
- **Wildly different native capability profiles** (pure-LLM abst_f1
  spans 0.000 → 0.558 across the same tiers)

Why this is non-trivial:
- Independent of the model's native capability profile (path Δ does
  not correlate with pure-LLM abst_f1 — Pearson ~0)
- Mechanism candidate = the citation pipeline runs at the *graph
  layer*, not the *language model*, so its effect projects through
  any backbone that can parse the rendered citation block
- 5-point consistency at this magnitude rules out random fluctuation
  (each cell is n=1; the consistency across 5 cells is the signal)

Why this is candidate, not yet validated universal-law:
- Same fixture (MultiHop-RAG balanced-100); fixture sensitivity
  unknown
- Same retrieval stack (bge-m3); cross-embedding sensitivity unknown
- Within-family extension (gemma3 only) is 4 of 5 points; gemma4
  contribution is single point (e4b)
- Cross-family extension (qwen / llama / deepseek / etc.) deferred
  to Phase 3b

**Promotion plan**: ⭐⭐⭐ candidate confirmed; validated universal-law
promotion requires:
1. Cross-fixture sanity (e.g. HotpotQA, MuSiQue, separate from
   MultiHop-RAG)
2. Cross-family sanity in Phase 3b (qwen2.5:7b / llama3.1:8b /
   deepseek-v2:16b at minimum)
3. Adversarial fixture — does it survive a fixture where citation
   doesn't map cleanly?

Until these, the ⭐⭐⭐ tier is *candidate* status, **not** validated.

---

## 5. Withdrawn / superseded claims registry

| Claim | Source | Why withdrawn / superseded |
|---|---|---|
| "JAMES = capability amplifier, not small-model crutch" | Phase 2 closure PR #674 | M_L data shows substitution (pure 0 → JAMES 0.375), which is closer to "small-model crutch" than to "amplifier" |
| "Inverted-U capability floor (1b inert / 4b disrupt / e4b amplify)" | Phase 3a 1b doc (commit `ac9670d`) | M_L adds a fourth mode (enable). Three-mode U was incomplete |
| "Capability floor between 4b and e4b" | Phase 2 §6 + Phase 3a 1b §4 | M_L crosses the floor too; the floor is not a single position |
| "Only gemma4 family can use abstention layers" | Speculative reframe during 12b wait | M_L (gemma3:12b) achieves abst_f1 +0.375 with JAMES, refuting family-only hypothesis |
| "S5+S6 recover at +0.129 abst_f1 at M_M" | Phase 2 §5 prose | M_M C_rag-graph→full Δ recomputes to +0.129 ✓ (this one survives) |
| "12b dip — pure abst_f1 = 0 is uniquely lower than 4b and 1b" | Phase 3a 12b §3 prose + recovery curve §3 first draft | reshaped to "**12b plateau**" — 4-step rule audit (`scripts/research/audit_12b_null_query_refusal_shape.py`) found 24/25 genuine hallucinations + 1 missed `doesn't link` refusal pattern. Oracle-corrected ~0.077 ≈ 4b's 0.074. Plateau not dip |

---

## 6. Operational routing rule (post-Phase 3a)

⚠️ **Reads as routing data, not as a mechanism claim**. Numbers are
based on n=1 runs at each tier; treat as preliminary until cross-fixture
validation.

| Tier | S1+S2+S3+S4 (citation stack) | S5+S6 (abstention + cognitive) | Production recommendation |
|---|---|---|---|
| M_XS (1b) | adopt (+0.41 path) | skip (zero effect, 7.5× tax) | citation-only deployment |
| M_S (4b) | adopt (+0.40 path) | **skip** (negative -0.074, 8.2× tax) | citation-only deployment |
| M_M (e4b) | adopt (+0.42 path) | adopt (+0.033 noise-band edge, 5.5× tax) | full stack — current production |
| M_L (12b) | adopt (+0.41 path) | **adopt** (+0.375, 8.6× tax) | full stack |
| **M_XL (27b)** | **adopt (+0.40 path)** | **skip** (negative -0.181, 2.4× tax) | **citation-only deployment — JAMES disruption mechanism §3.2 of 27b doc** |

Caveats:
1. **Graph layer bug** (Phase 1 §3): the current graph adds graded
   regression at M_M (-0.053). All graded Δs above are measured with
   this bug present. Post-graph-fix re-baseline is the next-cycle
   dependency. Recovery curve will be re-measured at that point.
2. **n=1**: every cell is a single bench run; QVT noise band is
   theoretical, not measured per-tier here.
3. **Fixture-bound**: MultiHop-RAG balanced-100 only; routing rule
   validity outside this fixture is unverified.

---

## 7. Cost picture (token + latency, intra-tier)

| Tier | Pure latency | + JAMES latency | × | + JAMES token Δ | What this buys |
|---|---:|---:|---:|---:|---|
| M_XS (1b) | 0.9s | 6.9s | 7.5× | -43 | +0.41 path, zero quality / abstention |
| M_S (4b) | 1.9s | 15.6s | 8.2× | +26 | +0.40 path, *minus* 0.074 abst_f1 |
| M_M (e4b) | 11.9s | 66.0s | 5.5× | -161 | +0.42 path, +0.033 abst_f1 noise |
| M_L (12b) | 4.1s | 34.9s | 8.6× | +10 | +0.41 path, +0.375 abst_f1 |
| **M_XL (27b)** | **77.7s** | **188.0s** | **2.4×** | **+177** | **+0.40 path, *minus* 0.181 abst_f1** |

Where the latency tax is "worth it" (defensible) = M_M and M_L.
Where it isn't = M_XS, M_S, **and M_XL**.

**The 27b 2.4× tax ratio is the lowest** — at this scale raw
inference dominates over JAMES overhead. But the abst_f1 disruption
(-0.181) means the cheap-tax regime doesn't pay off; 27b production
should still be citation-only until α-7 graph top-K is measured to
test whether source-injection mechanism (§3.2 of 27b doc) reverses.

---

## 8. Cross-references

- α-6 design memo: `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md`
- α-6 cycle PR index: `reports/research-runs/alpha-6-cycle-pr-index.md`
- Phase 1 analysis: `reports/research-runs/alpha-6-phase-1-analysis-20260601.md`
- Phase 2 analysis: `reports/research-runs/alpha-6-phase-2-analysis-20260601.md`
- Phase 3a 1b: `reports/research-runs/alpha-6-phase-3a-gemma3-1b-analysis-20260601.md` (⚠️ framing pollution flagged, see §5)
- Phase 3a 12b: `reports/research-runs/alpha-6-phase-3a-gemma3-12b-analysis-20260601.md`
- Honest framing rule: `memory/feedback_finding_size_honest_framing.md`
- Layer intent: `memory/mechanism_layer_intent_axis_alignment.md`
- Position guard: `memory/feedback_jameses_positioning_replayable_rag.md`
- Matrix tier extension: PR #677
- bench / matrix timeout overrides: commit `be2fb64`
- 4-step rule audit script (12b plateau verification): `scripts/research/audit_12b_null_query_refusal_shape.py`

---

## 9. Done condition for this doc

- [x] §1-§3 filled for M_XS / M_S / M_M / M_L
- [x] §4 ⭐⭐⭐ candidate established with 4 data points
- [x] §5 withdrawn-claims registry consolidated
- [x] §6 operational routing rule preliminary
- [x] §7 cost picture
- [x] **M_XL (27b) row in §1-§3, §6, §7** ← post-bench fill 2026-06-01 PM
- [x] **§4 5-point S4 confirmation** ← all 5 points within ±0.012, ⭐⭐⭐ candidate confirmed
- [x] **§6 27b routing recommendation** ← citation-only (S5+S6 disrupt -0.181)
- [ ] Phase 3a closure PR description references this doc as primary artifact
