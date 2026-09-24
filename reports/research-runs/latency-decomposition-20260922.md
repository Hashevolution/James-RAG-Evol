# Query latency decomposition — where 146 seconds go (2026-09-22)

> **Source**: `james_audit.db`, the QVT 5-axis baseline capture window
> `2026-09-22T09:43` .. `11:58` (`baseline_6deca66.json`, `gemma4:e4b`
> pinned, 3 runs, **0/54 generation failures**). Clean data: the run this
> is measured on is the one that succeeded.
>
> **Reproduce**: `python scripts/research/latency_decomposition.py
> --since 2026-09-22T09:43 --until 2026-09-22T11:58`
>
> **Method + its two judgment calls** are in that script's docstring and
> pinned by `tests/test_latency_decomposition.py` (11 tests).

> ## ⚠️ Erratum (2026-09-24)
>
> **The magnitudes in this report are one day's host state, not a
> property of the code.** Re-measured at the *same* 10 s budget on
> 2026-09-24 (arm A of `query-rewrite-budget-paired-20260924.md`):
>
> | | this report (09-22) | 09-24 |
> |---|---:|---:|
> | rewriter failed | 83.3% | **15.4%** |
> | timeout share of wall clock | 32.0% | **6.3%** |
> | `reason:synth` mean | 33.8 s | **14.2 s** |
>
> `synth` has no timeout interaction and no code change touched it, so
> its 2.4x speed-up isolates the host: the machine was materially slower
> on 09-22, for a reason nothing recorded and that cannot now be
> recovered. The **method and the shape** of the findings stand —
> retrieval is a small share, timeouts are a large one, and every
> observed timeout maps to a declared budget. The **headline numbers**
> should be read as that day's state.
>
> §5's "raise the budget -> recovers ~11 s/query" was also imprecise,
> and so was the correction offered afterwards. The paired run measures
> the knob at ~4.7 s/query on 09-24's host; see that report §3–§4.

## 1. Headline

**Retrieval is 1% of the wall clock. 32% is spent on LLM calls that
produced nothing.**

That reframes the latency problem. This system is not slow because
search is slow — search and rerank together cost **1.4 s** of a 145.7 s
query. It is slow because of LLM orchestration, and a third of that
orchestration is failed calls being paid for at full price.

## 2. Per-query budget

Window `2026-09-22T09:43` .. `2026-09-22T11:58` — **54 answerable queries**, wall mean **145.7 s**.

**Timeout share: 32.0%** of wall clock (46.6 s/query, n=131); observed gap budgets [5, 7, 10, 12, 20, 22, 30, 32, 45] s.

Floor if no call ever timed out: **99.0 s/query**.

| stage | n | total s | % | s/query | mean s |
|---|---:|---:|---:|---:|---:|
| `system:WARN:gemma.timeout` | 131 | 2517.7 | 32.0% | 46.6 | 19.2 |
| `reason:synth` | 54 | 1823.5 | 23.2% | 33.8 | 33.8 |
| `reason:reflect` | 82 | 1293.7 | 16.4% | 24.0 | 15.8 |
| `reason:route` | 242 | 984.8 | 12.5% | 18.2 | 4.1 |
| `reason:verify` | 159 | 576.3 | 7.3% | 10.7 | 3.6 |
| `reason:plan` | 27 | 377.1 | 4.8% | 7.0 | 14.0 |
| `reason:retry` | 8 | 203.1 | 2.6% | 3.8 | 25.4 |
| `reason:retrieve` | 78 | 53.2 | 0.7% | 1.0 | 0.7 |
| `reason:rerank` | 54 | 23.7 | 0.3% | 0.4 | 0.4 |
| `system:INFO:orchestrator.retrieve_done` | 54 | 6.1 | 0.1% | 0.1 | 0.1 |
| `system:INFO:llm_router.route` | 335 | 5.3 | 0.1% | 0.1 | 0.0 |
| `/query/` | 54 | 0.6 | 0.0% | 0.0 | 0.0 |
| `system:INFO:memory_loom.gate4_dedup` | 27 | 0.3 | 0.0% | 0.0 | 0.0 |
| `system:WARN:memory_loom.gate1_fail` | 16 | 0.2 | 0.0% | 0.0 | 0.0 |
| `system:INFO:memory_loom.store_ok` | 3 | 0.0 | 0.0% | 0.0 | 0.0 |

| stage | logged after a timeout | share |
|---|---:|---:|
| `reason:route` | 13/242 | 5.4% |
| `reason:verify` | 25/159 | 15.7% |
| `reason:reflect` | 23/82 | 28.0% |
| `reason:retrieve` | 65/78 | 83.3% |
| `reason:rerank` | 0/54 | 0.0% |
| `reason:synth` | 0/54 | 0.0% |
| `reason:plan` | 5/27 | 18.5% |
| `reason:retry` | 0/8 | 0.0% |

