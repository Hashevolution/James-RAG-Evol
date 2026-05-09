# License + monetization strategy (analytical)

> **Status**: analytical, not a final decision.
> **Audience**: maintainer + advisors (also useful for evaluators).
> **Cross-reference**: private operator notes (per `docs/handovers/v0.2.1-business-track.md` §7) hold the actual decisions, financial projections, and customer-specific tactics. This file holds only the public-friendly analytical frame.

This document analyzes how PROJECT JAMES should structure its license and
revenue model. The decision must be made before v0.4 (first paid customer
PoC) — committing too late means the first customer relationship cannot be
priced cleanly.

This file is intentionally analytical, not prescriptive. The recommended
direction is summarized in §6, but the final commitment is recorded in
`docs/handovers/v0.2.1-business-track.md` §8 (decision log) only when the
maintainer formally commits.

---

## 1. Why this question matters now

JAMES is currently:

- Licensed under MIT (permissive, all rights granted to anyone)
- Hosted publicly on GitHub
- Maintained by 1 operator + Claude (no external code contributors yet)
- Targeted at cloud-rejecting customers (gov / regulated / on-prem)
- Pre-revenue, capital-zero

If the license stays MIT through v1.0:
- Mother platform AND domain packs become free
- First customer (cafe franchise) can self-host without paying
- Revenue path is services-only (consulting, integration, support)
- Most Korean enterprises do not have a strong culture of paying for OSS
  support contracts → revenue will be low

If the license model changes too late (after external contributors are merged):
- Relicensing requires permission from every contributor
- Some contributors become unreachable; their code may need to be rewritten
- The transition costs months of engineering and creates a confusing
  fork window

The question is therefore time-sensitive. The answer must be in place by
v0.4 (~14 months from v0.2 start), but the **prerequisite legal
infrastructure** (Contributor License Agreement) must be in place NOW —
before the first external PR is merged.

---

## 2. Constraints that shape the decision

| Constraint | Implication |
|---|---|
| Cloud-rejecting target customers | They demand auditable / inspectable code → fully closed source is not viable |
| Korean B2B culture | Weaker willingness to pay for OSS support contracts than US/EU → pure services model is fragile |
| 1-operator + Claude origin | Today, full relicensing is still possible (no external contributors); waiting closes options |
| MIT inbound | Cannot easily be made more restrictive without contributor agreement |
| Capital-zero | Need a legal model that supports asking for money at v0.4 without surprising contributors |
| Mother-platform discipline (no parallel domains) | License model must distinguish mother (kept open) from domain packs (potentially commercial) without violating §3 of business-track |

---

## 3. The four candidate models

### 3.1 Stay MIT (status quo)

**How**: Mother + future domain packs all MIT.

| Dimension | Assessment |
|---|---|
| Trust signal | Strongest (purest OSS) |
| Customer evaluation | Easiest (zero friction) |
| Contributor friendliness | Highest |
| Revenue model | Services only — consulting, integration, custom development, training, support contracts |
| Korean market viability | Low (weak culture for OSS support contracts) |
| Competitor risk | High — large vendors can repackage with no obligation |
| Reversibility | One-way — adding restrictions later requires CLA-mediated relicensing |

**When this is right**: If the maintainer's goal is academic / prestige / open dataset / public-good, not commercial revenue.

### 3.2 Open Core (mother MIT + domain packs commercial)

**How**: `core/`, `llm/`, `tools/`, `processors/`, `frontend/` (the mother) stay MIT. Future `packs/cafe/`, `packs/government/`, etc. are **separate private repositories** released under a commercial license to paying customers. The plugin API (v0.3 Platform Skeleton milestone) is the boundary contract.

| Dimension | Assessment |
|---|---|
| Trust signal | Strong (mother visible) |
| Customer evaluation | Easy (mother auditable; pack negotiated separately) |
| Contributor friendliness | High for mother; pack contributors via NDA |
| Revenue model | Commercial license fees per domain pack + services + support |
| Korean market viability | Moderate-High (familiar from Atlassian / Elastic / GitLab patterns) |
| Competitor risk | Medium — competitors can copy mother but not pack ontologies |
| Reversibility | Adding new packs is reversible; mother license change still requires CLA |

