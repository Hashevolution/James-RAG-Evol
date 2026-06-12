# JAMES Technical Brief for v0.5 Pilot — RAB + LRB Measurement Evidence (v0.4.4 / 2026-06-12)

> Target audience: customer IT / architecture / security review team.
>
> All measurements traced to committed `result.json` + `bench.jsonl`
> artefacts in the JAMES repository
> (`https://github.com/Hashevolution/James-RAG-Evol`). Reproducible
> bit-for-bit from pre-registered scenario fixtures.
>
> **v0.4.4 update (2026-06-12)**: LRB axis extended from v0.2.1
> (cross-model V<N<J across 4 models) to **v0.2.3 cross-scale**
> (V<N<J preserved across 4-point scale ladder, 12.5× scale span,
> S2 N=80 → S3 N=1000). The cross-scale finding strengthens the
> evidence that the JAMES advantage on time-travel queries is an
> **architectural property of the validity-window mechanism**, not a
> single-model or single-corpus-size artefact. Reference: `papers/lrb-
> preprint/main.pdf` §4.6 + Zenodo DOI [`10.5281/zenodo.20652679`](https://doi.org/10.5281/zenodo.20652679).

---

## 1. JAMES architecture (one diagram)

```
┌─────────────────────────────────────────────────────────────┐
│ Customer infra (workspace-isolated single instance)          │
│                                                              │
│  Web UI ──┐                                                 │
│           ├─→ ReasoningEngine                                │
│  API   ───┘    │                                            │
│                ↓                                            │
│        ┌──────────────────────┐                             │
│        │ Retrieval pipeline    │ ← validity_at(t) filter    │
│        │  - Chroma (vectors)   │                             │
│        │  - Graph (entities)   │                             │
│        │  - Validity windows   │                             │
│        └──────────┬───────────┘                              │
│                   ↓                                          │
│        ┌──────────────────────┐                             │
│        │ LLM backend (pluggable)│                            │
│        │  - Ollama (local)     │   ← default                 │
│        │  - Claude (cloud opt-in via trust zone, abstraction)│
│        └──────────┬───────────┘                              │
│                   ↓                                          │
│        ┌──────────────────────┐                             │
│        │ Audit bridge          │ ← every event recorded     │
│        │  - audit_log (JSONL)  │                             │
│        │  - lifecycle events   │                             │
│        │  - provenance chains  │                             │
│        └──────────────────────┘                              │
└──────────────────────────────────────────────────────────────┘
```

Key points:
* **Single client instance** (no multi-tenancy at v0.5; each customer
  gets a dedicated deployment)
* **Workspace isolation** via `JAMES_WORKSPACE` env var (customer data
  + audit log scoped per workspace)
* **Local-first** (default Ollama; cloud LLM only via opt-in trust zone)
* **Audit-native** (every ingest / retrieve / synth / answer is recorded;
  log alone reconstructs full graph state)

## 2. Measurement evidence summary

Two external benchmarks measure JAMES's distinct contributions.

### 2.1 RAB (Replayable Audit Benchmark) — audit-side, publication tier

* **Spec**: `https://github.com/Hashevolution/James-RAG-Evol/blob/main/eval/rab/SPEC-v0.1.md`
* **DOI**: `10.5281/zenodo.20625533` (Zenodo software archive)
* **Scenario S2 (400 ops, 4-SUT gap structure)** results:

| SUT | AC (audit completeness) | RF (replay fidelity) | PC (provenance coverage) |
|---|---|---|---|
| **JAMES (audit-native)** | **1.000** | **1.000** | **1.000** |
| Reference (audit-perfect, self-verify) | 1.000 | 1.000 | 1.000 |
| Baseline-1 (OpenTelemetry GenAI bolt-on) | 0.500 | 0.000 | 0.000 |
| Baseline-0 (vanilla quickstart + default logging) | 0.275 | 0.000 | 0.000 |

Key finding: bolt-on tracing (OpenTelemetry GenAI) catches ANSWER events
but misses INGEST; default logging catches INGEST but misses ANSWER.
Both fail entirely at log-only state reconstruction (RF=0) and
provenance chain (PC=0). JAMES = audit-native, matches Reference.

**Anchor**: EU AI Act Art. 10 (data origin) / 12 (event logs) /
19 (≥6 month retention). Effective 2026-08-02.

### 2.2 LRB (Lifecycle Retrieval Benchmark) — retrieval-side, ⭐⭐⭐ tier

* **Spec / scenarios**:
  - `eval/external/_fixtures/lrb/scenario_S1_quarterly.json`
  - `eval/external/_fixtures/lrb/scenario_S2_yearly_timetravel.json`
* **arXiv preprint draft**: `papers/lrb-preprint/main.tex`

**Phase B (time-travel queries)** — 80 queries with explicit
`(query_time, valid_time)` pairs covering 4 types:

| SUT | R@1 token | gemma4 (4B) | gemma3:12b (12B) | mxtral (47B) | claude |
|---|---|---|---|---|---|
| Vanilla append-only RAG | 0.225 | 0.488 | 0.400 | 0.375 | 0.6125 |
| Naive supersede-aware RAG | 0.538 | 0.563 | 0.613 | 0.625 | 0.775 |
| **JAMES (validity-window)** | **0.713** | **0.725** | **0.775** | **0.838** | **0.975** |

**V < N < J** rank-order preserved in all 4 model families.
JAMES R@1 at claude = **0.9750** (≈ perfect first-result accuracy).

**Per-category breakdown** (R@10):

| Category | Vanilla | Naive | JAMES |
|---|---|---|---|
| current-director | 1.000 | 1.000 | 1.000 |
| historical-early-director | 1.000 (accident) | 0.000 (data lost) | 1.000 (by design) |
| historical-early-contract | 1.000 (accident) | 0.000 (data lost) | 1.000 (by design) |
| historical-mid-director | 1.000 | 0.600 | 1.000 |
| current-policy | 0.750 | 1.000 | 1.000 |

→ JAMES is the only SUT that **retains** prior versions AND **discriminates** by valid_time.

### 2.3 Hallucination Resistance (HR) — partial leg

NLI-based entailment check (RoBERTa-large-MNLI + DeBERTa-v3) on 10
generated answers, cross-verifier agreement:

| Cell | RoBERTa-MNLI | DeBERTa-v3 |
|---|---|---|
| Vanilla × gemma3:12b | 0.000 | 0.200 |
| Naive × gemma3:12b | 0.600 | 0.700 |
| JAMES × gemma3:12b | 0.600 | 0.700 |

Mechanism: Vanilla's append-only context surfaces both old AND new
versions; LLM picks one but NLI checks against full context → marked
neutral/contradiction. Validity-filter SUTs feed cleaner context.

⚠️ n=10 smoke; not yet publication tier. Operator action: n=100 full
sweep + TimeQA temporal-reasoning bench.

### 2.4 What is measured-equivalent (not a distinguishing advantage)

Cross-bench reproducibility check (MuSiQue multi-hop QA):

| SUT × gemma3:12b × k=20 | EM | F1 | support_recall |
|---|---|---|---|
| Vanilla | 0.200 | 0.3002 | 0.825 |
| Naive | 0.200 | 0.3002 | 0.825 |
| **JAMES** | **0.200** | 0.2863 | 0.825 |

→ **All three SUTs equivalent on closed-book multi-hop reasoning**.
JAMES is NOT a reasoning-improvement system. The validity-window
mechanism is task-orthogonal to multi-hop QA.

JAMES's distinct contribution = audit + time-validity, NOT reasoning.

## 3. Deployment topology for pilot

```
Pilot deployment options:

Option A (recommended): Customer-hosted, JAMES-managed
  - Customer infra (VPC / on-prem)
  - JAMES instance + Ollama in container
  - operator side: monthly RAB / LRB measurement only
  - data never leaves customer infra
  
Option B: JAMES-hosted dedicated
  - Cloud VPC (operator-managed)
  - Customer data uploaded via secure channel
  - Suitable for non-sensitive corpus (open law DB, etc.)
  - DPA required

Option C (future, v1.0): Multi-tenant SaaS
  - Not available at v0.5 (requires Dim D multi-tenancy gates)
```

For legal contract review domain, **Option A** is strongly recommended:
영업비밀 / 변호사-의뢰인 비밀특권 / 개인정보 보호 모두 만족.

## 4. Resource requirements (Option A)

Per pilot instance:
* **Compute**: 1 GPU (24GB VRAM for gemma3:12b) OR 1 CPU server with
  64GB RAM (gemma3:12b CPU mode, 5-10x slower but functional)
* **Storage**: 100-500 GB SSD (depending on corpus size)
* **Network**: outbound HTTPS for cloud LLM opt-in only (Claude API);
  otherwise internal-only
* **OS**: Linux (Ubuntu 22.04 / 24.04 tested), Windows Server (limited)

JAMES side:
* Operator time: ~40-60 hours / month (monthly measurement + incident
  response + onboarding support)
* No customer data on operator side

## 5. Security review checklist (for customer security team)

* [ ] Container isolation (JAMES + Ollama in dedicated network namespace)
* [ ] Audit log access controls (RBAC; only customer admins read full log)
* [ ] No outbound network by default (cloud LLM opt-in via trust zone)
* [ ] Encryption at rest (customer's choice of disk encryption)
* [ ] Encryption in transit (TLS 1.3 for all internal APIs)
* [ ] PolicyEngine boundary (every external call goes through one module)
* [ ] Abstraction trust contract (cloud egress masks entities pre-call)
* [ ] Source code audit (operator can provide repository access for
      customer security team review)

## 6. Reproducibility guarantee

Every measurement quoted in this brief is reproducible bit-for-bit
from the JAMES repository:

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol

# Reproduce RAB Phase 3 S2 4-SUT measurement
PYTHONPATH=. python scripts/research/rab_run.py

# Reproduce LRB Phase B 3-SUT measurement
PYTHONPATH=. python scripts/research/lrb_run_phase_b.py

# Reproduce LRB v0.2.1 cross-model sweep
PYTHONPATH=. python scripts/research/lrb_run_v021_cross_model.py \
  --modes token,llm-grounded \
  --models gemma4:e4b,gemma3:12b,mixtral:8x7b,claude-haiku-4-5

# Reproduce HR cross-NLI smoke
PYTHONPATH=. python scripts/research/lrb_v024_hr_smoke.py \
  --n 10 --sut all --model gemma3:12b --verifiers roberta-mnli
PYTHONPATH=. python scripts/research/lrb_v024_hr_rescore.py \
  --input "reports/external/lrb/v024-hr-smoke-*.bench.jsonl" \
  --verifier deberta-v3-anli
```

All result.json + bench.jsonl artefacts ship in the repository under
`reports/external/{lrb,musique,rab}/`.

## 7. References

* RAB SPEC: `eval/rab/SPEC-v0.1.md`
* LRB design memo: `docs/design/v0.4-lrb-lifecycle-retrieval-benchmark-design.md`
* All pre-registrations: `docs/research/lrb-*-preregistration-*.md`
* Phase A handover: `docs/handovers/v0.4-lrb-phase-a-results-2026-06-11.md`
* Phase B handover: `docs/handovers/v0.4-lrb-phase-b-cross-scenario-2026-06-11.md`
* v0.2.1 FINAL handover: `docs/handovers/v0.4-lrb-v021-cross-model-FINAL-2026-06-12.md`
* Cross-bench MuSiQue: `docs/handovers/v0.4-track-c-musique-honest-negative-2026-06-12.md`
* Improvement loop: `docs/handovers/v0.4-track-c-musique-improvement-loop-FINAL-2026-06-12.md`
* arXiv preprint draft: `papers/lrb-preprint/main.tex`

---

*Disclaimer: same as 01-exec-summary-legal-ko.md §5. Measurement
evidence reproducible; EU AI Act references descriptive only.*
