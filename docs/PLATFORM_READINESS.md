# JAMES — Platform Readiness Framework

> How we measure when JAMES is ready to be a "mother platform" from
> which domain packs (legal, food, retail, etc.) can branch off
> safely without breaking the core.

Status: living document. Last updated: v0.1.4 (planning v0.2 entry).

---

## 1. Why this document exists

JAMES is technically capable of solving multiple verticals
(legal contract analysis, food/beverage retail, travel ticketing,
franchise compliance, etc.). The temptation to "ship a vertical"
is constant.

**That temptation is the single biggest risk to the project.**

A platform that ships verticals before its extension contract is
stable becomes a per-vertical fork tree. Every later vertical pays
the cost of every earlier vertical's shortcuts. Most "platforms"
that fail, fail this way.

This document defines:

- the **6 dimensions** that determine mother-platform readiness
- the **gates at v0.2 / v0.3 / v0.4 / v1.0** that must be passed
  before each level of domain branching is allowed
- the **3 forms of branching** (Pack / Distribution / Vertical
  Product) and when each is appropriate

If a contributor proposes work that conflicts with this framework,
the burden of proof is on them to update this document first.

---

## 2. The 6 readiness dimensions

| # | Dimension | What it measures | How we test it |
|---|---|---|---|
| A | **Architecture stability** | module boundaries, file size, no circular imports | `pydeps core/` acyclic, all `core/` files < 20 KB |
| B | **Extension API stability** | plugin interface, version policy, backward compatibility commitment | Plugin loader exists; SemVer; deprecation policy documented |
| C | **Evaluation contract** | every change measured against a fixed yardstick; domain packs inherit it | RAGAS + STEP-N suite locked; PR contract enforces bench numbers |
| D | **Operational maturity** | HTTPS, SSO, backup, observability, audit | Multi-tenancy isolation; OpenTelemetry exporter; backup/restore CLI |
| E | **Security boundary** | PolicyEngine extracted; external red-team passed | All policy decisions go through one module; red-team report public |
| F | **Production proof** | at least one external user runs production for ≥ 6 months without core regression | Customer attestation; uptime metrics published |

A dimension is **passed** only when the test is automated and
re-runnable. Manual confirmations do not count.

---

## 3. Gates by milestone

### Gate v0.2 — Foundation (currently in progress)

**Theme**: make the v0.1 capabilities trustworthy enough to recommend
to a second user.

**Pass criteria** (all 6 dimensions partially satisfied):

- A: Architecture — `core/` modules ≤ 20 KB; `pydeps` acyclic
- B: Extension API — *not yet*; this gate does not require it
- C: Eval — STEP 7 locked as committed regression; RAGAS integrated
- D: Ops — structured logs with `trace_id` end-to-end; `/admin/trace/{id}`
- E: Security — `PolicyEngine` extracted; capability tokens for tools
- F: Production — single-user reproducible deployment validated

**Allowed at this gate**: bug fixes, refactors, eval harness work.

**Forbidden at this gate**: domain packs, vertical UIs, marketing
domain claims in README/ROADMAP.

### Gate v0.3 — Platform Skeleton

**Theme**: define and freeze the extension contract.

**Pass criteria**:

- B: Extension API — `core/plugins/base.py` defines 4 plugin types
  (Ontology / Prompt / UI panel / Scorer); plugin loader respects
  `JAMES_PLUGINS=` env var
- B: Reference Pack — JAMES's own default behavior runs as
  `packs/general/` (dogfood: removing the pack disables JAMES;
  swapping it changes domain)
- C: Eval contract — every pack must pass RAGAS + STEP-N; merge
  blocked otherwise
- D: Ops — multi-instance hosting (same code, different workspace)
  via `JAMES_WORKSPACE=` env var
- A versioning policy committed to repo: SemVer; deprecation
  guaranteed for 12 months

**Allowed at this gate**: building one Reference Pack inside the repo.

**Forbidden at this gate**: external/customer domain packs (the API
is not yet proven through real third-party use).

### Gate v0.4 — First Domain Pilot

**Theme**: prove the platform contract by running ONE real domain
in production for 6 months.

**Pass criteria**:

- B: One non-general domain pack (`packs/legal/` or `packs/food/`)
  exists and is loaded as a plugin without core code changes
- F: One external customer runs the pilot for ≥ 6 months
- F: Zero core regressions caused by the pack during the pilot
- C: Pack passes both general and domain-specific eval suites
- E: External red-team pass on prompt injection (replace pattern-only
  defense with ML guard + patterns)

**Allowed at this gate**: building exactly one domain pack with
a paying or signed-PoC customer.

**Forbidden at this gate**: a second domain pack (we don't yet know
if the contract works for non-trivial diversity — wait for v1.0).

### Gate v1.0 — Production-Grade Mother

**Theme**: make domain branching safe for outsiders.

**Pass criteria**:

- D: HTTPS / SSO / SAML / LDAP / multi-tenancy production-ready
- D: SOC2 or ISO27001 readiness assessment (not full cert; readiness)
- D: Backup / restore / rollback CLI tested under simulated failure
- D: Prometheus + OpenTelemetry exporter
- B: Public SDK + plugin author guide (`docs/PLUGIN_AUTHORING.md`)
- F: Bus factor ≥ 2 (at least one non-maintainer with full commit history
  and PR review responsibility)
- E: Annual external red-team scheduled

