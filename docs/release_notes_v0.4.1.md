# v0.4.1 — T6 Causality Chain (CASCADE extension) + QVT α track full closure

**Theme**: v0.4.1 closes the CASCADE pillar that v0.4.0 only half-finished. When `cascade_remove_doc_from_sources` empties a base fact's sources, edges whose `derived_from` references that base now auto-invalidate via `invalidate_derived_facts` — the derivation chain stays internally consistent without manual operator intervention. Plus the v0.4.0 carry-over `dispatch_contradiction` ingestion wiring (T2.D-1/2/2.b/3) lands as flag-gated default-OFF, and the QVT α track ships end-to-end.

## Why this is a citable release

v0.4.0 shipped the **EVENT** track (T1 Temporal Validity + T7 Supersede Chain + T2 Contradiction Arbitration) and made the CASCADE/EVENT separation provable. v0.4.1 ships the **CASCADE companion** (T6): when CASCADE removes a doc and the resulting empty base facts had derived edges depending on them, those derived edges auto-invalidate. The wiki stays internally consistent without manual operator intervention.

The **T6.C.b foundational-vs-corroborative refinement** is the architectural insight that landed during T6.C user review: not all `derived_from` entries are equal. `transitive` / `inferred` are structural chain links (loss of any one breaks the derivation); `operator` is corroborative (strengthens but doesn't single-handedly support when foundation is alive). This distinction is what the existing T6.A schema constants already encoded — the cascade module now respects it.

## What v0.4.1 delivers

### T6 Causality Chain — 5-PR sequence

Per `docs/handovers/v0.4.1-t6-causality-chain-entry.md`:

| Module | Surface | LoC | Tests |
|---|---|---|---|
| `core/lifecycle/schema.py` (extended) | `T6_EDGE_FIELD_DERIVED_FROM` + `VALID_DERIVATION_TYPES` + `validate_edge_t6_derived_from` (Decision 3 cycle reject) + `apply_t6_edge_defaults` | +~160 LOC | 23 |
| `scripts/migrate_v041_lifecycle.py` | `--dry-run` / `--apply` / `--verify` + pre-write snapshot | ~10 KB | — |
| `core/lifecycle/derivation.py` | `extract_derivation_chain` (operator-tagged + flag-gated LLM) | ~10 KB | 14 |
| `core/lifecycle/causality.py` | `should_invalidate_edge` (pure decision) + `invalidate_derived_facts` (soft invalidate, atomic per-file writes) | ~10 KB | 22 |
| `core/cascade/_delete.py` (extended) | `cascade_remove_doc_from_sources` invokes `invalidate_derived_facts` post-loop | +~30 LOC | (release-gating) |
| `tests/test_t6_release_gating_invariants.py` | 4 release-gating invariants vs tmpdir wiki fixtures + real cascade | — | 5 |

**83+ contract tests** pass when run together. 69 pre-T6 cascade tests (`test_phase_c_cascade.py` + `test_phase_e_graph_editor.py` + `test_t7_release_gating_invariants.py`) all still pass — **no regression**.

### Four release-gating invariants (T6.D)

`tests/test_t6_release_gating_invariants.py` — all four must remain green:

1. **`test_derived_invalidated_when_base_removed`** — cascade-remove a doc → base relation drops (sources empty) → derived edge auto-invalidates via T6.D propagation. End-to-end via the real `cascade_remove_doc_from_sources` call.
2. **`test_partial_base_loss_preserves_derived`** — T6.C.b refinement: a derived edge with foundation (`transitive`) alive + corroborator (`operator`) gone stays active. Confidence-decay-on-corroborator-loss is T3 territory; T6 is binary.
3. **`test_causality_chain_acyclic_rejected_at_write`** — Decision 3 LOCK: self-reference + 2-hop cycle rejected by `validate_edge_t6_derived_from`.
4. **`test_cascade_invalidate_emits_audit_row`** — every T6 invalidation emits an audit row with `mutation_type="invalidated_by_cascade"` + chain pointers (base_fact_id, derived_edge_id, entity_path) so the T7 replay primitive can reconstruct the history.

### T2.D — v0.4.0 carry-over `dispatch_contradiction` ingestion wiring (4 PRs)

The v0.4.0 release notes called this out as a v0.4.1 deliverable. Shipped:

| PR | scope |
|---|---|
| **#558 PR-T2.D-1** | `core/lifecycle/contradiction_ingest_detector.py` (~8 KB) — pattern P1 different_tail (CEO-change), P2 divergent_validity. 19 tests. |
| **#559 PR-T2.D-2** | `core/lifecycle/ingest_contradiction.py` (~9 KB) + `_merge.py` pre-merge hook. `JAMES_T2D_INGEST_DISPATCH=1` default OFF. 10 tests. |
| **#561 PR-T2.D-2.b** | A_invalidate cascade race fix via `PendingCascade` deferred-execution. Dispatcher captures cascade requests; `_merge.py` applies them AFTER writing back. Bad-doc-id heuristic: lowest-weight non-manual source. 15 tests. |
| **#560 PR-T2.D-3** | step7 v6 q17 *"Anthropic의 CEO는 누구야?"* + `tests/test_t2d3_dispatch_acceptance.py` (6 tests) end-to-end synthetic CEO-change. |

### QVT α track full closure (6 PRs)

QVT was formalised in v0.4.0 (handover memo #537). v0.4.1 ships its full **α-track implementation**:

| PR | scope |
|---|---|
| **#550 PR-α-1** | `docs/design/v0.4-qvt-alpha-non-saturating-oracle.md` (~14 KB). 3-axis oracle (Path Coverage / Graded Answer / Abstention F1) + fixture schema v5 + per-PR Quality Delta Card pattern + 5 exemption labels + 18-cell ablation matrix shape. |
| **#551 PR-α-2** | step7 fixture v4 → v5. `gold_signals` (3 atomic claims per query) + `abstention_truth` (12 present / 4 absent) + `min_recall: 1.0` on path-annotated queries. 11 invariant tests. |
| **#552 PR-α-3** | `eval/qvt/oracle.py` (~14 KB) — 3-axis scorer. `scripts/qvt_capture_baseline.py` (~13 KB) — operator wrapper, N=3 paired reruns. 20 contract tests. |
| **#553 PR-α-4** | `.github/PULL_REQUEST_TEMPLATE.md` + CLAUDE.md rule 2 extension + `docs/ARCHITECTURE.md` §5.7.10. |
| **#555 PR-α-3 baseline capture** | `eval/qvt/baseline_2a31b20.json` (~25 KB) — canonical reference. N=3 paired, 64-minute operator run. |
| **#556 PR-α-3 oracle calibration** | Korean security-block phrase additions + `blocked=True` short-circuit. `abstention_f1` **0.29 → 0.67** median (+0.38). |

`baseline_2a31b20.json` is now the immovable denominator for every future Quality Delta Card comparison.

### Replayable RAG positioning + other ships

- **#548 Replayable RAG positioning** — README + ARCHITECTURE adopt "Replayable RAG" as the JAMES category framing. Two contrast lines (vs Agentic RAG / vs Mem0).
- **#549 F9 cycle full closure** — q15 *"David Soria Parra가 누구야?"* zero-recall 8-cycle diagnostic ended with `path_recall = 1.0`.
- **#554 v0.4.0 post-mint DOI badge** — README DOI shields bumped to `10.5281/zenodo.20411354`.
- **#557 v0.4.1 entry memo** — 4-LOCK decisions (eager trigger / operator-tagged + LLM flag / strict cycle reject / **C.b foundational-vs-corroborative** — Decision 4 refined during this release).

## Default-off invariant verified (every new opt-in)

| Flag | Default | Verification |
|---|---|---|
| `JAMES_T2D_INGEST_DISPATCH` (T2.D-2) | OFF | `_merge.py` pre-merge hook only fires when `=1` |
| `JAMES_T6_LLM_DERIVATION` (T6.B) | OFF | `extract_derivation_chain` LLM-inferred path needs both flag AND caller-supplied provider |
| T6.D cascade integration | ON (cycle scope) | byte-identical retrieval because migration adds `derived_from: []`; no actual derivations populated yet |

Production fleets pulling v0.4.1 see byte-identical retrieval behavior relative to v0.4.0 unless they opt into one of the flags OR start populating `derived_from`.

## What v0.4.1 does NOT do

- No production flip of `JAMES_T2D_INGEST_DISPATCH` default to ON.
- No production population of `derived_from` (the migration adds `[]`; operator-tagged ingestion + the v0.4.2+ LLM-inferred path fill them in).
- No T3 (Aging) / T4 (Reviewer) / T5 (Snapshot replay) — those land at v0.4.2 / v0.4.3.
- No v0.4-end QVT ablation matrix capture (18 cells, ~20-hour operator run, deferred to late June+).

## Operator action (post-merge)

```powershell
# Optional but recommended for fleets that ingest new docs:
python scripts/migrate_v041_lifecycle.py --root wiki --apply

# Verify byte-stability:
python scripts/migrate_v041_lifecycle.py --root wiki --verify

# GitHub release publish (Zenodo auto-mint follows):
gh release create v0.4.1 --target main \
    --title "v0.4.1 — T6 Causality Chain (CASCADE extension) + QVT α track full closure" \
    --notes-file docs/release_notes_v0.4.1.md
```

## DOI lineage

```
v0.4.1          (this release, Zenodo auto-mint pending)
  ↑ isNewVersionOf
v0.4.0          10.5281/zenodo.20411354
  ↑ isDerivedFrom
v0.4.0-alpha.3  10.5281/zenodo.20391100
  ↑ isDerivedFrom
v0.3.3          10.5281/zenodo.20374227
v0.3.2          10.5281/zenodo.20372649
v0.3.1          10.5281/zenodo.20363998
```

## Verification

- T6 lifecycle suite: 83+ contract tests pass.
- T2.D ingest suite: 50 contract tests.
- QVT α: 22+ oracle contract tests + 11 step7 v5 schema tests + canonical `baseline_2a31b20.json`.
- No regression: 69 pre-T6 cascade tests still green; CASCADE/EVENT separation invariants from v0.4.0 hold unchanged.
- All five v0.4.1-cycle release-gating invariants green (T6.D 4 + T6.A Decision 3).
