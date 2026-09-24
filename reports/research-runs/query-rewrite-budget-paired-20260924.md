# Query-rewrite budget — paired arms, and what they did to two earlier claims (2026-09-24)

> **Design**: two arms, **same session, back-to-back**, on branch
> `feat/v0.6.2-query-rewrite-timeout-knob` (`b9aa8a0`), via
> `scripts/qvt_capture_baseline.py --n-runs 1 --output <arm>` so every
> integrity guard from this week applies (model pinned to `gemma4:e4b`
> with routing disabled; generation-failure abort; recorded provenance).
>
> | arm | `JAMES_QUERY_REWRITE_TIMEOUT_S` | artifact |
> |---|---|---|
> | A | unset (`env -u`) → 10 s | `qvt-arm-A-rewrite10-20260924.json` |
> | B | `30` | `qvt-arm-B-rewrite30-20260924.json` |
>
> Both written **outside** `eval/qvt/` on purpose: since #1139 the
> renderer selects the newest `captured_at` there as canonical, so an
> arm written into that directory would silently become the baseline.
>
> **n = 1 per arm.** This is screening, not a verdict — see §5.
> Host state during arm B: `host-state-armB-20260924.json`.

## 1. Results

| axis | arm A (10 s) | arm B (30 s) | Δ B−A | `baseline_6deca66` band |
|---|---:|---:|---:|---:|
| path_coverage | 0.9091 | 0.9091 | 0.000 | 0.0455 |
| graded_answer | 0.7500 | 0.7500 | 0.000 | 0.0667 |
| abstention_f1 | 0.5000 | 0.6667 | **+0.167** | 0.0714 |
| token_cost (chars) | 1318.7 | 1556.2 | +237.5 | 343.45 |
| latency_cost (s) | 73.51 | 61.40 | **−12.1** | 3.40 |

Both arms: 18/18 answers, 0 generation failures, `effective=gemma4:e4b`.

## 2. Mechanism — from `scripts/research/latency_decomposition.py`

| | arm A | arm B |
|---|---:|---:|
| wall mean (s/query) | 81.6 | 66.5 |
| **timeouts, total** | 7 | **0** |
| **rewriter failed** (`reason:retrieve` right after a timeout) | 4/26 = 15.4% | **0/24 = 0%** |
| `reason:synth` mean (s) | 14.2 | 12.4 |
| `reason:reflect` mean (s) | 12.8 | 10.6 |

**At 30 s the rewriter never timed out, and no stage anywhere did.**

## 3. Separating the knob from the order effect

`synth` also got 13% faster (14.2 → 12.4 s). `synth` has no timeout
interaction and this branch does not touch it, so that change is **not
the knob** — it is the second arm running on a warmer host. It is used
here as an internal control:

- scale arm A by synth's ratio (0.873): 81.6 → **71.2 s**
- arm B measured: **66.5 s**
- residual attributable to the knob: **≈ 4.7 s/query**
- arm A's measured timeout cost: **5.1 s/query**

The residual matches the timeout cost within 0.4 s. Of the 15 s wall
difference, roughly 10 s is order effect and roughly 5 s is the knob.

## 4. Two earlier claims, both corrected by this run

**4.1 The #1145 report's magnitudes were host-state, not a property of the code.**

`latency-decomposition-20260922.md` reported the rewriter failing on
**83.3%** of queries and timeouts at **32%** of wall clock. At the same
10 s budget, today's arm A shows **15.4%** and **6.3%**.

The reason is visible in the one stage that cannot be affected by any
budget: `synth` averaged **33.8 s** on 2026-09-22 and **14.2 s** today —
2.4× faster, on the same hardware and model, with no code change to
it. The host was in a materially slower state on 09-22. That report
did caveat "the hardware the baseline was captured on"; it did not
anticipate that the *same* hardware varies this much day to day, and
its headline numbers should be read as that day's state.

The cause of the 09-22 slowdown is **unknown and cannot now be
recovered**: nothing recorded GPU load, clocks or co-resident
processes at the time. (A CPU-offload hypothesis was checked and
refuted — `gemma4:e4b` loads at 3.01 GB and was fully GPU-resident.)

**4.2 "Raising the budget cannot recover time" was also wrong.**

Proposed before this run, on the reasoning that a longer budget can only
wait longer. The measurement says otherwise, and the mechanism is in
the audit log: a timeout **spends the whole budget and then triggers a
retry**. When a stage's natural completion time sits just above the old
budget, raising it replaces *budget + retry* with *natural time* — and
that is shorter. The original "recovers ~11 s" and the correction were
both imprecise; this run is the number.

## 5. What this does and does not license

**Does**: land the knob with the default unchanged. Arm A is the
default path; see §6.

**Does not**: flip the default to 30 s. Three reasons —

1. **n = 1 per arm.** `feedback_n1_verdict_inflation_n3_caught` is the
   repo's own record of an n=1 result that looked ⭐⭐ and collapsed
   into noise at n=3.
2. **abstention_f1 +0.167 is one query** (TP 2→3, FN 3→2), on the
   noisiest axis. Plausible — a completed rewrite can change retrieval
   enough to flip one abstention — but one query is not a measurement.
3. **The latency gain is host-dependent.** On 09-22's slower state the
   rewriter needed far more than 10 s; whether 30 s would then have
   been enough is not known from this run.

A default flip needs arm A vs arm B at **n = 3**, same session.

## 6. rule #2 — the default path

Arm A **is** the knob's default path (env unset). Against
`baseline_6deca66.json`:

| axis | baseline median | arm A | inside band? |
|---|---:|---:|:---:|
| path_coverage | 0.8636 | 0.9091 | at edge (0.9091 was the baseline's max run) |
| graded_answer | 0.7333 | 0.7500 | ✅ |
| abstention_f1 | 0.5000 | 0.5000 | ✅ |
| token_cost | 1525.35 | 1318.7 | ✅ |
| latency_cost | 130.2 | 73.5 | ❌ — host state, §4.1 |

Quality: no change. Latency: out of band by 17×, and attributable to
the host via the `synth` control rather than to this change.

## 7. The finding underneath all of this

**`baseline_6deca66.json`'s latency axis is not comparable across days.**
Its band is 3.40 s *within* a day; the day-to-day swing measured here is
~57 s. Any PR measured on a different day than the baseline will show a
large latency "improvement" or "regression" that is purely the host.

`token_cost` is fine — arm A lands inside its band. It is specifically
`latency_cost`, the axis #1137 celebrated gaining, that cannot be used
this way as-is.

Two remedies, both the same shape as this week's other fixes:

- **Record host state in the artifact** (GPU utilisation, clocks,
  co-resident processes, `ollama ps`). The 09-22 cause is lost because
  this was not done; `host-state-armB-20260924.json` is the first one.
- **Latency claims need a same-session control arm**, as this run used,
  or normalisation by a budget-independent stage such as `synth`.
