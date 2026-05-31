---
name: finding-multihop-rag-path-axis-dead
description: [2026-05-31, bucket-(d)] this is not just a slug formatting issue. graph_paths
metadata:
  type: project
---

# Finding — multihop-rag-path-axis-dead (2026-05-31)

**Bucket**: (d)  
**Tags**: data-quality, mechanism-candidate

## Source entry (verbatim from `reports/research-runs/qvt-ablation-findings.md`)

- **bucket**: (d) measurement artifact — bench.py was dropping
  `response.sources`; JAMES citation design was correct all along.
  Diagnosis: applied the 4-step rule (axis 0 → sample answers manually →
  check `response` keys → reconcile design vs matcher) and found
  `core/reasoning/pipeline.py:343` emits `sources: [d["source"] for d
  in docs[:3]]` while bench only inspected `graph_paths`.
- **pattern**: 100/100 queries with `expected_path` → `path_recall = 0.000`
- **cell context**: baseline L1/M_M (`baseline_f7762a3.json`), workspace
  ingested 183 articles (931 entities)
- **observation**: graph_paths actually returned 18-179 nodes per query
  (mean 60) but **none of them are MultiHop-RAG evidence article titles**.
  Sample q1 expected = `['The FTX trial is bigger than Sam Bankman-Fried',
  'SBF's trial starts soon, but how did he — and FTX — get here?', …]`;
  actual document entity name = `multihop_0010_SBF-s-trial-starts-soon-but-
  how-did-he-and-FTX-get-here` (prefix + slugified, max 80 chars).
- **surprise**: this is not just a slug formatting issue. graph_paths
  surfaces **concept / org / person entities** (the entities *extracted
  from* the article), not the **document entity** (the article itself).
  MultiHop-RAG's `evidence_list[].title` measures "did the system cite the
  right *source*" — that semantic doesn't map onto JAMES's concept-centric
  graph traversal.
- **data pointer**: `reports/bench_f7762a3_multihop_rag_20260531_063800.json`
  + `workspaces/hotpot_eval/eval/qvt/baseline_f7762a3.json` aggregate
- **follow-up tag**: `data-quality` + `mechanism-candidate`
- **probe ideas**:
  1. Modify `scripts/hotpot/build_fixture.py` to map each evidence title
     to the *concept/org entities extracted from that article*
     (post-ingest fixture rebuild). Requires loading wiki to find which
     concepts came from `source_document=multihop_<id>_<slug>.txt`.
  2. Modify `eval/qvt/oracle.py:score_path_coverage` to also credit
     document-via-`doc_id` matches when bench output includes the
     traversed document IDs.
  3. Accept path axis as fixture-incompatible for MultiHop-RAG; rely on
     graded + abstention + token + latency for matrix verdicts. Mark
     path Δ as "n/a — fixture limitation" in report.
  - Option 3 is cheapest; options 1 / 2 are methodologically cleaner.
- **immediate impact on α-5**: matrix loses 1/5 axes for verdict
  discrimination. With 4 remaining axes (3 quality + 2 cost; path frozen
  at 0), Pareto verdict still works but on a smaller surface. Sanity cell
  (think=ON vs OFF) still measurable on all 4 active axes.

## Promotion provenance

- Auto-drafted by `scripts/qvt_promote_findings.py` on the entry dated 2026-05-31.
- This is a DRAFT memo. Review before adding a line under MEMORY.md.
- If the finding was already resolved by a PR (e.g. `→ RESOLVED (#N)`),
  consider whether the memo should be archived as feedback rather than
  carried as an open mechanism candidate.
