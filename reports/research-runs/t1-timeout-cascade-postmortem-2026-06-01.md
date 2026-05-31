# T1 Timeout Cascade — Post-Mortem (UUU)

> **Symptom**: T1 cells L3 (ADAPTIVE_BUDGET only) and L4
> (SCOPE_ROUTING only) at gemma4:e4b production tier both ran 100
> queries per cell and ALL 200 queries returned
> `status=timeout, elapsed=120.0, answer_len=None, preview=""`.
> Resulting 5-axis aggregates are all-zero / saturated; no useful
> attribution data recovered.
>
> **Compute wasted**: ~6.7 hours (12001.9 s + 11999.6 s on local
> gemma4:e4b GPU).
>
> **Date**: 2026-06-01 (T1 launched 2026-05-31 17:28, completed
> 2026-06-01 00:09).
>
> **Cycle ledger entry**: this is the **7th wrong-fix-averted** in
> the α-5 cycle — *averted* because the 4-step rule applied to the
> matrix runner stdout (which reported `path=0 graded=0 abst_f1=0.4
> token=0 latency=0`) immediately surfaced the cascade pattern
> before any conclusion about ADAPTIVE_BUDGET / SCOPE_ROUTING was
> drawn.

---

## 1. 4-step rule application

| Step | Observation |
|---|---|
| 1. saturated axes | path=0, graded=0, abst_f1=0.4 (structurally perfect refusal — TP=25 FP=75 FN=0 TN=0 because all 100 answers were `None` → treated as abstention by phrase detector), token=0, latency=0 |
| 2. read raw samples | `bench_cd4ac76_multihop_rag_20260531_204851.json` (L3) first 3 rows: `status=timeout, elapsed=120.0, answer_len=None, preview=""` — 100/100 the same pattern |
| 3. JAMES response keys | server returned nothing within bench.py's per-query 120s timeout (`scripts/bench.py:501`); answer/sources/graph_paths all unset |
| 4. design vs matcher | bench.py + oracle work as designed — they're scoring whatever the server returned. The server returned nothing for 200 consecutive queries. This is **system-level**, not measurement-side. |

---

## 2. Failure attribution

| Layer | Was it the ADAPTIVE_BUDGET / SCOPE_ROUTING flags? | Evidence |
|---|---|---|
| ADAPTIVE_BUDGET (L3) | **probably not directly** | L1 baseline (production-default ADAPTIVE_BUDGET=0) completed cleanly at 64s/query average; same fixture worked in T0 |
| SCOPE_ROUTING (L4) | **probably not directly** | same as above; LEO's evidence_scope override at L.B is pure parameter, no infinite-loop risk in the code |
| Server-side stack | **most likely** | Ollama + JAMES server stack ran ~6h continuously through T0; degraded performance plausible. Per-query timing went from 64s (T0 cell L1) to >120s (every T1 query) |
| Per-query 120s timeout floor | **secondary** | even if server slowed to 100-150s per query, the 120s timeout would catch many; a longer timeout might have produced partial data |

The most parsimonious explanation: **Ollama service degraded over
~6h of continuous heavy use**. The matrix runner restarts the
JAMES Python server per cell (fresh process), but Ollama is a
persistent service it does not restart. By the time T1 cell L3
started at 17:28 (after T0 finished at 15:49), Ollama had been
serving for ~5h. By mid-L3 it was slow enough that every query
exceeded 120s.

---

## 3. What this is NOT

- **NOT an ADAPTIVE_BUDGET design failure** — the layer was never
  exercised meaningfully (server returned nothing for the layer's
  budget logic to act on)
- **NOT a SCOPE_ROUTING design failure** — same reason
- **NOT a JAMES code bug** — JAMES server's role here is to forward
  queries to Ollama and wait for the model; Ollama's slowness
  isn't a JAMES correctness issue
- **NOT a bench.py bug** — timeout fired as designed; it's the
  *floor* that's too low for degraded-Ollama conditions

---

## 4. What this IS

- **An operational lesson about Ollama session lifetime** — re-run
  long matrix sweeps with Ollama restarts between long phases
- **A measurement-prerequisite gap** — the layer-intent matrix
  (memory `mechanism_layer_intent_axis_alignment`) said:

  > "AUTO_ROUTER (D5) requires multi-tier backend registration ...
  >  ADAPTIVE_BUDGET (D1) requires per-stage budget metric capture"

  but did NOT include the obvious **"backend service in healthy
  state"** prerequisite. This is the new addition.

- **The 7th wrong-fix-averted in the α-5 cycle**:
  - Without the 4-step rule, the operator might have read
    `path=0 / graded=0 / abst_f1=0.4` and concluded "ADAPTIVE_BUDGET
    breaks JAMES at production tier" — a false bucket-(b) or
    bucket-(a) conclusion. Step 2 (reading the raw bench file)
    immediately surfaced the timeout cascade.

---

## 5. Recovery options

