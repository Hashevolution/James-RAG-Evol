# Roadmap

> **Note**: This roadmap describes intended directions, not commitments.
> Priorities will shift based on user feedback and real-world testing.

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

## v0.3.0 — Multi-Agent + Graph DB (~6 months)

**Theme**: Scale beyond single-user, optional graph DB backend.

### Priorities

- **Optional Neo4j backend**
  - Migrate from markdown wiki to graph DB
  - Cypher query support
  - Backward compatibility with markdown

- **Multi-agent system**
  - Specialist agents (researcher, coder, security)
  - Agent-to-agent communication
  - Task decomposition + delegation

- **Better evaluation**
  - Automated benchmarking
  - Comparison with other RAG systems
  - Domain-specific accuracy tests

- **API improvements**
  - OpenAI-compatible API for drop-in replacement
  - Streaming responses
  - Webhook support

---

## v1.0.0 — Production Hardening (~12 months)

**Theme**: Enterprise-ready features.

### Priorities

- **Multi-tenancy**
  - Per-tenant data isolation
  - Per-tenant model selection
  - Quota management

- **HTTPS + Production deployment**
  - Default TLS configuration
  - Docker deployment guide
  - Kubernetes Helm charts

- **Compliance preparation**
  - GDPR data deletion support
  - SOC 2 audit log requirements
  - Data residency options

- **Advanced security**
  - Rate limit per role / per endpoint
  - Anomaly detection on audit log
  - Optional 2FA

- **Operational tooling**
  - Backup / restore CLI
  - Migration scripts
  - Health check endpoint
  - Prometheus metrics

---

## Beyond v1.0 — Speculative

Things being considered, no commitment:

- **Federation**: connect multiple JAMES instances
- **On-device fine-tuning**: LoRA adapters per user
- **Edge deployment**: smaller models for embedded use
- **Plugin marketplace**: community-contributed tools
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

---

## Versioning

We follow [Semantic Versioning](https://semver.org/):

- `MAJOR.MINOR.PATCH-PRERELEASE`
- `0.x.y` versions may contain breaking changes
- `1.0.0` and beyond will follow strict semver

---

**Last updated**: v0.2.0-dev (foundation hardening plan)
