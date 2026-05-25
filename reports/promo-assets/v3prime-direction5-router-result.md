# Direction 5 — Auto-routing on Provider Contract: Closure (2026-05-25)

> Status: closed. 10-PR sequence (PR #474 – #483) landed in one
> session 2026-05-25, completing the v0.3.x measurement-framework
> follow-up Direction 5 + Direction 2 (absorbed) + Cross-lingual
> RAG option 3.

## Headline

JAMES now routes every LLM call through a per-call policy that
selects backend by task weight. **Opt-in** (`JAMES_AUTO_ROUTER=1`),
**byte-identical at default**, **observable** via `audit_log
reason:route` rows. The policy compounds D1 (Adaptive Budgeting)
findings with D5.B capability tags so that:

- substitution calls land on the cheapest viable backend
- heavy synthesis lands on the strongest registered backend
- the `verify` stage always escalates to the strongest backend
  (grounding-critical, D1 sub-finding: ~12.5% unique = high
  clustering — a stronger model improves grounding decisions)

Pre-existing wiki-entity-aliases infrastructure (`graph_engine.py:145-148`
on main before D5.D) gained a **code-side default alias pack** so
KO↔EN entity surface forms resolve to the same wiki entity_id
without per-install frontmatter edits — closing the 2026-05-25
"팔란티어 → VANCE_이란공습_분석.pdf" diagnostic root cause.

## Closure deliverables

| # | Phase | PR | What landed |
|---|---|---|---|
| 1 | D5.0 design memo | #474 | `docs/handovers/v0.3.x-direction5-auto-routing-track.md` (213 lines) — scope / phase plan / STEP 7 bench plan / Build-don't-broadcast applied / cross-lingual option 3 bundled |
| 2 | D5.A skeleton + flag | #475 | `core/reasoning/router.py` + 23 contract tests. flag `JAMES_AUTO_ROUTER` default OFF (mirrors D1 `JAMES_ADAPTIVE_BUDGET`). stub `select_backend` returns legacy backend regardless — opting in is safe at every intermediate PR. |
| 3 | D5.B capability tags | #476 | `BackendCapability(tier, provider)` + `UNKNOWN_CAPABILITY` + `get_backend_capability` + `list_backends_by_tier` + 2 builtin backends declared (`ollama_local` = small/local, `claude_code_cli` = large/cloud) + 14 tests |
| 4 | D5.C.1 policy decision tree | #477 | `_route_policy` v1 — 4-rule decision tree (verify→large, CAP_SUBSTITUTION→small, CAP_HEAVY→large, otherwise→legacy). 14 tests. flag-on branch dispatches to policy. |
| 5 | D5.C.2.a query_rewriter wiring | #478 | + helpers (`resolve_backend`, `emit_route_event`, `_budget_to_tier_label`). cap computed first → fed to router as `budget_signal` only when D1 flag also on. Audit emission every successful resolve. 11 tests. |
| 6 | D5.C.2.b planner wiring | #479 | Same pattern. budget_signal=None (planner not D1-wired). |
| 7 | D5.C.2.c reflect wiring + test query narrow | #480 | Single resolve serves both critique + revise. `tests/test_reflection_loop.py::_rows()` narrowed to exclude `reason:route` rows. |
| 8 | D5.C.2.d verify wiring | #481 | Grounding-critical stage. policy rule 1 escalation. reason="grounding-critical" audit label. |
| 9 | D5.C.2.e synth / trace_helpers wiring | #482 | L1 entry point. `resolve_backend_for_stage(stage)` result becomes `fallback_backend_id`. Closes the 5-stage wiring surface. `tests/test_reasoning_trace_helpers.py::_rows()` narrowed. |
| 10 | D5.D cross-lingual entity alias pack | #483 | `core/entity_alias_pack.py` (~30 entries, bidirectional KO↔EN) + `graph_engine.build_entity_map_snapshot` augmentation + 12 tests. Wiki frontmatter takes precedence (first-write); pack augments only when canonical name has wiki match. |

## Acceptance — bench-neutral by design

CLAUDE.md rule #2 (bench numbers) was applied per the design memo
plan, with operator option b adopted at the D5.C.2.a → e wiring
sequence: **test-level invariance** (flag-off byte-identical, 526
backend/router/graph/entity/rewriter/reflect/verify regression
tests pass) + **integrated STEP 7 sweep deferred to D5.E**.

The wiring is bench-neutral at the flag-OFF production default:
no operator on the existing fleet sees latency or grounded-rate
change from the 10 PRs above. Routing decisions only activate
when the operator sets `JAMES_AUTO_ROUTER=1` AND has registered
a backend at a non-`small` tier (e.g. `JAMES_ENABLE_CLAUDE_BACKEND=1`
adds the `large` tier).

### STEP 7 sweep — operator-run measurement (any time)

For an operator running the integrated sweep against this
closure, the procedure is:

1. **Baseline** (flag OFF, default):
   ```
   unset JAMES_AUTO_ROUTER
   python scripts/research/v3prime_direction1_adaptive_budget.py --n 20
   ```
   Records the D1 7-tier natural-stop gradient (62→1681 tokens,
   ground truth from D1 closure result doc).

2. **Treatment, small-tier-only fleet** (flag ON, only
   `ollama_local` registered):
   ```
   export JAMES_AUTO_ROUTER=1
   python scripts/research/v3prime_direction1_adaptive_budget.py --n 20
   ```
   Expected: latency / grounded-rate match baseline within ±5%
   per tier. All routing decisions land as `reason:fallback` or
   `reason:grounding-critical` (no large/medium registered →
   policy falls back to legacy). The audit row pile-up is the
   only observable change.

3. **Treatment, large-tier registered** (optional —
   `JAMES_ENABLE_CLAUDE_BACKEND=1`):
   ```
   export JAMES_AUTO_ROUTER=1
   export JAMES_ENABLE_CLAUDE_BACKEND=1
   python scripts/research/v3prime_direction1_adaptive_budget.py --n 20
   ```
   Expected: `verify` stage routes to `claude_code_cli` on every
   call → latency ↑, grounded=true rate ↑ (the Claude model is
   stronger at grounding decisions). Other stages route by
   budget — heavy synth → claude, substitution → ollama, light → legacy.

Acceptance criterion: **no grounded=true rate regression at any
tier** when comparing baseline vs treatment (2).

Cross-lingual diagnostic: re-run the "팔란티어가 뭐야?" query
that motivated PR #472 + this PR. Expected rerank top now =
`PLTR_*.pdf` or `Palantir_2026Q1_실적.pdf` (real Palantir
material), not `VANCE_01_이란공습_분석.pdf` (unrelated).

## What this closure does NOT claim

- **Production-grade routing policy v2**. The current `_route_policy`
  is a heuristic 4-rule tree. Cost-based scoring (token price ×
  latency × quality) and multi-objective optimization are v0.4
  follow-ups.
- **Per-domain-pack routing**. v0.5 Domain Pilot scope.
- **Per-stage explicit override under D5 ON**. When the flag is
  on, the router is the authority — operator's
  `JAMES_BACKEND_<STAGE>` env loses precedence to the router.
  A flag-aware per-stage override is a v0.4 follow-up.
- **Embedding model swap**. The cross-lingual fix (option 3) is
  a graph-resolution layer; the deeper fix (multilingual-e5-large
  or bge-m3 swap, option 4) is v0.4 backlog item BL-9.
- **D2 task-weight metric as an independent paper**. D2 was
  absorbed into D5 as the policy's task-classification
  heuristic; the per-prompt measured metric remains a candidate
  v0.4 research cycle if the heuristic plateaus on production
  bench.

## Cross-Direction map

- **D1** (Adaptive Budgeting, closed 2026-05-25) → input to D5
  policy (CAP_SUBSTITUTION / CAP_LIGHT / CAP_HEAVY tiers)
- **D2** (Task-weight metric) → absorbed into D5 as the
  policy's heuristic classifier
- **D3** (Cross-family generalization) → still queued for
  mid-June Robin collaboration window
- **D4** (Substitution bypass verification, closed 2026-05-24)
  → motivates D5 policy rule 2 (CAP_SUBSTITUTION prefers
  `small` because substitution bypasses sampling)
- **D5** (Auto-routing, this PR) → closed
- **D6(I)** (Joint paper consolidation) → still queued for
  Track 3 swap (Ali mid-June Gemini)
- **D6(J)** (Methodology spec, closed 2026-05-24) → independent

## Collaborator interaction

Per the Build-don't-broadcast principle (memory:
`feedback_build_dont_broadcast`):

