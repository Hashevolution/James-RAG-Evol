# IP boundary — mother vs domain packs

> **Status**: living document; the plugin API design (v0.3 Platform Skeleton)
> depends on this boundary being clear.
> **Companion**: `docs/strategy/license-and-monetization.md` analyzes the
> license-side implications. This document analyzes the **code-side**
> implications.

This document specifies the boundary between **mother** (the platform
intended to stay open and shared across all domains) and **domain packs**
(domain-specific extensions intended to be commercializable per
`license-and-monetization.md` §6).

The boundary must be clear before v0.3 plugin API freezes, because the
plugin API IS the boundary contract.

---

## 1. Definitions

- **Mother** — the platform code that any domain can build on. By
  definition, mother contains zero domain-specific knowledge. Mother is
  intended to stay MIT-licensed and publicly visible through v1.0.

- **Domain pack** — a coherent bundle of domain-specific assets
  (ontology, workflows, prompts, eval data, UI customizations) that
  extends mother for a particular vertical (cafe, travel, government).
  Domain packs MAY be released under a commercial license from a
  separate private repository starting at v0.4.

- **Plugin API** — the contract between mother and packs. Defined and
  frozen at v0.3 Platform Skeleton milestone. The plugin API is how
  packs extend mother without modifying mother source.

---

## 2. The boundary rule

> **Mother contains the engine. Packs contain the knowledge.**

If a piece of code, configuration, prompt, ontology, or test data is
specific to one domain (legal, food, retail, travel, government, etc.),
it MUST live in a pack — not in mother.

If a piece of code is generic (search, graph traversal, security, auth,
audit, evaluation harness), it MUST live in mother — not duplicated in
packs.

Violations of this rule:
- Domain code in mother → mother becomes a single-vertical product →
  mother's strategic frame collapses (per business-track §3)
- Generic code in packs → cannot be reused → wasted effort + drift

---

## 3. Current file inventory (as of v0.1.4)

All current source code is **mother**. There are no domain packs yet.

### 3.1 Confirmed mother (stays public + MIT)

```
core/                  # RAG pipeline, retrieval, graph, reasoning
llm/                   # LLM provider abstraction
tools/                 # Generic tool framework (8 subfolders)
processors/            # File ingestion (PDF, images, etc.)
frontend/              # Web UI (HTML + JS, no domain assumptions)
utils/                 # Generic utilities
scripts/               # Operational scripts
eval/                  # Eval harness
test/, tests/          # Test suites
config.py              # Generic config loader
server_llmwiki.py      # Main server (generic)
james_*.py             # Test runners (generic)
requirements*.txt      # Dependencies
*.md                   # Documentation
LICENSE                # MIT
```

### 3.2 Borderline files (case-by-case)

```
wiki/                  # Knowledge graph storage
                       #   → mother provides the markdown-based engine
                       #   → packs ship their own wiki content
                       # Boundary: mother ships an EMPTY wiki/ skeleton +
                       #           loader code; pack ships content
memory/                # Long-term memory DB
                       #   → mother provides schema + access layer
                       #   → packs may extend with domain-specific tables
                       # Boundary: schema in mother; domain rows in pack
workspace/             # Runtime data (backups, patches, proposals)
                       #   → mother provides the directory contract
                       #   → at runtime, contents come from operator usage
                       # Boundary: empty in repos; runtime-only data
reports/               # Test result outputs
                       #   → mother provides format + writer
                       #   → contents are runtime artifacts, not shipped
```

### 3.3 No domain packs exist yet

`packs/cafe/`, `packs/travel/`, `packs/government/` are explicitly
forbidden until v0.4 per business-track §3. Even stub directories (empty
`packs/cafe/.gitkeep`) are forbidden during v0.2-v0.4.

---

## 4. What goes into each domain pack (when they exist)

A domain pack is the union of the following per-domain assets. The
specific contents are defined post-v0.3 plugin API freeze, but the
categories are predictable today:

