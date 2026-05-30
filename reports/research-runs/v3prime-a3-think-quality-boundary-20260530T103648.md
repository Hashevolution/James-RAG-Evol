# A3 — think-mode quality boundary (gemma4:e4b, 5 cognitive stages)

**Date**: 2026-05-30T10:27:28.730184+00:00
**Model**: gemma4:e4b  **Cap**: 4096  **Temp**: 0.2  **n/cell**: 5
**Closes**: §17.5.3 of v3prime-cross-family-final-2026-05-29.md

## Per-stage verdicts (feeds A2 per-stage think policy)

| Stage | Fixture | think=ON eval | think=OFF eval | reclaim | primary quality (ON / OFF) | verdict | rationale |
|---|---|---|---|---|---|---|---|
| planner | easy | 699 | 94 | -605 | sub=3/json=1.0 / sub=3/json=1.0 | **think=OFF safe** | quality tie (Δ=+0.00); budget reclaim 605 tok |
| planner | hard | 947 | 182 | -766 | sub=4.2/json=1.0 / sub=4/json=1.0 | **think=OFF safe** | quality tie (Δ=+0.04); budget reclaim 766 tok |
| reflect | easy | 1353 | 473 | -880 | cov=3/dec=1.0 / cov=3/dec=1.0 | **think=OFF safe** | quality tie (Δ=+0.00); budget reclaim 880 tok |
| reflect | hard | 1205 | 519 | -686 | cov=3/dec=1.0 / cov=3/dec=1.0 | **think=OFF safe** | quality tie (Δ=+0.00); budget reclaim 686 tok |
| verify | easy | 1203 | 24 | -1179 | json=1.0/jdg=0.6/uns=0.4 / json=1.0/jdg=1.0/uns=0 | **think=OFF wins** | think=OFF higher quality by +0.40; reclaim 1179 tok bonus |
| verify | hard | 990 | 88 | -902 | json=1.0/jdg=1.0/uns=3 / json=1.0/jdg=1.0/uns=2.4 | **think=OFF safe** | quality tie (Δ=+0.00); budget reclaim 902 tok |
| synthesis | easy | 467 | 60 | -407 | dec=0.0,chars=315.4 / dec=0.0,chars=295.2 | **think=OFF safe** | quality tie (Δ=+0.00); budget reclaim 407 tok |
| synthesis | hard | 1135 | 539 | -596 | ent=3/3,conf=0.4 / ent=3/3,conf=1.0 | **think=OFF wins** | think=OFF higher quality by +0.60; reclaim 596 tok bonus |
| query_rewriter | easy | 530 | 29 | -501 | json=1.0 / json=1.0 | **think=OFF safe** | quality tie (Δ=+0.00); budget reclaim 501 tok |
| query_rewriter | hard | 606 | 24 | -582 | json=1.0/anchor=0.0 / json=1.0/anchor=0.0 | **think=OFF safe** | quality tie (Δ=+0.00); budget reclaim 582 tok |

## Reading

- `eval` = `eval_count` mean across n samples. think=ON includes the
  default-on hidden thinking trace (§16); think=OFF disables it.
- `reclaim` = budget recovered if we flip the stage to think=OFF.
- Primary quality signal differs per stage (see grader docstrings
  in the driver). Verdict heuristic: |Δquality| < 0.15 → OFF safe.
- Hard fixtures planted explicit reasoning targets so a non-
  reasoning answer is detectable (multi-hop conditional, planted
  defects, hallucinated claims, 3-way comparison with conflict,
  multi-hop entity anchor). Easy fixtures are the §16 baseline.

## A2 feed-through

Stages with **think=OFF safe** verdict on hard fixture are
candidates for A2 to force `think=false` in the call site
(reclaims ~85% of budget per call on e4b). Stages with
**think=ON needed** should keep the default (and the per-stage
cap must stay ≥ ~500 to leave the thinking trace room).

Artifact: this driver is self-contained, deterministic graders
only. No LLM-judge dependency. v2 (LLM-judge with gemma3:12b as
tie-breaker) is a follow-up if any cell lands in `ambiguous`.