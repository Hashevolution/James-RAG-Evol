# JAMES — Executive Summary for Legal Domain Pilot (English, 2026-06-12)

> **JAMES = a temporally-aware, audit-traceable, local-first RAG system**.
> Tracks the exact version of regulations / contracts / decision-makers
> valid at any historical point in time, and audits every retrieval +
> answer chain. v0.5 pilot validates company-use suitability in the
> legal contract review domain through six months of evidence-gathering.

This is the English-language companion to `01-exec-summary-legal-ko.md`
(the authoritative Korean version). Intended for foreign-affiliate
stakeholders (multinational law firms, overseas branches, English-language
counsel review). When the two versions diverge in nuance, the Korean is
authoritative.

---

## 1. Why JAMES (3 measurement-evidenced points)

### ① Audit traceability — RAB benchmark publication tier ✓

**Replayable Audit Benchmark (RAB v0.1.1)** results:

| System | Audit Completeness | Replay Fidelity | Provenance Coverage |
|---|---|---|---|
| **JAMES** | **1.000** | **1.000** | **1.000** |
| Vanilla RAG | 0.275 | 0.000 | 0.000 |
| OpenTelemetry tracing | 0.500 | 0.000 | 0.000 |

→ **Every INGEST / UPDATE / SUPERSEDE / DELETE / ANSWER event** automatically
logged. Graph state fully reconstructible from log alone. Aligned with EU AI
Act (effective 2026-08-02) Articles 10 / 12 / 19.

→ DOI: `10.5281/zenodo.20625533` (publicly archived on Zenodo, externally
reproducible).

### ② Temporally-aware retrieval — LRB benchmark ⭐⭐⭐ tier ✓

**Lifecycle Retrieval Benchmark (LRB v0.2.1)** results
(4 model families × 3 SUTs × time-travel scenarios):

| System | Top-1 retrieval accuracy (R@1) — claude model |
|---|---|
| Vanilla RAG | 0.6125 |
| Naive supersede-aware RAG | 0.7750 |
| **JAMES (validity-window)** | **0.9750** |

→ For temporally-anchored questions like "What was the policy at contract
signing time?" or "Who was the department head when the appointment was
issued?", **JAMES is the only system that answers correctly**. The Vanilla <
Naive < JAMES rank-order is preserved across all 4 model sizes (4B, 12B, 47B,
cloud) — not a single-model fluke.

### ③ Local-first + workspace isolation

* **Single-customer dedicated deployment** (instance isolated per customer
  via `JAMES_WORKSPACE`)
* **Zero outbound calls by default** (cloud LLM as opt-in via trust zone
  abstraction)
* **All customer data stays customer-side** (operator infrastructure
  contains zero raw customer data)
* **Open source** (`Hashevolution/James-RAG-Evol`)

Critical for legal-domain pilot: business secrets / attorney-client
privilege / personal information protection all satisfied.

---

## 2. What is NOT a measured advantage (honest)

The following axes show JAMES at **literature parity** (no measurement
evidence of JAMES advantage):

* **Generic multi-hop reasoning** (MuSiQue benchmark) — cell-by-cell
  identical to Vanilla and Naive RAG
* **Simple retrieval recall** (top-10) — comparable to Vanilla
* **Answer generation quality** — uses the base LLM (gemma3:12b / claude /
  etc.) directly; no JAMES-specific generation improvement

→ JAMES's value proposition is **NOT "generates better answers"** but
**"can trace which answer came from where and what was valid at the time"**.

---

## 3. v0.5 pilot proposal — 6 months

### Scope
* Department: 1 department (e.g., KM, or one practice area such as M&A,
  Labor, or Real Estate)
* Users: 50-200 active
* Data: contracts / opinions / policies / standard clauses (initial corpus
  5,000-50,000 docs)

### Success metrics (locked at kickoff)
1. **Audit completeness** (RAB AC) ≥ 0.99
2. **Temporal retrieval accuracy** (LRB R@1) ≥ 0.65
3. **User satisfaction** NPS ≥ 30 OR renewal intent ≥ 70%
4. **Production incidents** P1=0, P2≤2
5. **Core regression**: 0 (RAB monthly automated measurement)

### Pricing
* **Cost-recovery base**: ~₩4-6M/month (infrastructure + operator time at
  actuals)
* Co-publication option: 30% reduction if customer agrees to anonymised
  joint evidence publication
* Full commercial pricing: negotiated post-v1.0 (~22 months out), gated by
  customer evidence review

---

## 4. Next steps

| Step | Action | Timeline |
|---|---|---|
| 1 | Review this summary (customer IT / Legal) | 1-2 weeks |
| 2 | Technical brief shared (02-technical-brief.md) | 1 week |
| 3 | Pilot proposal discussion (03 + 04 + 05) | 2-4 weeks |
| 4 | LOI signature (NDA + DPA + pilot terms) | 2 weeks |
| 5 | Pilot kickoff (workspace deployment + corpus ingest) | 4 weeks |
| 6 | Pilot operation + monthly checkpoint | 6 months |

Total: 1-3 months to LOI, +6 months to pilot completion.

---

## 5. Contact

* **Email**: karu-7@hanmail.net
* **GitHub**: https://github.com/Hashevolution/James-RAG-Evol
* **Zenodo (RAB DOI)**: https://doi.org/10.5281/zenodo.20625533
* **Reference**: All measurement results in this document are reproducible
  from the repository above.

---

*Disclaimer: The measurement-evidenced claims in this document (RAB
AC/RF/PC = 1.000 / 0.275; LRB S2 R@1 J=0.975) are reproducible bit-for-bit
from committed `result.json` artefacts in the JAMES repository, given the
pre-registered scenario fixtures. JAMES is a local-first auditable knowledge
reasoning system; the purpose of this pilot is to validate the measurement
evidence in a real domain workflow, NOT to certify compliance with any
regulatory framework. EU AI Act references are descriptive, not prescriptive.*
