# Cycle γ D3 — multi-hop evidence selection: design + pre-registration

**Date**: 2026-06-10 (written BEFORE implementation — post-hoc fit barred)
**Status**: LOCKED before any D3 run.

> **Why**: The retrieval-arc closure proved the lever is **synth's
> handling of noisy multi-hop context** — the model solves the 2-hop
> given clean supporting paragraphs (oracle 72%) but abstains when those
> paragraphs sit among distractors (D2, all 16 docs → 12%). The fix is
> to feed synth a **small, clean** context. D1/D1b used the
> sub-questions as extra *retrieval paths* (wrong layer); D3 uses them
> to *select* evidence: take the top doc(s) for each sub-question and
> pass only those to synth.

---

## 1. Design

```
decompose → [q_orig, q1, q2, ...]              (reuse D1 decomposer, force)
   │
   for each q: hybrid_search(q, top_k=8) → take top-K_sel docs
   │
   union + dedup the per-subquery winners → a SMALL clean context
   │  (e.g. 2 sub-qs × top-2 = ~4 docs, vs R0's rerank-5 / D2's 16)
   │
   feed exactly those docs to synth (bypass the wide rerank set)
```

The intuition: each sub-question is query-similar to its own hop's
supporting paragraph, so its top doc is more likely to BE that
supporting paragraph than the original query's rerank top-5 (which is
original-query-biased and misses hop-2). Union of per-hop winners ≈ the
oracle's clean supporting set, minus the distractors that drown synth.

### 1.1 Wiring
- env-gate `JAMES_ENABLE_EVIDENCE_SELECT` (opt-in, default OFF
  byte-identical — independent of D1/D1b flags).
- In `run_loop_0_retrieve`: if enabled, decompose(force) → per-subquery
  hybrid_search → keep top `K_sel` each → union/dedup → set `loop_state
  ["docs"]` to this small set and **skip the wide rerank** (the whole
  point is a clean small context, not a reranked wide one).
- `K_sel = 2` per sub-question, capped at ~6 docs total (still far below
  R0's effective context). Original query included as one "sub-q" so a
  single-hop question degrades gracefully.
- Failure isolation: decompose empty / search error → fall back to the
  normal retrieve path (byte-identical to flag-OFF).

### 1.2 Cost
1 decompose call + N hybrid_search calls (N = #sub-qs, cheap, no LLM) +
1 synth. Cheaper than D1b (no per-hop extract call). The LLM cost is
just the decompose.

---

## 2. Measurement design

- **Verdict Q**: Does per-sub-question evidence selection (small clean
  synth context) lift gold-in-answer toward the oracle ceiling (72%),
  vs R0 (8%) and the failed retrieval-side attempts (D1/D1b/D2 all 12%)?
- **Diagnostic Q**: If not — (a) sub-q top docs aren't the supporting
  paragraphs (retrieval per sub-q still misses), (b) context is clean
  but synth still abstains. Inspect per-query: are the selected docs the
  gold supporting paragraphs? (supporting recall over the SELECTED set.)
- **Fixture**: same 25 MuSiQue-ans queries, same workspace, paired vs R0.
- **Primary axis**: gold-substring-in-answer.
- **Secondary axis**: supporting recall over the **selected** docs (the
  mechanism check — did selection actually surface the supporting set?).

### 2.1 Baselines (measured)
| | R0 | D1 | D1b | D2 | oracle |
|---|---|---|---|---|---|
| gold-in-answer | 8% | 12% | 12% | 12% | 72% |

---

## 3. Decision rule (LOCKED)

| Result | Verdict | Follow-up |
|---|---|---|
| gold-in-answer **≥ 40%** | **D3 WORKS strongly** — clean selection ≈ oracle | cross-model; measure cost + RGB side-effect for an option layer |
| gold-in-answer **25–40%** | **D3 WORKS** — meaningful lift, gap to oracle remains | diagnose residual; cross-model |
| gold-in-answer **15–25%** | **PARTIAL** — selection helps but synth still struggles | check if selected docs ARE supporting; if yes → synth is still the limiter |
| gold-in-answer **< 15%** (≈ prior attempts) | **D3 INSUFFICIENT** | if selected supporting recall is high but gold flat → synth cannot use even clean context (deeper than evidence-selection; re-point to synth/model). If selected recall low → per-sub-q retrieval itself misses (rare given oracle works) |

### Honesty guards (pre-stated)
1. n=25, mxtral single model; no cross-model claim until replicated.
2. em/f1 forbidden as standalone headline.
3. default-OFF stays; flip gated on multi-axis (MuSiQue gain vs RGB
   abstention loss vs cost), never this bench alone.
4. No post-hoc threshold movement. No joint-piece framing.
5. ⭐⭐ ceiling — per-subquery evidence selection / decomposed retrieval
   is prior art (self-ask, decomp-RAG, IRCoT); JAMES contribution =
   reproducible measurement on its own stack.

---

## 4. Execution

```
0. live smoke: 1 query JAMES_ENABLE_EVIDENCE_SELECT=1 — confirm small
   clean context (~4-6 docs, per-subq winners) reaches synth (wiring)
1. implement evidence-selection branch in run_loop_0_retrieve + env-gate
2. unit test: flag-OFF byte-identical
3. D3 run: mxtral n=25
4. compare gold-in-answer vs R0 (8%) + oracle (72%); compute selected
   supporting recall → §3 verdict
5. handover + PR (env-gate default OFF)
```

Estimated: implementation ~1h; measurement ~20 min.

---

*Committed before implementation. Commit hash = pre-registration evidence.*
