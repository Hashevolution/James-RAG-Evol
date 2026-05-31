# α-5 Diagnostic Chain — Post-Mortem (2026-05-30~31)

> Narrative of how three landmark "JAMES fails" findings during the
> α-5 cycle turned out to be measurement-side artifacts, not real
> JAMES weaknesses. Recording the chain so future cycles inherit the
> instinct + the rule, not the surprise.

---

## What we measured

The α-5 ablation matrix (`docs/design/v0.4-qvt-alpha-5-ablation-matrix.md`)
is the first JAMES evaluation against an external benchmark
(MultiHop-RAG, Tang & Yang 2024). When the first baseline landed
(`baseline_f7762a3.json`, 2026-05-31 06:38, 100 queries) the headline
read:

| Axis | Baseline 1 (raw) | Initial interpretation |
|---|---|---|
| path_coverage | **0.000** | "JAMES citation completely broken" |
| graded_answer | 0.333 | "JAMES gets ~1/3 of facts" |
| abstention_f1 | 0.316 | "JAMES hallucinates 76% on null queries" |

All three numbers were misleading on the JAMES-side, accurate on the
measurement-side. The cycle eventually pinned the corrected baseline
(`baseline_3a961a3_rescored.json`, the same bench data re-scored
through `eval/qvt/oracle.py` at main `40ae383+`):

| Axis | Baseline 1 (rescored) | Correction |
|---|---|---|
| **path_coverage** | **0.404** | bench was dropping the `sources` field |
| graded_answer | 0.343 | small graded uplift (different bench run) |
| **abstention_f1** | **0.704** | phrase list missed gemma4:e4b's English refusals |

---

## The three corrections, in order

### Correction 1 — path_coverage 0.000 → 0.404 (PR #618)

**Symptom**: `path_recall = 0.000` on all 75 path-annotated queries.
Bench captured `graph_paths` (18-179 nodes/query, mean 60), so the
graph traversal *was* working.

**Wrong first interpretation**: "JAMES surfaces concept entities but
not document entities — fixture is fundamentally incompatible with
JAMES's graph-RAG shape." That framing was about to become a paragraph
in the §7.4 backlog.

**User catch** (the decisive moment):

> "출처 인용에 대한 것도 내가 자메스상 설계해놓은 것으로 기억하는데,
> 만약 이게 안되있으면 문제가 될듯. 보완해야할것같아."

Translation: *"I remember designing source citation on JAMES — if
that's not working, that's a problem. Need to fix."*

This is the moment the chain pivoted. JAMES, by design, returns a
`sources` field separate from `graph_paths` in every `/query/`
response (`core/reasoning/pipeline.py:343`: `[d.get("source",
"unknown") for d in loop_state["docs"][:3]]`).

**Root cause**: `scripts/bench.py:326` read only
`data.get("graph_paths")`. The `sources` field was emitted by JAMES
all along, just discarded by bench.

**Fix scope**: bench captures `sources`, oracle's
`score_path_coverage` scores against *both* `graph_paths` entities
AND `sources` filenames after slug normalisation. `via_graph` and
`via_sources` are tracked separately per query so future analysis can
distinguish concept-traversal wins from citation-layer wins.

**Bucket**: (d) measurement artifact. JAMES code change: 0.

---

### Correction 2 — abstention_f1 0.316 → 0.704 (PRs #619 + #623)

**Symptom**: 19/25 null_query rows classified as
`FN_hallucination` — system answered when truth was `absent`. Reads
as a 76% hallucination rate.

**Wrong first interpretation**: "JAMES's grounding is weak; need
architecture change to add a refusal gate."

**Diagnostic chain** (4-step rule from
`memory/feedback_oracle_phrase_artifacts.md`):

1. Read 5 sample answers from the FN bucket directly.
2. Discover phrases like *"impossible to answer"*, *"cannot be
   determined"*, *"None of the provided internal data relate to…"* —
   semantically refusals, not hallucinations.
3. Cross-check `eval/qvt/oracle.py::_ABSTENTION_PHRASES`: the list
   was Korean-dominant ("정보가 없", "찾을 수 없"…) with a thin
   English tail ("no information", "cannot find"). gemma4:e4b's
   grounding-trained English refusals landed in a blind spot.
4. Confirm: the model is *correctly abstaining* via phrasings the
   detector doesn't recognise.

**Two-stage fix**:

