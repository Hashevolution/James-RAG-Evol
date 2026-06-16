---
license: cc-by-4.0
language:
  - en
pretty_name: "RAB — Replayable-Audit Benchmark for RAG / agent systems"
size_categories:
  - n<1K
task_categories:
  - question-answering
  - other
tags:
  - rag
  - audit
  - provenance
  - traceability
  - eu-ai-act
  - benchmark
  - replayable-audit
  - agent-evaluation
configs:
  - config_name: S1
    description: "lifecycle-small — 40 deterministic ops, K=10 checkpoints"
  - config_name: S2
    description: "lifecycle-large — 400 deterministic ops, K=40 checkpoints"
---

# RAB — Replayable-Audit Benchmark (SPEC v0.1.1, FROZEN)

> **A deterministic, LLM-judge-free benchmark for the *auditability* of
> RAG / agent systems** — not their answer quality. RAB asks a different
> question from accuracy benchmarks: *given only the system's exported
> audit log, can you tell what it did, replay its state at any past
> moment, and trace every cited answer back to where the content
> entered?*

RAB operationalises the record-keeping / traceability / provenance
concepts of **Regulation (EU) 2024/1689 (EU AI Act) Articles 10, 12,
and 19** (record-keeping obligations in force **2026-08-02**) into three
runnable, reproducible metrics.

> ⚠️ **RAB does NOT certify regulatory compliance.** It operationalises
> Art. 10/12/19 *concepts* into measurable proxies. A good RAB score is
> evidence of auditability, not a legal compliance attestation. This
> clause is frozen with the spec (§6).

---

## What this dataset contains

This dataset is the **published scenario fixtures** of RAB — the
deterministic driver programs a benchmark run executes against a system
under test (SUT). It does **not** contain any model weights or system
logs; logs are produced *by* the SUT at run time and scored against
these fixtures.

| Config | Name | Ops | Composition | Checkpoints |
|---|---|---|---|---|
| `S1` | lifecycle-small | 40 | 11 INGEST / 4 UPDATE / 3 SUPERSEDE / 2 DELETE / 20 QUERY | 10 |
| `S2` | lifecycle-large | 400 | 110 INGEST / 40 UPDATE / 30 SUPERSEDE / 20 DELETE / 200 QUERY | 40 |

Both scenarios are **synthetic, public-domain English prose** about a
fictional research lab (*Northbridge Labs*) — no real entities, no
licensing friction. Content is fully deterministic: no randomness, no
time-dependent inputs. S2 additionally guarantees supersede-chain depth
(avg ≥ 3, longest ≥ 5) and cross-reference density (≥ 2.5) so that
replay and provenance are stressed at scale.

### Row schema

Each row is one driver op:

| field | type | notes |
|---|---|---|
| `scenario` | string | `"S1"` / `"S2"` |
| `spec` | string | spec version the fixture targets (`"v0.1"` / `"v0.1.1"`) |
| `op_id` | string | unique, ordered within the scenario (e.g. `s1-019`) |
| `op` | string | `INGEST` / `UPDATE` / `SUPERSEDE` / `DELETE` / `QUERY` |
| `checkpoint` | bool | if true, the driver snapshots ground-truth state here (RF) |
| `doc_id` | string | content id for mutating ops (`""` for QUERY) |
| `old_doc_id` | string | superseded id for `SUPERSEDE` (`""` otherwise) |
| `title` | string | document title for mutating ops (`""` otherwise) |
| `text` | string | document body for mutating ops (`""` otherwise) |
| `query` | string | the question for `QUERY` ops (`""` otherwise) |
| `args_json` | string | the original `args` object, verbatim, as a JSON string (lossless) |

`args_json` is the canonical source; the broken-out columns are a
convenience view. Op order is the file order — **do not shuffle**, the
benchmark semantics depend on it.

## Usage

```python
from datasets import load_dataset

# one config at a time (the op order is the program — keep streaming=False)
s1 = load_dataset("JamesLabs/rab-replayable-audit-benchmark", "S1",
                  split="test", trust_remote_code=True)

for op in s1:
    if op["op"] == "QUERY":
        ask(op["query"])
    elif op["op"] == "SUPERSEDE":
        supersede(op["old_doc_id"], op["doc_id"], op["title"], op["text"])
    # ... INGEST / UPDATE / DELETE
    if op["checkpoint"]:
        snapshot_state()   # RF ground truth is taken here
```

> The loader needs `trust_remote_code=True` because RAB ships a small
> loading script (`rab.py`) that preserves op order and the per-op
> schema. The script only reads the bundled JSON fixtures — no network,
> no code execution beyond parsing.

To actually **score** a system you also need the driver + scorer, which
live in the source repository (`eval/rab/driver.py`, `eval/rab/scorer.py`)
— see *Running a full benchmark* below.

---

## The three metrics (all deterministic — no LLM judge anywhere)

