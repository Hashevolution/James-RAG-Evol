# RAB arXiv preprint — submission guide

> Companion to JAMES `v0.4.3` release / Zenodo
> [10.5281/zenodo.20625533](https://doi.org/10.5281/zenodo.20625533).

## Files

| File | Role |
|---|---|
| `main.tex` | Paper source (single file, minimal `article` class + `booktabs` + `hyperref`) |
| `refs.bib` | BibTeX references (ActiveGraph, agent-trace survey, EU AI Act, W3C PROV, NIST RMF, Audit Cards, AIReg-Bench, Black-Box Access, AI Act Eval Bench, Lewis 2020 RAG, JAMES Zenodo self-cite) |
| `README.md` | This file — submission step-by-step |

## Build

Local pdflatex (recommended for first iteration):

```bash
cd papers/rab-preprint
pdflatex main && bibtex main && pdflatex main && pdflatex main
# → main.pdf
```

Overleaf (easier for editing): upload `main.tex` + `refs.bib` to a new
project, set compiler to `pdfLaTeX`, build.

## arXiv submission metadata

### Recommended primary + cross-listings

| Category | Reason |
|---|---|
| **cs.SE** (Software Engineering) — primary | RAB is a benchmark + specification artifact; the closest single category |
| **cs.AI** (Artificial Intelligence) — cross-list | Audience overlap with agent-runtime / RAG community |
| **cs.CY** (Computers and Society) — cross-list | EU AI Act operationalisation makes this natural |

Some arXiv moderators prefer cs.AI as primary for AI-act-anchored
work; cs.SE is also defensible (benchmark + spec + scorer = SE
artefact). If the moderator asks for a swap, accept — content is the same.

### Title

> RAB: A Replayable-Audit Benchmark for RAG and Agent Systems Operationalising EU AI Act Articles 10, 12, 19

### Abstract (already in `main.tex` `\begin{abstract}` block)

The abstract is ~250 words and front-loads:
1. The EU AI Act deadline + the survey-named gap
2. The contribution = the benchmark (NOT the architecture; ActiveGraph
   gets explicit honest credit)
3. The three metrics + their anchors + the no-LLM-judge constraint
4. The gap table headline (3 SUTs) + the JAMES-wins disclaimer
5. The Zenodo DOI

### Comments field (suggested)

> 11 pages, 2 tables. Spec v0.1.1, two pre-registered scenarios
> (S1 40 ops, S2 400 ops), deterministic scorer, four adapters,
> and 12 re-verification artefacts at
> https://doi.org/10.5281/zenodo.20625533 (software) +
> https://doi.org/10.5281/zenodo.20635130 (Phase 3 pre-registration).
> Both measurements pre-registered before fixture/measurement.

### License

CC-BY 4.0 is the default arXiv recommendation; matches MIT-licensed
code on Zenodo. Alternative: arXiv perpetual non-exclusive license,
also fine.

## Endorsement

arXiv requires an endorser if you have not previously submitted to
cs.SE / cs.AI / cs.CY. Options:

1. **Self-endorsement** via institutional email if affiliation is
   eligible. Hashevolution is not in the auto-eligible list (most
   commercial/independent affiliations aren't).
2. **Personal endorser**: any existing arXiv author in the same
   category. Reach out to one of the cited authors (Yohei Nakajima
   for ActiveGraph / cs.AI; an Audit Cards author for cs.CY) with a
   short note + the v0.4.3 Zenodo link. They have 96 hours to act on
   the endorsement request.
3. **Co-author route**: add a co-author who is already endorsed.
   Robin / Ali / LEO are mentioned in JAMES collab arcs but the pre-reg
   explicitly separates this paper from the joint piece scope
   (see memory `feedback_eval_cycle_vs_collab_arc_separation`). Do
   NOT auto-link.

## Cross-link with Zenodo

After the arXiv ID is issued, update Zenodo to cite the arXiv ID as
`isSupplementedBy` (or `isDocumentedBy`) — this lets the two systems
discover each other:

1. Zenodo upload page → Edit metadata → Related/Alternate identifiers
2. Add `arXiv:<NNNN.NNNNN>` with relation `isSupplementedBy`
3. Save (no DOI version bump; this is post-mint metadata edit)

The paper itself already cites the Zenodo DOI in §Reproducibility +
the bib entry `seo2026jamesv043`.

## Honesty audit before submission

Run this checklist once more before clicking submit:

- [ ] No JAMES-wins framing — the headline word is "gap" everywhere,
      including the abstract. (Currently: ✅)
- [ ] ActiveGraph cited as independent co-invention in §Intro +
      §Related Work + abstract. (Currently: ✅)
- [ ] Pre-registration commit hash referenced — `8a35dee` appears
      in the title footnote and §Pre-registration. (Currently: ✅)
- [ ] EU AI Act effective date (2026-08-02) appears in §Intro.
      (Currently: ✅)
- [ ] Limitations section lists single-scenario + single-baseline-class
      + cited-source-only PC + synthetic-prose + author-of-benchmark
      conflict + **scenario-system co-design risk** +
      **mutation-site wiring partial** (7 items total). (Currently: ✅,
      paper v1.1)
- [ ] Zenodo DOI present in abstract + §Reproducibility + bib.
      (Currently: ✅)
- [ ] No language model is invoked anywhere in scoring (H1 honesty
      clause stated explicitly). (Currently: ✅)
- [ ] "RAB does not certify compliance" appears in abstract + §Spec.
      (Currently: ✅)
- [ ] **DFAH (arXiv 2601.15322) cited + "behavioural determinism vs
      log-artifact quality" disambiguation paragraph in §Related Work.**
      DFAH and RAB share "replayable" / "audit" terminology; the paper
      must say they measure orthogonal axes explicitly, or a reviewer
      will. (Currently: ✅, paper v1.1)
- [ ] **COMPL-AI (arXiv 2410.07959) cited + "model-level vs
      system-level AI Act" paragraph in §Related Work.** COMPL-AI is
      the AI-Act-benchmark precedent RAB inherits; not citing it would
      look like an oversight. (Currently: ✅, paper v1.1)
- [ ] **"First" framing is precise**: "to our knowledge, the first
      benchmark that scores the exported audit-log artifact …" rather
      than the unqualified "first replayable-audit benchmark". DFAH
      already uses the "replayable" word in a sibling category.
      (Currently: ✅, paper v1.2 abstract + conclusion)
- [ ] **Baseline-1 (OTel GenAI bolt-on) is in Results, not Future
      Work.** The 4-SUT gap table (Reference / JAMES / Baseline-1 /
      Baseline-0) is the headline; the two-fail-modes analysis is a
      named §Results subsection. (Currently: ✅, paper v1.2 §7)
- [ ] **"Two fail-modes" framing explicit.** Baseline-0 fails at
      INGEST coverage of ANSWER; Baseline-1 fails at INGEST coverage
      of corpus lifecycle. Both fail at RF/PC entirely. The AC overall
      column is explicitly disclaimed as not the headline. (Currently:
      ✅, paper v1.2 §7 + Conclusion)
- [ ] **OTel GenAI source-spec gap is named honestly.** The absence
      of INGEST/UPDATE/SUPERSEDE/DELETE in OTel GenAI is a property of
      the source spec, not of the adapter; the mapping table's
      rationale paragraph documents this and the paper repeats it.
      (Currently: ✅, paper v1.2 §5.3 + mapping-table file)
- [ ] **Scenario-S2 cross-scenario evidence is in Results, not Future
      Work.** Table 2 (S2 gap table) sits in §7 with its own subsection
      after Table 1; the two-fail-modes structure reproduces to 3
      decimal places; the conclusion that the gap structure is not a
      function of corpus size is stated explicitly. (Currently: ✅,
      paper v1.3 §7.2 + Conclusion)
- [ ] **RF-cost claim withheld honestly.** Phase 3 pre-registration
      §4 locked two thresholds; only the first cleared (S2 ratio
      2.79× < 5× locked); the paper reports the numbers and applies
      the locked decision rule rather than tightening the claim
      post-hoc. (Currently: ✅, paper v1.3 §7.2 + §6)
- [ ] **Honest tier landing matches the locked ladder.** The paper
      reports against the second rung of the pre-registered ladder
      ($\star\star$ cross-scenario partial); $\star\star\star$ remains
      ungated because the locked ladder required both the gap and the
      RF-cost leg, and only the first cleared. The pre-registration is
      the citation for "ladder as written." (Currently: ✅, paper v1.3
      §6 + §7 + Conclusion)
- [ ] **Scenario-S2 pre-registration DOI present in title footnote
      and §6.** The Phase 3 pre-registration is separately archived
      at Zenodo (DOI placeholder until minted) and cited in the title
      thanks block, §6, and §9. (Currently: ⏳ awaiting DOI mint;
      placeholder `10.5281/zenodo.20635130` in paper source.)

## What this preprint does NOT do

- It does not benchmark a third audit-native runtime — replication
  track is separate collaboration scope (§Future Work track 2).
- It does not present cross-vocabulary-basis cross-scenario results
  — S2 reproduces the gap at $10\times$ scale but uses the same
  canonical event set as S1; scenario-S3 (cross-lingual) is queued
  in §Future Work track 1.
- It does not claim the RF-cost $O(N^2)$ candidate finding — the
  pre-registration locked a $5\times$ threshold that the S2 ratio
  ($2.79\times$) does not clear; a third scenario at $\ge 4\times$
  S2 op count is the cleanest next data point (§Future Work track 1).
- It does not benchmark ActiveGraph — replication track is separate
  collaboration scope (§Future Work track 2).
- It does not propose new architectural primitives — the spec is the
  contribution.

## Post-submission follow-up

1. Add the arXiv ID to JAMES `CHANGELOG.md` `[0.4.3]` and to
   `.zenodo.json` `related_identifiers` (as `isSupplementedBy`) in a
   small post-mint PR (analogous to PR #769 for the DOI badge).
2. Update memory `project_r1_replayable_audit_benchmark` with the
   arXiv ID.
3. Add to the JAMES README badges row:
   `[![arXiv](https://img.shields.io/badge/arXiv-NNNN.NNNNN-b31b1b.svg)](https://arxiv.org/abs/NNNN.NNNNN)`

## What this is NOT for

- This is NOT the mid-June joint piece with Robin / Ali. That work has
  a separate scope, separate contributors, separate evidence pile, and
  a separate publication track. Per
  `feedback_eval_cycle_vs_collab_arc_separation`, the two MUST NOT be
  auto-linked.
