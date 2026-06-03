# Retrieval Quality Δ — graph(filter-OFF) vs ontology(filter-ON)

> Generated: 2026-06-03T10:13:38  
> baseline:  `reports/bench_b3c4562_multihop_rag_20260603_000057.json`  
> candidate: `reports/bench_b3c4562_multihop_rag_20260603_022251.json`  
> fixture:   `workspaces/hotpot_eval/eval/multihop_rag_queries.json`  
> k = 5

## Aggregate Δ (candidate − baseline)

| Metric | graph(filter-OFF) | ontology(filter-ON) | Δ |
|---|---:|---:|---:|
| ndcg@k | 0.4697 | 0.4766 | **+0.0069** |
| mrr | 0.7622 | 0.7778 | **+0.0156** |
| hits@k | 0.4044 | 0.4078 | **+0.0034** |

- Queries scored (baseline / candidate): 75 / 75

## Per-query Δ (NDCG threshold ±0.05)

- ✅ improved (NDCG+0.05+): **3** queries
- ❌ regressed (NDCG−0.05+): **2** queries
- ⚪ unchanged: 70

### Top improved

| id | Δndcg | base ndcg | cand ndcg | base rr | cand rr |
|---:|---:|---:|---:|---:|---:|
| 3 | +0.533 | 0.387 | 0.920 | 0.500 | 1.000 |
| 36 | +0.235 | 0.235 | 0.469 | 0.333 | 1.000 |
| 39 | +0.235 | 0.469 | 0.704 | 1.000 | 1.000 |

### Top regressed

| id | Δndcg | base ndcg | cand ndcg | base rr | cand rr |
|---:|---:|---:|---:|---:|---:|
| 9 | -0.246 | 0.637 | 0.390 | 1.000 | 1.000 |
| 12 | -0.235 | 0.704 | 0.469 | 1.000 | 1.000 |
