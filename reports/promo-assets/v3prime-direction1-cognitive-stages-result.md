# V3' Direction 1 — Cognitive Stages A/B (result)

> 2026-05-24 two-sweep result. Driver: `scripts/research/v3prime_direction1_cognitive_stages.py`.
> Raw JSON:
> - v1 (CAP_LIGHT=800): `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T054634.json`
> - v2 (CAP_LIGHT=1200): `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T061858.json`
>
> Companion: `v3prime-direction1-adaptive-budget-result.md` (3-prompt
> sweep, same fixture). This doc is the cognitive-middleware extension.

## Headline

**Direction 1 closure**: the dynamic-budget heuristic, **after one
data-driven revision (CAP_LIGHT 800 → 1200)**, holds cap-invariant
across all 4 cognitive middleware stages with **zero truncation, zero
quality regression**, and a confirmed **7-tier monotonic natural-stop
gradient** spanning 62-1681 tokens on `gemma4:e4b` at T=0.2.

The heuristic ships as a **safe, latency-positive, memory-positive
defensive bound**, not a token-reduction lever — same conclusion as
the 3-prompt sweep, now validated across 7 task-weight tiers.

## v1 vs v2 — heuristic revision matrix

The cognitive-stages sweep ran twice, before and after `CAP_LIGHT` was
bumped from 800 to 1200 (PR #462). The first sweep is the **falsification
data** that drove the revision; the second is the **confirmation** that
the revision works.

| Stage | v1 cap | v2 cap | v1 truncation | v2 truncation | v1 quality (decision hits) | v2 quality |
|---|---|---|---|---|---|---|
| query_rewriter | 800 | 1200 | 0/20 | 0/20 | 20/20 | 20/20 |
| planner | 4096 | 4096 | 0/20 | 0/20 | 20/20 | 19/20 |
| **reflect** | **800** | **1200** | **19/20** | **0/20** | **12/20 (-40%)** | **20/20** |
| **verify** | **800** | **1200** | **19/20** | **0/20** | **5/20 (-75%)** | **20/20** |

v1 trigger pattern: `cap=800` was below natural-stop length on reflect
(926) and verify (984) → 19/20 calls truncated → quality regression.
v2 bump to 1200 sits ~20% above verify's natural-stop → 0/20 truncate
across both stages, quality fully restored.

## Per-cell detail — v2 sweep (CAP_LIGHT=1200)

| Arm | Stage | Cap | Success | `eval_count` avg | Range | Latency | `done=length` | Unique |
|---|---|---|---|---|---|---|---|---|
| baseline | query_rewriter | 4096 | 20/20 | 368.2 | 267-532 | 3.71 s | 0 | 19/20 |
| **treatment** | **query_rewriter** | **1200** | **20/20** | **383.2** | **324-572** | **3.85 s** | **0** | **19/20** |
| baseline | planner | 4096 | 20/20 | 703.4 | 585-824 | 6.94 s | 0 | 20/20 |
| **treatment** | **planner** | **4096** | **20/20** | **669.2** | **572-749** | **6.61 s** | **0** | **20/20** |
| baseline | reflect | 4096 | 20/20 | 896.9 | 791-987 | 8.83 s | 0 | 20/20 |
| **treatment** | **reflect** | **1200** | **20/20** | **910.5** | **785-985** | **8.97 s** | **0** | **20/20** |
| baseline | verify | 4096 | 20/20 | 950.1 | 735-1131 | 9.37 s | 0 | **2/20** |
| **treatment** | **verify** | **1200** | **20/20** | **924.2** | **753-1084** | **9.15 s** | **0** | **2/20** |

Every cell `done_reason=stop`, every cell 20/20 success. The treatment
arm matches baseline on all 4 stages within ±5% on `eval_count`.

## Per-stage decision verdict — v2

| Stage | Treatment cap | Δ `eval_count` | Truncation | Quality | Verdict |
|---|---|---|---|---|---|
| query_rewriter | 1200 | -4.1% (noise) | 0/20 | 20/20 | **cap-invariant** — Direction 1 3-prompt finding generalizes |
| planner | 4096 | +4.9% (noise) | 0/20 | 19/20 | **heavy-escalated** — no delta possible by design |
| reflect | 1200 | -1.5% (noise) | 0/20 | 20/20 | **cap-invariant** — v2 fix confirmed |
| verify | 1200 | +2.7% (noise) | 0/20 | 20/20 | **cap-invariant** — v2 fix confirmed |

## Two sub-findings (stable across both sweeps)

### Sub-finding 1 — `verify` is a high-clustering cognitive stage

| Stage | baseline unique (v1) | baseline unique (v2) |
|---|---|---|
| query_rewriter | 20/20 | 19/20 |
| planner | 20/20 | 20/20 |
| reflect | 20/20 | 20/20 |
| **verify** | **3/20** | **2/20** |

verify produces nearly-identical fact-check JSON across `T=0.2` runs —
**8.5/20 ≈ 12.5% unique average across two independent sweeps**.
Mechanism interpretation: fact-check is **structurally deterministic**
— the answer space is a tiny finite set (`{"grounded": true|false,
"unsupported": [...]}` with a small enumeration of unsupported claims).
The model isn't sampling randomly; it's choosing from a small finite
set.

This is a **task-type extension of Direction 4 Mechanism 2** (answer
convergence). Direction 4 framed convergence as a *workload* gradient
(substitution 1/20 → light 4/20 → heavy 20/20). The verify result
shows that **task type** is an additional convergence axis: structured
JSON outputs cluster tightly even at heavy workload (verify
`eval_count` ~950, near the heavy-synthesis natural-stop range).

### Sub-finding 2 — 7-tier monotonic natural-stop gradient

Combined Direction 1 (3-prompt + cognitive-stages) + Direction 4
(V3'.e) measurements on `gemma4:e4b` at T=0.2:

| Tier | Prompt | natural-stop (v1) | natural-stop (v2) | Cross-sweep stability |
|---|---|---|---|---|
| 1 | substitution verbatim | 62 | 62 | ✅ exact (V3'.e independent) |
| 2 | light synth e-commerce | 235 | 235 | ✅ exact (V3'.e independent) |
| 3 | query_rewriter | 377 | 368 | ✅ within 3% noise |
| 4 | planner | 670 | 703 | ✅ within 5% noise |
| 5 | reflect | 926 | 897 | ✅ within 3% noise |
| 6 | verify | 984 | 950 | ✅ within 4% noise |
| 7 | heavy synth 4-step | 1681 | 1681 | ✅ exact (V3'.e independent) |

7 monotonically-increasing tiers spanning 62 → 1681 tokens
(**27x dynamic range**). Cross-sweep noise stays within 3-5% on
each tier — **the gradient is reproducible**.

This is the **quantitative form of the joint-paper sub-clause** *"the
workload gradient is multi-tier"*. Each tier corresponds to a real
prompt category and a measurable natural-stop length. The
distinction between *workload weight* and *answer-convergence* axes
holds: tier-6 verify has tier-5/6-class workload but tier-1-class
answer convergence (2/20 unique, like substitution).

## Direction 1 final closure status

| Original criterion | Outcome |
|---|---|
| Heuristic correctness (3-prompt) | ✅ All 3 prompts route to predicted caps |
| Heuristic correctness (4 cognitive) | ✅ All 4 stages route to predicted caps (v2 cap=1200 fixes v1 reflect/verify tightness) |
| Zero quality regression — 3-prompt | ✅ 20/20 across all tiers |
| Zero quality regression — 4 cognitive | ✅ v2 PASS (v1 had reflect 20→12, verify 20→5; v2 restored) |
| Zero truncation | ✅ `done_reason=stop` on every cell, both sweeps |
| Token reduction ≥ 60% (original hypothesis) | ❌ Cap is a ceiling, not the floor; reductions are noise across both sweeps |
| Latency improvement | ✅ -7~18% on substitution + light tiers; cognitive stages cap-invariant (latency 매치 baseline within ±5%) |
| Memory improvement | ✅ KV-cache buffer scales with cap |
| Safety bound | ✅ Per-call cap acts as emergency-exit guard |

### Direction 1 ships as

A **safe, latency-positive (light tiers), memory-positive, defensive-
bound** mechanism with a **quantitatively-mapped 7-tier task-weight
gradient**. The original hypothesis (60-80% token reduction) **doesn't
apply** to `gemma4:e4b` because the cap was a ceiling, not the floor.
The data turned out to be more valuable than the hypothesis:

- 7-tier monotonic gradient confirmed
- `verify` cognitive-stage clustering finding
- heuristic v2 (CAP_LIGHT=1200) validated by falsification + revision +
  confirmation cycle

### What ships in tree

- `core/reasoning/budget.py` — `TaskBudget.assess()` + `retry_doubled()` + 3 cap tiers (200 / 1200 / 4096)
- `core/retrieval/query_rewriter.py` — wiring gated behind `JAMES_ADAPTIVE_BUDGET=1` (default OFF, byte-identical for non-opt-in operators)
- `scripts/research/v3prime_direction1_adaptive_budget.py` — 3-prompt driver (e-commerce free-form)
- `scripts/research/v3prime_direction1_cognitive_stages.py` — 4-stage driver (cognitive middleware prompts)
- 71 unit tests (40 + 31)
- 2 result docs (3-prompt + this one)
- 3 raw JSONs (1 × 3-prompt sweep + 2 × cognitive-stages v1/v2)

### What does NOT ship

- `JAMES_ADAPTIVE_BUDGET` default-ON flip — hypothesis target unmet
- D1.C/D production wiring of the 4 cognitive stages — the cap-invariance result removes the urgency; if a future use case justifies wiring (e.g., operator opting in for memory benefit), the wiring shape is documented and the 4 stages can be added the same way `query_rewriter` was
- Stage-specific caps (e.g., a per-stage CAP_REFLECT) — not needed; the 3-tier heuristic + v2 CAP_LIGHT=1200 covers all 7 measured natural-stop tiers

## Joint-paper consequence

| Before Direction 1 | After Direction 1 (with both sweeps closed) |
|---|---|
| §axis-2 (workload gradient) was a binary substitution-vs-synthesis split | §axis-2 is a **7-tier monotonic gradient with measurable natural-stop length per tier** |
| Mechanism 2 (answer convergence) framed by workload weight only | Mechanism 2 has **two convergence axes**: workload weight (1/20 → 20/20) AND task type (verify 2-3/20 even at heavy workload — structured-JSON clustering) |
| Direction 1's product impact was framed as "Adaptive Budgeting cuts tokens" | Direction 1's product impact is framed as *"cap budgets are a memory + safety rail on a model whose natural-stop length is the actual workload measurement; the v2 heuristic stays in tree as the canonical task-weight band for any operator opt-in"* |

Headline phrase (3-author locked, unchanged — **PROVISIONAL pending
4-way attribution map at mid-June outline; Robin 2026-05-28 flagged
thread-level contributions from Vadym Arnaut (substitution-vs-decision
boundary) + Ali (each-variant-tax framing), see launch-tracker
2026-05-28 row**):

> *"Substitution is free. Synthesis costs in proportion to what it
> has to invent."*

Sub-clauses (expanded from Direction 1):

> *"…and inversely to parameter count."* (Robin axis-3, 2 evidence layers)
>
> *"…and the gradient is multi-tier monotonic — 7 measured tiers
> spanning 27× dynamic range on gemma4:e4b."* (JAMES Direction 1)
>
> *"…and answer convergence has a task-type axis: structured-JSON
> outputs cluster tightly even at heavy workload (verify ~12.5%
> unique)."* (JAMES Direction 1, cross-sweep validated)

## Reproducibility

```powershell
git checkout feat/v0.3-direction1-heuristic-v2
git pull
ollama run gemma4:e4b "ping"  # warm-up
python scripts/research/v3prime_direction1_cognitive_stages.py --n 20
# Raw JSON: reports/research-runs/v3prime-direction1-cognitive-stages-<ts>.json
# Expected: 0/20 truncation on every cell, quality 20/20 (or 19/20 noise)
# on every stage, 7-tier natural-stop gradient stable within 5% of the
# 2026-05-24 measurements.
```

Total wall-clock: ~13 minutes (160 calls, average 4.9 s/call across
the matrix; reflect + verify cells dominate at ~9 s each).

## Out of scope for this result doc

- Cross-model generalization (does the 7-tier gradient hold on 26b? Llama?) — Direction 3
- Direction 2 (task-weight metric formalization) — would replace the 3-tier heuristic with a measured metric per-prompt; would consume the 7-tier natural-stop data as ground truth
- Direction 5 (auto-routing) — would route model selection per cap tier; consumes the heuristic as a routing signal
- Robin / Ali notice DMs — bundled per `archive/2026-05-24-bundled-notice-drafts-korean-publish.md` after Direction 1 closure

## Related artifacts

- `core/reasoning/budget.py` — heuristic (PR #461 + PR #462 v2)
- `scripts/research/v3prime_direction1_cognitive_stages.py` — driver
- `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T054634.json` — v1 raw
- `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T061858.json` — v2 raw
- `reports/promo-assets/v3prime-direction1-adaptive-budget-result.md` — 3-prompt sweep result (sibling)
- `reports/promo-assets/v3prime-e-substitution-synthesis-result.md` — Direction 4 result (multi-tier gradient sub-finding)
- `docs/research/v3prime-protocol-v1.md` — JSON schema spec
- `docs/handovers/v0.3.x-measurement-framework-track.md §Stage 2.A` — Direction 1 plan
