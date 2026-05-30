# D1 7-tier budget — thinking-trace decomposition (INTERNAL upgrade study)

**Date**: 2026-05-30
**Framing**: 🔧 **JAMES-internal upgrade study — NOT a joint-piece artifact.**
**Trigger**: D3 §16 mechanism (gemma4:e4b cap-floor = thinking trace) applied to the D1 7-tier budget gradient.
**Driver**: `scripts/research/v3prime_e4b_7tier_thinking_split.py` (+ existing D1/D3 JSONs).

> **Why this is internal, not collaboration.** D1's "7-tier monotonic
> natural-stop gradient (62→1681 tokens, 27×)" is JAMES's own measurement
> axis, on JAMES's own default model. This study asks an *operational* question
> about JAMES routing — it does not touch the Robin 26b-scale anchor or the Ali
> managed-Gemini axis, and it does **not restate the public 27× figure**. The
> number stands; this study *recontextualises its interpretation internally*.
> Any external framing revision folds into the joint piece at the rendezvous,
> not a unilateral post. See D3 report §17.5 + memory `d3_e4b_floor_mechanism_thinking_trace`.

## 1. Question

D1's per-stage budget signal (`core/reasoning/budget.py`) routes off the 7-tier
gradient, and D5/LEO consume the same per-call budget. After §16 showed ~85% of
gemma4:e4b's *synthesis* budget is a hidden thinking trace, the operational
question is:

> For each of the 7 tiers D1 routes on, how much of `gemma4:e4b`'s per-tier
> budget is the thinking trace vs visible output — i.e. is D1 routing on task
> **workload** or on **reasoning-mode cost**?

## 2. Method

Stream `gemma4:e4b` on each of the 7 tier prompts (cap=4096, T=0.2), counting
visible `response` tokens against `eval_count` (the gap = hidden thinking trace,
language-independent — important since the cognitive tiers are Korean and a
chars/token heuristic does not transfer). Then re-run each tier with
`think=false` to show the reclaimable budget. Cross-family context comes from
the existing D1/D3 cap=4096 natural-budget JSONs (no new cross-family runs).

The 7 tiers (D1 ordering): substitution / light-synth / heavy-synth (English
e-commerce) + query_rewrite / planner / reflect / verify (Korean cognitive,
prompts pinned from `core/reasoning/*`).

## 3. gemma4:e4b per-tier decomposition

| Tier | visible tok | eval_count (think ON) | hidden | hidden % | eval (think OFF) | reclaim |
|---|---|---|---|---|---|---|
| 1. substitution | 61 | 62 | 1 | 2% | 62 | 0% |
| 2. light_synth | 59 | 433 | 374 | **86%** | 60 | 86% |
| 3. heavy_synth | 107 | 596 | 489 | **82%** | 100 | 83% |
| 4. query_rewrite | 38 | 534 | 496 | **93%** | 28 | 95% |
| 5. planner | 92 | 685 | 593 | **87%** | 95 | 86% |
| 6. reflect | 580 | 1492 | 912 | 61% | 463 | 69% |
| 7. verify | 23 | 1164 | 1141 | **98%** | 24 | 98% |

Gradient spans: think-ON `eval_count` **62→1492 (24×)** ← *this is the column the public D1 "27×" measures*; think-OFF (workload-only) 24→463 (19×); visible-output-only 23→580 (25×).

## 4. Cross-family context (existing JSONs, natural median eval_count, cap=4096, T=0.2)

The other six panel models have **no thinking capability** (§16.7), so their
`eval_count` == visible output.

| tier | gemma2 | qwen2.5 | qwen2.5-coder | llama3.1 | gemma3 | deepseek-v2 |
|---|---|---|---|---|---|---|
| substitution | 63 | 59 | 59 | 58 | 62 | 4 |
| light_synth | 57 | 72 | 95 | 89 | 73 | 89 |
| planner | 99 | 99 | 99 | 95 | 60 | 375 |
| reflect | 336 | 191 | 4 | 464 | 643 | 787 |
| verify | 18 | 86 | 19 | 90 | 24 | 17 |

