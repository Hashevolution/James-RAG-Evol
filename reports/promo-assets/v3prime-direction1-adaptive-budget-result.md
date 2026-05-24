# V3' Direction 1 — Adaptive Budget A/B (result doc)

> Status: **skeleton — awaiting first sweep**.
>
> Driver: `scripts/research/v3prime_direction1_adaptive_budget.py`.
> Run with `python scripts/research/v3prime_direction1_adaptive_budget.py --n 20`
> on the operator workstation (sandbox env has no live Ollama).
> Raw results land in `reports/research-runs/v3prime-direction1-
> adaptive-budget-<timestamp>.json`. Cell values in the matrix below
> get filled from that JSON.
>
> JSON schema: V3' Protocol v1 with two additive fields
> (`adaptive_cap_requested`, `adaptive_decision_reason`). Robin's
> cross-stack analysis pipeline reads this unchanged — additive only.

## Headline (template — finalize on data arrival)

**Direction 1 ships when**:
- substitution-arm `eval_count` reduces by ≥ 60% vs baseline `cap=4096`
- light-arm `eval_count` reduces by ≥ 60% vs baseline
- heavy-arm `eval_count` delta is within ±10% (no regression)
- quality keyword-hit counts hold (zero quality regression on all three arms)

If all four hold, the JAMES-side adaptive-budget mechanism is **validated for production wiring** (env flag flip from default-OFF to default-ON in a follow-up PR), with the underlying claim — *"parameter count buys reasoning routing precision, not just capacity"* (Robin Converse, 2026-05-24) — extended to its **task-weight axis** counterpart: *"task weight buys cap precision, not just floor safety."*

## Experiment shape