**When this is right**: If the maintainer plans to sell vertical solutions and the differentiation is in domain knowledge (ontology, workflows, customizations), not in the core engine.

**Precedents**: GitLab (Community vs Enterprise), Sentry (open core through 2019), Mattermost, Cal.com, Plausible, n8n (now Sustainable Use License but originally open core).

### 3.3 AGPLv3 + Dual Commercial License

**How**: Whole project (mother + packs) AGPLv3. Companies that want to embed JAMES into a closed-source product or SaaS without releasing their modifications must purchase a commercial license.

| Dimension | Assessment |
|---|---|
| Trust signal | Strong (genuine OSS) |
| Customer evaluation | Easy (auditable) |
| Contributor friendliness | High |
| Revenue model | Commercial license sold to companies that cannot accept AGPL terms |
| Korean market viability | Mixed — many Korean enterprises have "AGPL allergy" via legal review boards |
| Competitor risk | Medium — competitors must also AGPL their forks, which limits commercial reuse |
| Reversibility | Hard once contributions are merged (unless CLA in place) |

**When this is right**: If most enterprise customers can pay for a commercial license and the AGPL is enough deterrent. Works best when the user audience is primarily SaaS providers (who must avoid AGPL).

**Precedents**: MongoDB pre-SSPL, Elastic pre-SSPL, Sentry early years, Grafana (Apache + commercial), MariaDB.

### 3.4 Business Source License (BSL)

**How**: Source-available with usage restrictions for X years (typically 4), then automatic conversion to a true OSS license (e.g., Apache 2.0). Restrictions can be tuned (e.g., "no use as a competing managed service for 4 years").

| Dimension | Assessment |
|---|---|
| Trust signal | Medium (some communities reject BSL as "not real OSS") |
| Customer evaluation | Easy (still source-available) |
| Contributor friendliness | Medium (some contributors avoid BSL) |
| Revenue model | Commercial license sold for use cases the BSL restricts |
| Korean market viability | Low awareness, but improving |
| Competitor risk | Low (BSL restrictions can be specific) |
| Reversibility | Once chosen, future Apache fallback is automatic |

**When this is right**: If the project must explicitly prevent a specific competitive scenario (e.g., a hyperscaler hosting JAMES as managed service). Less appropriate for general OSS where freedom-of-use is a value.

**Precedents**: CockroachDB, MariaDB MaxScale, Couchbase, Sentry (current), HashiCorp's Terraform / Vault / Consul (since 2023).

---

## 4. Decision matrix

Score 1 (poor fit) — 5 (strong fit) for each candidate against JAMES's
specific constraints. Higher = better fit. Subjective; recorded for
calibration only.

| Criterion (weight) | MIT | Open Core | AGPL+Dual | BSL |
|---|---|---|---|---|
| Customer auditability for cloud-rejecting target (×3) | 5 | 4 | 5 | 4 |
| Revenue path strength (×3) | 1 | 4 | 4 | 4 |
| Korean B2B familiarity (×2) | 3 | 4 | 2 | 1 |
| Contributor friendliness (×2) | 5 | 4 | 4 | 3 |
| Competitor moat (×2) | 1 | 3 | 4 | 4 |
| Maintainer simplicity (×1) | 5 | 3 | 3 | 3 |
| Reversibility (cost of switching later) (×1) | 1 | 4 | 2 | 3 |
| **Weighted total** | **39** | **52** | **47** | **42** |

Weights are subjective; scores will shift as v0.3-v0.4 evidence accumulates.

---

## 5. Hybrid options

The four models above are not mutually exclusive. Two hybrids merit consideration:

### 5.1 Open Core + AGPL on mother

Mother is AGPLv3 (instead of MIT) with commercial dual license; packs are
proprietary. Strongest revenue position, but Korean market AGPL aversion may
dominate.

### 5.2 MIT today + Open Core at v0.4

Stay MIT through v0.3. At v0.4, when the first domain pack ships, that pack
ships closed-source from a separate private repository. Mother remains MIT.
The CLA in place from v0.2 protects the option to relicense mother later if
needed.

This is the **lowest-friction migration path** because:
- No license switch on existing mother code
- Pack lives in new private repo, never inherits mother's MIT
- Customers see mother is open, pack is commercial — clear separation
- Future option to relicense mother if AGPL or BSL becomes attractive

