# Changelog

All notable changes to PROJECT JAMES will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.0-alpha.2] — 2026-05-25 — v0.4 alpha bundle (Sprint 2 UI consistency + Sprint 3 plumbing & 5-stage D1 surface)

**Theme**: first alpha tag of the v0.4 cycle — the deliverable between v0.3.x closure (v0.3.3, D6 retry wiring) and the v0.4.0 final Layer 4 main theme (Lifecycle Semantics, Sprint 5). Two sprints of stabilisation work bundled into one citable archive. **Default-off invariant preserved** across all D1 / D5 flags: production fleets pulling alpha.2 see zero behaviour change relative to v0.3.3.

### Sprint 2 — UI consistency bundle (5 PRs)

- **#496 admin character profile page i18n consistency** — 38 new `char.*` keys + `window.onLangChange` dynamic re-render hook + `data-i18n="char.card.{core,values,style}"` on the summary card frame. Closes the long-standing bug where `buildCharacterSummary` / `renderConnectionsPanel` rendered Korean strings in EN mode (root cause was one layer below the existing `label_key` contract). `tests/test_i18n_char_keys_parity.py` (3 tests) pins EN↔KO `char.*` key parity + no orphan `t('char.…')` calls.
- **#497 chat sidebar hover auto-expand** — CSS-only sibling + self `:hover` rule on `.sidebar-open-btn` / `.sidebar.collapsed`. Click-toggle UX preserved untouched.
- **#498 always-visible chat model indicator chip** — new `GET /llm/active` endpoint (api_key only, not admin-gated) returns `{tag, source, warning}` from `resolve_chat()`. Chip in `index.html` header populated via `loadActiveModelChip()`; `data-source` attribute drives edge colour for non-default resolution (`preference` / `any` / `none`).
- **#499 chat-side model picker popover** — chip click opens popover listing installed models (aggregated from `MODE_OPTIONS`). Selection writes to `selectedModel` (per-session override) + `localStorage`. Resolution priority unchanged: per-call (`selected_model` param) > env (`config.GEMMA_MODEL`) > preference list > any > none.
- **#500 sticky top navigation on scrolling pages** — admin / workspace headers get `position:sticky; top:0; z-index:50`; chat / graph keep their `overflow:hidden` viewport pattern. `tests/test_header_sticky_parity.py` (4 tests) pins the per-page policy with negative assertions so a future refactor that "fixes the inconsistency" by adding sticky to chat / graph fails CI.

### Sprint 3 — Plumbing closure (5 PRs + 2 follow-ups)

- **#501 BL-1 emit_trace_step stdout mirror** — single-line `[reason:<stage>] applied_rule · backend · latency [trace abc12345] [err=…]` mirror lives inside `emit_trace_step` itself, so every caller (synth + planner + reflect + verify + retrieve + rerank + tool) gets the same console signal. Convention matches `observability.emit_step`: `JAMES_TRACE_STDOUT` default ON; `"0"` / `"false"` / `"no"` / empty silences. Closes `feedback_stdout_vs_audit_log_trace_split`.
- **#502 BL-2 attributes.summary legacy field cleanup** — `_ingestion.py` stops mirroring `description` into `attributes.summary`; `_frontmatter.py` defensively strips any caller-passed `attributes.summary` before frontmatter dump. Read fallback kept for legacy disk files. New wiki writes converge on the canonical top-level `summary`.
- **#503 D1 stage expansion #7a planner** — `Planner.__init__` accepts `max_tokens: Optional[int]` + `budget: Optional[TaskBudget]`. Per-call cap resolution: explicit int / `adaptive_budget_enabled() + TaskBudget.assess("planner", query)` / fall-back default. `backend.complete` → `complete_with_retry(stage="planner")`.
- **#504 D1 stage expansion #7b reflect** — `ReflectionLoop` critique + revise sub-stages share `TaskBudget.assess("reflect", query)` when both `*_max_tokens` are `None` and D1 is on. `complete_with_retry(stage="reflect")` wired through `_call`.
- **#505 D1 stage expansion #7c verify** — `Verifier.__init__` accepts `fact_check_max_tokens: Optional[int]` + `budget`. `_fact_check` routes through `assess("verify", query)` when D1 is on. D5 grounding-critical escalation (D5.C.1 rule 1) composes with D1 cap signal — both fire independently into the router policy + retry helper.
- **#506 follow-up** — `test_verifier.py::ANSWER_KO` fixture rebalanced under PR #495 (Sprint 1 #2) dominant-script `is_korean` contract. The fixture had ~24 Hangul + ~34 English alpha chars — English-dominant under the new rule, so the verifier's `_format` took the EN branch and the `"검증:"` assertion broke. Rebalanced to ~50 Hangul + 3 ASCII (`RAG`).
- **#507 follow-up** — `query_rewriter` local `_adaptive_budget_enabled()` migrated to `core.reasoning.budget.adaptive_budget_enabled` so all 5 reasoning stages read the D1 opt-in flag through one function.

### After v0.4.0-alpha.2 — 5-stage D1 surface uniform

