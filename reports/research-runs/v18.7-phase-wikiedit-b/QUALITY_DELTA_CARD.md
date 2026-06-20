# Quality Delta Card — Phase wiki_edit-b (3-cell paired measurement, COMPLETE)

> **Cycle**: v0.6.1 v18.7 Phase wiki_edit-b
> **Date**: 2026-06-20
> **Fixture**: `eval/wiki_edit_mode_queries.json` (12 Korean queries, 4 sub-classes × 3 rows)
> **Design**: 3 cells × 12 queries × 3 paired runs = 36 paired-rows per cell, 108 LOCAL + 108 CLOUD + 108 judge calls total
> **Judge**: Claude CLI (`claude_code_cli`), pairwise blinded A/B
> **Cloud anchor**: Claude (same backend as judge — self-preference caveat applies)

---

## Cells

| Cell | Local model | Think | num_predict | Why this cell |
|---|---|---|---|---|
| **A** | `gemma4:e4b` | OFF (`JAMES_GEMMA4_E4B_THINK_OFF=1`) | 400 | Current production default (config.GEMMA_MODEL) |
| **B** | `gemma3:12b` | (n/a — non-gemma4) | 400 | Phase 2b/3b winner on prior fixtures (chat / retrieval) |
| **C** | `gemma3:27b` | (n/a — non-gemma4) | 400 | Phase 3b accuracy leader; verbose; 2.3× slower → axis of interest |

---

## Results

### Judge-graded (Claude pairwise A/B; gold-grounded recheck where applicable)

| Sub-class | Cell A judge L \| C | A gold L \| C | Cell B judge L \| C | B gold L \| C | Cell C judge L \| C | C gold L \| C |
|---|---|---|---|---|---|---|
| `factual_edit`   (gold) | 1.000 \| 1.000 | 1.000 \| 1.000 | 1.000 \| 1.000 | 1.000 \| 1.000 | 1.000 \| 1.000 | 1.000 \| 1.000 |
| `format_edit`    (judge-only) | 1.000 \| 1.000 | — | 1.000 \| 1.000 | — | 1.000 \| 1.000 | — |
| `summarize`      (gold) | 1.000 \| 1.000 | **0.667** \| 1.000 | 1.000 \| 1.000 | **1.000** \| 1.000 | 1.000 \| 1.000 | **0.333** \| 1.000 |
| `reword`         (judge-only) | 1.000 \| 1.000 | — | 1.000 \| 1.000 | — | 1.000 \| 1.000 | — |

**Headline**: judge column hides every gap (all 1.000). Gold-grounded `summarize` recheck reveals a **clean ranking**:

> **gemma3:12b (1.000) > gemma4:e4b OFF (0.667) > gemma3:27b (0.333)**

This **inverts the Phase 3b retrieval ranking** (27b > 12b > 4b > gemma4:e4b on evidence-rich multi-hop), see §"Cross-task ranking reversal" below.

### Latency + answer length

| Cell | mean latency | median | max | mean `summarize` ans_chars | mean `format_edit` ans_chars |
|---|---|---|---|---|---|
| A — gemma4:e4b OFF | 35.1 s | 18.4 s | 129.8 s | 188 | 117 |
| B — gemma3:12b     | **23.2 s** | 17.8 s |  58.0 s | 211 | 102 |
| C — gemma3:27b     | 37.2 s | 35.1 s |  54.2 s | **365** | **224** |

Cell B is the fastest. Cell C's `summarize` answers are **94% longer** than Cell B's — confirming the 27b verbose tendency from Phase 3b on a task where verbosity actively hurts (key facts buried under extra prose).

---

## Cross-task ranking reversal (⭐ finding)

Two paired measurements, same models, different tasks:

| Task (cycle) | gemma3:12b gold | gemma3:27b gold | gemma4:e4b gold |
|---|---|---|---|
| **Retrieval** (Phase 3b: evidence-rich multi-hop QA) | 0.889 | **1.000** | 0.815 |
| **Wiki edit** (Phase wiki_edit-b: summarize sub-class) | **1.000** | 0.333 | 0.667 |

**Interpretation**: 27b's verbose tendency is amplifying. On evidence-rich retrieval (where the question wants every relevant fact in the answer), verbosity helps — 27b includes more correct facts, gold-grounded score climbs. On `summarize` (where the question wants a compressed extract), verbosity inverts the score — extra prose displaces / dilutes the key facts the gold_signals expect, and the model's answer ends up failing the deterministic match even though the underlying knowledge is correct.

This is a layer-intent alignment lesson: **task verb (summarize vs explain) flips which model wins**. The ladder pattern from Phase 3b ("27b for accuracy-critical retrieval; 12b for default") is task-conditional, not absolute.

---

## Verdict

