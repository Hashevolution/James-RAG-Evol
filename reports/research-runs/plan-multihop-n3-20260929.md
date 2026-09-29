# plan on multi-hop — the suite built for it: no gain, and it makes the model answer a plan nobody wrote (2026-09-29, n=3)

> **Why**: plan measured flat on step7 (`plan-only-n3-20260928.md`), and
> that report refused to recommend turning it off because step7 is
> almost all single-hop — plan's intent, *decomposing multi-step
> questions*, was untested. This is the test.
>
> **Design**: 6 captures on `main` `2650f3c`, interleaved PLAN ↔ NOPLAN
> ×3, in the isolated `workspaces/hotpot_eval` (MultiHop-RAG, 100
> questions: 25 each inference / comparison / temporal / null), ~6 h 25
> min. All 600 answers healthy. **reflect off and verify on in both
> arms** — the production configuration. NOPLAN sets
> `JAMES_ENABLE_PLANNER=0` explicitly (`config.py:52` reload).
>
> A 5-query smoke ran first to prove the workspace wiring (sources came
> back as `multihop_0175_…`, not the production corpus) and to measure
> the real per-query cost the scope decision was based on.
>
> | run | plan | reflect | verify | timeouts |
> |---|---:|---:|---:|---:|
> | PLAN r1 / r2 / r3 | 47 / 50 / 49 | 0 | 300 | 2 / 0 / 0 |
> | NOPLAN r1 / r2 / r3 | **0 / 0 / 0** | 0 | 300 | 1 / 0 / 0 |

## 1. Result

| axis | PLAN median | band | NOPLAN median | band | Δ |
|---|---:|---:|---:|---:|---:|
| Path Recall | 0.4111 | 0.0122 | 0.4000 | 0.0089 | −0.0111 |
| Graded Answer | 0.2633 | 0.0467 | 0.2967 | 0.0200 | +0.0334 |
| **Abstention F1** | 0.3556 | 0.0700 | **0.4396** | 0.0310 | **+0.0840** |
| Token Cost | 1501.3 | 131.6 | 1338.2 | 67.6 | −163.1 |
| **Latency** | 40.1 s | 0.7 | **36.4 s** | 0.3 | **−3.7 s (−9%)** |

**Abstention does not overlap**: all three NOPLAN runs (0.409–0.440)
sit above all three PLAN runs (0.326–0.396). Latency bands are under a
second, so −3.7 s is unambiguous. 100 questions per run made the bands
far tighter than step7's 20.

## 2. By question type — where plan was supposed to help

| type | axis | PLAN | NOPLAN | Δ | overlap |
|---|---|---:|---:|---:|---|
| inference | graded | 0.347 | 0.427 | +0.080 | partial |
| temporal | graded | 0.307 | 0.360 | +0.053 | partial |
| comparison | graded | 0.267 | 0.267 | 0.000 | — |
| **null** | **abstention** | 0.780 | **0.889** | **+0.108** | **none** |

On the three multi-step types plan is flat or worse. On null questions
it is clearly worse. Query-level: **7** null questions hallucinate in
≥ 2 of 3 PLAN runs while abstaining in ≥ 2 of 3 NOPLAN runs; **1** goes
the other way.

## 3. Mechanism — the model answers a plan it thinks the user wrote

`generator.py` prepends the plan to the system prompt:

```
[추론 계획]
1. <subtask> …
위 계획에 따라 단계별로 답변하라.
```

The model reads it as the user's own plan and responds to *that*:

> *"Hello! I appreciate you laying out such a detailed and methodical
> plan. It shows great diligence…"* — Q57, PLAN r3
>
> *"Based on the detailed plan you provided, I have completed the
> necessary analysis."*
>
> *"It sounds like you are tackling a complex, multi-layered
> investigation, and I appreciate your methodical approach."* — Q70

