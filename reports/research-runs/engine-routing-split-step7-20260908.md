# STEP 7 bench — engine_routing.py split (rule #2 gate for PR #1083)

**Date**: 2026-09-08
**Change under test**: `core/reasoning/engine.py` mode/model routing block
lifted to `core/reasoning/engine_routing.py` (rule #5 split-debt from #1080)
**Arms**: `3fafd8f` (main) vs `549ffd1` (branch)
**Harness**: `python scripts/bench.py --suite=step7 --mode=retrieval`,
20 queries, RAG path confirmed (auto-minted admin bearer, `graph_paths > 0`)

## 1. Why three runs, not two

The first A/B pair showed the branch **+323.2s (+20.3%)** slower. A verbatim
code move cannot cost 20% on a path whose queries each spend 60–200s in a
local LLM, and the repo's own variance study
(`step7-bench-variance-analysis-2026-05-29.md` §3) puts same-code 3-run CV at
**3.4%** — so the result was either a real regression or the A arm was an
outlier. A second run of **main** (A2) settles it.

## 2. Results

| run | sha | total | path recall |
|---|---|---:|---|
| A1 main | `3fafd8f` | 1594.6s | 0.818 (9/11) |
| A2 main | `3fafd8f` | 1818.9s | 0.833 (10/12) |
| B branch | `549ffd1` | 1917.8s | 0.833 (10/12) |

| comparison | Δ total | median per-query \|Δ\| | queries slower |
|---|---:|---:|---:|
| **A2 − A1** (identical code) | **+224.3s (+14.1%)** | **14.9s** | 15/20 |
| **B − A2** (the change) | **+98.9s (+5.4%)** | **7.6s** | 13/20 |

**The change's delta is smaller than the same-code delta on both measures.**
A1 was the outlier: it was the first run of the session, its q1 hit the 120s
timeout cap, and the spillover put q2 at 210.1s — the largest single value
anywhere in the three runs (q2 came in at 111.6s and 146.1s afterwards).

- **Path recall**: A2 and B are **identical** (0.833, 10/12). A1's 0.818 (9/11)
  differs only because the timed-out q1 was not scored — the denominator, not
  the retrieval.
- **Status flips**: q1 only, `timeout → ok → ok`. §3 of the variance study
  already classifies 120s-cap flips as boundary noise, not regression.
- **Blocked queries** (q11, q12 security): 0.0s in all three runs.

## 3. Structural verification (stronger than the timing)

The timing evidence is statistical; the change itself is provable. Of the
**100 lines removed** from `engine.py`:

- **98 reappear character-for-character** in `engine_routing.py` (indentation
  aside — a method body became a function body)
- **2 are the mechanical `self.` → `engine.` rename** required by the
  parameter: `self._log("query_router", …)` and
  `self._last_routed_model = _eff_model or ""`

`engine.py` gains 13 lines: a comment and the delegation call. No behavioural
edit exists to measure.

## 4. Axes not measured

Graded Answer, Abstention F1 and Token Cost need the QVT oracle applied to
answer text, which `scripts/bench.py` does not retain. Capturing them means
`qvt_capture_baseline.py` on both arms (~70 min each), and the only baseline
on disk is `eval/qvt/baseline_2a31b20.json` from 2026-05 — four months of
intervening change would be attributed to this PR. Recorded as a known gap
rather than papered over with a stale reference.

## 5. Verdict

**Bench-neutral.** The measured delta sits inside the same-code noise band,
path recall is identical against the comparable run, and the code is a proven
verbatim move. No evidence of regression on the axes this harness reports.
