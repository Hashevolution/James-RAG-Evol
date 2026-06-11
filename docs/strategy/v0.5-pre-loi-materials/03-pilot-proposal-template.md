# JAMES v0.5 Pilot Proposal Template (2026-06-12 draft)

> Template for pilot negotiation. Customer-specific addenda (NDA / DPA
> / MSA / SLA) sit outside this template — those are operator's legal
> counsel's domain. This template lays out scope / metrics / responsibilities
> / pricing / termination terms for a 6-month JAMES pilot in the legal
> contract review domain.

---

## 1. Parties

* **Operator**: Hashevolution / Jiwon Seo (sole proprietor) (이하 "운영자")
* **Customer**: [CUSTOMER NAME] (이하 "고객사")

## 2. Pilot purpose

To validate the v0.5 first-domain pilot of JAMES (audit-native + temporal-
retrieval RAG) in the customer's legal contract review workflow, with
measurement evidence backed by RAB AC/RF/PC = 1.000 × 3 and LRB v0.2.1
⭐⭐⭐ cross-model tier (see `02-technical-brief.md`).

The pilot's success is gated by 7 Dim F production-proof gate metrics
(§4) measured monthly. Pass = customer attestation of pilot success +
operator handover of all artefacts.

The pilot is **NOT** a commitment by either party to a long-term
commercial agreement; it is a 6-month evidence-gathering exercise.
Either party may terminate per §10 with cause.

## 3. Pilot scope

### 3.1 Functional scope (included)

| Capability | Spec reference |
|---|---|
| Workspace-isolated single-instance deployment | `docs/PLATFORM_READINESS.md` Dim D |
| Audit log (RAB-compliant) | `eval/rab/SPEC-v0.1.md` |
| Validity-window retrieval (LRB-compliant) | `docs/design/v0.4-lrb-lifecycle-retrieval-benchmark-design.md` |
| Local LLM backend (Ollama default) | `core/reasoning/backends/ollama_local.py` |
| Optional cloud LLM (Claude via trust zone) | `core/abstraction/` |
| Web UI (`server_llmwiki.py`) | `server/routes/*` |
| Monthly RAB / LRB measurement reports | per §4 |

### 3.2 Scope explicitly excluded (v0.5 limits)

* Multi-tenancy (single customer instance only)
* HTTPS / SSO / SAML / LDAP enterprise auth (v1.0 gate)
* SOC2 / ISO27001 certification (operator can provide readiness assessment only)
* Backup / restore via CLI (manual snapshot only at v0.5)
* Korean / cross-lingual benchmark validation (LRB v0.3 candidate)
* Domain-specific UI (legal-pack features) — operator will provide
  via `packs/legal/` plugin pattern AFTER pilot kickoff if requested,
  per CLAUDE.md mother-platform discipline

### 3.3 Domain scope

* **Department**: 1 부서 (예: KM, 또는 1 practice area such as M&A,
  노동, 부동산)
* **Active users**: 50-200
* **Corpus size**: 5,000-50,000 documents (계약서 / 의견서 / 정책 /
  표준 조항 / 판례 등)
* **Use cases (prioritised)**:
  1. "체결 시점 기준 표준 조항 retrieval" (LRB time-travel use case)
  2. "이 계약의 ingest / amend / supersede chain 감사" (RAB use case)
  3. "유사 case 의 답변 / 추론 chain 자체 감사" (RAB + LRB combined)

## 4. Success metrics (6-month gate)

Pass criteria = F.1 to F.6 all satisfied + F.7 ≥ 1 satisfied:

| Metric | Threshold | Measurement protocol |
|---|---|---|
| **F.1** Continuous operation | ≥ 180 days | Calendar |
| **F.2** Core regression | Δ ≤ -0.01 on any RAB axis per core/ PR | CI on every PR |
| **F.3** Weekly active users | ≥ 50 | audit log analytics |
| **F.4** RAB AC on production traffic | ≥ 0.99 | Monthly export + scorer |
| **F.5** LRB R@1 on production sample | ≥ 0.65 | Monthly 30-query gold labelling + scorer |
| **F.6** P1 incidents = 0, P2 ≤ 2 | per categorisation in §7 | Joint incident log |
| **F.7** Exit survey | NPS ≥ 30 OR 재계약 의향 ≥ 70% | Customer survey + interview |

## 5. Timeline (6 months from kickoff)

