# PROJECT JAMES — Summary

A one-page, external-facing summary. The internal `CHANGELOG.md` is the per-PR audit trail (long by design, internal terminology); this doc is what an external evaluator should read first.

---

## What JAMES is

**Replayable RAG.** A local-first knowledge reasoning system where every claim is sourced, every reasoning step is audited, and the system's state at any point in time can be replayed byte-identically — even after destructive deletes propagate through the graph.

Built behind a human approval gate for self-evolution. 100% on-device by default.

---

## What you get (5 bullets)

1. **Sources-aware Graph-RAG**, not just vector RAG. Every retrieved fact carries `sources` (doc_id + weight + role), every relation walks an explicit ontology graph (`core/graph_engine.py`), and every reasoning step is logged in `audit_log` so a `trace_id` reproduces the exact decision path.
2. **Deterministic memory lifecycle.** T1 temporal validity + T7 supersede chain + T2 contradiction arbitration + T6 causality cascade — all four shipped, all LLM-free (Mem0 routes via LLM-judge; JAMES routes via a deterministic 4-rule decision tree). Source code: `core/lifecycle/{schema,supersede_chain,contradiction_arbiter,causality}.py`.
3. **`reconstruct_view_at(t)` — replayable history.** When facts are corrected, the old version isn't overwritten; it's marked `superseded_by` + `superseded_at`. Querying "what did the system know at time T?" returns the byte-identical state from that moment, even after destructive deletes (CASCADE) on unrelated facts.
4. **Self-evolution behind a human gate.** Patches the system can write to itself require an `approver_username` in the audit log before they auto-apply. The gate cannot be bypassed without a code change that itself requires review (`docs/ARCHITECTURE.md §5.5`).
5. **100% local + air-gap-ready.** Default LLM is gemma4:e4b via Ollama; default embedder is bge-m3 (multilingual); default vector store is ChromaDB on disk. No network call required for the core retrieval / reasoning loop. Optional cloud backends (Claude / Gemini / OpenAI) are flag-gated.

---

## What's measured

Direct copy of the README's "What's Verified" table (numbers from current `main`, not aspirational):

| Surface | Value |
|---|---|
| Test suite | **~3500+ tests** across 230+ files, all green on PR CI |
| **RAB v0.1.1** | **JAMES AC/RF/PC = 1.000 / 1.000 / 1.000 vs Baseline-0 = 0.275 / 0.000 / 0.000** on scenario-S1 (3 deterministic metrics; EU AI Act Art. 10/12/19 anchor) — `eval/rab/SPEC-v0.1.md` |
| **LRB v0.2.3** | **R@1 V<N<J preserved across 4 model families × 4 scale points** (12.5× scale span); S3 publication V/N/J = 0.502 / 0.721 / **0.845**; J − N gap > +0.10 throughout — [`papers/lrb-preprint/main.pdf`](papers/lrb-preprint/main.pdf) |
| Release-gating invariants | 5 (T7 separation, `tests/test_t7_release_gating_invariants.py`) + 4 (T6 causality, `tests/test_t6_release_gating_invariants.py`) |
| QVT 3-axis baseline | path_recall **1.00** / graded_answer **0.58** / abstention_f1 **0.67** (median, N=3 paired reruns) — `eval/qvt/baseline_2a31b20.json` |
| STEP 7 regression | 17-query suite (v6) with gold_signals + abstention_truth + 5 path-annotated queries |
| Module size cap | 20 KB per `core/` file (CI-enforced, CLAUDE.md rule 5) |
| Default-off invariant | Every routing layer added since v0.3 (D5 / LEO / D1 / T2.D / T6 LLM) defaults OFF — byte-identical retrieval to v0.3.3 unless flag flipped |

### Two pre-registered, deterministic benchmarks

JAMES v0.4.3 + v0.4.4 release **two sibling benchmarks**, both pre-registered before measurement, both committed in this repository:

