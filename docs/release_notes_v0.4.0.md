# v0.4.0 — Layer 4 Lifecycle Semantics (T1 + T7 + T2 first bundle)

**Theme**: v0.4.0 final ships the Layer 4 Lifecycle Semantics first bundle — **T1 Temporal Validity + T7 Supersede Chain + T2 Contradiction Arbitration** — as a release-gated 8-PR Sprint 5 sequence. The CASCADE vs EVENT separation invariant the v0.4 cycle was retargeted around is now **provable end-to-end** via `tests/test_t7_release_gating_invariants.py` (run against the actual `tests/fixtures/lifecycle/` wiki, not mocks). Default-OFF invariant preserved across every opt-in flag added in this cycle.

## Why this is a citable release

v0.4.0 is the cycle's tagline shift: the runtime now distinguishes between **destructive bad-source removal** (CASCADE, Layer 3, T2.A path) and **history-preserving fact updates** (EVENT, Layer 4, T2.B path → T7 supersede chain). The two paths share no code on disk and the release-gating tests prove they cannot accidentally call each other.

This is the **Mem0 differentiator** wired into the production stack:

- **Mem0** routes contradiction decisions through an LLM-judge (latency + non-determinism + audit-opacity tax).
- **JAMES** routes them through `classify_contradiction` — a 4-rule deterministic decision tree (~10.2 KB pure function, no I/O, no clock side-effects), audited at every dispatch with `mutation_type` rows in `audit_log`.

The 8-PR sequence ships the primitive surface (PR-0 + PR-T1.A schema) → the temporal cascade (PR-T1.B) → the supersede chain ops (PR-T7.A) → the **release-gating invariants** (PR-T7.B, three tests against the real fixture) → the classifier (PR-T2.A) → the routing wire for both A-path and B-path (PR-T2.B + PR-T2.C). The closure PR (PR-T7.C, this one) flips ROADMAP + docs.

## What v0.4.0 delivers

### Layer 4 lifecycle primitives

| Module | Surface | LoC | Tests |
|---|---|---|---|
| `core/lifecycle/clock.py` | `now()` — single monkeypatch point | ~2 KB | included in PR-0 51 |
| `core/lifecycle/schema.py` | field constants + validators + defaults | ~9 KB | 51 |
| `scripts/migrate_v04_lifecycle.py` | `--dry-run` / `--apply` / `--verify` | — | 18 |
| `core/lifecycle/expiration_cascade.py` | `is_source_expired` + `expiration_cascade` | ~15.5 KB | 16 |
| `core/lifecycle/supersede_chain.py` | `supersede_edge` + `walk_supersede_chain` + `reconstruct_view_at` | ~13.8 KB | 15 |
| `core/lifecycle/contradiction_arbiter.py` | `classify_contradiction(old, new, *, now) → A/B/ignore` | ~10.2 KB | 17 |
| `core/lifecycle/contradiction_router.py` | `route_a_invalidate` + `route_b_supersede` + `dispatch_contradiction` | ~11.3 KB | 19 |
| `tests/test_t7_release_gating_invariants.py` | 3 invariants + 2 chain-walker sanity | — | 5 |

**123+ contract tests** pass when run together. The release-gating suite (PR-T7.B) runs against the curated `tests/fixtures/lifecycle/` wiki, not mocks — every PR thereafter that touches CASCADE or the supersede chain re-validates the invariants automatically.

### Three release-gating invariants (the part that makes "provable" not aspirational)

`tests/test_t7_release_gating_invariants.py` — all five tests must remain green:

1. **`test_supersede_does_not_trigger_cascade`** — defense-in-depth. Patches both `core.cascade.cascade_remove_doc_from_sources` AND the underlying `_delete.*` entry point with `MagicMock`; runs `supersede_edge` on a real fixture edge; asserts neither mock was called. If anyone accidentally wires CASCADE into the B-path in a future PR, this test fires.
2. **`test_cascade_preserves_supersede_chain`** — fires real CASCADE against the fixture; asserts chain links on unrelated edges are byte-identical post-CASCADE. The separation isn't just "CASCADE doesn't touch supersede chains today" — it's "CASCADE provably can't ever overwrite supersede metadata."
3. **`test_historical_replay_via_chain`** — end-to-end. CASCADE removes a bad source → `supersede_edge` rewrites a different edge → `reconstruct_view_at` queried at three timestamps returns the correct chain link at each. This is the "replay" primitive — the thing that makes T7 worth shipping, working through a real CASCADE event.

