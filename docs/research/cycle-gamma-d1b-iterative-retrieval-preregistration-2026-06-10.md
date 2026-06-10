# Cycle γ D1b — iterative retrieval: design + pre-registration

**Date**: 2026-06-10 (written BEFORE implementation — post-hoc fit barred)
**Status**: LOCKED before any D1b run.

> **Why D1b**: D1 (static query decomposition,
> `v0.4-cycle-gamma-d1-query-decomposition-results-2026-06-10.md`) was
> INSUFFICIENT — the hop-2 sub-question stayed an anaphora ("Who is the
> spouse of *that person*?") because decomposition splits BEFORE hop-1
> is answered. D1b resolves the pronoun by answering hop-1 first, then
> substituting into hop-2 before the 2nd retrieval round.

---

## 1. Design

### 1.1 Mechanism (iterative / self-ask style)

```
decompose → [q1 (hop-1), q2 (hop-2), ...]          (D1 decomposer, reused)
   │
round 1: retrieve(q1) → docs_1
   │
   ├─ extract: LLM("answer q1 using docs_1, ≤8 words") → a1   ("Steve Hillage")
   │
   ├─ resolve: substitute the anaphora in q2 with a1
   │           "Who is the spouse of that person?"
   │        →  "Who is the spouse of Steve Hillage?"
   │
round 2: retrieve(q2_resolved) → docs_2
   │
union(docs_1, docs_2) → existing rerank → synth
```

For ≥3-hop questions the extract→resolve→retrieve step iterates
(a1 feeds q2, a2 feeds q3), capped at the decomposer's ≤4 sub-questions.

### 1.2 Wiring + cost

- Reuse `core/retrieval/query_decomposer.py` (ordered sub-questions) and
  `core/orchestrator.py` `extra_queries` (union path).
- New: an iterative resolver that, per hop, (a) retrieves the hop's
  sub-q, (b) extracts a short answer via the model, (c) substitutes it
  into the next sub-q. Host = a new helper invoked from
  `run_loop_0_retrieve` (the decompose call site).
- **env-gate `JAMES_ENABLE_ITER_RETRIEVAL`** (opt-in, default OFF
  byte-identical). Independent of `JAMES_ENABLE_QUERY_DECOMP` (D1 static
  path stays available for comparison).
- **Cost** (must be measured, not hidden): per query =
  1 decompose call + (N−1) extract calls + N retrieval rounds, where N =
  #sub-questions. For 2-hop: 2 LLM calls + 2 retrievals vs R0's 1
  retrieval. Latency/token are a **first-class axis** — a default flip
  requires the quality gain to justify this cost.

### 1.3 Extract prompt (fixed)

> "Using only the context, answer the question in as few words as
> possible (a name, place, or short phrase). If the context does not
> contain the answer, output 'UNKNOWN'.\n\nContext: {docs_1}\n\n
> Question: {q1}\nAnswer:"

On "UNKNOWN" / empty → skip substitution for that hop (fall back to the
static sub-q, i.e. degrade to D1 behaviour for that query, never worse).

### 1.4 Resolve (substitution)

Heuristic first (cheap, deterministic): replace anaphora tokens in the
next sub-q — `that person`, `that company`, `that place`, `it`, `they`,
`this person`, `the person`, etc. — with `a1`. If no anaphora token is
present, append a disambiguator: `"{q_next} (regarding {a1})"`. No extra
LLM call for resolve (keeps cost to the extract calls only).

---

## 2. Measurement design (methodological-chain labelling)

- **Verdict Q**: Does iterative retrieval (hop-1 answer substituted into
  hop-2) lift gold-in-answer + supporting recall toward the oracle
  ceiling (72%), vs R0 single-shot (8%) and D1 static (12%)?
- **Diagnostic Q**: If not — (a) extract produces wrong/UNKNOWN hop-1
  answers, (b) resolved hop-2 still misses supporting, (c) coverage
  rises but synth still abstains. Inspect extracted a1 + resolved q2 +
  per-query supporting recall.
- **Fixture**: same 25 MuSiQue-ans queries, same workspace, paired
  against existing R0 + D1 JSONs. Verdict-grade (external standard +
  official scorer).
- **Primary axis**: gold-substring-in-answer (em/f1 response-style
  confounded per Phase C.2 §3.3).
- **Secondary axis**: supporting-paragraph recall (does round-2 surface
  the hop-2 supporting paragraph? — the direct mechanism check; this is
  what D1 left flat at 0.60).
- **Cost axis (first-class)**: mean latency/query + extra LLM calls.

### 2.1 Baselines (measured)

| Metric | R0 single-shot | D1 static | oracle ceiling |
|---|---|---|---|
| gold-in-answer | 8% (2/25) | 12% (3/25) | 72% (18/25) |
| supporting recall | 0.600 | 0.600 | — |

---

## 3. Decision rule (LOCKED)

Δ = D1b − R0 on the same 25 queries, mxtral first.

| Result | Verdict | Follow-up |
|---|---|---|
| gold-in-answer **≥ 30%** AND supporting recall **≥ 0.75** | **D1b WORKS** — iterative reaches hop-2 | cross-model (gemma4/llama); then weigh cost axis for an option-layer / default-flip case |
| gold-in-answer 15–30% OR (recall ≥0.75 but gold 15–30%) | **PARTIAL** — iterative helps, gap remains | diagnose residual misses; decide if cost justifies an option layer |
| gold-in-answer < 15% AND supporting recall flat (≤0.65) | **D1b INSUFFICIENT** | retrieval is not the only limiter on this fixture — re-point (graph traversal? the bench itself? synth/abstention tuning) |
| supporting recall ↑ (≥0.75) but gold-in-answer flat (<15%) | **retrieval FIXED, synth/abstention is the limiter** | the lever moves downstream — re-point to synth/abstention, not retrieval |

### Honesty guards (pre-stated)

1. n=25, mxtral single model for first verdict; **no cross-model claim**
   until gemma4+llama replicate.
2. em/f1 **forbidden** as standalone headline (response-style artifact).
   gold-in-answer + supporting recall are the verdict axes.
3. **Cost is reported in the headline**, not buried — iterative is
   strictly more expensive than R0; a quality win must be weighed
   against 2× LLM calls + 2× retrievals before any default-flip talk.
4. **default-OFF stays** regardless of result until a multi-axis
   measurement (MuSiQue gain vs RGB abstention loss vs cost) licenses a
   flip.
5. Honest tier ceiling: ⭐⭐ (external bench) — iterative/self-ask/IRCoT
   multi-hop RAG is **prior art**; JAMES contribution = reproducible
   measurement on its own stack + the per-query overlap method, NOT
   mechanism novelty. ⭐⭐⭐ barred.
6. No post-hoc threshold movement. No joint-piece framing.

---

## 4. Execution order

```
0. live smoke: 1 query JAMES_ENABLE_ITER_RETRIEVAL=1 — confirm a1 extracted +
   q2 resolved (anaphora gone) + round-2 retrieval fires (wiring, not verdict)
1. implement iterative resolver + extract + heuristic substitution + env-gate
2. unit test: flag-OFF byte-identical; flag-ON resolves a known anaphora case
3. D1b run: mxtral n=25 on cycle_gamma_musique_ans
4. compare vs R0 + D1 (gold-in-answer, supporting recall, cost) → §3 verdict
5. if WORKS → cross-model; else → §3 re-point
6. handover + PR (env-gate default OFF)
```

Estimated: implementation ~1–2h; measurement slower than D1 (extra
extract call + 2nd retrieval round) — budget ~25–35 min for n=25.

---

*Committed before implementation. Commit hash = pre-registration evidence.*
