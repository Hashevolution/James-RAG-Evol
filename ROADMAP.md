# Roadmap

> **Note**: This roadmap describes intended directions, not commitments.
> Priorities will shift based on user feedback and real-world testing.

For the underlying readiness framework (6 dimensions, gate criteria,
branching forms), see [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md).

---

## v0.1.0 — Foundation (current, alpha)

**Status**: Released

### Done
- Hybrid Search (Vector + BM25 + keyword)
- Graph-RAG with ontology (12 relation types)
- 3-stage security model (RBAC + ABAC + Instruction Isolation)
- JWT auth + rate limiting + audit log
- Self-evolution scaffolding (Patch Pipeline 4-Gate)
- Multi-LLM routing (Ollama-based)
- Multimodal hooks (image / video / audio)
- Web search (Tavily + DuckDuckGo)
- 11-trait personality system
- Knowledge tracker (8 abilities + 6 domains)
- Internationalization (English + Korean UI)

### Known Gaps (to address in v0.2)
- Real-data validation pending
- Multimodal pipeline integration limited
- Self-evolution untested at scale

---

## v0.2.0 — Foundation Hardening (released 2026-05-08)

**Theme**: Make the v0.1 capabilities trustworthy enough to recommend
to a second user. Six axes, all of them P0/P1. **Five axes engineering-
complete.** Axis 6 ongoing — gated on second-user adoption rather than
code, which is now in self-feedback + recruitment phase.

### Axis 1 — Architecture Separation (P0) ✅

Goal: no single file owns more than one responsibility.

- [x] Split `core/reasoning_engine.py` into `core/reasoning/`
      package: `engine.py` (orchestration), `pipeline.py` (loop),
      `modes.py` (mode dispatch). PRs #37 / #38 / #39.
- [x] Consolidate `memory_*` into `core/memory/` package with
      documented public API. PR #35.
- [x] Public typed interfaces for: `Retriever`, `GraphEngine`,
      `PolicyEngine`, `Reasoner`, `OutputFilter`. PR #50.
- [ ] `tools/self/` sub-process boundary — deferred to v0.3 (no
      observed need at v0.2 scale; in-proc access is contained).

**Done when**: ✅ `import` graph is acyclic and each module has < 20 KB.

### Axis 2 — Evaluation Harness (P0) ✅

Goal: every change is measured against the same yardsticks.

- [x] STEP 7 13-query suite locked as committed regression baseline
      (`eval/regression/step7_*.json`, `scripts/bench.py`). PR #52.
- [x] **RAGAS** integrated for retrieval / faithfulness / answer
      relevance. Live `/query/` integration. PRs #51 / #64 / #66.
- [x] `scripts/bench.py` with `--check` / `--update-baseline`. PR #52.
- [x] PR-contract: `core/{retrieval,graph,reasoning}` PRs paste
      bench numbers. CLAUDE.md rule 2 + CONTRIBUTING. PR #43.
- [ ] LegalBench subset — intentionally deferred (domain-coupled;
      contradicts the "no parallel domains" mother-platform rule
      until v1.0).

**Done when**: ✅ a PR cannot land without bench numbers attached.

### Axis 3 — Observability / Tracing (P1) ✅

Goal: any answer can be debugged without re-running it.

- [x] `trace_id` ContextVar end-to-end + structured stage logs
      (`auth → retrieve → rerank → graph → tool → answer →
      complete`). PR #67.
- [x] `JAMES_TRACE_STDOUT` console mirror (default ON for the
      single-user operator workflow). PRs #71 / #75.
- [x] `GET /admin/trace/{trace_id}` full pipeline replay. PR #82.
- [x] Per-stage `p50 / p90 / p99 / max` latency histograms in
      `GET /admin/metrics?window_hours=24`. PR #83.
- [x] 7-day auto-prune (`JAMES_TRACE_RETENTION_DAYS` env, default 7).
      PR #84.

**Done when**: ✅ a hallucination report can be diagnosed by trace_id alone.

### Axis 4 — Security Boundary (P1) ✅

