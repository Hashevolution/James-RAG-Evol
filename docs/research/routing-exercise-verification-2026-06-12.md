# Routing exercise — D5 + LEO L runtime verification

> **Date**: 2026-06-12 (post-v0.4.4)
> **Purpose**: 사용자 catch — "라우팅 work 가 어디서 정체됐는지 환기" — 에 대한 응답으로 실제 multi-backend env 에서 D5 + LEO L routing decision 을 trace 한 검증 결과.
> **Honest tier**: ⭐ infrastructure exercise — production 측정 아님. Router decision logic 의 design correctness 확인용.

---

## 1. Motivation

User raised that model routing work has felt stalled since some past session. Looking at git history, three routing cycles all **CLOSED** in May 2026:

- **D1** Adaptive Budget (output-token prediction, 7-tier)
- **D5** Auto-routing (2026-05-25, 10 PRs #474-#484): `JAMES_AUTO_ROUTER` flag + 4-rule policy + 5-stage wiring + entity alias pack
- **D6** Retry/Truncation (2026-05-25 KST late, PRs #486-#488): `complete_with_retry` + native Ollama `done_reason`
- **LEO L** Evidence-scope routing (2026-05-25~, PRs #514 / #516 / #526): Leo's input-side signal (evidence scope) augmenting D1's output-side prediction

The α-5 post-closure (#648) flagged that `AUTO_ROUTER` was "no-op in single-backend env". User wanted to verify this is design intent (not bug) and see whether further D5 follow-ups are warranted.

## 2. Method

Two backends ship with v0.4.4 (`core/reasoning/backends/`):
- `ollama_local` — tier=small / provider=local (always registered)
- `claude_code_cli` — tier=large / provider=cloud (registered only when `JAMES_ENABLE_CLAUDE_BACKEND=1`)

Exercise:

```bash
JAMES_ENABLE_CLAUDE_BACKEND=1 JAMES_AUTO_ROUTER=1 python ...
```

Then traced `Router().select_backend(stage, prompt, ...)` across:
- 5 stages × 3 prompt sizes × 2 budget signals (1500 substitution / 4000 heavy)
- 1 stage (`synth`) × 3 evidence_scope values (0.10 narrow / 0.50 mid / 0.90 wide; LEO L.B)

No actual LLM call made — `select_backend()` returns the decision only.

## 3. Findings

### 3.1 Decision matrix (multi-backend env, AUTO_ROUTER on)

```
stage           prompt sizes (small/medium/large)        budget=1500    budget=4000
─────────────────────────────────────────────────────────────────────────────────────
query_rewriter  ollama_local everywhere                   ollama_local   ollama_local
planner         ollama_local everywhere                   ollama_local   ollama_local
reflect         ollama_local everywhere                   ollama_local   ollama_local
verify          claude_code_cli everywhere ← grounding-critical (D5.C.1)
synth           ollama_local everywhere                   ollama_local   ollama_local

stage   evidence_scope=0.10   evidence_scope=0.50   evidence_scope=0.90 (wide)
─────────────────────────────────────────────────────────────────────────────────
synth   ollama_local           ollama_local           claude_code_cli ← LEO L.B wide-scope escalation
```

### 3.2 What works (design correctness confirmed)

| Mechanism | Confirmed | Evidence |
|---|---|---|
| **D5.C.1 grounding-critical stage rule** | ✓ | `verify` → `claude_code_cli` always (independent of prompt size / budget) |
| **LEO L.B evidence_scope wide → large** | ✓ | `synth` + scope=0.90 → `claude_code_cli` (narrow + mid stay on `ollama_local`) |
| **Default-off byte-identical baseline** | ✓ | With `JAMES_AUTO_ROUTER=0`, all 5 stages → `ollama_local` regardless of inputs (pre-D5 behavior preserved) |
| **`JAMES_ENABLE_CLAUDE_BACKEND=1` gate** | ✓ | Without the flag, `claude_code_cli` is not in the registry → AUTO_ROUTER cannot escalate (correctly designed no-op) |

### 3.3 What does NOT trigger escalation (also design-correct)

- **Prompt size alone**: a 5000-char prompt on `synth` still stays on `ollama_local`. Escalation needs an explicit signal (`budget_signal` or `evidence_scope`), not heuristic prompt-length detection. This is correct: D5's policy is `budget_signal`-driven; LEO L's policy is `evidence_scope`-driven; raw prompt size was deliberately not made a routing axis (would introduce stochastic length-vs-tier coupling that the D1/D5/LEO trio explicitly avoids).
- **Budget signal alone on non-grounding-critical stages**: even `budget_signal=4000` (heavy) on `synth` stays on `ollama_local`. The current D5.C.1 policy reserves `claude_code_cli` for grounding-critical stages and LEO L.B wide-scope cases; pure-budget heavy synth still routes to local. This may be a future v2 axis if multi-backend cost calculus matters, but is design-correct for v0.4.4.

## 4. α-5 verdict re-examination

α-5 post-closure (PR #648) flagged `AUTO_ROUTER` as "no-op in single-backend env." This exercise confirms:

> **α-5 was empirically correct AND design-intent.** In a single-backend env (the default; `JAMES_ENABLE_CLAUDE_BACKEND` unset), the registry has only `ollama_local`. There is nothing to escalate to. The routing code still runs, still emits `reason:route` audit rows, still returns a backend ID — but the decision space collapses to a single option. This is by design: D5's auto-router activates the moment a second backend joins the registry; it does not synthesise a fake escalation target.

No code change needed. The α-5 verdict was an honest observation about the user's environment, not a bug report.

## 5. D5 follow-up re-prioritisation

The D5 closure entry listed four follow-ups. Updated assessment after this exercise:

| Follow-up | Status | New verdict |
|---|---|---|
| **cost-based scoring v2** | Not shipped | **Deferred indefinitely.** User runs Max-plan claude (flat-rate), so per-call cost-axis has marginal value. Re-evaluate if a metered-API backend is added or if a customer pilot demands per-call cost budgeting. |
| **per-pack policy** | Not shipped | **v1.0 deferred.** Per-domain pack routing policy requires the plugin API freeze, which is the v0.3 → v0.5 → v1.0 gate. |
| **per-stage explicit override** | **Already implemented** | `JAMES_BACKEND_<STAGE>` env override exists in `core/reasoning/backends/__init__.py::resolve_backend_for_stage`. Verified at runtime via the `[BACKEND] JAMES_REASONING_BACKEND=...` fallback message. No additional work needed. |
| **embedding swap BL-9** | Not shipped | Retrieval-side, orthogonal to routing. Separate cycle if customer pilot needs a non-bge-m3 embedder. |

## 6. Decision

**Routing track is design-complete and runtime-verified at v0.4.4.** No further D5 / LEO L wiring required. The 'stalled' impression was a consequence of operating in a single-backend environment by default; activation requires only the operator's explicit consent (`JAMES_ENABLE_CLAUDE_BACKEND=1`).

Next routing-related work, if any, is gated on either:
1. A multi-backend production setting (operator's own deployment with claude API key or other cloud provider).
2. A customer pilot whose architecture requires per-pack routing policy (`v0.5 → v1.0` plugin API freeze gate).

Until either of those triggers, the routing infrastructure is **complete and warm**.

## 7. Related

- `core/reasoning/router.py` — Router + `select_backend` + `emit_route_event`
- `core/reasoning/backends/__init__.py::_autoregister` — registry + JAMES_ENABLE_CLAUDE_BACKEND gate
- `core/reasoning/backends/ollama_local.py` + `claude_code_cli.py` — the 2 builtins
- `docs/handovers/v0.3.x-direction5-auto-routing-track.md` — D5 design memo
- `docs/handovers/v0.4-leo-evidence-scope-routing-track.md` — LEO L design memo
- Memory: `direction_5_auto_routing_closure.md`, `feedback_d1_d5_retry_doubled_wiring_gap.md`, `feedback_router_latent_backend_id_bug.md`
- α-5 verdict: PR #648
