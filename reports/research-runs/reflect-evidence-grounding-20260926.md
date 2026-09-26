# Reflect grounding — the fix, and the two things the measurement rejected (2026-09-26)

> **Design**: pre-fix / post-fix arms, **same session, back-to-back**,
> via `scripts/qvt_capture_baseline.py --n-runs 1 --output <arm>`. Arms
> differ by **commit**, not by env, so each artifact's `git_sha` records
> which code produced it. Every integrity guard from #1141–#1149 applied;
> all seven arms report 18/18 healthy answers.
>
> **n = 1 per arm.** The aggregate is a regression check, not a verdict.
> The claim rests on per-query `audit_log` traces (§2), the same method
> that found the defect.

## 1. What was wrong

`reports/research-runs/cognitive-stages-contrast-20260924.md` §4.1
traced reflect deleting a correct, grounded answer. `CRITIQUE_PROMPT_*`
was formatted with `{query}` and `{draft}` only, so the only yardstick
the critique had for *"명백히 틀린 사실"* was the model's training data.
The pre-fix critique said so itself, in arm D3:

> **심각한 오류 (Hallucination):** 현재 시점(또는 **일반적인 지식 범위**)에서
> GPT-6 모델이 2026년 4월 15일에 공식 발표되었다는 객관적이고 검증[되지 않음]

Evidence newer than the model — the normal case for an internal
knowledge base — therefore reads as a hallucination.

## 2. Q14 across seven arms — the result the fix rests on

| arm | sha | code | Q14 | Q17 | Q20 | abst_f1 | graded |
|---|---|---|---|---|---|---:|---:|
| A-0924 | `65d25e4` | pre-fix | **fp_incorrect_abstention** | fn_hallucination | tn_answer | 0.5000 | 0.6667 |
| D-pre | `f8603cc` | pre-fix | **fp_incorrect_abstention** | fn_hallucination | tn_answer | 0.5000 | 0.7000 |
| E-nofix | `2aba26a` | critique only | tn_answer | fn_hallucination | tn_answer | 0.5714 | 0.5833 |
| D2-pre | `f8603cc` | pre-fix | **fp_incorrect_abstention** | fn_hallucination | tn_answer | 0.5000 | 0.6833 |
| **F-guard** | **`d4d27cc`** | **shipped** | **tn_answer** | fn_hallucination | tn_answer | **0.5714** | **0.6500** |
| D3-pre | `f8603cc` | pre-fix | **fp_incorrect_abstention** | fn_hallucination | tn_answer | 0.5000 | 0.6500 |
| G-final | `b152fc7` | +revise rule | tn_answer | fn_hallucination | **fp_incorrect_abstention** | 0.5000 | 0.6333 |

**Q14: false abstention in 4/4 pre-fix arms, answered in 3/3 post-fix
arms.** The mechanism flipped with it — arm G's critique reads
*"자료 미근거 / 내부 모순: 없음. 답변의 모든 내용은 [근거 자료]에 명확하게
근거하고 있으며"*, and the grounded fact shipped.

## 3. Quality Delta vs `baseline_6deca66`

Paired arms **D2 → F** (same session, consecutive, shipped code).
Noise bands from `baseline_6deca66.json` `aggregate.*.noise_band`.

| axis | D2 (pre-fix) | F (shipped) | Δ | band | contribution |
|---|---:|---:|---:|---:|---|
| Path Recall | 0.9091 | 0.9091 | 0.0000 | 0.0455 | within-noise |
| **Graded Answer** | 0.6833 | 0.6500 | −0.0333 | 0.0667 | **primary-flat** |
| Abstention F1 | 0.5000 | 0.5714 | +0.0714 | 0.0714 | improvement (at the band edge) |
| Token Cost | 1578.5 | 1510.8 | −67.7 | 343.45 | within-noise |
| Latency Cost | 64.56 | 64.95 | +0.39 | 3.40 | within-noise |

