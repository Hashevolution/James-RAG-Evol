# v0.4.3 — RAB (Replayable-Audit Benchmark) v0.1.1 + Cycle γ multi-hop arc closure

**Released**: 2026-06-10 (R1 trace: PR sequence #758 → #760 → #761 →
#762 → #763 → #764 → #766 → #767; Cycle γ multi-hop arc trace: PRs
#752 → #753 → #754 → #755 → #756 → #757).

**Theme**: v0.4.3 ships **RAB v0.1.1** — the first replayable-audit
benchmark for RAG / agent systems whose 3 metrics (AC / RF / PC) are
operationalisations of EU AI Act Articles 10, 12, 19 (in force
2026-08-02). Same cycle closes the cycle γ multi-hop arc (7 probes,
6 honest nulls, 2 self-corrections — `multi-hop improvement` reframed
out of the JAMES roadmap; **graph build O(N²) finding** lifted into RAB
as the RF-cost axis).

Two tracks closed; no production runtime change. JAMES production
audit / lifecycle / graph code paths are unchanged byte-for-byte —
**RAB measures what was already there**, it does not modify it. The
adapter (`eval/rab/adapters/james.py`) calls the existing
`core.lifecycle.replay_audit.emit_lifecycle_event` and
`core.lifecycle.replay_graph.reconstruct_graph_at` against a
workspace-scoped audit.db; production audit.db is untouched.

## RAB v0.1.1 — the headline

A frozen benchmark spec + scenario fixture + deterministic scorer +
reference / JAMES / Baseline-0 adapters + the first gap-table
measurement.

### Authority axes externalised (4 axes, locked before any
measurement)

1. **Anchors**: EU AI Act Art. 10(2)(b) / 12(1)(2)(b) / 19 verbatim
   + W3C PROV `wasDerivedFrom` + NIST AI RMF + Mathkar et al. agent
   trace survey (arXiv 2606.04990) which explicitly names
   "realistic execution-trace benchmarks" as an open challenge → RAB
   responds to a published gap, not a self-defined one.
2. **Scoring**: deterministic only. No LLM judge anywhere in the
   scorer (SPEC §6.1, pinned by test).
3. **Application**: generic audit-log JSONL interface — any system
   that can export an append-only log per SPEC §1 is scoreable.
   Baseline-0 (vanilla quickstart + Python-logging) is scored
   alongside JAMES; the **gap structure across SUTs is the headline**
   (SPEC §5 / §6.5).
4. **Verification**: every result ships with the SPEC §4
   re-verification triple — `result.json`, exported audit log
   JSONL, mapping table JSON — committed to `reports/rab/`. Re-running
   the deterministic scorer on the same artifacts must reproduce the
   numbers bit-for-bit.

### Honest framing — what RAB is not

* Not a regulatory compliance certification. RAB operationalises
  Art. 10 / 12 / 19 *concepts*; SPEC §6.3 says this wherever scores
  are published.
* Not an architecture novelty claim. ActiveGraph (arXiv 2605.21997,
  2026-05-21) independently published event-sourced log +
  deterministic replay + log-only reconstruction. **The contribution
  is the benchmark**, not the audit-native runtime (R1.0 prior-art
  finding, memory `project_r1_replayable_audit_benchmark`).
* Not a JAMES-wins announcement. JAMES = reference on scenario-S1 is
  *expected* per SPEC §6.5. The bolt-on-vs-audit-native gap is the
  finding.

### R1.0 → R1.5 sequence