Goal: policy is a layer, not a sprinkle.

- [x] `core/policy_engine.py` — single point of role/sensitivity
      decisions. Wired into retrieval / graph / output / tools.
      10 PRs (#50, #53, #54, #56, #57, #58, #59, #60, #61, #63).
- [x] Capability tokens for tool access (no direct fs path strings).
      PRs #57 / #58 / #59.
- [x] Multimodal inputs flagged + quarantined before joining LLM
      context. PRs #60 / #61 / #63.
- [x] Risky-coding hard-refuse policy at `pre_check`. PR #70.
- [ ] External red-team pass on prompt injection — deferred to v0.4
      (per ROADMAP — needs an external partner, not internal work).

**Done when**: ✅ removing the policy engine breaks 6+ modules.

### Axis 5 — Controlled Evolution (P1) ✅

Goal: self-evolution cannot deploy without a human.

- [x] Opt-in env flag `JAMES_ENABLE_EVOLUTION=0` (default off) +
      `JAMES_AUTO_APPROVE` safety check (refuses to start without
      `JAMES_DEV_MODE`). PR #69.
- [x] feedback → candidate → eval → **human approval** → deploy →
      rollback pipeline.
- [x] Eval gate via `scripts/bench.py --check` subprocess on every
      `/admin/patch/approve` deploy. PR #77.
- [x] Audit log records `approver_username` / `approver_role` /
      `approved_at` / `approval_method` / `before_metrics` /
      `after_metrics`. Lifecycle JSONL `james_patch_log.jsonl`.
      PRs #69 / #77.
- [x] Auto-rollback on bench regression + lifecycle log records the
      `ROLLED_BACK` event. Tested for byte-identical recovery
      under simulated mid-write crash. PR #78.
- [x] `GET /admin/patch/audit?since=&approver=&outcome=&limit=`
      operator-facing query endpoint. PR #79.

**Done when**: ✅ any deployed patch has an `approver_username` field
in the audit DB, and deploy without it is rejected.

### Axis 6 — Real-Data Validation (carries forward from v0.1) 🟡

Goal: numbers from real data, not just synthetic.

- [x] Wiki corpus to 161 entities (concept 62 / org 57 / person 11
      / document 31, hard-deduped via PR #28).
- [x] STEP 7 13-query suite includes negative / dedup / lang-mix /
      security / meta categories.
- [x] Multimodal pipeline integration (image / video / audio,
      OCR-poison quarantine). PRs #60 / #61 / #63.
- [x] Edge case discovery: #5 / #6 / #7 / #8 / #11 / #14 / #20
      all closed via real-data feedback loops.
- [ ] **Second-user end-to-end bench run**: pending. This is the
      v0.2 → v0.3 gate; not a code task but a recruitment task.

### Known cuts from earlier v0.2 plan

The following moved to v0.3 to keep v0.2 focused:

- Self-evolution end-to-end demonstration → folded into Axis 5
- Performance profiling → after Axis 1 (premature otherwise)
- Tutorial documentation → after Axis 1 stabilizes

### Deferred follow-ups (recheck before v0.3)

- **Change Request primitive — generalise the approver_username
  pattern. ✅ v0.2.x landed (CR-A~D); CR-E moved to v0.3.**
  v0.1 hard-coded approver tracking for self-evolution alone
  (Axis 5). Every other write — wiki edits, workspace job runs,
  ontology patches, config saves — landed with no proposal, no
  review, no diff, no rollback. v0.2.x shipped `core/change_request.py`
  + `core/change_request_apply.py` + 6 endpoints + workspace UI +
  two target types (`wiki_entity` PR #243, `run_jobs` PR #240).
  Spans Axis 4 (security boundary generalisation) + Axis 5
  (controlled write authorisation generalised beyond self-evolution).
  - Trust zone documented in `docs/ARCHITECTURE.md §5.6`.
  - Cycle plan + frozen schema + invariants in
    `docs/handovers/v0.2.x-cr-track.md`.
  - Deliberately closed enum for `target_type` — the registration
    API surface is the v0.3 plugin contract.
  - Multi-approver, team / project / department, external
    notification routing → all deferred to v0.3.
  - Self-evolution gate wrap (CR-E) **descoped from v0.2.x**
    (4 locked JSONL-shape test files + eval-gate + rollback chain
    too large for the cycle without regression risk). Moved to v0.3
    deliverables — see v0.3 "Change Request — finish the primitive".
  - Done-when (full): every audit row carrying an `approver_username`
    today goes through `core/change_request.py` — achieved for
    `wiki_entity` / `run_jobs`; self-evolution approvers still
    bypass until CR-E.

- **Audit Phase 4b-2 — remove 16 JSONL writer sites.** The
  JSONL → SQLite migration completed every reader path
  (PRs #206 / #207 / #208 / #210 / #211): the legacy `/admin/audit`
  endpoint, `/admin/dashboard`, `/code/surface/` all query
  `audit_log` directly, and the new `/admin/audit/list` categories
  (`tools` / `attack` / `system`) surface the mirrored rows in the
  admin UI. **JSONL writers remain in place** as a belt-and-suspenders
  safety net because `core/audit_bridge.mirror_to_audit_db` is
  best-effort (`try/except`), so a silent SQLite write failure would
  otherwise be unrecoverable.
  - Re-entry criteria: 2–4 weeks of production use with no
    SQLite mirror gaps observed (compare `audit_log` row count
    vs JSONL line count weekly), then drop the writers.
  - Alternative if mirror reliability is uncertain: gate JSONL
    writers behind an env var (`JAMES_AUDIT_JSONL=1`, default off)
    before deletion.
  - Touch points: `core/security_layer.log_attack` + `log_system_event`;
    9 module-local `_log_system` copies (llm/router, gemma_client,
    graph_engine, query_expander, orchestrator, retrieval_engine,
    memory/loom, memory/trust, reasoning/engine); 5 tool writers
    (tools/router, tools/code/{sandbox,code_reader,code_analyzer,
    code_editor}).

---

## v0.3.0 — Platform Skeleton (~6 months after v0.2)

**Theme**: define and freeze the extension contract that all future
domain packs will be built against.

**Required for**: any domain pack work (forbidden until this gate passes).

### Plugin contract — the v0.3 core

- [ ] `core/plugins/base.py` — typed interfaces for 4 plugin types:
  - `OntologyPack` (entity types, relations, hierarchies)
  - `PromptPack` (system prompts, few-shot examples per task)
  - `UIPanel` (server-rendered admin/user widgets)
  - `Scorer` (custom retrieval/answer scoring overrides)
- [ ] `core/plugins/loader.py` — `JAMES_PLUGINS=general,reference`
      env-driven dynamic loader; signed manifest; SemVer enforcement
- [ ] `core/plugins/manifest.py` — `pack.yaml` schema with `license:`
      field (SPDX, allowed values `MIT` / `Apache-2.0` / `AGPL-3.0` /
      `proprietary` — `proprietary` warns at load time, full validation
      activates only on future license-transition trigger; see
      [`docs/LICENSE_PLAN.md §5.2`](docs/LICENSE_PLAN.md))
- [ ] `packs/general/` — JAMES's default behavior extracted as a
      pack (dogfood gate: removing it disables JAMES; swapping changes
      domain)
- [ ] `docs/PLUGIN_AUTHORING.md` — author guide
- [ ] `JAMES_WORKSPACE=` env var for multi-instance hosting (same
      code, different data root)
- [ ] SemVer + 12-month deprecation policy committed to
      `docs/VERSIONING.md`
- [ ] Eval contract: every pack passes RAGAS + STEP-N before merge

### Change Request — finish the primitive

- [ ] **CR-E**: route self-evolution approvals
      (`/admin/patch/approve`, `/admin/proposals/{id}/approve|reject`)
      through `core/change_request.py` as a shadow row so the unified
      audit shape becomes part of the platform contract. Deferred from
      v0.2.x; high regression risk (4 locked JSONL-shape test files +
      eval-gate + rollback chain), so paired with the plugin contract
      where the contract surface changes anyway.
      Scoping note: `docs/handovers/v0.2.x-cr-track.md §5`.
- [ ] (Stretch) Open the `target_type` registration API to plugins —
      today it's a closed enum on purpose; this is the surface every
      plugin pack will hook through.

### Knowledge cascade — relation provenance

- [ ] Replace the v0.2 single-`confidence` field with `sources:
      [{doc_id, weight, role, ts}]` so file delete/modify can
      surgically update only the affected derived knowledge without
      losing other docs' contributions. 5-phase plan (A schema → B
      ingestion → C delete → D modify → E graph editor) in
      [`docs/design/v0.3-knowledge-cascade.md`](docs/design/v0.3-knowledge-cascade.md).
      Phase A is reversible; Phase E ships behind `JAMES_GRAPH_EDIT=1`.
      May slip to v0.3.x patch — calibrate expectations.

### Governance — license / CLA / monitoring

- [x] License decision for v0.3: **MIT held**. Trigger conditions
      (T1–T5), conversion procedure, and pre-built infrastructure
      (CLA §4-bis relicensing grant, plugin `license:` field,
      trademark + patent tracks) committed to
      [`docs/LICENSE_PLAN.md`](docs/LICENSE_PLAN.md) (2026-05-11).
- [ ] CLA Assistant install + `docs/legal/CLA.md` + `.github/workflows/cla.yml`
      — external contributors can sign before opening their first PR
      with the relicensing grant in place. Full track in
      [`docs/handovers/session-2026-05-09-license-infrastructure.md`](docs/handovers/session-2026-05-09-license-infrastructure.md) Track B.
- [ ] `THIRD_PARTY_LICENSES.md` (dependency inventory; license-strength
      independent)
- [ ] Quarterly trigger monitoring — first measurement recorded at the
      v0.3 release in `docs/LICENSE_PLAN.md §8`
- [ ] Trademark + patent tracks opened (lawyer consult scheduled,
      progress logged in `docs/LICENSE_PLAN.md §6 / §7`)

### Carryover follow-ups (from v0.2.x)

- [ ] **`core/memory/store.py` split** — 21 KB, 1 KB over the
      CLAUDE.md rule #5 module-size gate. Split along algorithm
      boundaries when blast radius is small. Tracked from
      `docs/handovers/v0.2.0-platform-track.md §3 P3`.
- [ ] **Audit Phase 4b-2 — remove 16 JSONL writer sites.** Re-entry
      after 2–4 weeks of production mirror-reliability monitoring;
      gating + alternative described in §"Deferred follow-ups" below.

### Done when

- A new contributor can build a no-op pack from `docs/PLUGIN_AUTHORING.md`
  alone in < 1 day, load it, and observe its effect.
- The dogfood test passes: `packs/general/` produces byte-identical
  STEP 7 results to v0.2 main; deleting the pack breaks the server
  cleanly with a clear "no pack loaded" error.
- Every self-evolution approval row has a paired Change Request row
  (CR-E acceptance).
- CLA Assistant blocks any unsigned external PR at the workflow gate.

### Out of scope (deferred to v0.4)

- Any domain-specific pack (legal, food, retail)
- External plugin marketplace
- Plugin signing infrastructure beyond manifest hash
- Multi-approver workflows / team-project-department scoping on CR
  (still v0.3 plugin contract surface; ships only if a real second
  user needs it)

---

## v0.4.0 — First Domain Pilot (~6 months after v0.3)

**Theme**: prove the platform contract by running ONE real domain
in production for 6 months with one external customer.

**Required for**: a second domain pack (forbidden until this gate passes).

### Deliverables

- [ ] **One** domain pack chosen from informal candidates
      (likely `packs/legal/` or `packs/food/`)
      — selection criteria: signed PoC interest + clear legal
      liability boundary
- [ ] Customer onboarding playbook (`docs/CUSTOMER_ONBOARDING.md`)
- [ ] External red-team pass on prompt injection
      (replaces pattern-only defense with ML guard + patterns)
- [ ] Public eval results in `eval/RESULTS.md` (mother + first pack)
- [ ] 6-month no-core-regression production track record

### Done when

- One paying or formal-PoC customer has run the deployment for
  6 months with no core code change attributable to their domain
  needs (only pack-level changes).

### Out of scope

- A second domain pack
- Vertical Product packaging
- Public marketplace

---

## v1.0.0 — Production-Grade Mother (~6 months after v0.4)

**Theme**: make domain branching safe for outsiders. After this gate,
external developers can publish their own packs.

### Deliverables

- [ ] HTTPS / SSO / SAML / LDAP — production defaults
- [ ] Multi-tenancy (per-tenant data isolation, per-tenant pack
      selection, quota management)
- [ ] SOC 2 or ISO 27001 readiness assessment
- [ ] Backup / restore / rollback CLI tested under simulated failure
- [ ] Prometheus + OpenTelemetry exporters
- [ ] Public SDK and plugin author guide finalized
- [ ] Bus factor ≥ 2 (one non-maintainer with full commit/review history)
- [ ] Annual external red-team schedule established

### Done when

- A third party (not a customer) builds and publishes a pack against
  the v1.0 SDK without contacting maintainers.
- The platform survives a single-maintainer 30-day absence with no
  customer-visible regressions.

### Out of scope

- Vertical Products (separate business decision per domain after v1.0)
- Federation across multiple JAMES instances (Beyond v1.0 section)

---

## Beyond v1.0 — Speculative

After v1.0, growth is by domain accumulation, not core feature
addition. See `docs/PLATFORM_READINESS.md` §4 for the three branching
forms (Pack / Distribution / Vertical Product) and selection criteria.

Long-considered, no commitment:

- **Optional Neo4j backend** — migrate from markdown wiki to graph DB,
  Cypher query support, backward compatibility with markdown
  (was tentatively v0.3; reframed as post-v1.0 optimization)
- **Multi-agent system** — specialist agents (researcher, coder,
  security), agent-to-agent communication, task decomposition
  (was tentatively v0.3; reframed as post-v1.0 capability)
- **OpenAI-compatible API** for drop-in replacement
- **Streaming responses + Webhook support**
- **Federation**: connect multiple JAMES instances
- **On-device fine-tuning**: LoRA adapters per user
- **Edge deployment**: smaller models for embedded use
- **Plugin marketplace**: community-contributed packs
- **Visual graph editor**: web UI for ontology editing
- **Voice interface**: ASR + TTS pipeline

---

## How to Influence the Roadmap

- **GitHub Issues**: feature requests, prioritized by upvotes
- **Discussions**: longer-form proposals
- **Pull Requests**: implement what you need

We prioritize based on:
1. Security-critical fixes (immediate)
2. Real-data feedback from users
3. Strategic alignment with the project's direction
4. Community contribution (volunteer-friendly tasks first)

Domain-specific feature requests during v0.2 — v0.4 are out of scope.
See `docs/handovers/v0.2.1-business-track.md` §3 for the rationale
and the "no parallel domains" rule.

---

## Versioning

We follow [Semantic Versioning](https://semver.org/):

- `MAJOR.MINOR.PATCH-PRERELEASE`
- `0.x.y` versions may contain breaking changes
- `1.0.0` and beyond will follow strict semver
- After v1.0 ships, plugin API gets its own SemVer track with a
  12-month deprecation guarantee (see `docs/PLATFORM_READINESS.md`
  Gate v0.3 criteria)

---

**Last updated**: 2026-05-13 — post-v0.2.x Change Request cycle.
Six axes engineering-complete; Axis 6 second-user gate in self-feedback
+ recruitment phase. v0.2.x added the Change Request primitive
(`core/change_request.py` + `wiki_entity` + `run_jobs` apply paths)
and closed dependabot 6 high-severity alerts. v0.3 prep tracks
(license / CLA / plugin contract) and the CR-E self-evolution wrap
moved into the v0.3 deliverables above. Open issues: 0.
