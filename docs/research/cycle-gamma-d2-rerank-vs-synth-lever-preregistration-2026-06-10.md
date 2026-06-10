# Cycle γ D2 — rerank vs synth lever: pre-registration

**Date**: 2026-06-10 (written BEFORE the run — post-hoc fit barred)
**Status**: LOCKED before any D2 run.

> **Why**: D1b's correction showed retrieval is not the bottleneck —
> retrieve(top-8) catches both supporting paragraphs 13/25. The loss is
> downstream. A static pass over the 25 queries splits it:
>
> | stage | both-supporting | loss |
> |---|---|---|
> | retrieve top-8 | 13/25 | — |
> | after rerank (top-5, what synth sees) | 8/25 | rerank drops 5 (lever 1) |
> | final gold-in-answer (R0) | 2/25 | synth loses 6 of 8 (lever 2) |
>
> Both levers are live; synth-noise (8→2) looks larger than rerank
> (13→8). This run confirms it live.

---

## 1. Verdict question

**If we preserve both supporting paragraphs into the synth context
(rerank OFF + wide top_k), does gold-in-answer rise — or does synth
still abstain on the distractor-laden context?**

- Rises → **rerank/truncation was the binding lever** (lever 1): keep
  the evidence and the model solves it.
- Stays low → **synth noise-robustness is the binding lever** (lever 2):
  the model gets the supporting paragraphs but can't use them amid
  distractors. Re-points to the synth/abstention layer (Phase E-min).

## 2. Cells

| Cell | env | what synth sees |
|---|---|---|
| **R0** (baseline, measured) | default 8/5, rerank ON | rerank top-5 |
| **D2** (this run) | `JAMES_RETRIEVE_TOP_K=16` + `JAMES_RERANK_TOP_K=16` + `JAMES_DISABLE_RERANK=1` | all 16 retrieved docs (rerank bypassed → docs[:16]) |

D2 maximises both-supporting preservation (≈ retrieve top-16 coverage)
at the cost of maximal distractor noise — exactly the trade-off the
verdict question probes.

- Model: mxtral:8x7b, n=25, same `cycle_gamma_musique_ans` workspace.
- Paired against the existing R0 JSON.

## 3. Decision rule (LOCKED)

Primary axis = **gold-substring-in-answer** (em/f1 response-style
confounded). Baselines: R0 8%, oracle ceiling 72%.

| Result | Verdict |
|---|---|
| D2 gold-in-answer **≥ 30%** | **rerank was the binding lever** — preserving evidence solves it. Next = rerank multi-hop fix (per-subquery rerank / rerank disabled for multi-hop intent), measure cost + RGB abstention side-effect |
| D2 gold-in-answer **15–30%** | **both levers matter** — partial lift from evidence preservation; residual is synth-noise. Pursue both |
| D2 gold-in-answer **< 15%** (≈ R0) | **synth noise-robustness is the binding lever** — model gets the evidence (both 13/25 in context) but still abstains. Re-point to synth/abstention; connect to Phase E-min (rerank/cog_stages × abstention). Retrieval-side work is done |

### Honesty guards (pre-stated)
1. n=25, mxtral single model; no cross-model claim until replicated.
2. em/f1 forbidden as standalone headline.
3. **default-OFF stays** — rerank ON / top_k 8/5 remains production
   default regardless of result; rerank helps RGB abstention (Phase
   E-min) so a global flip needs the multi-axis trade-off, not this
   single bench.
4. No post-hoc threshold movement. No joint-piece framing.
5. ⭐⭐ ceiling (external bench; rerank/multi-hop-RAG is prior art).

## 4. Execution

```
1. D2 run: JAMES_RETRIEVE_TOP_K=16 JAMES_RERANK_TOP_K=16
   JAMES_DISABLE_RERANK=1, mxtral n=25
2. compare gold-in-answer vs R0 (8%) + oracle (72%) → §3 verdict
3. handover + (no code — env-gate already exists; this is a measurement)
```

Estimated: ~20 min (16 docs to synth = longer prompts).

---

*Committed before the run. Commit hash = pre-registration evidence.*
