# JAMES Routing Matrix — what model each mode actually calls

> **Status**: v0.6.1 v18.7 (2026-06-16). Verified by live probe
> `scripts/research/routing_matrix_probe.py` + resolver introspection.
> Re-run the probe after any routing change to keep this table honest:
> `python scripts/research/routing_matrix_probe.py --no-llm` (fast) or
> without `--no-llm` for a full live engine confirmation.

## Defaults

- `config.GEMMA_MODEL` = **gemma4:e4b** (general / chat default)
- `config.CODING_MODEL` = **qwen2.5-coder:32b**
- Thinking: gemma4 family receives `think:false` when
  `JAMES_GEMMA4_E4B_THINK_OFF=1` (production `.env`). Non-gemma4 models
  ignore the flag (think_policy no-op).

## Auto-routing table (no user model pick)

| Mode | Trigger (IntentClassifier) | Model | Resolution path | Observability | Status |
|---|---|---|---|---|---|
| **chat** | 일상 대화·인사 | **gemma3:12b** | engine.py `resolve_for_mode("chat", requested="")` → preference top | `[MODEL] mode=chat auto-routed → gemma3:12b` ✅ observed | **measurement-backed (Phase 2c)** |
| **retrieval** | 지식 검색·정보 조회 | **gemma3:12b** | engine.py `resolve_for_mode("retrieval", requested="")` → preference top | `[MODEL] mode=retrieval auto-routed → gemma3:12b` ✅ observed | **measurement-backed (Phase 3c)** |
| **meta** | 내부자료 인벤토리 | none (no LLM) | fast-path inventory generation | `(fast-path)` ✅ confirmed | n/a |
| **coding** | 코드 작성·버그 | qwen2.5-coder:32b | `llm.router(task_type="coding")` | `[coding_route]` / router log ✅ | dedicated router |
| **wiki_edit** | 지식 수정·삭제 (admin) | gemma4:e4b | `call_gemma(model=None)` → `resolve_chat()` → GEMMA_MODEL | silent | legacy (unmeasured) |
| **self_evolve** | 자메스 자기개선 (admin) | gemma4:e4b | `call_gemma(model=None)` → `resolve_chat()` → GEMMA_MODEL | silent | legacy (unmeasured) |
| vision | (FUTURE — not routed) | llava:13b | `call_gemma_vision` direct | n/a | inactive |

## Resolution priority (3-tier)

```
1. user secondary-picker selection      → catalog-validated tag wins (every mode)
2. chat/retrieval + no pick              → gemma3:12b (Phase 2c/3c; kill-switch JAMES_DISABLE_MODE_AWARE_ROUTING=1)
3. other mode + no pick                  → legacy GEMMA_MODEL (gemma4:e4b), or coding=qwen-coder:32b
```

## The `resolve_chat()` trap (important)

`resolve_chat()` passes `config.GEMMA_MODEL` as `requested`.
`resolve_for_mode` Step 1 returns the requested tag the moment it is
installed — so `resolve_chat()` returns **gemma4:e4b and never consults
the preference list**. Only `resolve_for_mode(mode, requested="")` (empty
requested) lets the preference list drive. This is why:

- chat-mode (Phase 2c) calls `resolve_for_mode("chat", requested="")`
  to actually reach the measured-best gemma3:12b.
- retrieval / wiki_edit / self_evolve still call `resolve_chat()` (via
  `call_gemma(model=None)`), so they stay on GEMMA_MODEL until each gets
  its own measurement + a wire that uses `requested=""`.

## Observability gap (noted, not yet fixed)

The silent default paths (retrieval / wiki_edit / self_evolve) emit **no
`[MODEL]` log line** on the happy path — `call_gemma(model=None)` only
prints `[MODEL_RESOLVE]` on a fallback warning. The live probe reports
"(silent default path — inferred)" for these. A 1-line logging
improvement (always print the resolved model) is a candidate for the
Phase 3 wire when these modes get measured, but is intentionally NOT
done now (no behavior change without measurement).

## Live probe results (2026-06-16)

```
chat        → gemma3:12b                       (21.4s)  ✅ observed
retrieval   → gemma4:e4b (silent — inferred)   (118s)   pipeline runs, model silent
meta        → (fast-path — no LLM)             (5.7s)   ✅ confirmed
coding      → qwen2.5-coder:32b (llm.router)   (99.6s)  ✅ observed
wiki_edit   → gemma4:e4b (silent — inferred)   (24.3s)
self_evolve → gemma4:e4b (silent — inferred)
```

## Phase 3a — local complexity-tier ladder (DEFINED, not yet consumed)

Operator decision 2026-06-16 (Option B): D5 escalates among **local
ollama model sizes** by query complexity, not local↔cloud. The existing
`BackendCapability` tier vocabulary (small ≤4B / medium 12-27B / large
70B+ or cloud) gives no third local rung — a 12 GB GPU has no local 70B+.
So the local ladder is its own mapping in `core/model_resolver.py`,
separate from the backend-tier system:

| Rung | Model | When (Phase 3b will wire) | Measured? |
|---|---|---|---|
| `light` | gemma3:4b | narrow scope / CAP_SUBSTITUTION / cheap | lost Phase 2b chat |
| `standard` | gemma3:12b | default; chat leader | ✅ Phase 2b |
| `deep` | gemma3:27b | broad scope / CAP_HEAVY / verify stage | not yet |