```
Week 0-2   Kickoff
  - NDA / DPA / boundary review (security teams both sides)
  - Workspace isolation deployment + connectivity test
  - Initial corpus definition + curation
  - F.4 / F.5 metric protocol final lock
  - F.7 exit survey question set lock

Week 3-6   Setup & ingest
  - JAMES instance deployed in customer environment
  - Initial corpus ingest + RAB AC baseline
  - 10-20 friendly users onboarded
  - LRB R@1 baseline measured (operator + customer expert pair-label
    30 historical-style queries)

Week 7-12  Expansion
  - 50+ active users
  - Weekly retro (15 min)
  - Small adjustments (UI / search hints / etc.)

Week 13-20 Stabilisation
  - Monthly RAB measurement automated
  - Monthly LRB R@1 measurement (30 queries fresh per month)
  - Core regression watch (any core/ PR → CI re-runs RAB)
  - Quarterly business review

Week 21-24 Closure
  - F.1-F.7 measurement finalised
  - Customer exit interview
  - Artefact handover
  - Either renewal discussion OR clean handoff
```

## 6. Responsibilities

### 6.1 Customer responsibilities

* Provide pilot sponsor at 3 levels: 임원 + 부서장 + 운영 PIC
* Provide initial corpus + categorisation + ingest authority
* Onboard 50+ active users by Week 12
* Participate in monthly retros
* Provide domain expert for monthly 30-query gold labelling (LRB F.5)
* Approve security / compliance review at kickoff (DPA / NDA / IRB if applicable)

### 6.2 Operator responsibilities

* Deploy workspace-isolated instance per §3.1
* Provide monthly RAB / LRB measurement reports
* Weekly office hour (1 hour) for incident triage
* Provide pack-level UI extensions per `packs/<domain>/` plugin pattern
  (if requested by customer)
* Provide complete handover at pilot end: all artefacts + data export

### 6.3 Shared responsibilities

* Lock success metric protocol at kickoff (§4 thresholds + measurement
  methodology)
* Monthly checkpoint meeting (1 hour)
* Risk register maintenance (per §8)
* Pilot communications (no external public announcements without joint
  approval)

## 7. Incident categorisation (§4.F.6)

* **P1** = Service down or data loss
* **P2** = Functional impairment or material performance degradation
* **P3** = Minor issue, workaround available

Operator response SLAs (best-effort during pilot; not contractual):
* P1: within 4 hours during business hours (KST)
* P2: next business day
* P3: weekly batch

## 8. Pricing

### 8.1 Cost-recovery base

| Item | Monthly | Total (6 mo) |
|---|---|---|
| Infrastructure (Option A customer-hosted) | included in customer side | — |
| Operator time (40-60h/mo monthly measurement + support) | ~₩4-6M | ₩24-36M |
| Travel + on-site support (KST domestic, as needed) | actuals | actuals |
| **Total** | | **₩24-36M (~$18-27K)** |

### 8.2 Co-publication option

If customer agrees to joint publication of pilot evidence (anonymised /
aggregated; specifics negotiated), operator reduces base by 30%.

### 8.3 Renewal / commercial pricing

Pilot pricing does NOT extend to renewal. Post-pilot commercial pricing
= negotiated separately after pilot results review, gated by v1.0
platform maturity.

## 9. IP, data, and confidentiality

* **Customer data**: customer property; operator has no rights to
  customer data beyond pilot operation; all customer data exported +
  deleted from operator-controlled storage at pilot end
* **JAMES software**: operator property (Apache 2.0 license to repo;
  any operator-developed customer-specific packs/extensions = operator
  property, but customer gets perpetual non-exclusive license for
  internal use)
* **Pilot evidence**: jointly produced (operator can use anonymised
  aggregate evidence for benchmarks / publications subject to
  customer review)
* **Confidentiality**: 5-year mutual NDA on all customer data and
  pilot specifics; perpetual on customer trade secrets

## 10. Termination

* Either party may terminate at any time with 30 days notice and
  cause
* Causes:
  * Customer: failure of F.4 (RAB AC) ≥ 0.99 for 2 consecutive months
  * Operator: P1 incident with customer-side root cause and customer
    refusal to remediate; or unpaid invoice > 60 days
* Upon termination, operator returns/destroys all customer data within
  7 days

## 11. Governing law

대한민국 법 (서울 중앙지방법원 1심 관할).

## 12. Signatures

| | Operator | Customer |
|---|---|---|
| Name | Jiwon Seo | [CUSTOMER NAME] |
| Title | Sole proprietor, Hashevolution | [CUSTOMER TITLE] |
| Date | | |
| Signature | | |

---

*This is a TEMPLATE. Customer-specific terms (entity names, currency,
specific dates, jurisdiction overrides, etc.) inserted per customer
during negotiation. Legal counsel review required before signature.*
