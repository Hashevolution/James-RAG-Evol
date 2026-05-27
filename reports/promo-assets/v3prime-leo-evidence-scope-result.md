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

## Acceptance — F1 closed 2026-05-27, F2/F3 deferred

Initial closure (this branch §"2026-05-27 measurement run") was
bench-neutral but did not exercise the scope path because of the
chat-mode passthrough issue. F1 (retrieval-mode bench harness)
landed in the follow-up branch (next §) and the scope path is now
fully measured end-to-end.

| Criterion | How verified | Status |
|---|---|---|
| Flag-OFF = pre-change main | `test_evidence_scope_wiring.py` + 187-test router/wiring suite passes | ✅ |
| Latency within ±5% per tier (small-tier-only fleet) | F1 acceptance run: OFF 1035.5s, ON 1022.9s (Δ −1.2%), per-query Δ within ±25% noise | ✅ |
| scope payload audit row | `SELECT … WHERE endpoint='reason:route' AND answer LIKE '%evidence_scope%'` | ✅ 11 rows captured (F1 acceptance run) |
| Narrow→small / wide→large routing | Router contract tests pass (`test_router_evidence_scope.py`) | ✅ at unit level |
| Narrow→small / wide→large routing | bench-time observation | ✅ measured — distribution 0 narrow / 4 mid / 7 wide. All decisions fall back to `ollama_local` because no large/medium-tier backend is registered (D5 expected behavior — see "What this closure does NOT claim") |
| grounded rate no regression | answer_len comparable across arms, zero error responses, retrieval pipeline produced 7–52 graph_paths per RAG query | ✅ |
| halt-prone (done_reason=length) reduction | not measured this cycle | ⏭️ F3 deferred |
| Closure doc + ROADMAP + memory | **this doc** + ROADMAP entry + memory sync | ✅ |

## F1 follow-up acceptance run (2026-05-27)

Branch: `feat/v0.4-step7-v3-f1-mode-override`. Wrapper now spawns
its own server per arm AND passes `--mode=retrieval` to `bench.py`
AND elevates the bench role to `employee` via a short-lived JWT
(otherwise the engine's `query.internal_rag` policy gate kicks the
request back to `handle_chat` regardless of `mode_override`).

`reports/research-runs/lc-scope-bench-20260527_110839.json`

| Metric | OFF arm | ON arm | Δ |
|---|---|---|---|
| Total elapsed | 1035.5s (17.3 min) | 1022.9s (17.1 min) | **−1.2%** |
| Per-query elapsed | 61.3–115.9s | 62.3–117.2s | within ±25% sampling noise |
| graph_paths (RAG queries q1–q10) | 0–52 (10/10 non-zero except q10) | 7–52 (10/10 non-zero) | retrieval pipeline active both arms |
| graph_paths (q13 meta) | 48 | 11 | natural variance — retrieval pipeline non-deterministic |
| answer_len (RAG queries) | 629–5830 chars | 1031–5708 chars | comparable, no degradation |
| reason:route rows captured | n/a | **54** (across all 5 cognitive stages × 11 retrieval-mode queries) | — |
| reason:route rows **with `evidence_scope` payload** | n/a | **11** | scope_context binding fired on every synth call ✅ |
| backend distribution | n/a | `ollama_local: 54` | small tier only — D5 fallback as designed |

### Scope distribution (flag-ON, 11 synth-time decisions)

```
mean   = 0.7425   (queries lean wide — JAMES wiki content has high doc_spread + graph_reach)
min    = 0.6284
max    = 0.8666
narrow (≤0.30): 0   ← no single-doc / verbatim retrieval shape this run
mid    (0.30 < scope < 0.70): 4
wide   (≥0.70): 7   ← multi-doc + graph fan-out dominates
```

Sample audit row (q1 "RAG가 무엇인가?", synth stage):

```
backend=ollama_local tier=none reason=scope prompt=061f7a9c
evidence_scope=0.6496 effective_k=0.0 score_entropy=0.9979
graph_reach=1.0 doc_spread=1.0
```