**34 of 300 PLAN answers (11%) address a plan the user never wrote.
0 of 300 NOPLAN answers do.** On a null question the meta-response
carries no abstention phrase, so it scores as an answer; some go on to
fabricate — Q64 PLAN r1: *"The first letter of the Asian country is
**I**, representing India."* The same question abstained in 2 of 3
NOPLAN runs.

This is a **known defect class, mitigated in one mode only**. The
comment at `generator.py` (2026-06-05 §24) records that the same
directive produced *"Hello, I am JAMES. I will follow the plan
step-by-step"* openings — 23 of 28 unstrippable meta-mode answers in
PM-15 — and fixed it by skipping the plan **in terse mode**. Natural
style, the default, still receives it.

## 4. Two findings independent of plan

**verify is weak on multi-hop.** Annotation axis, strict mode, with the
multi-hop fixture: recall **0.16–0.20** (it flags 25–32 of ~155 wrong
answers), precision 0.63–0.73. Unlike step7 there are strict-mode false
alarms (12–15): verify annotating **correct refusals**, because the
fact-check lists the refusal text itself ("insufficient information")
as an unsupported claim.

**The largest multi-hop quality problem is over-abstention, and it is
not plan's.** Both arms falsely abstain on **~47% of answerable
questions** (144 and 141 of 300). About **half of those** (68 and 71)
still contain at least one gold signal — the model found the answer and
wrapped it in a refusal. The smoke showed the shape:

> *"ANSWER: insufficient information\nThe context identifies Sam
> Bankman-Fried as the individual facing charges…"* — the question asked
> exactly who that was.

"At least one gold signal" is a loose criterion, so the half is an
approximation; the 47% is not.

## 5. Layer-intent verdict for plan

Stage `plan`, primary axis `graded_answer`, prerequisites met. Plan's
contribution (PLAN − NOPLAN): graded −0.033 (flat, overlapping),
abstention −0.084 (**non-overlapping regression** on a regression-check
axis), latency +3.7 s.

§5.6: *"any regression_check_axes has verdict_contribution ==
regression → reject."*

```json
{
  "layer_id": "Cognitive stages / plan",
  "suite": "multihop_rag (100q)",
  "primary_axes": ["graded_answer"],
  "per_axis_delta": {
    "graded_answer": {"delta": -0.0334, "verdict_contribution": "primary-flat"},
    "abstention_f1": {"delta": -0.0840, "verdict_contribution": "regression"},
    "latency_cost":  {"delta": +3.7,    "verdict_contribution": "cost"}
  },
  "verdict": "reject",
  "reason": "on the suite built for its intent, plan regresses abstention without overlap and costs 9% latency, via a traced mechanism"
}
```

The first `reject` of this arc — and on plan's own ground, which is what
step7 could not give.

## 6. What this licenses — and what it does not

**Licensed**

- **plan off**, as an operator recommendation. Like reflect, it is off
  by default in code (`planner.py`: `== "1"`); the deployment `.env`
  turns it on.
- The plan-injection defect (§3) is real, measured at 11%, and would
  need fixing before plan is re-enabled in any mode — the plan must not
  read as the user's words.
- Over-abstention (§4) is the next quality target on multi-hop, larger
  than any stage effect measured in this arc.

**Not licensed**

- ❌ "Planning cannot help multi-hop." This is *this* planner, injected
  *this* way. A plan that is not framed as user text is untested.
- ❌ Reading the graded deltas by type as effects — they overlap.
- ❌ A precise size for the "found it but refused" half (§4).

## 7. Where the cognitive stages end up

| stage | cost / query | step7 | multi-hop | status |
|---|---:|---|---|---|
| reflect | ~30 s | none; Q19 harm | — | **off** (`.env`, 2026-09-28) |
| plan | ~4–5 s | none | **regresses abstention; 11% meta-answers** | recommend **off** |
| verify | ~9 s | catches 3–6 of 9–11 wrong | recall 0.16–0.20; flags correct refusals | on |

With reflect and plan off: ~36 s/query on multi-hop, ~34 s on step7,
against 69.6 s at the start of the arc.
