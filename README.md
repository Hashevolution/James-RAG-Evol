# PROJECT JAMES

> **JAMES** — a local-first, auditable knowledge reasoning platform.
> Graph-RAG retrieval, deterministic contradiction arbitration,
> append-only audit log, replayable knowledge state, and a human
> approval gate for self-evolution. Built as a general
> **mother platform** through v1.0; domain packs (legal, food,
> retail, …) branch off only after v1.0 (see
> [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md)).
>
> **One differentiator highlight**: *Replayable RAG* — the system's
> state at any past point can be reconstructed byte-identically via
> the T7 supersede chain + append-only audit log (`reconstruct_view_at`).
> Other first-class differentiators include Graph-RAG retrieval,
> Knowledge Cascade (Layer 3), Layer 4 Lifecycle (T1–T7), the Plugin
> API, and the deterministic 4-rule contradiction tree.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v0.4.4-blue.svg)](https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.4.4)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/12806/badge)](https://www.bestpractices.dev/projects/12806)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20652679.svg)](https://doi.org/10.5281/zenodo.20652679)
[![RAB SPEC](https://img.shields.io/badge/RAB%20SPEC-v0.1.1-green.svg)](eval/rab/SPEC-v0.1.md)
[![LRB Benchmark](https://img.shields.io/badge/LRB-v0.2.3-green.svg)](papers/lrb-preprint/main.pdf)

![PROJECT JAMES — 3D ontology graph visualizer](reports/promo-assets/screenshots/06-3d-graph.jpg)

[한국어 README](README.ko.md) · [🚀 처음 시작하시는 분 (10살도 따라할 수 있어요)](README.beginner.ko.md)

---

## Why JAMES? (60-second scan)

Most production RAG stacks today (LangChain, LlamaIndex, vanilla retrieval-augmented quickstarts) optimise for **answer quality on a frozen corpus**. JAMES is built for the next two axes those frameworks leave unmeasured:

| Axis | LangChain / LlamaIndex / vanilla RAG | **JAMES** |
|---|---|---|
| **Audit-native lifecycle** | `logger.info()` strings; no canonical event taxonomy; replay impossible from logs alone | Event-sourced `audit_log` schema; `reconstruct_graph_at(t)` replays system state byte-identically from log alone — measured on **RAB v0.1.1** (AC/RF/PC = 1.0 × 3 vs Baseline-0 default-logging floor = 0.275/0/0) |
| **Time-valid retrieval** | Latest version only; cannot answer *"what was this contract's clause 6 months ago?"* without an external versioned store | Per-document validity windows (T1) + supersede chain (T7); time-travel queries return the version valid at `query_time` — measured on **LRB v0.2.3** (R@1 V<N<J preserved across 4 models × 4 scales, JAMES − Naive gap > +0.10 throughout) |
| **Local-first execution** | Cloud-default (OpenAI / Anthropic API calls in every retrieval) | Runs on local Ollama (gemma4:e4b 4B → mxtral 47B); cloud is opt-in per query; data never leaves the host without explicit consent |
| **EU AI Act 2026-08 alignment** | "Compliance" is a TODO | RAB's 3 metrics map verbatim to Articles 10/12/19; the benchmark is the audit instrument the Act assumes exists |

What JAMES does **not** claim:
- **Better answer quality on closed-book QA** — verified equivalent on MuSiQue (3-SUT identical EM/F1 by construction; *§ honest negative* in [LRB preprint](papers/lrb-preprint/main.pdf) §5)
- **Novel architecture** — ActiveGraph ([arXiv:2605.21997](https://arxiv.org/abs/2605.21997)) demonstrates the same event-sourced runtime class independently; the benchmark, not the runtime, is the contribution
- **Drop-in LangChain replacement** — JAMES is a *platform* with a different operational model (audit-first); migration is an integration project, not a one-line `pip install`

If your use case is *audit / lifecycle / time-travel / on-prem* — JAMES is built for it, measured for it, and citeable for it. If your use case is *fastest possible answer on a fixed corpus* — use LangChain.

> **Looking for MRR / NDCG / RAGAS / hallucination-rate coverage?** See [`docs/evaluation/v0.5-evaluation-coverage-mapping.md`](docs/evaluation/v0.5-evaluation-coverage-mapping.md) — a full mapping of standard RAG / IR metrics to what JAMES measures (and what it deliberately doesn't), including code paths and procurement-ready answers.

---

## 🔬 What does Graph-RAG contribute?

A single 4-cell ablation on the `multihop_rag` fixture (N=100, n=3 paired, M_M = gemma4:e4b 4B, git_sha `b686f35`):

| Cell | path_coverage | graded_answer | abstention_f1 | token_cost | latency |
|---|---|---|---|---|---|
| C_minus (no RAG) | 0.000 | 0.213 | 0.356 | 675 | 9.8s |
| C_rag-basic (+ vector) | 0.000 | 0.260 | 0.306 | 783 | 12.5s |
| **C_rag-graph (+ graph)** | **0.4056** | 0.203 | 0.400 | 1675 | 32.4s |
| C_rag-ontology (+ typed filter) | 0.4056 | 0.230 | 0.4286 | 1695 | 32.4s |

**Graph-RAG contribution** (C_rag-basic → C_rag-graph):
- **path_coverage +0.41** (load-bearing win, noise band 0.02) — vector-only retrieval recovers 0% of gold supporting-doc paths on multi-hop queries; graph traversal recovers ~40%.
- abstention_f1 +0.094 (graph evidence improves "when to say I don't know" calibration).
- graded_answer −0.057 (honest loss — graph evidence adds noise to short-answer queries; typed-filter recovers +0.027).
- **2.1× token cost, 2.6× latency** (the path-coverage win is not free).

**Cross-time reproducibility**: the α-6 cycle (2026-06-01, n=1) measured path_coverage 0.408; this Step 1 rerun (2026-06-13, n=3 median) confirms 0.4056. **Stable across 12 days of oracle revisions.**

Full table + LRB V<N<J architecture ablation + RAB AC/RF/PC audit ablation + honest negatives (closed-book QA, cycle γ deep-multi-hop floor, cost trade-offs) all in [`docs/evaluation/v0.5-graph-rag-contribution.md`](docs/evaluation/v0.5-graph-rag-contribution.md).

---

## 📑 Papers & Reproducibility

Two benchmarks released as a sibling pair, both pre-registered before measurement, both deterministic-scorer-only, both committed in this repository.

### RAB v0.1.1 — Replayable-Audit Benchmark
[📄 PDF (10 pages)](papers/rab-preprint/main.pdf) · [📋 SPEC](eval/rab/SPEC-v0.1.md) · [🧪 Reproduce](#reproduce-in-60-seconds)

> *RAB scores the exported audit-log artifact (Audit Completeness / Replay Fidelity / Provenance Coverage) of any RAG or agent system that can dump an append-only log. Three metrics map verbatim to EU AI Act Articles 10, 12, 19. Headline: 4-SUT gap structure (Reference / JAMES audit-native / OpenTelemetry-GenAI bolt-on / vanilla default-logging) — not JAMES's score.*

### LRB v0.2.3 — Lifecycle Retrieval Benchmark
[📄 PDF (11 pages)](papers/lrb-preprint/main.pdf) · [🧪 Reproduce](#reproduce-in-60-seconds)

> *LRB scores temporal validity (`query_time`, `valid_time`) retrieval quality across three deterministic scenarios (S1 quarterly, S2 yearly-with-time-travel, S3 publication-scale 1000 docs). Three SUTs (Vanilla append-only / Naive-supersede / JAMES validity-window) compared on 7 deterministic axes + 3 exploratory top-1 axes. Headline: V < N < J on R@1 preserved across **4 model families × 4 scale points** (12.5× scale span) with JAMES − Naive gap > +0.10 throughout.*

### Citation (BibTeX)

<details>
<summary>Click to expand</summary>

```bibtex
@misc{seo2026jamesv044,
  author    = {Seo, Jiwon},
  title     = {{PROJECT JAMES} v0.4.4 (LRB v0.2.3 S3 publication-scale + cycle $\gamma$ 4-bench infrastructure closure)},
  year      = {2026},
  month     = {6},
  doi       = {10.5281/zenodo.20652679},
  url       = {https://doi.org/10.5281/zenodo.20652679},
  version   = {v0.4.4},
  publisher = {Zenodo},
  note      = {Source: https://github.com/Hashevolution/James-RAG-Evol}
}

@misc{seo2026rab,
  author        = {Seo, Jiwon},
  title         = {{RAB}: A Replayable-Audit Benchmark for {RAG} and Agent Systems Operationalising {EU AI Act} Articles 10, 12, 19},
  year          = {2026},
  howpublished  = {Preprint v0.1.1},
  url           = {papers/rab-preprint/main.pdf},
  note          = {Data: \href{https://doi.org/10.5281/zenodo.20652679}{10.5281/zenodo.20652679}}
}

@misc{seo2026lrb,
  author        = {Seo, Jiwon},
  title         = {{LRB}: A Lifecycle Retrieval Benchmark for Temporal {RAG}},
  year          = {2026},
  howpublished  = {Preprint v0.2.5},
  url           = {papers/lrb-preprint/main.pdf},
  note          = {Data: \href{https://doi.org/10.5281/zenodo.20652679}{10.5281/zenodo.20652679}}
}
```

</details>

### Reproduce in 60 seconds

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol.git
cd James-RAG-Evol
python -m pip install -r requirements.txt

# RAB scenario-S1 (deterministic; no LLM call; ~5 seconds)
python scripts/research/rab_run.py --sut reference     # AC/RF/PC = 1.000/1.000/1.000
python scripts/research/rab_run.py --sut baseline0     # AC/RF/PC = 0.275/0.000/0.000
python scripts/research/rab_run.py --sut james         # AC/RF/PC = 1.000/1.000/1.000

# LRB Phase B (S2 time-travel) token-mode (deterministic; no LLM; ~30 seconds)
PYTHONPATH=. python scripts/research/lrb_run_phase_b.py --scenarios S1,S2

# LRB S3 publication-scale (1000 docs / 5.6k events / 1000 queries; ~3 minutes)
python scripts/research/build_lrb_scenario_s3.py --scale publication
python scripts/research/lrb_run_s3.py --scale publication
```

Every `result.json` + `bench.jsonl` artifact in `reports/external/lrb/` and `reports/rab/` is SHA-pinned against the scenario fixture; **byte-identical re-runs are the verification protocol**.

---

## Architecture (one-page Mermaid view)

```mermaid
flowchart TB
    classDef user fill:#fde7e7,stroke:#c33,color:#000
    classDef sec fill:#fff7d6,stroke:#b8860b,color:#000
    classDef pipe fill:#e0f2fe,stroke:#0369a1,color:#000
    classDef life fill:#dcfce7,stroke:#15803d,color:#000
    classDef store fill:#f3e8ff,stroke:#7e22ce,color:#000
    classDef bench fill:#ffedd5,stroke:#c2410c,color:#000

    USER[/"User query<br/>(REST / CLI / UI)"/]:::user

    SEC["3-Stage Security<br/>RBAC + ABAC + Instruction Isolation<br/>(core/security/)"]:::sec

    subgraph RETRIEVAL["Retrieval pipeline (core/)"]
      direction TB
      RETR["Hybrid Retrieval<br/>BM25 + dense embed (BAAI/bge-m3)<br/>core/retrieval/"]:::pipe
      GRAPH["Graph-RAG ontology walk<br/>12 typed relations<br/>core/graph_engine.py"]:::pipe
      REASON["Reasoning loop<br/>plan → retrieve → reflect → verify → synth<br/>core/reasoning/engine.py"]:::pipe
    end

    subgraph LIFECYCLE["Layer 4 Lifecycle (T1-T7)"]
      direction TB
      T1["T1 Temporal validity<br/>(valid_from, valid_to)"]:::life
      T2["T2 Contradiction arbitration<br/>4-rule deterministic tree<br/>core/lifecycle/contradiction_arbiter.py"]:::life
      T5["T5 Replayable Audit Graph<br/>reconstruct_graph_at(t)<br/>core/lifecycle/replay_graph.py"]:::life
      T6["T6 Causality cascade<br/>invalidate_derived_facts"]:::life
      T7["T7 Supersede chain<br/>supersede_by + supersede_at"]:::life
    end

    subgraph STORE["Storage (default local)"]
      direction TB
      CHROMA[("ChromaDB<br/>vector store")]:::store
      WIKI[("wiki/<br/>doc + metadata")]:::store
      AUDIT[("audit.db<br/>append-only audit log")]:::store
      MEM[("memory/<br/>session state")]:::store
    end

    subgraph LLM["LLM backends (default local)"]
      direction LR
      OLLAMA["Ollama<br/>gemma4:e4b default"]
      CLOUD["Cloud (opt-in)<br/>claude / openai / gemini"]
    end

    subgraph BENCHES["Pre-registered deterministic benchmarks (v0.4.3 / v0.4.4)"]
      direction LR
      RAB["RAB v0.1.1<br/>Audit Completeness / Replay Fidelity / Provenance Coverage<br/>EU AI Act Art. 10/12/19 anchor<br/>papers/rab-preprint/"]:::bench
      LRB["LRB v0.2.3<br/>Temporal validity (query_time, valid_time)<br/>R@1 V&lt;N&lt;J × 4 model × 4 scale<br/>papers/lrb-preprint/"]:::bench
    end

    USER --> SEC
    SEC --> RETR
    RETR --> GRAPH
    GRAPH --> REASON
    REASON --> CHROMA
    REASON --> WIKI
    REASON --> AUDIT

    REASON <--> LIFECYCLE
    AUDIT --> T5
    T1 --> T7
    T2 --> T6
    T7 --> T6

    REASON --> OLLAMA
    REASON -.opt-in.-> CLOUD

    AUDIT -."scored by".-> RAB
    GRAPH -."scored by".-> RAB
    RETR -."scored by".-> LRB
    LIFECYCLE -."scored by".-> LRB
```

**The flow in one sentence**: a user query passes through 3-stage security (RBAC + ABAC + instruction isolation), enters the retrieval pipeline (hybrid BM25 + dense embed → Graph-RAG ontology walk → reasoning loop), reads + writes the Layer 4 lifecycle store (T1-T7), and is replayable from the audit log via `reconstruct_graph_at(t)`. RAB scores the audit log; LRB scores the retrieval quality on time-travel queries. Both benchmarks are external deterministic instruments — JAMES does not score itself.

---

## What's Verified (one-screen summary)

The numbers below come from the current `main` branch — not aspirational, not from an older release. Every value is reproducible by cloning + running the listed command.

| Surface | Verified | Where to check |
|---|---|---|
| **Test suite** | **3290 tests** collected across `tests/` (224 test files), all green on PR CI | `python -m pytest tests/ --collect-only -q` |
| **CASCADE / EVENT separation** | Provable end-to-end via 5 release-gating invariants run against a real wiki fixture (not mocks) | `tests/test_t7_release_gating_invariants.py` |
| **T6 causality cascade** | 4 additional release-gating invariants pin foundational vs corroborative semantics | `tests/test_t6_release_gating_invariants.py` |
| **QVT 3-axis quality baseline** | path_recall **1.00** / graded_answer **0.58** / abstention_f1 **0.67** (median, post-calibration, N=3 paired reruns) | `eval/qvt/baseline_2a31b20.json` |
| **STEP 7 regression** | 17-query suite with `gold_signals` + `abstention_truth` + `expected_path.nodes` ground truth on 5 queries | `eval/regression/step7_queries.json` v6 |
| **F9 entity-anchor q15 fix** | q15 ("David Soria Parra가 누구야?") path_recall **0.00 → 1.00** after `JAMES_ENABLE_ENTITY_ANCHOR=1` + `JAMES_EMBEDDING_MODEL=BAAI/bge-m3` + `JAMES_ENABLE_QUERY_REWRITE=1` | `reports/research-runs/step7-bench-baseline-run*.json` |
| **Module size discipline** | 20 KB cap enforced on every `core/` file. Largest current: `core/lifecycle/schema.py` at 18.9 KB | CLAUDE.md rule 5 + module-size CI gate |
| **Default-off invariant** | Every routing layer added since v0.3 (D5 / LEO / D1 / T2.D / T6 LLM) defaults OFF — production fleets pulling v0.4.1 see byte-identical retrieval to v0.3.3 unless they opt in | `JAMES_*` env audit (CHANGELOG `[0.4.x]` table) |
| **Deterministic contradiction arbitration** | `classify_contradiction` is an LLM-free 4-rule decision tree (~10.2 KB pure function). Audit-replay-safe by construction. | `core/lifecycle/contradiction_arbiter.py` |
| **RAB v0.1.1 — Replayable-Audit Benchmark** | **JAMES AC/RF/PC = 1.000 / 1.000 / 1.000 vs Baseline-0 (vanilla quickstart + default logging) = 0.275 / 0.000 / 0.000** on scenario-S1. Deterministic scorer (no LLM judge); 3 metrics map to EU AI Act Art. 10/12/19 (applies from 2026-08-02 per Art. 113). | `eval/rab/SPEC-v0.1.md` + `python scripts/research/rab_run.py --sut {reference,baseline0,james}` |
| **LRB v0.2.3 — Lifecycle Retrieval Benchmark** | **R@1 V<N<J preserved across a 4-point scale ladder** (S2 N=80 → S3 publication N=1000, **12.5× scale**) and **across 4 model families** (gemma4:e4b / gemma3:12b / mixtral / claude). S3 publication R@1: V/N/J = 0.502 / 0.721 / **0.845**. JAMES − Naive gap > +0.10 at every scale point. Pattern + gap scale-robust ⭐⭐⭐; absolute magnitude scenario-sensitive ⭐⭐. | `papers/lrb-preprint/main.pdf` + `python scripts/research/lrb_run_s3.py --scale publication` |

**What is NOT yet headline-verified**: a single-page ablation card showing **Graph-RAG vs flat RAG** on the same fixture. The infrastructure to produce it (`scripts/qvt_capture_baseline.py` + the 18-cell ablation matrix design from QVT memo §5) is wired; the operator-run capture is the late-June deliverable. Until then, the graph contribution is measurable via `graph_paths_count` per query in any STEP 7 bench output, but not summarized in one table.

---

## Project Status: v0.4.4 — LRB v0.2.3 S3 publication-scale + cycle γ 4-bench infrastructure closure

Released **2026-06-12**. v0.4.4 extends v0.4.3 with **LRB v0.2.3** — the *Lifecycle Retrieval Benchmark*'s cross-scale reproducibility extension and a sibling axis to RAB v0.1.1. v0.2.1 cross-model (gemma4:e4b 4B / gemma3:12b 12B / mixtral:8x7b 47B / claude-haiku-4-5) established that **R@1 V<N<J on Phase B (S2 time-travel)** is not a single-model artefact; **v0.2.3 adds the scale axis**: a 4-point ladder spanning a **12.5× scale jump** (S2 N=80 → S3 publication N=1000) preserves the V<N<J inequality at every cell with the JAMES − Naive gap above +0.10 throughout. **Pattern + gap are scale-robust ⭐⭐⭐; absolute magnitudes are scenario-sensitive ⭐⭐** (honest framing locked in preprint §5; the S3.1 contract-vocabulary fix retracted a pre-S3.1 over-tight verdict — first **self-catch** in the JAMES cycle history's 12 wrong-fix-averted instances).

Same cycle ships the **cycle γ 4-bench measurement infrastructure closure**: D-alce research-tier NLI adapter (RoBERTa-MNLI + DeBERTa-v3-ANLI) and D-2wiki supporting-fact-aware producer promote ALCE and 2Wiki cells from ⭐ infra-only (v0.4.3) to research-tier-ready infrastructure for 4-of-4 cycle γ benches.

**Papers ready for submission** (pre-flight complete, arXiv endorsement pending):
- **RAB preprint** (10 pages): [papers/rab-preprint/main.pdf](papers/rab-preprint/main.pdf) — *Operationalising EU AI Act Articles 10/12/19 into a measurable audit-quality benchmark.*
- **LRB preprint** (11 pages): [papers/lrb-preprint/main.pdf](papers/lrb-preprint/main.pdf) — *Temporal validity axis for RAG; V<N<J across 4 model families × 4 scale points.*

No JAMES production runtime change — v0.4.4 ships generators, scorers, runners, NLI adapters, and 8 pre-registration LOCK documents. The arXiv preprints cite Zenodo DOI [10.5281/zenodo.20652679](https://doi.org/10.5281/zenodo.20652679) for data availability.

---

## Project Status: v0.4.3 — RAB v0.1.1 (Replayable-Audit Benchmark) + Cycle γ multi-hop arc closure

Released **2026-06-10**. v0.4.3 ships **RAB v0.1.1** — the first replayable-audit benchmark for RAG / agent systems whose 3 deterministic metrics (AC / RF / PC) are operationalisations of EU AI Act Articles 10, 12, 19 (in force 2026-08-02). The full SPEC, scenario fixture, scorer, reference / JAMES / Baseline-0 adapters, and 9 measurement artifacts (reports/rab/) are committed. Headline = the **gap structure** across SUTs (JAMES audit-native = 1.000 / 1.000 / 1.000 vs Baseline-0 default-logging floor = 0.275 / 0.000 / 0.000 on scenario-S1), not JAMES's score — SPEC §6.5 explicitly disclaims JAMES-wins framing. Honest framing: **the benchmark is the contribution, not the architecture** — ActiveGraph (arXiv 2605.21997) is independent co-invention of the audit-native runtime; the unfilled gap was the measurement, not the system.

Companion track in the same cycle closes the **Cycle γ multi-hop arc** (PRs #752 → #757) with 6 honest nulls: multi-hop improvement reframed out of the JAMES roadmap; the **graph build O(N²)** secondary finding lifted into RAB as the RF-cost axis.

No JAMES production runtime change — RAB measures the existing audit / lifecycle / graph paths via a workspace-scoped adapter; production `audit.db` is untouched. Default-off invariant preserved.

Pre-v0.4.3: **v0.4.2** (2026-06-06) shipped T5 Replayable Audit Graph — full event-sourced graph-wide reconstruction (`reconstruct_graph_at(t)` audit-only primitive, the building block RAB measures the quality of).

Pre-v0.4.2: **v0.4.1** (2026-05-28) closed the CASCADE pillar that v0.4.0 only half-finished: when a base fact's sources are fully removed, edges whose `derived_from` references that base now auto-invalidate via `invalidate_derived_facts` — the derivation chain stays internally consistent without manual operator intervention. Per-derivation-type semantics (T6.C.b refinement): `transitive` / `inferred` are structural chain links (any base empty → invalidate); `operator` is corroborative (only invalidates when no hard deps AND all operator bases empty).

Pre-v0.4.1: **v0.4.0** (2026-05-27) shipped the Layer 4 first
bundle — **T1 Temporal Validity + T7 Supersede Chain + T2
Contradiction Arbitration** — across an 8-PR Sprint 5 sequence.
The CASCADE vs EVENT separation invariant is **provable end-to-end**
via `tests/test_t7_release_gating_invariants.py`, run against the
actual wiki fixture (not mocks). The supersede chain primitive
(`reconstruct_view_at`) lets the system answer "what was true at
time T?" deterministically, even after destructive CASCADE
operations on unrelated facts.

Pre-v0.4: v0.3.0 (2026-05-17) closed Foundation Hardening — all
six axes (architecture / eval / observability / security /
controlled evolution / real-data validation) green; second-user
validation closed 2026-05-13.

- **NOT production-ready** — operational maturity (HTTPS / SSO /
  multi-tenancy / backup CLI) is a v1.0 deliverable; see
  [SECURITY.md](SECURITY.md)
- Designed with security-first principles end to end
- Open to collaboration — external contributors sign a one-click CLA
  on their first PR (see [License](#license))

---

## Strategic frame: Mother Platform, not a single product

JAMES is **not building one vertical**. It is being hardened as a
"mother platform" from which domain packs (legal, food, retail,
travel, etc.) can branch off **only at v1.0**. Until then:

- No domain-specific features land in `core/`
- Every change is graded against the same six-dimension readiness
  framework (architecture / extension API / eval contract /
  operational maturity / security boundary / production proof)
- The plugin contract that future packs will be built against is
  being designed and stress-tested

See [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md) for
the 6 dimensions, 4 gates (v0.2 / v0.3 / v0.4 / v1.0), and 3
branching forms (Domain Pack / Distribution / Vertical Product).

---

## RAB — Replayable-Audit Benchmark (new in v0.4.3)

**RAB v0.1.1** is a frozen benchmark spec + scenario fixture +
deterministic scorer + adapter contract for systems that claim
audit-replayable RAG / agent state. Three metrics, all deterministic
(no LLM judge anywhere):

* **AC — Audit Completeness** (EU AI Act Art. 12(1)/(2))
* **RF — Replay Fidelity** (Art. 12(2)(b) post-market reconstruction)
* **PC — Provenance Coverage** (Art. 10(2)(b) + W3C PROV)

**Why a new benchmark**: the Mathkar et al. 2026 agent-trace survey
(arXiv 2606.04990) names "realistic execution-trace benchmarks" as
an open challenge; RAB responds to that gap. The benchmark — not the
audit-native runtime — is the contribution: ActiveGraph (arXiv
2605.21997) independently published the event-sourced log + replay
architecture; **RAB is what was missing**.

**Headline = gap structure**, not JAMES's score. Scenario-S1 v0.4.3
result:

| SUT | AC | RF-exact | RF-graded | PC |
|---|---|---|---|---|
| reference (self-verify gate) | 1.000 | 1.000 | 1.000 | 1.000 |
| **JAMES** (audit-native) | **1.000** | **1.000** | 1.000 | **1.000** |
| **Baseline-0** (vanilla quickstart + default logging) | **0.275** | **0.000** | 0.000 | **0.000** |

JAMES = reference on S1 is **expected** (SPEC §6.5). The audit-native
vs default-logging delta is the finding. Honest tier: ⭐⭐
scenario-S1 confirmed. Re-verification triple committed to
`reports/rab/` (SPEC §4 bit-for-bit determinism).

**Not a regulatory certification.** RAB operationalises the AI Act's
*concepts* into measurable form; SPEC §6.3 says so wherever scores
are published.

Reproduce:

```bash
python scripts/research/rab_run.py --sut reference  # 1.000 / 1.000 / 1.000 (gate)
python scripts/research/rab_run.py --sut james      # 1.000 / 1.000 / 1.000
python scripts/research/rab_run.py --sut baseline0  # 0.275 / 0.000 / 0.000
```

See [`eval/rab/SPEC-v0.1.md`](eval/rab/SPEC-v0.1.md),
[`docs/handovers/v0.4-r1-4-gap-table-2026-06-10.md`](docs/handovers/v0.4-r1-4-gap-table-2026-06-10.md),
[`docs/research/r1-4-preregistration-2026-06-10.md`](docs/research/r1-4-preregistration-2026-06-10.md).

---

## What's Different — Replayable RAG

Most RAG systems answer one question: *"what's the answer?"*
JAMES answers two extra:

- **What did the system know at time T?** — T7 supersede chains
  preserve historical fact states; `reconstruct_view_at(t)` returns
  the edge that was active at any past timestamp, even after
  unrelated CASCADE delete events.
- **Why did the system say that?** — every reasoning step (query
  rewrite, retrieval, rerank, planner, reflect, verify, synth)
  writes an append-only audit row. `scripts/replay_trace.py
  <trace_id>` reconstructs the full sequence byte-identically.

The two combined make JAMES a **Replayable RAG** system — a
category distinct from Agentic RAG (which optimises for *what an
AI can do*) and from Mem0-style memory layers (which use an LLM
judge to update beliefs). JAMES updates beliefs via a
deterministic 4-rule decision tree (`core/lifecycle/
contradiction_arbiter.py:classify_contradiction`) that is
LLM-free by design, and preserves both the old and the new fact
for replay rather than overwriting.

### How that's built

1. **Deterministic memory lifecycle** (v0.4.0) — T1 Temporal
   Validity + T7 Supersede Chain + T2 Contradiction Arbitration.
   CASCADE (destructive, Layer 3) and EVENT (history-preserving,
   Layer 4) are guaranteed-separate paths — release-gated by
   `tests/test_t7_release_gating_invariants.py` against the real
   wiki fixture.
2. **Sources-aware Graph-RAG** — 12 typed relations carry semantic
   meaning beyond embeddings, and every relation carries
   `sources: [{doc_id, weight, role, ts}]` so deleting or modifying
   a document surgically updates only the affected derived knowledge
   (Knowledge Cascade A→E, v0.3.0).
3. **Cognitive Layer** — cross-encoder reranker (default ON), LLM
   query rewriter, reflection loop (draft → critique → revise),
   verification engine (security + fact check), and tool router.
   One `trace_id` reconstructs the full 8-stage reasoning sequence
   via `scripts/replay_trace.py`.
4. **PolicyEngine as a layer, not a sprinkle** — single point of
   role / sensitivity decisions wired into retrieval, graph, output,
   and tools; removing it breaks 6+ modules (v0.2 Axis 4).
5. **Change Request primitive** — every write (wiki edits, workspace
   jobs, self-evolution patches) routes through propose → review →
   admin approval → atomic apply → audit row. No silent writes.
6. **Self-evolution behind a human gate** — feedback → candidate →
   bench eval → human approval → deploy → auto-rollback on
   regression. Every deployed patch has an `approver_username`
   audit row (v0.2 Axis 5).
7. **100% local** — runs on a laptop with Ollama; no cloud LLM
   dependency by default.

> Each feature is regression-tested against the STEP 7 13-query
> baseline + RAGAS metrics. PRs touching `core/{retrieval,graph,reasoning}`
> cannot land without bench numbers.

---

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed and running
- Min 16GB RAM (32GB+ recommended)
- (Optional) NVIDIA GPU for faster inference
- (Optional) Tavily API key for web search ([free 1k/month](https://tavily.com))

### Installation

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol

# Configure environment
cp .env.example .env
# Edit .env — set JAMES_API_KEY, JAMES_JWT_SECRET

# Install dependencies
pip install -r requirements.txt

# Start the server (admin wizard auto-recommends a model on first login)
python server_llmwiki.py
```

Open `http://localhost:8000/admin` — the admin wizard measures your
hardware and offers a one-click install of an appropriate Ollama
model. Then open `http://localhost:8000` for the chat UI.

---

## Architecture

```
[User Query]
     ↓
[Security Filter]      ← injection patterns + PolicyEngine pre-check
     ↓
[Query Router]         ← chat / coding / retrieval / web_search
     ↓
[Query Rewriter]       ← LLM rewrite (opt-in, JAMES_ENABLE_QUERY_REWRITE)
     ↓
[Hybrid Search]        ← Vector(60%) + BM25(20%) + keyword(10%) + name(10%)
     ↓
[Cross-Encoder Rerank] ← MiniLM-L-6-v2 (default ON; JAMES_DISABLE_RERANK=1 to disable)
     ↓
[Graph Engine]         ← DFS + sources-aware + sensitivity gating
     ↓
[Reasoning Loop]       ← retrieve → expand → reflect (opt-in) → verify (opt-in)
     ↓
[Tool Router]          ← read tools direct; write tools → Change Request
     ↓
[Output Filter]        ← PII masking + role-based filter
     ↓
[Answer + Reasoning Path + trace_id]
```

Every stage emits a row tied to one `trace_id`.
`scripts/replay_trace.py <trace_id>` reconstructs the full sequence
from `audit_log`. See [`docs/ARCHITECTURE.md §5.7`](docs/ARCHITECTURE.md)
for the Cognitive Layer design.

---

## Folder Structure

```
James-RAG-Evol/
├── core/
│   ├── reasoning/        retrieval/reflection/verification/tool router
│   ├── retrieval/        hybrid search + cross-encoder reranker + query rewriter
│   ├── memory/           long-term memory (db / conversation / summaries)
│   ├── plugins/          plugin contract surface (Provider Protocol)
│   ├── policy_engine.py  single point of role/sensitivity decisions
│   ├── change_request.py propose/review/approve write primitive
│   ├── cascade.py        file delete/modify → graph surgical update
│   ├── graph_editor.py   edge edit (replace/append/delete) + bidirectional sync
│   └── ...
├── eval/                 STEP 7 regression baseline + RAGAS suite
├── llm/                  LLM provider abstraction
├── tools/                Capability-token gated tool modules
├── frontend/             Web UI (HTML + JS)
├── processors/           File preprocessing
├── wiki/                 Knowledge graph (markdown + sources)
├── memory/               Long-term memory DB
├── workspace/            Change requests, patches, proposals
├── scripts/              bench.py / replay_trace.py / ops scripts
├── reports/              Eval results + promo assets
├── docs/                 ARCHITECTURE / PLATFORM_READINESS / ROADMAP / handovers
└── server_llmwiki.py     Main server entry point
```

---

## Security Approach

JAMES treats security as a **design principle, not a feature**:

- **3-stage access control**: Vector → Graph → Output
- **RBAC** (4 roles) + **ABAC** (4 sensitivity levels)
- **Instruction isolation**: separates commands from data
- **JWT auth** + rate limiting + full audit log
- **Sandboxed execution** (for tool calls)

> Realistic note: synthetic-data testing differs from adversarial production testing. See [SECURITY.md](SECURITY.md).

---

## Current Features

| Feature | Status |
|---------|--------|
| Hybrid Search (Vector + BM25 + keyword + name) | Working |
| Cross-encoder reranker (MiniLM-L-6-v2) | Working — default ON (v0.3) |
| LLM query rewriter | Opt-in (v0.3) |
| Sources-aware Graph-RAG (Knowledge Cascade A→E) | Working (v0.3) |
| PolicyEngine (RBAC + ABAC + capability tokens) | Working (v0.2 Axis 4) |
| Reflection loop (draft → critique → revise) | Opt-in (v0.3) |
| Verification engine (security + fact check) | Opt-in (v0.3) |
| Tool router (read direct, write → Change Request) | Working (v0.3) |
| Change Request primitive (wiki + jobs + patches) | Working (v0.2.x + v0.3) |
| Self-evolution (human approval + auto-rollback) | Working (v0.2 Axis 5) |
| Trace replay (one `trace_id` → full reasoning seq) | Working (v0.3) |
| Multimodal (image/video/audio + OCR-poison quarantine) | Working (v0.2 Axis 4) |
| Web search (Tavily / DuckDuckGo fallback) | Working |
| Multi-LLM routing (Ollama + Claude CLI backends) | Working |
| STEP 7 regression baseline + RAGAS | Working (v0.2 Axis 2) |
| Real-data validation (second-user gate) | Passed 2026-05-13 |

---

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **LLM**: Ollama (Gemma, DeepSeek-Coder, LLaVA)
- **Vector DB**: ChromaDB
- **Embedding**: Sentence-Transformers (MiniLM)
- **Search**: BM25 + Vector hybrid
- **Web search**: Tavily (primary) + DuckDuckGo (fallback)
- **Auth**: JWT (python-jose)
- **Storage**: SQLite + markdown wiki

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) and [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md).
Summary:

- **v0.1**: Core engine + scaffolding (released)
- **v0.2**: Foundation Hardening — 6 axes (closed 2026-05-13)
- **v0.3**: Platform Skeleton — Cognitive Layer + Knowledge Cascade
  + Change Request primitive (current; released 2026-05-17)
- **v0.4**: First Domain Pilot — one pack + one external customer,
  6-month no-regression
- **v1.0**: Production-Grade Mother — HTTPS / SSO / multi-tenancy /
  SOC2 readiness; external developers can publish their own packs

Multi-agent specialists, optional Neo4j backend, OpenAI-compatible
API, streaming responses, and federation are speculative Beyond
v1.0 work — see [`ROADMAP.md` §Beyond v1.0](ROADMAP.md).

---

## Contributing

Welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

Priority areas:
- Documentation, examples, translations
- Bug fixes, test coverage
- New tool integrations and LLM provider support

---

## License

**Licensed under the MIT License.** Use freely. See [LICENSE](LICENSE).

External contributors sign a one-click
[Contributor License Agreement](docs/legal/CLA.md) on their first pull
request (CLA Assistant). One signature covers all future contributions
to the project. See [CONTRIBUTING.md](CONTRIBUTING.md#license--contributor-license-agreement-cla)
for the full §License & CLA section, and
[docs/legal/non-cla-contributions.md](docs/legal/non-cla-contributions.md)
for contribution paths that don't require signing.

A full inventory of third-party dependency licenses is available in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Acknowledgements

Inspired by:
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [Graphiti](https://github.com/getzep/graphiti)
- Palantir-style ontology approaches
- Architectural direction, Platform Readiness gates, and roadmap framing are discussed with LEO, continuing collaborator on this work

---

## Disclaimer

**Use at your own risk.** This is research code. No guarantees regarding sensitive-data handling or production security without further hardening.