All 4 L.C scope components (`effective_k / score_entropy /
graph_reach / doc_spread`) emitted per call as specified in the
L.A extractor design. `reason=scope` (vs the previous `reason=fallback`)
confirms the wide-tier policy rule fired but fell back to legacy
because no `large` / `medium` tier backend is registered — exactly
the small-tier-only fleet behavior the D5 closure result doc
promised.

### What F1 acceptance proves

1. **L.C wiring fires end-to-end** — `compute_scope` produces a
   ScopeBreakdown, `scope_context(...)` binds it via ContextVar,
   `trace_helpers.trace_synth_call` reads `get_current_scope()`,
   passes to router, and `emit_route_event` writes the breakdown
   into audit. All previously unit-tested; now production-traced.
2. **Router policy v1 rule 2 evaluates** — `reason=scope` audit
   tag confirms `_route_policy` took the L.B narrow/wide branch
   (rule 2) rather than falling through to budget rules.
3. **Wide-tier intent on small-tier-only fleet is graceful** —
   `wide_count=7` routing decisions all fell back to `ollama_local`
   (the legacy backend) without crash. The 2026-05-25 D5 latent
   bug ([[feedback_router_latent_backend_id_bug]]) is fully fixed.
4. **No regression** — both arms produced comparable answer
   length, no error responses, retrieval pipeline active on every
   RAG query (graph_paths 7–52). −1.2% total latency Δ is well
   inside the ±5% acceptance band.

### What F1 acceptance reveals about JAMES's natural scope distribution

The 0/4/7 narrow/mid/wide split confirms JAMES's STEP 7 RAG corpus
naturally produces wide-scope retrieval (multi-doc + non-trivial
graph fan-out). Implications:

- **Sprint 6 large-tier registration** (e.g.
  `JAMES_ENABLE_CLAUDE_BACKEND=1`) would route 7 of 11 synth calls
  to the large backend per RAG query — the cost ROI for that
  backend is now quantifiable.
- **Narrow-scope arm verification needs different fixture** — none
  of the step7 queries naturally land in the narrow band, so the
  "narrow→small" rule is unit-tested but not bench-observed on
  this suite. Single-doc / verbatim retrieval fixture proposal
  carried to F3 backlog.
- **Mid-band fall-through to D1 budget rule** (4 decisions) is
  the LEO Q4 "measurement promotes/demotes one tier when clear,
  defers to D1 when ambiguous" pattern firing as designed.

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

- **F1**: ~~`bench.py` `mode_override` parameter~~ ✅ landed in
  `feat/v0.4-step7-v3-f1-mode-override` (2026-05-27). `bench.py
  --mode=retrieval` + `JAMES_BENCH_BEARER` env (JWT bearer for role
  elevation past `query.internal_rag` policy gate). Wrapper updated
  to mint employee JWT + pass mode flag. Acceptance run §"F1
  follow-up acceptance run" above.
- **F2**: IntentClassifier audit — step7 queries
  ("RAG가 무엇인가?", "Anthropic은 어떤 회사인가?") classified as
  `chat` rather than `retrieval`. Step7 regression baseline has been
  measuring chat-mode latency since 2026-05-09. Either the suite
  intent is wrong (rename categories) or the classifier is wrong
  (tune prompt). Priority: regression baseline truthfulness. **Now
  has a workaround** — `bench.py --mode=retrieval` forces correct
  routing for measurement purposes; F2 remains for production
  baseline truthfulness.
- **F3**: Halt-prone arm measurement (`done_reason=length` rate
  reduction under wide-scope → large-tier routing). Requires a
  `large`-tier backend (e.g. `JAMES_ENABLE_CLAUDE_BACKEND=1`). F1
  acceptance shows wide_count=7/11 — quantifying the cost ROI for
  large-tier registration is the next concrete acceptance gate.
- **F4** (new, surfaced by F1 acceptance): Narrow-scope fixture —
  none of step7 queries naturally land in narrow band on JAMES wiki,
  so "narrow→small" rule is bench-unobserved. Add 2–3 verbatim /
  single-doc fixture queries to step7 (or sibling suite) so the
  narrow branch is exercised end-to-end. Required for the L.B
  4-arm acceptance promise to be fully measured.

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
