# V3'.e Direction 3 — Cross-family / cross-generation final analysis

**Date**: 2026-05-29 evening session + 2026-05-30 lower-cap closure
**Status**: 🔒 **Internal consolidated — sharing decision deferred to operator**
**Trigger**: handover §5 M3 (Direction 3, user-deferred earlier) + §5 M11 (arxiv:2605.09104 prior art finding); 2026-05-30 follow-up closes §11 Limitation 1 cap-range sub-gap
**Drivers**: `scripts/research/v3prime_e_mode_split.py` (`--model` flag), `v3prime_planner.py`, `v3prime_reflect.py`, `v3prime_verify.py`; four single-purpose copies (`v3prime_e_mode_split_complex.py`, `v3prime_e_mode_split_cap200.py`, `v3prime_e_mode_split_cap50_100.py`, `v3prime_e4b_cap4096_audit.py`) for fixture / cap variants
**Total trials**: ~1960 across 7 models × multiple fixtures × multiple caps × n=10 (n=20 for boundary reproducibility, n=50 for e4b cap=4096 natural-budget audit)
**Headline**: H1 (checkpoint-isolated cap-floor on `gemma4:e4b`) **CONFIRMED** by the 7-model panel. **Mechanism RESOLVED 2026-05-30 (§16)**: the floor is the `gemma4:e4b` **thinking trace** (a default-on reasoning phase, ~85% of generated tokens, hidden from the `response` stream) consuming the `num_predict` budget — **not** verbosity (§7/§15.6) and **not** keyword positioning (§15.5). think=false collapses eval_count from ~400 to ~45 and removes the floor. The §15 "verbosity / 5-10× token-tax / position-fraction" framings are superseded by §16; H1 itself stands and is now mechanistically explained.

