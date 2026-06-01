---
name: finding-jameses-graph-too-many-entities-surfaced
description: [2026-06-01, bucket-(a)] the graph layer is providing MORE noise than the
metadata:
  type: project
---

# Finding — jameses-graph-too-many-entities-surfaced (2026-06-01)

**Bucket**: (a)  
**Tags**: anti-pattern, mechanism-candidate

## Source entry (verbatim from `reports/research-runs/qvt-ablation-findings.md`)

- **bucket**: (a) — architecture, optimizable (engineering, not
  fundamental)
- **cell context**: α-6 Phase 1, C_rag-graph cell, gemma4:e4b
- **pattern**: per-query graph_paths counts in trace JSONL range
  41-161 entities (sample queries 96-100 show counts of 90, 41,
  137, 161). LLM context window flooded with potentially-irrelevant
  graph entities.
- **observation**: adding S2 graph traversal + S3 preproc + S4
  citation as a bundle on top of S1 RAG degrades graded_answer by
  -0.054 (0.327 → 0.273). The aggregate Power-of-Noise pattern
  (semantically-similar irrelevant entities hurt more than random
  noise) reproduces on the graph axis.
- **surprise**: the graph layer is providing MORE noise than the
  document layer alone. Aggressive top-K filtering on graph
  results (by query embedding similarity, threshold ~0.3) is the
  cheapest engineering improvement candidate.
- **data pointer**: `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/qvt-ablation-cell-C_rag-graph-M_M.json`;
  trace files in `workspaces/hotpot_eval/reports/trace/2026-06-01/`
- **follow-up tag**: `mechanism-candidate` + `anti-pattern`
- **probe ideas**:
  1. Implement top-K graph filtering (~1 day code) — expected
     graded +0.03-0.05
  2. Per-question-type routing — graph for multi-hop queries
     only, skip for comparison/temporal/null
  3. Query embedding similarity threshold in
     `engine.graph.rank_nodes`
- **immediate impact on α-6**: an engineering candidate that could
  shift the C_rag-graph cell verdict from "neutral" to "adopt"
  with one focused PR. Tagged for after Phase 2/3 completes (so
  the fix is informed by the cross-model data).

## Promotion provenance

- Auto-drafted by `scripts/qvt_promote_findings.py` on the entry dated 2026-06-01.
- This is a DRAFT memo. Review before adding a line under MEMORY.md.
- If the finding was already resolved by a PR (e.g. `→ RESOLVED (#N)`),
  consider whether the memo should be archived as feedback rather than
  carried as an open mechanism candidate.
