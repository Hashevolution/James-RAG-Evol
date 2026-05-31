# Don't Build a Layer for the Bug

## A cycle of measurement-side debt in external-benchmark RAG evaluation

> **Draft status**: structure + framing locked; concrete numbers fill
> after the α-5 matrix completes. Target length ~2,500-3,000 words once
> filled. Audience: practitioners building RAG systems who do their own
> evaluation — especially those debating "do we add a layer" vs "do we
> swap a model."
>
> **Authors**: Hashevolution + [potential co-author slots]
> **Companion repo**: PROJECT JAMES, v0.4.x α-5 cycle (2026-05-30~31).
> **Reference cycle**: 22 PRs (#608 ~ #[final]) over ~36 hours, single
> machine.

---

## Section 1 — The opening number

A RAG system runs against an external multi-hop benchmark for the
first time. The baseline result, as reported by the eval harness:

```
path_coverage:  0.000   ← system never cites the right source
graded_answer:  0.333   ← answers contain ~1/3 of expected facts
abstention_f1:  0.316   ← system hallucinates 19 of 25 null queries (76%)
```

The first read says: *the system doesn't know how to cite, and it
hallucinates three-quarters of the time when it should refuse.*

A normal next step is to design new layers: a citation layer to fix
path_coverage, a grounding architecture to fix the hallucination rate.
Maybe swap the model — its grounding training is clearly weak.

This essay is about why none of that would have been the right next
step.

The corrected reality, after 5 PRs of measurement-side fixes:

```
path_coverage:  0.404   ← the citation layer was always there
graded_answer:  0.343   ← unchanged, this was real
abstention_f1:  0.704   ← true hallucination rate is 24%, not 76%
```

**Total JAMES (system-side) code changes**: 0.

The intervening 5 PRs all sat on the *measurement* side — the bench
adapter, the oracle's phrase list, the matrix runner. The system did
what it was designed to do all along. The harness was lying.

The pattern repeated. When the ablation matrix's first cell finished
five hours later, the cell aggregate read 0.000 / 0.028 / 0.000 again.
Same three saturated axes, same first-read panic. The fifth fix (a
sibling oversight in the matrix's score-collection glob) recovered
the cell's real numbers — 0.419 / 0.327 / 0.591 — which were the
expected mid-range readings for the L1 production baseline tier.

| Read              | Cell L1/M_M (before) | Cell L1/M_M (after #638) |
|-------------------|----------------------|--------------------------|
| `path_coverage`   | 0.000                | **0.419**                |
| `graded_answer`   | 0.028                | **0.327**                |
| `abstention_f1`   | 0.000                | **0.591**                |

The discipline isn't just for the opening baseline. Every measurement
the harness produces has to clear the same checks, every time. The
α-5 cycle is the story of treating that as a habit, not a one-off
debugging episode.

---

## Section 2 — Why this happens to everyone

External RAG benchmarks are not neutral measuring sticks. Each
benchmark encodes a particular **semantic contract**:

- *What counts as a "source"?* — paragraph IDs? document titles? URLs?
- *What counts as "abstention"?* — a refusal phrase? an empty answer?
  a low confidence score?
- *What counts as a "grounded claim"?* — keyword overlap? embedding
  similarity? LLM-judge agreement?

A RAG system encodes its own answers to each of these questions in its
data structures (`response.sources` vs `response.graph_paths`), its
text style (the model's natural refusal phrasings), and its
configuration (`source_type=prod` filtering).

The benchmark and the system speak different dialects of the same
question. The eval harness is a translation layer between them — and
translation layers, like systems, accumulate **measurement debt**.

The α-5 cycle is a worked example of paying that debt down without
changing a single line of the underlying system. The pattern
generalises.

---

## Section 3 — The 4-step verification rule

Before any system-side change is proposed in response to a benchmark
result, walk this rule:

> 1. **Read 3-5 raw answer samples** from the suspicious bucket
>    (e.g., the queries flagged as hallucinations). Not the aggregate,
>    not the summary — the actual model output strings.
> 2. **Identify what the oracle / fixture / bench is actually
>    comparing** against. Is the comparison the full text? A keyword?
>    A normalised slug?
> 3. **Cross-check what the system actually emits** in its response.
>    Where does the field the oracle reads come from? Is there a
>    *different* field that contains what the oracle should have been
>    reading?
> 4. **Only after measurement-side is ruled out**, consider system
>    side: architecture, model, feature gap.

This is a discipline, not a debug procedure. It's not "step 4 if all
else fails" — it's "step 4 *because* steps 1-3 came up clean." Most
practitioners reach for system-side hypotheses first; the cycle
described here came close to doing the same on three separate
occasions.

### Why step 1 (read raw samples) is the load-bearing step

In our cycle, the 76% hallucination claim survived two rounds of
aggregate review. The fix arrived when someone read five sample
"hallucinated" answers and noticed they all started with phrases like
*"impossible to determine"*, *"cannot be answered"*, *"None of the
provided internal data relate to..."* — semantically correct
abstentions in a phrasing the abstention-phrase detector didn't
recognise.

There's no way to derive that observation from the aggregate. The
aggregate said *19 hallucinations*. The raw text said *14 of those 19
are honest refusals using phrasing the harness didn't anticipate*.

If you have a benchmark surprise, **stop the meeting and read the
sample answers**. Discipline.

### Why step 3 (check the system's actual fields) catches the deep ones

For the citation case, the harness read `response.graph_paths` (the
graph traversal nodes) but the citation field was
`response.sources` (the top-3 source documents the LLM saw). The
system's design *included* the right field; the harness simply
discarded it.

The pivot moment in our cycle was a single user sentence:

> *"I remember designing source citation on JAMES — if that's not
> working, that's a problem."*

No test caught this. No code review caught this. The UI didn't
surface this. The pivot came from system-author domain knowledge
crossing with a benchmark result. Discipline: **when the system's
owner says "wait, that doesn't match the design," that's the
highest-priority signal in the room.**

---

## Section 4 — A 4-bucket taxonomy for what to do next

After the 4-step rule clears the measurement side, the remaining
hypotheses fall into one of four buckets. The buckets matter because
each requires a *different shape* of follow-up work:

| Bucket | Symptom | Right fix shape | Wrong fix shape |
|---|---|---|---|
| **(a) Architecture** | layer's designed boundary is wrong | redesign / split / merge | swap model (model wasn't the problem) |
| **(b) LLM model** | model capability ceiling | tier change / model swap | rewrite the layer (the layer is fine) |
| **(c) Feature gap** | no layer covers this need | new layer design | tune existing layer (won't go past the ceiling) |
| **(d) Measurement** | oracle / fixture / bench miss | matcher fix (system code change: 0) | add a new layer (the system already does the thing) |

**Diagnosis order**: (d) → (b) → (a) → (c). Reversed, you build layers
to compensate for benchmark blindness.

The α-5 cycle's bug taxonomy by PR:

| PR | Symptom reported | Bucket | What we did | What we'd have done with the wrong bucket |
|---|---|---|---|---|
| #618 | path_coverage = 0.000 | (d) | bench captures `sources` + slug-normalise both sides | (c) "build a citation layer" — but it existed |
| #619 | abstention F1 = 0.316 | (d) | add 7 narrow English refusal phrases | (a) "rewrite grounding pipeline" — model was already refusing |
| #623 | abstention F1 = 0.627 | (d) | add 3 more narrow phrases | (b) "swap to a model with better grounding" — model was fine |
| #625 | matrix verdict near-zero | (a) | un-hardcode `--suite=step7` in cell runner | (b) "small model can't do routing" — actually wrong fixture |
| #638 | cell L1/M_M 0/0/0.028 | (a) | un-hardcode glob `bench_*_step7_*.json` in score collection | (a) "baseline is dead, layer-on cells can't help" |
| later | [FILL: actual α-5 routing verdict] | (a)/(b)/(c)/(d) | [FILL] | [FILL] |

The two (a) bugs (#625 and #638) were both caught by routine inspection,
not testing — and both were sibling oversights of the same `step7`
constant left over from before the multihop_rag suite was added. The
three (d) bugs were caught by reading sample answers and tracing
field names. **Zero of the bugs were caught by aggregate inspection.**
Aggregate values were what triggered the suspicion (the saturated 0
or saturated near-1) but the diagnosis happened by walking the data
backwards from the suspicious number to its source.

---

## Section 5 — The cost of getting the bucket wrong

Each wrong bucket has a characteristic failure mode:

### (c) Wrong fix when the right bucket was (d)

Build a "citation layer" because the harness reports zero citations.
The layer ships, the next benchmark run still reports zero (the
harness still reads the wrong field), so the team concludes "the
citation layer is broken" and iterates on a feature that didn't need
to exist. By the time someone reads sample outputs and notices both
the new layer AND the old data structure cite correctly, six months
of layer work needs to be reverted or quarantined.

### (a) Wrong fix when the right bucket was (d)

Rewrite the grounding architecture because the harness reports 76%
hallucination. The new architecture probably works fine for unrelated
reasons (touching grounding always produces *some* improvement). The
harness still misses 9 of the new refusals (the new architecture
produces phrasings the detector still doesn't know). Team concludes
"grounding is hard" and continues iterating. The original
architecture was never the bottleneck.

### (b) Wrong fix when the right bucket was (a)

Conclude the model can't handle multi-hop routing because the matrix
cells all show null verdicts. Spend two weeks evaluating larger
models. Discover that the matrix runner was measuring against the
wrong fixture — the larger models would have read as null too on the
wrong fixture, but they'd be expensive null instead of cheap null.
Restart the cycle with the right fixture and the smaller model
suddenly works.

These are all real failure modes for teams under deadline pressure.
The discipline is to **make the buckets explicit BEFORE proposing the
fix**.

---

## Section 5.5 — The fourth case, caught mid-write

[Added 2026-05-31 PM during T0 smoke completion.]

The cycle made four wrong-fix-averted corrections, not three. The
fourth landed as PR #638 when the first T0 cell JSON wrote at 12:07
and the 4-step rule was applied to it as routine hygiene (per
discipline 7.3 below).

The cell aggregate reported `path_coverage=0.000`, `abstention_f1=0.000`,
and `graded_answer=0.028` on a 100-query MultiHop-RAG cell. Three
saturated quality axes on a JAMES baseline that already showed
graded ≈ 0.33 + path ≈ 0.40 on the corrected baseline JSON. The
saturation was too clean.

Step 1: axis values triggered the rule. Step 2: read the cell JSON's
`runs[0].bench_output` field — it pointed at
`bench_nogit_step7_20260507_194228.json`, a 24-day-old step7 file
from a completely different fixture. Step 3: trace the matrix runner.
The bench subprocess was correctly running `--suite=multihop_rag` (the
#625 fix from earlier in the cycle), writing a fresh 100-query bench
to `bench_87ed176_multihop_rag_20260531_120746.json`. But the runner's
post-bench detection glob (`bench_*_step7_*.json`, line 380) still
scanned the legacy suite and never saw the fresh file. `new[-1]`
returned the lexicographically last stale step7 file. Step 4:
reconcile design vs matcher — the matrix is producing the right
measurement, but the score-collection wiring sees the wrong file.

Bucket-(a) architecture. Sibling oversight to #625: that PR fixed the
subprocess CALL but didn't audit the glob used to detect the
subprocess's OUTPUT. The plumbing was 95% the way through; this was
the final 5%.

Real numbers after `scripts/qvt_rescore_ablation_cell.py` swapped in
the actual bench file:

| Axis              | Stale step7 (0/0/0.028) | Real multihop_rag |
|-------------------|-------------------------|-------------------|
| path_coverage     | 0.000                   | **0.419**         |
| graded_answer     | 0.028                   | **0.327**         |
| abstention_f1     | 0.000                   | **0.591**         |

Same cell, same matrix run, same JAMES code — completely different
verdict. If the operator had taken the saturated read as truth, the
entire matrix would have been re-interpreted as "JAMES baseline is
already 0; layer-on cells can't help what's dead." A multi-hour
debug spiral was averted by ~5 minutes of 4-step-rule application
to the first cell JSON the matrix wrote.

The wider lesson: **the 4-step rule is bucket-(a) applicable too**.
The original `feedback_oracle_phrase_artifacts` memory framed the
rule as primarily a bucket-(d) "matcher coverage" tool. Case 4
shows the same procedure catches bucket-(a) plumbing bugs
identically — saturated axis → read samples → check the wiring
layer → reconcile design vs matcher. The rule generalises from
"oracle phrase coverage" to "any measurement-side wiring."

This is the second wrong-fix averted by the same discipline within
the same cycle. The cycle's contribution is the rule's
*generalisation* across both buckets, not just the per-case fixes.

---

## Section 6 — The cycle as evidence

[FILL: this is the section that depends on the actual α-5 matrix
verdict. Pattern:

If the matrix shows routing layers help —

> "After the 5 measurement-side PRs landed, the corrected matrix
> showed [routing layer X] moves the [axis] by [Δ] on [tier]. That
> verdict is the routing-policy evidence the cycle was designed to
> produce. It survives publication review because the measurement-
> side artifacts are out of the way."

If the matrix shows routing layers null —

> "After the 5 measurement-side PRs landed, the corrected matrix
> showed [no routing layer moves any axis past noise] / [some axes
> move but cost regresses]. That's bucket-(d) on the routing-layer
> ROI question — measurement artifacts are out, the layers are
> genuinely inert at production tier. The deprecation track follows
> from honest measurement."

Either branch is a publishable result because the *measurement
discipline* is the contribution. The numbers happen to support
[whichever verdict]. Past benchmarks showing JAMES "fails" without
this discipline would have been wrong in either direction.]

---

## Section 7 — Operationalising the discipline

Three habits the cycle landed:

### 7.1 Mandatory bucket tag on every finding

Every entry in the findings log
(`reports/research-runs/qvt-ablation-findings.md`) carries a
`bucket: (a)/(b)/(c)/(d)` field. Adding the field forces the writer
to commit to a hypothesis before recommending a fix. The two found
artifacts of this cycle (path=0, abst=0.316) were both tagged (d)
*before* the fix — the tagging IS the discipline.

### 7.2 `fix` PR exemption from the Quality Delta Card

Quality Delta Cards (PR-gate pattern from CLAUDE.md rule 2) compare
the change against a baseline measurement. When the change *is* the
measurement fix, the comparison is circular — you'd measure against
the broken oracle.

The `fix` label exemption (added to CLAUDE.md rule 2 during this
cycle) gives the reviewer one line — `Quality delta: exempt (label:
fix)` — to mark the PR as a measurement-side correction without
generating noise. The discipline: the exemption requires the bucket
tag in the PR description. You can't claim `fix` without claiming
bucket (d) or (a) measurement-side.

### 7.3 Routine hygiene loops in long-running runs

The matrix-runner bug (#625) was caught by a planned stale-cell
cleanup, not by tests, not by code review, not by dry-run. Hygiene
loops are intentionally low-stakes — clear stale files, rebuild
indices, eyeball one or two output samples — but they force
inspection of artifacts that would otherwise sit unread for hours.

In long-running cycles (the α-5 ablation matrix runs ~5 hours per
tier; the full N=3 across all tiers is ~30 hours), schedule at least
one hygiene loop per 4-hour block. It pays for itself the moment it
catches one bug like ours.

---

## Section 8 — Generalisation beyond this cycle

The pattern is not specific to JAMES, not specific to MultiHop-RAG,
not specific to graph-RAG. The same dynamics arise whenever:

- A new external benchmark gets pointed at an existing system
- A new model release is evaluated against an existing eval harness
- A new fixture / dataset is added to a regression suite
- A team changes the answer format / response schema and the eval
  harness wasn't updated synchronously

Each of these is a translation-layer event. The translation can have
bugs the same way systems can. The 4-step rule + 4-bucket taxonomy
gives the team a way to debate the right intervention without falling
into "obvious" architectural fixes that don't address the actual
problem.

The α-5 cycle was a 36-hour single-machine effort. Its PRs are a
public worked example a team facing the same translation-debt problem
can pattern-match against.

---

## Section 9 — What this is not

This essay is **not** an argument that measurement should always be
the first suspect.

- Real architectural bugs exist. Real model ceilings exist. Real
  feature gaps exist.
- The 4-step rule is a 5-minute exercise, not a 5-week one. If the
  raw samples confirm the harness is right, move to (b)/(a)/(c)
  immediately. Discipline does not mean delay.
- The bucket framework is a heuristic for *categorising hypotheses*,
  not a verdict mechanism. Two reviewers can disagree on bucket and
  still resolve via the underlying data.

The argument is narrow: **when surprise results come in from a
benchmark, the cheapest, fastest, most-frequently-overlooked
hypothesis is that the benchmark and the system are speaking
different dialects.** The cycle described here is one team's
demonstration that paying attention to that hypothesis first turns
an apparent disaster into a 22-PR, 36-hour, 0-system-code-change
correction.

---

## References

- PROJECT JAMES, v0.4.x α-5 cycle: PRs #608 through #[final]
  (2026-05-30 to 2026-05-31)
- Findings log: `reports/research-runs/qvt-ablation-findings.md` —
  every entry carries a bucket tag
- 4-step verification rule + 4-bucket taxonomy:
  `memory/feedback_oracle_phrase_artifacts.md`
- Diagnostic chain post-mortem:
  `reports/research-runs/alpha-5-diagnostic-chain-post-mortem.md`
- Cycle summary: `reports/research-runs/alpha-5-cycle-summary-DRAFT.md`
- External benchmark: Tang & Yang. "MultiHop-RAG: Benchmarking
  Retrieval-Augmented Generation for Multi-Hop Queries." EMNLP 2024.
  HuggingFace `yixuantt/MultiHopRAG`.

---

## Notes for joint piece negotiation

- This draft assumes Hashevolution as primary author. If joint with
  Robin Converse / Ali Afana / Vadym from prior collaboration, each
  co-author's contribution surfaces in §1 (results), §2 (whose
  benchmark / model), §6 (cycle as evidence).
- Acceptable formats: arXiv preprint, blog post, conference workshop
  paper.
- Acceptable submission timing: after the v0.4-end α-5 closure PR
  lands AND a 1-week reflection window. The submission should not be
  rushed off the same week the cycle finishes.
- Avoid: framing as "JAMES superior to peers" — the cycle is a
  measurement-discipline story, not a system-comparison story. The
  matrix numbers happen to support whichever verdict; the *discipline*
  is what's transferable.