---

## 6. Recommendation (analytical)

Based on §4 weighted scoring and the hybrid analysis in §5.2, the
recommended direction is:

> **Stay MIT for v0.2 and v0.3. At v0.4, ship the first domain pack from a
> separate private repository under a commercial license. Keep mother MIT
> through v1.0. CLA must be in place NOW to preserve future relicense options.**

This is **NOT a binding decision**. It is a recommendation calibrated
against today's evidence. The decision is recorded in
`docs/handovers/v0.2.1-business-track.md` §8 only when the maintainer
formally commits.

The recommendation may shift if:
- Korean B2B culture for OSS support contracts proves stronger than expected
  → MIT may be sufficient (revenue from services + support)
- A specific large customer offers AGPL-acceptable terms early → AGPL
  becomes more attractive
- A specific competitor scenario emerges (e.g., a Korean cloud vendor
  pre-announces a managed JAMES offering) → BSL may become necessary

---

## 7. What to do NOW (regardless of final decision)

These actions are **license-decision-agnostic** and should be taken in the
v0.2 cycle so future options remain open:

| Action | Why | Status |
|---|---|---|
| Add `.github/CLA.md` | Preserves all four future license options | done |
| Require CLA acknowledgment in PR template | Mechanism for inbound rights grant | done |
| Update `CONTRIBUTING.md` with CLA reference | Contributor-visible documentation | done |
| Document mother / pack IP boundary | Enables open-core split when v0.4 comes | done in `docs/strategy/ip-boundary.md` |
| Add commercial-use note to README (EN + KO) | Sets expectations; avoids surprise at v0.4 | done |
| Append decision-log placeholder to business-track §8 | Records this as a known-pending decision | done |

After this PR, the next license-related action is the v0.4 cutover decision
itself, which lives in private operator notes until formally committed.

---

## 8. Risks and watch-list

| Risk | Mitigation |
|---|---|
| External PR merged without CLA acknowledgment → relicensing impossible for that file | PR template hard-required checkbox + manual review verification before merge |
| Cafe franchise self-hosts JAMES from public repo (no contract) | Pack lives in private repo; mother alone is insufficient for the cafe domain solution |
| Large vendor (hyperscaler-style) offers managed JAMES, capturing the SaaS layer | If/when this happens, evaluate switching to BSL for mother |
| Korean enterprise asks for "everything" under MIT including pack | Pricing thesis: pack license is non-negotiable; services + customization are |
| Competitor copies mother and ships faster | Domain packs + Korean operator + customer relationships are the moat — code alone cannot be moat |

---

## 9. Decision deadlines

| By | Decision required |
|---|---|
| v0.2 close (~month 4) | Confirm CLA + IP boundary doc are in place. (No license change yet.) |
| v0.3 close (~month 10) | Confirm plugin API boundary is clean enough that domain packs can ship from separate repos |
| v0.4 start (~month 10-14) | Final license commitment for first domain pack |
| v0.4 close (~month 22) | Decide whether mother license also changes (likely no) |
| v1.0 (~month 22+) | Public pricing thesis if open-core route is taken |

The v0.4 start decision is the irrevocable one. Everything before that is
reversible. Everything after that is committed to customers.

---

## 10. 한국어 핵심 요약

- 현재: MIT 라이선스, 1인 + Claude, 외부 contributor 0명. **모든 옵션 살아있음**
- 의사결정 데드라인: v0.4 (첫 PoC 시작) **약 10–14개월 후**
- 추천 방향 (잠정): v0.2/v0.3은 MIT 유지 + CLA 도입. v0.4에서 첫 도메인 팬 (cafe)을 **별도 private repo + 상용 라이선스**로 출시. mother는 MIT 유지
- 지금 반드시 해야 할 것: **CLA 도입** (외부 PR 머지 전), IP 경계 문서, 상용 사용 README 공지
- 위 추천은 잠정. 한국 B2B 시장 OSS 지원 계약 문화, 경쟁사 등장 여부에 따라 v0.4 시점에 재평가
- 구체적 가격, 고객별 조건, 재무 추정은 **이 저장소가 아닌 비공개 운영자 노트**에 보관 (business-track §7)