1. **RAB v0.1.1** (Replayable-Audit Benchmark) — scores the exported audit-log artefact (AC / RF / PC) of any RAG or agent system that can dump an append-only log. Three metrics map verbatim to EU AI Act Articles 10, 12, 19 (apply from 2026-08-02 per Art. 113). 4-SUT gap table headline (Reference / JAMES audit-native / OpenTelemetry-GenAI bolt-on / vanilla default-logging). [`papers/rab-preprint/main.pdf`](papers/rab-preprint/main.pdf) (10 pages).

2. **LRB v0.2.3** (Lifecycle Retrieval Benchmark) — scores temporal-validity retrieval quality (`query_time`, `valid_time` pair) across three deterministic scenarios (S1 quarterly / S2 yearly-with-time-travel / S3 publication-scale 1000 docs). 3-SUT × 4-model × 4-scale gap structure preserved. [`papers/lrb-preprint/main.pdf`](papers/lrb-preprint/main.pdf) (11 pages).

Both papers cite **Zenodo DOI [10.5281/zenodo.20652679](https://doi.org/10.5281/zenodo.20652679)** for data availability. Headlines are gap structures, not JAMES's score — neither paper claims a novel architecture (ActiveGraph and lifecycle-aware retrieval are independent prior art).

---

## Differentiators (vs neighbouring categories)

| Category | What it provides | What JAMES adds |
|---|---|---|
| **Agentic RAG** (LangGraph / LlamaIndex agents) | iterative tool use over a query | + sourced graph + deterministic memory lifecycle + replayable history |
| **Mem0 / Letta / Cognee** (memory layers) | persistent facts across sessions | + LLM-free contradiction arbitration (deterministic 4-rule tree, audit-replay-safe) + supersede-chain replay primitive |
| **Vector-only RAG** | retrieval over embeddings | + explicit ontology graph + per-source confidence + CASCADE / EVENT lifecycle separation |
| **Self-evolution agents** (AutoGPT etc.) | autonomous code rewrite | + mandatory human approval gate (operator can't be bypassed without a separate code change) |

---

## Status + provenance

- Current release: **v0.4.4** (LRB v0.2.3 S3 publication-scale + cycle γ 4-bench infrastructure closure) — DOI [`10.5281/zenodo.20652679`](https://doi.org/10.5281/zenodo.20652679)
- **Current cycle**: **v0.5 entry** (2026-06-12) — first-domain pilot path; enterprise document ontology design LOCK ([entry handover](docs/handovers/v0.5-entry-2026-06-12.md))
- Predecessor: v0.4.3 (RAB v0.1.1 + Cycle γ multi-hop arc closure) — DOI [`10.5281/zenodo.20625533`](https://doi.org/10.5281/zenodo.20625533)
- License: MIT
- Entry: `README.md` → `docs/ARCHITECTURE.md` → `docs/PLATFORM_READINESS.md`
- Per-PR audit trail: `CHANGELOG.md` (long-form, internal terminology — start with the section header you care about and skip the rest)
- Per-release narrative: `docs/release_notes_v{0.3.0,0.3.1,0.4.0,0.4.1,0.4.2,0.4.3}.md` + `RELEASE_NOTES_v0.4.4.md`

---

## What to read next

| If you want to … | Start here |
|---|---|
| Run JAMES locally in 5 minutes | `README.beginner.ko.md` (Korean, beginner-friendly) |
| Read the architecture | `docs/ARCHITECTURE.md` |
| See the platform-readiness gate definitions | `docs/PLATFORM_READINESS.md` |
| Reproduce the RAB / LRB benchmarks | the `README.md` 'Reproduce in 60 seconds' code block (no LLM call required) |
| Cite the work academically | the `README.md` 'Papers & Reproducibility' section (BibTeX block) |
| Reproduce a verified number from "What's measured" | the right column of the table above; commands work as-typed |
| Audit a PR's quality delta | `.github/PULL_REQUEST_TEMPLATE.md` (Quality Delta Card section) |
| Audit the contradiction arbitration logic | `core/lifecycle/contradiction_arbiter.py` (~10 KB pure function, 17 contract tests) |
| Read the RAB / LRB preprints | `papers/rab-preprint/main.pdf` (10pg) + `papers/lrb-preprint/main.pdf` (11pg) |
