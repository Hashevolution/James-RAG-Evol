# Turning reflect off: −44% latency, no axis worse, verify kept (2026-09-28, n=3)

> **Design**: 6 captures on `main` `c2ef5ba`, **interleaved**
> ON → NOREFLECT → ON → NOREFLECT → ON → NOREFLECT, one `--n-runs 1`
> each, same session, ~1 h 52 min. All six 18/18 healthy.
>
> The arms differ only in `JAMES_ENABLE_REFLECT` — **plan and verify
> run in both**. That is the point of this cut: the 2026-09-27 n=3
> disabled all three stages together and could not separate their
> costs from their benefits, and verify is the stage with the
> demonstrated catch.
>
> **A trap avoided**: `config.py:52` loads `.env` only for keys whose
> process value is *empty*. Unsetting `JAMES_ENABLE_REFLECT` would have
> let `.env` restore it to `1` and both arms would have been identical.
> The NOREFLECT arm set it to `0`, and `audit_log` confirms it:
>
> | run | plan | reflect | verify | timeouts |
> |---|---:|---:|---:|---:|
> | ON r1 / r2 / r3 | 8 / 8 / 8 | 34 / 31 / 32 | 54 / 54 / 54 | 2 / 5 / 0 |
> | NOREFLECT r1 / r2 / r3 | 8 / 8 / 7 | **0 / 0 / 0** | 54 / 54 / 54 | 4 / 0 / 0 |
>
> Every artifact records `c2ef5ba` — commits for the parallel
> annotation-axis work were held until the run finished, because the
> capture records `HEAD` per run and a mid-run commit would have given
> identical code six different provenances. GPU steady (SM clock
> 2650–2738 MHz).

## 1. Result

| axis | ON median | band | NOREFLECT median | band | Δ |
|---|---:|---:|---:|---:|---:|
| Path Recall | 0.9091 | 0.0000 | 0.9091 | 0.0000 | 0.0000 |
| Graded Answer | 0.6833 | 0.0500 | **0.7500** | 0.1000 | **+0.0667** |
| Abstention F1 | 0.5714 | 0.0953 | 0.5714 | 0.1667 | 0.0000 |
| Token Cost | 1545.5 | 194.7 | 1395.5 | 263.9 | −150.1 |
| Latency Cost | **69.6 s** | 5.7 | **39.0 s** | 8.8 | **−30.6 s (−44.0%)** |

The latency bands are tight this time — no cold first run — so −30.6 s
sits far outside both. Hallucinations per run: ON [3, 2, 3],
NOREFLECT [2, 3, 3].

Reflect cost more than the ~20 s the 09-24 decomposition suggested. That
decomposition predates #1151, which gave the critique the retrieved
evidence (up to 8000 characters) — a longer prompt, on every query.

## 2. The graded shift is one-directional, and it has a mechanism

2026-09-27's identical medians hid five per-query flips that went both
ways and cancelled. Not here: **2 queries differ, both toward
NOREFLECT, none the other way.**

| query | ON (3 runs) | NOREFLECT (3 runs) |
|---|---|---|
| Q1 "RAG가 무엇인가?" | 0.33 · 0.67 · 0.33 | 0.67 · 0.67 · 0.67 |
| Q19 "Which company issues IBIT and FBTC?" | 0.33 · 0.67 · 0.33 | 0.67 · 1.00 · 1.00 |

Q19 was traced:

- **ON r1** — synth: *"ANSWER: BlackRock and Fidelity. The context
  identifies IBIT as "블랙록의 비트코인 ETF"…"* → critique: *"makes two
  definitive claims … Unsupported"* → revise: *"the evidence … does not
  contain explicit information identifying the issuing c[ompanies]"*.
- **ON r3** — the same: a correct, cited answer replaced by *"The
  provided evidence does not explicitly state which company issues IBIT
  and FBTC."*
- **NOREFLECT** — synth's answer ships.

With n = 3 and one query traced, +0.0667 is not a claim about graded. It
is a direction, with the mechanism in hand.

## 3. Correction to #1151

`reflect-evidence-grounding-20260926.md` licensed *"reflect no longer
deletes a fact its own evidence supports"*. That holds for the case it
was measured on — Q14, where the evidence stated the fact outright. It
does **not** hold when the support is an inference: the evidence says
IBIT is "블랙록의 비트코인 ETF", which answers "who issues IBIT", and the
grounded critique rejected it because the word *issues* is absent.

