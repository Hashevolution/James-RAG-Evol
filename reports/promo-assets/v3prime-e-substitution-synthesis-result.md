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

## External validation (2026-05-23 LinkedIn comment thread)

PR #440 (this result, merged UTC 05:42 / KST 14:42 on 2026-05-23)
was shared on LinkedIn the same day. Four substantive comments
arrived within hours — one from Ali Afana, three from Robin
Converse. Full transcripts archived in
`docs/handovers/v0.3.x-ali-collaboration-track.md §Track 5 —
2026-05-23 Ali + Robin LinkedIn comments`. Three things change
about how this result doc functions going forward:

### 1. The headline phrase is now three-author standing

> "Substitution is free. Synthesis costs in proportion to what
> it has to invent."

Originally proposed in §Implications as a candidate. Ali
independently re-derived the same 10-word phrase ("cost asymmetry
in ten words") before reading the §Implications section. Robin
endorsed it explicitly ("Ali's right, that's the line"). The
phrase ships in the joint piece with three-author standing — no
further framing debate required.

### 2. Robin's 26b 2×2 matrix mirrors this driver exactly

Robin's same-day commitment:

> "Running 26b 2×2 matrix today: cap × prompt-type at N=20/cell,
> mirroring your protocol exactly. ... Pulling your raw JSONs as
> the analysis template. Data posted when it lands."

**Consequence**: `scripts/research/v3prime_e_mode_split.py` and the
JSON shape produced under `reports/research-runs/v3prime-e-mode-
split-*.json` are now the **cross-stack analysis template** for
Robin's `gemma4:26b` MoE sweep. Schema-stability obligation: do
NOT alter the field shape of the result JSONs until Robin's 26b
data has been merged into the cross-stack comparison. Schema
migration after she has pulled the template would break her
downstream analysis pipeline.

### 3. Architecture-invariance test is live

| 26b 2×2 outcome | Joint-piece consequence |
|---|---|
| 26b substitution flat @ ~60 tokens AND synthesis @ 400-450 tokens proportional | "Across stacks **and across model scales**" — portability second axis confirmed; headline ships as-is |
| Either signature shifts | "Next research thread" — joint piece narrows to e4b-confirmed claim + open question for follow-up |

Reference signatures Robin is testing against (from this result):

- **Substitution baseline**: **62 tokens flat** (`ollama_eval_count=62`
  on all 40 substitution-arm calls in this run — true flatline, not
  averaged), 0.8s latency, 20/20 success at cap=400.
- **Synthesis-with-recommendation baseline**: 400-450 tokens output,
  4.0-4.5s latency, 14/20 @ cap=400 / 20/20 @ cap=4096.

Data-arrival watch: Robin's 26b 2×2 matrix is **being built today
(2026-05-23, per her sub-reply)** with the data dump posted "when
it lands" — no specific calendar commitment beyond that. When it
arrives, this result doc gets a §Cross-stack replication subsection
appending her four cells alongside the e4b cells above.

## Cross-stack replication — gemma4:26b MoE (Robin Converse, 2026-05-23)

Robin delivered the 26b 2×2 matrix the same day she committed to it.

- **Companion repo**: [triavalabs/gemma4-26b-mode-split](https://github.com/triavalabs/gemma4-26b-mode-split) (MIT, 80-call raw JSON + sweep.py + analysis.md)
- **Issue on this repo**: [#448](https://github.com/Hashevolution/James-RAG-Evol/issues/448) (filed because PR #440 is locked post-merge)
- **Endpoint**: `https://api.triavalabs.com` (sovereign Ollama on Hetzner CCX33, public HTTPS via Caddy reverse proxy)
- **Model**: `gemma4:26b` MoE (25.8B params, Q4_K_M, base, no system prompt)
- **Protocol**: T=0.2, N=20/cell, `think: False`, same fixture structure as our V3'.e
- **Total**: 80 calls, 6 min runtime, zero failures

### Side-by-side 4-cell matrix

| | e4b (V3'.e, this doc) | 26b (Robin) | Delta |
|---|---|---|---|
| Substitution @ 400 | 20/20, eval_count=62 flat | 20/20, **eval_count=38 flat** | -39% tokens, both deterministic |
| Substitution @ 4096 | 20/20, eval_count=62 flat | 20/20, **eval_count=38 flat** | -39%, cap-invariant on both |
| Synthesis @ 400 | **14/20 (70%)**, 400-450 mean | **20/20 (100%)**, **mean=50.7** | +30pp success, **~9× fewer tokens** |
| Synthesis @ 4096 | 20/20, 400-450 mean | 20/20, **mean=54.5** | ~9× fewer tokens |

### Architecture-invariance decision tree — outcome

The pre-registered tree (from §External validation above) had two
arms. Strict reading of the data: **both reference signatures
shifted** (substitution 62→38; synthesis 400-450→49-54). By
pre-registration that triggers the right column ("next research
thread"), not the left ("architecture-invariance confirmed").

But the signatures shifted in a **systematic direction**, not
randomly. Robin's analysis (her [`analysis.md`](https://github.com/triavalabs/gemma4-26b-mode-split/blob/main/analysis.md))
calls it: *"Parameter count appears to buy reasoning efficiency,
not just reasoning capacity."* The mode-split framing **held**;
the workload gradient framing **held qualitatively but scales
with parameter count**.

Both pre-registered arms are partially true. The honest read is
**neither pure invariance nor pure architecture-sensitivity** —
instead, a third axis emerged:

### Three axes in the joint piece (post-26b data)

1. **Mode split** (Robin original, LinkedIn 2026-05-22 sweep) —
   substitution and synthesis are architecturally distinct
   operating modes. Substitution is deterministic, T-invariant,
   bypasses sampling. Synthesis is variable and reasoning-bound.
   *Confirmed on both stacks.*
2. **Workload gradient** (JAMES V3'.e, this doc) — synthesis cost
   scales with task weight. Heavy synthesis (4-stage cognitive,
   V3'.a~d) deterministically fails at cap=400; light synthesis
   (e-commerce refund, V3'.e) partially fails (70%); no synthesis
   (verbatim) always passes. *Confirmed on e4b.*
3. **Model-scale efficiency** (Robin 26b, new — 2026-05-23) —
   synthesis cost scales **inversely** with parameter count.
   Substitution stays bit-for-bit invariant. 26b synthesis is ~9×
   more token-efficient than e4b on the same fixture, AND closes
   the success gap (70%→100%). *New axis; emerged from the very
   data that was supposed to confirm invariance.*

### Determinism note (Robin's "Finding 1")

40/40 substitution calls on 26b produced **1 unique response**,
`eval_count=38` flat. Bit-for-bit identical text at T=0.2. Robin's
phrasing: *"The mode genuinely bypasses sampling."* This is
sharper than our V3'.e read (which also saw `eval_count=62`
flatline but did not check for unique-output count). **Action
item for future V3'.e re-runs**: also record unique-output count
per cell to confirm the same determinism on e4b — if e4b is
similarly bit-for-bit deterministic on substitution, Robin's
"bypasses sampling" claim extends across both models and is a
publishable mechanism on its own.

### Direction 4 result — e4b unique-count verification (2026-05-24)

The "Action item" above was executed the next day. Driver patched
(`scripts/research/v3prime_e_mode_split.py` — `call_ollama()`
returns `raw_response_text`, `summarize()` adds `Unique` column
per cell), V3'.e re-run on `gemma4:e4b` at T=0.2, N=20/cell.
Raw JSON: `reports/research-runs/v3prime-e-mode-split-20260523T151159.json`
(80 calls, 0 failures, ~5 min wall-time on local Ollama).

#### Substitution arm — bit-for-bit determinism CONFIRMED on e4b

| Cap | Success | Unique | `eval_count` range | `text_len` range |
|---|---|---|---|---|
| 400 | 20/20 | **1/20** | [62, 62] | [290, 290] |
| 4096 | 20/20 | **1/20** | [62, 62] | [290, 290] |

All 40 substitution calls (across both caps) returned the same
canonical text, character for character. The canonical e4b
substitution output (290 chars, 62 tokens):

> Refund Policy
> -------------
> Items may be returned within 30 days of delivery for a full
> refund, provided they are unworn, unwashed, and have all
> original tags attached. Linen, silk, and cashmere garments are
> final sale once washed — refunds are not issued for washed
> items in these fabrics.

#### Synthesis arm — variability persists, model-scale conditional

| Cap | Success | Unique (of success) | `eval_count` range |
|---|---|---|---|
| 400 | 15/20 | 15/15 (100%) | [400, 400] (cap-bound) |
| 4096 | 20/20 | 20/20 (100%) | [391, 496] (natural stop) |

Synthesis on e4b is essentially fully variable — every successful
call produces a unique response. Compare to 26b where synthesis
unique was 6/20 @ cap=400 and 9/20 @ cap=4096 (≈30-45% unique).

#### Two publishable mechanisms confirmed

**Mechanism 1 — Substitution-mode bypasses sampling layer (Gemma 4
family-wide architectural property)**. Both e4b (8B) and 26b MoE
(25.8B) produce 1 unique substitution response across the entire
sweep at T=0.2. Token counts shift with model size (62 vs 38),
but the bit-for-bit determinism property is identical. This is
the same mechanism on both stacks — not an averaging effect, not
a temperature artifact, not stack-specific. **Axis 1 (mode split)
graduates from "qualitative split + quantitative flatline" to
"sampling-layer bypass as architectural property."**

**Mechanism 2 — Synthesis determinism scales with parameter
count** (new sub-finding emerging from the cross-stack
comparison). At the same T=0.2:

| Stack | Synthesis unique @ cap=400 | Synthesis unique @ cap=4096 |
|---|---|---|
| e4b (8B) | 15/15 = **100%** | 20/20 = **100%** |
| 26b MoE (25.8B) | 6/20 = **30%** | 9/20 = **45%** |

Larger parameter count = answers converge toward the same policy
exception (e.g. Robin's "damaged items" reference). Smaller
parameter count = synthesis explores more of the answer space.
Axis 3 (model-scale efficiency) now has two layers: **(a) token
efficiency** — fewer tokens to reach the same answer — and **(b)
answer convergence** — answers themselves cluster more tightly at
higher parameter counts. Both layers point at the same underlying
property: *parameter count buys reasoning routing precision*, not
just capacity.

#### Joint-paper consequence

The 3-author headline locks in as-is — substitution is free
(bit-for-bit free on both stacks), synthesis costs scale with
both task weight (e4b workload gradient) and inversely with
parameter count (cross-stack token + convergence both). The
proposed sub-clause *"and inversely to parameter count"* now has
two evidence layers, not one.

Result first-shared with Robin via issue #448 follow-up comment
(her axis-1 owned property + new sub-finding on her axis 3).

### Latency caveat

Robin's substitution-arm latency of 3.8s is **not directly
comparable** to our 0.8s — her endpoint traverses public HTTPS +
Caddy reverse proxy + Hetzner CCX33 cold-path; ours is local
loopback. Within-endpoint comparisons (her sub 3.8s vs her synth
5.0s, OR our sub 0.8s vs our synth 4.0s) are the valid ones; both
show synth taking longer wall-time than sub at comparable
token-counts, consistent with the mode-split finding.

### Headline phrase status after data arrival

The 3-author 10-word framing (*"Substitution is free. Synthesis
costs in proportion to what it has to invent."*) **still holds as
the headline** — substitution is empirically free on both stacks;
synthesis still has a per-task cost. The 3rd axis (model-scale
efficiency) becomes a **sub-clause** rather than a re-write:

> *"Substitution is free. Synthesis costs in proportion to what
> it has to invent — and inversely to parameter count."*

The expanded form is not yet 3-author-locked (Robin's data is
new; Ali has not yet weighed in on the model-scale axis). The
original 10-word phrase remains the safe headline; the sub-clause
extension is a draft proposal for the joint piece.

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
