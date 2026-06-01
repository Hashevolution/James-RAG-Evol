# α-6 Phase 2 — Rate-Limit Corruption Post-Mortem (8th wrong-fix-averted)

> **Symptom**: Phase 2 cell `C_minus / M_S` (gemma3:4b, all sectors
> off) "completed" in 53 seconds with an apparently valid 5-axis
> aggregate (`abst_f1=0.521`, `graded=0.137`). Background task
> `b7z1i104c` reported "succeeded."
>
> **Reality**: 70 of 100 queries returned HTTP 429 (rate limit
> exceeded) instead of reaching the LLM. The bench treated empty
> answers as abstentions, fabricating apparently-valid scores.
>
> **Caught by**: the 4-step rule + arithmetic — *"latency 1.71s
> × 100 = 171s, but cell finished in 53s; the math doesn't add
> up."* Log inspection immediately surfaced the 429s.
>
> **Date**: 2026-06-01 PM (Phase 2 mid-flight)
> **Wrong-fix-averted count**: 7 → **8**
> **JAMES code change attributable to this**: 0 lines

---

## 1. The 4-step rule, applied

| Step | Observation |
|---|---|
| 1. axis values | abst_f1 0.521, graded 0.137 — **plausible**. Latency 1.71s — **fast but plausible** for small model |
| 2. arithmetic / raw log | cell wall-clock 53s. If 100 queries × 1.71s avg = 171s, the cell can't have finished in 53s. Difference forces inspection. |
| 3. raw output read | task output log lines 31-100 = `"HTTP_ERROR: 요청 한도 초과. 60초 후 재시도하세요. remaining: 0"` — 70 queries rate-limited |
| 4. design vs matcher | bench treats `status != "ok"` answers as missing data; oracle treats `answer is None / empty` as abstention. 70 errors → 70 "abstain" votes → fabricated TP/FP/FN/TN |

The math step (`53s ≠ 171s`) was the unlock. Without it the
fabricated abst_f1 = 0.521 looks like a normal small-model
abstention pattern.

---

## 2. Root cause

`server_llmwiki.py:117`:

```python
_rate_limiter = RateLimiter(max_requests=30, window_sec=60)
```

**30 requests per 60 seconds** = 0.5 req/sec per IP. Designed for
single human operator + occasional UI use.

When the bench hits the server from localhost with gemma3:4b's
~1.7s/query response time:
- 30 queries succeed in ~51s
- Request 31 onward hit the 60s window cap → 429
- The 60s window resets ~9s later, but by then 70 queries are
  already cued and they all blast through instantly returning 429s

Larger models (gemma4:e4b at ~12s/query in C_rag-basic/M_M) never
hit this because their per-query latency keeps the request rate
under 30/min naturally.

**Why this didn't show up before**:
- α-5 measured gemma4:e4b only; ~12s/query × 30 = 360s window, no
  rate limit hit
- α-6 Phase 1 same (M_M tier, ~12-66s/query)
- α-6 Phase 2's C_minus/M_S is the FIRST cell with sub-2s/query
  on this matrix

---

## 3. Affected cells

| Cell | Status |
|---|---|
| `C_minus / M_S` | **CORRUPTED** (70/100 errors) — rerun required |
| `C_rag-basic / M_S` | OK (~2.5s/query; under rate limit ceiling) |
| `C_rag-graph / M_S` | likely OK (graph adds latency) — verify post-run |

Also pre-emptively affected if launched as-is:
- `L1 / M_S` (full stack but small model — query latency could be
  fast enough to hit limit)
- Future `M_S` cells with cheap sector configurations

---

## 4. Fix options (ranked by leverage)

### Option A — bench.py rate-limit-aware retry (recommended)

Add to `scripts/bench.py`:

```python
# Detect 429 + Retry-After header, sleep, then retry up to N times.
if r.status_code == 429:
    retry_after = int(r.headers.get("Retry-After", "60"))
    time.sleep(retry_after + 1)
    continue  # retry the same query
```

This is the *bench-side* fix. The server's rate limit stays at
the operator-safe 30/60s; bench just plays nice.

Effort: ~30 min code + 30 min test
Affects: bench.py only (not JAMES core)

### Option B — env-var override for the rate limit

