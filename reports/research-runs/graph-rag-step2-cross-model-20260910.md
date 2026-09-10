# Graph-RAG synthesis Step 2 — cross-model results (2026-09-10)

Runner: `scripts/research/graph_rag_synth_step2_cross_model.py` (default
scope) → `scripts/qvt_ablation_matrix.py --suite multihop_rag --tiers M_S,M_L
--sector-cells C_rag-basic,C_rag-graph,C_rag-ontology --n-runs 3`.
Aggregation: `scripts/research/graph_rag_synth_step2_aggregate.py`.
Pre-registration of the interpretation rules:
`docs/evaluation/v0.5-graph-rag-contribution.md` §3.2 (2026-06-13).

| | |
|---|---|
| Fixture | `multihop_rag` v1, N=100 (75 with an expected path, 25 null) |
| Tiers | M_S = gemma3:4b · M_L = gemma3:12b (new) · M_M = gemma4:e4b (Step 1, 2026-06-12, reused) |
| Cells | 3 sector cells × 2 new tiers × n=3 paired = 18 runs |
| Server | one fresh `uvicorn` per cell on `:8011`, no `--reload`; `:8000` untouched; port verified released at the end |
| git_sha | M_S / M_L `11b9506`; M_M `b686f35` (see §5 confound) |
| Wall clock | 10:05 → 15:29 = **5 h 24 min** (roadmap estimate 14 h; runner estimate 6.6 h) |

## 1. Table 3.2 — cross-model Δ (medians of n=3; band = larger noise band of the pair)

### Graph-RAG contribution (C_rag-basic → C_rag-graph)

| Axis | M_M gemma4:e4b (Step 1) | M_S gemma3:4b | M_L gemma3:12b |
|---|---|---|---|
| **path_coverage** | 0.000 → **0.4056** (**+0.406**, band 0.020) | 0.000 → **0.3989** (**+0.399**, band 0.010) | 0.000 → **0.4033** (**+0.403**, band 0.000) |
| graded_answer | 0.260 → 0.203 (−0.057, band 0.037) | 0.413 → 0.387 (−0.027, band 0.020) | 0.403 → 0.390 (−0.013, band 0.017 — *within band*) |
| abstention_f1 | 0.306 → 0.400 (+0.094, band 0.176 — *within band*) | 0.348 → 0.244 (**−0.104**, band 0.082) | 0.311 → 0.256 (−0.055, band 0.136 — *within band*) |
| token_cost (answer chars) | 783 → 1675 (**2.14×**) | 469 → 475 (**1.01×**) | 503 → 494 (**0.98×**) |
| latency | 12.5 s → 32.4 s (2.58×) | 7.0 s → 15.5 s (2.21×) | 3.5 s → 11.0 s (3.11×) |

### Typed-filter contribution (C_rag-graph → C_rag-ontology)

| Axis | M_M | M_S | M_L |
|---|---|---|---|
| path_coverage | 0.000 (within band) | −0.007 (within band) | −0.003 (within band) |
| graded_answer | +0.027 (band 0.020) | +0.003 (within band) | **−0.017** (band 0.010) |
| abstention_f1 | +0.029 (within band) | +0.082 (band 0.082 — at the edge) | +0.007 (within band) |
| token_cost | 1.01× | 0.98× | 1.03× |
| latency | 1.00× | 1.00× | 1.01× |

## 2. Pre-registered rules, applied mechanically (aggregator output)