- ❌ No LinkedIn / X / blog announcement for this cycle.
- ❌ No Robin coupling (D5 is product, not measurement).
- ✅ Ali single design-preview DM at D5.0 merge (Provider
  Contract layer courtesy — "router lands above the contract,
  no contract-shape change, mid-June Gemini backend slots in
  cleanly"). Operator action.

## Files (canonical references)

| Surface | File |
|---|---|
| Design memo | `docs/handovers/v0.3.x-direction5-auto-routing-track.md` |
| Router | `core/reasoning/router.py` (~12 KB; Router class, `_route_policy`, `resolve_backend`, `emit_route_event`, `_budget_to_tier_label`) |
| Backend capability | `core/reasoning/backends/__init__.py` (`BackendCapability` dataclass, `UNKNOWN_CAPABILITY`, `get_backend_capability`, `list_backends_by_tier`) |
| Backend declarations | `core/reasoning/backends/ollama_local.py` (`capability = BackendCapability("small", "local")`); `core/reasoning/backends/claude_code_cli.py` (`capability = BackendCapability("large", "cloud")`) |
| Stage wiring | `core/retrieval/query_rewriter.py` (D5.C.2.a); `core/reasoning/planner.py` (D5.C.2.b); `core/reasoning/reflect.py` (D5.C.2.c); `core/reasoning/verify.py` (D5.C.2.d); `core/reasoning/trace_helpers.py` (D5.C.2.e) |
| Alias pack | `core/entity_alias_pack.py`; `core/graph_engine.py` (D5.D snapshot augmentation in `build_entity_map_snapshot`) |
| Tests | `tests/test_router_skeleton.py` (D5.A, 23), `tests/test_backend_capability.py` (D5.B, 14), `tests/test_router_policy.py` (D5.C.1, 14), `tests/test_query_rewriter_router_wiring.py` (D5.C.2.a, 11), `tests/test_entity_alias_pack.py` (D5.D, 12) |
| Architecture amendment | `docs/ARCHITECTURE.md` §5.7.8 (D5 routing layer + cross-lingual alias resolution) |
| ROADMAP | `ROADMAP.md` §Measurement framework Direction 5 (closed entry with PR list) |