| Stage | D1 cap | D6 retry | Router signal |
|---|---|---|---|
| `query_rewriter` | ✅ (v0.3.1 / PR #461) | ✅ (v0.3.3 / PR #486) | budget signal under D1 on |
| `synth` | ✅ (v0.3.1) | ✅ (v0.3.3, via `trace_synth_call`) | budget signal under D1 on |
| `planner` | ✅ (v0.4.0-alpha.2 / PR #503) | ✅ (v0.4.0-alpha.2) | budget signal under D1 on |
| `reflect` | ✅ (v0.4.0-alpha.2 / PR #504) | ✅ (v0.4.0-alpha.2) | budget signal under D1 on |
| `verify` | ✅ (v0.4.0-alpha.2 / PR #505) | ✅ (v0.4.0-alpha.2) | budget signal + grounding-critical |

### Default-off invariant verified

Every wiring landed in v0.4.0-alpha.2 stays gated behind `JAMES_ADAPTIVE_BUDGET=1`. Without the env opt-in, every reasoning stage hits the pre-#7a cap (4096 / 1024) byte-identically. The router signal in budget-aware mode is also a no-op under flag-off — `_budget_for_router` is `None`, so policy rules 1 / 4 don't fire on a fake CAP_HEAVY value.

### Verified

- 12 PRs land green on `pytest` for the changed surface + broader regression (planner / reflect / verify / query_rewriter / router / budget / trace / chip wiring / sticky parity / i18n parity).
- New tests added across the bundle: `test_i18n_char_keys_parity.py` (3), `test_llm_active_endpoint.py` (8, including ChipPickerPopoverTests), `test_header_sticky_parity.py` (4), `test_emit_trace_step_stdout_mirror.py` (6), `test_attributes_summary_cleanup.py` (3), `test_planner_d1_wiring.py` (8), `test_reflect_d1_wiring.py` (6), `test_verify_d1_wiring.py` (6).
- No `core/` file exceeds 20 KB after the bundle. `verify.py` approached the cap at 21.4 KB during #7c development; trimmed docstrings landed it at 19.2 KB — split is the next-action for any further verify additions (extract `_verify_security` / `_verify_fact_check`).
- ruff / hooks clean on every PR.

### Operator action

GitHub release publish triggers Zenodo automatic mint. The minted DOI for v0.3.3 will be supplied by the operator at v0.4.0-alpha.2 publish time and added as `isNewVersionOf` in the next deposit; the chain back to v0.3.2 / v0.3.1 (specific DOIs `10.5281/zenodo.20372649` / `10.5281/zenodo.20363998`) stays explicit in `related_identifiers` as `isDerivedFrom`.

### Out of scope for v0.4.0-alpha.2 (Sprint 4-5 follow-up)

- **Sprint 4 retrieval quality** — BL-9 embedding model swap (`paraphrase-multilingual-MiniLM-L12-v2` → `bge-m3` / `multilingual-e5-large`). Re-embeds all chroma chunks. Cross-lingual diagnostic fixture (`feedback_rag_cross_lingual_diagnostic` memory) is the test bed.
- **Sprint 5 Layer 4 main theme** — T1 Lifecycle states + T2 Event-driven transitions + T7 Cross-workspace federation primitives. The architectural shift planned for v0.4.0 final.
- `verify.py` module split (19.2 KB, approaching 20 KB cap; extract `_verify_security` / `_verify_fact_check` on next addition).
- `docs/ARCHITECTURE.md` LLM-model authority chain documentation polish (Sprint 2 #3c).
- admin sidebar collapsed-state parity (Sprint 2 #5b) — bundled with sticky-nav follow-up when needed.

---

## [0.3.3] — 2026-05-25 — D6 retry-wiring follow-up cycle closure (D1 design/wiring gap closed)

**Theme**: close the design ↔ wiring gap surfaced by the 2026-05-25 user diagnostic question (*"does D1 7-tier cover all cases / what about exceptions?"*). The `retry_doubled` helper that existed since v0.3.1 (D1 closure) but was never invoked from any production call site is now wired through `complete_with_retry`. Truncation triggers single retry up to `CAP_HEAVY`. `audit_log reason:retry` row records every retry decision. Native Ollama `done_reason` replaces the heuristic when the provider exposes it (heuristic preserved as fallback for cache hits / Ollama < 0.1.30 / non-Ollama providers).

Three-PR sequence (#486 + #487 + #488) plus two operator-trail PRs (#489 launch-tracker rows + #490 README DOI badge bump to v0.3.2).

### Added — `complete_with_retry` helper (PR #486)

- `core/reasoning/budget.py:complete_with_retry(backend, prompt, *, cap, max_cap=CAP_HEAVY, timeout, stage="", **opts)` — single retry on `done_reason="length"`, bounded by `max_cap`. `opts` forwarded both calls. Added to `__all__`.
- `core/reasoning/backends/__init__.py` — `CompletionResult.done_reason: str = ""` field. Backward compat: backends without the attribute are tolerated (helper falls back to no-retry).
- `core/reasoning/backends/ollama_local.py` — length-+-terminator heuristic. Two signals must fire to mark `"length"`: response length ≥ 90% × `max_tokens` × 4 chars AND no sentence terminator (`.`, `?`, `!`, `다`, `요`, `음`, `}`, `]`, `"`, `'`, `)`). Conservative — biased to false negatives.
- `core/retrieval/query_rewriter.py` — `backend.complete(...)` → `complete_with_retry(...)` at the only call site where retry can actually fire (D1 wired stage with dynamic cap signal under `JAMES_ADAPTIVE_BUDGET=1`).
- 14 contract tests in `tests/test_complete_with_retry.py` covering retry trigger / no-retry conditions / cap saturation / custom max_cap / backend-without-`done_reason` / opts forwarding / ollama heuristic edge cases.

### Added — `audit_log reason:retry` emission (PR #487)

- `complete_with_retry` drops one `reason:retry` row to `audit_log` every time a retry actually fires.
- Schema: `endpoint="reason:retry"`, `target=stage` (or `backend_id` when stage empty), answer column auto-serialized JSON `{"cap_before": <int>, "cap_after": <int>, "backend": "<id>", "prompt_hash": "<8 hex>"}`.
- Operator monitoring channel: `SELECT endpoint='reason:retry' FROM audit_log` shows retry rate / stage distribution / backend distribution for new fail-case discovery + heuristic false-positive rate tracking.
- Audit emission is try/except-wrapped — never blocks production.
- 5 new tests pinning the emit / no-emit conditions + reason label correctness + audit-failure-survives-retry.

### Added — native Ollama `done_reason` exposure (PR #488, 4-layer additive)

- `core/gemma_client.py` — `GemmaClient._last_done_reason` instance attribute populated from `resp.json().get("done_reason", "")`. Reset at the top of `call_gemma` so a cache hit / early-return path doesn't leak the prior call's signal.
- `llm/base.py` — `BaseLLM.generate_meta(messages, **kwargs) → dict` default implementation wraps `generate(...)` into `{"text": str, "done_reason": ""}`. Providers that don't override get graceful fallback.
- `llm/providers/ollama_client.py` — OllamaClient holds a single GemmaClient instance (`_gemma_client` lazy-initialized via `_client()`). `generate_meta` returns `{"text": ..., "done_reason": client._last_done_reason}`.
- `llm/router.py` — `call_router_meta(prompt, task_type=None, **kwargs) → dict` mirrors `call_router`. `RouterWrapper.call_gemma_meta` is a thin shim. Hard fallback path reads `GemmaClient._last_done_reason` after the direct `call_gemma` call.
- `core/reasoning/backends/ollama_local.py` — `complete()` tries `router.call_gemma_meta` first (callable + dict-return check); on absent / non-dict / exception, falls through to legacy `call_gemma` + heuristic.
- 12 new tests in `tests/test_native_done_reason.py` covering BaseLLM default + OllamaClient stash read + RouterWrapper shim + `call_router_meta` + ollama_local preference order + heuristic fallback + GemmaClient reset.

### Added — operator trail (PRs #489 + #490)

- `reports/promo-assets/launch-tracker.md` — 3 new audit-trail rows (D5 cycle CLOSED catalog + v0.3.2 GitHub release published + D6 retry-wiring follow-up cycle).
- `README.md` / `README.ko.md` — Status badge v0.3.1 → v0.3.2 + DOI badge `10.5281/zenodo.20363998` → `10.5281/zenodo.20372649`.

### D1 safety net status — all backed

| # | Net | Pre-D6 | Post-D6 |
|---|---|---|---|
| 1 | `retry_doubled` fallback | Definition-only, no wiring | **Wired via `complete_with_retry` (query_rewriter) + audit `reason:retry` + native Ollama `done_reason` precision** |
| 2 | Falsification cycle | Measurement-driven heuristic evolution | + `audit_log reason:retry` row pile-up is now the monitoring channel for new fail-case discovery |
| 3 | flag-off default | Pre-D6 byte-identical | Pre-D6 byte-identical (`JAMES_AUTO_ROUTER` / `JAMES_ADAPTIVE_BUDGET` both default OFF) |
| 4 | Heuristic asymmetry | Half-effective (escalate but no retry) | Fully backed — escalate path retries on truncation, native signal where available |

### Verified

- Final state: **587 backend/router/budget/rewriter/graph/reflect/verify/alias/retry/gemma/done regression tests pass**.
- 31 new D6 contract tests across 2 files (`test_complete_with_retry.py` 19 + `test_native_done_reason.py` 12).
- ruff clean on all touched files.
- Module sizes all under the 20 KB gate.

### Out of scope for v0.3.3

- **Native `done_reason` for other providers** (Claude / DeepSeek) — 3-condition gated (operator opts into `JAMES_ENABLE_CLAUDE_BACKEND=1` + `JAMES_AUTO_ROUTER=1` + observed `reason:retry` rows with that backend > 0). Memory: `feedback_d1_d5_retry_doubled_wiring_gap.md`.
- **planner / reflect / verify wiring through `complete_with_retry`** — these stages currently use a fixed `self._max_tokens = 4096` which is already at the `CAP_HEAVY` ceiling, so retry would be no-op. Wiring lands together with the D1 budget signal expansion (v0.4 follow-up).
- **D2 task-weight metric in measured form** — absorbed into D5 as the policy's heuristic classifier; revisit as a measured metric if the heuristic plateaus on production bench.
- **Cost-based scoring v2** / **per-pack policy** / **per-stage explicit override under D5 ON** / **embedding swap (BL-9 bge-m3 / multilingual-e5-large)** — v0.4 follow-ups.
- **D3 / D6(I)** — cross-family generalization + joint paper consolidation remain queued for the mid-June Robin / Ali Gemini collaboration window.

### Acknowledgements

- The 2026-05-25 user diagnostic question (*"7단계 사다리로 나누는 것이 전부 커버가 되나? 예외가 발생할 가능성이 제로는 아닐 것 같은데"*) directly motivated this cycle. The honest engineering response — admit the gap, ship the wiring, add the monitoring channel, swap the heuristic for native signal when available — followed in three small PRs over the same session.
- D1 (`core/reasoning/budget.py`, v0.3.1) defined the `retry_doubled` helper that v0.3.3 finally activates. The 7-tier natural-stop gradient remains the measurement baseline.
- D5 (Auto-routing, v0.3.2) shares the `audit_log` infrastructure: `reason:route` (D5.C.2.a, PR #478) + `reason:retry` (this cycle, PR #487) together give operators a complete picture of every routing decision plus every truncation retry.

---

## [0.3.2] — 2026-05-25 — Direction 5 (Auto-routing on Provider Contract) cycle closure

**Theme**: ship a per-call backend-selection layer above the Provider Contract. Every production LLM call path now consults a router that picks backend by task weight + stage type. Default OFF; opt-in via `JAMES_AUTO_ROUTER=1`. Byte-identical to pre-v0.3.2 at the production call path when the flag is unset. 10-PR sequence (#474–#484) merged in a single 2026-05-25 session.

### Added — `core/reasoning/router.py` (Router + policy + helpers)

- New `core/reasoning/router.py` (~12 KB) providing:
  - `Router(*, enabled=None)` — env-flag-gated (`JAMES_AUTO_ROUTER`). Default OFF.
  - `Router.select_backend(stage, prompt, *, context, budget_signal) → str` — dispatches to `_route_policy` when flag-on, returns `_legacy_backend_id()` when flag-off.
  - `_route_policy` — 4-rule decision tree: (1) `stage == "verify"` (grounding-critical) → prefer `large` → `medium` → legacy; (2) `budget_signal == CAP_SUBSTITUTION` → prefer `small` → legacy; (3) `budget_signal == CAP_HEAVY` → prefer `large` → `medium` → legacy; (4) otherwise (CAP_LIGHT / None / unknown) → legacy.
  - High-level stage-call-site helpers: `resolve_backend`, `emit_route_event`, `_budget_to_tier_label`. `resolve_backend` returns `fallback_backend_id` when flag-off (byte-identical); under flag-on, the router is the authority — stage-level `self._backend_id` is intentionally overridden.

### Added — `BackendCapability(tier, provider)` metadata

- `core/reasoning/backends/__init__.py` extended with `BackendCapability` frozen dataclass, `UNKNOWN_CAPABILITY` sentinel, `get_backend_capability(name)`, and `list_backends_by_tier(tier)`.
- `tier` ∈ `{small, medium, large}` (model-size class); `provider` ∈ `{local, sovereign, cloud}` (deployment surface). Free-form strings — plugin backends can declare niche tiers without modifying core.
- Two builtin backends declared: `ollama_local` = `BackendCapability(tier="small", provider="local")`; `claude_code_cli` = `BackendCapability(tier="large", provider="cloud")`.
- Backward compat: backends without `capability` → `UNKNOWN_CAPABILITY`, treated as fallback only (not preferred by policy).

### Added — 5-stage wiring (every production LLM call path)

- `core/retrieval/query_rewriter.py` (D5.C.2.a) — first stage wired. cap computed first → fed to router as `budget_signal` only when D1 `JAMES_ADAPTIVE_BUDGET=1` is also on. Audit row every successful resolve.
- `core/reasoning/planner.py` (D5.C.2.b) — same pattern, `budget_signal=None` (planner not D1-wired).
- `core/reasoning/reflect.py` (D5.C.2.c) — single backend resolve serves both critique + revise passes.
- `core/reasoning/verify.py` (D5.C.2.d) — grounding-critical stage, `reason="grounding-critical"` audit label. The stage where a small-tier-only fleet sees routing actually take effect when operator opts into a larger backend.
- `core/reasoning/trace_helpers.py:trace_synth_call` (D5.C.2.e) — L1 unified entry point. `resolve_backend_for_stage(stage)` result becomes `fallback_backend_id` for `resolve_backend(...)`. Closes the 5-stage surface.

### Added — `audit_log` `reason:route` rows

- Per successful resolve, one row recording `(stage, prompt_hash[:8], selected_backend, budget_tier_label, reason)`. `reason` values: `auto` (D1+D5 both on), `fallback` (D5 on, D1 off), `grounding-critical` (verify stage escalation), `policy` (helper default).
- Audit emission is try/except-wrapped — failure never blocks production.

### Added — `core/entity_alias_pack.py` (cross-lingual entity resolution, D5.D)

- New `core/entity_alias_pack.py` (~3.6 KB) — `_ENTITY_ALIAS_PACK` list of ~30 high-traffic entities with bidirectional KO↔EN surface forms (Palantir, Tesla, Nvidia, Apple, Microsoft, Google, Meta, Amazon, Anthropic, OpenAI, AMD, BYD, BlackRock, Citi, Archer, Bouygues, Cursor, Claude, FOMC, Federal Reserve, White House, Pentagon, …).
- `core/graph_engine.py:build_entity_map_snapshot` augmented — after the wiki-frontmatter pass, iterate the alias pack and augment the snapshot with KO↔EN surface forms (silent skip when the canonical name has no matching wiki entity).
- Pairs with the v0.3.1 follow-up PR #472 `_SYNONYM_MAP` keyword expansion: two layers, same KO↔EN problem, different pipeline stages (query expansion vs graph entity resolution).
- Backward compat: wiki frontmatter `aliases:` takes precedence (first-write); removing the pack reverts to v0.3.1 alias-from-frontmatter-only behavior.

### Added — closure documentation

- `docs/handovers/v0.3.x-direction5-auto-routing-track.md` (PR #474, 213 lines) — design memo with scope / phase plan / STEP 7 bench plan / Build-don't-broadcast principle application.
- `docs/ARCHITECTURE.md` §5.7.8 (PR #484) — D5 routing layer + activation flag + decision tree + authority model + audit row schema + cross-lingual entity resolution.
- `reports/promo-assets/v3prime-direction5-router-result.md` (PR #484) — closure result doc: 10-PR catalog + acceptance (bench-neutral by design) + operator-run STEP 7 procedure for 3 scenarios + "what this closure does NOT claim" + cross-Direction map.
- `ROADMAP.md` Direction 5 `[ ]` → `[x]` with 10-PR sequence.

### Verified

- All wiring PRs land on test-level invariance (flag-off byte-identical). 526 backend / router / graph / entity / rewriter / reflect / verify regression tests pass on the full D5 surface.
- 74 new D5-specific contract tests across 5 files (`test_router_skeleton.py` 23 + `test_backend_capability.py` 14 + `test_router_policy.py` 14 + `test_query_rewriter_router_wiring.py` 11 + `test_entity_alias_pack.py` 12).
- Module sizes all under the 20 KB gate: `router.py` ~12 KB, `entity_alias_pack.py` ~3.6 KB, `graph_engine.py` +29 lines.
- ruff clean on all touched files.

### Operator-run STEP 7 sweep (any time)

The result doc documents a 3-scenario procedure: (1) baseline with flag OFF; (2) treatment with flag ON, only `ollama_local` registered — expected match baseline (all routing falls back to legacy with `reason:route` audit row pile-up); (3) treatment with flag ON + `JAMES_ENABLE_CLAUDE_BACKEND=1` — verify stage routes to Claude on every call, expected latency ↑ + grounded=true rate ↑. Acceptance: no grounded=true rate regression at any tier in scenario (2).

The cross-lingual diagnostic ("팔란티어가 뭐야?" → wiki entity `palantir_technologies__pltr_` matching) was the 2026-05-25 root cause this release closes at the graph layer.

### Out of scope for v0.3.2

- **Cost-based routing scoring v2** — current 4-rule heuristic stays. Token price × latency × quality weighted score is a v0.4 follow-up.
- **Per-domain-pack policy** — v0.5 Domain Pilot scope.
- **Per-stage explicit override under D5 ON** — when the router flag is on, stage-level `self._backend_id` is intentionally overridden; a flag-aware per-stage override mechanism is a v0.4 follow-up.
- **Embedding model swap** (BL-9) — bge-m3 / multilingual-e5-large for global retrieval quality is v0.4 retrieval-rework cycle backlog.
- **Direction 2 (task-weight metric) as a paper** — absorbed into Direction 5 as the policy's heuristic classifier (Build-don't-broadcast principle).
- **D3 / D6(I)** — cross-family generalization + joint paper consolidation remain queued for mid-June Robin / Ali Gemini collaboration window.

### Acknowledgements

- Direction 1 (`core/reasoning/budget.py`, v0.3.1) provided the `budget_signal` input the router consumes — this release stands on the 7-tier natural-stop gradient ground truth.
- The Build-don't-broadcast principle (memory: `feedback_build_dont_broadcast`) was applied throughout: D5 is a product cycle, not a research cycle. No public broadcast, no Robin coupling. Single Ali design-preview DM at D5.0 merge.

---

## [0.3.1] — 2026-05-24 — Direction 1 (Adaptive Budgeting) cycle closure

**Theme**: ship the dynamic-token-budget mechanism as a **data-bearing experiment artifact**, not a runtime change. Default OFF; opt-in via `JAMES_ADAPTIVE_BUDGET=1`. Three publishable findings + one process finding on `gemma4:e4b` at T=0.2, validated by two A/B sweeps × N=20/cell × 7 task-weight tiers.

### Added — `core/reasoning/budget.py` (TaskBudget module)

- New `core/reasoning/budget.py` (~7.2 KB) providing `TaskBudget.assess(stage, prompt) → int` with a 3-tier heuristic: `CAP_SUBSTITUTION = 200`, `CAP_LIGHT = 1200` (v2; bumped from 800 on 2026-05-24 after the cognitive-stages sweep showed reflect/verify natural-stop ~926/~984), `CAP_HEAVY = 4096`. Fallback: `retry_doubled(prev_cap)` for `done_reason=length` retry, bounded by `CAP_HEAVY`.
- 40 unit tests in `tests/test_adaptive_budget.py` pin every tier value, every regex branch, and the retry helper contract.

### Added — `core/retrieval/query_rewriter.py` adaptive-budget wiring (default OFF)

- `QueryRewriter.__init__` accepts an optional `budget: TaskBudget` arg and `max_tokens=None` default. Cap resolution is three-way: (1) explicit `max_tokens=int` → fixed cap (experiment baseline), (2) `None` + `JAMES_ADAPTIVE_BUDGET=1` → dynamic via `TaskBudget.assess()`, (3) `None` + flag off → `DEFAULT_MAX_TOKENS=4096` (byte-identical legacy).
- `JAMES_ADAPTIVE_BUDGET` env flag, **default OFF**. 5 default-off invariant tests in `tests/test_query_rewriter.py` prove byte-identical pre-v0.3.1 behaviour for any operator who has not opted in.
- Stdout trace `[budget] query_rewriter cap=N reason=...` when both `JAMES_ADAPTIVE_BUDGET=1` and `JAMES_TRACE_STDOUT=1` (default ON via `core/observability.py` convention).

### Added — research drivers + result docs (experiment-grade artifacts)

- `scripts/research/v3prime_direction1_adaptive_budget.py` — 3-prompt A/B driver (substitution/light/heavy), 120 calls/N=20, same fixture as V3'.e (PR #440 / PR #453). V3' Protocol v1 schema with two additive fields (`adaptive_cap_requested`, `adaptive_decision_reason`).
- `scripts/research/v3prime_direction1_cognitive_stages.py` — 4-stage cognitive A/B driver (query_rewriter / planner / reflect / verify) using production prompt templates imported from the live modules. 160 calls/N=20.
- `reports/promo-assets/v3prime-direction1-adaptive-budget-result.md` — 3-prompt sweep result.
- `reports/promo-assets/v3prime-direction1-cognitive-stages-result.md` (NEW) — full v1 vs v2 comparison + per-cell detail + 2 sub-findings (verify clustering + 7-tier gradient) + Direction 1 final closure.
- `reports/research-runs/v3prime-direction1-adaptive-budget-20260524T050347.json` — 3-prompt raw data (120 calls, 0 failures).
- `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T054634.json` — cognitive v1 sweep (CAP_LIGHT=800; falsification data — exposed reflect/verify truncation).
- `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T061858.json` — cognitive v2 sweep (CAP_LIGHT=1200; PASS data — 0/20 truncation on every cell, quality 20/20 restored).

### Findings — three publishable + one process

1. **Cap is a ceiling, not the floor**. `gemma4:e4b` naturally stops well below 4096 on every measured tier; cap reduction → 0% token change, but +7-17% latency win on substitution/light tiers (Ollama KV-cache buffer sizing) + ~20× per-call memory allocation reduction on substitution + bounded emergency-exit guard. PR #399's lifted cap was *permission to finish*, not waste.
2. **7-tier monotonic natural-stop gradient** spanning 62 → 1681 tokens on `gemma4:e4b` at T=0.2. 27× dynamic range, cross-sweep noise within 5% per tier. The quantitative form of the joint-paper sub-clause *"the workload gradient is multi-tier monotonic on a single model"*.
3. **`verify` is a high-clustering cognitive stage** (~12.5% unique baseline responses across 40 calls, stable across two independent sweeps). Direction 4 Mechanism 2 (answer convergence) now has **two axes**: workload weight + task type.
4. **Process finding** — heuristic v2 (CAP_LIGHT 800 → 1200) was data-driven by a falsification → revision → confirmation cycle.

### Joint paper sub-clauses now drafted

3-author headline holds verbatim: *"Substitution is free. Synthesis costs in proportion to what it has to invent."* Direction 1 closure adds three sub-clauses:

- *"…and inversely to parameter count."* (Robin axis-3 — 2 evidence layers)
- *"…and the gradient is multi-tier monotonic — 7 measured tiers spanning 27× dynamic range."* (JAMES Direction 1)
- *"…and answer convergence has a task-type axis: structured-JSON outputs cluster independent of workload."* (JAMES Direction 1, cross-sweep validated)

### Verified

- 71 unit tests pass (40 budget + 31 query_rewriter); ruff clean; `core/reasoning/budget.py` 7.2 KB / `core/retrieval/query_rewriter.py` 12 KB (CLAUDE.md rule #5 < 20 KB).
- Default-OFF invariant proven by 5 dedicated tests.
- Operator real-traffic signal: STEP 7 bench at intermediate commit `eccfc4d` passed within band [158.7, 413.7] @ 172.7 s — additional real-traffic robustness evidence beyond unit tests.

### PR references

- PR #461 — D1.A module + D1.B wiring (default OFF) + 3-prompt driver + cognitive-stages extension driver + first result doc.
- PR #463 — Heuristic v2 (CAP_LIGHT 800 → 1200) + v2 sweep PASS + closure result docs + 7-tier gradient documentation.

### Out of scope

- Flipping `JAMES_ADAPTIVE_BUDGET` default to ON — token-reduction hypothesis target unmet on `gemma4:e4b`; stays OFF.
- Production wiring of the 4 cognitive stages (planner / reflect / verify / synth) — cap-invariance removes urgency.
- Direction 2 (task-weight metric formalization), Direction 3 (cross-family generalization), Direction 5 (auto-routing) — separate cycles.

---

## [Unreleased] — v0.3.x patches

### Added

- **Working memory turn-end cleanup wired into `engine.query()`
  (Cognitive Phase 3 PR-10b)** — the public `query()` is now a
  thin try/finally wrapper that delegates to a new `_query_impl`;
  the finally block clears the turn's working-memory scratch and
  releases the session ContextVar on every return path, including
  exception unwinds and the early `_blocked_result` returns from
  `pre_check`. Before this PR, a crashed turn or a pre_check
  rejection could leave the session ContextVar bound at the thread
  level — the next request reusing that thread would have
  inherited a stale `(session_id, turn_id)` until
  `set_session_context` ran again. Working memory had no production
  call sites yet (PR-10a infra-only), but the same cleanup invariant
  now holds end-to-end before the wiring sites are added in a
  future PR. 3 new integration tests in `tests/test_working_memory.py`
  lock the contract (normal return, exception, early blocked
  return). `tests/test_chat_mode_picker.py::test_engine_query_validates_override`
  updated to scan both `query()` and `_query_impl` for the override
  whitelist since the validation logic now lives in `_query_impl`.

- **Working memory infrastructure (Cognitive Phase 3 PR-10a)** —
  `core/memory/working.py` ships a turn-scoped scratch store sibling
  to the episodic memory landed in PR-9. Where episodic captures the
  **final** plan/reflect/verify decisions across turns, working memory
  holds **intra-turn** intermediate state (reflection critique drafts,
  per-claim verifier intermediates, planner subtask scratch) that
  reasoning stages hand off to each other while the answer is being
  built and that the audit_log already keeps a forensic copy of.
  In-process dict with `threading.Lock` (no SQLite) keeps the
  "cleared at turn end" invariant safe against operator restart
  races. ContextVar reuse: the PR-9b `(session_id, turn_id)` binding
  is the only one needed — `working_event()` reads it directly so
  PR-10b call sites stay one-liners.
  15 new tests in `tests/test_working_memory.py` lock the contract
  (round-trip, turn isolation, session isolation, keys(), clear_turn,
  prune_idle_turns, thread-safety, helper no-op outside tracked turn,
  helper write under bound context, singleton stability). Wiring into
  the cognitive stages and the `engine.query()` finally-block
  cleanup lands in PR-10b. Design memo:
  [`docs/design/v0.3-working-memory.md`](docs/design/v0.3-working-memory.md).

### Changed

- **Verifier base scan (security_validator) is now default ON**
  (Cognitive Phase 2 PR-6 default flip). A fresh JAMES install now
  gets injection-echo detection on every answer without an operator
  having to discover the env flag. The base scan is ~5ms of
  pure-Python pattern matching against the final answer — well below
  the STEP 7 measurement noise floor (Run-A all-off: 159.6s vs
  Run-B verify-on attempt: 152.5s; the ~7s spread is LLM-call
  variance, not verifier cost) and independent of LLM availability.
  Fact-check (LLM-driven, +5-15s/query) remains opt-in via
  `JAMES_ENABLE_FACT_CHECK=1`. The legacy opt-in flag
  `JAMES_ENABLE_VERIFY=1` is still honoured as a no-op (truthy →
  True) so existing `.env` files keep working unchanged. A new hard
  opt-out `JAMES_DISABLE_VERIFY=1` silences both the base scan and
  any pending fact-check — consistent with operator intent for
  baseline-cost measurement or quiet-mode operation.

### Added

- **Episodic memory wiring across cognitive stages (Cognitive Phase 3
  PR-9b)** — a follow-up question in the same session can now see what
  the planner decomposed the prior question into, what reflection
  revised, and what verification flagged. PR-9a (`core/memory/episodic.py`)
  shipped the session-scoped SQLite store; this PR wires the
  `record_event()` calls into `planner.py`, `reflect.py`, `verify.py`,
  and the shared `trace_helpers.trace_synth_call` (covers every synth
  sub-stage). `engine.query()` binds `(session_id, turn_id)` to a
  ContextVar at turn start; `engine_memory.build_memory_context`
  reads the last 3 turns of plan / reflect / verify events and
  prepends a compact "[이전 추론 흔적 (이 세션)]" block to the system
  prompt. Same-session isolation enforced at the SQL layer
  (`WHERE session_id = ?`); the PR-O4 N-3 gate already prevents
  cross-session leak on a new session's first turn. Opt-out via
  `JAMES_EPISODIC_CONTEXT=0` for measuring baseline cost. New admin
  endpoint `GET /admin/episodic/{session_id}` returns the session's
  events for debugging (gated by the same `admin.metrics` permission
  as `/admin/trace/*`). 8 new tests in
  `tests/test_episodic_wiring.py` lock the contract (stage record,
  cross-turn read, new-session isolation, cross-session isolation,
  opt-out, ContextVar no-op when unbound, ContextVar happy path).

### Fixed

- **Cross-document evidence accumulation now works** — uploading two
  documents that both attest to the same `(subject, predicate, object)`
  triple now produces a relation with 2 sources (confidence ≈ 0.91
  with default LLM weights), rather than only the first doc's
  contribution. Previously `core/wiki_generator.py:640` returned
  `continue` when an entity already existed, silently dropping every
  subsequent doc's strengthening — Knowledge Cascade relations were
  permanently single-source, so the noisy-OR formula never had
  multi-source state to act on and `--dry-run` of the recompute
  migration found 0 affected relations across 278 production entity
  files. New helper `_merge_relations_into_existing_entity` matches
  on `(target_name, normalized_type)`, skips duplicate `doc_id` for
  idempotency (re-upload safe), recomputes confidence via noisy-OR,
  and writes the frontmatter back. Both forward and inverse
  directions aggregate symmetrically. 5 new tests in
  `tests/test_phase_b_ingestion_sources.py` lock the behaviour
  (cross-doc append, inverse aggregation, noisy-OR confidence after
  2 sources asserting 0.91, same-doc idempotency, distinct-target
  new-row). Design memo
  [`docs/design/v0.3-knowledge-cascade.md §4`](docs/design/v0.3-knowledge-cascade.md)
  describes the same behaviour as a historical reference.

- **Confidence from multiple sources no longer saturates at 2** —
  `compute_confidence_from_sources` now uses noisy-OR
  (`P = 1 - Π(1 - w_i)`) instead of clamped sum (`min(Σw, 1.0)`).
  With default LLM weights ~0.7, the clamped-sum implementation
  reached confidence = 1.0 from just 2 corroborating sources, losing
  all signal about *how strongly* a relation was supported (5 vs 20
  attestations collapsed to the same value). It also broke monotone
  cascade semantics: deleting one of multiple sources didn't reduce
  confidence when others kept it pinned at the ceiling. Noisy-OR
  preserves the signal asymptotically (5×0.7 → 0.998, < 1) and
  guarantees strict monotonicity on source add/remove — important
  for the graph DFS `confidence < 0.6` threshold gate in
  `core/graph_engine.py:335`. Single-source identity preserved
  (`min(w, 1) == 1 - (1-w) == w` for one source), so Phase A
  back-fills remain byte-identical and STEP 7 bench stayed within
  baseline tolerance. Production wiki audit: 0 multi-source
  relations existed at the time of the fix (because of the cross-doc
  bug above), so no historical confidence values changed. Includes
  `scripts/migrate_recompute_confidence.py` for any installation
  that may have accumulated multi-source relations under the wrong
  formula. 7 new tests in `tests/test_relations_schema.py` lock the
  behaviour (single-source identity, 2-source divergence from
  clamped sum asserting 0.58, asymptotic-not-saturated for 5+
  sources, strict monotonicity on add/remove, per-element weight
  clamping). Design memo
  [`docs/design/v0.3-knowledge-cascade.md §3`](docs/design/v0.3-knowledge-cascade.md)
  arrived at the same formula as a historical reference.

---

## [0.3.0] — Platform Skeleton (2026-05-17)

After 190 merged PRs since v0.2.0 (9 days, 129 test files), JAMES exits
the v0.2 Foundation Hardening cycle and enters **v0.3 Platform Skeleton**.
Axis 6's second-user gate cleared on 2026-05-13. The original v0.3 plan
(Plugin API as the single theme) was rebalanced after the 2026-05-14
user briefing: **Cognitive Layer** and **Knowledge Cascade** become the
two main tracks, **Plugin API** slips to v0.3.x or v0.4 pending external
contributor demand.

Full release notes: [`docs/release_notes_v0.3.0.md`](docs/release_notes_v0.3.0.md).

### Added

#### Change Request primitive (v0.2.x track)
- **`core/change_request.py`** generalises the `approver_username`
  pattern that v0.1 hard-coded for self-evolution alone. Every write
  becomes a proposal → review → admin approval → atomic apply →
  audit row. Two target types ship: `wiki_entity` (markdown edits with
  `base_hash` conflict detection) and `run_jobs` (workspace job gate).
  Trust zone documented in `docs/ARCHITECTURE.md §5.6`. PRs #237, #243,
  #239, #240, #247.
- Workspace UI panel for proposers / reviewers (`/workspace` Change
  Request tab). PR #239.
- CR-E (self-evolution wrap) deferred to Cognitive Layer Phase 2 PR-6
  per the 2026-05-14 user decision (verification engine fuses with CR-E
  end-to-end).

#### Knowledge Cascade (Phase A → E, sources-aware graph)
- **Phase A** — `sources: [{doc_id, weight, role, ts}]` schema replaces
  the v0.2 single `confidence` field on every relation. Production wiki
  migrated (213 entities / 656 relations back-filled; backup at
  `wiki.pre-v03-migration/`). PR #266.
- **Phase B** — `process_document_for_entities` writes sources directly
  (`role=extract` outgoing + `role=inverse` inverse + doc-entity
  self-source). Legacy callers unaffected. PR #269.
- **Phase C** — `DELETE /admin/files` cascade. New `core/cascade.py`
  with strengthened orphan-detection rules. PR #270.
- **Phase D** — `PUT /admin/files` (multipart replace) cascade. Extraction
  sidecar JSON + diff_triples. PR #274.
- **Phase E backend** — `core/graph_editor.py` (replace / append / delete
  + bidirectional sync + manual metadata). Behind `JAMES_GRAPH_EDIT=1`
  opt-in flag. PR #271.
- **Phase E UI** — `/admin/graph` edit-mode toggle + edge-click modal
  (sources display + manual append + delete relation). PR #273.

#### Cognitive Middleware Layer (architecture only, code in v0.3.x)
- **`docs/ARCHITECTURE.md §5.7`** introduces the Cognitive Middleware
  Layer between retrieval and LLM synthesis. 7 named components
  (Planner / Query Rewriter / Reflection / Verification / Tool Router /
  Memory Manager / Security Reasoner / Context Optimizer), trust zone,
  trace-replay invariant, **5-role multi-agent cap (anti-sprawl)**,
  memory scope layering (system / workspace / session), and deployment
  isolation deferred to v0.4. Code lands across v0.3.x phases. PR #275.
- Cycle plan: `docs/handovers/v0.3-cognitive-layer-track.md`.

#### Operational UX (cycle 12, live usability)
- **PR-O1** — `/admin/entities/<id>` 노드 클릭 요약 403 fix (Bearer
  header). PR #277.
- **PR-O2** — chat suggestion chips: 3 natural-language patterns added
  ("혹시 ~궁금하신가요?", "~에 대해 더 알고 싶으시면", "관련된
  질문으로는"), threshold relaxed `>=2 → >=1`. PR #279.
- **PR-O3** — long-term wiki save chip in-place spinner → ✓/✗ transition
  with mint accent ring, 1.4 s failure restore. PR #280.
- Remaining PR-O4 (N-3 long_ctx isolation) / PR-O5 (external matrix
  tightening) / PR-O6 (node editing + Korean labels) / PR-O7 (drag +
  click-to-connect) deferred to v0.3.0.x. Track:
  `docs/handovers/v0.3-operational-ux-track.md`.

#### Cyber UI — mono-cyber palette (6a → 6d)
- Mono-cyber palette migration: single `--accent` (mint) on dark
  background, replacing the v0.2 multi-hue gradient. PRs #222–#224.
- **6a** background texture (grid + corner radials). PR #223.
- **6b** single-accent glow on primary surfaces. PR #224.
- **6c** modal glassmorphism (`@supports (backdrop-filter)`). PR #225.
- **6d** live indicators (pulse dot + scan line, 4-page rollout). PRs
  #226 / #228.
- Token consolidation into `frontend/static/tokens.css`. PRs #214 / #221.
- WCAG dialog pattern on every modal (focus trap + ESC + ARIA roles).
  PR #216. `aria-label` on icon-only and JS-populated buttons. PR #217.
  `--muted-2` lifted above WCAG AA. PR #218.
- Inline-handler → `data-action` event delegation across all 4 pages.
  PRs #230, #232, #233, #241.

#### Audit pipeline — JSONL → SQLite mirror (Phase 1 → 4)
- **Phase 1** — tool JSONL events mirrored to SQLite `audit_log`. PR #206.
- **Phase 2** — attack + system JSONL events mirrored. PR #207.
- **Phase 3** — `/admin/audit/list` categories (`tools` / `attack` /
  `system`). PR #208.
- **Phase 4a** — legacy `/admin/audit` dropped; dashboard reads SQLite.
  PR #210.
- **Phase 4b-1** — `/code/surface/` reader migrated to SQLite. PR #211.
- **Phase 4b-2 (writer removal)** intentionally deferred 2–4 weeks of
  production mirror-reliability monitoring. ROADMAP "Deferred follow-ups".

#### Workspace + Scheduler (W7 / W8)
- **W7-A** — `data_artifacts` table + lifecycle (uploaded → extracted →
  indexed / failed). `wiki_links` records doc → entity derivation. PR #191.
- **W7-B** — standalone `/workspace` data-explorer page. PR #192.
- **W8-A** — generic job execution backbone + 3 handlers
  (`excel_build` / `doc_combine` / `entity_export`). PR #193.
- **W8-B** — chat-sidebar workspace tab. PR #194.
- **W8-C** — `wiki_links` populated on upload. PR #195.
- **W8-D** — scheduler with small cron DSL (`every:N` / `hourly` /
  `daily:HH:MM` / `weekly:DOW:HH:MM`) + 90-day result retention. PR #197.
- **W8-D follow-up** — `/admin/scheduler/status` + `/jobs/unschedule`. PR #204.

#### Auth + Policy matrix (W4 P3 / Q1-Q3)
- **W4 P3-2** — request authentication accepts `X-API-Key` header or
  `?api_key=` query parameter; system key resolves to `employee` role
  (no implicit admin authority). PRs #179 / #180.
- **W4 P5** — chat-page password-reset modal. PR #182.
- **W4 P6** — admin audit log page (category filter + search + paging).
  PR #183.
- **W4 Q1** — feature capability registry (`core/feature_registry.py`
  + `feature_overrides` table + `PolicyEngine.can_use_feature`). PR #184.
- **W4 Q2-a** — wire 17 admin endpoints onto `_require_feature`. PR #187.
- **W4 Q2-b** — catalog extension + remaining 38 endpoints. PR #188.
- **W4 Q2-c** — user-facing feature gates on `/query` / `/upload` /
  `/password` / `/api-keys`. Behaviour change: `/upload` denied for
  `employee` / `external` by default (previously any valid api_key).
  PR #189.
- **W4 Q3** — admin permission matrix UI (feature × role grid).
  PR #190.

#### License Track A + OpenSSF passing badge
- License Track A cleanup: `THIRD_PARTY_LICENSES.md` (one-shot via
  `pip-licenses`), README license-line unification, first-quarter
  trigger monitoring entry in `docs/LICENSE_PLAN.md §8`. PR #259.
- **OpenSSF Best Practices passing badge** achieved (2026-05-11,
  Tiered 111%). Badge displayed in `README.md` / `README.ko.md`.
  Project page: https://www.bestpractices.dev/projects/12806.

#### v0.2 axes 6 closure + Axis 6 user-feedback follow-ups
- **N-1** — `/admin/graph` snapshot now reflects entity files written
  by other engines (cache invalidation). PR #256.
- **N-3** — new-session greeting + cross-session leak (partial fix;
  full isolation in v0.3.0.x PR-O4). PR #257.
- **Web learn fix** — `/web learn` routes through proper LLM triple
  extraction (no more query-as-node). PR #252.
- **2-pass UNRESOLVED sweep** — every ingest resolves UNRESOLVED
  target_id references on a second pass. PR #253. Manual grand-sweep
  trigger: `POST /admin/wiki/resolve-relations`. PR #261.
- **One-shot cleanup script** for pre-#252 web-learn noise concepts.
  PR #254 (user runs `--apply` after dry-run review).
- **Workspace continuity** — `core/reasoning/modes.py` conversation
  continuity (Axis 6 item 1). PR #249.
- **Clean answer + dual web-search chip** (Axis 6 items 2-3). PR #248.
- **Reasoning panel** — retrieve → expand → verify phase grouping in
  `/admin/dashboard`. PR #235.
- **Citation chips** — `graph_paths` rendered as mint citation chips
  in chat answers. PR #229.

#### Chat UX (cycle 5)
- **N-4** — suggestion chip header with mint accent + uppercase. PR #263.
- **N-5** — mid-band web-search chip when retrieval below the
  configurable threshold. PR #263.
- **N-6** — in-page long-term save modal (`jamesConfirm()` replaces
  native `confirm()`, 6c glass + mint, WCAG dialog ARIA). PR #264.

#### Multimodal + extras
- **Video ASR** — ffmpeg + Whisper pipeline (`W1 §3-C Option A`). PR #198.
- **Chat file drag-drop + clipboard paste** with mini-thumbnails and
  sidebar auto-switch (W5 / W6). PRs #185 / #186.

### Changed

- **`core/memory/store.py` split** — 24 KB → 12 KB across natural
  boundaries (`db.py` / `conversation.py` / `summaries.py` +
  `store.py` facade). Public API preserved. CLAUDE.md rule #5 module
  size gate restored. PR #260.
- **Mono-cyber palette migration** — every page repainted; legacy CSS
  token aliases removed. PR #220.
- **`urllib3 >= 2.7.0` + `python-multipart >= 0.0.27`** floors
  raised to close 6 Dependabot high-severity alerts. PR #244.

### Security

- **`python-multipart >= 0.0.18`** floor raised earlier in the cycle
  for GHSA-59g5-xgcq-4qw3 (DoS via unbounded multipart part headers).
  PR #213.
- **`/upload/` feature gate** — `employee` / `external` denied by
  default (W4 Q2-c). A leaked `JAMES_API_KEY` alone (resolves to
  `employee`) no longer ingests documents.
- **Multimodal trust quarantine** continues from v0.2 Axis 4; web
  results pass `PolicyEngine.quarantine()` before joining the LLM
  context. Codified in `core/policy_engine.py` + `TrustedContent`.

### Fixed

- **F541 / F401 lint cleanup** — main CI green restored after Phase A
  migration residuals. PR #278.
- Several smaller live-usage fixes folded into the cycle 12 quick-fix
  bundle (PRs #277 / #279 / #280).

### Deprecated / Removed

- **Legacy `/admin/audit` endpoint** removed in Audit Phase 4a (#210).
  Operators migrate to `/admin/audit/list?category=…`.
- **Legacy CSS token aliases** removed. PR #220.

### Migration

```bash
git pull origin main
git checkout v0.3.0
pip install -r requirements.txt   # urllib3 >= 2.7.0, python-multipart >= 0.0.27

# new opt-in env knobs:
export JAMES_GRAPH_EDIT=1            # enable Phase E graph editor
export JAMES_ENABLE_EVOLUTION=0      # self-evolution opt-in (unchanged)
export JAMES_TRACE_STDOUT=0          # silence per-stage console mirror (unchanged)

# verify:
python -m unittest discover -s tests
python scripts/bench.py --suite=step7
```

If you ran v0.2.0 with a populated wiki, the Phase A migration ran
automatically on first boot under v0.3 — verify backup at
`wiki.pre-v03-migration/` before deleting it.

### Pending live validation (shipped, will follow up if regressions)

- Phase D file-modify cascade (#274) — end-to-end live verification
  with diverse formats
- Phase E graph editor UI (#273) — full edit-mode UX flow
- Cycle 12 PR-O1 / PR-O2 / PR-O3 — admin-UI / chat live spot-check
- Phase A migration (#266) `bench step7 --check` byte-identical
  verification on the user's production corpus

---

## [0.2.0] — Foundation Hardening (released 2026-05-08)

### Security

- **`python-multipart` spec floor raised to `>=0.0.18`** (GHSA-59g5-xgcq-4qw3
  — Denial of Service via unbounded multipart part headers). The pinned
  install (`requirements_pinned.txt`) was already on 0.0.26, so no
  upgrade-side risk; this change aligns `requirements.txt`'s spec with
  the safe minimum and closes Dependabot alerts #5 and #6 (both High).

### Added

#### OpenSSF Best Practices passing badge
- Achieved the **OpenSSF Best Practices passing badge** (2026-05-11,
  Tiered 111%). Badge is now displayed in `README.md` and
  `README.ko.md`. Project page:
  https://www.bestpractices.dev/projects/12806
- The submission documents the project's posture on bug-reporting,
  vulnerability disclosure (GitHub PVR + backup email), licensing
  (MIT), versioning (SemVer + 7 GitHub Releases), test suite
  (`james_*_test.py` and `tests/`), bcrypt password storage
  (PR #173, W4 P1-A), and static analysis baseline
  (PR #196 — ruff F821 enforcement with phased plan).

#### Reasoning Graph Visualizer (Axis 3 Observability/Explainability)
- **`/admin/graph`** — new admin-only 3D page that renders every wiki
  entity as a point in a soft-ball sphere and every ontology relation
  as a connecting line. Drag to rotate 360°, scroll to zoom, click to
  focus. Force-directed layout with link strength ∝ `min(deg(s), deg(t))`
  so densely-connected nodes drift together; a custom radial spring
  pulls the layout toward a sphere shell.
- **`/admin/graph/snapshot`** — new admin-gated read-only data endpoint
  (`source_type=prod|test`) that materializes the full entity + edge
  set as JSON. Cached by `(source_type, max_mtime)`; gzip-friendly
  short keys (`s`/`t`).
- **Pulse animation** — when a query is asked from the page's bottom
  query bar, the response's `graph_paths` strings are parsed
  client-side and a cyan additive sprite tweens along each traversed
  edge in chronological order, leaving a 4 s afterglow.
- **Sensitivity-aware**: nodes with `sensitivity == "sensitive"` and
  edges whose ontology entry is `sensitive=True` (HAS_SECRET,
  KNOWS_PASSWORD, HAS_CREDENTIAL, OWNS_PRIVATE) are filtered out
  server-side by default. `include_sensitive=1` is locked off until a
  dedicated elevated role lands.

### Implementation notes
- New module `core/graph_snapshot.py` (~8.4 KB) sits alongside
  `core/graph_engine.py` (15.8 KB) so the latter stays well under the
  20 KB module-size gate. No retrieval / pipeline / ontology code was
  modified — the visualizer is pure observability over data that
  already exists.
- 3D libs (Three.js 0.160, 3d-force-graph 1.73, d3-force-3d 3) are
  loaded from CDN; matches the project's no-bundler vanilla-JS
  posture. Vendoring for air-gapped deploys is tracked separately.
- Tests in `tests/test_graph_snapshot.py` cover the snapshot shape,
  sensitivity filter, mtime-based cache invalidation, server route
  registration, and frontend artifact contract.

---

## [0.1.1] — Path Auto-Detection (Patch)

### Fixed

#### Critical: Hardcoded Paths Removed
- **config.py**: `BASE_DIR` was hardcoded. Now auto-detected from `config.py`'s own location.
- **config.py**: Removed hardcoded user paths exposing the developer's Windows username.
- **vector_store.py**: `LOCAL_MODEL_PATH` was hardcoded. Now derives from `BASE_DIR`. Fixes the issue where renaming the project folder caused the embedding model to be re-downloaded externally.
- **patch_abac_fields.py / tools/admin/seed_data.py / tools/admin/wiki_reset.py**: Replaced hardcoded fallback paths with location-relative detection.

#### Cross-Platform Support
- Tesseract OCR path: auto-detected for Windows / macOS / Linux
- Poppler path: auto-detected for Windows; uses system PATH on macOS / Linux
- Ollama path: uses system PATH (no hardcoded location)

### Added
- Environment variable overrides for all binary paths:
  - `TESSERACT_PATH` — Tesseract binary
  - `JAMES_POPPLER_PATH` — Poppler bin directory
  - `OLLAMA_PATH` — Ollama binary
  - `JAMES_MODEL_PATH` — Sentence-Transformer model location
  - `JAMES_LLM_MODEL` — Default LLM model name (default: `gemma2:2b`)
  - `OLLAMA_API_URL` — Ollama API endpoint
  - `JAMES_MAX_UPLOAD_MB` — Upload size limit (default: 100)

### Security
- **CRITICAL**: Previous version (v0.1.0) included paths revealing the developer's local Windows username. Anyone cloning the repository could see this information. Now removed.
- Project folder can be renamed/moved freely without breaking functionality.
- Anyone cloning the repository can run `python server_llmwiki.py` immediately without editing paths.

### Migration from v0.1.0
No migration steps needed. The fix is backward compatible:
- Existing installations will continue to work
- Folder rename now safe
- No database / data changes required

---

## [0.1.0-alpha] — Initial Release

### Added

#### Core Engine
- Hybrid Search (Vector 60% + BM25 20% + keyword 20%)
- Graph-RAG with 12 ontology relation types
- DFS traversal with confidence-based pruning
- ChromaDB vector store with Sentence-Transformers embeddings
- Ollama-based local LLM execution

#### Security
- 3-stage access control (Vector / Graph / Output)
- RBAC with 4 roles
- ABAC with 4 sensitivity levels
- 31+ prompt injection pattern detection
- Instruction Isolation framework
- JWT authentication
- Rate limiting (30 req/60s)
- Full audit log in SQLite

#### Knowledge Management
- Markdown-based wiki as knowledge graph
- File ingestion (PDF, DOCX, images, video, audio)
- Automatic entity extraction and linking
- Relations stored in YAML frontmatter

#### Self-Evolution Scaffolding
- Patch Pipeline with 4-Gate validation
- 11-trait personality system
- Knowledge tracker (8 abilities + 6 domains)
- Feedback engine

#### Multimodal & Tools
- LLaVA, Whisper, ffmpeg, pytesseract, easyocr integrations
- Sandboxed Python execution
- File upload pipeline

#### Web Search
- Tavily (primary) + DuckDuckGo (fallback)

#### User Interface
- Web-based chat UI + Admin dashboard
- Session management
- Reasoning path visualization
- Confidence badges

#### Internationalization
- 286 i18n keys (English / Korean)
- Default language: English
- Live toggle (KO / EN)

#### Documentation
- README.md, README.ko.md
- SECURITY.md, ROADMAP.md, CONTRIBUTING.md, CHANGELOG.md
- .env.example

---

[0.3.0]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.3.0
[0.2.0]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.2.0
[0.1.1]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.1.1
[0.1.0-alpha]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.1.0-alpha