| §3.2 rule | Result | Verdict |
|---|---|---|
| path_coverage Δ within ±0.05 across all three | +0.406 / +0.399 / +0.403, **spread 0.007** | **Fires.** The +0.41 finding upgrades from "load-bearing on M_M" to **load-bearing on the 4B–12B gemma family** |
| path_coverage Δ diverges by >0.10 | no | — |
| graded_answer Δ flips sign | no — negative on all three (−0.057 / −0.027 / −0.013), M_L within its band | Loss is consistent in sign and **shrinks with model size** |
| typed-filter +0.027 holds across models → ⭐⭐ | no — M_S +0.003 (within band), M_L −0.017 | **Not promoted**; stays ⭐ operational |
| typed-filter Δ negative at M_L | yes, −0.017 with band 0.010 | **Fires.** Honest negative: the 12B model self-corrects graph noise and the filter becomes a small regressor. Default-on (PR #689) gets the pre-registered caveat |

## 3. What the cross-model view adds beyond the rules

1. **The "2.1× token cost" does not generalise — and it was never a prompt
   cost.** `token_cost` in this oracle is *answer characters*
   (`eval/qvt/oracle.py::score_token_cost`, `mean_chars`). At M_M, gemma4:e4b
   writes answers 2.1× longer once graph context is present (783 → 1675
   chars); gemma3:4b and gemma3:12b do not (1.01× / 0.98×). Table 3.1's
   explanation "graph context inflates prompt" attributed a
   **model-specific verbosity response** to the retrieval layer. The
   multiplier is model-dependent; the latency multiplier (2.2–3.1×) is not.
2. **abstention_f1 is not a graph win.** M_M's +0.094 sits inside its own
   0.176 band (already flagged in #1118); at M_S the same Δ is **−0.104,
   beyond its 0.082 band**; at M_L −0.055 within band. One tier inside the
   noise, one tier a loss, one tier inside the noise. Table 3.1's "real win"
   framing does not survive cross-model; the honest statement is
   *no consistent effect, with a loss at the smallest tier*.
3. **gemma4:e4b is the weakest of the three on this fixture in basic mode**
   (graded_answer 0.260 vs 0.413 / 0.403). The production default is not
   the strongest 4B option on multi-hop short answers — consistent with the
   Phase 2b / 3b routing measurements that already moved chat and
   retrieval modes to gemma3:12b.

## 4. Two things that looked like defects and were not

Recorded so the next session does not repeat the alarm.

- **The bench log's "path recall: mean=0.00" on every one of the 18 runs.**
  That line is `scripts/bench.py`'s own diagnostic, not the oracle. Its slug
  match still fails on this fixture: in the graph cells the per-query
  `path_metrics` show `actual_node_count > 0` on 70/75 queries and
  `hits = 0` on all of them, while the oracle (the authority per the
  comment at `bench.py:405`) scores path_coverage 0.40. The diagnostic's
  own comment says the 2026-06-03 slug fix ended a streak of "last 35 runs
  all reported mean_path_recall=0.0"; it did not. Hygiene item, `fix` label,
  not this PR.
- **`sector_disabled: True` in traces mid-run.** That was cell 2 =
  `C_rag-basic / M_L`, where the overlay sets `JAMES_DISABLE_GRAPH=1` by
  design. The dry-run order is basic/M_S → basic/M_L → graph/M_S → … ;
  misreading it as graph/M_S produced a false alarm. Ruled out along the
  way, and useful to keep: no `JAMES_DISABLE_*` leak from `.env` or the
  shell; `_cell_env` composes from a fresh `os.environ.copy()` per cell;
  `core/feature_flags.py` does not cover the graph flag and is
  non-persistent.

## 5. Confound to carry, and the clean follow-up

**M_M is a June measurement.** Its three cells were captured 2026-06-12
at `b686f35`; M_S / M_L today at `11b9506`. Between them: the lifecycle
live-consistency arc (#1021–#1026), the engine split (#1083), response-style
changes. The §3.2 rules were pre-registered against Step 1's M_M, so the
verdicts above are exactly what was pre-registered — but two of the three
axes that moved (answer chars, abstention) are *answer-side* and could
carry code drift as well as model difference.

What is **not** confounded: path_coverage. It is oracle-side, and the
lifecycle gate is a no-op on this workspace — its 2,605 relations carry no
`status` / `mutation_type` / `validity` at all (counted 2026-09-10), and
`relation_is_live()` treats untagged edges as live.

**Clean follow-up**: re-run the three M_M cells at `11b9506`
(`--tiers M_M`, ~3–5 h at Step 1's pace). If M_M's answer-chars multiplier
and abstention Δ reproduce under today's code, findings 3.1 and 3.2 are
model effects; if they collapse toward the gemma3 numbers, they were code
drift. Operator's call — it is GPU time, not a correctness blocker for the
pre-registered verdicts.

## 6. Per-cell wall clock (n=3 runs each)

| Cell | run 1 | run 2 | run 3 |
|---|---|---|---|
| C_rag-basic / M_S | 13.0 min | 11.7 | 11.6 |
| C_rag-basic / M_L | 5.9 | 5.9 | 5.8 |
| C_rag-graph / M_S | 26.1 | 25.9 | 25.8 |
| C_rag-graph / M_L | 18.3 | 18.3 | 18.4 |
| C_rag-ontology / M_S | 25.9 | 25.9 | 25.9 |
| C_rag-ontology / M_L | 18.4 | 18.5 | 18.5 |

gemma3:12b is *faster* than gemma3:4b here: the 12B model fits the 12 GB GPU
whole, while the 4B run is bounded by CPU-side embedding, not generation.

## 7. Artefacts

- Cells: `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/qvt-ablation-cell-{C_rag-basic,C_rag-graph,C_rag-ontology}-{M_S,M_L}.json` (schema v4). The schema-v3 `…-M_S.json` files from 2026-06-01 (n=1) that were in the directory are superseded by these; the aggregator refuses v3.
- Per-run bench output: `reports/bench_{b181c01,980ac2c}_multihop_rag_20260910_*.json` (18 files; the sha in the name changed at 10:30 when #1118 merged — a new script only, no server code).
- Log: `reports/research-runs/_step2_cross_model_20260910_1005.log`.

## One line

The +0.41 path-coverage contribution of graph traversal is **model-independent across the 4B–12B gemma family (spread 0.007)**; the "2.1× token cost" and "abstention win" attached to it in Table 3.1 were gemma4:e4b-specific and do not survive cross-model.