(query_rewrite and heavy_synth cross-family not in existing JSONs; not load-bearing for the internal question.)

## 5. Findings

**F1 — On `gemma4:e4b`, 5 of 7 tiers are 82–98% thinking trace.** substitution
(2%) is the think-free baseline; reflect (61%) is mixed; light_synth /
heavy_synth / query_rewrite / planner / verify are 82–98% thinking. `think=false`
reclaims 83–98% of those tiers' budget (verify 1164→24, query_rewrite 534→28,
planner 685→95) with the visible answer unchanged.

**F2 — The D1 budget *magnitude* is, on e4b, substantially a thinking-trace
gradient, not a workload gradient.** What D1 routes on for verify is a
1164-token budget whose *visible output is 23 tokens*. The 24× "span ratio"
looks similar with think ON vs OFF, but that is coincidental (different tiers
sit at the extremes); the per-tier **magnitudes** collapse 5–48× when reasoning
is disabled.

**F3 — `reflect` is the exception: real cross-model workload.** reflect has 580
*visible* tokens on e4b (not just thinking), and the cross-family grid confirms
other non-thinking models are also verbose on reflect (gemma3 643, deepseek 787,
llama3.1 464). So the reflect tier carries genuine task-workload signal; the
others are e4b-reasoning-inflated.

**Net**: the 7-tier gradient is a **mix** — `reflect` (and the substitution
baseline) are real workload; the remaining five tiers' magnitudes on e4b are
dominated by the thinking trace.

## 6. Operational implications (A5 / D4 / D5)

1. **A5 (planner/reflect/verify hold cap=4096) is now explained.** They are sized
   to clear the thinking trace (verify needs 1164, reflect 1492, planner 685),
   not the visible output (23 / 580 / 92). With `think=false`, verify/planner
   need ~24/95 tokens — caps could drop 7–48× on those stages.
2. **D1/D5 budget routing caveat.** The per-call budget signal these consume is,
   on e4b, mostly reasoning-mode cost. Routing decisions keyed to it are keyed to
   "is reasoning on" more than "is the task heavy". D4 (task-weight metric) should
   measure the **think-OFF / visible** budget if it wants a workload signal.
3. **Reclaim is gated on quality (A3).** `think=false` reclaims 83–98% on five
   tiers, but whether disabling reasoning *degrades* those stages is unmeasured
   on hard inputs — that is exactly the deferred A3 think-mode quality-boundary
   experiment. reflect keeps 463 visible tokens think-OFF (output survives);
   verify's visible output is tiny either way (23–24) so its 1141 thinking tokens
   may or may not change the verdict. **Do not flip `think=false` in production
   until A3 measures per-stage quality impact.**

## 7. Collaboration handling

- The public D1 "27×" figure is **not restated or corrected here**. The
  measurement stands; the interpretation gains a thinking-trace caveat that is
  internal-only until the joint piece.
- This study stays in JAMES's D1 slot. It does not pre-empt or alter the Robin /
  Ali cross-family narrative. Share/recontextualisation folds into the joint
  piece at the 6/6+ rendezvous (same discipline as D3 §17.5).

## 8. Artifact

- `scripts/research/v3prime_e4b_7tier_thinking_split.py` — streams e4b on all 7
  tiers (think ON visible/hidden split + think OFF reclaim), reuses the pinned
  `core/reasoning/*` prompt constants. cp949-safe.

## 9. Backlog linkage

Advances **A5** (D1 stage expansion — now has the mechanism) and informs **D4**
(task-weight metric should use think-OFF budget). Gated next step is **A3**
(think-mode quality boundary). See `docs/handovers/v0.4.x-backlog-reconciliation-2026-05-30.md`.