```python
_rate_limiter = RateLimiter(
    max_requests=int(os.environ.get("JAMES_RATE_LIMIT_MAX", "30")),
    window_sec=int(os.environ.get("JAMES_RATE_LIMIT_WINDOW_SEC", "60")),
)
```

Operator opts the cell into `JAMES_RATE_LIMIT_MAX=10000` to
effectively disable.

Effort: ~20 min code + test
Affects: `server_llmwiki.py`

### Option C — matrix runner passes the env override per cell

Layered on B: matrix runner sets `JAMES_RATE_LIMIT_MAX=10000` in
its server spawn env so EVERY cell bypasses the rate limit. No
operator action needed.

Effort: ~10 min additional on top of B
Affects: matrix runner + B

### Combined recommendation

**B + C** in one PR (~1 hour total): operator can set the env, AND
the matrix runner sets it automatically per cell. Bench.py also
gets a retry-on-429 path as defense in depth.

Without the fix:
- Every α-6 cell with sub-3s/query will corrupt silently
- Phase 3a (gemma3:1b at sub-1s/query) will be ENTIRELY corrupted
- Phase 3b (small qwen/llama models) likely corrupted too

---

## 5. Discipline log — 8th wrong-fix-averted

Cycle wrong-fix-averted count: 7 → **8**.

| # | Catch | Bucket | When |
|---|---|---|---|
| 1 | `path_recall=0` was bench dropping sources field | (d) | α-5 Correction 1 |
| 2 | abstention F1 0.316 missing English refusals | (d) | α-5 Correction 2 |
| 3 | matrix subprocess hardcoded step7 | (a) | α-5 Correction 3 |
| 4 | matrix glob hardcoded step7 | (a) | α-5 Correction 4 |
| 5 | AUTO_ROUTER no-op (single backend) | (a) | α-5 post-closure |
| 6 | ADAPTIVE_BUDGET judged on wrong axes | (a) | α-5 post-closure |
| 7 | T1 Ollama timeout cascade | (a)/(b) | α-5 T1 |
| **8** | **Phase 2 rate-limit corruption** | **(a)** | **α-6 Phase 2** |

**Pattern**: every cycle's first run at a NEW (model, configuration)
point catches a measurement-side issue. The 4-step rule applied
within minutes of cell completion remains the cheapest catch.

JAMES code change attributable to all 8 corrections: **0 lines**.

---

## 6. Memory update

`memory/feedback_oracle_phrase_artifacts.md` §"확장 3" should add
"사건 8 — rate-limit corruption" as a worked example of the
**arithmetic step** of the 4-step rule:

> When axis values look plausible but cell wall-clock time
> contradicts per-query latency × n_queries, the corruption is in
> the request-success path before the LLM, not in the LLM or oracle.

Run `scripts/qvt_promote_findings.py` after appending to the
findings log to draft the memory entry.

---

## 7. Immediate operator actions

1. **Don't trust C_minus/M_S** — re-run after fix
2. **Verify C_rag-graph/M_S post-completion** — apply 4-step rule
   (check cell wall-clock vs `latency × 100`)
3. **Apply B+C fix before Phase 3** — gemma3:1b and other
   fast-response cells are at high risk
4. **Defer L1/M_S launch** until fix lands

---

## 8. The bigger discipline lesson

For α-6 and future cycles:
- **Always include arithmetic check** as part of the 4-step rule —
  "does cell wall-clock × axis math add up?"
- **Per-tier latency expectation should be pre-recorded** so
  outliers (like 53s for what should be ~170s) trigger immediate
  attention
- **The rate limiter's per-IP semantics** are operator-safe in
  production but adversarial to benchmark loops. The bypass needs
  to be in the matrix runner's env, not a server-side compromise.

---

## 9. References

- Server rate limiter source: `server_llmwiki.py:117`, :442
- Affected cell JSON: `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/qvt-ablation-cell-C_minus-M_S.json`
- Phase 2 task output: `b7z1i104c.output`
- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`
- Discipline log: `reports/research-runs/alpha-5-cycle-pr-index.md` (#655) + `alpha-6-cycle-pr-index.md` (#670)
- Cycle wrong-fix-averted ledger: 8 total across α-5 + α-6 post-closure self-audit
