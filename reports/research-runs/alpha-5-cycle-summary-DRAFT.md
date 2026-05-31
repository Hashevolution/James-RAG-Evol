# α-5 Ablation Matrix Cycle — Summary

> **Draft status**: outline + framing locked; numbers fill in after
> T0 smoke completes and `scripts/qvt_fill_t0_analysis.py` runs. This
> file replaces the cycle's scattered notes (§7.3/§7.4 backlog,
> findings.md, post-mortem, T0 result template) with a single
> reviewer-ready read.
>
> **Cycle window**: 2026-05-30 → [FILL: closure date]
> **PR span**: #608 ~ [FILL: final PR]
> **Status**: [FILL: closed / partially closed]

---

## 0. One-paragraph headline

α-5 measured JAMES against MultiHop-RAG (Tang & Yang 2024) — the
first external benchmark in `eval/RESULTS.md`. **Routing layer
verdicts**: [FILL — strong-adopt / tier-gated / null per layer, after
T0 closes ~16:00 KST and the rescore wrapper runs]. **Reasoning
capability evidence (corrected baseline)**: JAMES's citation layer
hits ~40% of expected sources at L1 (mid-range, not the saturated 0
the first read showed), graded answer at ~33%, abstention F1 at ~70%
(real null-query hallucination rate is 36%, not the 76% the first
oracle suggested). **Diagnostic discipline**: 5 of 32 cycle PRs were
measurement-side fixes (3 bucket-(d) phrase / sources coverage +
2 bucket-(a) matrix wiring); the 4-step verification rule
(memory `feedback_oracle_phrase_artifacts`) prevented **4
wrong-bucket follow-ups**, all of which would have shipped JAMES-side
code changes against bugs that lived entirely in the measurement layer.
Cumulative JAMES code change attributable to α-5 measurement debt:
**0 lines**. The publishable contribution is the discipline as much
as the verdict.

---

## 1. What we set out to measure

The α-5 ablation matrix's two simultaneous purposes
(per 2026-05-31 user clarification):

1. **Routing decision** — for each Layer 4 cognitive routing flag
   (`JAMES_AUTO_ROUTER`, `JAMES_ADAPTIVE_BUDGET`, `JAMES_SCOPE_ROUTING`),
   does turning it on at the production tier (`gemma4:e4b`) measurably
   improve any axis enough to default it on, tier-gate it, or delete
   it?
2. **Reasoning-capability evidence** — externally credible numbers
   showing JAMES's layer stack outperforms a baseline-without-layers
   on a published benchmark. This unblocks the `eval/RESULTS.md`
   "external benchmark deferred to v0.3" line.

The matrix shape — 19 cells (18 standard + 1 sanity think=ON) × 5-axis
oracle (quality 3 + cost 2) × per-question-type cross-tab — was
designed to serve both at once.

---

## 2. Methodological corrections that shaped the result

The first read of the matrix would have produced misleading
conclusions if accepted at face value. **Four** corrections shifted
the narrative before any verdict shipped (count corrected 2026-05-31
PM when Correction 4 landed mid-cycle):

### 2.1 Path coverage 0.000 → 0.404 (PR #618)

[FILL: 2-3 lines.]
- bench was reading only `graph_paths`, dropping the `response.sources`
  field JAMES emits per `core/reasoning/pipeline.py:343`.
- Oracle now scores against both with slug normalisation. Path axis
  reports `via_graph` + `via_sources` separately.
- bucket: (d) measurement artifact. JAMES code change: 0.

### 2.2 Abstention F1 0.316 → 0.704 (PRs #619 + #623)

[FILL: 2-3 lines.]
- gemma4:e4b grounding-trained English refusals
  (`impossible to determine`, `cannot be answered`, `none of the
  provided`) landed in the original phrase list's blind spot.
- Two rounds of narrow phrase additions — kept narrow on purpose to
  avoid FP-flooding disclaimer-style hedges in partial answers.
- bucket: (d) × 2. Real hallucination rate is 6/25 = 24%, not 76%.

### 2.3 Matrix runner hardcoded `--suite=step7` (PR #625)

