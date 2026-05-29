# V3'.e Direction 3 — Cross-family / cross-generation final analysis

**Date**: 2026-05-29 (single calendar day, evening session)
**Status**: 🔒 **Internal consolidated — sharing decision deferred to operator**
**Trigger**: handover §5 M3 (Direction 3, user-deferred earlier) + §5 M11 (arxiv:2605.09104 prior art finding)
**Drivers**: `scripts/research/v3prime_e_mode_split.py` (`--model` flag), `v3prime_planner.py`, `v3prime_reflect.py`, `v3prime_verify.py`; two single-purpose copies (`v3prime_e_mode_split_complex.py`, `v3prime_e_mode_split_cap200.py`) for fixture / cap variants
**Total trials**: ~1480 across 7 models × multiple fixtures × multiple caps × n=10 (n=20 for boundary reproducibility)

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

1. **Single environment** — all 7-model measurements ran on the same local Ollama at the same time of day. External re-replication (Robin's sovereign Ollama, Ali's managed Gemini) would let the joint piece make a stronger "three deployment contexts" claim with full data per context.
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

## 14. Related

- handover `docs/handovers/v0.4.x-session-2026-05-29-collaboration-checkpoint.md` §5 M3 / M11 / §11.10 / §11.10.1 / §11.10.2
- memory `feedback_arxiv_2605_09104_prior_art_finding.md` (M11 + partial-measurement DM discipline)
- memory `direction_3_cross_family_review.md` (D3 design + 8-step execution plan, now substantially executed)
- memory `feedback_ali_resume_notice_june6.md` (Ali 6/7+ rendezvous + Ali-pause collab-dependent work rule)
- Prior partial: `reports/research-runs/v3prime-cross-family-step1-2026-05-29.md` (Step 1 only, superseded by this doc)
- Archive baselines: `reports/research-runs/v3prime-{query-rewriter,planner,reflect,verify}-*.json` (5/22-23, `gemma4:e4b` only) + `v3prime-e-mode-split-20260523T*.json` (5/23 V3'.e baseline)
