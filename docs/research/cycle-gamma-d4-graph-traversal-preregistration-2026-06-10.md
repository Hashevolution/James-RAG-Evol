# Cycle γ D4 — graph traversal for multi-hop: design + pre-registration

**Date**: 2026-06-10 (written BEFORE the graph build + run — post-hoc
fit barred)
**Status**: LOCKED before any D4 run.

> **Why**: The multi-hop arc closure found the wall is **unsupervised
> supporting-paragraph selection** — dense retrieval can't pick the
> query-dissimilar hop-2 supporting paragraph. The literature's answer
> is graph traversal (entity-link, not vector similarity). A critical
> prerequisite was discovered: the MuSiQue workspace had **0 entities**
> — all six prior measurements (R0/breadth/D1/D1b/D2/D3) ran on a
> **graph-less stack**. D4 builds the graph and tests JAMES's existing
> graph layer — the one layer never exercised this cycle.
>
> Smoke confirmed entity extraction works on MuSiQue paragraphs:
> "Steve Hillage … album Green … partner Miquette Giraudy" →
> entities {Steve Hillage, Green, Miquette Giraudy} + relations
> (PRODUCES, partner). The hop-2 entity (spouse) — the exact thing
> dense retrieval missed — is captured by the graph.

---

## 1. Design

No new code — JAMES already has a graph layer (`run_loop_1_expand`:
entity extraction + graph DFS). The missing piece was the **graph
itself**. D4:

1. **Build the graph** on the existing `cycle_gamma_musique_ans`
   workspace: call `process_document_for_entities(source_id, text, [])`
   for every ingested MuSiQue paragraph (~500). Model: gemma4:e4b
   (~8.6s/para → ~71 min). Isolated workspace — production graph
   (`BASE_DIR/wiki`) untouched.
2. **Measure R0-with-graph**: the same R0 run (full JAMES, default
   knobs) now finds a populated graph, so `run_loop_1_expand` contributes
   graph paths. Compare against the graph-less R0 (8%) and oracle (72%).

`JAMES_DISABLE_GRAPH` stays unset (graph ON, default) — the point is to
measure the default stack *with the graph actually present*.

## 2. Measurement design

- **Verdict Q**: Does the graph layer (entity-link traversal to the
  hop-2 paragraph), once the graph is actually built, lift gold-in-answer
  on MuSiQue 2-hop vs the graph-less R0 (8%)?
- **Diagnostic Q**: If not — (a) graph built but traversal doesn't reach
  hop-2 (entity linking too sparse / wrong relations), (b) graph reaches
  hop-2 but synth still drowns in the combined context. Inspect
  graph_paths emitted + whether hop-2 entities appear.
- **Fixture**: same 25 MuSiQue-ans queries, same workspace (now with
  graph), paired vs the graph-less R0.
- **Primary axis**: gold-substring-in-answer.
- **Secondary**: do graph_paths surface the hop-2 entity? (mechanism
  check).

### 2.1 Baselines (measured)
| | R0 (graph-less) | D1/D1b/D2 | D3 | oracle |
|---|---|---|---|---|
| gold-in-answer | 8% | 12% | 8% | 72% |

## 3. Decision rule (LOCKED)

| Result | Verdict | Follow-up |
|---|---|---|
| gold-in-answer **≥ 30%** | **GRAPH WORKS** — entity-link traversal reaches hop-2 | this is the multi-hop answer JAMES already had; measure cost + cross-model; the graph layer earns its place |
| gold-in-answer **15–30%** | **PARTIAL** — graph helps, gap remains | diagnose; compare vs LazyGraphRAG (review R7) |
| gold-in-answer **< 15%** (≈ prior) | **GRAPH INSUFFICIENT** | even JAMES's graph doesn't crack MuSiQue multi-hop → the honest closure is "multi-hop graded answer is a known-hard axis; not JAMES's moat" → pivot to moat (R1) / hygiene (R3/R4). Retrieval/graph arc fully exhausted |

### Honesty guards (pre-stated)
1. n=25, mxtral single model (synth); gemma4 for graph build + decompose.
   No cross-model claim until replicated.
2. em/f1 forbidden as standalone headline.
3. **Path D**: this is a ONE-shot measurement of an existing layer, NOT
   the start of multi-hop-QA tuning. Whatever the result, JAMES's moat is
   replayable audit, not MuSiQue score. No selector/graph tuning loop.
4. No post-hoc threshold movement. ⭐⭐ ceiling (GraphRAG is prior art).
5. Graph build is isolated (`cycle_gamma_musique_ans` workspace);
   production graph untouched (verified: WIKI_DIR differs).

## 4. Execution

```
0. smoke ✅ (done — entity extraction works, hop-2 entity captured, ~71min est)
1. build script: process_document_for_entities over MuSiQue 500 paras
2. graph build run (gemma4, ~71 min, background)
3. R0-with-graph run: mxtral n=25
4. compare gold-in-answer vs graph-less R0 (8%) + oracle (72%);
   inspect graph_paths → §3 verdict
5. handover + (no production code — graph build is a measurement script)
```

---

*Committed before the graph build + run. Commit hash = pre-reg evidence.*