- **#619** added 7 narrow English refusal phrases (`impossible to
  answer`, `cannot be determined`, `insufficient information`, etc.).
  F1: 0.316 → 0.627. FN: 19 → 9.
- **#623** added 3 more after inspecting the remaining FNs (`none of
  the provided`, `cannot be confirmed`, `cannot be identified`).
  F1: 0.627 → 0.704. FN: 9 → 6.

Each round kept phrases narrow on purpose — broader patterns like
*"does not contain"* / *"is not present"* would FP-match
disclaimers in partial-answer-plus-caveat responses ("The company is
Amazon. However, the source material does not contain…"). The
discipline: each phrase must appear only in unhedged refusal
positions in the actual dataset before it joins the list.

**Real hallucination rate after both rounds**: 6/25 = **24%**, not
76%. Of the 6, 1 is a confident wrong answer (*"The first letter of
the Asian country is I."*) — the real signal a routing layer could
plausibly improve.

**Bucket**: (d) measurement artifact (round 1) + (d) again (round 2).
JAMES code change: 0.

---

### Correction 3 — matrix runner respected wrong suite (PR #625)

**Symptom**: T0 smoke restart was 25 minutes into a 117-minute cell,
and the first cell JSON had been written with path_coverage=0.017,
abstention_f1=0.000. The cell JSON also recorded:

  `bench_output: bench_3a961a3_step7_20260531_101025.json`

`_step7_` is the smoking gun. The matrix was supposed to be
measuring `multihop_rag`.

**Wrong first interpretation** (averted): the operator might have
let T0 finish 5.3 hours later, looked at the numbers, and concluded
"JAMES routing layers do nothing" — because step7's Korean wiki
fixture is meaningless against the hotpot_eval workspace's English
news corpus.

**Diagnosis** (the 4-step rule does NOT apply here — this is a wiring
bug, not a measurement-coverage bug):

1. Cell completes too fast → check the bench filename.
2. Filename says `_step7_` → check `_run_single_bench`.
3. Line 352: `"--suite=step7"` hardcoded.
4. `--suite=multihop_rag` plumbed everywhere ELSE (fixture resolver,
   output dir, baseline capture) but missed the per-cell bench
   subprocess.

**Bucket**: (a) architecture. The plumbing got 90% of the way through
when --suite was first added; the per-cell subprocess call was the
10% that was missed.

**Caught by**: a planned stale-cell-JSON cleanup that the operator
triggered as a routine hygiene check while T0 was running. Without
that cleanup, the 5.3-hour T0 would have finished and the wrong
verdict would have been the published result. The cleanup wasn't
*looking* for the bug — but it forced inspection of the cell JSON
file, which surfaced the filename. **Routine hygiene > careful
review** as a bug-catcher.

### Correction 4 — matrix runner bench-output glob still hardcoded step7 (PR #638)

**Symptom**: T0 smoke cell L1/M_M completed cleanly at 12:07; cell
JSON written immediately after; 4-step rule applied as a routine
check on the first cell aggregate. All three quality axes saturated:
path_coverage = 0.0, abstention_f1 = 0.0, graded_answer = 0.0278
(one stale row matched the generic "Based" keyword). Cost axes
plausible-but-low (token=2212, latency=42.68 s) — a mismatch with
the actual 65 s mean visible in the trace files.

  `bench_output: bench_nogit_step7_20260507_194228.json`

`bench_nogit_step7_*` is the smoking gun *again*. The cell JSON
recorded a step7 file from **2026-05-07** (24 days before the run)
even though the matrix subprocess was correctly invoking
`--suite=multihop_rag` and writing
`bench_87ed176_multihop_rag_20260531_120746.json` (the fresh
100-query bench, 6598 s of compute).

**Diagnosis** (4-step rule, applied step by step):

1. axis values — three quality axes at 0/saturated; cost axes
   "almost normal." Suspicious enough to inspect.
2. Read the cell `runs[0].bench_output` — `bench_nogit_step7_*` from
   May 7th, n_queries=12. The actual matrix run was a 100-query
   multihop_rag suite. Smoking gun.
3. Check what `_run_single_bench` does post-bench. Line 380:
   `after = set((ROOT / "reports").glob("bench_*_step7_*.json"))`.
   Hardcoded step7 glob. The pre-existing set on line 355 uses
   `bench_*_{suite}_*.json` (correct), so `after - pre_existing`
   only contained stale step7 files that happened to land between
   line 356 and line 380 — none of which were the fresh multihop
   bench. `new[-1]` then picked the lexicographically last,
   `bench_nogit_*` from May 7.
4. Reconcile design vs matcher: the matrix DOES write the right
   bench file; the runner's score collection just CAN'T SEE IT,
   so it picks an unrelated stale step7 file as the "newly emitted"
   bench output and scores 12 unrelated queries as the cell result.

**Bucket**: (a) architecture. Sibling oversight to #625: that PR
fixed the subprocess CALL but didn't audit the glob used to detect
the subprocess's OUTPUT. The plumbing was 95% the way through;
this was the final 5%.

**Wrong first interpretation** (averted, again): the cell shows
"JAMES L1 baseline gets 0/0/0.028 on 5-axis." Without the 4-step
rule applied to the cell JSON, the operator would have concluded
the baseline cell already shows JAMES can't do MultiHop-RAG at all,
and the remaining 18 cells would be re-interpreted as "tier-and-
layer choices don't matter because the baseline is dead." A
multi-hour debug spiral was avoided.

**The real numbers** (after `scripts/qvt_rescore_ablation_cell.py`
ran on the same cell JSON against the *actual* bench file):

| Axis              | Stale step7 (0/0/0.028) | Real multihop_rag |
|-------------------|-------------------------|-------------------|
| path_coverage     | 0.000                   | **0.419**         |
| graded_answer     | 0.028                   | **0.327**         |
| abstention_f1     | 0.000                   | **0.591**         |
| token_cost        | 2212 chars              | 1224 chars        |
| latency_cost      | 42.68 s                 | 65.99 s           |

Same matrix run, same JAMES code, same cell — completely different
verdict. The numbers above are L1/M_M baseline; the layer-on cells
ought to *improve* on them, not collapse from 0/0/0.028.

**Caught by**: the same 4-step rule the cycle's prior memory entry
codified, applied as part of the planned "look at the first cell
JSON when it lands" hygiene check (i.e. the cycle's own learning
from Correction 3). This is the second wrong-fix averted by the
same discipline within the same cycle.

**Companion tool**: `scripts/qvt_rescore_ablation_cell.py` —
auto-resolves the correct bench file by mtime proximity to the cell
file, rewrites `runs[*].scores` + `aggregate`, writes a side-copy
`.before-rescore.json` for the diagnostic trail. The currently-
running T0 matrix is NOT killed — it continues to produce correct
bench JSONs while the cell aggregates are scored wrong, and post-
hoc rescore at matrix end is cheap (~seconds per cell).

**4-step rule is bucket-(a)-applicable too**. The original memory
entry framed the rule as primarily a bucket-(d) "matcher coverage"
tool. Correction 4 shows the same procedure catches bucket-(a)
plumbing bugs identically — saturated axis → read samples → check
the wiring layer → reconcile design vs matcher. Update the rule
text accordingly.

---

## What stays in the head after this

### 1. The four-step rule (from `feedback_oracle_phrase_artifacts.md`)

When an axis reads as `0` or `saturated` or `wildly off`, **before**
proposing any code change:

1. Read 3-5 raw answer / response samples for that axis.
2. Confirm what the oracle / fixture / bench is actually comparing
   against vs what JAMES emits.
3. Check the JAMES response keys (`routes/query.py::QueryResponse`)
   + the pipeline code (`core/reasoning/pipeline.py`).
4. Only after (d) measurement-side is ruled out, consider buckets
   (a) architecture / (b) model / (c) feature gap.

### 2. Routine hygiene catches non-obvious bugs

The matrix-runner suite bug (#625) was not caught by code review,
not by tests, not by the dry-run. It was caught by a routine cleanup
that forced one cell JSON to be opened. **Plan deliberate hygiene
loops into long-running cycles** — they pay back for themselves the
moment they catch one bug like this.

### 3. The user's domain knowledge is the strongest signal

The pivot moment for path_coverage=0 was a single line from the
user remembering JAMES's citation design. No automated test
caught it; the existing UI didn't surface it. The discipline:
when a system's owner says "wait, that doesn't match the design,"
treat it as the highest-priority signal.

### 4. Each "fix" PR after #618 / #619 / #623 / #625 is bucket-(d) or
   bucket-(a) on the *measurement side*, not the JAMES side. None
   of them rewrote JAMES retrieval, grounding, or routing logic.
   The JAMES code did exactly what it was designed to do all
   along.

---

## What the corrected baseline says (the load-bearing read)

`baseline_3a961a3_rescored.json`, current main, balanced-100 against
MultiHop-RAG:

```
path_coverage:  0.404  (positive — citation layer works)
graded_answer:  0.343  (1/3 of gold facts surface in the answer)
abstention_f1:  0.609  (true F1 after phrase recovery)
token_cost:     1150   chars/query (mean), 2912 (p95)
latency_cost:   64s    /query (mean), 75s (p95)
```

Per-question-type (from `aggregate_by_question_type` in the same
file):

```
comparison:  path=0.45  graded=0.28  ★ best path
inference:   path=0.38  graded=0.52  ★ best graded
temporal:    path=0.39  graded=0.33  longest answers
null:        path=n/a   graded=0.17  abst_f1=0.57 (most queries refuse)
```

This is the actual starting point for the matrix verdict — not the
"76% hallucination + zero path" framing of the first read.

---

## References

- PRs: #616 (initial baseline + first finding), #618 (path
  source-recall), #619 (abstention round 1), #620 (rescore tool +
  §7.4 correction), #621 (4-bucket taxonomy), #622 (render_report
  defensive + bucket retroactive), #623 (abstention round 2),
  #624 (ROADMAP §v0.4.x record), #625 (matrix runner suite bug),
  #626 (analysis template)
- Memory: `feedback_oracle_phrase_artifacts` — 4-step rule + 4-bucket
  taxonomy
- Backlog: `docs/handovers/v0.4.x-backlog-reconciliation-2026-05-30.md`
  §7.3 (cycle reset) + §7.4 (corrections)
- Design: `docs/design/v0.4-qvt-alpha-5-ablation-matrix.md` §3.1
  (Pareto verdict walk-through) + §3.2 (routing policy)
- Findings log: `reports/research-runs/qvt-ablation-findings.md`
  (mandatory bucket tag per #621)
