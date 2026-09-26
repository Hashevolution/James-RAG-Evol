# Verify hardening — three arms, and a regression check that found nothing (2026-09-27)

> **Design**: three arms, **same session, back-to-back**, differing by
> **commit** so each artifact's `git_sha` records which code produced
> it. `scripts/qvt_capture_baseline.py --n-runs 1 --output <arm>`; all
> three report 18/18 healthy answers.
>
> | arm | sha | code |
> |---|---|---|
> | H | `a68f2c3` | pre-fix (`main`) |
> | I | `3b39a0d` | + package split + echo corroboration |
> | J | `1207b1d` | + verify coverage gaps (includes I) |
>
> **n = 1 per arm.** On this suite the aggregate is a regression check,
> nothing more — `graded_answer` flips on roughly half the queries
> between identical-code runs (see the 2026-09-26 report §3).

## 1. The headline: verify's decisions did not move

`audit_log`, counted over each arm's 20 episodes:

| arm | accept | annotate | **block** |
|---|---:|---:|---:|
| H (pre-fix) | 13 | 5 | **0** |
| I (echo corroboration) | 13 | 5 | **0** |
| J (+ coverage) | 13 | 5 | **0** |

Identical counts. The annotated **sets** overlap on 3 of 5, and the two
that differ are the same queries whose `graded_answer` flips between
runs — synth wording variance upstream of verify, not a shift in what
verify decides.

That is the result these arms were run to get. Both changes tighten
paths that are supposed to be rare, and neither perturbed the healthy
path.

**What the arms did *not* do is exercise either fix.**

- **Zero blocks in all three arms, including pre-fix.** The Q17 false
  block that motivated the echo work (2026-09-24, arm A) did not recur
  here, so arm I cannot show it being fixed. The block is intermittent:
  it needs synth to phrase its citation a particular way.
- **The bare-claim annotation never fired.** The one short answer in
  arms I and J — `"ANSWER: insufficient information"` — is **32
  characters**, two over `BARE_CLAIM_ANSWER_CHARS = 30`, so it took the
  threshold path and accepted. (Not annotating it is the right outcome:
  the fact-check had flagged the refusal *itself* as an unsupported
  claim, which is a checker artifact. The boundary did the right thing
  by luck, not by design.)

So the evidence for both fixes is the unit tests plus the two traced
defects they were written from, and the arms' contribution is the
regression check above. Stated plainly rather than dressed up.

## 2. Quality Delta vs `baseline_6deca66`

Bands from `aggregate.*.noise_band`.

| axis | H (pre-fix) | I (echo) | Δ H→I | J (coverage) | Δ H→J | band |
|---|---:|---:|---:|---:|---:|---:|
| Path Recall | 0.9091 | 0.9091 | 0.0000 | 0.9091 | 0.0000 | 0.0455 |
| Graded Answer | 0.6500 | 0.7333 | +0.0833 | 0.6167 | −0.0333 | 0.0667 |
| Abstention F1 | 0.5714 | 0.5000 | −0.0714 | 0.5000 | −0.0714 | 0.0714 |
| Token Cost | 1732.9 | 1648.3 | −84.6 | 1314.3 | −418.6 | 343.45 |
| Latency Cost | 67.53 | 65.95 | −1.58 | 62.45 | −5.08 | 3.40 |

Three deltas land outside their bands — graded H→I (+0.0833), token
H→J (−418.6) and latency H→J (−5.08). **None is attributable to either
change**, and all three are in the direction that would flatter the
PRs, which is exactly when to be careful:

- Neither change touches generation. Verify runs *after* the answer
  exists, and its recommendation counts are identical (§1), so no
  answer text was altered by it in these arms.
- The single abstention difference is Q19, and the trace shows it
  upstream: arm H's synth produced the full answer, arms I and J's
  synth produced `"ANSWER: insufficient information"` for the same
  query. Verify accepted in all three.
- Token and latency follow answer length, which follows the same synth
  variance.

**Layer-intent card** (rule #2, `v0.4-alpha-6-sector-llm-ablation-matrix.md`
§5.6). Layer `Cognitive stages`, primary axis `graded_answer`,
prerequisites met (verify ran in all three arms — 18 `reason:verify`
episodes each):