A SUT is scoreable iff it can export its audit log as **JSONL**, one
event per line, with at least: `event_id`, `ts`, `event_type`,
`parent_id`, `inputs_hash`, `payload`. The SUT's native event types are
mapped once to RAB's canonical vocabulary (`INGEST`, `UPDATE`,
`SUPERSEDE`, `DELETE`, `RETRIEVE`, `RERANK`, `SYNTH`, `VERIFY`,
`ANSWER`, `OTHER`) via a declared **mapping table** submitted with the
log.

### AC — Audit Completeness  ·  *anchor: Art. 12(1)–(2)*
Fraction of the decision-bearing actions the driver actually requested
that show up, correctly typed, in the exported log.
`AC = |matched| / |E_exec|`, reported overall and per canonical type.
Unmapped decision-bearing events count *against* AC — executed but not
auditable in canonical terms.

### RF — Replay Fidelity  ·  *anchor: Art. 12(2)(b)*
At each checkpoint the driver snapshots true state `S_k` via the SUT's
live query interface. After the run, a **replayer** is given **only the
exported log** and must reconstruct `R_k`.
- `RF-exact = #{k : canon(R_k) == canon(S_k)} / K` (byte-identical after canonicalisation)
- `RF-graded = mean_k Jaccard(items(R_k), items(S_k))` (partial credit)
- `RF-cost` = wall-clock seconds per 1 000 log events folded during replay (a **scale axis**, reported alongside, **never blended into the score**)

### PC — Provenance Coverage  ·  *anchor: Art. 10(2)(b), W3C PROV `wasDerivedFrom`*
For every `ANSWER`, each cited source id must chain back through
`parent_id` links to an **origin-bearing** event (`INGEST` **or**
`SUPERSEDE` — both introduce content):
`ANSWER → SYNTH → RETRIEVE → INGEST|SUPERSEDE`, unbroken and acyclic.
`PC = traceable citations / total citations`. v0.1 scopes provenance to
*cited sources only*; claim-level provenance is explicitly out of scope.

> **EU AI Act mapping is a design anchor, not a compliance claim.** The
> article references explain *why* each metric exists; they do not imply
> that a high score satisfies the Regulation.

---

## Running a full benchmark (driver + scorer)

This HF dataset gives you the fixtures. The deterministic driver,
scorer, and reference/baseline adapters are in the source repo:

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
python scripts/research/rab_run.py --scenario S1 --sut <your-adapter>
# scorer is deterministic: re-running on the same artifacts reproduces
# the numbers bit-for-bit.
```

A RAB result is the tuple
`{spec, scenario, sut, sut-version, AC{overall,per-type},
RF{exact,graded,cost_s_per_1k}, PC, log_sha, mapping_table_sha,
runner_env}`, and is published **only with the re-verification
artifacts** (log file, mapping table, scenario) per SPEC §4.

### Baselines and the headline
The v0.1 release measures: **Baseline-0** (vanilla RAG quickstart,
default logging — the floor), **Baseline-1** (Baseline-0 + bolt-on
tracing mapped to the log interface), **JAMES** (audit-native
reference), and invited audit-native runtimes. **The headline of any RAB
release is the *gap structure* across these systems, not any single
system's score** — and explicitly not the benchmark author's own system
scoring well (frozen honesty clause §5).

---

## Honesty clauses (frozen with the spec)

1. No LLM judge anywhere in scoring.
2. RF consumes the exported log **only** — no live-state access during replay.
3. RAB operationalises Art. 10/12/19 concepts; it does **not** certify compliance, and says so wherever scores are published.
4. Scores are published only with re-verification artifacts.
5. The benchmark author's system scoring well is *expected* and is **not** the headline.
6. Spec changes never retro-apply: every result carries its spec version.

---

## Versioning

- **SPEC**: v0.1.1 (FROZEN 2026-06-10). Changes require a version bump + changelog; results always cite their spec version.
- Scenario files are versioned and **hash-pinned**; scores cite `(spec vX.Y, scenario sZ, scenario-sha)`.
- v0.1.1 widened PC's origin rule from "INGEST only" to "INGEST **or** SUPERSEDE" (content introduced via supersede has its origin in the log). No measurements were taken against v0.1.0.

## License

- **Scenario fixtures + this dataset card**: CC-BY-4.0 (matches the RAB
  pre-registration deposit on Zenodo). The prose is synthetic and
  public-domain in character; CC-BY-4.0 governs the curated collection.
- **Loader script (`rab.py`) and the driver/scorer in the source repo**:
  MIT (the JAMES project license).

## Citation

If you use RAB, cite the software archive and the spec version:

```bibtex
@software{rab_replayable_audit_benchmark,
  title        = {RAB — Replayable-Audit Benchmark for RAG / agent systems},
  author       = {Seo, Ji Won},
  organization = {JAMES (Hashevolution)},
  year         = {2026},
  version      = {SPEC v0.1.1},
  doi          = {10.5281/zenodo.20625533},
  url          = {https://github.com/Hashevolution/James-RAG-Evol}
}
```

- Software archive (v0.4.3): https://doi.org/10.5281/zenodo.20625533
- Pre-registration (scenario-S2 priority anchor): see `reports/zenodo/` in the source repo
- Source: https://github.com/Hashevolution/James-RAG-Evol — spec at `eval/rab/SPEC-v0.1.md`
