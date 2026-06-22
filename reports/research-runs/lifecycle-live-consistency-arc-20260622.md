# Lifecycle live-consistency arc — results (2026-06-22)

Measurement/fix loop, iter 1–4. Triggered by the operator question
"does editing a document fire a cascade that keeps reasoning consistent?"
and the follow-up "측정 관련".

## The finding (measured, not assumed)
`scripts/research/cascade_consistency_probe.py` (deterministic, calls the
REAL `GraphEngine.build_graph_context_str`) showed the **live graph query
path ignored lifecycle status entirely** — it filtered relations by
`confidence` only. So cascade-/T1-/T7-deactivated relations
(invalidated / superseded / expired) leaked into the LLM context.
Lifecycle status was honored ONLY in the `reconstruct_*_at` time-travel
path. ⇒ the entity-edit cascade (#1018/#1019) and the broader lifecycle
were **cosmetic at the live-query layer**.

Probe (4 scenarios), pre-fix vs the status-aware filter:

| arm | invalidated leakage | active retention | consistent |
|---|---|---|---|
| CURRENT (legacy) | 3/3 | 1.0 | 1/4 |
| FILTERED (fix) | 0 | 1.0 | 4/4 |

The fix removes the leak with **zero active-relation loss** (Pareto).

## The fixes (live-consistency triad)
| PR | change | site |
|---|---|---|
| #1021 | `relation_is_live(rel)` gate — exclude `status.active==False` / `mutation_type∈{invalidated,superseded,expired}` | `expand_dynamic` + `build_graph_context_str` |
| #1023 | dead edges no longer inflate the graph score (DFS halting / ranking) | `compute_graph_score` |
| #1024 | honor the T1 **validity window** (`validity.to<now` / `validity.from>now`) — catches time-expired edges the BATCH `expiration_cascade` sweep hasn't marked yet | `relation_is_live` (clock-aware) |

All gated by `JAMES_DISABLE_STATUS_FILTER=1` (A/B + rollback).

## No-regression evidence (Rule #2)
- **STEP7 / 5-axis Δ = 0, structural**: the current KG has **0 deactivated
  edges and 0 non-null `validity.to`** (316 files / ~879 relations), so
  `relation_is_live` is True for every existing edge → the filter is a
  **no-op on current data**. It only changes traversal once edges get
  deactivated/expired — which is exactly the consistency it restores.
- ~160 graph/cascade tests green across the arc; core/graph files < 20 KB.

## Time-travel isolation (iter 4, verified)
`reconstruct_graph_at` is a **pure event-replay** (LOCK 4 — reads only the
audit_log, not the wiki / graph engine). Source audit confirmed
`core/lifecycle/**` references none of the live now-based functions, so
the live filter does NOT pollute historical snapshots (a
historically-valid-then-expired edge is still present at its past `t`).
Pinned by `tests/test_reconstruct_isolation.py`.

## Honest scope / remaining
- **Live LLM cascade dogfood** = operator-gated (mutates real KG + vector
  store; mixtral re-extraction non-deterministic) — not an autonomous PR.
  Manual check: edit an entity → "관계 N개 무효화/추가" → query → the
  dropped relation is gone from the answer's graph path.
- **Inbound / T6 causality** propagation (other entities' edges into a
  changed fact) is doc-level / T6 cascade territory — out of this arc.
- `compute_graph_score` is now the only score path filtered; if other
  ranking surfaces read raw relations, audit them in a future arc.