```json
{
  "layer_id": "Cognitive stages",
  "flag": "JAMES_ENABLE_VERIFY", "flag_value": "1",
  "design_intent": "Multi-step planning / reflection / verification",
  "primary_axes": ["graded_answer"],
  "regression_check_axes": ["path_coverage", "abstention_f1",
                            "token_cost", "latency_cost"],
  "prerequisites_met": true,
  "verdict": "zero",
  "reason": "verify's recommendation counts are identical across all three arms; every axis delta tracks synth variance upstream of the stage"
}
```

## 3. What each PR fixes, and the evidence for it

### PR A — an injection echo must have a source (`3b39a0d`)

`INSTRUCTION_INJECTION_PATTERNS` is the **input**-side list. verify ran
it over the **output**, where four of its six patterns are ordinary
answer content: citing a source, telling a user to run the following
command, closing a session, displaying data. On 2026-09-24 that cost a
correct answer — Q17 "Anthropic의 CEO는 누구야?" was answered
"Dario Amodei", sourced from a document title, and the user received the
refusal message while the grounding check on the same answer said
`grounded: true`.

An echo has a source. The scan now reports one only when the matched
span is present in the evidence, compared on lowercased,
whitespace-collapsed text so a reflowed copy still counts.

**Known residual, pinned by a test rather than hidden**: quoting a
runbook that genuinely contains "다음 명령을 실행하세요" is corroborated,
so it still blocks. Narrowing the pattern list for output use, or
downgrading `block` to `annotate` for the ambiguous patterns, is a
trust-boundary decision and an operator call.

**Prerequisite**: `verify.py` was 20,008 B against rule #5's 20 KB cap —
472 B of headroom — so it was split into a package first. Pure move;
the full suite passes with **no test edits**, which is the evidence.
`_is_korean` was missed from the façade on the first pass and
`tests/test_i18n_language_detection.py` caught it.

### PR B — verify checks the whole answer, and acts on a bare claim (`1207b1d`)

Three gaps, all the same shape, all surfaced by one traced answer —
"Alex Karp", offered as Anthropic's CEO (2026-09-26 report §4.1):

1. `len(answer) < 30 → accept` ran before anything, so a 9-character
   answer skipped the security scan *and* the fact check. The floor was
   backwards: a short answer is usually a bare factual claim, the kind
   that most needs grounding. Only an empty answer short-circuits now.
2. `ANNOTATE_THRESHOLD = 2` meant one unsupported claim never
   annotated, and a bare claim has exactly one. Same number, inverted
   job: `BARE_CLAIM_ANSWER_CHARS = 30` is the length at or under which
   an answer is one claim. Long answers keep the threshold.
3. `context[:2000]` against synth's 8000: a claim supported only by the
   unseen tail was annotated "not directly supported by the source
   data" for no reason but the window. `answer[:2000]` was the mirror —
   claims past it were never checked, and the measured answer p95 on
   2026-09-26 was 6133 characters. Both now read
   `core/reasoning/evidence_budget.py`, shared with the critique budget
   from #1151 (#1149's lesson: copied guards drift), and truncation
   states itself inside the prompt.

## 4. What this licenses — and what it does not

**Licensed**

- Neither change moved verify's decisions on the healthy path (§1).
- Both defects are fixed at the code level, each pinned by tests that
  encode the traced failure.

**Not licensed**

- ❌ "The echo false positive is fixed" **as a measured claim**. It did
  not occur in any arm here. The fix is unit-tested and mechanically
  sound; it has not been observed correcting a live block.
- ❌ "The bare-claim annotation works" as a measured claim. It never
  fired — the only short answer missed the boundary by 2 characters.
- ❌ Any reading of the graded / token / latency deltas (§2). They sit
  on synth variance and they happen to flatter the PRs.
- ❌ "Verify is fixed." Q17 is `fn_hallucination` in all three arms, as
  in the seven before them.

## 5. Follow-ups

1. **The output-echo pattern list.** Corroboration removes the
   model's-own-framing class of false positive, not the
   document-genuinely-contains-instruction-text class. Operator
   decision: curate an output-specific pattern set, or downgrade the
   ambiguous patterns from `block` to `annotate`.
2. **`BARE_CLAIM_ANSWER_CHARS = 30` is inherited, not derived.** It is
   the old gate's number reused. A 32-character answer sat just outside
   it in this very run. Worth deriving from the claim count the fact
   check returns rather than a length, if this path ever fires often
   enough to measure.
3. **n = 3, and a fixture that actually triggers a block**, before
   claiming either fix works in vivo. The step7 suite blocks
   intermittently at best.
