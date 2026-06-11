# LRB v0.2.1 S2 — claude-haiku-4-5 vanilla R@1 reproducibility band

> **Date**: 2026-06-12 (audit-trail closure following 6h autonomous loop)
> **Honest tier**: ⭐ small finding, supports existing claim
> **Scope**: LRB v0.2.1 cross-model S2 cell (claude-haiku-4-5, vanilla SUT,
>           llm-grounded mode)

## 1. Finding

The **vanilla SUT under llm-grounded mode** (where claude-haiku-4-5 is the
re-ranking LLM) shows R@1 run-to-run variance of ~10pp between two
back-to-back full runs:

| Run | started_at (UTC) | elapsed | R@1 | n |
|---|---|---|---|---|
| 154815Z | 2026-06-11T16:13:10 | 1494.5s | **0.5125** | 80 |
| 155045Z (canonical) | 2026-06-11T16:14:39 | 1434.1s | **0.6125** | 80 |

Both runs:
- same `fixture_sha = 9f40d2e0a16f4a8e776858ec5191626c6b09f32f2394dd3dd1e71c73427bb98d`
- same scenario_spec `v0.1.0-draft-phase-b`
- ran ~1.5 minutes apart
- completed normally (no timeout, no early exit)

Per-record retrieval order **diverged on 29/80 queries** (36%), driven by
claude-haiku API output non-determinism in the LLM-grounded reranker step.
Token-mode runs (Phase A/B, no LLM rerank) are fully deterministic across
≥4 timestamp-distinct reproductions (R@1 identical to 6 decimal places).

## 2. Per-category breakdown

| Category | 154815Z R@1 | 155045Z R@1 | Δ |
|---|---|---|---|
| current-director | 0.55 | 0.60 | +0.05 |
| current-policy | 0.375 | 0.625 | +0.25 |
| current-project-lead | 0.083 | 0.083 | 0 |

The variance is concentrated in `current-policy` (smallest n=8 bucket, so
even single-query flips move R@1 by 0.125). Larger categories show
smaller variance.

## 3. Effect on the v0.2.1 ⭐⭐⭐ 4/4 V<N<J claim

The FINAL handover §2 reports **V=0.6125** for the claude-haiku-4-5 S2
cell, using the canonical 155045Z run (chronologically last, complete).

Effect of using the lower bound (154815Z V=0.5125) instead:

| Model | V (lower bound) | V (canonical) | N | J | V<N<J holds? |
|---|---|---|---|---|---|
| claude-haiku-4-5 | 0.5125 | 0.6125 | 0.775 | 0.975 | **✓ yes (either V)** |

The 4/4 model V<N<J ⭐⭐⭐ tier claim is **robust** to this variance band:
even at the lower bound 0.5125, V < N (0.775) < J (0.975) by wide margins.

## 4. What this changes

**Updated honest framing for cross-model LLM-grounded S2 cells** (paper
methods section addendum):

> Vanilla SUT under llm-grounded mode inherits the re-ranking LLM's
> output non-determinism. For LLM APIs that do not expose `seed` /
> `temperature=0` controls (claude-haiku-4-5 is one such; OpenAI o4-mini
> and gemma3 via ollama with temperature=0 are deterministic), the
> vanilla R@1 should be reported as a ~10pp confidence band rather than
> a point estimate. We commit the bench.jsonl + result.json for both
> runs to the repository as audit-trail evidence.

**No change to claim**: V<N<J 4/4 cross-model preserved; ⭐⭐⭐ tier holds.

## 5. Artifacts

Committed in this audit-trail PR:

```
reports/external/lrb/v021-s2-claude-haiku-4-5-llm-grounded-20260611T154815Z.vanilla.{bench.jsonl,result.json}
reports/external/lrb/v021-s2-claude-haiku-4-5-llm-grounded-20260611T155045Z.vanilla.{bench.jsonl,result.json}
```

Removed (crash / scratch / token-mode-redundant reruns):

```
reports/external/lrb/phase-a-smoke-20260611T115731Z.{james,vanilla}.result.json     (crash, n=180 elapsed=0.1s no R@1)
reports/external/lrb/phase-a-smoke-20260611T115811Z.{james,vanilla}.result.json     (crash)
reports/external/lrb/phase-a-smoke-20260611T121245Z.{james,naive-supersede,vanilla}.result.json  (token-mode reproduction, identical R@1 to canonical 115935Z)
reports/external/lrb/phase-b-s1-20260611T121913Z.{james,naive-supersede,vanilla}.result.json     (token-mode reproduction, identical R@1 to canonical 121934Z)
reports/external/lrb/v021-s2-claude-haiku-4-5-llm-grounded-20260611T154519Z.vanilla.result.json  (crash, elapsed=0.23s)
reports/external/2wiki/dev-smoke-20260611T071506Z.result.json                       (crash, empty axes)
reports/external/alce/asqa-smoke-20260611T051847Z.result.json                       (crash)
reports/external/musique/track-c-musique-smoke-20260611T163526Z.james-gemma4-e4b.result.json (crash, empty axes)
```

## 6. Related

- FINAL handover: `docs/handovers/v0.4-autonomous-loop-FINAL-2026-06-12.md` §2
- v0.2.1 pre-registration: `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md`
- LRB design memo: `docs/design/v0.4-lrb-lifecycle-retrieval-benchmark-design.md`
- Memory: `project_lrb_phase_a_smoke.md`
- Honest framing rule: `memory/feedback_finding_size_honest_framing.md`
