# RAB — Replayable-Audit Benchmark — SPEC v0.1 (FROZEN)

**Status**: FROZEN 2026-06-10. Changes require a version bump (v0.2…)
with a changelog; results are always reported against a spec version.
**Design rationale**: `docs/design/v0.4-r1-replayable-audit-benchmark.md`
(prior-art + external-anchor verification completed 2026-06-10).
**Scope**: RAB operationalises the record-keeping / traceability /
provenance concepts of Regulation (EU) 2024/1689 Articles 10, 12, 19
(in force 2026-08-02) into deterministic, runnable metrics. RAB does
**NOT** certify regulatory compliance.

---

## 1. Abstract audit-log interface

A system under test (SUT) is scoreable iff it can export its audit log
as **JSONL**, one event per line, each line an object with at least:

| field | type | requirement |
|---|---|---|
| `event_id` | string | unique within the log |
| `ts` | ISO-8601 string | monotone non-decreasing in file order |
| `event_type` | string | from the SUT's own vocabulary; mapped once to RAB's canonical types via a declared **mapping table** (part of the submission) |
| `parent_id` | string \| null | the event this one derives from (provenance edge) |
| `inputs_hash` | string | hash of the event's inputs (SUT-chosen stable hash) |
| `payload` | object | event-type-specific; for state-mutating events MUST contain enough to replay the mutation |

RAB canonical event types: `INGEST`, `UPDATE`, `SUPERSEDE`, `DELETE`,
`RETRIEVE`, `RERANK`, `SYNTH`, `VERIFY`, `ANSWER`, `OTHER`.
A SUT's mapping table maps its native types onto these; unmapped
decision-bearing events count against AC (they were executed but not
auditable in canonical terms).

The log MUST be append-only in spirit: scoring uses the file as given;
no out-of-band artifacts are consulted for RF (that is the point).

## 2. Metrics (deterministic — no LLM judge anywhere)

### 2.1 AC — Audit Completeness
> Anchor: Art. 12(1) "automatic recording of events (logs) over the
> lifetime of the system"; Art. 12(2) "traceability of the functioning".

- The RAB **driver** executes the published scenario (§3) against the
  SUT and records ground truth `E_exec`: the ordered list of
  decision-bearing actions the driver requested + observed (each with a
  driver-assigned `op_id`).
- The SUT's exported log yields `E_audit`: events matched to driver ops
  by (canonical type, scenario step window). One log event may match at
  most one driver op (greedy in time order).
- **AC = |matched| / |E_exec|**, reported overall and per canonical type.

### 2.2 RF — Replay Fidelity
> Anchor: Art. 12(2)(b) logs must facilitate post-market monitoring —
> i.e. post-hoc reconstruction from logs.

- The scenario defines **checkpoints** k = 1..K (after each mutating
  step). At each checkpoint the driver snapshots ground-truth state
  `S_k` via the SUT's *live* query interface (canonical form, §2.4).
- After the run, the **replayer** is given ONLY the exported log and
  must produce `R_k` for every checkpoint (the SUT provides its replay
  command; for JAMES this is `reconstruct_graph_at(t_k)`).
- **RF-exact = #{k : canon(R_k) == canon(S_k)} / K** (byte-identical
  after canonicalisation).
- **RF-graded = mean_k Jaccard(items(R_k), items(S_k))** (partial credit).
- **RF-cost** (scale axis): wall-clock seconds per 1 000 log events
  folded, measured during replay. Reported alongside, never blended
  into the score.

### 2.3 PC — Provenance Coverage
> Anchor: Art. 10(2)(b) "origin of data"; W3C PROV `wasDerivedFrom`.

- For every `ANSWER` event, its cited source identifiers must chain
  back through `parent_id` links to an `INGEST` event:
  `ANSWER → SYNTH → RETRIEVE → INGEST` (intermediate hops may repeat;
  the chain must be unbroken and acyclic).
- **PC = traceable citations / total citations** across all answers.
- v0.1 scopes provenance to **cited sources only** (identifiers the
  SUT emits with its answer). Claim-level provenance is explicitly out
  of scope (a future spec version with its own honesty review).

### 2.4 Canonical form
State snapshots serialise as JSON with: keys sorted, arrays of
entities/edges sorted by id, timestamps normalised to UTC ISO-8601,
floats fixed to 6 dp, no insignificant whitespace. `canon()` is this
serialisation; it is part of the scorer and identical for S and R.

## 3. Scenario (fixture) requirements

A RAB scenario is a published JSON file: an ordered list of driver ops
with deterministic content (no randomness, no time-dependent inputs):

```
[{op_id, op: INGEST|UPDATE|SUPERSEDE|DELETE|QUERY, args...,
  checkpoint: bool}, ...]
```

- v0.1 ships **scenario-S1** ("lifecycle-small"): ~40 ops covering
  ingest (10 docs), update (5), supersede (3), delete (2), query (20),
  with K=10 checkpoints. Content is synthetic English prose with
  deterministic ids — public domain, no licensing friction.
- Scenario files are versioned and hash-pinned; scores cite
  `(spec vX.Y, scenario sZ, scenario-sha)`.

## 4. Reporting

A RAB result is the tuple:

```
{spec: v0.1, scenario: S1, sut, sut-version,
 AC: {overall, per-type}, RF: {exact, graded, cost_s_per_1k},
 PC, log_sha, mapping_table_sha, runner_env}
```

All inputs needed to re-verify (log file, mapping table, scenario) are
published with the score. Re-running the scorer on the same artifacts
MUST reproduce the numbers bit-for-bit (the scorer is deterministic).

## 5. Baselines (part of the v0.1 release)

| SUT | Expectation (to be measured, not assumed) |
|---|---|
| **Baseline-0**: vanilla RAG quickstart (LangChain or LlamaIndex, default logging) | establishes the floor |
| **Baseline-1**: Baseline-0 + tracing (LangSmith/OTel export mapped to §1) | measures how far bolt-on tracing gets |
| **JAMES** | audit-native reference |
| (invited) ActiveGraph or other audit-native runtimes | second audit-native point |

The headline of any RAB release is the **gap structure** across these,
not any single system's score.

## 6. Honesty clauses (frozen with the spec)

1. No LLM judge anywhere in scoring.
2. RF consumes the exported log ONLY (no live-state access).
3. RAB operationalises Art. 10/12/19 concepts; it does not certify
   compliance, and the spec says so wherever scores are published.
4. Scores published only with re-verification artifacts (§4).
5. The benchmark author's system scoring well is expected and is not
   the headline (§5).
6. Spec changes never retro-apply: results carry their spec version.

## 7. Work plan position

```
R1.0 prior-art + anchors  ✅ (2026-06-10)
R1.1 THIS SPEC (frozen)
R1.2 scenario-S1 fixture  → eval/rab/scenarios/s1_lifecycle_small.json
R1.3 driver + scorer      → eval/rab/{driver,scorer}.py + tests
R1.4 pre-registered measurement: JAMES + Baseline-0 (+1)
R1.5 release (spec+scenario+scorer+scores, Zenodo DOI)
R1.6 replication invites (separate collab scope)
```
