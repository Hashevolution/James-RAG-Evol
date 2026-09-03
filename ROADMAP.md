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

## v0.3.0 — Platform Skeleton (entered 2026-05-13, **closed 2026-05-25** at v0.3.3 stabilization)

**Closure summary (2026-05-25)**: Platform Skeleton theme completed across three Zenodo-archived releases:

- **v0.3.0** — V3' Protocol v1 methodology spec (`docs/research/v3prime-protocol-v1.md`)
- **v0.3.1** (DOI `10.5281/zenodo.20363998`) — D1 Adaptive Budgeting closure with 7-tier natural-stop gradient
- **v0.3.2** (DOI `10.5281/zenodo.20372649`) — D5 Auto-routing on Provider Contract (10-PR sequence #474–#484)
- **v0.3.3** (DOI `10.5281/zenodo.20374227`) — D6 retry-wiring follow-up cycle (PR #486 wiring + #487 audit + #488 native Ollama done_reason)

ROADMAP §Plugin contract / Change Request / Knowledge cascade / Governance / Carryover / v0.3-only follow-ups / Measurement framework Direction 1+4+5+6(J) — all checked. Done-when: 3/4 fully satisfied + 1/4 partial (first external pack author trial awaits Ali mid-June Gemini PR). v0.4 entry triggered.

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
- [x] **Direction 5 — Auto-routing on Provider Contract**
      (closed 2026-05-25, 10-PR sequence PR #474-#483). New
      `core/reasoning/router.py` (D5.A skeleton + D5.B capability
      tags + D5.C.1 policy decision tree) consumes Direction 1's
      budget to select backend (`small`/`medium`/`large` tier ×
      `local`/`sovereign`/`cloud` provider). 5-stage wiring
      complete (`query_rewriter` / `planner` / `reflect` /
      `verify` / synth via `trace_helpers`) — every production
      LLM call path consults the router, gated by
      `JAMES_AUTO_ROUTER` flag (default OFF → byte-identical to
      pre-D5). Audit row `reason:route` per resolve call.
      **Verify stage** is grounding-critical → policy escalates
      to `large` tier when registered (e.g. `JAMES_ENABLE_CLAUDE_BACKEND=1`).
      Provider Contract surface unchanged (router sits above L1).
      Cross-lingual RAG option 3 (`core/entity_alias_pack.py` +
      `graph_engine.build_entity_map_snapshot` augmentation,
      PR #483) bundled — KO↔EN surface forms now resolve to the
      same wiki entity_id without per-install frontmatter edits.
      Per Build-don't-broadcast principle (memory: `feedback_build_dont_broadcast`)
      this is a product cycle — no public broadcast, no Robin
      coupling. Operator-run STEP 7 sweep numbers (D1 7-tier
      ground truth) integrate into the closure result doc when
      operator runs the measurement; the wiring is bench-neutral
      at flag-OFF default.
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

## v0.4.0 — Layer 4 Lifecycle Semantics (entered 2026-05-25, **T1+T7+T2 first bundle shipped 2026-05-27** at Sprint 5)

**Status**: T1 (Temporal Validity) + T7 (Supersede Chain) + T2 (Contradiction Arbitration) first bundle landed via Sprint 5 (8 PRs, #523~#543). v0.4.0 is **release-ready** — the CASCADE / EVENT separation invariant is provable end-to-end via the release-gating tests in `tests/test_t7_release_gating_invariants.py`.

**Entry handover**: `docs/handovers/v0.4.0-entry-track.md` — 6-sprint plan covering data correctness, UI consistency, plumbing, retrieval quality, Layer 4 main theme (T1+T2+T7), and long-term backlog. Sprint 0 (this entry) + Sprint 1 (graph entity-event relation diagnostic + language detection&matching) ran first.

**Sprint 5 first-bundle entry**: `docs/handovers/v0.4.0-sprint5-layer4-first-bundle-entry.md` — the locked-decision 7-PR sequence (PR-0 schema validators → PR-T1.A migration → PR-T1.B expiration cascade → PR-T7.A supersede chain → PR-T7.B release-gating invariants → PR-T2.A classifier → PR-T2.B A-path routing → PR-T2.C B-path routing → PR-T7.C closure) that shipped here.

### Original Layer 4 scope (preserved below for the eventual T1/T2/T7 sprint)

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

### Done when — ✅ All items satisfied at v0.4.0 (2026-05-27)

- ✅ T1 + T7 + T2 (minimum) shipped, with new invariants green
  (`tests/test_lifecycle_*.py` + `tests/test_t7_*.py` +
  `tests/test_t2_*.py`, 123 tests).
- ✅ **Separation invariant provable** — `test_t7_release_gating_invariants.py`
  pins three release-gating invariants against the actual wiki
  fixture (not mocks): `test_supersede_does_not_trigger_cascade`,
  `test_cascade_preserves_supersede_chain`,
  `test_historical_replay_via_chain`. The B-class CEO-change
  scenario (Joby CEO Alice → Bob) is end-to-end exercised in
  `test_supersede_chain_replayable_after_dispatch`.
- ✅ Operator scenario A (CASCADE): `cascade_remove_doc_from_sources`
  unchanged from v0.3 + now reachable via
  `contradiction_router.route_a_invalidate` with audit row
  carrying `mutation_type=invalidated`.
- ✅ Operator scenario B (EVENT): `expiration_cascade` (T1) +
  `supersede_edge` (T7) + `route_b_supersede` (T2.C) land. Edges
  are marked `status.active=False` not deleted; historical replay
  works via `reconstruct_view_at`.
- ✅ Reference architecture memo + 7-area design memo published
  (`docs/architecture/memory-lifecycle-architecture.md` +
  `docs/design/v0.4-lifecycle-semantics-roadmap.md`).
- ⏭️ **Carried into v0.4.1**: ingestion-path caller that invokes
  `dispatch_contradiction` at a real contradiction-detection
  point. Sprint 5 ships the primitive surface + the routing wire;
  the call site is the next operator integration. End-to-end
  STEP 7 supersede bench (Alice → Bob historical replay)
  deferred to the ingestion-wire PR.

### Out of scope (deferred to v0.5)

- Any domain pack (legal / food / retail) — moved to v0.5
- External customer onboarding playbook
- Public eval results in `eval/RESULTS.md`
- 6-month production track record

---

## v0.4.1 — T6 Causality Chain (CASCADE extension, shipped 2026-05-28)

**Status**: ✅ **CLOSED**. T6 Causality Chain landed as the v0.4.1 cycle's main theme (5-PR sequence T6.A → T6.B → T6.C → T6.C.b refinement → T6.D + the v0.4.0 carry-over T2.D-1/2/2.b/3 + QVT α track full closure). 21 PRs in a single multi-day session (#548 ~ #566).

**Entry handover**: `docs/handovers/v0.4.1-t6-causality-chain-entry.md` — 4-LOCK decisions (eager trigger / operator-tagged + LLM flag / strict cycle reject / **C.b foundational-vs-corroborative semantics** — Decision 4 refined in T6.C.b vs the original memo text).

### Done — T6 5-PR sequence + 4 release-gating invariants

- **PR-T6.A** (#562) — `derived_from` schema field + `validate_edge_t6_derived_from` cycle validator (Decision 3 LOCK) + `apply_t6_edge_defaults` idempotent helper. `scripts/migrate_v041_lifecycle.py` (`--dry-run` / `--apply` / `--verify` / pre-write snapshot). 23 contract tests.
- **PR-T6.B** (#563) — `core/lifecycle/derivation.py` `extract_derivation_chain` (operator-tagged path + `JAMES_T6_LLM_DERIVATION` flag-gated LLM-inferred path). 14 contract tests.
- **PR-T6.C** (#564) — `core/lifecycle/causality.py` `invalidate_derived_facts(base_fact_id, entity_root, *, additional_empty_bases, audit_emit)`. Soft-invalidate (status.active=False + mutation_type=invalidated, sources preserved for T7 replay). Atomic per-file writes. 19 contract tests.
- **PR-T6.C.b** (#565) — foundational-vs-corroborative refinement. `transitive` / `inferred` are hard deps (any base empty → invalidate); `operator` is corroborative (only invalidates when no hard deps AND all operator bases empty). 22 tests (19 original + 3 new C.b cases).
- **PR-T6.D** (#566) — cascade integration. `cascade_remove_doc_from_sources` now calls `invalidate_derived_facts` for every relation whose sources became empty (single walk batched via `additional_empty_bases`). `tests/test_t6_release_gating_invariants.py` (5 tests): `test_derived_invalidated_when_base_removed`, `test_partial_base_loss_preserves_derived` (T6.C.b), `test_self_reference_rejected_at_write` + `test_two_hop_cycle_rejected_at_write` (Decision 3), `test_cascade_invalidate_emits_audit_row`. Run against tmpdir wiki fixtures + real `cascade_remove_doc_from_sources` — no mocks of the cascade itself.

### Done — v0.4.0 carry-over `dispatch_contradiction` ingestion wiring (T2.D, 4 PRs)

- **PR-T2.D-1** (#558) — `core/lifecycle/contradiction_ingest_detector.py` (P1 different_tail + P2 divergent_validity patterns). 19 tests.
- **PR-T2.D-2** (#559) — `core/lifecycle/ingest_contradiction.py` + `_merge.py` pre-merge hook. Flag-gated by `JAMES_T2D_INGEST_DISPATCH` (default OFF). 10 tests.
- **PR-T2.D-2.b** (#561) — A_invalidate cascade race fix via `PendingCascade` deferred-execution. 15 tests.
- **PR-T2.D-3** (#560) — step7 v6 q17 *"Anthropic의 CEO는 누구야?"* + acceptance integration test. 6 tests.

### Done — QVT α track full closure (6 PRs)

- **PR-α-1** (#550) — `docs/design/v0.4-qvt-alpha-non-saturating-oracle.md`. 3-axis non-saturating oracle + per-PR Quality Delta Card pattern + 5 exemption labels.
- **PR-α-2** (#551) — step7 fixture v4 → v5 (`gold_signals` + `abstention_truth`).
- **PR-α-3** (#552) — `eval/qvt/oracle.py` + `scripts/qvt_capture_baseline.py` (operator wrapper).
- **PR-α-4** (#553) — `.github/PULL_REQUEST_TEMPLATE.md` + CLAUDE.md rule 2 extension + `docs/ARCHITECTURE.md` §5.7.10 QVT subsystem.
- **PR-α-3 baseline capture** (#555) — `eval/qvt/baseline_2a31b20.json` (N=3 paired reruns, canonical reference).
- **PR-α-3 oracle calibration** (#556) — Korean security-block phrase additions + `blocked=True` short-circuit. `abstention_f1` 0.29 → 0.67 median.

### Done — also in v0.4.1

- **Replayable RAG positioning** (#548) — README + ARCHITECTURE category framing.
- **F9 cycle full closure** (#549) — q15 zero-recall closure result doc + audit-trail bench JSON.
- **v0.4.0 post-mint DOI** (#554) — `10.5281/zenodo.20411354`.
- **v0.4.1 entry memo** (#557).

### Default-off invariant preserved across every opt-in

| Flag | Default | Verification |
|---|---|---|
| `JAMES_T2D_INGEST_DISPATCH` (T2.D-2) | OFF | `_merge.py` pre-merge hook only fires when `=1` |
| `JAMES_T6_LLM_DERIVATION` (T6.B) | OFF | `extract_derivation_chain` LLM-inferred path needs provider AND flag |
| T6.D cascade integration | ON (default-on per cycle scope) | byte-identical retrieval because migration adds `derived_from: []`; no actual derivations yet |

### Done when — ✅ All items satisfied at v0.4.1 (2026-05-28)

- ✅ T6 5-PR sequence merged with all 83+ contract tests green.
- ✅ T6.D 4 release-gating invariants run against real wiki fixtures (`tests/test_t6_release_gating_invariants.py`).
- ✅ T2.D ingestion wiring (carry-over from v0.4.0) shipped with race-free pending_cascades pattern.
- ✅ QVT α track complete: oracle module + canonical baseline JSON + PR-gate template + CLAUDE.md rule 2 extension + ARCHITECTURE.md §5.7.10.
- ✅ Migration script (`scripts/migrate_v041_lifecycle.py`) is idempotent + byte-stable; `--verify` mode confirms.
- ✅ 69 pre-T6 cascade tests still green (no regression).
- ✅ Closure docs published: `docs/release_notes_v0.4.1.md` + CHANGELOG `[0.4.1]` + `.zenodo.json` v0.4.1.

### Out of scope (deferred to v0.4.2+)

- **T3 Evidence Aging** — confidence decay over time (EVENT track)
- **T4 Reviewer Authority Hierarchy** — multi-level governance (GOVERNANCE track)
- **T5 Replayable Audit Graph** — full event-sourced reconstruction (partial in v0.4.0 via `reconstruct_view_at`)
- ~~v0.4-end QVT ablation matrix capture (18 cells × N=3 reruns, ~20 hours operator-run)~~ — **re-shaped 2026-05-30~31 into the α-5 cycle below**.
- `JAMES_T2D_INGEST_DISPATCH` default flip to ON (waits for fixture coverage)
- Production seeding of `derived_from` (waits for operator workflow or v0.4.2+ LLM path)

---

## v0.4.x — α-5 Ablation Matrix Cycle (2026-05-30~31, **T0 closed 2026-05-31 15:52 KST**)

**Theme**: the v0.4-end ablation matrix that v0.4.1's "out of scope" line
deferred — re-shaped end-to-end during execution. The single bullet
"18 cells × N=3, ~20 h" turned out to be too thin a frame for what
the matrix actually needs to deliver. Recording the corrected sizing,
the external-benchmark adoption, and the **dual purpose** so the next
operator entering this cycle reads the right shape on the way in.

### Dual purpose (per 2026-05-31 user clarification)

1. **Routing decision** — flag-ON / tier-gating for each Layer 4 cognitive
   routing layer (`AUTO_ROUTER` D5, `ADAPTIVE_BUDGET` D1,
   `SCOPE_ROUTING` LEO). The original framing.
2. **Reasoning-capability evidence** — publishable proof that JAMES's
   layer stack outperforms peers on external benchmarks. Ties to
   `eval/RESULTS.md`'s `external benchmark` line that v0.3 deferred —
   this cycle is the unblock.

Both purposes must be served by every cell verdict; **bucket-(d)
measurement artifacts** must be removed before either narrative ships
externally (per `feedback_oracle_phrase_artifacts` 4-step rule).

### Actual sizing (vs the original 18×N=3 ≈ 20h estimate)

- **19 cells** (18 standard + 1 sanity `M_M/L1 think=ON`) — extra cell
  carries A2 default-flip evidence inside the matrix.
- **5-axis oracle** — 3 quality (path / graded / abstention) + 2 cost
  (token_cost, latency_cost) per cell, Pareto verdict
  (strong-adopt / adopt / efficiency-adopt / tier-gated / reject /
  zero). Cost integration was added to serve user requirement #3
  (token / time efficiency).
- **Workspace runtime** (MultiHop-RAG balanced-100, 931-entity
  workspace, A2 think=OFF):
  - Ingest: 264 min for 183 articles (latency grew with workspace
    size — first 25 s, last 197 s)
  - Baseline N=1: 107 min (100 queries × ~64 s)
  - T0 smoke (N=1, 3 cells): ~5.3 h estimate
  - Full N=3 sanity-included T0+T1: ~16 h
  - Full N=3 T0+T1+T2 across all 3 tiers: ~30 h (vs original 20 h)
- **Adaptive tiering** — `--t0-smoke` (~2-5 h) gates whether T1
  (M_M, ~5.5 h) is worth running; T1 gates whether T2 (M_S + M_L,
  ~13 h) adds tier-gating signal.

### External benchmark adoption

`eval/RESULTS.md` originally said *"BEIR / MS MARCO — too large for
laptop, defer to v0.3"* and *"KLUE-RC — no clean public option yet,
watch for v0.4."* This cycle finally lands an external benchmark via
**MultiHop-RAG** (Tang & Yang, EMNLP 2024) — 2,556 multi-hop QA over
609 news articles, CC-BY-4.0, with 4 question types (comparison /
inference / temporal / null) that map directly onto the routing /
abstention measurement need.

Workspace isolation via the existing `JAMES_WORKSPACE` env
(`config.py:74`, `core/plugins/workspace.py`) — zero code change to
the data-dir resolver. Production wiki is untouched throughout the
cycle.

### PR sequence (24 PRs to date, 2026-05-30 → 2026-05-31, T0 smoke mid-flight)

| PR | Layer | Note |
|---|---|---|
| #615 | reset | MultiHop-RAG external benchmark + 5-axis + per-question-type matrix |
| #616 | exec | Ingest wrapper + bench timeout fix + path-axis finding |
| #617 | docs | §7.4 first per-question-type baseline signal |
| #618 | fix (d) | source-recall — bench was dropping `response.sources` |
| #619 | fix (d) | abstention phrases — gemma4:e4b English refusals |
| #620 | tool | re-score tool + §7.4 76% → 36% correction |
| #621 | docs | 4-bucket diagnostic taxonomy + dual purpose |
| #622 | fix | render_report defensive path + bucket retroactive |
| #623 | fix (d) | session_id suite-aware + 3 narrow abstention phrases |
| #624 | docs | ROADMAP §v0.4.x α-5 cycle entry (this section, initial form) |
| #625 | fix (a) | matrix runner — bench subprocess respects `--suite` (was hardcoded step7) |
| #626 | docs | T0 smoke result analysis TEMPLATE (`qvt-ablation-T0-smoke-analysis-TEMPLATE.md`) |
| #627 | docs | Pareto verdict walk-through + CLAUDE.md rule 2 `fix` label exempt + diagnostic post-mortem |
| #628 | feat | T0 analysis fill script — auto-populate template from cell JSONs |
| #629 | docs | oracle.py → package split design (deferred to post-matrix) |
| #630 | docs | α-5 cycle summary outline — reviewer-ready closure read |
| #631 | docs | publishable narrative draft — "Don't Build a Layer for the Bug" |
| #632 | docs | bucket-(c) LLM-judge abstention detector design memo |
| #633 | feat | `qvt_promote_findings.py` — auto-draft memory entries from findings.md |

All 19 cycle PRs above land on `main` between `f7762a3` and `ba50c47`.
Two landmark findings of the cycle — `path_recall = 0` and
`null_query hallucination = 76%` — were **both bucket-(d) oracle
artifacts**, fixed in #618 / #619 / #623. Without the 4-step
verification rule (memory `feedback_oracle_phrase_artifacts`) they
would have generated wrong-bucket follow-ups (new citation layer,
grounding architecture change) and the matrix verdicts would have
read as "JAMES fails the benchmark" when the failure was on the
measurement side.

**Wrong-fix avoided count**: 3 (path_recall=0 → new citation layer
prevented #618; 76% hallucination → grounding rewrite prevented
#619+#623; matrix near-zero verdict → AUTO_ROUTER decommission
prevented #625). Cumulative system code change attributable to
α-5 measurement debt: **0 lines**.

**Mid-cycle infra additions** (#626–#633): 1 template + 1 fill
script + 2 design memos + 1 closure outline + 1 publishable
narrative + 1 finding-promotion script. Locked deferred-bucket-(c)
follow-up + locked the methodology lesson in a publishable form
before the cycle closes.

### Cycle deliverables — T0 closure 2026-05-31 15:52 KST

- [x] **5-axis matrix report** at
      `reports/promo-assets/v0.4-qvt-ablation-matrix-20260531T065209.md`.
      Both L1/M_M (baseline) and L5/M_M (full stack) classified
      **reject** vs corrected baseline; sanity cell L1/M_M-thinkON
      also reject.
- [x] **T0 analysis** at
      `reports/research-runs/qvt-ablation-T0-smoke-result-20260531-1552.md`.
- [x] **Rescore audit** at
      `reports/research-runs/qvt-ablation-rescore-summary.md` —
      3/3 cells QQ-bugged at write time, all rescored in one pass.
- [x] **Findings log** at
      `reports/research-runs/qvt-ablation-findings.md` — all entries
      `bucket:`-tagged (a/d).
- [x] **ROADMAP / backlog sync** — this section locked, status
      moved from "in flight" to "T0 closed". A1 in backlog §2
      marked closed.
- [ ] Routing-flag default-flip PRs per layer — **not applicable**
      at production tier (Branch B verdict). Tier-gated assessment
      requires T1 (M_S + M_L) which is post-T0 operator decision.
- [ ] T1 / T2 operator decision — see §"T0 verdict + post-closure"
      below.

### T0 verdict + post-closure (2026-05-31)

| Read | Number | Compared to |
|---|---|---|
| L1/M_M baseline (production) | path **0.419** / graded **0.327** / abst_f1 **0.591** | corrected baseline `3a961a3_rescored` (path 0.404 / graded 0.343 / abst_f1 0.609) |
| L5/M_M full stack (all routing ON) | path 0.412 / graded 0.317 / **abst_f1 0.500** | abst_f1 -0.091 vs L1 — real regression |
| Sanity L1/M_M think=ON | path 0.404 / graded 0.370 / abst_f1 0.533 / token -109 chars / latency -1.7 s | think=ON not unambiguously winning; A2 default-flip gate (real-query QDC) unchanged |

**Verdict (post-closure-corrected 2026-05-31 PM)**: routing-layer
stack as exercised in α-5 reduces to
`ADAPTIVE_BUDGET + SCOPE_ROUTING + (AUTO_ROUTER no-op)` because the
matrix env registered only the always-on `ollama_local` backend
(`core/reasoning/backends/__init__.py:329`); without multi-tier
backend registration the routing policy in `core/reasoning/router.py`
collapses to legacy on every branch. The combined stack regresses
abstention_f1 by **0.091** without meaningful cost benefit
(token -1.5%, latency +3.6%) at the M_M production tier. Both cells
classify **reject** under the 5-axis Pareto rule.

**AUTO_ROUTER verdict is not in evidence** at this cycle; proper
measurement requires multi-tier backend registration (engineering
preconditions documented in α-6 design memo). **ADAPTIVE_BUDGET was
under-instrumented** — judged by quality axes when its design intent
(per `core/reasoning/budget.py` docstring) is cost-optimization at
quality-neutral. Per-layer isolation (L2 / L3 / L4 cells) defers to
T1. **Branch B** of the publishable narrative §6 applies *as
"conditional Branch B"* — routing-layer stack inert *as measured by
quality axes*, with explicit caveats. Opt-in flags remain available;
no default-flip PRs file at this verdict.

**Cycle totals**: 36 PRs (#608 → #645+), 5 measurement-side fixes
(3 bucket-d + 2 bucket-a), 4 wrong-fix-averted, **0 lines of JAMES
code changed against α-5 measurement debt**. The publishable claim
(see §6.1 of `reports/research-runs/alpha-5-publishable-narrative-DRAFT.md`)
is the cycle's load-bearing artifact.

### Operator decision — T1 / T2 sizing

T1 (M_M + more rows) and T2 (M_S + M_L) are operator-budget calls.
Recommended:

- **T1** (~5.5 h on M_M) — measures whether individual layers (L2/L3/L4)
  show effects that all-on L5 smears together. Could surface
  ADAPTIVE_BUDGET (L3) wins inference-query graded while AUTO_ROUTER
  (L2) hurts abstention.
- **T2** (~13 h on M_S + M_L) — tests the **tier-gated routing**
  hypothesis: smaller models might benefit MORE from routing
  (compensating for base-capability gap); larger models might benefit
  LESS. T2 closes the cycle's "model is universally tested" caveat.

Both deferable. **T0 closure is itself shippable** as
"production-tier evidence: routing layers inert" + Branch B
publication. T1/T2 fold into an α-5.1 or α-6 cycle.

### Open methodology questions for the next cycle

- **bucket-(c) LLM-judge abstention detector** — 6 of 9 remaining FN
  on baseline_f7762a3 use "not possible to" / "is not available"
  phrasings that broader phrase additions would FP-flood. An LLM
  classifier ("does the answer refuse to answer the question?") would
  resolve them without phrase-overlap risk. Deferred candidate.
- **Korean-corpus version of MultiHop-RAG** — current cycle is English
  only (gemma4:e4b handles both per `core/i18n.py`, but the matrix
  measures English routing only). No public Korean multi-hop RAG
  benchmark exists; translation cost vs. value is a v0.5+ question.
- **Production-real-query Quality Delta Card** — bridging the
  benchmark-vs-production gap for the A2 default-flip
  (`JAMES_GEMMA4_E4B_THINK_OFF`) decision. Plan is documented but the
  card itself is a separate cycle.

---

## v0.4.x — α-6 Sector × LLM Ablation Cycle (2026-05-31~, **Phase 3a in flight**)

**Theme**: successor to α-5. α-5 toggled 5 routing flags at one model
tier and found the routing stack inert at production tier (Branch B).
α-6 reshapes to:

1. **Sector-level ablation** (10 sectors of JAMES infrastructure
   instead of 5 routing flags). Cells are sector *combinations*, not
   flag combinations.
2. **Multi-LLM extension** — gemma3 1b/4b/12b/27b + gemma4:e4b + (later)
   cross-family (qwen2.5 / llama3.1 / deepseek-v2).
3. **JAMES-vs-vanilla comparison** — α-5's L1 baseline already had
   every other JAMES sector on; α-6's C_minus cell strips them off and
   measures bare gemma against benchmark.

**Cycle sizing** (vs original α-6 design memo §3):

- 4 phases (Phase 0 sector flags / Phase 1 M_M / Phase 2 M_S / Phase 3a
  scale ladder / Phase 3b cross-family deferred).
- 75+ PRs through Phase 3a entry, 8 wrong-fix-averted, **0 lines of
  JAMES code changed** against measurement debt.
- Per-tier wall-clock: M_XS ~15 min / M_S ~30 min / M_M ~107 min /
  M_L ~65 min / M_XL ~6-8h (GPU/CPU split, see below).

### Phase status (live)

| Phase | Tier | Status |
|---|---|---|
| Phase 1 | M_M (gemma4:e4b) | ✅ closed 2026-06-01 AM |
| Phase 2 | M_S (gemma3:4b) | ✅ closed 2026-06-01 AM — tier-gated hypothesis REVERSED |
| Phase 3a step 1 | M_XS (gemma3:1b) | ✅ closed 2026-06-01 PM |
| Phase 3a step 2 | M_L (gemma3:12b) | ✅ closed 2026-06-01 PM — gemma4-only hypothesis REVERSED |
| Phase 3a step 3 | M_XL (gemma3:27b) | 🟡 in flight (bench timeout overrides applied, see PR-pending) |
| Phase 3a closure | recovery curve + closure PR | ⏳ post-27b |
| Phase 3b | cross-family (qwen / llama / deepseek) | deferred (gated on Phase 3a verdict) |

### Findings (4 tier-tagged per `feedback_finding_size_honest_framing`)

| Finding | Tier | Status |
|---|---|---|
| S4 citation tier-invariant — path Δ +0.397~+0.420 across 1b/4b/12b/e4b (4-point series, 27b pending) | ⭐⭐⭐ candidate | universal-law promotion gated on 27b confirmation + cross-fixture sanity |
| JAMES S5 effect non-monotonic in pure-model abstention (1b 0 / 4b -0.074 / 12b +0.375 / e4b +0.033) | ⭐⭐ partial | mechanism candidate = instruction-following capacity threshold |
| Graph layer regresses graded (-0.054 at M_M C_rag-graph step) | ⭐⭐ measurement debt | resolves on α-7 graph top-K fix; logged in `qvt-ablation-findings.md` |
| Withdrawn framings — "JAMES amplifier", "inverted-U capability floor", "gemma3 vs gemma4 family", "REVERSES tier-gated hypothesis" | ❌ self-deception | superseded by 12b / 27b data; honest framing memory applied |

### Cycle PR index

`reports/research-runs/alpha-6-cycle-pr-index.md`.

### Closure deliverables (in flight on `feat/v0.4-alpha6-phase-3a-closure`)

- Phase 3a 1b analysis (`alpha-6-phase-3a-gemma3-1b-analysis-20260601.md`)
  with post-12b reconciliation header
- Phase 3a 12b analysis (`alpha-6-phase-3a-gemma3-12b-analysis-20260601.md`)
  with honest framing tier table
- Phase 3a 27b analysis (post-bench)
- Recovery curve doc (`alpha-6-phase-3a-recovery-curve-20260601.md`)
  with §5 withdrawn-claims registry
- Closure PR consolidating all 3 analyses + recovery curve + 2 timeout
  fix patches + CLAUDE.md sync + α-7/α-8 design memo seeds

---

## v0.4.x — α-7 Graph Top-K Cycle (post-α-6 closure)

**Theme**: first JAMES code change against α-5 + α-6 measurement debt.
Per α-6 Phase 1 §3 finding, the graph layer (`expand_dynamic` in
`core/graph_engine.py:314`) is the net regressor on `graded` at M_M
(-0.054). 41-161 entities surface per query at the 931-entity workspace,
swamping the LLM context window with low-signal nodes.

**Status**: design memo landed
(`docs/design/v0.4-alpha-7-graph-topk.md`); implementation gated on
α-6 closure + re-baseline.

**Scope** (per design memo §2):

- New module `core/graph_topk.py` (~3 KB target) — post-DFS top-K
  filter, default K=10
- Tighten `DFS_SCORE_THRESHOLD` 0.05 → 0.08
- Wire into `expand_dynamic` return
- Avoids forcing `core/graph_engine.py` split (already 20.4 KB,
  marginally over the 20 KB gate — new module routes around it)
- Re-baseline `multihop_rag` post-PR (~107 min operator action)
- 5-axis Quality Delta Card with per-question-type cross-tab

**Acceptance band** (per design memo §4): `graded_answer Δ ≥ +0.030`
for adopt; +0.010-0.030 for tier-gated; ≤ +0.010 → reject + sub-finding
investigation.

**Honest framing** (per memory `feedback_finding_size_honest_framing`):

- ⭐ **operational** — top-K filtering is a standard GraphRAG technique
  (MS GraphRAG, Neo4j LLM KG Builder both do variants). PR's value is
  the measured Δ numbers, not the mechanism.
- Don't frame as "JAMES discovered top-K filtering" — false claim.

**Cycle dependencies**:

- Predecessor: α-6 closure (the re-baseline depends on Phase 3a
  closure being on main)
- Successor: α-8 ontology typed-filter (A/B compares against α-7's
  K-bound baseline)
- Parallel: T3 Evidence Aging (orthogonal axis)

### α-7 cycle CLOSURE (2026-06-02) — REJECT

**Status**: cycle closed as REJECT. PR #680 closed without merge.
α-7 graph top-K is a research artifact, not a production change.

**5-tier remeasurement verdict** (1000 queries, 0 timeouts, 0 errors,
10/10 cells written):

| Tier | α-6 contribution | α-7 contribution | change | mode change |
|---|---:|---:|---:|---|
| M_XS (1b) | 0.000 | 0.000 | 0 | unchanged (inert) |
| M_S (4b) | -0.074 | -0.067 | +0.007 | unchanged (disrupt) |
| **M_M (e4b)** | **+0.033** | **-0.283** | **-0.316** | **CRASH** amplify → disrupt |
| **M_L (12b)** | **+0.375** | **-0.076** | **-0.451** | **CRASH** create → disrupt |
| M_XL (27b) | -0.181 | -0.359 | -0.178 | worse disrupt |

**Mechanism (CONFIRMED)**: top-K=10 removes "evidence-of-absence"
signal at every tier where pure-LLM had nonzero abstention capability.
Universal regression. K=50/K=25 tuning would not fix — wrong-knob
mechanism, not wrong-value problem.

**S4 universal-law candidate** (path Δ) survives the context reshape:
spread ±0.013 across 5 tiers (vs α-6 ±0.022). ⭐⭐⭐ candidate
strengthens — citation pipeline is graph-entity-count independent.

**Wrong-fix-averted**: 10th cumulative (7 α-5 + 2 α-6 + 1 α-7).
α-7 cycle's value = preventing the wrong fix from shipping, plus
mechanism finding informing α-8.

**Carry-forward to α-8**:
- Bucket-(d) phrase additions (7 total: 5 α-7 PR + 2 follow-up) —
  eligible for separate docs-only PR for oracle improvement.
- α-7 closure analysis preserved at
  `reports/research-runs/alpha-7-closure-analysis-20260602.md`.
- α-7 5-tier 10 cell JSONs preserved at
  `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/`.

**Memory entries** added 2026-06-02:
- `feedback_alpha7_top_k_destroys_positive_contributions`
- `feedback_s4_citation_survives_context_reshape`
- `feedback_12b_pure_capability_misclassified_as_plateau`
- `project_alpha_7_closure_state`

---

## v0.4.x — α-8 Ontology Typed-Filter Cycle (post-α-7 closure)

**Theme**: measures whether **typed** filtering (only surface entities
whose type matches query intent) beats α-7's **type-agnostic** K
filter on multihop_rag. A/B isolation: `Δ = C_rag-ontology −
C_rag-graph_post-α-7`.

**Status**: design memo landed
(`docs/design/v0.4-alpha-8-ontology-typed-filter.md`); implementation
gated on α-7 closure.

**Scope** (per design memo §2 + §3):

- Extend `core/ontology.py` (10 KB → ~14-15 KB; under gate):
  - Abstract root `Entity` + `ENTITY_TYPES` registry
  - 5 new horizontal types: `event`, `date`, `location`, `quantity`,
    `project` (additive; existing `person / org / concept / document`
    unchanged)
  - 6 new relations: `OCCURRED_AT`, `HAPPENED_ON`, `LOCATED_IN`,
    `INVOLVES`, `MEASURED_AS`, `WORKED_ON`
- **Migration cost: 0** — additive only; old types and 931 wiki
  entities unchanged.
- New sector flag `JAMES_DISABLE_TYPED_FILTER` (disable-polarity,
  default OFF = sector ON = production byte-identical)
- New matrix cell `C_rag-ontology` (between `C_rag-graph` and
  `C_rag-full`)
- Query intent → expected-type classifier (keyword heuristic; LLM
  classifier deferred to v0.5+)
- 5-axis QDC + per-question-type cross-tab against post-α-7 C_rag-graph

**Acceptance band** (per design memo §4):

- ⭐⭐ adopt — `graded Δ ≥ +0.030`
- tier-gated — `+0.010 ≤ graded Δ < +0.030` (enable per question_type
  only)
- reject — `graded Δ < +0.010` (heuristic top-K is sufficient; ontology
  layer stays in codebase but disabled by default)

**Rule #1 boundary test** (per design memo §2.3): each proposed type
checked horizontally. The 5 accepted types pass; `regulation`,
`transaction`, `recipe` flagged for deferral or rejection.

**Forward compat hook** (per design memo §3.4): `since:` field anchor
allows v0.5 domain packs to register pack-specific types via the same
mechanism without absorbing them into the mother schema.

**Honest framing** (per memory `feedback_finding_size_honest_framing`):

- ⭐⭐ **partial** if Δ exceeds noise — typed filtering is a known
  technique; JAMES-specific value is the empirical position, not the
  mechanism
- ⭐ **operational** if Δ ≤ noise — confirms heuristic top-K is
  sufficient; finding logged either way
- ❌ Don't claim "JAMES discovered typed semantics matter" — decades-
  old territory

**Cycle dependencies**:

- Predecessor: α-7 closure (baseline = post-α-7 C_rag-graph)
- Successor: cross-fixture sanity (deferred to v0.5 entry)
- Parallel: T3 Evidence Aging (orthogonal)

---

## v0.4.x — Sequencing rule (2026-06-01 strategy handover §4)

Graph-touching cycles **serial** to avoid measurement baseline drift:
`α-6 closure → α-7 → α-8`. Confidence/time-axis cycles **parallel** to
graph track: T3 Evidence Aging is orthogonal to entity surfacing/typing
and can land in any cycle alongside the graph track.

The v0.5 first-domain candidate is **enterprise internal knowledge
ontology** (horizontal, audit/ownership/correction moat) per 2026-06-01
strategy handover §6. This framing applies to v0.5 *domain selection
criteria*, not to v0.4 cycle scope. Mother-platform rule #1 holds —
v0.4.x cycles add only horizontal infrastructure (top-K, abstract types,
forward-compat hooks), no domain-specific types.

---

## v0.5.x — Cycle close + post-close consolidation (2026-06-12 → 2026-06-13)

**v0.5 entry declared 2026-06-12** after v0.4.4 closure (LRB v0.2.3
S3 publication-scale + cycle γ 4-bench infrastructure closure; Zenodo
DOI [`10.5281/zenodo.20652679`](https://doi.org/10.5281/zenodo.20652679)).

Operator decision at entry: *"이제는 진짜 엔터프라이즈 온톨로지 장착으로 간다"*
([entry handover](handovers/v0.5-entry-2026-06-12.md)).

**v0.5 closed 2026-06-12 PM** with 21 PRs (#841 – #861) per the
[v0.5 close handover](handovers/v0.5-close-2026-06-12.md). 23
additional PRs (#863 – #886) landed between cycle close and
2026-06-13 implementing most of the close handover §5 work queue —
see the [v0.6 entry skeleton](handovers/v0.6-entry-skeleton-2026-06-13.md)
for the post-close work-queue status sweep.

### Four work streams (CLAUDE.md rule #1 preserved — actual status at 2026-06-13)

| Stream | Scope | Status at 2026-06-13 |
|---|---|---|
| **A** — Pre-LOI materials + Hashevolution dogfooding | Customer-facing 자료 v0.4.4 sync (7 docs) + Hashevolution own-company scenario (시나리오 C: internal dogfooding + external outreach 병행) + G1.a/G1.b/G1.c tenant-id contract + G2.a/G2.b/G2.c approval-evidence contract | A.1 / A.2 ✅; A.3 / A.4 **operator-pending**; G1+G2 SaaS-readiness trio ✅ (#860 / #861 / #869 / #870 / #882 / #883) |
| **B** — Enterprise ontology framework (mother-level) | B.1 audit + B.2 multi-tenant + B.3 plugin API + B.5 enterprise document ontology + G8.a-c mount + SDK.a-c trio | B.5.a-d ✅; B.1 audit + G3/G4/G5/G7 ✅; B.2/B.3 design memos ✅; G8.a-c ✅; SDK.a-c trio ✅ (#875 / #876 / #881); G8.d **LOI-blocked** |
| **C** — Measurement infra carry-over | v0.2.3b S3 cross-model + D-alce + D-2wiki + HR full sweep + arXiv submission + graph-RAG synthesis | Graph-RAG Step 1 ✅ (#864 / #877, +0.41 path_coverage ⭐⭐⭐ n=3); Step 2 driver scaffold ✅ (#885); all others **operator-attended** |
| **D** — LOI-gated (blocked) | Customer-specific NDA/DPA/MSA + ingestion + pilot kickoff + vertical pack (legal) + G8.d capability grant workflow + F.2 CR.e customer theming | **BLOCKED** until LOI signed (Fork A of v0.6 entry contract) |

### Additional surfaces landed post-close (not in original v0.5 stream definitions)

- **Track F.1 — Time-Travel Dashboard quartet** (#865 / #878 / #879 / #880): TT.a timestamp picker + TT.b corpus-state diff renderer (audit replay overlay) + TT.c reasoning trail replay at time T + TT.d now-vs-T diff view modal. Surfaces v0.4.2 T5 `reconstruct_graph_at` + v0.5 G3 `reconstruct_corpus_view_at` + `replay_audit` primitives as a single operator dashboard.
- **Track F.2 — Change Review Workspace quartet** (#866 / #867 / #873 / #874): CR.a list page + CR.b detail modal with diff renderer + CR.c contradiction-arbiter visualisation + CR.d approve/reject buttons with G2.a evidence capture wire.
- **Track C — CSP nonce middleware** (#884): `core/security/csp_nonce.py` per-request nonce primitive + `build_security_headers` composition seam + `request.state.csp_nonce` middleware wire-in. `script-src` flag safe today; `style-src` flag reserved for UI #6 inline-style migration.

### Rule discipline (preserved + new)

| Rule | Status at 2026-06-13 |
|---|---|
| **CLAUDE.md rule #1** (no domain features until v1.0) | **PRESERVED across all 44 cycle + post-close PRs** — 4-layer protection contract (code-level capability gate + doc-level "Out of scope" + naming-level domain-agnostic + trigger-level LOI tagging) held throughout |
| **#2** (bench numbers + Quality Delta Card on core/ PRs) | Preserved (all 44 PRs touch UI / lifecycle primitives / security / SDK packaging / docs — none touch `core/retrieval` / `core/graph` traversal / `core/reasoning`) |
| **#3** (self-evolution opt-in) | Preserved |
| **#4** (architecture changes require `architecture` label) | Preserved |
| **#5** (`core/` 20 KB module size) | Preserved for NEW files; five legacy modules grandfathered (largest `core/reasoning/reflect.py` at 29.2 KB — split planned, tracked in v0.6 entry skeleton §5 NEW solo-doable items) |
| **NEW #6** Dogfooding evidence ≠ Dim F evidence | Hashevolution own-use = iteration feedback; Dim F still requires external customer pilot |
| **NEW #7** Enterprise ontology = mother-level | Vertical-pack (legal etc.) waits for LOI or v1.0; B.5 horizontal subtypes ✅ landed |
| **NEW #8** External-facing claims gated on measurement evidence | Zenodo DOI + result.json refs mandatory; Step 1 graph-RAG finding cites n=3 paired evidence per `feedback_n1_verdict_inflation_n3_caught` |

### Cycle entry → close deliverables (actual status)

- [x] v0.5 entry handover doc (`docs/handovers/v0.5-entry-2026-06-12.md`)
- [x] Pre-LOI material refresh (7 docs, PR #840)
- [x] Hashevolution own-company scenario doc (PR #840)
- [x] B.5.a-d enterprise document ontology (4 PRs, #841 / #842 / #843 / #844)
- [x] B.1 audit + 4 gap closures (G3 / G4 / G5 / G7) — 5 PRs (#845 – #849)
- [x] B.2 / B.3 design memos (G1+G2 multi-tenant contract / G8 plugin-API stability — 2 PRs, #850 / #851)
- [x] UI improvement stream (6 PRs, #852 – #858)
- [x] External evaluation disclosure (PR #857)
- [x] Server-side hardening (3 PRs, #859 – #861 — security headers + G1.a tenant-id + G2.a approval-evidence)
- [x] v0.5 close handover (PR #862, [2026-06-12 PM](handovers/v0.5-close-2026-06-12.md))
- [x] **Track A** G1.b replay-side tenant filter + G2.b CR merge wire-in + G1.c deployment guide + G2.c OIDC + asyncio variant (4 PRs, #869 / #870 / #882 / #883)
- [x] **Track B** G8.a-c ontology pack mount + SDK.a-c trio (6 PRs, #868 / #871 / #872 / #875 / #876 / #881)
- [x] **Track C** CSP nonce middleware (PR #884)
- [x] **Track F.1** Time-Travel Dashboard quartet (4 PRs, #865 / #878 / #879 / #880)
- [x] **Track F.2** Change Review Workspace quartet (4 PRs, #866 / #867 / #873 / #874)
- [x] Graph-RAG synthesis Step 1 + Step 2 scaffold (3 PRs, #864 / #877 / #885)
- [x] v0.6 entry preparation skeleton (PR #886) — bridges v0.5 close → v0.6 entry under 2-fork contract
- [ ] Stream A.3 operator: Hashevolution dogfooding start (**operator action**)
- [ ] Stream A.4 operator: Tier S contact list + outreach (**operator action**)
- [ ] Graph-RAG synthesis Step 2 cross-model measurement (~14 h wall, **operator-launchable** via `scripts/research/graph_rag_synth_step2_cross_model.py`)
- [ ] v0.2.3b LLM-grounded S3 cross-model run (**operator-attended**)
- [ ] D-alce real NLI verifier + paper v1.4 (**operator-attended**)
- [ ] HR full sweep n=100 (**operator-attended**)
- [ ] arXiv preprint submission (Path A defer; **pending operator outreach outcome**)

### v0.5 → v0.6 gate (Dim F)

**Dim F gate** (≥6 month external customer pilot + measured success
metrics per `docs/PLATFORM_READINESS.md` §3) is **NOT cleared**.
The 2-fork v0.6 entry contract from the
[v0.6 entry skeleton §4](handovers/v0.6-entry-skeleton-2026-06-13.md) governs:

- **Fork A** — LOI signed → Track D vertical pack scoping begins. G8.d capability grant workflow + F.2 CR.e customer theming unblock.
- **Fork B** — 6-month no-LOI → reassess strategy. v0.5 mother-platform work stays the baseline; v0.6 cycle re-scopes around the next strategic direction.

Until one resolves, mother-platform hardening continues; vertical content stays BLOCKED per CLAUDE.md rule #1.

---

## v0.6.x — Product hardening + restart (2026-06-13 → 2026-06-26; maintenance 2026-08; restart 2026-09-03)

**Status**: on `main`, **unreleased** (no tag, no DOI). This is not a
formal cycle — the v0.5 → v0.6 gate (Dim F) is still open, so the work
below is mother-platform product hardening carried out *inside* the
"v0.5 closed, v0.6 not yet entered" interval.

**Canonical state doc**:
[`docs/handovers/v0.6.2-restart-roadmap-2026-09-03.md`](handovers/v0.6.2-restart-roadmap-2026-09-03.md)
— read it before this section; per CLAUDE.md rule #6 it wins on any
disagreement.

### What landed (PRs #886 – #1078, ~190 PRs)

| Stream | PRs | Summary |
|---|---|---|
| Deployment hardening (P1 / P3) | #890 – #894 | trusted `X-Forwarded-*` (rate-limit bypass + audit IP spoof closed), HTTPS guide, per-request tenant middleware + workspace path resolver |
| Operator surfaces (P4) | #895 – #899 | onboarding flow, knowledge rollback, 3-swimlane reasoning-flow view, glossary + tooltips, Korean quickstart |
| Rule #5 split series | #900 – #908 | 7 oversize `core/` modules split into packages |
| Template-formatting engine | #909, #913, #916 | domain-agnostic form shaping (register → apply → download; md/txt/html/docx; image OCR). **Zero templates shipped** — rule #1 held |
| Agent track | #918 – #921, #1039 – #1047 | `core/agent_tools`, tool-use loop, agent chat panel, folder/model pickers, cloud Claude via Max-plan CLI, `run_shell` (default-OFF, admin-only) |
| LLM routing unification | #922, #961 – #977 | DB-first settings repo + admin UI, per-mode `DEFAULT_PREFERENCE`, 3-cell paired measurements per mode, measurement-environment isolation contract |
| Chat UX rebuild | #927 – #960 | Claude-style sidebar/sessions/favourites, typography, mobile readability, truncation guardrail, **SEKOS / JAMES naming split (#934)** |
| Privacy + cost cap | #980 – #988 | privacy gate + monthly cost cap, wired into cloud egress with defence-in-depth |
| UI consolidation 8 → 5 pages | #998 – #1017 | de-emoji, intro front door (`/` intro, `/chat` chat), graph hub tabs, workspace source-docs tab, answer→trace→graph loop, **visual-regression harness** |
| **Lifecycle live-consistency arc** | #1018 – #1027, #1033 – #1034 | probe proved live traversal ignored lifecycle `status` → `relation_is_live()` gate across traversal / score / T1 / 3D snapshot; time-travel isolation pinned; 0 active-relation loss |
| Backlog re-measurement | #1028 – #1032 | D-alce / HR N=100 (identical) / v0.2.3b (J−N +0.21) — no regression from the lifecycle filter |
| CSP + image ingest + long requests | #1062 – #1075 | 596 inline styles → classes, multi-file upload, `qwen2.5vl:7b` + `num_ctx` 8192, vision→OCR routing, `/query/`+`/upload/` heartbeat, detailed answer style |
| Citation + CI | #1077, #1078 | v0.3.3 DOI lineage correction, ruff F-class gate cleared |

### Invariant status — one sanctioned break

CLAUDE.md rules #1 (no vertical), #3 (self-evolution opt-in) and #4
(architecture label) held across the whole stream. Two notes:

- **Rule #2 / traversal streak — broken once, on purpose.** The
  lifecycle live-consistency arc changed `core/graph` traversal. It was
  probe-first (#1020 measured the defect), measurement-gated,
  kill-switch-equipped (`JAMES_DISABLE_STATUS_FILTER`), and re-measured
  against the LRB SUT backlog afterwards. Later documents must **not**
  restate "0 lines changed in `core/graph` traversal" for this period.
- **Rule #5 — resolved by #1080, one file grandfathered.**
  `core/response_style.py` (22,036 B) was split into
  `core/response_style_presets.py` with every public name re-exported and
  the presets verified field-by-field against the pre-split module.
  `core/reasoning/engine.py` (21,464 B) is grandfathered **with a split
  plan**: it lives in `core/reasoning`, so rule #2 requires STEP 7 bench
  numbers, which need a live server plus Ollama — an operator machine, not
  a session container. `tests/test_v06_module_size_gate.py` is green.

### Maintenance PRs #1079 / #1080 (2026-08-26 / 08-28)

Two post-idle maintenance PRs landed before this section was written:

- **#1079** — Ali Afana's four engineering findings (bidi override-span
  removal, non-ASCII numerics in `chat.js`, Arabic tatweel / presentation-form
  folding, sweep run-identity salt); a **uuid7 production defect**
  (`start_trace()` called `uuid.uuid7()`, stdlib only from Python 3.14 while
  `pyproject` declares >=3.10 and CI pins 3.11 — it raised `AttributeError`
  on every supported interpreter, taking down the `/query/` edge for any
  caller not minting its own `trace_id`; invisible because browsers always
  send one and `test_observability.py` is on the CI ignore list); and an
  Arabic-pipeline capability audit — `detect_language` scores Arabic zero and
  falls through to the Korean branch, three tokenisers then yield zero tokens
  — **recorded as evidence for a v0.6 scope conversation, not fixed**.
- **#1080** — CI worked cause by cause: FastAPI 0.141.1 / starlette 1.6.0
  append an `_IncludedRouter` wrapper per `include_router`, and the wrapper
  has no `path`, so 19 wrappers hid ~137 endpoints from every
  `{r.path for r in app.routes}` assertion (unwrapping now lives once in
  `tests/_app_routes.py`); the two rule #5 violations resolved; a probe that
  overwrote a tracked measurement report on every suite run; two real UI
  defects. The run log at that head reads **5 failed, 4,368 passed**.

### Known-red CI (reduced)

`.github/workflows/test.yml` (pytest) still fails on `main` — latest run
2026-08-28 — but at **5 failures / 4,368 passed / 6 skipped** (read from
the run log, not estimated). `ruff` and `bandit` are green. The five:
one LRB S2 reproduction mismatch (test expects R@1 0.7125, the run yields
0.6875, and the README documents 0.688 — an adjudication the roadmap says
to settle from committed artifacts before touching either side); three
`FixtureLockTest` cases that require `workspaces/hotpot_eval/eval/`, which
`.gitignore` excludes, so they cannot pass in CI as written; and one
`mobile.css` `!important` count (29 against a 25 ceiling). The
deterministic benchmark tier (`bash benchmarks/run_all.sh`) is
unaffected; the LRB item is the one to watch, since it touches a
published number.

### Restart plan (Phase 1 – 7)

Detailed in the restart roadmap §2; summarised here:

| Phase | Name | Owner | Blocked by |
|---|---|---|---|
| 1 | Documentation-currency restore + recurrence guard | solo | — (**done 2026-09-03**) |
| 2 | CI green restore (P0 — blocks new features; scope reduced by #1080) | solo | Phase 1 |
| 3 | Idle-debt closure (mobile long-query drop, CSP enforce, OCR remainder) | solo + device check | Phase 2 |
| 4 | v0.6.1 formal cycle close (handover + release notes + tag) | solo | Phases 2, 3 |
| 5 | Measurement backlog (graph-RAG Step 2 cross-model, v0.2.3b matrix, D-alce, arXiv) | operator-attended | Phase 2 |
| 6 | **Fork A / Fork B strategy decision** (decision point ≈ 2026-12-13) | **operator** | — |
| 7 | v0.6 formal entry | per fork | Phases 4 + 6 |

---

## v0.5.0 — First Domain Pilot (Fork A of v0.6 entry contract)

**Theme**: prove the platform contract by running ONE real domain
in production for 6 months with one external customer. **Moved here
from v0.4** so Layer 4 governance lands first — see v0.4 retarget
rationale above.

> **Status note (2026-06-13)**: this section describes **Fork A** of
> the v0.6 entry contract (LOI signed → vertical pack scoping
> begins). v0.5 cycle close (above) shipped the **mother-platform
> infrastructure** that this fork builds on — G8.a-c ontology pack
> mount mechanism, G1/G2 SaaS-readiness primitives, SDK.a-c trio
> for third-party pack authors, Time-Travel Dashboard surface for
> audit operators. **The Dim F gate clock starts only when a
> customer LOI is signed**; until then, v0.6 cycle entry waits on
> the operator's decision per the [v0.6 entry skeleton §4](handovers/v0.6-entry-skeleton-2026-06-13.md).

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

### Scalability — vector compression tier (trigger-gated, NOT version-scheduled)

**Entry trigger** (none of which is currently met): a real deployed
corpus whose float32 vector index exceeds available RAM — concretely
**> ~1M documents** at the default 384-dim, or a pilot that measures a
vector-store memory bottleneck. Until a trigger fires this stays a note,
not work: at 384-dim even 1M docs ≈ 1.5 GB fits the reference 32 GB
machine, so adopting compression now would be optimization against an
**unproven premise** (cf. the cloud-tier S6/S7 shelving lesson).

**Priority ladder when the trigger fires** — ranked by
*(memory saved × recall kept) ÷ replay/audit cost*, not memory alone,
because byte-identical replay (RAB / `reconstruct_graph_at(t)`) is the
crown-jewel constraint:

- [ ] **1. Int8 scalar quantization** (~4×) — *replay-safe*: a fixed,
      audit-logged scale makes it deterministic; backend-agnostic
      (quantize at the embedding level before ChromaDB). First and
      lowest-risk. Entry PR must paste a 5-axis Quality Delta Card
      (rule #2) — the "Recall within 1%" claim is re-measured on JAMES's
      own QVT/LRB queries, not imported from the literature.
- [ ] **2. Dimensionality reduction** — requires a **model swap** (the
      default `paraphrase-multilingual-MiniLM-L12-v2` is multilingual
      and **not** Matryoshka, so head-truncation is unsafe). Forces full
      re-ingestion + **KO/EN bilingual re-validation** (bilingual
      regression has bitten before — see `feedback_d2_v2_softener_bilingual_regression`).
      Separate measurement cycle.
- [ ] **3. FAISS IVFPQ** (~10–100×) — strongest memory win but the
      **trained codebook is a replay liability**: historical replays must
      pin their era's codebook. Also a **backend change** (ChromaDB →
      FAISS = trust-boundary / `docs/ARCHITECTURE.md` PR, rule #4).
      Architecture decision precedes any build.
- [ ] **4. Binary + rescoring** — only at very large scale; keeps float32
      for rescore (so the "32×" is index-only), and rescore ordering must
      be made deterministic for audit reproducibility.

Rule #1 is not implicated (horizontal infra, not a domain feature) — this
is a *priority/trigger* question, not a permission one.

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

**Last updated**: 2026-09-03 — **문서 최신성 복구 + 재개 로드맵**.
약 2 개월 유휴 (마지막 기능 세션 2026-06-26, 마지막 커밋 2026-08-19) 후
루트 문서 6 종이 서로 다른 시점에 멈춰 있던 것을 동기화하고, 위의
`v0.6.x` 섹션 + [restart roadmap](handovers/v0.6.2-restart-roadmap-2026-09-03.md)
를 단일 진실원으로 세웠습니다. 신규 CLAUDE.md rule #6 (상태는 한 곳에만) +
entry-pointer 가드의 recency 불변식이 재발을 막습니다. 이번 갱신에서 처음
문서화된 사실: **`main` CI (pytest) 가 2026-06-22 이후 계속 실패** (단
#1080 이후 CI 실패는 5 건) — 재개 Phase 2 가 이를 초록으로
되돌리기 전까지 신규 기능 금지.

**Prior update (2026-05-22)**: **v0.4 retarget to Layer 4
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
