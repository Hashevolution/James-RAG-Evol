# v0.5 Pre-LOI Customer-Facing Materials

> **Status**: solo-drafted (autonomous loop). External-facing assets
> for the v0.5 first-domain pilot outreach. Each document is a Korean
> + English pair targeting the Primary domain (legal contract review)
> identified in `docs/strategy/v0.5-domain-candidate-evaluation-
> 2026-06-11.md`.
>
> **Predecessors**:
> - `v0.5-domain-candidate-evaluation-2026-06-11.md` (legal contract 86%
>   Primary)
> - `v0.5-pilot-scope-spec-2026-06-11.md` (generic Dim F gate spec)
> - `docs/PLATFORM_READINESS.md` (6-dimension framework)
>
> **Constraint**: Per CLAUDE.md rule #1 mother-platform discipline.
> These materials do NOT promise domain-specific features that don't
> exist; they frame the measurement-evidenced moats (audit + temporal
> retrieval) as the pilot evidence.

---

## Material set

| File | Audience | Purpose | Length |
|---|---|---|---|
| `01-exec-summary-legal-ko.md` | C-level / 법무팀장 | 1-pager 한국어 | ~1 page |
| `01-exec-summary-legal-en.md` | C-level / English | 1-pager English | ~1 page |
| `02-technical-brief.md` | IT / Architecture team | RAB + LRB measurement evidence summary | ~3 pages |
| `03-pilot-proposal-template.md` | Procurement / Legal counsel | Pilot terms negotiation base | ~5 pages |
| `04-roi-scenarios.md` | CFO / 운영팀 | ROI / cost-benefit scenarios (3 sizes) | ~2 pages |
| `05-risk-mitigation.md` | Security / Compliance officer | Risk matrix + mitigation | ~2 pages |

## Out of scope (this PR)

* Customer-specific addenda (NDA / MSA / SLA) — pilot kickoff
* Korean translation polishing — operator review
* Visual design / branding — operator action
* Customer name lists / outreach playbook — v0.5.3 (separate cycle)

## 사용 시점

| 단계 | Materials | Who |
|---|---|---|
| Cold introduction | 01 (exec summary) | Operator → 잠재 customer |
| Initial interest | 02 (technical brief) | Operator → customer IT team |
| Pilot 상담 | 03 (proposal template) + 04 (ROI) + 05 (risk) | Joint discussion |
| LOI 서명 | (별도 legal doc) | Operator + customer legal |
| Pilot kickoff | `v0.5-pilot-scope-spec-2026-06-11.md` + customer-specific addenda | Joint |

## Disclaimer (모든 docs 상단에 포함)

```
This pilot materials set is provided AS-IS for evaluation. The
measurement-evidenced claims (RAB AC/RF/PC = 1.000 / 0.275; LRB
S2 R@1 J=0.975) trace to committed result.json artefacts in
https://github.com/Hashevolution/James-RAG-Evol; reproducible
bit-for-bit on the operator's environment given the pre-registered
scenario fixtures. JAMES is a local-first auditable knowledge
reasoning system; the pilot's purpose is to validate the
measurement evidence in a real domain workflow, NOT to certify
compliance with any regulatory framework. EU AI Act references
are descriptive, not prescriptive.
```

## Korean / English pairing

For each customer-facing doc (01 / 02 / 03 / 04 / 05), the Korean
version is the primary; the English version is supporting context
for foreign-affiliate stakeholders (multinational law firms,
overseas branches, etc.). When the two diverge, Korean is
authoritative.