| Option | Cost | Risk |
|---|---|---|
| **A. Restart Ollama service, rerun T1 L3 + L4** | ~3.5 h compute (~110 min × 2) | low — fresh Ollama state ought to perform like T0 |
| **B. Bump bench.py per-query timeout 120s → 240s** | one-line code, then rerun T1 (~7 h) | medium — masks the real Ollama issue but produces data |
| **C. Skip per-layer isolation, treat L3/L4 as "not in evidence"** | $0 | low — α-5 closure already had Branch B; T1 was optional |
| **D. Investigate Ollama degradation root cause** | unbounded | tangential to α-5 |

**Recommended sequence**: A first (restart Ollama → rerun T1) → if A
still hits timeouts, B → if B still hits timeouts, C (accept "not
in evidence" for L3 + L4 like AUTO_ROUTER) and move to α-6.

---

## 6. Operational guidance — long matrix sweeps

Add to the matrix closure runbook (`docs/handovers/v0.4-alpha-5-matrix-closure-runbook.md`)
a new Step 0.5 between pre-flight check and rescore:

> **0.5 — Ollama healthcheck before any new cell launch.**
> If the previous cell run cumulative time exceeds 4 hours,
> restart Ollama (`Restart-Service Ollama` on Windows) before
> launching the next cell. Ollama service state can degrade under
> sustained heavy use; cell-level Python server restarts don't
> address it.

Also add to bench.py: a smoke-check at start of run that issues
one warm-up query and fails fast if it times out, instead of
chewing through 100 queries × 120s = 200 minutes of wasted
compute.

---

## 7. Updates to other artifacts

### 7.1 `memory/mechanism_layer_intent_axis_alignment.md`

Add to §"Layer 측정 prerequisite 의무" table:

| Layer | Prerequisite (new line) |
|---|---|
| ALL | **Backend service (Ollama / cloud provider) in healthy state — query latency in the normal range for the model, not degraded by sustained sweep load** |

### 7.2 `memory/feedback_oracle_phrase_artifacts.md` §"확장 3"

Add "사건 7": T1 timeout cascade — example of step 2 (read raw
samples) catching a system-side failure that the saturated axes
made look like a layer-design failure.

### 7.3 Cycle ledger

- Wrong-fix-averted count: 6 → **7**
- New PR: this one (UUU)

---

## 8. T1 data status

For the α-5 cycle's final attribution:

| Cell | Status | Evidence |
|---|---|---|
| L1 (production baseline) | ✅ valid (rescored) | T0 bench |
| L5 (full stack) | ✅ valid (rescored) | T0 bench |
| Sanity L1/M_M-thinkON | ✅ valid (rescored) | T0 sanity bench |
| L3 (ADAPTIVE_BUDGET only) | ❌ **not in evidence** — timeout cascade | UUU |
| L4 (SCOPE_ROUTING only) | ❌ **not in evidence** — timeout cascade | UUU |

The cycle's **per-layer attribution gap remains open**. ADAPTIVE_BUDGET
and SCOPE_ROUTING individual verdicts are still pending. AUTO_ROUTER
verdict was already "not in evidence" per DDD (Correction 5).

So at α-5 cycle close, **3 of 3 routing-layer single-flag verdicts**
are "not in evidence" — only the all-on L5 cell has data, and that
data already classified `reject` against L1 baseline.

---

## 9. Bigger lesson — "not in evidence" is the right verdict

The cycle's self-discipline (4-step rule + layer-intent matrix +
prerequisite check) repeatedly funnels to a single conclusion:
*"the layer's verdict at this point is not in evidence, not 'no
effect'."* This is the bucket-(a) measurement-debt family's
honest output. It does NOT mean the layer is bad; it means the
measurement infrastructure to evaluate the layer cleanly is the
work that comes first.

This carries forward to α-6 Phase 3 / α-6 Phase 5+ — *"plan the
prerequisites before the cells, not during."*

---

## 10. References

- T1 launch: matrix runner output at
  `C:\Users\karu-\AppData\Local\Temp\claude\C--Project-James-RAG-Evol-v010\...\b82bipgbh.output`
- T1 bench files:
  `reports/bench_cd4ac76_multihop_rag_20260531_204851.json` (L3) +
  `reports/bench_cd4ac76_multihop_rag_20260601_000906.json` (L4)
- T1 cell JSONs:
  `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/qvt-ablation-cell-L{3,4}-M_M.json`
- RRR memo (pre-T1 hypothesis space):
  `reports/research-runs/t1-l3-silent-failure-hypothesis-2026-05-31.md`
  — H1/H2 (JSON serialisation / stdout buffering) RESOLVED as
  not the cause; real cause is timeout cascade
- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`
- Layer-intent matrix: `memory/mechanism_layer_intent_axis_alignment.md`
- bench.py per-query timeout: `scripts/bench.py:501`
- Closure runbook: `docs/handovers/v0.4-alpha-5-matrix-closure-runbook.md`
- DDD post-closure correction (AUTO_ROUTER no-op + ADAPTIVE_BUDGET wrong-axes): PR #648
