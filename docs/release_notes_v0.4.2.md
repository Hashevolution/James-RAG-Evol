# v0.4.2 — T5 Replayable Audit Graph (full event-sourced reconstruction)

**Released**: 2026-06-06 (PR sequence #719 → #720 → #721 → #722 → PR-T5.D).

**Theme**: v0.4.2 closes the EVENT track's last piece. v0.4.0 shipped
`reconstruct_view_at` — a single-supersede-chain replay primitive.
v0.4.2 extends that to **graph-wide event-sourced reconstruction**: a
pure-function `reconstruct_graph_at(t)` that rebuilds the full graph
snapshot at any past time using only `audit_log` event rows, with no
wiki file access. The on-disk wiki, the knowledge tracker, and the
graph engine are not read during reconstruction — the audit_log alone
is the source of truth. That is the **audit-only invariant** (design
memo §2 + §4 I1).

This invariant is what makes the **ABAC + replay** claim in the
corpus retrieval analysis (PR #712 §6) externally demonstrable: an
operator can ship the audit_log JSON to a third party and the third
party can reproduce the graph state at any past `t` and the answer's
decision tree on top, with no other artifact. v0.4.2 is the cycle
that promotes that claim from partial (single-chain) to full
(graph-wide).

## 5-PR sequence

Per `docs/design/v0.4.2-t5-replayable-audit-graph.md`:

### PR-T5 design memo (#719)

`docs/design/v0.4.2-t5-replayable-audit-graph.md` — 15 sections
covering the partial-vs-full scope split, the audit-only invariant,
the event-type taxonomy, the API design, the cross-chain
integration contract, the 5-PR phase plan, the 5 Decision LOCKs,
the cross-cutting impact analysis, and the closure conditions.

### PR-T5.A — event taxonomy + emit helper + audit_log migration (#720)

- `core/lifecycle/replay_audit.py` — `LIFECYCLE_EVENT_TYPES` (7
  entries: T7 supersede ×2, T6 cascade, T1 expiration, T2 dispatch,
  T2.D ingest dispatch, migration backfill) + `EVT_*` constants +
  `is_lifecycle_event(event_type)` exact-match predicate +
  `emit_lifecycle_event(event_type, payload, ...)` synchronous
  in-transaction insert. LOCK 1 (event_payload = JSON string
  column) + LOCK 2 (synchronous in-transaction emit). Never raises
  — matches `audit_bridge.mirror_to_audit_db` contract.

- `scripts/migrate_v042_replay_audit.py` — Idempotent ALTER TABLE
  adding `event_type` + `event_payload` columns to `audit_log`.
  `--dry-run` / `--apply` / `--verify` / `--no-snapshot`. Pre-write
  snapshot at `<db>.pre-v042-migration`. Same operator workflow as
  `migrate_v041_lifecycle.py`.

- `tests/test_t5_event_taxonomy.py` — 19 contract tests
  (taxonomy / is_lifecycle_event / emit round-trip / migration /
  pre-migration compatibility). 19/19 pass.

### PR-T5.B — `reconstruct_graph_at` audit-only primitive (#721)

- `core/lifecycle/replay_graph.py` — `GraphSnapshot` dataclass
  (frozen: edges / supersede_chains / invalidated_ids /
  replayed_at / event_count) + `reconstruct_graph_at(t, *,
  audit_log_path=None, include_event_types=None)`. Per-event-type
  handlers for every `LIFECYCLE_EVENT_TYPES` entry; an import-time
  `assert set(_HANDLERS) == set(LIFECYCLE_EVENT_TYPES)` makes any
  drift a load-time error. LOCK 4 — pure function: the only
  side-channel is the audit_log SELECT. Defence-in-depth: malformed
  JSON, unknown event_type, missing payload, pre-migration DB,
  non-existent file all return the empty snapshot rather than
  raising.

- `tests/test_t5_reconstruct_graph_at.py` — 20 contract tests
  (snapshot shape / supersede chain / cascade + expiration / cutoff
  semantics / determinism + idempotence / I1 audit-only via
  monkeypatched `sqlite3.connect` / `include_event_types` filter /
  malformed rows / backfill bootstrap). 20/20 pass.

### PR-T5.C — cross-chain integration + ARCHITECTURE §5.7.2 extension (#722)

- `core/lifecycle/replay_graph.py` — added `view_from_snapshot(snap,
  head_id, t)`. Single-chain projection of a `GraphSnapshot`. Same
  iterate-forward + last-match + `validity.from <= t < validity.to`
  + invalidated-edge-skip semantics as the live
  `core.lifecycle.supersede_chain.reconstruct_view_at`. The
  `_validity_contains` private helper mirrors the live primitive
  byte-for-byte on edge selection. Cross-chain consistency
  contract: `view_from_snapshot(snap, head, t) ∈
  snap.edges.values() ∪ {None}`.

- `docs/ARCHITECTURE.md` §5.7.2 — Added "Graph replay invariant"
  subsection under the existing "Trace replay invariant". Pins the
  audit-only invariant in the architecture spec.

- `tests/test_t5_cross_chain_consistency.py` — 11 contract tests
  (view-from-snapshot matches `reconstruct_view_at` semantics on
  same chain / multi-link window selection / left-closed boundary /
  invalidated edge excluded / consistency invariant / cutoff
  respected). 11/11 pass.

### PR-T5.D — release-gating invariants + closure (this PR)

- `tests/test_t5_release_gating_invariants.py` — 5 release-gating
  tests against in-memory SQLite fixtures with the real `emit_*` +
  `reconstruct_*` code path (no mocks of the primitives themselves):

  1. `test_graph_replay_at_t_matches_event_log` — every successful
     `emit_lifecycle_event` produces exactly one fold step in the
     snapshot (I4 weak form, mutation-wiring-free).
  2. `test_replay_audit_only_no_db_scan` — `reconstruct_graph_at`
     opens only the audit_log DB (I1, via monkeypatched
     `sqlite3.connect`).
  3. `test_replay_preserves_supersede_chain` — interleaved emits
     across two heads keep their chains separate and in order (I2).
  4. `test_replay_respects_cascade_invalidate` — `cascade.invalidate`
     removes from `edges` AND adds to `invalidated_ids` (I3).
  5. `test_reasoning_trace_replay_invariant` — reasoning trace rows
     and lifecycle rows coexist in the same `audit_log` without
     interference (§5.7.2 trace replay still works after the v0.4.2
     schema migration).

- `CHANGELOG.md` `[0.4.2]`.
- `.zenodo.json` updated to v0.4.2.
- `docs/release_notes_v0.4.2.md` (this file).

## Done when — all items satisfied at v0.4.2 (2026-06-06)

- ✅ T5.A schema + migration land + 19 contract tests pass.
- ✅ T5.B `reconstruct_graph_at` audit-only primitive land + 20
  contract tests + 4 invariants (I1/I2/I3 strong, I4 weak).
- ✅ T5.C cross-chain integration + ARCHITECTURE §5.7.2 extension
  land + 11 contract tests + cross-chain consistency invariant.
- ✅ T5.D 5 release-gating invariants land green against in-memory
  SQLite fixtures + real `emit_*` / `reconstruct_*` code path.
- ✅ Migration script idempotent + snapshot-first + verify mode
  detects pre-migration DB.
- ✅ Pre-T5 reasoning trace replay (`tests/test_replay_trace.py`,
  §5.7.2) still green — no regression on the v0.4.1 invariant.
- ✅ Pre-T5 supersede chain (`core.lifecycle.supersede_chain`,
  v0.4.0 T7) unchanged — no import of replay_audit/replay_graph
  yet; the cross-chain consistency is between the live primitive
  and the audit-only equivalent, not a replacement.
- ✅ Closure docs published: this file + CHANGELOG `[0.4.2]` +
  `.zenodo.json` v0.4.2.

## Default-off invariant preserved

No new env flag was added in this cycle. The new columns
(`event_type` / `event_payload`) default to NULL on existing rows
and are only populated by future `emit_lifecycle_event` calls —
production byte-identical until the mutation-site wiring follow-up
(v0.4.2.x or v0.4.3) starts emitting lifecycle events.

## Verification

- T5.A `tests/test_t5_event_taxonomy`: 19/19 PASS
- T5.B `tests/test_t5_reconstruct_graph_at`: 20/20 PASS
- T5.C `tests/test_t5_cross_chain_consistency`: 11/11 PASS
- T5.D `tests/test_t5_release_gating_invariants`: 5/5 PASS
- v0.4.1 `tests/test_replay_trace` (§5.7.2): 16/16 PASS
- **Total: 71/71 PASS** across the T5 lifecycle suite + the
  pre-existing reasoning trace replay.

## What v0.4.2 does NOT do

- **No mutation-site wiring**. The T1 expiration cascade, T2 dispatch
  contradiction, T2.D ingest dispatch, T6 cascade invalidate, and T7
  supersede edge_created call sites do NOT yet call
  `emit_lifecycle_event` — that wiring is a separate cross-cutting
  change (lifecycle / graph / audit_log all touched) and was kept
  out of v0.4.2 so the read-side primitive can land independently of
  the write-side rollout. Production `audit_log` keeps emitting only
  reasoning trace rows; `reconstruct_graph_at(now)` returns the
  empty snapshot until wiring lands.

- **No I4 against the live wiki**. Strong I4 (snapshot at t = now
  byte-equal to the live graph state) requires mutation-site wiring
  + a live-state fixture. PR-T5.D pins the round-trip form: every
  `emit_lifecycle_event` becomes exactly one fold step. Strong I4
  follows in the wiring follow-up.

- **No `derived_from` re-derivation from event log**. T6 `derived_from`
  fields are still managed by the existing causality chain code paths
  (v0.4.1 PR-T6.C / C.b). The event log carries the cascade
  invalidate events; reconstructing the *derivation graph itself*
  from the event log is a v0.4.3+ concern.

- **No T3 Evidence Aging, no T4 Reviewer Authority Hierarchy**.
  Both deferred to v0.4.3+. The roadmap (§ROADMAP `v0.4.3 / v0.5
  prep`) is unchanged.

## Out of scope (deferred to v0.4.2.x or v0.4.3)

- Mutation-site wiring (lifecycle call sites → `emit_lifecycle_event`).
- Strong I4 against the live on-disk wiki.
- `audit_log` UI layer surfacing lifecycle events (`/admin/audit/list`
  already shows them by `endpoint` mirror but the typed view is a
  separate UI cycle).
- Production `audit_log` historic backfill (operator decision; the
  `EVT_BACKFILL_SNAPSHOT` event type is the bootstrap path).
- ABAC state visualizer on top of `reconstruct_graph_at` (replay
  primitive is the layer; the visualizer is the next layer).

## Cycle γ connection

v0.4.2 unblocks Cycle γ (`docs/design/v0.4-cycle-gamma-external-
benchmark-integration.md`). The cross-bench measurement deliverable
in Phase D of cycle γ needs the "ship the audit_log → reproduce the
state" demo artifact; the primitive that produces it now exists.

## Sources

- Design memo: `docs/design/v0.4.2-t5-replayable-audit-graph.md`
- Layer 4 Lifecycle roadmap: `docs/design/v0.4-lifecycle-semantics-roadmap.md`
- Architecture: `docs/ARCHITECTURE.md` §5.7.2 (Trace replay +
  Graph replay invariants)
- Corpus retrieval analysis (external evidence path):
  `reports/research-runs/corpus-retrieval-competitive-analysis-
  20260605.md` §6