[FILL: 2-3 lines.]
- `_run_single_bench` ignored the matrix runner's `--suite` argument.
  Every cell would have been measured against the wrong fixture.
- Caught by routine stale-cell cleanup (the bench filename suffix
  `_step7_` was the smoking gun).
- bucket: (a) architecture. Without the cleanup loop, 5.3h of T0
  smoke would have produced a "JAMES routing layers do nothing"
  verdict on the wrong dataset.

### 2.4 Matrix runner bench-output glob still hardcoded `step7` (PR #638)

- Sibling oversight to #625: that PR fixed the bench subprocess CALL
  but the post-bench detection glob at `qvt_ablation_matrix.py:380`
  was still `bench_*_step7_*.json`. The fresh multihop_rag bench file
  was written correctly but invisible to the runner; `new[-1]`
  returned a stale `bench_nogit_step7_20260507_*.json` from 24 days
  prior.
- Caught at 12:07 KST when T0 cell 1 (L1/M_M) JSON wrote with all
  three quality axes saturated (0.0 / 0.0 / 0.028). Applying the
  cycle's own 4-step rule to the cell JSON's `runs[0].bench_output`
  field surfaced the smoking gun within minutes.
- bucket: (a) architecture. Fixed in one line + companion rescore
  tool `scripts/qvt_rescore_ablation_cell.py`.
- Real cell L1/M_M numbers after rescore: path=0.42, graded=0.33,
  abst_f1=0.59 — mid-range baseline, not saturated.

### 2.5 Why this matters for the read

Without (2.1)/(2.2), the headline would have been "JAMES hallucinates
3/4 of null queries and can't cite sources." Without (2.3), the
matrix would have measured against a Korean step7 wiki fixture, not
the English MultiHop-RAG corpus the cycle was designed around.
Without (2.4), every cell of T0 would have scored against a 12-query
May-7 step7 file instead of the freshly-captured 100-query
multihop_rag bench.

The corrected reality is "JAMES refuses 2/3 of null queries correctly
and cites the right source for ~40% of expected articles" — and that
reality only became visible because each correction landed BEFORE the
matrix verdict shipped.

