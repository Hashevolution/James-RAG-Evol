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
| **retrieval** | 지식 검색·정보 조회 | gemma4:e4b | `call_gemma(model=None)` → `resolve_chat()` → GEMMA_MODEL | silent (no log on happy path) | legacy (unmeasured) |
| **meta** | 내부자료 인벤토리 | none (no LLM) | fast-path inventory generation | `(fast-path)` ✅ confirmed | n/a |
| **coding** | 코드 작성·버그 | qwen2.5-coder:32b | `llm.router(task_type="coding")` | `[coding_route]` / router log ✅ | dedicated router |
| **wiki_edit** | 지식 수정·삭제 (admin) | gemma4:e4b | `call_gemma(model=None)` → `resolve_chat()` → GEMMA_MODEL | silent | legacy (unmeasured) |
| **self_evolve** | 자메스 자기개선 (admin) | gemma4:e4b | `call_gemma(model=None)` → `resolve_chat()` → GEMMA_MODEL | silent | legacy (unmeasured) |
| vision | (FUTURE — not routed) | llava:13b | `call_gemma_vision` direct | n/a | inactive |

## Resolution priority (3-tier)

```
1. user secondary-picker selection   → catalog-validated tag wins (every mode)
2. chat + no pick                     → gemma3:12b (Phase 2c; kill-switch JAMES_DISABLE_MODE_AWARE_CHAT=1)
3. other mode + no pick               → legacy GEMMA_MODEL (gemma4:e4b), or coding=qwen-coder:32b
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

## Phase status (5-phase routing build-out)

- ✅ Phase 1 — preference list plumbing (`DEFAULT_PREFERENCE`, PR #969)
- ✅ Phase 2a/b/c — chat fixture + measurement + engine wire (PR #970/971/972)
- ⏳ **Phase 3** — D5 AUTO_ROUTER (complexity-tier escalation) + backend
  tier adapters (gemma3:12b / 27b / mixtral need `BackendCapability`
  tier declarations)
- ⏳ Phase 4 — privacy gate (PII) + cost-aware cap + cloud (Claude) routing
- ⏳ Phase 5 — sub-class routing inside chat + admin routing dashboard

Related memory: `project_routing_buildout_5phase_v18_7`,
`project_phase2c_engine_chat_wire_v18_7`,
`project_phase2b_chat_mode_measurement_v18_7`.
