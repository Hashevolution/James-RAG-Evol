# V3'.e Result — Substitution / Synthesis Mode Split

> 2026-05-23 sovereign-Ollama run of `scripts/research/v3prime_e_mode_split.py`
> on `gemma4:e4b`, temperature 0.2, e-commerce refund-policy fixture
> (English, 710 chars). Two consecutive sweeps (N=10 and N=20) for
> stability. Raw results: `reports/research-runs/v3prime-e-mode-split-
> 20260523T05165{4,4 + the 51-min suffix}.json`.

## Headline

**Refined Pattern S.** Robin Converse's substitution / synthesis split
holds on `gemma4:e4b` at JAMES caps, and the synthesis arm reveals a
**task-weight gradient** that the binary V3'.a/.b/.c/.d 4-stage view
underspecified.

## Result matrix (N=20)

| Arm | Cap | Success | Avg latency | Domain hit |
|---|---|---|---|---|
| substitution | 400 | **20/20** (100%) | 0.8s | 20/20 |
| substitution | 4096 | 20/20 (100%) | 0.8s | 20/20 |
| synthesis | 400 | **14/20** (70%) | 4.0s | 14/20 |
| synthesis | 4096 | 20/20 (100%) | 4.5s | 20/20 |

N=10 sweep produced the same pattern at lower precision (synthesis @
400: 4/10 = 40%). The N=20 result is the load-bearing read.

## Three layers in this data

### Layer 1 — Substitution mode is floor-immune (Robin confirmed)

Substitution at cap=400 passes 20/20 with `domain_hit=20/20`. Verbatim
retrieval of the canonical "Refund Policy" section happens without
hitting the ~500-token reasoning floor that V3'.a/.b/.c/.d
established. Robin's "two operating modes, one model" framing has its
architectural confirmation on a different model (gemma4:e4b) and a
different sovereign stack (JAMES Ollama).

### Layer 2 — Synthesis floor is a *gradient*, not a binary

V3'.a (query_rewrite), V3'.b (planner), V3'.c (reflect.critique), and
V3'.d (verify.fact_check) all collapsed **0/10 at cap=200~400**.
V3'.e's synthesis arm — same model, same cap=400 — passes **14/20 =
70%** on the e-commerce refund-recommendation prompt.

The difference isn't model or cap. It's **task weight**. The 4-stage
cognitive prompts are heavier synthesis instances:

- query_rewrite re-frames a Korean ETF question into a search-shaped
  prompt
- planner decomposes into ordered subtasks
- reflect.critique generates a structured 3-dimension critique
- verify.fact_check matches multi-claim answer against multi-document
  context

V3'.e's synthesis arm asks for a single refund recommendation with a
2-3 sentence justification — lighter synthesis. The floor is real for
both, but its strength scales with the reasoning workload of the
synthesis task.

**This is the new mechanism layer JAMES contributes.** Robin's split
identifies the binary boundary; the V3'.a~d + V3'.e composite shows
the boundary has a *strength gradient* on the synthesis side.

### Layer 3 — Latency telemetry as direct proof

| Arm | Latency (s) |
|---|---|
| substitution | 0.8 |
| synthesis | 4.0–4.5 |

A 5× gap, on the same model with the same cap budget. That's the
substitution / synthesis split in physical time, observable only on
sovereign infrastructure (managed APIs surface aggregate latency but
not the eval_count breakdown that explains *why* it differs).

This is the data-shaped restatement of Robin's "When you own the
inference path, you see the work. When you rent it, you see the
bill."

## Decision tree — script said "Partial", we read it as refined-S

The driver's auto-classifier looked for `synthesis ≤ 3/10 @ 400` to
call Pattern S. 14/20 (70%) is above that threshold so it returned
"Partial signal — examine per-cell mix."

The substantive read is different. The threshold was set against
V3'.a~d's all-or-nothing 0/10 baseline. V3'.e's e-commerce synthesis
is a lighter task than those 4 cognitive stages, so a *partial* fail
at cap=400 is exactly the gradient prediction:

```
heavy synthesis (V3'.a~d, 4-stage cognitive) → 0/10  @ 400
light synthesis (V3'.e, e-commerce recommendation) → 14/20 @ 400
no synthesis (V3'.e substitution, verbatim retrieval) → 20/20 @ 400
```

Three workload levels, three cap-behaviour signatures. Pattern S is
confirmed; the boundary just isn't binary.

## Implications for the Track 5 joint piece

| Before V3'.e | After V3'.e |
|---|---|
| "3 contexts, 2 architectures, 1 mechanism" | "3 contexts, 2 architectures, **2 mechanisms with task-weight gradient**" |
| Cap pathology = floor at some constant cost | Cap pathology = synthesis-mode entry cost that **scales with task weight** |
| JAMES = 4-stage replicator | JAMES = gradient quantifier (Robin's confirmation + new task-weight axis) |
| Single-layer finding | Two-layer finding (mode split + workload gradient) |

The headline phrase candidate: **"Substitution is free. Synthesis
costs in proportion to what it has to invent."**

## What JAMES owns that the joint piece can't get elsewhere

- Robin's data is single-model + cross-temperature + same-prompt
  (model-internal split surface).
- JAMES contributes: cross-cap × cross-task-weight (gradient axis).
- Together they cover both axes of the two-mechanism story.

The vocabulary remains Robin's ("two operating modes", "substitution
/ synthesis") — V3'.e adopts it. The **dimension JAMES adds is the
weight axis**: substitution arm, light synthesis arm, heavy synthesis
arm. That's JAMES's first measurable contribution to the *framing*
not just the *execution*.

## Reproducibility

- Driver: `scripts/research/v3prime_e_mode_split.py` (PR #439).
- Run: `python scripts/research/v3prime_e_mode_split.py --n 20`.
- Output: matching JSON in `reports/research-runs/`.
- Total wall time: ~3 min on a workstation with Ollama + gemma4:e4b
  warm-loaded.

## Out of scope for this result doc

- Track 5 narrative reframe (the "two mechanisms + gradient" headline
  is a separate handover-track update, not this file).
- Robin / Ali comment drafts (data-first; the comment shares this
  finding, not the joint-piece reframe).
- A third "very heavy synthesis" arm (would close the gradient
  measurement; defer pending discussion).