- `resolve_local_tier(rung)` — installed-check + downgrade (deep → standard → light) + env override `JAMES_LOCAL_TIER_<RUNG>`.
- Inspect: `python scripts/research/routing_matrix_probe.py --tier-ladder`
- **NOT consumed by the pipeline yet.** Phase 3b runs a complexity-paired measurement (narrow vs broad query × {4b, 12b, 27b}) BEFORE wiring escalation into D5 — α-7 caveat (no activation without measurement) is binding.

## Phase status (5-phase routing build-out)

- ✅ Phase 1 — preference list plumbing (`DEFAULT_PREFERENCE`, PR #969)
- ✅ Phase 2a/b/c — chat fixture + measurement + engine wire (PR #970/971/972)
- 🔄 **Phase 3** (Option B — local size ladder)
  - ✅ 3a — `LOCAL_TIER_LADDER` + `resolve_local_tier()` defined (plumb-first)
  - ✅ 3b — complexity-paired measurement done (4-cell: 4b/gemma4:e4b/12b/27b × multihop). **gold-grounded reversal**: judge-only said escalation pointless, but gold_signals shows 27b=1.000 > 12b=0.889 > 4b=0.852 > gemma4:e4b=0.815. Escalation has a basis (modest +0.111) but costs 2.3× latency + verbose answers. Side finding: gemma4:e4b (current default) is *lowest* on evidence-rich retrieval. See `reports/research-runs/v18.7-phase3b-tier-ladder/QUALITY_DELTA_CARD.md`.
  - ✅ 3c — **retrieval mode wired** to `resolve_for_mode("retrieval", "")` → gemma3:12b (the measured-best *default*; gemma4:e4b demoted as weakest on evidence-rich retrieval). Done via the same engine.py mode-routing block as chat (kill-switch generalized to `JAMES_DISABLE_MODE_AWARE_ROUTING`). **Full 27b complexity escalation NOT auto-wired** — the +0.111 gold-accuracy gain over 12b doesn't justify 2.3× latency + verbose answers for a default path. `LOCAL_TIER_LADDER` infra (3a) preserved for a future verify-stage-only deep escalation with verbosity-curbing response_style. `JAMES_AUTO_ROUTER` stays OFF.
- ✅ **Phase 4** — privacy gate (PII) + cost-aware cap (plumb-first
  primitives shipped in PR #980, design memo
  `docs/design/v0.6.1-phase4-privacy-cost-cap.md`).
  - ✅ 4a — `core/routing/` primitives: `PrivacyCheck` /
    `detect_pii` / `check_query_privacy` + `CostStatus` /
    `CostBudget` / `default_budget` / `check_cap`. Default
    behaviour byte-identical (force_local OFF, cap=0.0).
    `resolution_snapshot()` advances to
    `phase4_privacy_cost_cap_primitives` and exposes `privacy` +
    `cost_cap` sub-keys for operator introspection. Surface locked
    by `RoutingPhase4Surface` lock-test + `routing_phase4_primitives`
    pre-flight check.
- 🔄 **Phase 5** — cloud egress consumer wire + cloud-as-preference + sub-class routing inside chat + admin routing dashboard
  - ✅ 5a — **gate wired into the cloud egress site**
    (`scripts/research/local_vs_cloud_paired.call_cloud_via_
    abstraction`). Gate calls `check_query_privacy(prompt)` +
    `check_cap(tokens_estimate, usd_estimate)` BEFORE `run_cloud_
    egress`. Trips raise `RuntimeError("cloud refused by privacy
    gate: ...")` / `RuntimeError("cloud refused by cost cap: ...")`
    which the caller's cloud-error catch records. Source-level
    invariants locked by `WireSourceInvariantTests` in
    `tests/test_phase5a_cloud_gate.py` (5 source-pattern checks +
    3 behaviour tests with mocked egress). Default behaviour
    byte-identical: gate is a pure no-op until the operator flips
    `JAMES_PRIVACY_FORCE_LOCAL=1` or sets
    `JAMES_COST_CAP_MONTHLY_USD>0`.
  - ⏳ 5b — production router cloud branch wire (same gate, applied
    inside the eventual `engine.py` cloud route — gated on Phase
    5 cloud-as-preference measurement).
  - ⏳ 5c — cloud as preference option + sub-class routing inside chat + admin routing dashboard.

**Phase 4 env contract** (all default OFF / no-cap):

| Env | Default | Effect |
|---|---|---|
| `JAMES_PRIVACY_FORCE_LOCAL` | unset (OFF) | When `1`, the gate blocks egress on any PII pattern match. When unset, matches are reported but not blocking. |
| `JAMES_PRIVACY_PII_PATTERNS_EXTRA` | unset | Comma-separated `name:regex` pairs — operator-extensible patterns. Invalid regex logged + skipped, never raises. |
| `JAMES_COST_CAP_MONTHLY_USD` | `0.0` | USD ceiling for the current month. `0.0` = no cap. |
| `JAMES_COST_CAP_FILE` | `$JAMES_WORKSPACE/.james_cost.json` (cwd fallback) | Tally file path. |

Layering vs §5.7.12 / §5.7.13:

- §5.7.12 / §5.7.13 — per-entity mask / pass / keep-local INSIDE a
  cloud call (already shipped in `core/abstraction/`).
- Phase 4 — per-query pre-check that the cloud call can happen at
  all (privacy gate + cost cap).

These are orthogonal. A query can pass Phase 4 and still have its
entities masked by §5.7.12; or fail Phase 4 (PII / over-cap) and
never reach §5.7.12.

Related memory: `project_routing_buildout_5phase_v18_7`,
`project_phase2c_engine_chat_wire_v18_7`,
`project_phase2b_chat_mode_measurement_v18_7`.