| Dimension | Value |
|---|---|
| Model | `gemma4:e4b` (default; override `--model`) |
| Temperature | 0.2 (V3' protocol standard) |
| N per cell | 20 (V3' Protocol v1 §statistical-floor) |
| Cells | 2 arms × 3 prompt types = 6 |
| Total calls | 120 (`2 × 3 × 20`) |
| Wall-clock | ~5 min on warm-loaded local Ollama |
| Fixture | V3'.e e-commerce refund policy context (same as PR #440 / PR #453) |

### Three prompt tiers (task-weight gradient)

| Prompt | Trigger | Predicted treatment cap |
|---|---|---|
| **substitution** | *"Return verbatim ..."* (no synthesis required) | 200 (`CAP_SUBSTITUTION`) |
| **light** | *"In one sentence, what is the standard refund window?"* | 800 (`CAP_LIGHT`) |
| **heavy** | *"Compare ... step by step. Then produce a 4-step decision tree."* | 4096 (`CAP_HEAVY`) |

Heuristic resolution verified by import-time test (no Ollama needed):

```
substitution  → cap= 200 reason=substitution_pattern   ✓
light         → cap= 800 reason=default_light          ✓
heavy         → cap=4096 reason=heavy_marker           ✓
```

## Result matrix — **empty until first sweep**

| Arm | Type | Cap | Success | `eval_count` avg | Latency | `done=length` |
|---|---|---|---|---|---|---|
| baseline | substitution | 4096 | _/_ | _ | _ s | _ |
| treatment | substitution | 200 | _/_ | _ | _ s | _ |
| baseline | light | 4096 | _/_ | _ | _ s | _ |
| treatment | light | 800 | _/_ | _ | _ s | _ |
| baseline | heavy | 4096 | _/_ | _ | _ s | _ |
| treatment | heavy | 4096 | _/_ | _ | _ s | _ |

### Token reduction

| Prompt | baseline `eval_count` | treatment `eval_count` | Δ |
|---|---|---|---|
| substitution | _ | _ | _% |
| light | _ | _ | _% |
| heavy | _ | _ | _% |

### Quality regression check

| Prompt | metric | baseline | treatment |
|---|---|---|---|
| substitution | policy-keyword hits | _/20 | _/20 |
| light | decision-keyword hits | _/20 | _/20 |
| heavy | decision-keyword hits | _/20 | _/20 |

## Direction 1 pass/fail decision tree

Same shape as V3'.e's pre-registered decision tree — written *before* data arrives.

| Substitution token Δ | Light token Δ | Heavy token Δ | Quality regression | Outcome |
|---|---|---|---|---|
| ≤ -60% | ≤ -60% | within ±10% | zero | **PASS** — flip env flag default to ON; D1.C/D wiring activates |
| -30% to -60% | any | any | zero | **PARTIAL** — heuristic too conservative; consider lowering `CAP_LIGHT` |
| > -30% | any | any | zero | **REGRESSION** — heuristic mis-classifies; tighten substitution detection |
| any | any | any | non-zero | **STOP** — quality regression supersedes any token-reduction win |
| substitution `done=length` > 0 | any | any | any | **STOP** — CAP_SUBSTITUTION=200 too tight; bump to 400 and re-run |

## Cross-experiment integration

V3' Protocol v1 schema compliance (this file extends V3'.e shape):

| V3'.e field | Direction 1 field | Compatibility |
|---|---|---|
| `arm` ∈ {substitution, synthesis} | `arm` ∈ {baseline, treatment} | semantic re-use, same field name |
| `cap` (numeric) | `adaptive_cap_requested` (additive) | additive — V3'.e parsers read either |
| (n/a) | `adaptive_decision_reason` (additive) | new — V3'.e parsers ignore unknown fields |
| `ollama_eval_count`, `raw_response_text`, etc. | same | unchanged |

Robin's analysis pipeline (`triavalabs/gemma4-26b-mode-split`)
reads this JSON without code changes. If the dataset proves the
JAMES-side claim, the data slots directly into the joint-paper §axis-2 (workload gradient) as the **JAMES product-validation row** —
moving the workload-gradient axis from "measured in research" to
"shipped in product".

## Headline candidates (operator selects on data arrival)

1. *"Adaptive budget is free on substitution, free on light synthesis, and a tax-free no-op on heavy synthesis — N=20, e4b, e-commerce fixture."*
2. *"Same answer for ~80% fewer reasoning tokens on the substitution + light tiers, no regression on the heavy tier — JAMES-side validation of Robin Converse's *parameter count buys routing precision* on the task-weight axis."*
3. *"V3'.e's three workload tiers were the right gradient; Direction 1 turns it into a production knob."*

## What this experiment is NOT

- Not a benchmark vs another budget heuristic — the comparison is against the **fixed-cap status quo** (`DEFAULT_MAX_TOKENS=4096`)
- Not a cross-model test — single model (`gemma4:e4b`); cross-model is Direction 3
- Not a cross-stack test — single stack (local Ollama); Robin's 26b cross-stack is published as PR #440 + issue #448
- Not a `core/reasoning/budget.py` unit test — that lives at `tests/test_adaptive_budget.py` (40 tests; ships with PR #461)

## Reproducibility

```powershell
# 0. PR #461 merged on main (TaskBudget module + query_rewriter wiring,
#    gated behind JAMES_ADAPTIVE_BUDGET, default-OFF byte-identical)

# 1. Warm-load Ollama with gemma4:e4b (recommended)
ollama run gemma4:e4b "ping" 2>$null

# 2. Run the experiment driver (no env flag needed — the driver
#    calls TaskBudget.assess() directly, bypassing the wiring's
#    runtime env gate)
python scripts/research/v3prime_direction1_adaptive_budget.py --n 20

# 3. Driver writes:
#    reports/research-runs/v3prime-direction1-adaptive-budget-<ts>.json
#    + prints the result matrix + token-reduction quantification + pass/fail classification

# 4. Append the JSON path to this result doc; backfill the
#    "Result matrix" + "Token reduction" + "Quality regression check"
#    + select headline.

# 5. PASS outcome → follow-up PR flips JAMES_ADAPTIVE_BUDGET default
#    from "0" to "1" in core/retrieval/query_rewriter.py +
#    documents it in v0.3.x-measurement-framework-track.md.
#    REGRESSION outcome → tighten heuristic + re-run before any
#    wiring flip.
```

## Out of scope (this result doc)

- D1.C/D wiring (planner / reflect / verify / synth) — sequenced after this experiment's PASS
- Direction 2 (task-weight metric formalization) — would replace `_SUBSTITUTION_REGEX` / `_HEAVY_REGEX` with a measured metric
- Direction 5 (auto-routing) — separate cycle, layers model selection on top of this budget
- Joint paper consolidation (Direction 6(I)) — picks this data up after Ali Gemini backend (mid-June) lands the third stack

## Related artifacts

- `core/reasoning/budget.py` — heuristic module (PR #461)
- `core/retrieval/query_rewriter.py` — wiring gate (PR #461)
- `scripts/research/v3prime_direction1_adaptive_budget.py` — driver (this experiment)
- `reports/promo-assets/v3prime-e-substitution-synthesis-result.md` — V3'.e + Direction 4 (sibling experiment using same fixture)
- `docs/research/v3prime-protocol-v1.md` — JSON schema spec
- `docs/handovers/v0.3.x-measurement-framework-track.md §Stage 2.A` — Direction 1 plan this experiment instruments
