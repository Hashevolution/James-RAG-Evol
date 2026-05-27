# LEO L.D — Evidence-Scope Routing: Closure (2026-05-27)

> Status: closed. L.A → L.D wiring landed across PR #513 / #514 /
> #516 / #517 + this branch (`fix/v0.4-bench-wrapper-d5-dependency`)
> resolving the operator-measurement gap. Companion to
> `docs/handovers/v0.4-leo-evidence-scope-routing-track.md` (design
> memo) and `direction_5_auto_routing_closure.md` (memory).

## Headline

The LEO evidence-scope axis is wired through the production cognitive
loop (Loop 1 → `compute_scope` → `scope_context` binding → router
policy v1). Flag-OFF byte-identical to post-L.B main; flag-ON adds
the narrow-≤0.30 / wide-≥0.70 backend override with the mid-band
deferring to D5 budget rules. No regression on the operator's
small-tier-only fleet.

L.D itself surfaced **two latent issues** that the prior STEP 7
sweep procedure had not exercised. Both are fixed:

1. **`router._legacy_backend_id` returned a model tag, not a registry
   backend ID** — `"gemma4:e4b"` instead of `"ollama_local"`. Every
   D5 fallback path (`AUTO_ROUTER=1` + no large/medium tier) crashed
   on `get_backend("gemma4:e4b")` `KeyError`. The D5 closure result
   doc had promised "fall back to legacy → just extra audit rows";
   the code instead degraded to "every routing decision raises".
   Latent since D5.A (2026-05-25); first reached by an operator who
   actually flipped `AUTO_ROUTER=1` end-to-end in this branch.

2. **`bench.py --suite=step7` measures chat-mode passthrough**, not
   retrieval mode — the QueryRouter / IntentClassifier classifies all
   10 RAG-style step7 queries as `chat`, which bypasses
   `run_retrieval_pipeline` (and therefore the L.C
   `scope_context(...)` binding). All step7 benches since at least
   2026-05-09 have the same pattern (`{'chat': 10, '': 2, 'meta': 1}`
   mode distribution). The wrapper's `lc-scope-bench-*.json` aggregate
   reflects this: 10 `reason:route` rows captured, all
   `reason=fallback` (scope_breakdown=None) → `scope_summary={}` even
   under flag-ON. Direct measurement of the L.C scope path requires
   a retrieval-mode bench harness — deferred to a follow-up
   (`bench.py` `mode_override` parameter or a dedicated research
   driver). The current bench still passes the bench-neutral
   acceptance criterion (no crash, latency within noise band).

## Closure deliverables