- **R1.0 prior-art + EU AI Act anchors (#758/#760/#761)** —
  benchmark-vacancy confirmed; Art. 12/10/19 mapping verbatim; AI
  Act effective date 2026-08-02 confirmed via Art. 113.
- **R1.1 SPEC v0.1.1 FROZEN (#762)** — `eval/rab/SPEC-v0.1.md`. The
  abstract log interface (SPEC §1), three metrics (§2), scenario
  contract (§3), reporting format (§4), 5 baselines (§5), 6
  honesty clauses (§6). Spec changes never retro-apply; results
  carry their spec version (SPEC §6.6).
- **R1.2 scenario-S1 fixture (#763)** —
  `eval/rab/scenarios/s1_lifecycle_small.json`. 40 ops (11 INGEST /
  4 UPDATE / 3 SUPERSEDE / 2 DELETE / 20 QUERY) + 10 checkpoints +
  Northbridge Labs synthetic prose. Public-domain content,
  deterministic ids.
- **R1.3 driver + scorer + reference adapter (#764)** —
  `eval/rab/{driver,scorer}.py` + `eval/rab/adapters/reference.py` +
  `tests/test_rab_benchmark.py` (14 tests). The reference adapter
  caught a SPEC v0.1.0 defect during implementation (supersede-born
  docs untraceable under INGEST-only PC rule), corrected to v0.1.1
  before any measurement was taken — adapter-as-spec-validation
  worked.
- **R1.4 pre-registration + JAMES adapter + Baseline-0 adapter +
  scenario-S1 measurement (#766 / #767)** — see gap table below.
  31 tests green (reference 14 + Baseline-0 8 + JAMES 9).
- **R1.5 = this release** — packaged for external review.

### Gap table (RAB SPEC v0.1.1 / scenario-S1, deterministic,
re-runnable from `reports/rab/`)

| SUT | AC overall | AC INGEST | AC UPDATE | AC SUPERSEDE | AC DELETE | AC ANSWER | RF-exact | RF-graded | PC | log events |
|---|---|---|---|---|---|---|---|---|---|---|
| reference (self-verify gate) | **1.000** | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **1.000** | 1.000 | **1.000** | 80 |
| **JAMES** | **1.000** | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **1.000** | 1.000 | **1.000** | 80 |
| **Baseline-0** (floor) | **0.275** | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.000** | 0.000 | **0.000** | 40 |

* AC INGEST = 1.0 across all three (default logging covers add-doc).
* AC UPDATE / SUPERSEDE / DELETE / ANSWER = 0 for Baseline-0 (vanilla
  logger doesn't distinguish them, has no supersede taxonomy, often
  doesn't log deletes, emits no ANSWER event).
* RF = 0 for Baseline-0 (logs carry strings, not payload — replay
  has nothing to fold).
* PC = 0 for Baseline-0 (no `parent_id` chain).
* JAMES = reference on S1 is expected (SPEC §6.5); the headline is
  the audit-native vs default-logging gap.

Honest tier: **⭐⭐ scenario-S1 audit-native vs floor gap confirmed**
(deterministic, re-runnable from artifacts). ⭐⭐⭐ cross-scenario
remains ungated until R1.5+ ships additional scenarios.

### Reproduce the table

```bash
git checkout v0.4.3
python -m pytest tests/test_rab_benchmark.py \
                 tests/test_rab_baseline0.py \
                 tests/test_rab_james_adapter.py    # 31 tests, all green
python scripts/research/rab_run.py --sut reference  # AC 1.0 / RF 1.0,1.0 / PC 1.0 (gate)
python scripts/research/rab_run.py --sut james      # AC 1.0 / RF 1.0,1.0 / PC 1.0
python scripts/research/rab_run.py --sut baseline0  # AC 0.275 / RF 0.0,0.0 / PC 0.0
# inspect reports/rab/*.result.json — values match
# the committed v0.4.3 artifacts bit-for-bit (SPEC §4 determinism).
```

The driver + scorer is deterministic over a fixed artifact set. The
adapter step has wall-clock-dependent timestamps but the AC/RF/PC
values are stable across re-runs (`test_baseline0_deterministic`,
`test_james_deterministic_mode_repeat`).

## Cycle γ multi-hop arc closure (companion track)

Cycle γ's MuSiQue probes concluded that **"multi-hop improvement"
is not a JAMES roadmap item**. The wall is unsupervised supporting-
selection, not retrieval breadth and not model ceiling. Retrieval
recall on the top-8 set is 0.76 (both R0 and ablated); the gap to
oracle-grounded performance is the selection step. Memory:
`project_cycle_gamma_phase_c2_retrieval_bottleneck`.

7-probe trace (PRs #752 → #757):

* **#752** MuSiQue → retrieval-bottleneck hypothesis (later corrected
  by #754)
* **#753** D1 static decompose → INSUFFICIENT (hop-2 anaphora)
* **#754** D1b iterative → INSUFFICIENT + sources-top3 artifact
  isolation: `retrieve(top-8)` 13/25 both arms — the diagnosis pivot.
* **#755** D2 rerank-OFF → synth-noise is the actual lever
  (oracle 72% vs noisy 12%, a 9× jump when supporting paragraphs are
  given directly).
* **#756** D3 evidence-select → INSUFFICIENT → **multi-hop arc
  closure**.
* **#757** D4 graph: feature already verified (250+ tests); Path-D
  over-investment PASS; **★ graph build O(N²) finding** — folded
  into RAB as the RF-cost axis (SPEC §2.2 `cost_s_per_1k_events`).
  Lifted out of MuSiQue scope where it had no leverage, lifted into
  RAB scope where it has structural meaning.

Operator-facing artifacts: env-gate `JAMES_RETRIEVE_TOP_K` /
`JAMES_RERANK_TOP_K` (defaults 8 / 5; byte-identical when unset).
**Default-off invariant preserved.**

## R0 P0 (pre-cycle disciplinary + security)

* **#750** R5 pre-registration rules + R2 measurement-discipline rules
  (`docs/rules/`) checked in as repo-side audit trail of CLAUDE.md
  rules previously memory-only. Bus-factor + auditability fix
  (R2 external review action item).
* **#751** `starlette` 1.0.1 (CVE) + `chromadb` risk-accept note
  (`docs/security/`).

## Verification

* RAB test suite (this release): **31/31 PASS**
  - `tests/test_rab_benchmark.py` — 14 (reference adapter + scorer +
    fault injection)
  - `tests/test_rab_baseline0.py` — 8 (floor pinned)
  - `tests/test_rab_james_adapter.py` — 9 (audit-native demo +
    workspace isolation + lifecycle bridge + reconstruct_graph_at
    agreement + log-only replay invariant)
* RAB measurement artifacts committed under `reports/rab/`:
  - `reference-S1-*.{result.json,log.jsonl,mapping.json}`
  - `james-S1-*.{result.json,log.jsonl,mapping.json}`
  - `baseline0-S1-*.{result.json,log.jsonl,mapping.json}`
  Each result.json carries `scenario_sha`, `log_sha`,
  `mapping_table_sha`, `sut_version`, `runner_env` for SPEC §4
  re-verification.
* JAMES core test suite: no regression (no `core/` change).

## What v0.4.3 does NOT do

* **No production runtime change in JAMES core**. The audit / lifecycle
  / graph paths are unchanged byte-for-byte. RAB measures the existing
  paths via a workspace-scoped adapter; production `audit.db` is never
  touched.
* **No cross-scenario RAB result**. S1 is the only scenario in v0.1.1.
  Additional scenarios (S2 cross-lingual / S3 larger graph / etc.)
  unlock the ⭐⭐⭐ cross-scenario ceiling in a future cycle.
* **No Baseline-1**. SPEC §5 names Baseline-1 as
  "default-quickstart + LangSmith/OTel tracing mapped to SPEC §1".
  It is a separate SUT in a future cycle; this release is the
  default-vs-native gap only.
* **No mutation-site wiring follow-up**. v0.4.2's audit-only invariant
  (I4 strong form) still depends on the mutation-site wiring cross-
  cutting cycle (T1/T2/T2.D/T6/T7 call sites → `emit_lifecycle_event`).
  Out of scope for v0.4.3.
* **No multi-hop retrieval improvement**. Cycle γ closure explicitly
  re-framed this as NOT a JAMES roadmap item (memory
  `project_cycle_gamma_phase_c2_retrieval_bottleneck`).
* **No regulatory compliance certification claim**. SPEC §6.3.

## Out of scope (deferred)

* Baseline-1 (LangSmith / OTel adapter).
* RAB scenario-S2 + cross-scenario gating.
* Replication invites to ActiveGraph + other audit-native runtimes
  (R1.6, separate collab scope —
  `feedback_eval_cycle_vs_collab_arc_separation`).
* Mutation-site wiring (T1/T2/T2.D/T6/T7 → `emit_lifecycle_event`)
  carried forward from v0.4.2.

## Sources

* RAB SPEC: `eval/rab/SPEC-v0.1.md`
* Pre-registration: `docs/research/r1-4-preregistration-2026-06-10.md`
* Gap-table handover: `docs/handovers/v0.4-r1-4-gap-table-2026-06-10.md`
* Cycle γ closure handover (companion track):
  `docs/handovers/v0.4-cycle-gamma-phase-c2-musique-retrieval-bottleneck-2026-06-10.md`
* Session entry: `docs/handovers/v0.4-next-session-entry-2026-06-10-r1-rab.md`