## 3. Three findings

### 3.1 The query rewriter fails 83% of the time

`reason:retrieve` is logged immediately after a timeout in **65 of 78**
cases. The timeout gaps preceding it are **5, 7, 10, 12 s** — matching
`core/retrieval/query_rewriter.py:48`, `DEFAULT_TIMEOUT_S = 10.0`.

The budget is 10 s; the model does not finish in 10 s. So the rewriter
burns ~11 s/query and **the feature is effectively off** — it completes
on roughly 1 query in 6.

🔴 This matters beyond latency. `baseline_6deca66.json` records
`JAMES_ENABLE_QUERY_REWRITE: '1'` as part of the pinned environment. The
flag is on; the feature is not running. That is the third instance this
week of *the environment declaring one thing and the system doing
another* — after the model pin (#1142) and AUTO_ROUTER evidence (#1136).

### 3.1b Every observed timeout value maps to a declared budget

Independent confirmation that the decomposition reads real budget
exhaustion rather than noise — the gap values the audit log shows line
up with the constants in the source:

| component | declared budget | observed gaps |
|---|---:|---|
| `core/retrieval/query_rewriter.py::DEFAULT_TIMEOUT_S` | 10.0 s | 10, 12 |
| `core/reasoning/planner.py::DEFAULT_TIMEOUT_S` | 20.0 s | 20, 22 |
| `core/reasoning/verify.py::DEFAULT_FACT_CHECK_TIMEOUT_S` | 30.0 s | 30, 32 |
| `core/reasoning/reflect/prompts.py::DEFAULT_CRITIQUE_TIMEOUT_S` | 30.0 s | 30, 32 |
| `core/reasoning/reflect/prompts.py::DEFAULT_REVISE_TIMEOUT_S` | 45.0 s | **45** |

Observed set: `[5, 7, 10, 12, 20, 22, 30, 32, 45]`. The 5 and 7 are
shorter than any declared budget — plausibly a retry arriving with a
reduced remaining allowance — and are not attributed here.

This also settles the attribution in §3.1: the 10/12 cluster sitting
immediately before `reason:retrieve` is the rewriter's 10 s budget, not
some other component that happens to fail there.

### 3.2 `synth` is healthy; everything around it is not

| stage | timed out | mean |
|---|---:|---:|
| `reason:synth` | **0%** | 33.8 s |
| `reason:rerank` | 0% | 0.4 s |
| `reason:route` | 5.4% | 4.1 s |
| `reason:verify` | 15.7% | 3.6 s |
| `reason:plan` | 18.5% | 14.0 s |
| `reason:reflect` | 28.0% | 15.8 s |
| `reason:retrieve` | **83.3%** | 0.7 s |

The stage that produces the answer never times out. The cognitive
stages around it (`plan` / `reflect` / `verify`) fail 16–28% of the
time, which means they are frequently paying their full budget and
contributing nothing to the answer.

### 3.3 Fixing timeouts is necessary but not sufficient

| | s/query |
|---|---:|
| current | 145.7 |
| if no call ever timed out | **99.0** |
| the 3 queries that had zero timeouts | 118.3 |

Removing every timeout lands at ~99 s. Conversational latency needs the
**number of LLM calls** to come down too: the current shape is ~4.5
`route` + ~2.9 `verify` + ~1.5 `reflect` + 1 `synth` + 0.5 `plan` per
query.

## 4. What this does not say

- **Not a claim about model quality.** Nothing here measures answers;
  it measures where time goes. The capture it draws on had 0 generation
  failures, so these are the timings of a *working* run.
- **Not generalisable off this host.** Budgets that fit a faster machine
  would not time out. The finding is that *on the hardware the baseline
  was captured on*, the budgets are mis-set — which is exactly the
  hardware the baseline now speaks for.
- **Not a verdict on the cognitive stages.** That they time out often is
  measured; whether the answer is worse without them is not. That is a
  paired measurement against `baseline_6deca66.json`, not an inference.

## 5. Ordered next steps

1. **Raise or retire the query-rewrite budget** (`DEFAULT_TIMEOUT_S`
   10 s). Recovers ~11 s/query *and* makes a flagged-on feature real.
   Touches `core/retrieval` → rule #2 Quality Delta Card required.
2. **Re-budget `reflect` / `verify` / `plan`** — ~35 s/query between them.
3. **Measure `JAMES_DISABLE_COGNITIVE_STAGES=1` against the baseline.**
   These stages cost ~46 s/query and often produce nothing; whether the
   answer degrades is now answerable, because the 5-axis reference
   exists.