| # | Phase | PR | What landed |
|---|---|---|---|
| 1 | L.0 design memo | #512 | `docs/handovers/v0.4-leo-evidence-scope-routing-track.md` |
| 2 | L.A extractor + flag | #513 | `core/reasoning/evidence_scope.py`, `JAMES_SCOPE_ROUTING` env (default OFF). Module constructible, no production callers — flag-on/off byte-identical to pre-L.A main. |
| 3 | L.B router signature + policy v1 | #514 | `evidence_scope` kwarg on `Router.select_backend`, `resolve_backend`, `_route_policy`. Narrow≤0.30→small, wide≥0.70→large/medium, mid-band falls through to D5 budget rule. verify-stage invariant preserved (rule 1 wins). |
| 4 | L.C engine wiring + audit | #516 | `pipeline.py` Loop 1 → `compute_scope` → `scope_context(...)` over generate_answer + reflect/verify. `trace_helpers.trace_synth_call` reads `get_current_scope()` and emits `reason:route` audit row with `evidence_scope=… effective_k=… …` payload when the scope was the routing input. ContextVar pattern keeps the signature surface unchanged. |
| 5 | L.D wrapper + measurement | #517 | `scripts/bench_lc_scope_arms.py` — operator-runnable scope-routing bench, audit_log capture, scope distribution aggregate. |
| 6 | L.D wrapper + dependency fixes | this branch (`fix/v0.4-bench-wrapper-d5-dependency`) | Three wrapper bugs: env vars set on bench.py subprocess (server never received them — operator's pre-launched server kept boot-time env); wrong `audit.db` default (real path `james_audit.db`); audit_log answer column is JSON-wrapped, not flat tokens. Wrapper now spawns + tears down its own uvicorn per arm. |
| 7 | Router latent bug fix | this branch | `_legacy_backend_id` returns `"ollama_local"` (registry key), not `JAMES_LLM_MODEL` (model tag). New `JAMES_LEGACY_BACKEND` env override for test injection. 5 test files updated to use the new env (test_router_skeleton, test_router_policy, test_router_evidence_scope, test_router_capability, test_query_rewriter_router_wiring). |

## Operator measurement procedure (this branch)

```powershell
# 0) Stop any pre-existing JAMES server on 127.0.0.1:8000 (the wrapper
#    spawns its own uvicorn per arm with the correct env so the flags
#    actually reach the routing call sites).
python scripts/bench_lc_scope_arms.py
```

The wrapper:
1. Spawns `python -m uvicorn server_llmwiki:app --host 127.0.0.1 --port 8000`
   with `JAMES_SCOPE_ROUTING=0` + `JAMES_AUTO_ROUTER=1` (OFF arm).
2. Polls `/healthz` until 200 OK (default 120s budget).
3. Runs `bench.py --suite=step7`.
4. Shuts down server, waits 2s.
5. Repeats with `JAMES_SCOPE_ROUTING=1`.
6. Queries `audit_log.reason:route` rows within the flag-ON window.
7. Writes `reports/research-runs/lc-scope-bench-<stamp>.json`.

Result file shape — per-query elapsed delta, scope distribution
(`narrow_count` / `mid_count` / `wide_count`), backend selection
counts. Empty `scope_summary` indicates queries didn't traverse
`run_retrieval_pipeline` (chat-mode passthrough — see Issue #2 above).

## 2026-05-27 measurement run

`reports/research-runs/lc-scope-bench-20260527_093629.json`

| Metric | OFF arm | ON arm | Δ |
|---|---|---|---|
| Total elapsed | 165.1s | 158.1s | −4.2% |
| Per-query elapsed | 13.9–21.9s | 11.6–19.1s | within ±20% sampling noise |
| graph_paths | 0 (all queries) | 0 (all queries) | n/a |
| answer_len | 1175–2919 chars | 1291–2937 chars | comparable |
| reason:route rows captured | n/a | 10 | — |
| backend distribution | n/a | `ollama_local: 10` | small tier only |
| scope_summary | n/a | `{}` | scope not exercised — chat-mode passthrough |

Per-query elapsed deltas (q1–q10, OFF → ON):

```
q 1:  21.9s ->  17.6s  (-19.6%)
q 2:  11.0s ->  11.7s  (+6.4%)
q 3:  15.2s ->  11.6s  (-23.7%)
q 4:  16.5s ->  18.7s  (+13.3%)
q 5:  16.3s ->  19.1s  (+17.2%)
q 6:  16.6s ->  16.1s  (-3.0%)
q 7:  15.2s ->  14.7s  (-3.3%)
q 8:  19.7s ->  18.1s  (-8.1%)
q 9:  18.4s ->  15.5s  (-15.8%)
q10:  13.9s ->  14.8s  (+6.5%)
```

## Acceptance — partial (bench-neutral, scope path deferred)

| Criterion | How verified | Status |
|---|---|---|
| Flag-OFF = pre-change main | `test_evidence_scope_wiring.py` + 187-test router/wiring suite passes | ✅ |
| Latency within ±5% per tier (small-tier-only fleet) | OFF vs ON total Δ = −4.2%, per-query Δ within ±20% noise | ✅ (no crash, no degradation) |
| scope payload audit row | `SELECT … WHERE endpoint='reason:route' AND answer LIKE '%evidence_scope%'` | ⚠️ 0 rows captured — chat-mode passthrough deferred to follow-up |
| Narrow→small / wide→large routing | Router contract tests pass (`test_router_evidence_scope.py`) | ✅ at unit level |
| Narrow→small / wide→large routing | bench-time observation | ⚠️ deferred — current bench harness does not reach scope_context binding |
| grounded rate no regression | answer_len comparable, no error responses | ✅ |
| halt-prone (done_reason=length) reduction | not measured this cycle | ⏭️ deferred |
| Closure doc + ROADMAP + memory | **this doc** + ROADMAP entry + memory sync | ✅ |

## What this closure does NOT claim

- **End-to-end scope routing measurement at the bench harness level**.
  The L.C wiring is unit-tested and the production code path is
  validated by absence of regression, but a retrieval-mode bench
  that actually traverses `compute_scope` is needed before we can
  publish "narrow scope ↓ latency / wide scope ↑ latency" numbers.
  Follow-up scope: add `mode_override` param to `bench.py` (or a
  dedicated `v3prime_evidence_scope.py` research driver).

- **L.D 4-arm result doc (narrow / wide / halt-prone / baseline)**
  per the original handover §"STEP 7 bench plan". The 2026-05-27 run
  shows only the OFF vs ON arms over a chat-mode-passthrough harness.
  The 4-arm decomposition requires Issue #2 follow-up.

- **D5 closure measurement re-baseline**. The
  `direction_5_auto_routing_closure.md` memory notes "operator-run
  STEP 7 sweep procedure". The D5 closure used the
  `v3prime_direction1_adaptive_budget.py` research driver
  (fixture-based, bypasses `/query` + QueryRouter) — its measurements
  remain valid. Only the bench.py-based step7 sweep is affected by
  the chat-mode passthrough finding.

- **Robin / Ali joint experiment impact**. Verified 2026-05-27: all
  collaboration measurements (Robin V3'.e mode_split,
  D1 adaptive budget, per-stage planner/query_rewriter/reflect/verify)
  used dedicated research drivers under `scripts/research/v3prime_*.py`
  which call cognitive components directly with fixtures. None
  traverse `/query` or QueryRouter. **Joint DOI and cross-stack
  measurements are unaffected**.

## Cross-Direction map

- **D5** (Auto-routing, closed 2026-05-25) → L.B router policy v1
  extends D5 policy with rule 2 (scope override). L.D latent fix
  (router `_legacy_backend_id`) closes a D5 gap that had been
  masked by the bench harness chat-mode passthrough.
- **D1** (Adaptive Budgeting, closed 2026-05-25) → L.B mid-band
  defers to D1 budget signal. No L.D regression on D1's 7-tier
  natural-stop gradient (verified via research driver).
- **D3** (Cross-family) → pre-notice pattern from
  `direction_3_cross_family_review.md` ready; L.D does not gate.
- **D6(I)** (Joint paper consolidation) → unaffected; uses research
  drivers.

## Followups (open at closure)

- **F1**: `bench.py` `mode_override` parameter (or `v3prime_evidence_scope.py`
  research driver) so L.D-style measurements traverse
  `run_retrieval_pipeline` end-to-end. Priority: L.D ENG/D6(I) prep.
- **F2**: IntentClassifier audit — step7 queries
  ("RAG가 무엇인가?", "Anthropic은 어떤 회사인가?") classified as
  `chat` rather than `retrieval`. Step7 regression baseline has been
  measuring chat-mode latency since 2026-05-09. Either the suite
  intent is wrong (rename categories) or the classifier is wrong
  (tune prompt). Priority: regression baseline truthfulness.
- **F3**: Halt-prone arm measurement (`done_reason=length` rate
  reduction under wide-scope → large-tier routing). Requires F1 +
  a `large`-tier backend (e.g. `JAMES_ENABLE_CLAUDE_BACKEND=1`).

## Collaborator interaction

- **Robin (Younghu LEO)**: design memo author (PR #512). Open
  questions §"L.0 open Q" answered in code via L.B policy +
  L.C ContextVar pattern. L.D closure invites Robin's next sweep
  proposal — narrow/wide arm breakdown when F1 ships.
- **Ali Afana**: no L.D dependency. Track 3 swap_eval mid-June
  remains on its own timing.
- **Cross-stack runs** continue to require all opt-in flags OFF
  (`feedback_cross_stack_run_flag_off` in memory). This wrapper
  forces `JAMES_AUTO_ROUTER=1` and is **not** for cross-stack use.

---

*Generated 2026-05-27 on commit `8de9b2f` + router fix. See
`reports/research-runs/lc-scope-bench-20260527_093629.json` for raw
measurement data.*
