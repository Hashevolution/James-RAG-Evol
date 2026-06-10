# Cycle γ D1 — query-decomposition retrieval: design + pre-registration

**Date**: 2026-06-10 (written BEFORE D1 is implemented — post-hoc fit
barred, same discipline as Phase C.2 pre-registration)
**Status**: LOCKED before any D1 measurement run. Thresholds / verdict
rules below do not change after measurement; if they must, the run is
demoted to exploratory.

> **Why D1**: Phase C.2 (`v0.4-cycle-gamma-phase-c2-musique-retrieval-bottleneck-2026-06-10.md`)
> proved with 3 measurements that **single-shot dense retrieval is the
> dominant multi-hop bottleneck** — the model solves MuSiQue 2-hop when
> given the supporting paragraphs (oracle gold-in-answer 72%) but JAMES
> R0 retrieval only surfaces them 8% of the time. D1 makes retrieval
> reach the 2nd hop.

---

## 1. Design

### 1.1 Mechanism (MVP = query decomposition)

JAMES's `orchestrator.retrieve` already runs a **multi-query** merge:
`original` + `expanded` + `keyword`, each through `hybrid_search`, then
concat + dedup. All three are variants of the *same* question, so the
2nd hop (query-dissimilar) is never reached.

D1 adds **sub-question paths** to that query set:

```
multi-hop query
   │
   ├─ (D1) LLM decomposer → [sub_q1, sub_q2, ...]   ← NEW
   │
   └─ orchestrator.retrieve(queries = original + expanded + keyword + sub_q*)
        → hybrid_search each → merge → dedup → rerank → synth
```

`sub_q2` ("Who is the spouse of Steve Hillage?") is query-similar to the
hop-2 supporting paragraph, so it surfaces what `original` cannot.

### 1.2 Wiring

- New module `core/retrieval/query_decomposer.py` (LLM decompose via
  `GemmaClient`, the model passed through from the engine call).
- Pipeline STEP 0.5c (after entity-anchor + query-rewrite, before
  `run_loop_0_retrieve`): if enabled, decompose and stash sub-questions
  on `loop_state` so `run_loop_0_retrieve` adds them to the retrieve
  query list.
- **env-gate `JAMES_ENABLE_QUERY_DECOMP`** (opt-in). Unset → no
  decompose call, retrieve query set byte-identical to today
  (mother-platform principle 3: short-answer/specialised behaviour is an
  opt-in option layer, not a default flip — flip is gated on a later
  multi-axis measurement, same as the top_k env-gate).
- Failure isolation: decompose exception → fall back to the original
  query set (D1 must never block retrieval).

### 1.3 Decompose prompt (fixed for the measurement)

> "Break the following question into the minimal ordered sub-questions
> needed to answer it step by step. Output one sub-question per line, no
> numbering, no explanation. If it is already a single-hop question,
> output it unchanged."

Cap: ≤ 4 sub-questions; on empty/garbage output fall back to the
original query (no-op).

---

## 2. Measurement design (methodological-chain labelling)

- **Verdict Q**: Does query decomposition (D1) lift gold-supporting
  retrieval coverage and gold-in-answer on MuSiQue-ans 2-hop, vs
  single-shot R0, toward the oracle ceiling (72%)?
- **Diagnostic Q**: If it does NOT lift, why? — (a) decomposer produces
  bad sub-questions, (b) sub-q retrieval still misses hop2, (c) coverage
  rises but synth still abstains. Inspect raw sub-questions + per-query
  supporting recall.
- **Fixture**: same 25 MuSiQue-ans queries, same workspace
  (`cycle_gamma_musique_ans`), paired against the existing R0 JSONs.
  Verdict-grade (external standard bench + official scorer, self-eval
  trap pass).
- **Primary axis**: **gold-substring-in-answer** (em/f1 are
  response-style-confounded per Phase C.2 §3.3 — the model answers in
  NATURAL prose; substring is the honest capability signal).
- **Secondary axis**: **supporting-paragraph recall** (does decompose
  surface the hop-2 supporting paragraph? the direct mechanism check).
- **Tertiary (diagnostic only)**: abstain rate, em, f1 (reported, not
  verdict-bearing).

### 2.1 Baselines (already measured, Phase C.2)

| Metric | R0 single-shot (mxtral) | oracle ceiling (mxtral) |
|---|---|---|
| gold-in-answer | 8% (2/25) | 72% (18/25) |
| abstain | 76% | 24% |
| supporting recall (top-3 shown) | 0.60 | — (all support fed) |

---

## 3. Decision rule (LOCKED)

Δ = D1 − R0 on the **same 25 queries**, mxtral first.

| Result | Verdict | Follow-up |
|---|---|---|
| gold-in-answer **≥ 30%** (≥ +22pp over R0's 8%) AND supporting recall **≥ 0.75** | **D1 WORKS** — decomposition reaches hop2 | cross-model (gemma4/llama) → if holds, design D1 as an option layer + measure cost (latency/token) for a default-flip case |
| gold-in-answer 15–30% | **PARTIAL** — decompose helps but incompletely | diagnose which hop2s still miss; consider iterative round 2 |
| gold-in-answer < 15% OR supporting recall flat (≤ 0.65) | **D1 INSUFFICIENT** | decomposition is not enough; pivot to iterative retrieval (retrieve→read→re-query) — separate pre-registration |
| supporting recall ↑ but gold-in-answer flat | **retrieval fixed, synth/abstention is now the limiter** | re-point to synth/abstention layer, not retrieval |

### Noise / honesty guards (pre-stated)

1. n=25, mxtral single model for the first verdict; **no cross-model
   claim until gemma4+llama replicate** (`feedback_n1_verdict_inflation`,
   cross-model rule).
2. **em/f1 forbidden as standalone headline** (response-style artifact).
   gold-in-answer + supporting recall are the verdict axes.
3. **default-OFF stays** until a multi-axis measurement (MuSiQue gain vs
   RGB abstention loss vs latency/token cost) licenses a flip. D1 adds
   an LLM call + N extra retrievals — cost is real and must be weighed.
4. No post-hoc threshold movement. No joint-piece framing
   (`feedback_eval_cycle_vs_collab_arc_separation`).
5. Honest tier ceiling: ⭐⭐ (external bench), ⭐⭐⭐ barred — iterative /
   decomposed multi-hop RAG is prior art (IRCoT, self-ask, decomp-RAG);
   JAMES contribution = reproducible measurement on its own stack, not
   mechanism novelty.

---

## 4. Execution order

```
0. live smoke: 1 query with JAMES_ENABLE_QUERY_DECOMP=1 — confirm
   sub-questions are generated + added to retrieve set (wiring, not verdict)
1. implement core/retrieval/query_decomposer.py + STEP 0.5c wiring + env-gate
2. unit test: flag-OFF byte-identical query set; flag-ON adds sub-q paths
3. D1 run: mxtral n=25 on cycle_gamma_musique_ans
4. compare vs R0 (gold-in-answer, supporting recall) → §3 verdict
5. if D1 WORKS → cross-model; else → diagnose / iterative pivot
6. handover + PR (env-gate default OFF)
```

Estimated: implementation ~1–2h; measurement ~15 min/run.

---

*Committed before implementation. Commit hash = pre-registration evidence.*
