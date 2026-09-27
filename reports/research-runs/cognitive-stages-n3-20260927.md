# The cognitive stages cost 62% of the latency and buy nothing the oracle can see (2026-09-27, n=3)

> **Design**: 6 captures on `main` `788308c`, **interleaved**
> ON→OFF→ON→OFF→ON→OFF, one `--n-runs 1` each, same session, ~2 h.
> Arms differ only by `JAMES_DISABLE_COGNITIVE_STAGES`. All six runs
> report 18/18 healthy answers; the flag is confirmed in `audit_log`
> (OFF arms have **0** plan / reflect / verify events, ON arms have
> 8–9 / 28–35 / 54).
>
> Interleaved rather than blocked on purpose. Blocked, the second arm
> always runs later, and any drift over the session is indistinguishable
> from an arm effect — the failure this project already hit when the same
> model and budgets ran 2.4× apart on 09-22 vs 09-24. Interleaving cost
> nothing and §4 shows it earned its keep.
>
> Aggregation is medians over 3 runs, same formula as
> `_aggregate_runs` (median / min / max / band = max − min).

## 1. Result

| axis | ON median | band | OFF median | band | Δ (OFF − ON) |
|---|---:|---:|---:|---:|---:|
| Path Recall | 0.9091 | 0.0909 | 0.9091 | 0.1061 | **0.0000** |
| Graded Answer | 0.6833 | 0.0500 | 0.6833 | 0.0334 | **0.0000** |
| Abstention F1 | 0.6667 | 0.0953 | 0.6667 | 0.0833 | **0.0000** |
| Token Cost | 1597.2 | 102.0 | 1392.2 | 356.1 | −205.0 (−12.8%) |
| Latency Cost | **69.4 s** | 36.6 | **26.5 s** | 40.4 | **−42.9 s (−61.8%)** |

All three quality axes land on the same median. Per-run values:

```
path      ON 0.9091 0.9091 0.8182   OFF 0.8030 0.9091 0.9091
graded    ON 0.7000 0.6833 0.6500   OFF 0.6833 0.6833 0.7167
abstention ON 0.6667 0.5714 0.6667  OFF 0.7500 0.6667 0.6667
latency   ON 102.1  69.4   65.5     OFF 66.5   26.1   26.5
```

## 2. The identical medians are not identical behaviour

Aggregates can hide compensating movement, so every query was compared.
**5 of 20 differ at the median, in both directions:**

| query | ON | OFF |
|---|---:|---:|
| Q1 | 1.0000 | 0.6667 |
| Q3 | 1.0000 | 0.6667 |
| Q2 | 0.0000 | 0.3333 |
| Q4 | 0.6667 | 1.0000 |
| Q19 | 0.0000 | 1.0000 |

ON wins two, OFF wins three, and they cancel. That is the shape of
run-to-run variance, not a systematic quality effect — the same churn
that flipped 9 of 20 queries between identical-code runs on 09-26.

Abstention is steadier: **no query's majority classification differs**
between arms. Hallucinations per run: ON [2, 3, 2], OFF [2, 2, 2].
False abstentions: ON [1, 0, 1], OFF [0, 1, 1].

## 3. Layer-intent verdict

CLAUDE.md rule #2 + `v0.4-alpha-6-sector-llm-ablation-matrix.md` §5.6.
Layer `Cognitive stages`, design intent *"multi-step planning /
reflection / verification"*, **primary axis `graded_answer`**, latency an
expected trade-off. Prerequisites met (the stages ran: 8–9 plan, 28–35
reflect, 54 verify events per ON run).

```json
{
  "layer_id": "Cognitive stages",
  "flag": "JAMES_DISABLE_COGNITIVE_STAGES", "flag_value": "0 (layer ON)",
  "primary_axes": ["graded_answer"],
  "regression_check_axes": ["path_coverage", "abstention_f1",
                            "token_cost", "latency_cost"],
  "prerequisites_met": true,
  "per_axis_delta": {
    "graded_answer":  {"delta": 0.0,    "noise_band": 0.05,  "verdict_contribution": "primary-flat"},
    "path_coverage":  {"delta": 0.0,    "noise_band": 0.106, "verdict_contribution": "within-noise"},
    "abstention_f1":  {"delta": 0.0,    "noise_band": 0.095, "verdict_contribution": "within-noise"},
    "token_cost":     {"delta": +205.0, "noise_band": 356.1, "verdict_contribution": "within-noise"},
    "latency_cost":   {"delta": +42.9,  "noise_band": 40.4,  "verdict_contribution": "cost"}
  },
  "verdict": "zero",
  "reason": "the layer's primary axis is flat at n=3 while the layer costs 61.8% of query latency"
}
```