**Layer-intent card** (CLAUDE.md rule #2, `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md` §5.6):

```json
{
  "layer_id": "Cognitive stages",
  "flag": "JAMES_ENABLE_REFLECT", "flag_value": "1",
  "design_intent": "Multi-step planning / reflection / verification",
  "primary_axes": ["graded_answer"],
  "regression_check_axes": ["path_coverage", "abstention_f1",
                            "token_cost", "latency_cost"],
  "prerequisites_met": true,
  "prerequisite_notes": "reflect ran in both arms — 33 and 31 reason:reflect events in audit_log",
  "per_axis_delta": {
    "graded_answer":  {"delta": -0.0333, "noise_band": 0.0667, "verdict_contribution": "primary-flat"},
    "path_coverage":  {"delta":  0.0000, "noise_band": 0.0455, "verdict_contribution": "within-noise"},
    "abstention_f1":  {"delta": +0.0714, "noise_band": 0.0714, "verdict_contribution": "within-noise"},
    "token_cost":     {"delta": -67.7,   "noise_band": 343.45, "verdict_contribution": "within-noise"},
    "latency_cost":   {"delta":  +0.39,  "noise_band": 3.40,   "verdict_contribution": "within-noise"}
  },
  "verdict": "zero",
  "reason": "primary axis (graded_answer) within noise and no regression-check axis regressed"
}
```

**The mechanical verdict is "zero", and that is reported as-is.** Two
honest notes, neither of which upgrades it:

- The §5.6 table assigns cognitive stages `graded_answer` as primary
  because it was written for **layer ablations**. This PR is a **defect
  fix**, and the defect lives on `abstention_f1` — a correct answer
  turned into a refusal. Scored on the axis the defect actually
  occupies, the delta is +0.0714 against a 0.0714 band: an improvement
  sitting exactly on the boundary, which at n = 1 is not a claim.
- `graded_answer` moved on **9 of 20 queries in both directions**
  between the first pre/post pair, on substring signals over generated
  prose. A ±0.03 aggregate on that axis at n = 1 carries no information.

## 4. Two changes the measurement rejected

Both were written during this arc and are **not in the shipped diff**.

### 4.1 The first fix introduced a hallucination (caught by arm E)

Arm E, Q17 *"Anthropic의 CEO는 누구야?"*: retrieval returned Palantir
material, synth correctly answered *"insufficient information"*, and the
newly grounded critique called that *"factually incorrect and misleading
because the provided evidence explicitly an[swers it]"*. Revise shipped
**"Alex Karp"** — Palantir's CEO.

Removing the training-data yardstick also removed the check that had
been rejecting the wrong entity, and nothing replaced it. Verify never
saw it: at 9 characters the answer fell under
`MIN_ANSWER_LEN_FOR_VERIFY = 30` (`core/reasoning/verify.py:286`) and
was skipped entirely.

Fixed in the shipped diff (`d4d27cc`): when the evidence does not cover
the subject the question asks about, a draft reporting missing
information is the correct answer, and supplying the same kind of fact
about a different subject is the hallucination. "Missing core" is scoped
to the question's subject for the same reason.

### 4.2 The revise removal rule was an abstention dial-move — reverted

`b152fc7` made revise **delete** a claim the critique flagged as
unsupported instead of attaching a citation to it. Arm G measured it:

- **It fixed nothing new.** Q17, the case it was written for, is
  `fn_hallucination` in **all seven arms**, including every pre-fix one,
  and stayed that way under the rule. It is a pre-existing failure this
  branch neither causes nor fixes.
- **It cost Q20.** On *"RAG 기법을 사용하는 코딩 도구 3 개를 알려줘"* synth
  answered correctly; the critique noted the evidence ties only one of
  the four listed tools directly to RAG; revise applied the new rule and
  refused: *"제공된 자료만으로는 … 3개를 명확하게 확인할 수 없습니다."*
- `abst_f1` returned to the pre-fix 0.5000. Q14's win was handed
  straight back.

This is `feedback_abstention_dial_vs_pareto`: the dial moved, the curve
did not. Reverted in `7b913e3`; the branch head is byte-identical to the
`d4d27cc` that arm F measured.

## 5. What this licenses — and what it does not

**Licensed**

- reflect no longer deletes a fact its own evidence supports. Q14:
  4/4 → 3/3, with the critique's reasoning flipping in the trace.
- No axis regressed past its noise band (§3).

**Not licensed**

- ❌ "Reflect is fixed." One traced defect is fixed. Q17 is
  `fn_hallucination` in all seven arms and is untouched by this work.
- ❌ Any claim from the aggregate deltas. n = 1 per arm, and
  `graded_answer` flips on ~half the suite between runs.
- ❌ Reading +0.0714 on abstention_f1 as an effect. It equals the band.

## 6. Follow-ups this arc surfaced

1. **`MIN_ANSWER_LEN_FOR_VERIFY = 30` lets a short wrong answer skip
   verification entirely** (§4.1). "Alex Karp" — 9 characters, confidently
   wrong, never checked. Belongs with the verify PR.
2. **Verify's fact-check reads `context[:2000]`** (`verify.py:349`) while
   synth writes from `JAMES_SYNTH_CONTEXT_CHARS` (default 8000). A claim
   supported only by the unseen tail can be annotated "unsupported" —
   the same shape as the defect fixed here, in the next stage over. The
   critique's budget was tied to the synth variable precisely to avoid
   this; verify's was not.
3. **n = 3 same-session pair** before any further change to reflect's
   prompts or budgets.
4. `prompts.py` is at 17.4 KB against the 20 KB rule #5 cap. The next
   prompt addition should split the file first.
