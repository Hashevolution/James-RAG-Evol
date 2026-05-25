# Roadmap

> **Note**: This roadmap describes intended directions, not commitments.
> Priorities will shift based on user feedback and real-world testing.

For the underlying readiness framework (6 dimensions, gate criteria,
branching forms), see [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md).

---

## v0.1.0 — Foundation (released, foundational)

**Status**: Released (2026, initial alpha)

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

## v0.2.0 — Foundation Hardening (released 2026-05-08, closed 2026-05-13)

**Theme**: Make the v0.1 capabilities trustworthy enough to recommend
to a second user. Six axes, all of them P0/P1. **All six axes complete.**
Axis 6 (second-user gate) closed on 2026-05-13 with the user secured —
v0.2 → v0.3 gate clear, project formally entering v0.3 Platform Skeleton.

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

### Axis 6 — Real-Data Validation (carries forward from v0.1) ✅

Goal: numbers from real data, not just synthetic.

- [x] Wiki corpus to 161 entities (concept 62 / org 57 / person 11
      / document 31, hard-deduped via PR #28).
- [x] STEP 7 13-query suite includes negative / dedup / lang-mix /
      security / meta categories.
- [x] Multimodal pipeline integration (image / video / audio,
      OCR-poison quarantine). PRs #60 / #61 / #63.
- [x] Edge case discovery: #5 / #6 / #7 / #8 / #11 / #14 / #20
      all closed via real-data feedback loops.
- [x] **Second-user end-to-end bench run**: secured (2026-05-13).
      v0.2 → v0.3 gate clear.

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

## v0.3.0 — Platform Skeleton (current cycle, entered 2026-05-13)

**Theme**: define and freeze the extension contract that all future
domain packs will be built against.

**Required for**: any domain pack work (forbidden until this gate passes).

### Plugin contract — the v0.3 core

- [x] `core/plugins/base.py` — typed interfaces for 4 plugin types
      (✅ PR #344, Track C PR-C2):
  - `OntologyPack` (entity types, relations, hierarchies)
  - `PromptPack` (system prompts, few-shot examples per task)
  - `UIPanel` (server-rendered admin/user widgets)
  - `Scorer` (custom retrieval/answer scoring overrides)
- [x] `core/plugins/loader.py` — `JAMES_PACKS=general,reference`
      env-driven dynamic loader; SemVer enforcement (✅ PR-C3 #409).
      Coexists with the pre-existing reasoning-backend plugin loader
      at `core/reasoning/backends/_load_plugins` (PR #326); the two
      use separate env vars (`JAMES_PACKS` vs `JAMES_PLUGINS`) per
      design memo Option A
- [x] `core/plugins/manifest.py` — `pack.yaml` schema with closed
      `license:` enum (✅ PR-C3 #409)
- [x] `core/plugins/registry.py` — slot registry per Protocol type
      (✅ PR-C3 #409)
- [x] **`packs/general/`** — first first-party pack as **no-op
      overlay** dogfood (✅ PR-C5a #413). Skeleton only:
      `GeneralOntology` + `GeneralPrompts` satisfy the Protocols with
      empty values; existing JAMES defaults in
      `core/relations_schema.py` + `core/reasoning/modes/` remain
      authoritative. Server startup wiring shipped in **PR-C5b #418**
      (2026-05-23) — the loader now runs at FastAPI startup and the
      pack registers into the process-wide registry.
- [x] `JAMES_WORKSPACE=` env var for multi-instance hosting
      (✅ PR-C6 #410 — resolver only; ✅ PR-C6.b #421, 2026-05-23 —
      `config.py` consumes the resolver for `RAW_DIR` / `WIKI_DIR` /
      `UPLOAD_DIR` / `CHROMA_DIR`; default unset behavior is
      byte-identical to pre-v0.3)
- [x] `docs/PLUGIN_AUTHORING.md` — author guide (✅ PR-C7 #412)
- [x] `docs/VERSIONING.md` — SemVer + 12-month deprecation policy
      (✅ PR-C8 #411)
- [x] Eval contract — every pack passes static manifest + slot-import
      + ruff via `scripts/eval_pack.py`, enforced by the
      `.github/workflows/packs-eval.yml` CI gate
      (✅ PR-C9 #419, 2026-05-23). Heavyweight RAGAS layer reserved
      as a follow-up step in the same workflow.
- [x] `scripts/dogfood_check.py` + CI hook — runtime check of the 4
      end-to-end contract invariants of the dogfood gate (default
      loads `packs/general/`; `JAMES_PACKS=''` refused; missing pack
      refused; path-traversal refused) (✅ PR-C10 #420, 2026-05-23).

→ **Plugin API status: 8/8 PRs landed (100%)** as of 2026-05-24
post-PR-C10/C6.b. The eight-PR sequence (PR-C2 / C3 / C5a / C5b / C6 /
C6.b / C7 / C8 / C9 / C10) closed in the 2026-05-22~24 window. Full
breakdown: `docs/handovers/v0.3.x-audit-2026-05-23.md`.

→ **All other v0.3 gate items closed in the 2026-05-24 marathon
session**: CR-E shadow rows via Stage B 4-PR sequence (#433/#434/
#435/#436), module size violations via Stage C 5-PR sequence
(#427/#428/#429/#431/#432), Audit Phase 4b-2 JSONL-writer removal
via Stage D.1 (#430).

### Change Request — finish the primitive

- [x] **CR-A~D** completed v0.2.x — scoping (CR-A), state machine +
      apply dispatcher + wiki_entity (CR-B, PRs #237/#243), workspace
      UI panel (CR-C, PR #239), run_jobs apply path (CR-D, PR #240).
- [x] **CR-E**: route self-evolution approvals
      (`/admin/patch/approve`, `/admin/proposals/{id}/approve|reject`)
      through `core/change_request.py` as a shadow row so the unified
      audit shape becomes part of the platform contract.
      **✅ Stage B 4-PR sequence complete 2026-05-24**:
      - CR-E.1 (#433) — target_type enum + no-op apply dispatcher
        (`self_evo_patch` / `self_evo_proposal`)
      - CR-E.2 (#434) — `/admin/patch/approve` shadow write + close
        on bench-pass / apply_failed / regression
      - CR-E.3 (#435) — `/admin/proposals/{id}/approve|reject`
        shadow write + close
      - CR-E.4 (#436) — `/admin/patch/audit` unifies legacy JSONL +
        CR-shadow read via `include_shadow=True` (default ON in the
        endpoint, default OFF in the library function for back-compat)
      Dual-write permanent. Legacy `james_patch_log.jsonl` +
      `james_evo_log.jsonl` remain authoritative for the deploy
      timeline; CR row is additive shadow with a no-op apply handler.
      The 4 locked JSONL-shape tests (`test_self_evolution_gate`,
      `test_evolution_bench_gate`, `test_evolution_rollback`,
      `test_evolution_audit_query`) all stay green.
- [ ] (Stretch) Open the `target_type` registration API to plugins —
      today it's a closed enum on purpose; this is the surface every
      plugin pack will hook through.

### Knowledge cascade — relation provenance

- [x] Replaced the v0.2 single-`confidence` field with `sources:
      [{doc_id, weight, role, ts}]`. **5-phase plan completed**:
      Phase A schema (#266), Phase B ingestion (#269), Phase C delete
      (#270), Phase D modify (#274), Phase E graph editor (#271, #273).
      Two hotfixes for cross-doc aggregation + noisy-OR derivation
      (#349, #350). 12 invariants locked in
      `tests/test_relations_schema.py` +
      `tests/test_phase_b_ingestion_sources.py`. Postmortem:
      `docs/postmortems/2026-05-20-knowledge-cascade-defects.md`.

### Governance — license / CLA / monitoring

- [x] License decision for v0.3: **MIT held**. Trigger conditions
      (T1–T5), conversion procedure, and pre-built infrastructure
      (CLA §4-bis relicensing grant, plugin `license:` field,
      trademark + patent tracks) committed to
      [`docs/LICENSE_PLAN.md`](docs/LICENSE_PLAN.md) (2026-05-11).
- [x] **CLA Assistant install + `docs/legal/CLA.md` +
      `.github/workflows/cla.yml`** — operator window closed
      2026-05-20 (B-3/B-4/B-5/B-6 all verified end-to-end with a
      dry-run from a separate GitHub account). External contributors
      can sign before opening their first PR with the relicensing
      grant in place.
- [x] `THIRD_PARTY_LICENSES.md` (dependency inventory; license-strength
      independent) — ✅ PR #414 (2026-05-23, `idna 3.13 → 3.15`
      security pin refresh; full pip-licenses snapshot at repo root).
      Re-run only on dependency churn.
- [x] Quarterly trigger monitoring — first measurement recorded at the
      v0.3 release in `docs/LICENSE_PLAN.md §8` — ✅ PR #415 (third
      quarterly measurement, 2026-05-23, stars 5→13, triggers 0/5).
- [ ] Trademark + patent tracks opened (lawyer consult scheduled,
      progress logged in `docs/LICENSE_PLAN.md §6 / §7`) — operator
      track

### Carryover follow-ups (from v0.2.x)

- [x] **`core/memory/store.py` split** — was 21 KB at v0.2 close;
      currently ~17 KB on origin/main (`9a756b7`). Reached
      compliance without an explicit split (incidental shrinkage
      from later refactors). No action needed.
- [x] **Audit Phase 4b-2 — remove 16 JSONL writer sites** — ✅
      Stage D.1 (#430, 2026-05-24). 14 files touched, ~158 lines
      removed / 47 added (entry dicts + mirror_* calls retained; only
      the `try: open(JSONL_PATH).write(json.dumps(entry))` blocks +
      orphaned path constants + `import json` removed). SQLite
      `audit_log` table via `core/audit_bridge.py` is now the sole
      sink. `tests/test_router_capability.py` was migrated to the
      `mirror_to_audit_db` capture-via-mock pattern (9/9 pass).

### v0.3-only follow-ups discovered post-design

These items were identified during the v0.3 cycle but are not in the
original design memos:

- [x] **i18n contract invariant** — backend `label_key` pattern across
      7 modules (~316 entries). Convention test in 5 `test_*_i18n.py`
      files. Established by the 2026-05-22 sweep series
      (PRs #393/#394/#395/#396/#397/#398/#400/#404).
- [x] **Reasoning cap defaults** — `DEFAULT_MAX_TOKENS` for
      query_rewriter / planner / reflect / verify bumped from
      200/400/400/400 to 4096 each, above the ~500-token reasoning
      floor measured on `gemma4:e4b` (PR #399 + V3'.a/.b/.c/.d
      4-stage validation set, PR #407).
- [x] **CASCADE vs EVENT separation axiom** — established by PR #401
      (architecture memo). v0.4 first ship bundle rescoped to
      T1+T7+T2 (PR #403).
- [x] **Module size gate violations** discovered by 2026-05-23 audit
      → ✅ Stage C 5-PR sequence complete 2026-05-24. All five files
      now split into mixin/composition packages with every sub-module
      ≤17 KB:
      - C.1 `core/wiki_generator.py` 51 KB → 6-file mixin package
        (max 17 KB) via PR #427
      - C.2 `core/cascade.py` 24 KB → 4-file package (max 12 KB,
        Phase C delete + Phase D modify + shared helpers) via PR #428
      - C.3 `core/character_profile.py` 24 KB → 4-file mixin package
        (max 11 KB) via PR #429
      - C.4 `core/security_layer.py` 23 KB → 5-file package (max
        7.2 KB; landed after Stage D.1's JSONL removal shrunk the
        file ~50 lines first) via PR #431
      - C.5 `core/graph_editor.py` 20 KB → 3-file package (max
        11 KB, edge mutation writes / helpers / facade) via PR #432
      Pure refactor — no signatures, return shapes, or behaviour
      changed. PLATFORM_READINESS Gate v0.3 dimension A fully clear.
- [ ] **admin.html → 3-page split** — inventory completed (PR #385);
      actual split (Option-A Phase 3) deferred. Operator decision
      whether to land before v0.4 entry or run as v0.3.x parallel.

### Measurement framework track (V3' series, 2026-05-22~ open)

The V3'.a/.b/.c/.d (4-stage cap-budget validation, PR #407) + V3'.e
(substitution/synthesis mode split, PR #440) sweeps together
established a reproducible 3-axis measurement framework for LLM
cost behavior. Robin Converse's 2026-05-23 same-day cross-stack
replication (issue #448, repo
[triavalabs/gemma4-26b-mode-split](https://github.com/triavalabs/gemma4-26b-mode-split))
adopted the JAMES JSON schema as the cross-stack analysis template
— graduating the framework from "data we publish" to "schema
another lab analyses against".

**Three confirmed axes**:

1. **Mode split** (substitution = deterministic / synthesis =
   variable). Robin original + JAMES e4b + Robin 26b — confirmed
   on both stacks.
2. **Workload gradient** (heavy / light / no synthesis cost
   scales with task weight). JAMES V3'.e + V3'.a~d — confirmed
   on e4b.
3. **Model-scale efficiency** (synthesis cost ∝ 1/param-count;
   substitution invariant). Robin 26b 2026-05-23 — new axis,
   single point so far.

Six follow-up directions queued for v0.3.x cycle (none are domain
features; all are platform-skeleton strengthening or research):

- [x] **Direction 4 — Substitution bypass verification on e4b**
      (1-day, JAMES standalone). Patch `v3prime_e_mode_split.py`
      to record `unique_response_count` per cell; verify Robin's
      Finding 1 ("mode bypasses sampling layer") on our e4b data.
      If `unique=1` confirmed → publishable mechanism axis 1
      strengthened.
- [x] **Direction 1 — Adaptive Budgeting in Cognitive Middleware**
      (closed 2026-05-25). PR #461 (TaskBudget module +
      experiment driver + cognitive-stages extension), PR #463
      (v2 heuristic CAP_LIGHT 800→1200 + closure result docs +
      **7-tier monotonic natural-stop gradient**, 62→1681 tokens,
      27× dynamic range, cross-sweep stable <5% per tier), PR
      #469 (entity_extract cap 1500→4096 alignment). 4 cognitive
      stages all zero truncation + zero quality regression. Ships
      as safe / latency-positive / memory-positive /
      defensive-bound. Sub-finding: `verify` is a high-clustering
      cognitive stage (~12.5% unique across 40 baseline calls) —
      adds task-type axis to Mechanism 2.
- [ ] **Direction 2 — Task-weight metric formalization** —
      absorbed into Direction 5 as a dependent fragment, not run
      as an independent 1-2 week cycle. The 7-tier natural-stop
      gradient from Direction 1 closure provides the ground-truth
      dataset. Per [Build-don't-broadcast principle](docs/handovers/v0.3.x-measurement-framework-track.md):
      research-only directions are run on collaborator cadence;
      D2 in isolation is collaborator-coupled but the *piece D5
      needs* is product work and lands inside D5.
- [x] **Direction 6(J) — Methodology spec standalone** (closed
      2026-05-24, PR #457). `docs/research/v3prime-protocol-v1.md`
      shipped: 441 lines, 12 sections + KO, JSON schema frozen
      v1, 12-month grace policy, BibTeX (author=Hashevolution),
      §11 external adopter table (JAMES + Triava Labs). Other
      labs can cite the protocol without depending on JAMES code.
- [ ] **Direction 5 — Auto-routing on Provider Contract** —
      🔵 **next big cycle (queued for 2026-05-26~)**. New
      `core/reasoning/router.py` consumes Direction 1's budget to
      select backend (e4b for substitution / light, 26b or cloud
      for heavy synthesis). Provider Contract surface unchanged.
      Cross-lingual RAG option 3 (wiki entity `aliases:` +
      entity_extract resolve, follow-up to PR #472's keyword
      `_SYNONYM_MAP`) bundled in this cycle while retrieval
      contract is being touched.
- [ ] **Direction 3 — Cross-family generalization** (~2-3 weeks,
      research). V3'.e on Llama 3.1 / Qwen 2.5 / DeepSeek v2 via
      Ollama. Output: mode-split universality vs Gemma-only
      judgment. Result first-shared with Robin (axis-1 owner) per
      collaborator informational-notice pattern.
- [ ] **Direction 6(I) — Joint paper consolidation** (Track 5
      essential). Three-author byline (Ali / Robin / Hashevolution)
      after Directions 1-5 produce input. Track 4 scope-lock note
      applied.

**Collaborator interaction pattern**: Track 1 success pattern
(land first + "no action needed" DM) applies to all directions
except 6(I) joint paper. Direction 3 result first-shared to
Robin; Direction 5 design preview shared to Ali; otherwise
informational notice on PR landing.

**v0.4 / v0.5 alignment**: Direction 1 (adaptive budgeting) +
Direction 5 (auto-routing) integrate naturally with v0.4 Layer 4
GOVERNANCE/EVENT tracks (budget decisions = audit trail; routing
decisions = events). Direction 5 also strengthens v0.5 Domain
Pilot value proposition (domain pack-aware model routing).
Detailed handover: `docs/handovers/v0.3.x-measurement-framework-track.md`.

### Done when

| Criterion | Status |
|---|---|
| A new contributor can build a no-op pack from `docs/PLUGIN_AUTHORING.md` alone in < 1 day, load it, and observe its effect | ⚠️ — PLUGIN_AUTHORING.md exists (#412); end-to-end author run not yet validated. Awaits first external pack author. |
| The dogfood test passes: `packs/general/` produces byte-identical STEP 7 results to v0.2 main; deleting the pack breaks the server cleanly | ✅ — `packs/general/` registers at startup via PR-C5b (#418); `scripts/dogfood_check.py` (PR-C10 #420) locks the four runtime invariants (default loads general; empty `JAMES_PACKS` refused; missing pack refused; path-traversal refused) on every PR via `.github/workflows/packs-eval.yml`. Byte-identity is preserved because the overlay is empty. |
| Every self-evolution approval row has a paired Change Request row (CR-E acceptance) | ✅ — Stage B 4-PR sequence complete. PR #433 (target enum + no-op apply), PR #434 (`/admin/patch/approve` shadow write), PR #435 (`/admin/proposals/{id}/approve|reject` shadow write), PR #436 (`/admin/patch/audit` unified read via `include_shadow=True`). Dual-write: legacy JSONL stays authoritative, CR table is additive shadow. All 4 locked tests green. |
| CLA Assistant blocks any unsigned external PR at the workflow gate | ✅ — verified end-to-end 2026-05-20 |

→ **3/4 fully satisfied + 1/4 partially satisfied as of 2026-05-24
(post-Stage-B/C/D marathon session).** Only remaining partial:
first external author trial against `PLUGIN_AUTHORING.md`
(infrastructure complete; awaits Ali's mid-June Gemini backend PR
as the first external trial). See
`docs/handovers/v0.3.x-audit-2026-05-23.md` for the staged plan and
the post-marathon reconciliation table.

### Out of scope (deferred to v0.4)

- Any domain-specific pack (legal, food, retail)
- External plugin marketplace
- Plugin signing infrastructure beyond manifest hash
- Multi-approver workflows / team-project-department scoping on CR
  (still v0.3 plugin contract surface; ships only if a real second
  user needs it)

---

## v0.4.0 — Layer 4 Lifecycle Semantics (~6 months after v0.3)

**Theme**: deepen the memory lifecycle beyond the v0.3 Layer 3
cascade (Memory OS) into Layer 4 — two complementary tracks
**EVENT/TEMPORAL** (semantic evolution) and **GOVERNANCE**
(write-time control), plus a Layer 3 extension for causality.
Seven areas (T1–T7) chosen from the 2026-05-21 user critique
series.

**Core architectural axiom — CASCADE vs EVENT separation**
(`docs/architecture/memory-lifecycle-architecture.md §1.5`):

| Class | Trigger | Handling | Example |
|---|---|---|---|
| **Invalidated** → CASCADE (Layer 3) | Explicit invalidation signal (doc delete, ingestion error, source revoke) | Source removal + propagation + orphan sweep | Mis-uploaded doc / withdrawn report / typo correction |
| **Superseded** → EVENT/TEMPORAL (Layer 4-A) | New doc / time progression / policy change / state transition | Validity window close + supersede chain (past data preserved) | CEO change / policy revision / contract termination |

Many naive RAG/KG systems collapse both into one mechanism
(overwrite/append) → contradiction explosion, stale retrieval,
hallucination increase. v0.4 enforces the separation as a
*test-level invariant* (T7 invariants:
`supersede_does_not_trigger_cascade` /
`cascade_preserves_supersede_chain`).

**Why v0.4 was retargeted from "Domain Pilot"**: the v0.3 cascade
(Phase A–E + 2 hotfixes) revealed that "Layer 3 alone" doesn't
cover real operational governance — stale facts accumulate,
contradicting sources reject silently (Gate 5), manual entries
have no reviewer hierarchy, and event sourcing for arbitrary-time
graph replay is absent. The Domain Pilot moves to v0.5 (it
requires Layer 4 governance to be production-credible anyway).

**Required for**: any v0.5 domain pilot (forbidden until Layer 4
T1+T7+T2 minimum lands and the CASCADE/EVENT separation invariant
is provable).

### Scope — 7 areas across 3 tracks (T1–T7)

| Stage | Area | Track | Goal |
|---|---|---|---|
| **T1** | Temporal Validity & Expiration | **EVENT** | Fact valid window definition + auto-expiration (mark, not delete) |
| **T2** | Deterministic Contradiction Arbitration | **GOVERNANCE → routing** | LLM-free deterministic resolution + A/B classification (CASCADE vs EVENT) |
| **T3** | Evidence Aging & Trust Decay | **EVENT** | Per-source weight decay by domain function |
| **T4** | Reviewer Authority Hierarchy | **GOVERNANCE** | Multi-level manual source governance (analyst / manager / admin) |
| **T5** | Replayable Audit Graph | **EVENT** | Event-sourced reconstruction, arbitrary-time graph replay |
| **T6** | Causality Chain Tracking | **CASCADE extension** | Derived fact base-fact tracking + auto-invalidation propagation |
| **T7** ⭐ | Supersede Chain | **EVENT** | Edge-level `status: {active, superseded_by}`. World change → past preserved + new edge created + chain walk |

Full design: `docs/design/v0.4-lifecycle-semantics-roadmap.md`.
Reference architecture: `docs/architecture/memory-lifecycle-architecture.md`.

### Phase plan

- **v0.4.0** (2026 Q4 ~ 2027 Q1): **T1 + T7 + T2** (EVENT core +
  routing). T1 (validity window) and T7 (supersede chain) ship
  together — separation is meaningless without both. T2's A/B
  routing enforces the separation at write time (misclassification
  becomes immediately testable).
- **v0.4.1** (2027 Q1 ~ Q2): T6 — Causality Chain (CASCADE extension)
- **v0.4.2** (2027 Q2): T3 — Evidence Aging (EVENT)
- **v0.4.3** / **v0.5 prep** (2027 Q3 ~ Q4): T4 + T5 — Reviewer
  Authority + Replayable Audit

### Invariants (extending v0.3's 12 invariants)

- **Existing 12** locked in `tests/test_relations_schema.py` +
  `tests/test_phase_b_ingestion_sources.py` (Layer 3 cascade).
- **New T1–T7 invariants**: ~27 (cumulative 39). Per-stage
  contract test files following the 2026-05-22 i18n sweep
  pattern (`tests/test_*_i18n.py` × 5 already pin label_key
  conventions — same `_contract`-style files for T1–T7).
- **Critical separation invariants** (T7):
  - `test_supersede_does_not_trigger_cascade` — EVENT mutation
    must not call Layer 3 `cascade_remove`
  - `test_cascade_preserves_supersede_chain` — CASCADE invalidation
    must not break `status.superseded_by` links (active history preserved)
  - `test_historical_replay_via_chain` — `reconstruct_view_at(t)`
    accurately reconstructs the graph state at any past time

### Cross-cutting contracts (preserved from v0.3)

- **i18n `label_key`** — every UI-exposed label from new Layer 4
  modules (reviewer_rank, approval_state, contradiction reason,
  aging policy names) must follow the backend label_key contract
  established by the 2026-05-22 sweep across 7 modules. Convention
  test in the corresponding `test_*_i18n.py` blocks silent
  regression.
- **Bench gate (CLAUDE.md rule 2)** — T1 expiration cascade,
  T6 invalidation cascade, and any other change touching
  `core/retrieval` / `core/graph` / `core/reasoning` must paste
  STEP 7 bench numbers in PR body.
- **Module size gate (CLAUDE.md rule 5)** — new
  `core/lifecycle/*.py` files each < 20 KB. Split first if a
  change would push over.

### Done when

- T1 + T7 + T2 (minimum) shipped, with new invariants green and
  STEP 7 baseline no-regression.
- **Separation invariant provable**: write a B-class fact (e.g.,
  `(Joby, CEO, Bob)` arriving after existing `(Joby, CEO, Alice)`)
  → T2 routes to EVENT supersede chain → old Alice edge survives
  with `status.superseded_by` link → CASCADE log shows zero
  `cascade_remove` calls for this mutation.
- Operator scenario A (CASCADE): a withdrawn report uploaded
  earlier is deleted via admin UI; its sourced facts cleanly
  vanish or recompute confidence — supersede chains for unrelated
  edges remain intact.
- Operator scenario B (EVENT): a 분기 보고서 uploaded with
  `valid_until` expires automatically; its edge is *marked*
  `status.active = false` not deleted, and historical replay at
  the prior date still returns it.
- Reference architecture memo + 7-area design memo published
  (`docs/architecture/memory-lifecycle-architecture.md` +
  `docs/design/v0.4-lifecycle-semantics-roadmap.md`).

### Out of scope (deferred to v0.5)

- Any domain pack (legal / food / retail) — moved to v0.5
- External customer onboarding playbook
- Public eval results in `eval/RESULTS.md`
- 6-month production track record

---

## v0.5.0 — First Domain Pilot (~6 months after v0.4)

**Theme**: prove the platform contract by running ONE real domain
in production for 6 months with one external customer. **Moved here
from v0.4** so Layer 4 governance lands first — see v0.4 retarget
rationale above.

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

## v1.0.0 — Production-Grade Mother (~6 months after v0.5)

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

**Last updated**: 2026-05-22 — **v0.4 retarget to Layer 4
Lifecycle Semantics + CASCADE/EVENT 분리 axiom 채택**. v0.3 cycle
의 Knowledge Cascade (Layer 3 Memory OS) 가 안정화되며, 2026-05-21
사용자 비판 시리즈에서 "Layer 3 alone" 의 governance gap (stale facts
/ Gate 5 silent reject / manual hierarchy 없음 / event sourcing 부재)
드러남. 후속 architectural insight 로 **CASCADE (invalidation
propagation) 와 EVENT/TEMPORAL (semantic evolution) 의 명확 분리**
axiom 채택 — 두 종류 mutation 을 같은 메커니즘으로 처리하면
contradiction 폭발. 7 영역 (T1–T7, T7 supersede chain 신규) 디자인
메모 (`docs/architecture/memory-lifecycle-architecture.md` §1.5 +
`docs/design/v0.4-lifecycle-semantics-roadmap.md` §9.5) 작성. v0.4
첫 ship bundle = T1+T7+T2 (EVENT 핵심 + A/B routing). 기존 v0.4
(First Domain Pilot) → v0.5 로 shift. 2026-05-22 i18n sweep 시리즈
(7 PR, ~304 entries, 7 backend 모듈) 가 `label_key` 패턴을 platform
invariant 로 lock-in — v0.4 신규 라벨도 동일 contract 필수. Open
issues: 0.

**Prior update (2026-05-13)**: **v0.3 진입 정식**. Axis 6 두 번째
사용자 게이트도 모집 완료 → 6 axes 모두 통과 → v0.2 → v0.3 gate clear.
v0.2.x 가 더한 Change Request 기반 (`core/change_request.py` +
`wiki_entity` + `run_jobs`) + dependabot 6 high-severity 마감 +
정공법 3 PR (#252/253/254: 웹 학습 LLM-triple 위임 / UNRESOLVED sweep /
노이즈 cleanup 스크립트). v0.3 Platform Skeleton 트랙 활성 — License /
CLA / Plugin API / Knowledge Cascade / CR-E 가 본 사이클부터 deliverable.