§5.6's rule reads *"a layer that misses its intent axes is reject
regardless of stable non-intent axes"*. Applied literally to a layer
that is flat on its intent axis and costs 43 s/query, that is **reject**.
The card above says `zero` because `zero` is the rule's own label for
"all primary axes within noise", and the distinction matters: `zero`
states what was measured, `reject` is a recommendation. §5 is why the
recommendation does not follow from this run alone.

## 4. Correction — the 09-24 report over-attributed the timeouts

`cognitive-stages-contrast-20260924.md` §2 stated that the three stages
cost *"~48 s of a 74 s query and **all 7 timeouts**"*. The first half
holds; the timeout half does not.

| run | timeouts | latency |
|---|---:|---:|
| ON r1 | 22 | 102.1 s |
| OFF r1 | **27** | 66.5 s |
| ON r2 | 1 | 69.4 s |
| OFF r2 | 0 | 26.1 s |
| ON r3 | 0 | 65.5 s |
| OFF r3 | 0 | 26.5 s |

Timeouts concentrate in the **first run of each configuration**,
including the arm with the stages disabled, and vanish in warm runs of
both. They are a cold-configuration artifact, not something the stages
cause. n=1 could not see this: on 09-24 the single OFF run happened to
be the warm one.

The latency gap itself is unaffected — OFF r1 was faster than ON r1
while carrying *more* timeouts — and the interleaved design is what
surfaced it. Blocked, all three OFF runs would have sat after all three
ON runs and the r1 spike would have read as an arm effect.

GPU state was steady throughout (mean SM clock 2648–2747 MHz, power
177–197 W), so the r1 cost is warm-up inside the process, not
throttling.

## 5. What this licenses — and what it does not

**Licensed**

- On this suite, at n=3, the cognitive stages move **no** measured
  quality axis and cost **42.9 s/query (61.8%)** plus 205 characters.
- That holds with the stages *fixed*: this run includes #1151's reflect
  grounding fix and #1153 / #1154's verify work, so it is not measuring
  the broken versions the 09-24 contrast found.
- Timeouts are not stage-attributable (§4).

**Not licensed**

- ❌ **"Turn the cognitive stages off."** The strongest argument against
  is a capability the five axes do not score: with the stages off,
  verify produces **no annotations at all**, where ON produced 3, 7 and
  4 per 18 queries. One of that class caught `Alex Karp` offered as
  Anthropic's CEO two days ago. Its frequency is ~1% of traffic
  (`bare-claim-frequency-20260927.md`), so 18 queries × 3 runs cannot
  register it, and `abstention_f1` being flat is not evidence it does
  not matter. Removing a layer on axes that cannot see its main output
  is `feedback_single_axis_ablation_misframing`.
- ❌ **"The stages are useless."** step7 is 20 queries of mostly
  single-hop retrieval. The layer's stated intent is *multi-step*
  planning and reflection; nothing here exercises that.
- ❌ Any per-query reading of §2. Those five flips are bidirectional
  variance.
- ❌ Treating the bands as tight. `latency_cost` bands are 36–40 s
  because of the r1 warm-up (§4); the medians are the usable statistic
  and the bands are not a precision claim.

## 6. What would settle it

1. **A multi-hop suite.** The stages' intent axis is quality on
   multi-step questions. Until that is measured, "flat on step7" and
   "no benefit" are different statements.
2. **Score the annotations.** verify's output is currently invisible to
   the oracle. An axis that credits a correct "this claim is
   unsupported" note — and penalises a wrong one — would let the
   trade-off be judged instead of argued.
3. **A per-stage split.** plan, reflect and verify were turned off
   together. Their costs and benefits are almost certainly not equal,
   and verify is the one with the demonstrated catch.