**Allowed at this gate**: external developers can publish their own
domain packs. Marketplace conversation begins.

**Forbidden**: nothing related to platform stability — but please
keep building Domain Packs first (Distribution / Vertical Product
require sustained customer demand, not aspiration).

---

## 4. Branching forms (when v1.0 is passed)

A domain can branch from JAMES in one of three forms. The right
choice depends on the domain's traction.

### 4.1 Domain Pack (lightweight)

- **Contains**: ontology + prompts + UI templates + rule book
- **Touches core**: zero lines
- **Build cost**: 2~4 months per domain
- **Analogy**: VS Code extension
- **Examples**: `packs/cafe/`, `packs/franchise/`, `packs/clinic/`,
  `packs/legal/`
- **When to use**: first 1~3 deployments in a domain. Validates fit.

### 4.2 Domain Distribution (medium)

- **Contains**: Pack + custom integrations (POS, EHR, GDS, ERP, e-결재)
- **Touches core**: zero lines (integrations are sub-modules)
- **Build cost**: 4~8 months per domain
- **Analogy**: Linux distribution (Ubuntu vs CentOS)
- **Examples**: "JAMES-Cafe with Cafe24 connector", "JAMES-Pharmacy
  with claim-system connector"
- **When to use**: domain has signed > 3 customers and needs
  industry-standard integrations.

### 4.3 Vertical Product (heavy)

- **Contains**: Distribution + own brand + own UI + own billing + own sales
- **Touches core**: zero lines (still uses mother as engine)
- **Build cost**: 12+ months per vertical
- **Analogy**: WordPress.com vs WordPress.org; Salesforce Industry Clouds
- **Examples**: "JAMES Legal" SaaS product, "JAMES Cafe" point-of-sale companion
- **When to use**: domain has predictable revenue ≥ ARR 5억 and demands
  isolated brand / SLA / billing.

**Typical evolution**: Pack → market validation → Distribution →
revenue validation → Vertical Product. Skipping a step is the most
common failure mode.

---

## 5. The "do not branch yet" trap

The most common project-killing pattern:

| Wrong pattern | Consequence |
|---|---|
| Build a domain pack while v0.2 architecture is still moving | Pack pressure freezes the wrong abstractions; refactor cost balloons |
| Promise a domain customer "we'll add X" before v0.3 plugin API exists | Forces core fork; later domains pay the cost forever |
| Try two domains at once before the first is stable in production | Neither generalizes; both diverge from the platform contract |
| Market the platform's domain coverage before v0.4 pilot completes | Sales-marketing-eng feedback loop forces unsupported promises into the codebase |

Discipline: **before each gate is passed, the next form of branching
is forbidden** (see Gate sections above).

---

## 6. Strategic timeline (calendar estimate)

Assumes current solo-maintainer + AI-pair pace; team scaling can
compress this.

| Milestone | Cumulative time | Cumulative team | Cumulative cost (KRW) |
|---|---|---|---|
| v0.2 (Foundation) | 4 months | 1 + Claude | 0 ~ 0.5억 |
| v0.3 (Platform Skeleton) | 10 months | 2~3 | 2~3억 |
| v0.4 (First Pilot) | 16 months | 4~5 | 5~7억 |
| v1.0 (Mother-ready) | 22 months | 6~8 | 10~15억 |

Beyond v1.0, the platform compounds: each new Domain Pack reuses
mother-level investments (security, observability, eval, policy)
that would otherwise have to be rebuilt per vertical.

---

## 7. Domain candidates currently being evaluated (for reference only)

These are domains that have been informally evaluated against JAMES's
current capabilities. **Inclusion here is not a roadmap promise** —
none will be built before v0.3 at the earliest.

| Domain | Match strength | Earliest entry gate |
|---|---|---|
| Legal contract analysis (B2B 법무팀) | high | v0.4 (first pilot candidate) |
| Food / beverage retail (franchise HQ) | high | v0.4 (alternative pilot) |
| Travel ticketing (OTA, refund disputes) | medium-high | v1.0+ |
| Franchise compliance (가맹사업법) | medium-high | v1.0+ (extends legal pack) |
| Retail / distribution (supplier 360°) | medium | v1.0+ |
| Personal knowledge / second brain | medium | v1.0+ Domain Pack |

The decision of which domain becomes the v0.4 First Pilot will be
made in the v0.3 cycle, based on (a) which has signed PoC interest,
(b) which has clearer regulatory / legal liability boundaries.

---

## 8. How to update this document

- Adding a dimension or changing a gate criterion: PR with
  `architecture` label and rationale; require maintainer approval.
- Updating the timeline: PR with current-cycle metrics that justify
  the change.
- Adding a domain candidate: PR with informal fit-check; no roadmap
  commitment.
- Removing the "no branching before v1.0" discipline: do not.

---

## 9. 한국어 요약

자메스는 **v1.0(약 22개월 후)까지** 도메인 분화 없이 "모체 플랫폼"으로만 강화합니다. 6가지 측정 차원(아키텍처/확장 API/평가/운영/보안/프로덕션 검증)이 모두 임계치를 넘어야 도메인 분화가 안전합니다. 그 전까지는 도메인 작업이 모체를 깨뜨리는 가장 큰 위험이며, **각 게이트 통과 전에는 다음 단계의 분화가 금지**됩니다. 도메인 후보(법률·식품·유통·여행 등)는 informally 평가만 진행하고, 실제 코드 작업은 v0.3 이후에 결정합니다.