This doc supersedes the partial `v3prime-cross-family-step1-2026-05-29.md` landed earlier (#599). That partial Step 1 record stays for the diagnostic chain but the headline findings here are the load-bearing read.

## 1. Question framing

Direction 3 was meant to extend V3'.a~e (originally measured on `gemma4:e4b` only) to a cross-family / cross-generation panel, in the context of:

- handover §3 Robin/Ali "three deployment contexts, two architectures, single mechanism" narrative
- arxiv:2605.09104 (Yang et al. 2026) CES production framework with M_int (internal reasoning) and M_ext (external tools) as substitutable factors — framework only, no empirical cross-family fit yet
- The pre-existing measurement gap between V3'.a~d (cognitive prompts, Korean, deterministic 0/10 floor on `gemma4:e4b` at cap=400) and V3'.e (e-commerce synthesis, English, ~65-70% soft boundary on the same model)

Three working hypotheses about the cap-floor:

| H | Claim |
|---|---|
| H1 | Checkpoint-specific — only `gemma4:e4b` exhibits the floor |
| H2 | Fixture-complexity dependent — any sufficiently hard prompt elicits the floor regardless of model |
| H3 | Cognitive-task-domain dependent — Korean cognitive prompts produce the floor regardless of model |

## 2. Models tested

| Family | Model | Scale |
|---|---|---|
| Gemma 4 | `gemma4:e4b` (baseline) | 4B |
| Gemma 3 | `gemma3:12b` | 12B |
| Gemma 2 | `gemma2:2b` | 2B |
| Qwen 2.5 | `qwen2.5:7b` (general) | 7B |
| Qwen 2.5 | `qwen2.5-coder:7b` (coder variant) | 7B |
| Llama 3.1 | `llama3.1:8b` | 8B |
| DeepSeek-v2 | `deepseek-v2:16b` | 16B |

5 distinct families, scale range 2B–16B (4× spread).

## 3. Phase summary

| Phase | Variant | Models | Conditions | Result file pattern |
|---|---|---|---|---|
| **Step 1** | V3'.e basic, temp=0.2, n=10 | 4 (installed) | sub/syn × cap=400/4096 | `T12414*–T12445*.json` |
| **Step 2** | V3'.e basic, temp=0.2, n=10 | 3 (newly pulled) | sub/syn × cap=400/4096 | `T13021*–T13032*.json` |
| **A** | V3'.e basic, temp=0.2, **n=20** | `gemma4:e4b` only | sub/syn × cap=400/4096 (reproducibility) | `T131130.json` |
| **C** | V3'.e basic, **temp=0.7**, n=10 | 7 (all) | sub/syn × cap=400/4096 | `T13150*–T13200*.json` |
| **B-orig** | V3'.e **complex** synthesis (2-item), temp=0.2, n=10 | 7 (all) | sub/syn × cap=400/4096 | `T13235*–T13313*.json` |
| **B-revised** | V3'.b/.c/.d (planner/reflect/verify, **Korean cognitive**), temp=0.2, n=10 | 6 (excl. baseline) | cap=400/4096 | `v3prime-planner-*`, `v3prime-reflect-*`, `v3prime-verify-*` |
| **Option A (cap=200)** | V3'.e basic, temp=0.2, n=10, **cap=200** | 7 (all) | sub/syn × cap=200/4096 | `T14471*–T14515*.json` |

All trials cleanly completed (no Ollama errors, no timeouts).

## 4. Substitution mode — cross-family universal byte-identical retrieval

All 7 models / 5 families / both caps / both temperatures: 10/10 success + 1/10 unique (response_sha256 collapses to a single bucket per cell).

This replicates Robin Converse's 2026-05-23 issue #448 Finding 1 ("40/40 → 1 unique on 26b substitution") across:

- Gemma 4 / 3 / 2 (3 generations, same family)
- Qwen 2.5 general + coder (2 checkpoints, same family)
- Llama 3.1, DeepSeek-v2 (2 cross-family architectures)

**Substitution mode is an architectural primitive that holds across family, generation, scale, and temperature.** No model in the panel deviates.

| Substitution `eval_count` (token usage) at cap=400, temp=0.2 |   |
|---|---|
| `gemma4:e4b` | 62 tokens |
| `gemma3:12b` | 62 |
| `gemma2:2b` | 63 |
| `qwen2.5-coder:7b` | 59 |
| `qwen2.5:7b` | 59 |
| `llama3.1:8b` | 58 |
| `deepseek-v2:16b` | **4** ⚠️ (single-token outlier — see §9) |

Excluding the DeepSeek outlier (which still yields 10/10 success but emits substantially less), the substitution-mode reasoning budget converges to ~58-63 tokens across 4 families / 6 checkpoints. The fixture (English e-commerce policy quoted verbatim) appears to be a near-deterministic copy task at this prompt shape.

## 5. Synthesis mode — checkpoint-isolated floor on `gemma4:e4b`

### 5.1 V3'.e basic (single-item e-commerce, English) — `gemma4:e4b` boundary

`gemma4:e4b` syn @ cap=400 success rate across all measurements:

| Measurement | n | success | rate |
|---|---|---|---|
| 5/23 #1 (archive) | 10 | 4/10 | 40% |
| 5/23 #2 (archive) | 20 | 14/20 | 70% |
| 5/23 #3 (archive) | 20 | 15/20 | 75% |
| 5/29 Step 1 | 10 | 8/10 | 80% |
| 5/29 A (n=20) | 20 | 14/20 | 70% |
| 5/29 C (temp=0.7) | 10 | 4/10 | 40% |
| **Total** | **90** | **59/90** | **66%** |

Soft boundary, noisy across runs. The 80% Step 1 reading is the upper tail; the long-run estimate is ~65-70%. Higher temperature (0.7) drops the success rate noticeably (40%) — the floor is temperature-modulated, not temperature-independent.

Cross-family on the same fixture: all other 6 models hit **10/10** at cap=400 (temp=0.2 and temp=0.7), with median `eval_count` 46-95 tokens — they finish well below the cap and stop on their own.

### 5.2 V3'.e complex (two-item e-commerce, English)

| Model | syn @ cap=400 |
|---|---|
| **`gemma4:e4b`** | **0/10** ❌ |
| `gemma3:12b` | 10/10 ✅ |
| `gemma2:2b` | 10/10 ✅ |
| `qwen2.5-coder:7b` | 10/10 ✅ |
| `llama3.1:8b` | 10/10 ✅ |
| `qwen2.5:7b` | 10/10 ✅ |
| `deepseek-v2:16b` | 10/10 ✅ |

`gemma4:e4b` drops from soft 70% (single-item) to **deterministic 0** (two-item). All other 6 models remain at 10/10. **H2 (fixture-complexity drives floor universally) refuted** — the complex fixture is harder for `gemma4:e4b` only.

### 5.3 V3'.b/.c/.d cognitive (Korean planner/reflect/verify)

| Model | planner @ 400 | reflect @ 400 | verify @ 400 |
|---|---|---|---|
| `gemma3:12b` | 10/10 | 10/10 | 10/10 |
| `gemma2:2b` | 10/10 | 10/10 | 10/10 |
| `qwen2.5-coder:7b` | 10/10 | 10/10 | 10/10 |
| `llama3.1:8b` | 10/10 | 10/10 | 10/10 |
| `qwen2.5:7b` | 10/10 | 10/10 | 10/10 |
| `deepseek-v2:16b` | 10/10 | 10/10 | 10/10 |

(`gemma4:e4b` results from the 2026-05-22~23 V3'.a~d archive: 0/10 at cap=400 across all three stages, deterministic floor.)

All 6 cross-family models clear cap=400 cleanly on the Korean cognitive prompts. **H3 (cognitive-task-domain drives floor universally) refuted** — Korean cognitive prompts produce no floor on the other 6 models.

### 5.4 Option A: V3'.e basic at cap=200

| Model | syn @ cap=200 | hit cap (eval=200)? | natural median eval_count |
|---|---|---|---|
| **`gemma4:e4b`** | **0/10** ❌ | **10/10** ⚠️ | (capped) |
| `gemma3:12b` | 10/10 ✅ | 0/10 | 73 |
| `gemma2:2b` | 10/10 ✅ | 0/10 | 50 |
| `qwen2.5-coder:7b` | 10/10 ✅ | 0/10 | 95 |
| `llama3.1:8b` | 10/10 ✅ | 0/10 | 84 |
| `qwen2.5:7b` | 10/10 ✅ | 0/10 | 60 |
| `deepseek-v2:16b` | 10/10 ✅ | 0/10 | 62 |

`gemma4:e4b` reproduces the V3'.a query_rewriter signature (cap=200 → 0/10 with full-cap eval) exactly on the synthesis arm. The other 6 models comfortably finish their natural 50-95 token budget without approaching the cap. The cap=200 threshold sits **above** their natural completion length and **inside** `gemma4:e4b`'s hidden-reasoning budget.

### 5.5 Floor magnitude — monotonic with fixture complexity, `gemma4:e4b` only

| Fixture | `gemma4:e4b` syn @ cap=400 success | Other 6 models |
|---|---|---|
| Single-item e-commerce, temp=0.2 | ~65-70% | 10/10 |
| Single-item e-commerce, temp=0.7 | 40% | 10/10 |
| Two-item e-commerce | 0% | 10/10 |
| Korean cognitive (V3'.b/.c/.d) | 0% (archive) | 10/10 (cross-family) |

`gemma4:e4b` shows a monotonic decline in success rate as fixture complexity rises; the other 6 models stay at the 10/10 ceiling across all four fixtures. The Korean-cognitive ↔ English-complex deterministic-0 alignment indicates the floor is a fixed reasoning-budget effect on `gemma4:e4b` rather than a domain or language quirk.

## 6. Hypothesis verdict — H1 confirmed

| H | Verdict | Evidence |
|---|---|---|
| **H1 — checkpoint-specific** | ✅ **CONFIRMED** | `gemma4:e4b` is the only model exhibiting cap-floor across 4 fixture/cap conditions; the other 6 models clear all conditions cleanly. |
| H2 — fixture-complexity universal | ❌ REJECTED | Two-item e-commerce: `gemma4:e4b` 0/10, other 6 at 10/10. |
| H3 — cognitive-task-domain universal | ❌ REJECTED | Korean cognitive: other 6 at 10/10 across planner/reflect/verify. |

## 7. Token-consumption signature — `gemma4:e4b` is 4-9× more verbose

> **Correction (2026-05-30)**: the 400-token figure below is the cap=400 cap-hit ceiling, not the true natural budget. The cap=4096 audit (§15.1) measures e4b synthesis natural median at **464 tokens** with 0/50 cap-hits, giving a corrected cross-family spread of **5-10×** (§15.6). The §7 table is retained for audit trail.

`gemma4:e4b` synthesis median `eval_count` vs the other 6 models (cap=400, temp=0.2, single-item e-commerce):

| Model | median eval_count | ratio vs `gemma4:e4b` |
|---|---|---|
| `gemma4:e4b` | **400** (cap hit, 10/10) | 1.0× |
| `gemma3:12b` | 73 | 5.5× less |
| `gemma2:2b` | 46 | **8.7× less** |
| `qwen2.5-coder:7b` | 95 | 4.2× less |
| `llama3.1:8b` | 84 | 4.8× less |
| `qwen2.5:7b` | 62 | 6.5× less |
| `deepseek-v2:16b` | 54 | 7.4× less |

This is the cross-family generalization of Robin Converse's 26b-vs-e4b 9× synthesis-efficiency observation (issue #448, 2026-05-23). The 9× was specific to the within-Gemma-family scale comparison; this run shows the same 4-9× spread holds across families against `gemma4:e4b`.

Ali Afana's 2026-05-22 elevation "each variant has its own tax" is the exact framing this table operationalizes — each checkpoint declares its own synthesis-mode token tax, and `gemma4:e4b`'s tax is uniformly the highest.

## 8. Yang et al. 2026 (arxiv:2605.09104) CES framework — empirical layer

Yang et al. propose a CES production function `Y = A · [δK^ρ + (1-δ)M^ρ]^(θ/ρ) · L^β · e^ε` treating internal reasoning (M_int) and external tools (M_ext) as substitutable factors. They sketch the §3.2 "Token Quantity" subsection that compression has a floor, but they do not measure the floor, the substitution boundary, or the per-checkpoint budget threshold cross-family.

This work supplies the empirical layer that maps directly to their framework:

| Yang et al. framework element | This work measurement |
|---|---|
| Substitution mode (M_int ≈ 0) | Universal across 7 checkpoints / 5 families / 4 generations / 2B-16B scale range / both temperatures |
| Synthesis-mode `M_int` budget threshold | Checkpoint-specific. `gemma4:e4b` ≥ ~400 tokens; other 6 checkpoints 46-95 tokens median (4-9× lower) |
| Token cap as resource constraint on M_int production | Floor visible only when `cap < model's natural M_int budget`. Other 6 models clear cap=200 cleanly; `gemma4:e4b` hits cap=200 at 10/10 |

This is the first cross-family empirical fit of their framework as of 2026-05-29.

## 9. Notable sub-finding: `deepseek-v2:16b` substitution outlier

| Cell | `deepseek-v2:16b` |
|---|---|
| Substitution @ cap=400, temp=0.2 | success 10/10, **eval_count median 4** (vs 58-63 for the other 6 models) |
| Substitution @ cap=200, temp=0.2 | success 10/10, eval_count median 4 |
| Synthesis @ cap=400, temp=0.2 | success 10/10, eval_count median 54 (in line with other 6) |

`deepseek-v2:16b` succeeds at substitution with ~4 tokens — an order of magnitude shorter than the other 6 models. Likely interpretations:

- Different tokenizer producing far fewer tokens for the same verbatim fragment (most likely)
- Different decoding strategy that emits a compact reference rather than the full quoted text
- Possibly partial output that still satisfies the "has_linen_clause" detector

Verifying which requires inspecting `raw_response_text` per call. Not load-bearing for the H1 verdict (synthesis cell sits in the normal 50-95 token band). Flagged here so a future closer reading doesn't miss the asymmetry.

## 10. Narrative impact (joint piece read)

Nothing in the prior Robin/Ali/Vadym/Hashevolution narrative gets retired. The only mechanical change is a **scope clarification** from "Gemma 4 family-wide cap pathology" to "`gemma4:e4b` checkpoint-isolated cap pathology". Robin's substitution/synthesis split, Ali's walk-back framing and "each variant has its own tax" line, and Vadym's substitution-vs-decision boundary all get **stronger** under cross-family confirmation rather than weaker.

The new findings layered on top:

1. **Substitution = architectural primitive** (Robin's split is family-, generation-, and scale-invariant within the 7-model panel)
2. **Synthesis-mode floor = checkpoint property** (training/distillation/quantization choice, not architecture; H1 confirmed)
3. **Yang et al. CES framework empirical layer** (cross-family first fit)
4. **9× synthesis efficiency** (Robin's within-Gemma observation generalizes; 4-9× spread holds against `gemma4:e4b` across 5 families)
5. **Direction 3 contribution** belongs to the Hashevolution slot of the four-way attribution — methodology + measurement + framework anchor

The "three deployment contexts, two architectures, single mechanism" line from Phase R5/R6 stays valid; the JAMES local-Ollama context is now explicitly the `gemma4:e4b`-checkpoint context, not a Gemma-4-family claim.

## 11. Limitations (honest framing)

1. **Single environment** — all 7-model measurements ran on the same local Ollama at the same time of day. External re-replication (Robin's sovereign Ollama, Ali's managed Gemini) would let the joint piece make a stronger "three deployment contexts" claim with full data per context. (Note: prior sub-limitation "cap range tested only 200-4096 on the other 6 models" is **closed** by the 2026-05-30 lower-cap sweep — see §15.7.)
2. **Two language / two domain pairs** — English e-commerce (substitution, simple synthesis, complex synthesis) + Korean cognitive (planner, reflect, verify). A Korean e-commerce condition would untangle whether the `gemma4:e4b` floor is genuinely a reasoning-budget property or a language–domain interaction. Not in scope today.
3. **`gemma4:e4b` mechanism unresolved** — why this specific checkpoint has a 4-9× higher synthesis-mode token tax is unanswered. Plausible candidates: quantization tier (e4b is the 4-bit-quantized variant), training-data distribution, distillation choice. The empirical signature is clear; the causal story is open.
4. **No external validation yet** — the Robin/Ali side has not independently re-run this protocol on the 6 new models. The joint-piece value rises sharply when they do.
5. **Yang et al. 2605.09104 framework anchor** — Yang et al. could publish their own cross-family empirical follow-up at any time. The "first" framing assumes a 2026-05-29 timestamp window; if their follow-up lands, this run reads as confirmation rather than the original fit.

## 12. What is NOT shared yet

Per the partial-measurement DM discipline (handover §11.10.2):

- Robin DM today (2026-05-29) was Option B pre-notice + Vadym attribution ask + Yang et al. prior art share. **No follow-up first-share DM has been sent**; this consolidated read is the consolidated DM substrate, drafting deferred to operator.
- Ali side: paused through 6/6 per Phase 12 (memory `feedback_ali_resume_notice_june6.md`). At resume, the same consolidated read folds into the joint-deposit discussion.

## 13. Reference — file inventory (this session)

Raw JSONs landed in `reports/research-runs/`:

| Phase | Files | Count |
|---|---|---|
| Step 1 | `v3prime-e-mode-split-20260529T1241*.json` × 4 | 4 |
| Step 2 | `v3prime-e-mode-split-20260529T1302*.json` × 3 | 3 |
| A | `v3prime-e-mode-split-20260529T131130.json` × 1 | 1 |
| C | `v3prime-e-mode-split-20260529T1315*-T1320*.json` × 7 | 7 |
| B-orig | `v3prime-e-mode-split-20260529T1323*-T1331*.json` × 7 | 7 |
| B-revised | `v3prime-{planner,reflect,verify}-20260529T133*-T134*.json` × 18 | 18 |
| cap=200 | `v3prime-e-mode-split-20260529T14*.json` × 7 | 7 |
| **Total** | | **47** |

Driver copies for fixture/cap variants:

- `scripts/research/v3prime_e_mode_split.py` (existing, unchanged)
- `scripts/research/v3prime_e_mode_split_complex.py` (new, B-orig two-item synthesis fixture)
- `scripts/research/v3prime_e_mode_split_cap200.py` (new, Option A cap=200 variant)
- `scripts/research/v3prime_{planner,reflect,verify}.py` (existing, used as-is with `--model` flag)

## 15. Update 2026-05-30 — lower-cap closure + ratio correction

Closes §11 Limitation 1 sub-gap (cap range untested below 200 on the other 6 models) with two additional sweeps plus an e4b natural-budget audit. The H1 verdict (§6) gets **stronger** under this data, not weaker.

### 15.1 `gemma4:e4b` natural budget — cap=4096 audit (n=50, temp=0.2)

50/50 done=stop (100% natural finish), **0/50 cap-hit**. `eval_count` distribution [390, 662], median **464**, p75 496. Synthesis budget fully characterized; cap=4096 sits comfortably above. Driver: `scripts/research/v3prime_e4b_cap4096_audit.py`.

This invalidates §7's use of the cap=400 cap-hit value (400 tokens) as the e4b natural budget. Corrected ratios in §15.6.

### 15.2 cap=50 / cap=100 sweep — 6 cross-family models

`v3prime_e_mode_split_cap50_100.py` (n=10 per cell):

| Model | sub@50 | sub@100 | syn@50 | syn@100 |
|---|---|---|---|---|
| `gemma2:2b` | 10/10 | 10/10 | 10/10 | 10/10 |
| `qwen2.5:7b` | 10/10 | 10/10 | 10/10 | 10/10 |
| `qwen2.5-coder:7b` | 10/10 | 10/10 | 10/10 | 10/10 |
| `gemma3:12b` | 10/10 | 10/10 | 10/10 | 10/10 |
| `llama3.1:8b` | 10/10 | 10/10 | 10/10 | 10/10 |
| `deepseek-v2:16b` | **0/10** ⚠️ | **0/10** ⚠️ | 10/10 | 10/10 |

5/6 models clean at cap=50 on both arms (well below their natural 46-95 token budgets). `deepseek-v2:16b` substitution arm reproduces the §9 4-token outlier (median eval=4, "linen" never emitted) at cap=50/100 — confirms per-checkpoint output-style property, not a cap effect.

### 15.3 cap=20 / cap=30 sweep — 6 cross-family models

| Model | sub@20 | sub@30 | syn@20 | syn@30 |
|---|---|---|---|---|
| `gemma2:2b` | 0/10 | 0/10 | 10/10 | 10/10 |
| `qwen2.5:7b` | 0/10 | 0/10 | 10/10 | 10/10 |
| `qwen2.5-coder:7b` | 0/10 | 0/10 | 9/10 | 10/10 |
| `gemma3:12b` | 0/10 | 0/10 | 10/10 | 10/10 |
| `llama3.1:8b` | 0/10 | 0/10 | 10/10 | 10/10 |
| `deepseek-v2:16b` | 0/10 | 0/10 | **0/10** | 10/10 |

**Substitution arm**: 5 models drop from 10/10 @ cap=50 → 0/10 @ cap=30. Sharp phase transition — detector artifact. The canonical "Refund Policy\n-------------\nItems may be returned within 30 days..." header pushes "linen" to the ~50-60 token mark; cap≤30 truncates before the keyword. The answer is being produced correctly; the detector is positionally biased. Not pathology.

**Synthesis arm**: 5/6 models retain 100% detector hit at cap=20 (21-43% of their natural budget). `deepseek-v2:16b` is the single floor-activation case: 0/10 @ cap=20 → 10/10 @ cap=30 — narrow window, keyword sits in 20-30 token range post-prompt.

### 15.4 H1 strengthened — operational-range asymmetry 20-30×

| Model | synthesis floor activation cap | as % of natural budget |
|---|---|---|
| `gemma4:e4b` | cap ≤ 400 (47.5% miss @ cap=400) | **~86%** |
| `deepseek-v2:16b` | cap ≤ 20 (clears @ cap=30) | ~37% |
| Other 5 | cap ≤ 20 (not reached — 100% @ cap=20) | < ~25% |

Activating the synthesis-mode floor on the other 5 checkpoints requires cap below 20 (cap=10 or less, untested but extrapolatable). On `deepseek-v2:16b` the window is narrow (cap=20 only). `gemma4:e4b` sits **20-30× higher** on the activation-cap axis.

At any cap in the deployment-meaningful range (200+), `gemma4:e4b` is the only checkpoint showing the floor.

### 15.5 Mechanism — budget magnitude × response-shape positioning

> **⚠️ SUPERSEDED by §16 (2026-05-30).** Direct streaming + `think`-toggle measurement shows e4b's reasoning lives in a **hidden thinking trace** (not at the visible-response tail), and the visible answer is the *same length* as the other models. The "budget × position_fraction" model below is discarded; the keyword-position estimates here were never measured (the actual visible-text keyword position is frac ≈ 0.07, decision-first). Retained for audit trail.

Two compounded factors:

1. **Natural budget magnitude** — e4b 464 tokens vs others 46-95 tokens (5-10× gap, §15.6)
2. **Detector keyword positioning** — e4b is **reasoning-first** (decision keyword at response tail: *"Based on the policy, since the customer washed the linen item, the clause states... therefore no refund applies."*). Other 5 are **decision-first** (keyword in first 20 tokens: *"No refund. The customer washed a linen item, which is final sale per the policy."*). `deepseek-v2:16b` sits midway (keyword at 20-30 token mark).

Activation cap ≈ `natural_budget × position_fraction`. For e4b: `464 × ~0.86 ≈ 400`. For other 5: `~60 × ~0.3 ≈ 18`. For `deepseek-v2`: `54 × ~0.5 ≈ 27`.

The §7 "4-9× more verbose" captures factor 1 only; **factor 2 (response shape) is the dominant driver of the operational asymmetry**. A model that produces 100 tokens reasoning-first with the keyword at token 95 would behave like e4b at cap=80; a model that produces 100 tokens decision-first with the keyword at token 5 would clear cap=10. Budget alone underdetermines floor activation.

### 15.6 §7 ratio correction (5-10× via natural median)

> **⚠️ SUPERSEDED by §16 (2026-05-30).** The natural median 464 is ~85% hidden thinking-trace tokens, not output volume. e4b is **not** 5-10× more verbose — its *visible* answer matches the panel (~320 chars). The ratio below measures thinking-trace cost, not verbosity. Retained for audit trail.

Using the cap=4096 audit (§15.1) natural median **464** instead of cap=400 cap-hit value:

| Model | natural median | ratio vs e4b (464) |
|---|---|---|
| `gemma4:e4b` | 464 | 1.0× |
| `gemma2:2b` | 46 | **10.1× less** |
| `deepseek-v2:16b` | 54 | 8.6× less |
| `qwen2.5:7b` | 62 | 7.5× less |
| `gemma3:12b` | 73 | 6.4× less |
| `llama3.1:8b` | 84 | 5.5× less |
| `qwen2.5-coder:7b` | 95 | 4.9× less |

Corrected cross-family spread: **5-10×** (was 4-9× in §7 using cap-hit ceiling). Robin Converse's within-Gemma 9× observation (issue #448, 2026-05-23) falls cleanly in the upper half of the corrected range.

### 15.7 §11 Limitation 1 — closed; new minor gap (cap=10 boundary)

§11 Limitation 1 sub-gap (cap range untested below 200 on the other 6 models) **closed** by §15.2 + §15.3.

**New minor gap**: the cap=10 boundary on the 5 decision-first models is untested. §15.5 mechanism predicts floor activation at cap ≤ 10 for these models (specifically: keyword-at-token-5 models clear cap=10; keyword-at-token-15-to-20 models fail). The question is whether this gap warrants an additional sweep before sharing.

**Verdict**: **defer unless externally triggered**. Rationale below.

**Arguments for running now**:

1. *Mechanism falsifiability* — §15.5 makes a sharp prediction; a cap=10 sweep is the direct test. If all 5 decision-first models still clear cap=10, the position-fraction model is wrong (or grossly miscalibrated).
2. *Symmetrizes the H1 asymmetry claim* — currently the e4b side is measured directly (cap=400, 47.5% miss) while the other-5 floor is bounded from above only (cap=20 clears, cap=10 unknown). Direct measurement would let §15.4 quote the asymmetry as a measured ratio rather than a lower bound.
3. *Cheap* — ~5 min, 6 model × cap=10 × n=10. No new code; flip `CAP_DEFAULT=10, CAP_LIFTED=10` in `v3prime_e_mode_split_cap50_100.py`.
4. *Preempts the obvious reviewer question* — Robin or a joint-piece referee will ask "you ran cap=20 and cap=30, why not cap=10?"

**Arguments against running now**:

1. *H1 verdict does not depend on it* — §15.4's 20-30× operational-range asymmetry is already established by **measured** points (cap=400 vs cap≤20). Even if cap=10 cleared on all 5 decision-first models, the asymmetry holds at ≥20×. Even if cap=10 failed on all 5, it tightens the ratio toward 40× but does not change the qualitative claim.
2. *Phenomenon confound risk* — at cap=10 the response is ~5-8 tokens of actual content after prompt overhead. The §15.3 substitution-arm finding (cap≤30 → detector miss is *positional truncation*, not floor activation) extends downward: at cap=10, even synthesis-arm misses likely conflate two distinct phenomena —
   - **floor activation**: model produces its normal response shape; cap truncates before the keyword (the e4b cap=400 phenomenon)
   - **subcritical truncation**: model cannot emit anything meaningful in 10 tokens; nothing is "produced and then cut"; the measurement is dominated by tokenizer/prompt-echo artifacts

   §15.5 mechanism applies cleanly to (a). Running cap=10 risks measuring (b) and labeling it (a).
3. *Detector positional bias is now known to dominate at low cap* — §15.3 already established this for the substitution arm at cap ≤ 30. The cap=10 substitution arm would re-measure the same artifact at a more extreme point, not new physics.
4. *§15.5 prediction is split, not pointwise* — the mechanism predicts intra-class variance among the 5 decision-first models (some clear, some fail, depending on keyword token position). Measuring this variance is a secondary signal about keyword positioning, not load-bearing for H1 or for the cross-family architectural-primitive claim.
5. *Pre-registration cost is sunk* — §15.5 already states the falsifiable prediction. Future verification (by us or by Robin/Ali) has a clear pre-registered hypothesis; running it now vs later changes nothing about the prediction's epistemic status.

**Recommendation**: defer. Document the §15.5 prediction as pre-registered; if a reviewer asks, or if Robin/Ali want to run it on their stacks for cross-environment replication, the sweep takes 5 minutes and the prediction is already on record. Adding it now would primarily generate audit-trail (the §15.3 detector-position framing applies; the answer is largely foreseeable) rather than novel evidence.

**Optional cheap hedge** (if zero-confound, ~5 min): run cap=10 *synthesis-arm only* on the 5 decision-first models (skip substitution — known detector artifact at low cap, would only add noise). Reports back one number per model (clear / fail) directly against the §15.5 prediction. This is the minimum-confound version of the test if running it at all feels safer than deferring.

### 15.8 File inventory delta (vs §13)

12 new JSONs in `reports/research-runs/`:

| Phase | Files | Count |
|---|---|---|
| cap=50/100 sweep (§15.2) | `v3prime-e-mode-split-20260529T2326*-T2330*.json` × 6 | 6 |
| cap=20/30 sweep (§15.3) | `v3prime-e-mode-split-20260529T2354*-T2356*.json` × 6 | 6 |
| **2026-05-30 additions** | | **12** |

Drivers (currently untracked, in `scripts/research/`):
- `v3prime_e4b_cap4096_audit.py` (§15.1, read-only audit of prior JSONs)
- `v3prime_e_mode_split_cap50_100.py` (§15.2 + §15.3; `CAP_DEFAULT`/`CAP_LIFTED` constants swapped between batches, currently restored to 50/100; `sys.stdout.reconfigure(encoding='utf-8')` added at module top for cp949-safe Windows console operation)

## 16. Update 2026-05-30 — mechanism RESOLVED: the floor is the gemma4:e4b thinking trace (overturns §7 / §15.5 / §15.6 framing)

Closes §11 Limitation 3 (`gemma4:e4b` mechanism unresolved). A direct probe — `scripts/research/v3prime_e4b_mechanism_probe.py` — settles the causal story and **invalidates the "verbosity" and "keyword-positioning" framings carried in §7, §15.5, and §15.6.** The H1 verdict (§6, checkpoint-isolated floor) is untouched and now mechanistically explained.

### 16.1 The decisive measurement — visible tokens vs counted tokens

Streaming each model's synthesis generation (num_predict=4096, temp=0.2) and counting *emitted* `response` tokens against `eval_count`:

| Model | visible tokens | eval_count | hidden | hidden % | answer chars |
|---|---|---|---|---|---|
| `gemma4:e4b` | 63 | 440 | **377** | **85.7%** | 323 |
| `qwen2.5:7b` | 61 | 62 | 1 | 1.6% | 298 |
| `gemma3:12b` | 56 | 57 | 1 | 1.8% | 283 |
| `llama3.1:8b` | 90 | 91 | 1 | 1.1% | 435 |
| `gemma2:2b` | 46 | 47 | 1 | 2.1% | 220 |

For all six non-e4b models, `eval_count == visible tokens` (hidden == 1, just EOS). **`gemma4:e4b` carries ~84-86% hidden tokens** that are counted in `eval_count` (and therefore consume the `num_predict` cap) but never appear in the `response` stream. Crucially, the *visible* answer is the **same length** as every other model (~63 visible tokens / ~320 chars ≈ qwen's 61 / 303). The "464-token natural budget" measured in §15.1 is ~85% invisible.

### 16.2 Root cause — `gemma4:e4b` is a thinking model, by design

`ollama show gemma4:e4b` declares the **`thinking`** capability (alongside vision/audio/tools; arch `gemma4`, 8.0B, Q4_K_M). The hidden tokens are a structured **"Thinking Process:"** reasoning trace the checkpoint emits by default. Exposed directly via `/api/chat` with the `think` toggle (cap=400, temp=0.2):

| call | eval_count | done | answer chars | thinking field |
|---|---|---|---|---|
| `/api/chat` think=True | 378-404 | stop | ~230-307 | **yes (~1200-1360 chars)** |
| `/api/chat` think=False | **44-45** | stop | ~204-215 | none |
| `/api/generate` think=False | **44** | stop | ~204 | none |

`think=False` collapses `eval_count` from ~400 to ~45 — landing exactly in the other-six band (45-95) — with the **same visible answer**. The floor disappears entirely. **The floor IS the thinking trace.** This is the same class of phenomenon as o1/R1-style reasoning models where `max_tokens` must budget for invisible reasoning; Ollama's `/api/generate` simply does not surface the trace, so it read as a mysterious "cap floor."

### 16.3 What this overturns

- **§7 "4-9× more verbose"** and **§15.6 "5-10× more verbose"** — ❌ e4b is **not** more verbose. Its visible answer is the same length as the panel. The token-count gap is the thinking trace, not output volume.
- **§15.5 "reasoning-first; decision keyword at the tail (position_fraction ≈ 0.86)"** — ❌ Measured keyword position in the *visible* text is frac ≈ 0.07 (early/decision-first, like the others). e4b's reasoning is real but lives in the **hidden** channel **before** the answer, not at the tail of the visible response. The `activation_cap ≈ budget × position_fraction` model is discarded.
- **§15.4 "20-30× operational-range asymmetry"** — the *measured asymmetry holds* (e4b floors at cap≤400, others at cap≤20), but the cause is reclassified: it is the thinking-trace token cost, not a budget×shape interaction.

### 16.4 Why only `gemma4:e4b` (H1, now mechanistic)

The other six panel checkpoints are not thinking-capable models — they answer directly (`eval_count == visible tokens`). `gemma4:e4b` is the only one in the panel that emits a default-on reasoning trace, so it is the only one whose `num_predict` budget is dominated by invisible tokens. The floor follows the thinking capability one-to-one — exactly the checkpoint-isolation H1 asserted.

### 16.5 JAMES operational implication (in-scope, actionable)

JAMES production calls Ollama via **`/api/generate` with `think` unset**, and `gemma4:e4b` is the code-default model. Under that path the thinking trace is **still generated and counted** (silently stripped from `response`). Consequences:

1. Every synthesis/reasoning call silently spends ~85% of its `num_predict` budget on the hidden trace.
2. Any tightened cap below ~450 (e.g. D1 Adaptive Budgeting `CAP_LIGHT` 800-1200 is safe; but lower experimental caps, or the planner/reflect/verify stages if ever capped tighter) risks **empty or truncated output** on the default model — the 39% empty-at-cap=400 rate measured in §16.1's stored data.
3. Mitigations, if desired: pass `think=false` for stages that do not need reasoning (reclaims ~85% of budget, full answer in ~45 tokens), or ensure caps stay ≥ ~500 for synthesis-class calls on `gemma4:e4b`. This is a measurement finding only — **no code change is made here**; it is flagged for a separate D1/budget follow-up.

### 16.6 Artifact

- `scripts/research/v3prime_e4b_mechanism_probe.py` — self-contained, reproducible. Part A (live stream: visible vs counted tokens), Part B (stored-JSON chars/token corroboration: e4b 0.71 vs others ~4.8), Part C (`think` toggle root-cause isolation), Part D (cross-model reasoning-cost comparison, §16.7). cp949-safe.

### 16.7 Is the reasoning cost e4b-specific? No — it is a default-mode difference, not an efficiency defect

Natural follow-up: can the "thinking cost" be measured on the *other* models too? Two findings settle it.

**(A) Native `think` toggle is e4b-only.** `ollama show` confirms only `gemma4:e4b` declares the `thinking` capability; the other six list `completion` (+ `tools`/`vision`/`insert`). Passing `think:true` to a non-thinking model is rejected:

```
/api/chat think=true on qwen2.5:7b → HTTP 400 Bad Request
```

So there is no native thinking phase to toggle or measure on the other six — their reasoning happens implicitly in the forward pass and emits **no** extra output tokens (§16.1: `eval_count == visible`).

**(B) Prompt-induced explicit reasoning is universal and comparable in cost.** Forcing any model to reason out loud ("Think step by step through each relevant clause before giving your final recommendation") converts the implicit reasoning into explicit output tokens, which `eval_count` then captures (cap=4096, temp=0.2, single-item e-commerce):

| Model | plain `eval_count` | CoT `eval_count` | induced reasoning tokens |
|---|---|---|---|
| `qwen2.5:7b` | 63 | 272 | +209 |
| `gemma3:12b` | 51 | 440 | +389 |
| `llama3.1:8b` | 72 | 240 | +168 |
| `gemma2:2b` | 48 | 215 | +167 |

The induced reasoning cost (~170–390 tokens) lands in the **same band as e4b's native trace (~377)** — `gemma3:12b` at +389 is essentially identical. Explicit reasoning costs roughly the same on every model.

**Reframing.** `gemma4:e4b` is **not** abnormally expensive at reasoning. The cap-400 floor is a **default-mode** difference, not a reasoning-efficiency defect:

| | `gemma4:e4b` (thinking model) | other six (standard models) |
|---|---|---|
| explicit reasoning | **default-on** | opt-in (only when prompted) |
| visibility | **hidden** (stripped from `response`) | visible (it is the requested output) |
| counted in `num_predict` budget | yes | yes |
| operator perception | "unexplained floor" | "I asked for it" |

When the other six are *asked* to reason, they pay the same token tax and could floor at the same caps; when e4b is told `think=false`, it drops to ~45 tokens like the others. The asymmetry is entirely "reasoning on-by-default and invisible" vs "reasoning off-by-default and visible." This is the cleanest cross-family statement of the mechanism for the joint piece: the token economy of reasoning is roughly model-invariant; what differs is the **default reasoning mode and its visibility**.

## 14. Related

- handover `docs/handovers/v0.4.x-session-2026-05-29-collaboration-checkpoint.md` §5 M3 / M11 / §11.10 / §11.10.1 / §11.10.2
- memory `feedback_arxiv_2605_09104_prior_art_finding.md` (M11 + partial-measurement DM discipline)
- memory `direction_3_cross_family_review.md` (D3 design + 8-step execution plan, now substantially executed)
- memory `feedback_ali_resume_notice_june6.md` (Ali 6/7+ rendezvous + Ali-pause collab-dependent work rule)
- Prior partial: `reports/research-runs/v3prime-cross-family-step1-2026-05-29.md` (Step 1 only, superseded by this doc)
- Archive baselines: `reports/research-runs/v3prime-{query-rewriter,planner,reflect,verify}-*.json` (5/22-23, `gemma4:e4b` only) + `v3prime-e-mode-split-20260523T*.json` (5/23 V3'.e baseline)