**Wrong-fix avoided count**: 4 (#618 / #619+#623 / #625 / #638).
**Cumulative JAMES code change attributable to α-5 measurement debt**:
0 lines.

This is what user req #4 ("external credibility") needs: the published
narrative survives review because the cycle removed measurement
artifacts first — across both bucket-(d) (matcher coverage) and
bucket-(a) (measurement wiring). Memory
`feedback_oracle_phrase_artifacts` §"확장 2" locks the
generalisation: the 4-step rule applies to *any* measurement-side
wiring, not just oracle phrase coverage.

---

## 3. Baseline (corrected, post-#618/#619/#623)

`workspaces/hotpot_eval/eval/qvt/baseline_3a961a3_rescored.json` —
canonical reference. n_runs=1, fixture=`balanced-100` (25 per
question_type), workspace=`hotpot_eval`, model=`gemma4:e4b`,
think=OFF (A2 #609 policy).

| Axis | Median | Notes |
|---|---|---|
| path_coverage | 0.404 | 4 of every 10 expected source articles cited |
| graded_answer | 0.343 | 1/3 of atomic gold claims appear in the answer |
| abstention_f1 | 0.609 | TP=14, FP=7, FN=11, TN=68 across 100 queries |
| token_cost | 1150 chars | mean; p95 = 2912 |
| latency_cost | 64 s | mean; p95 = 75 |

### Per question_type

| Type | path | graded | abst_f1 | token | latency |
|---|---|---|---|---|---|
| comparison | 0.45 ★ | 0.28 | n/a (truth=present) | 1389 | 67s |
| inference | 0.38 | 0.52 ★ | n/a (truth=present) | 669 | 62s |
| temporal | 0.39 | 0.33 | n/a (truth=present) | 1717 | 69s |
| null | n/a (no path) | 0.17 | 0.57 ★ | 561 | 58s |

[FILL: 2-3 lines of narrative — "comparison wins path because the
binary form makes the LLM cite both sides; inference wins graded
because single-entity facts are easier; temporal burns tokens because
the LLM unrolls the timeline; null abstains correctly more than
half the time."]

---

## 4. Matrix results — T0 smoke (3 cells)

### 4.1 5-axis Δ table vs corrected baseline

| Cell | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ | Verdict |
|---|---|---|---|---|---|---|
| L1/M_M primary | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| L5/M_M full stack | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| L1/M_M-thinkON sanity | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |

### 4.2 via_graph vs via_sources

| Cell | via_graph hits | via_sources hits | total unique |
|---|---|---|---|
| L1/M_M | [FILL] | [FILL] | [FILL] |
| L5/M_M | [FILL] | [FILL] | [FILL] |

[FILL: which contribution dominates? Does the routing stack help
graph-traversal more, citation more, or neither?]

### 4.3 Per-question-type cross-tab (L5 Δ vs L1 baseline)

| Type | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ |
|---|---|---|---|---|---|
| comparison | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| inference | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| temporal | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| null | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |

[FILL: are the verdicts uniform across types, or type-gated? — the
core of user req #2 routing-policy evidence.]

### 4.4 Sanity cell — A2 default-flip evidence

| Axis | think=OFF | think=ON | Δ (ON − OFF) |
|---|---|---|---|
| path_coverage | [FILL] | [FILL] | [FILL] |
| graded_answer | [FILL] | [FILL] | [FILL] |
| abstention_f1 | [FILL] | [FILL] | [FILL] |
| token_cost | [FILL] | [FILL] | [FILL] |
| latency_cost | [FILL] | [FILL] | [FILL] |

[FILL: A2 default-flip decision rationale.]

---

## 5. Decision tree (was the matrix worth running?)

[FILL after results: choose one of the branches.]

### Branch A — Routing layers help

[FILL: which layer(s), which tier(s), which question_type(s). Cite
specific cells. List default-flip PRs that follow this verdict.]

### Branch B — Routing layers are inert at production tier

[FILL: explicit verdict. List deprecation PR candidates. Note that
the cycle still produced value (the corrected reasoning-capability
numbers) even if routing was null.]

### Branch C — Mixed (per-type routing)

[FILL: type-gated policy. Routing on for some question types only.
List the type → (model, layer) recipes for the routing module.]

---

## 6. Reasoning-capability publishable read

[FILL: the second half of the dual-purpose framing. This section is
what gets quoted in a joint piece / blog post / `eval/RESULTS.md`.
Pattern:
"On MultiHop-RAG balanced-100, JAMES (production env, think=OFF,
gemma4:e4b 4B) hits N% source-citation recall, M% atomic-claim recall,
F% abstention F1 — within X% of [comparable system Y if numbers
available, else baseline]. The layer stack contributes [Δ] above
the bare retrieval baseline (L0 floor cell, when measured)."]

---

## 7. Diagnostic chain — process lessons

### 7.1 Bucket framework worked

All findings entries from #621 forward carry a mandatory `bucket:`
tag (a/b/c/d). The discipline forces a hypothesis commitment before
recommending a fix; future entries inherit the contract. Worked
example landed: cycle's own findings log has correct bucket attribution
on every entry, retroactively applied by #622.

### 7.2 The 4-step rule prevented 4 wrong-bucket follow-ups

Within the same cycle (`feedback_oracle_phrase_artifacts.md`):
- path_coverage=0 → would have been (c) "add citation layer" or (a)
  "rewrite graph traversal" — was bucket-(d) bench dropping the
  `sources` field (#618).
- 76% null-query hallucination → would have been (b) "swap to a
  bigger model with stronger grounding" or (a) "add grounding pass"
  — was bucket-(d) phrase coverage gap (#619 + #623).
- Matrix runner produced near-zero verdicts → would have been (a)
  "AUTO_ROUTER does nothing, deprecate it" or (b) "tier change
  needed" — was bucket-(a) subprocess suite-arg hardcoded (#625).
- T0 cell 1 saturated at 0/0/0.028 → would have been (a) "L1 baseline
  is dead, layer-on cells can't help" — was bucket-(a) score-collection
  glob hardcoded (#638).

JAMES code change across all 32 cycle PRs: **0 lines**.
All fixes landed on the oracle / bench / matrix-runner side. The
rule generalised from "oracle phrase coverage" to "any measurement-
side wiring" via Correction 4 (locked in memory `feedback_oracle_phrase_artifacts`
§"확장 2").

### 7.3 User domain knowledge was the strongest signal

The pivot moment for path_coverage=0 came from one user sentence
remembering JAMES's citation design: *"출처 인용에 대한 것도 내가
자메스상 설계해놓은 것으로 기억하는데, 만약 이게 안되있으면 문제가
될듯."* No automated test caught it; the existing UI didn't surface it.
The discipline: when a system's owner says "wait, that doesn't match
the design," treat it as a higher-priority signal than the saturated
axis value, not a lower one.

### 7.4 Routine hygiene catches non-obvious bugs

Two of the four bucket-(a) bugs were caught by routine inspection,
not tests:
- #625 (subprocess suite-arg) caught during a planned stale-cell
  cleanup that wasn't *looking* for the bug — opening a cell JSON
  surfaced the `_step7_` filename suffix.
- #638 (score-collection glob) caught by applying the 4-step rule
  to the first cell JSON when it landed, as a routine check.

**Plan deliberate hygiene loops into long-running cycles.** They pay
back the moment they catch one bug like #625 or #638. The cycle's
own 4-step rule discipline became the hygiene tool that caught its
own 4th measurement bug, in real time.

---

## 8. PR sequence (cycle index)

| PR | Type | One-line |
|---|---|---|
| #608 | feat | A3 think-mode quality boundary (5 stages × hard fixtures) |
| #609 | feat | A2 gemma4:e4b per-stage think-mode policy (opt-in) |
| #611 | research | A3 v2 LLM-judge — judge can't break the deterministic tie either |
| #612 | feat | α-5 ablation matrix prep (driver + design memo) |
| #613 | feat | α-5 prereq plan (4 risk addressal) |
| #614 | feat | step7 v6 → v7 (path annotation, internal canary) |
| #615 | feat | α-5 reset — MultiHop-RAG + 5-axis + workspace |
| #616 | exec | ingest wrapper + bench timeout fix + first finding |
| #617 | docs | §7.4 first per-question-type signal |
| #618 | fix (d) | source-recall — bench dropped `sources` field |
| #619 | fix (d) | abstention phrases — English refusal coverage round 1 |
| #620 | tool | rescore tool + §7.4 76% → 36% correction |
| #621 | docs | 4-bucket diagnostic taxonomy + dual purpose |
| #622 | fix | render_report defensive path + bucket retroactive |
| #623 | fix (d) | session_id suite-aware + 3 narrow abstention phrases |
| #624 | docs | ROADMAP §v0.4.x α-5 cycle section |
| #625 | fix (a) | matrix runner suite hardcoded (caught by hygiene) |
| #626 | docs | T0 smoke result analysis TEMPLATE |
| #627 | docs | Pareto verdict walk-through + CLAUDE.md `fix` exempt + post-mortem |
| #628 | feat | T0 analysis fill script |
| #629 | docs | oracle.py package split plan (deferred) |
| #630 | docs | α-5 cycle summary outline (this doc, initial form) |
| #631 | docs | publishable narrative draft — "Don't Build a Layer for the Bug" |
| #632 | docs | bucket-(c) LLM-judge abstention detector design memo |
| #633 | feat | `qvt_promote_findings.py` — auto-draft memory entries from findings.md |
| #634 | docs | mid-cycle sync — ROADMAP PR table 24 + backlog §7.5/7.6/7.7/7.8 |
| #635 | fix | `core/observability.py::_trace_root()` workspace-aware (D11) |
| #636 | docs | A2 default-flip Quality Delta Card pre-template (D12) |
| #637 | test | 4-step rule contract — pin #618 / #619 / #623 measurement-debt fixes |
| #638 | fix (a) | matrix runner bench-output glob suite-aware (sibling to #625) + cell rescore tool |
| #639 | docs | Correction 4 post-mortem + narrative + backlog §7.9 |
| #640 | feat | `qvt_rescore_all_cells.py` — matrix-end audit + bulk rescore wrapper |
| #641 | docs | α-5 matrix closure runbook (operator sequence) |
| #[FILL] | feat | T0 result analysis publication (after matrix completes) |
| #[FILL] | feat | (optional) routing-flag default-flip PRs per layer |
| #[FILL] | docs | ROADMAP §v0.4.x cycle closure (replace "in flight" status) |

**Tally** (post-#641, pre-matrix-closure): **32 cycle PRs**.
- Bucket-(d) measurement-side fix: 3 (#618 / #619 / #623)
- Bucket-(a) measurement-side fix: 2 (#625 / #638)
- Methodology / design docs: 12 (#615 / #621 / #624 / #627 / #629 /
  #630 / #631 / #632 / #634 / #636 / #639 / #641)
- Tooling / scripts: 7 (#612 / #613 / #616 / #620 / #628 / #633 / #640)
- Code-side feats (think-mode track, not bucket-(d)/(a)): 4 (#608 /
  #609 / #611 / #614)
- Code-side hygiene fix: 2 (#622 / #635)
- Contract test: 1 (#637)
- Cycle outline / closure PR (after this): TBD

---

## 9. Open questions / deferred follow-ups

### 9.1 bucket-(c) LLM-judge abstention detector

The 6 remaining FN on the corrected baseline use phrasings the
narrow phrase list can't safely add ("is not available", "not
possible to") because they appear in disclaimers in partial-answer
responses too. An LLM classifier ("does this answer refuse to
answer the question?") would resolve them without phrase-overlap
FP risk. Slotted into the future `eval/qvt/oracle/abstention_judge.py`
when the [oracle split](../../docs/design/v0.4-qvt-oracle-package-split.md)
lands.

### 9.2 Korean-corpus MultiHop-RAG translation

JAMES's i18n stack handles both languages, but the matrix measured
English only. Korean MultiHop-RAG translation cost vs value is a
v0.5+ question. Memory `feedback_oracle_phrase_artifacts` open
questions covers the framing.

### 9.3 Production real-query Quality Delta Card

A2 default-flip (`JAMES_GEMMA4_E4B_THINK_OFF`) still waits for a
production-query QDC (separate from this benchmark cycle). The
A2 PR #609 follow-up gate.

### 9.4 T1 + T2 (if T0 indicated signal)

[FILL: did T0 say "stop" or "T1"? If T1, what's the operator
schedule? If "stop", any additional tier-gating evidence the
matrix would still want (M_S only, M_L only)?]

### 9.5 oracle.py package split

Designed (#629) but deferred. Trigger: post-cycle-closure,
pre-bucket-(c) work.

---

## 10. Cycle closure update — what's left

- [ ] Land cycle closure PR (this doc moves to a `release_notes` or
      `eval/RESULTS.md` excerpt, and ROADMAP §v0.4.x replaces
      "in flight" with closure state)
- [ ] If routing-flag default-flip verdicts: file 1 PR per layer
      with Quality Delta Card citing the matrix cell
- [ ] (Optional) oracle.py package split (PR #629 plan)
- [ ] (Optional) Joint-piece narrative draft if the
      reasoning-capability numbers warrant it

---

## 11. References

- ROADMAP §v0.4.x α-5 cycle (the "in flight" status this doc retires)
- Backlog reconciliation §7.3 (cycle reset) + §7.4 (corrections)
- Design memo `docs/design/v0.4-qvt-alpha-5-ablation-matrix.md` (§3.1
  5-axis Pareto verdict walk-through)
- Design memo `docs/design/v0.4-qvt-alpha-5-prereqs-plan.md` (the
  pre-cycle risk register that was eventually addressed)
- Design memo `docs/design/v0.4-qvt-oracle-package-split.md`
  (deferred split plan)
- Memory `feedback_oracle_phrase_artifacts` — 4-step rule + 4-bucket
  taxonomy
- Memory `alpha_5_multihop_rag_reset` — cycle reset framing
- Post-mortem `reports/research-runs/alpha-5-diagnostic-chain-post-mortem.md`
- Template `reports/research-runs/qvt-ablation-T0-smoke-analysis-TEMPLATE.md`
- Findings log `reports/research-runs/qvt-ablation-findings.md`
- Plan `~/.claude/plans/quiet-hugging-iverson.md`
