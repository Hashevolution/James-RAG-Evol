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

## v0.2.0 — Foundation Hardening (next, ~3-4 months)

**Theme**: Make the v0.1 capabilities trustworthy enough to recommend
to a second user. Six axes, all of them P0/P1.

### Axis 1 — Architecture Separation (P0)

Goal: no single file owns more than one responsibility.

- [ ] Split `core/reasoning_engine.py` (50 KB) into:
      `pipeline.py` (loop), `answer.py` (generation),
      `parsing.py` (JSON/citation extraction)
- [ ] Consolidate `memory_*` (5 files, ~70 KB) into
      `core/memory/` package with documented public API
- [ ] Move `tools/self/` behind a sub-process boundary
      (no in-proc access to core modules)
- [ ] Public typed interfaces for: `Retriever`, `GraphEngine`,
      `PolicyEngine`, `Reasoner`, `OutputFilter`

**Done when**: `import` graph is acyclic and each module has < 20 KB.

### Axis 2 — Evaluation Harness (P0)

Goal: every change is measured against the same yardsticks.

- [ ] Lock STEP 7 12-query suite as committed regression baseline
      (currently runs locally only)
- [ ] Integrate **RAGAS** for retrieval / faithfulness / answer relevance
- [ ] Adopt a **LegalBench** subset for domain stress test
      (replaces vague "legal-style" prompts)
- [ ] Add `scripts/bench.py` that runs all three on every PR locally
- [ ] Publish numbers in PR descriptions for any change touching
      `core/retrieval_engine.py`, `core/graph_engine.py`,
      `core/reasoning_engine.py`

**Done when**: a PR cannot land without bench numbers attached.

### Axis 3 — Observability / Tracing (P1)

Goal: any answer can be debugged without re-running it.

- [ ] OpenTelemetry-style `trace_id` end-to-end
- [ ] Structured stage logs:
      `query → retrieve → rerank → graph → tool → answer`
- [ ] `GET /admin/trace/{id}` returns full pipeline replay
- [ ] Per-stage latency histograms in `/admin/metrics`

**Done when**: a hallucination report can be diagnosed by trace_id alone.

### Axis 4 — Security Boundary (P1)

Goal: policy is a layer, not a sprinkle.

- [ ] Extract `core/policy_engine.py` — single point of role/sensitivity
      decisions, called by retrieval / graph / output / tools
- [ ] Capability tokens for tool access (no direct fs path strings)
- [ ] Multimodal inputs (image/audio/web) flagged and quarantined
      before joining the LLM context
- [ ] External red-team pass on prompt injection (replace pattern-only
      defense with ML guard + patterns)

**Done when**: removing the policy engine breaks at least 4 modules
(meaning every consumer is wired through it).

### Axis 5 — Controlled Evolution (P1)

Goal: self-evolution cannot deploy without a human.

- [ ] Wire opt-in env flag `JAMES_ENABLE_EVOLUTION=0` (default off)
- [ ] feedback → candidate → eval → **approval (human)** → deploy → rollback
- [ ] Eval gate uses the Axis 2 harness — no bypass
- [ ] Audit log records approver, timestamp, before/after metrics

**Done when**: any patch deployed has an `approved_by` field in the
audit DB, and deploy without it is rejected.

### Axis 6 — Real-Data Validation (carries forward from v0.1)

Goal: numbers from real data, not just synthetic.

- [ ] 30+ real entities across diverse domains (carries from v0.1)
- [ ] User-tested query patterns (carries from v0.1)
- [ ] Multimodal pipeline integration completion
- [ ] Edge case discovery and fixing

**Done when**: a second user (not the maintainer) can run the bench
suite on their own corpus end-to-end without intervention.

### Known cuts from earlier v0.2 plan

The following moved to v0.3 to keep v0.2 focused:

- Self-evolution end-to-end demonstration → folded into Axis 5
- Performance profiling → after Axis 1 (premature otherwise)
- Tutorial documentation → after Axis 1 stabilizes

---

## v0.3.0 — Platform Skeleton (~6 months after v0.2)

**Theme**: define and freeze the extension contract that all future
domain packs will be built against.

**Required for**: any domain pack work (forbidden until this gate passes).

### Deliverables

- [ ] `core/plugins/base.py` — typed interfaces for 4 plugin types:
  - `OntologyPack` (entity types, relations, hierarchies)
  - `PromptPack` (system prompts, few-shot examples per task)
  - `UIPanel` (server-rendered admin/user widgets)
  - `Scorer` (custom retrieval/answer scoring overrides)
- [ ] `core/plugins/loader.py` — `JAMES_PLUGINS=general,reference`
      env-driven dynamic loader; signed manifest; SemVer enforcement
- [ ] `packs/general/` — JAMES's default behavior extracted as a
      pack (dogfood gate: removing it disables JAMES; swapping changes
      domain)
- [ ] `docs/PLUGIN_AUTHORING.md` — author guide
- [ ] `JAMES_WORKSPACE=` env var for multi-instance hosting (same
      code, different data root)
- [ ] SemVer + 12-month deprecation policy committed to
      `docs/VERSIONING.md`
- [ ] Eval contract: every pack passes RAGAS + STEP-N before merge

### Done when

- A new contributor can build a no-op pack from `docs/PLUGIN_AUTHORING.md`
  alone in < 1 day, load it, and observe its effect.
- The dogfood test passes: `packs/general/` produces byte-identical
  STEP 7 results to v0.2 main; deleting the pack breaks the server
  cleanly with a clear "no pack loaded" error.

### Out of scope (deferred to v0.4)

- Any domain-specific pack (legal, food, retail)
- External plugin marketplace
- Plugin signing infrastructure beyond manifest hash

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

**Last updated**: v0.2.1 (platform readiness gates added)