| Category | Mother holds | Pack holds |
|---|---|---|
| Ontology schema engine | YES | — |
| Domain ontology types + relations | — | YES (cafe: menu, store, region, ...) |
| Retriever framework | YES | — |
| Domain-specific retrievers (e.g., menu-aware search) | — | YES |
| RBAC/ABAC engine | YES | — |
| Domain role definitions (e.g., 가맹점주, 본사 SV, ...) | — | YES |
| Audit log writer | YES | — |
| Domain-specific audit categories | — | YES |
| Eval harness | YES | — |
| Domain eval datasets (RAGAS test sets) | — | YES |
| Frontend chrome | YES (themable shell) | — |
| Domain UI customizations + branding | — | YES |
| Tool registry | YES | — |
| Domain-specific tools (e.g., POS integration) | — | YES |
| Plugin loader | YES | — |
| Pack manifest (`pack.yaml`) | — | YES |

This table is the working contract. The plugin API designed in v0.3 must
support every "Pack holds" row without modification to mother.

---

## 5. Plugin API requirements (preview for v0.3)

The plugin API will be specified in detail at v0.3 Platform Skeleton
milestone. This section records the requirements that flow from the
license / IP boundary, so the API design starts with them in scope.

The plugin API MUST allow a pack to:

1. **Register an ontology** — declare entity types, relation types,
   sensitivity levels, without modifying mother source
2. **Register retrievers** — add domain-specific retrieval strategies
3. **Register tools** — add domain-specific callable tools
4. **Register policies** — add domain-specific RBAC/ABAC rules
5. **Register prompts** — domain-specific system prompts and user templates
6. **Register UI components** — domain-specific frontend modules
7. **Provide eval data** — domain-specific RAGAS test sets
8. **Declare dependencies** — on mother version, on other packs

The plugin API MUST also support:

9. **Loading from a separate repository** — packs are not co-located with
   mother source, may live in a private repository
10. **License-aware loading** — mother loader respects pack licenses (e.g.,
    does not log pack source code in error reports if pack license forbids)
11. **Pack signing / integrity** — for closed-source packs distributed as
    binaries or encrypted assets

These requirements must not leak into mother as domain assumptions — they
are protocol-level only.

---

## 6. Discipline rules during v0.2-v0.4

To preserve the boundary clean, the following rules apply during v0.2 and v0.3:

- ❌ No `packs/*` subdirectory in this repository, even empty
- ❌ No domain-specific names in mother source (e.g., no `cafe_retriever.py`)
- ❌ No domain-specific test data in mother eval suite
- ❌ No domain-specific README sections beyond the horizon table in
  `docs/PLATFORM_READINESS.md`
- ✅ Plugin API contract design lives in mother (v0.3 deliverable)
- ✅ Generic plugin/extension examples live in mother under
  `docs/plugin-api/examples/` once the API exists
- ✅ A "general" reference pack (per ROADMAP v0.3) may live in mother ONLY
  IF it ships zero domain-specific knowledge — the goal is to exercise
  the plugin API surface, not to ship knowledge

---

## 7. Cross-references

- License analysis: `docs/strategy/license-and-monetization.md`
- CLA: `.github/CLA.md`
- Cycle handovers: `docs/handovers/v0.2.0-platform-track.md`,
  `docs/handovers/v0.2.1-business-track.md`
- Roadmap (v0.3 plugin API milestone): `ROADMAP.md`
- Readiness gates (Axis 4 PolicyEngine extraction): `docs/PLATFORM_READINESS.md`
- Architecture principles: `docs/ARCHITECTURE.md`

---

## 8. Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-09 | Mother / pack boundary documented as analytical | v0.3 plugin API design depends on this; recorded before any external PR merged |
| 2026-05-09 | All current source confirmed as mother | No domain code exists; clean baseline |
| 2026-05-09 | Plugin API requirements 1–11 listed for v0.3 | Down-stream requirements derived from license / IP framing |

Future entries append below. Do not delete history.

---

## 9. 한국어 핵심 요약

- **mother (엔진) ↔ 도메인 팬 (지식)** 경계 명문화
- 현재 모든 코드는 mother. 도메인 팬 0개 (v0.4 전엔 추가 금지)
- v0.3 plugin API가 이 경계를 강제하는 계약. 11개 요구사항 §5에 기록
- 팬 후보: 온톨로지 + 도메인 검색기 + 도메인 권한 + 도메인 평가 데이터 + UI 커스터마이즈 (+ 별도 private repo + 상용 라이선스 가능)
- v0.2~v0.4 동안 `packs/*` 디렉토리 0개. 빈 디렉토리도 금지