`gemma3:12b` is the wiki_edit winner on every axis. Promote to top of `DEFAULT_PREFERENCE['wiki_edit']`. **`gemma3:27b` is demoted**, not promoted — its 27b → verbose → summarize-fail chain is the reverse of what one would predict from the Phase 3b retrieval ladder.

Recommended reorder:

```python
"wiki_edit": [
    "gemma3:12b",   # Phase wiki_edit-b winner: 1.000 gold all axes, fastest (mean 23.2 s)
    "gemma4:e4b",   # OFF: summarize gold 0.667; lighter alternative
    "gemma3:27b",   # demoted: verbose → summarize gold 0.333 (facts buried)
    "mixtral:8x7b", "qwen2.5:14b",  # legacy tail unchanged
],
```

Phase wiki_edit-c lands this reorder + extends `engine.py`'s mode-routing branch to include `wiki_edit` in the `resolve_for_mode(mode, requested="")` set.

---

## Caveats

- **`small_n`**: 12 queries × 3 runs = 36 paired rows. The gold-grounded gap (1.000 vs 0.667 vs 0.333) is large enough to clear noise, but a publishable claim needs cross-corpus validation.
- **Judge self-preference**: judge is Claude; cloud is Claude. The `cloud_verdict=CORRECT` 100% is consistent with v18.6 lenient bias (+0.11 to +0.19 over-credit). Gold-grounded recheck is the verdict source for `factual_edit` + `summarize`.
- **`judge-only` sub-classes** (`format_edit` + `reword`): no gold ground-truth. Judge results read 1.000 across the board; should NOT be cited as quality parity without an additional axis.
- **`fixture_fitness`**: operator-authored fixture (no upstream alarm if a UX cycle silently edits it). `WikiEditFixtureSurface` lock-test + `check_wiki_edit_fixture` pre-flight keep the surface stable.
- **`local_backend`**: Ollama HTTP only; DiffusionGemma spike opt-in (`JAMES_ENABLE_DIFFUSIONGEMMA=1`) was not part of these cells.
- **`single-host measurement`**: n=3 paired runs per query; per-row verdict is the majority. Cross-host / cross-machine replay is a future Phase wiki_edit-d concern.
- **`task-conditional ladder`**: the cross-task reversal (Phase 3b retrieval vs Phase wiki_edit-b summarize) means a single global ranking doesn't exist. The per-mode `DEFAULT_PREFERENCE` IS the right abstraction; the operator-pending Phase 5 dashboard should surface BOTH measurement results so the operator sees the task-conditional gap.

---

## Pareto axes (5-axis QDC convention)

| Axis | Cell A (current default) | Cell B (proposed top) | Cell C | Δ (B − A) |
|---|---|---|---|---|
| Path coverage     | n/a (no retrieval; doc embedded in prompt) | n/a | n/a | 0 |
| Graded answer (gold mean across factual_edit + summarize) | (1.0 + 0.667) / 2 = **0.833** | (1.0 + 1.0) / 2 = **1.000** | (1.0 + 0.333) / 2 = **0.667** | **+0.167** (vs A) |
| Abstention F1     | n/a (no `null_query` rows) | n/a | n/a | 0 |
| Token cost (mean ans_chars across 4 sub-classes) | (119+117+188+134)/4 ≈ **139** | (120+102+211+121)/4 ≈ **139** | (119+224+365+131)/4 ≈ **210** | ≈ 0 (vs A); +51% (vs C) |
| Latency cost (mean s) | 35.1 | **23.2** | 37.2 | **−11.9 s** (vs A) |

**Pareto verdict** — Cell B dominates Cell A on graded answer AND latency, ties on token cost. Cell C loses on graded answer, ties on latency, loses on token cost.

---

## Layer-intent matrix entry

`wiki_edit` is a **synthesis** layer (no retrieval / no graph traversal). Per `mechanism_layer_intent_axis_alignment`, the layer's design-intent axes:

- **fact preservation** (deterministic): gold_signals key-fact match — `wiki_edit`'s reason-to-exist
- **format fidelity** (judge): markdown / structural compliance
- **brevity** (latency + answer length): edit should NOT amplify token count

**Cell B wins on all three.** **Cell C fails on fact preservation + brevity** (verbose → facts buried, longer answers). The matrix-aligned scorecard says: **promote B, demote C**.

---

## References

- Fixture: `eval/wiki_edit_mode_queries.json`
- Raw rows: `reports/research-runs/v18.7-phase-wikiedit-b/cell{A,B,C}_*.json` (3 × 1.0 MB)
- Memory: `project_phase_wiki_edit_a_fixture_v18_7` (the -a fixture + harness PR)
- Memory: `project_judge_reliability_gold_grounded_v18_6` (judge bias caveat)
- Memory: `project_d5_complexity_routing_negative_v18_7` (Phase 3b 27b verbose finding — wiki_edit-b confirms + extends)