### LEO L.D measurement-substrate (10 cycles, PR #526~#536)

L.D wrapper end-to-end validation surfaced two latent issues during the operator-execution phase that L.D F1~F7 + Idea 1 + F2 + F6 + F7 collectively isolated to the right layer (each cycle ~30 minutes; **"diagnose cost > fix cost"** lesson captured in memory):

- **Router latent backend-id bug** (#526) — D5 closure's "fall back to legacy → just extra audit rows" promise had silently degraded to "every routing decision raises" because `_legacy_backend_id` returned a model tag rather than a registry key. First fixed end-to-end by an operator who actually flipped `JAMES_AUTO_ROUTER=1` server-side.
- **bench → step7 chat-mode passthrough reattribution** (#531, F2) — `IntentClassifier` ran 14 / 14 (100% accuracy). The actual chain: `external` role → policy gate blocks `query.internal_rag` → engine returns `handle_chat` regardless of classifier output. F1's JWT-bearer pattern (`JAMES_BENCH_BEARER`) remains the right fix; the earlier attribution was wrong.
- **q15 zero-recall — 8-cycle diagnosis chain** (F1 → F2 → F6 → F7 → BL-9 prep → BL-9 acceptance): not stochasticity, not classifier, not embedding model alone. Final cluster: **proper-noun-mediated retrieval is the MiniLM weakness**; bge-m3 swap is keep, but the q15 fix moves to the query expansion layer (F9 spawned).

### QVT — Quality Verification Track handover (#537)

`docs/handovers/v0.4-quality-verification-track.md` (12 §, ~240 lines) formalises the meta-frame the L.D 10-cycle work was building.

- **Diagnosis**: cost is rigorously measured (V3' protocol cross-validated through Robin's 26b matrix work) but quality is assumed; routing machines (D1 / D5 / LEO) all flag-OFF dormant.
- **Plan**: Sprint 1 non-saturated quality oracle (the α the cycle is missing) → Sprint 3~5 PR-gate ambient → v0.4 end ablation matrix → v0.5 Domain Pilot flag-ON.
- **The Sprint 5 8-PR sequence in this release IS the QVT step-3 PR-gate first installment.**

## Default-off invariant verified (every new opt-in)

| Flag | Default | Verification |
|---|---|---|
| `JAMES_SCOPE_ROUTING` (LEO L.C) | OFF | `test_flag_off_ignores_bound_scope` + pipeline.py `scope_context(None)` no-op path |
| `JAMES_AUTO_ROUTER` (D5) | OFF | unchanged from alpha.3 |
| `JAMES_ADAPTIVE_BUDGET` (D1) | OFF | unchanged from alpha.3 |
| `JAMES_EMBEDDING_MODEL` (Sprint 4 prep / BL-9) | unset → legacy MiniLM | `models/miniLM` + `chroma_db` path resolution unchanged. Default flip waits on F9 query-expansion fix. |
| `JAMES_ENABLE_CLAUDE_BACKEND` (F3 / #535) | OFF | wrapper opt-in only; default fleet runs small-tier-only |

**Production fleets pulling v0.4.0 see byte-identical retrieval behaviour relative to v0.4.0-alpha.3** unless they opt into one of the flags.

## What v0.4.0 does NOT do

- **No ingestion-path caller** for `dispatch_contradiction`. The Sprint 5 PRs ship the primitive surface + the routing wire; the call site that detects "new fact arrived → look up old edge → invoke dispatch" is the next operator integration, carried into **v0.4.1** with the canonical CEO-change STEP 7 bench scenario.
- **No production BL-9 embedding swap default flip**. The bge-m3 swap is opt-in via `.env` + the operator-run `scripts/migrate_embedding.py`. The default flip lands in a follow-up PR once F9 query-expansion gives the swap a path-recall acceptance gate to pass.
- **No T3 / T4 / T5 / T6**. Those land at **v0.4.1 / v0.4.2 / v0.4.3** per the ROADMAP phase plan. v0.4.0 ships only T1 + T7 + T2 — the first bundle that makes the CASCADE/EVENT separation provable.

## Sprint 5 8-PR sequence (the actual delivery shape)

| PR | Phase | Surface |
|---|---|---|
| #524 | PR-0 | `core/lifecycle/schema.py` + `core/lifecycle/clock.py` + 51 tests |
| #525 | PR-T1.A | `scripts/migrate_v04_lifecycle.py` + 18 tests |
| #538 | PR-T1.B | `core/lifecycle/expiration_cascade.py` + `scripts/run_expiration_cascade.py` + 16 tests |
| #539 | PR-T7.A | `core/lifecycle/supersede_chain.py` + 15 tests |
| #540 | PR-T7.B | `tests/test_t7_release_gating_invariants.py` + `tests/fixtures/lifecycle/` + 5 tests |
| #541 | PR-T2.A | `core/lifecycle/contradiction_arbiter.py` + 17 tests |
| #542 | PR-T2.B | `core/lifecycle/contradiction_router.py` (A-path) + 13 tests |
| #543 | PR-T2.C | router B-path + final dispatch + 6 additional tests |
| #544 | PR-T7.C | this closure PR — ROADMAP / CHANGELOG / .zenodo.json / README badge / release notes |

## DOI lineage

- v0.4.0 (this) — `10.5281/zenodo.20411354` (minted at publish; recorded by PR #554), **isNewVersionOf** v0.4.0-alpha.3
- v0.4.0-alpha.3 — `10.5281/zenodo.20391100` (LEO L.0→L.D + Sprint 4 prep + CI / module hygiene)
- v0.4.0-alpha.2 — prepped (PR #508) but **never released to GitHub**; no DOI minted. Scope superseded by alpha.3.
- v0.3.3 — `10.5281/zenodo.20374227` (D6 retry-wiring closure)
- v0.3.2 — `10.5281/zenodo.20372649`
- v0.3.1 — `10.5281/zenodo.20363998`

> **Correction (2026-08-19)** — this block previously carried a row
> reading `v0.4.0-alpha.1 — 10.5281/zenodo.20374227` and left v0.3.3
> as "pre-v0.4" with no DOI. **`v0.4.0-alpha.1` never existed**: the
> v0.4 cycle's first alpha tag was alpha.2 (PR #508 prep, itself never
> released — see its own `.zenodo.json`: *"v0.4.0-alpha.2 is the first
> alpha tag of the v0.4 cycle"*), and alpha.3 is the second. There is
> no alpha.1 PR, tag, release, or CHANGELOG entry.
>
> `20374227` belongs to **v0.3.3**: PR #520 (`v0.4.0-alpha.3 post-mint
> DOI chain`) added it to `.zenodo.json` as alpha.3's `isNewVersionOf`,
> and alpha.3's own notes name that target — *"the explicit
> isNewVersionOf chain back to v0.3.3 (10.5281/zenodo.20XXXXXX,
> operator-supplied at publish time)"*. PR #520 is the operator filling
> that placeholder.
>
> Root cause: the README DOI badge went v0.3.1 (#466) → v0.3.2 (#490)
> → **skipped v0.3.3** → alpha.3 (#520), so v0.3.3's number sat
> unrecorded for three days and was written into this file against the
> wrong label. `docs/release_notes_v0.4.1.md`, `ROADMAP.md`,
> `.zenodo.json` and the M9 joint-deposit draft all carry the correct
> `v0.3.3 = 20374227` mapping and were not changed.

## Operator publish steps (after PR-T7.C merges)

1. `git tag -a v0.4.0 -m "v0.4.0 — Layer 4 Lifecycle Semantics first bundle (T1+T7+T2)"`
2. `git push origin v0.4.0`
3. GitHub release UI → "Draft a new release" → tag `v0.4.0` → title `v0.4.0 — Layer 4 Lifecycle Semantics first bundle` → paste this file's body as the description → publish
4. Zenodo auto-mint fires via the GitHub webhook; the new DOI lands in the deposit list within ~5 minutes
5. Open a small follow-up PR to drop the freshly-minted DOI into the README badge + `.zenodo.json` `related_identifiers` chain (the chain-back-to-self that v0.4.0 publishes can only be filled in once minted)

## Acknowledgements

LEO (Younghu, external contributor `222315AIS`) — Evidence-Scope Routing track design memo, the input-side routing axis that v0.4.0-alpha.3 carried and v0.4.0 hardened through the L.D measurement substrate. First external contributor to this repo.

Robin Converse (Triava Labs, 26b MoE cross-stack) and Ali Afana (Provia, mid-June managed-Gemini cross-stack) — V3' protocol cross-validation collaboration; cross-stack comparison runs (Robin V3'.e schema-adopted, Ali Track 3 swap_eval) pinned with all opt-in routing flags OFF for apples-to-apples purity.