So #1151 traded one failure for a narrower one. Before: the critique
judged against training data and deleted post-training facts. After: it
judges against the evidence **literally** and deletes reasonable
inferences from it. Both end with a correct synth answer replaced by a
refusal.

## 4. verify, scored

With the annotation axis (`annotation-axis-20260928.md`):

| arm | mode | annotated | P | R | TA | FA | miss |
|---|---|---:|---:|---:|---:|---:|---:|
| ON | strict | 14 | 1.00 | 0.56 | 5 | 0 | 4 |
| NOREFLECT | strict | 11 | 1.00 | 0.30 | 3 | 0 | 7 |
| ON | graded | 14 | 0.63 | 0.56 | 5 | 3 | 4 |
| NOREFLECT | graded | 11 | 0.38 | 0.30 | 3 | 5 | 7 |

**verify keeps running and keeps its precision** — no false alarm in
strict mode in either arm. Its **recall is lower without reflect**:
5 of 9 wrong answers flagged against 3 of 10. That is the one axis that
moved against NOREFLECT. The counts are small (two catches), and the
mechanism is not established — reflect rewrites answers before verify
sees them, so the two arms hand verify different text — but it is
reported rather than rounded away.

## 5. Layer-intent verdict for reflect

Rule #2 + §5.6. Stage `reflect` within `Cognitive stages`, primary axis
`graded_answer`, prerequisites met (31–34 reflect events per ON run).

```json
{
  "layer_id": "Cognitive stages / reflect",
  "flag": "JAMES_ENABLE_REFLECT", "flag_value": "1 (stage ON)",
  "primary_axes": ["graded_answer"],
  "regression_check_axes": ["path_coverage", "abstention_f1",
                            "token_cost", "latency_cost"],
  "prerequisites_met": true,
  "per_axis_delta": {
    "graded_answer":  {"delta": -0.0667, "noise_band": 0.10,  "verdict_contribution": "primary-flat"},
    "path_coverage":  {"delta":  0.0,    "noise_band": 0.0,   "verdict_contribution": "within-noise"},
    "abstention_f1":  {"delta":  0.0,    "noise_band": 0.167, "verdict_contribution": "within-noise"},
    "token_cost":     {"delta": +150.1,  "noise_band": 263.9, "verdict_contribution": "within-noise"},
    "latency_cost":   {"delta": +30.6,   "noise_band": 8.8,   "verdict_contribution": "cost"}
  },
  "verdict": "zero",
  "reason": "reflect's primary axis is flat (and trends negative, with a traced mechanism) while the stage costs 44% of query latency"
}
```

Deltas are stated as reflect's contribution (ON − NOREFLECT).

## 6. What this licenses — and what it does not

**Licensed**

- On step7, at n=3, disabling reflect cuts query latency **69.6 s →
  39.0 s (−44%)** with **no quality axis worse** and verify's warnings
  retained at the same precision.
- reflect still replaces correct answers with refusals after #1151,
  via over-literal grounding (§2, §3).
- An operational recommendation, for the operator: **reflect off**.
  Note the shape of that decision — `JAMES_ENABLE_REFLECT` is **already
  off by default in the code** (`reflect/loop.py`:
  `return os.environ.get("JAMES_ENABLE_REFLECT") == "1"`); it is the
  deployment's `.env` that turns it on. The change is a line in `.env`,
  not a code change, and it is the operator's configuration to change.

**Not licensed**

- ❌ "reflect has no value." step7 is mostly single-hop. Reflection's
  intent is multi-step revision, which nothing here exercises.
- ❌ "Removing reflect improves quality." +0.0667 graded is two queries
  at n = 3; one is traced, one is not.
- ❌ Ignoring §4. verify's recall fell from 5/9 to 3/10. Small, and
  unexplained, and the one number that argues the other way.
- ❌ Anything about plan. It ran in both arms.

## 7. Follow-ups

1. **The operator decision** in §6.
2. **reflect's over-literal grounding** (§3) — if reflect stays in any
   configuration, the critique prompt needs to accept inference from
   the evidence, not only restatement. Measured on this axis and Q19.
3. **verify's recall with and without reflect** (§4) — larger n, or a
   trace of the missed wrong answers, before it is read as an effect.
4. **plan** is the remaining stage without a measurement of its own.
