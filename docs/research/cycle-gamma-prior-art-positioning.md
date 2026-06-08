# Cycle γ Phase B+C — Prior art positioning

**Date**: 2026-06-08 (post Phase C closure session)
**Purpose**: Position the cycle γ "true signal" + inverse-lift finding
against published literature, identify what's JAMES-specific vs
already-established. Required reading before any publication-grade
claim (joint piece, paper, blog).

**TL;DR**: The broad framing ("JAMES enables abstention", "scaffold
helps weak models more", "JAMES emits model-independent signal") is
**already in published literature** under various names. JAMES
contributions that survive prior-art scrutiny are **narrower and
empirical** rather than mechanism-discovery.

---

## 1. What we claimed (post-Phase C handover)

From `docs/handovers/v0.4-cycle-gamma-phase-c-4model-true-signal-
2026-06-08.md`:

> "JAMES pipeline emits a benchmark-level latent abstention signal.
> Model absorption fraction depends on model capacity / instruction-
> following. Override of base model's native signal is a side effect
> of signal-model conflict resolution."

Implied universal-law candidate. Was framed as "architecturally-
invariant" because mxtral JAMES set = llama JAMES set EXACTLY on
RGB-en negrej.

---

## 2. Prior art that subsumes the broad framing

### 2.1 "RAG as external scaffolding" / "cognitive orthotic" / "cheat sheet effect"

Multiple sources frame RAG as scaffolding that compensates for weak
base model capability:

- **Direct quote (Wikipedia / RAG survey)**: "RAG benefits weaker
  models more than stronger ones. For weaker models like LLAMA-2,
  RAG significantly improves helpfulness, overall rating, generated
  definition rating, affordance rating. However, for stronger models
  (GPT3.5, Mixtral, WizardLM), RAG has no significant effect on
  enhancing or degrading the quality of generated texts on all
  metrics."

- This is **exactly the inverse-lift pattern** JAMES re-discovered
  on RGB-en (gemma4 +big, gemma3:12b 0, mxtral +small, llama 0/-).

- The "**saturation effect**" — stronger models already have the
  knowledge so RAG is redundant — is the published explanation that
  matches JAMES's "above-ceiling = no help" observation.

- **The "cheat sheet effect" of RAG** is an existing named concept
  for this exact pattern.

→ **JAMES did not discover this.** JAMES re-confirmed it on its
specific stack.

### 2.2 Boosting weak-to-strong (Schapire 1990, AdaBoost)

- Number of iterations to lift a weak learner is **inversely
  proportional to the weak learner's accuracy advantage γ**:
  `O(1/γ² log 1/ε)`.
- This is the canonical mathematical form of "scaffold helps weak
  more than strong".
- JAMES's empirical inverse-lift is a 2026 RAG-era re-instantiation
  of a 35-year-old proven result.

### 2.3 Knowledge distillation capacity gap

- Well-documented in KD literature: student capacity vs teacher
  capacity gap determines absorption.
- "When student capacity is too low … student struggles to
  effectively incorporate the logits information." — matches
  JAMES's gemma4 "4/6 absorption" finding mechanism.
- "When student capacity is excessively large … expected
  improvements may not materialize." — matches JAMES's llama
  "6/6 absorption with no Δ" because lateral swap.
- This is **the closest published analog to JAMES's "absorbed
  fraction" framework**.

### 2.4 Chain-of-Thought (Wei et al. 2022 + inverse-scaling work)

- CoT only helps at ~100B+ model scale; hurts smaller models.
- This is **opposite** to JAMES's inverse-lift: CoT helps strong
  models, JAMES helps weak.
- Different scaffold class (CoT = reasoning prompt; JAMES =
  retrieval+verification pipeline). The fact that scaffold-type
  determines which capacity tier benefits is itself a known
  meta-pattern in scaffold literature.

### 2.5 Toolformer (Schick et al. 2023) + small-model tool use

- 6.7B Toolformer surpasses 175B GPT-3 — small models with tools
  beat large without.
- The "tool gives small model what large model has internally"
  framing is established.

### 2.6 AbstentionBench (facebookresearch 2025-2026)

- Direct quote: "The fundamental two-stage architecture was
  preserved across all models: confidence robustly predicted
  abstention in every case. This dissociation suggests that while
  training procedures shape the specifics of abstention policy,
  **the use of confidence signals to guide metacognitive control
  emerges as a convergent solution across LLM implementations.**"
- This is **functionally identical** to JAMES's "true signal"
  framing — convergent abstention behavior across model
  implementations.
- AbstentionBench has 20 datasets + 35,000 queries, vs JAMES's
  single bench n=25.

→ **JAMES did not discover convergent cross-model abstention.**
AbstentionBench published this with much larger evidence base.

### 2.7 HALT-RAG (2025, arXiv:2509.07475)

- Calibrated NLI ensemble + lexical features + meta-classifier for
  RAG hallucination detection + abstention.
- F1 0.9786 on QA, much higher than JAMES's 0.276 / 0.387.
- Does NOT explicitly claim cross-model invariance of the
  abstention signal — that piece is closer to AbstentionBench.
- HALT-RAG is the methodologically-strongest published RAG
  abstention scaffold; JAMES's stack is weaker on the same task.

### 2.8 MKA (Multilingual Knowledge Abstention, arXiv:2503.23687)

- Uses cross-lingual consensus for abstention decisions — same
  "use multiple model views to drive abstention" framing as JAMES's
  "true signal".

### 2.9 LLM Cascades with Early Abstention (arXiv:2502.09054)

- Confidence-threshold-based deferral / abstention in cascades.
- Provides published framework for "model abstention as signal
  absorption".

---

## 3. What JAMES contributions actually survive prior art

### 3.1 Specific empirical measurement (modest but real)

- 4-model cross-architecture paired comparison on RGB-en
  (gemma4:e4b / gemma3:12b / mxtral:8x7b / llama3.1:8b)
- 200 LLM calls, n=25 per cell, 0 errors
- Two-workspace design (full vs negrej-only) — defensible
  apples-to-apples test methodology
- Open scripts (`scripts/research/cycle_gamma_rgb_corpus_build.py`,
  `cycle_gamma_rgb_compare.py`, `_audit_gemma4_negrej.py`) and
  open data
- Reproducibility = the contribution

### 3.2 Per-query identical-set observation on RGB-en

- mxtral JAMES abstention set = llama JAMES abstention set EXACTLY
  {3, 9, 14, 15, 17, 18} despite 47B MoE vs 8B dense architecture
- This per-query overlap is **empirically suggestive** of the
  AbstentionBench "convergent solution" claim
- BUT: n=2 architectures, n=25 queries — small sample. Cannot
  generalize to "all architectures converge" from this alone.
- Possible novel angle: **most prior work measures aggregate
  metrics (F1, recall) rather than per-query overlap sets.**
  Per-query overlap analysis as a method might be a minor
  methodology contribution.

### 3.3 PR #440 substitution-vs-synthesis gradient (with Robin extension)

- Two-mode separation (substitution = floor-immune; synthesis =
  gradient with task weight) on JAMES stack with
  cap-floor measurement
- Robin's 26B reproduction (DOI 10.5281/zenodo.20570701) extends
  this to **byte-identical cross-model + cap-invariant**
- This **specific mode-gradient finding** may be a JAMES + Robin
  contribution not directly covered by RAG-as-scaffolding
  literature
- Needs deeper lit search on "RAG mode separation" and "cap-floor
  in retrieval-vs-synthesis"

### 3.4 Quantitative absorbed-fraction framework on RGB-en

- Specific fractions (4/6, 3/6, 6/6, 6/6) tied to specific models
- Provides operating guidance: "if your base model is at gemma4-
  capacity tier, JAMES will absorb ~67% of available signal"
- Operating-doc contribution, not theoretical

---

## 4. Honest tier reassessment (post prior-art search)

| Tier | Status | Reason |
|---|---|---|
| ⭐ stable | ✅ | 4-model paired data, 200 LLM calls, 0 errors — measurement quality is the asset |
| ⭐⭐ confirmed (★재정정 #2★) | ⚠️ NARROWED | Empirical confirmation of established RAG-as-scaffolding / convergent-abstention literature on a specific stack. Reproducibility + per-query-overlap method = the contribution. Not mechanism discovery. |
| ⭐⭐⭐ universal-law | ❌ NOT CANDIDATE | Underlying mechanism is published (Schapire 1990, KD literature, AbstentionBench, RAG-as-scaffolding). JAMES is empirical re-instantiation. |

The Phase C handover overstated novelty. This doc corrects it.

The CASCADE-class 4/4 check still passes for "natural emergence +
unique implementation + operational value + honest framing", but
the bar for ⭐⭐⭐ requires **mechanism not in literature** —
which our broad framing fails.

---

## 5. Scope: JAMES-internal evaluation, NOT joint piece content

**★ Correction 2026-06-08 (user catch) ★**: an earlier version of
this section framed cycle γ Phase B+C findings as "joint piece
evidence" and proposed a "joint piece safe framing" subsection.
That was a **scope creep + co-author pre-agreement violation**.
Removed. See `memory/feedback_eval_cycle_vs_collab_arc_separation.md`
for the rule it violated.

### Why this doc does NOT feed into the mid-June joint piece

The mid-June joint piece is a **separate collaborative arc** with
its own 4-week+ negotiation history and pre-committed structure:

- **Topic (locked)**: "Two operating modes, one model" — substitution
  vs synthesis cap-floor mechanism in LLM cognitive scaffolds.
- **Headline (3-author locked)**: *"Substitution is free. Synthesis
  costs in proportion to what it has to invent."*
- **3 axes (pre-committed)**:
  1. Mode split (Robin, 26b sovereign)
  2. Workload gradient (JAMES PR #440 V3'.e on e4b)
  3. Model-scale efficiency (Robin 26b finding)
- **4-way contributors (pre-committed)**: Robin Converse / Ali Afana
  / Vadym Arnaut / Jiwon (JAMES)
- **Evidence pile (pre-committed)**: PR #440 V3'.e + Robin 26b
  companion repo + Ali e-commerce walk-back + Robin DOI
  10.5281/zenodo.20570701 (2026-06-08 arrival)
- **Prior art anchor (pre-committed)**: arxiv:2605.09104 Yang et al.
  2026 Token Economics (CES factor substitution framework)

**Cycle γ Phase B+C (this doc's subject)** = JAMES-internal RGB-en
evaluation, completely separate research arc:

- **Topic**: RGB-en abstention F1 + noise robustness on JAMES stack
- **Mechanism claim** (narrowed): empirical re-confirmation of
  published RAG-as-scaffolding pattern
- **Bench**: RGB-en (Chen et al. 2024 EMNLP) — different fixture
  from V3'.e e-commerce / Robin 26b sovereign
- **Contributors**: JAMES solo (no Ali/Robin/Vadym pre-agreement
  on this arc)
- **Time arc**: 2026-06-08 only

Adding cycle γ findings as "joint piece evidence" without explicit
Ali/Robin/Vadym pre-agreement = **vehicle mismatch + scope creep**.
That's prohibited by the rule in
`feedback_eval_cycle_vs_collab_arc_separation.md` (4 questions
checklist: vehicle / publication target / scope / framing-link).

### Where cycle γ findings DO belong

| Vehicle | Appropriate framing |
|---|---|
| Solo Zenodo DOI (future v0.4.x release) | "JAMES-side RGB-en evaluation dataset + measurement protocol on the JAMES stack" — same template as v0.3.1/v0.3.2/v0.3.3 metadata (see `zenodo_metadata_reframing_drafts.md`) |
| Internal handover docs | "cycle γ Phase B+C — JAMES-internal evaluation arc" |
| Mother-platform engineering record | Internal eval evidence for v0.5 readiness gate (D2 evidence), NOT publication |

### Claims to AVOID (regardless of vehicle)

The honesty-framing claims from §4 still apply:

1. ❌ "JAMES discovered cross-model abstention convergence" —
   AbstentionBench precedes this with much larger evidence.
2. ❌ "JAMES discovered inverse-lift / scaffold helps weak models
   more" — Schapire 1990, KD literature, RAG cheat-sheet effect
   all precede.
3. ❌ "JAMES emits a model-independent abstention signal" — basic
   claim covered under "scaffold provides external signal" framings.
4. ❌ "⭐⭐⭐ universal-law candidate" — mechanism is published.
5. ❌ **(new) "joint piece evidence / publishable for mid-June
   piece"** — separate collab arc, not pre-agreed.

### What about Robin's just-arrived DOI?

Robin's 26B byte-identical + cap-invariant reproduction
(DOI 10.5281/zenodo.20570701) extends PR #440 V3'.e Track 1 —
that **is** joint piece evidence (already pre-agreed scope).
That is a separate matter from this cycle γ doc.

The Robin DOI integration into the joint piece deposit happens via
the M9 prep ledger track (see
`docs/handovers/v0.4.x-session-2026-05-29-collaboration-checkpoint.md`
§5 M9 + `feedback_ali_resume_notice_june6.md`), NOT via this cycle
γ doc.

### Path D decision (2026-06-08, 7th honest-framing catch): do NOT chase HALT-RAG

After Phase D execution + the speculative "+0.050 from disabling
3 components" framing was caught (rule
`memory/feedback_single_axis_ablation_misframing.md`), a natural
follow-up question was raised: "should JAMES try to match HALT-RAG
abstention F1 0.978?" The four candidate paths considered:

| Path | What | Effort | Predicted F1 lift |
|---|---|---|---|
| A | Integrate NLI verifier (RoBERTa/DeBERTa ensemble) — HALT-RAG's core mechanism | 1-2 weeks | 0.387 → ~0.7 |
| B | Train HALT-RAG-style meta-classifier on labeled JAMES outputs | Months (ML cycle + data labeling) | 0.387 → ~0.978 |
| C | Add cascade abstention threshold (LLM Cascades style) | 1-2 PR | 0.387 → ~0.5 |
| **D** | **Don't chase HALT-RAG; preserve JAMES category** | 0 | unchanged |

**User decision 2026-06-08: Path D selected.** Recorded as
`memory/feedback_path_d_james_not_specialty_verifier.md`.

Reasoning:
- HALT-RAG = post-hoc verification specialty system
- JAMES = full-RAG + replayable audit + mother-platform 6-dim
  readiness
- Different categories. Single-axis (abst_f1) chase would dilute
  JAMES's unique strengths (replayable audit / per-query overlap
  method / open reproducibility / full pipeline integration)
- The HALT-RAG 0.978 vs JAMES 0.387 comparison was already
  on **different benchmarks** (HaluEval QA vs RGB-en negrej) —
  so the "2.5x gap" framing in earlier session summaries was
  not even apples-to-apples
- Path D preserves JAMES's actual contribution boundary as
  defined by this positioning doc

What Path D rejects:
- ❌ Path A NLI verifier integration (for the purpose of
  abst_f1 chase)
- ❌ Path B meta-classifier training
- ❌ Path C abstention-specific cascade threshold (for the
  purpose of abst_f1 chase)
- ❌ "JAMES is bad at abstention" framing (apples-to-oranges)
- ❌ Even Step 1 (NLI re-scoring of existing JAMES outputs) —
  that measurement was for deciding among Paths A/B/C, so it
  is also moot under Path D

What Path D allows (because motivated by axes OTHER than abst_f1):
- ✅ NLI used for noise robustness or graded improvement
- ✅ Cascade used for multi-hop reasoning improvement
- ✅ Cross-bench (ALCE/MuSiQue/2Wiki) — preserves JAMES's per-query
  overlap method as a methodology contribution
- ✅ Phase E multi-axis ablation — measures JAMES's actual axis
  bundle (not single abst_f1 chase)
- ✅ Mother platform 6-dim work (T3/T4/T5+ Lifecycle Semantics,
  ABAC, etc.)
- ✅ M9 joint deposit prep — separate collab arc, independent

This decision is the natural endpoint of the prior-art search
in this doc + the layer-intent-axis discipline in cycle β/γ:
**JAMES's contribution is the full-RAG + audit category, not a
specialty axis. Don't try to win at someone else's axis.**

---

## 6. What would need to change to reach ⭐⭐⭐

The "JAMES emits universal latent signal" claim could only become
⭐⭐⭐ universal-law if EITHER:

### Path A: empirical extension beyond what AbstentionBench covers
- per-query overlap analysis across **20+ models + 20+ benchmarks**
- demonstrate that per-query overlap mechanism is consistent at
  scale beyond aggregate F1
- this is essentially "AbstentionBench v2 with per-query overlap"
  → would need separate research project, not a cycle γ
  continuation

### Path B: mechanistic ablation of JAMES pipeline
- isolate WHICH JAMES component (query_rewrite / retrieval /
  reranker / verifier) emits the "true signal"
- if a specific component-level mechanism is identified that
  literature doesn't have, that could be a novel contribution
- requires Phase D mechanistic experiments (1-2 PR scope on RGB-en)

### Path C: novel measurement form
- the per-query overlap analysis ITSELF could be the contribution,
  not the underlying finding. If JAMES publishes the per-query-
  overlap measurement framework as a tool (with multi-bench multi-
  model results), that could be a methodology contribution.
- Closest to publishable from current data + scripts.

---

## 7. Recommended next steps

### Immediate (this session if continuing)

- **Update Phase C handover** with prior-art positioning footnote.
  Don't rewrite — append a "post prior-art search" addendum.
- Update memory entry to reflect narrowed tier claim.

### Joint piece prep (mid-June)

- **Use the §5 safe framing.** Frame JAMES as empirical +
  reproducibility contribution, not mechanism discovery.
- **Cite AbstentionBench, RAG-as-scaffolding, Schapire 1990,
  HALT-RAG** in any positioning artifact.
- **Robin's substitution-determinism Track 1 stays a JAMES + Robin
  joint result** — that one IS less covered by prior art (mode
  separation + cap-floor) than the abstention finding.

### Cycle γ continuation (if pursued)

- Phase B Option B cross-bench would add empirical breadth but
  NOT close the prior-art gap on its own — would still be empirical
  re-confirmation of known mechanisms.
- Phase D mechanistic ablation (Path B above) is the only path
  toward genuinely novel mechanism contribution.

---

## 8. Sources cited

### Boosting + classical
- Schapire, R. E. (1990). "The strength of weak learnability."
  Machine Learning. (Originator of inverse-lift claim.)
- Hsu, D. (2020). "Boosting" lecture notes. COMS 4995, Columbia.

### Knowledge distillation
- Hinton, G. et al. (2015). "Distilling the knowledge in a neural
  network." (Originator of student-teacher framework.)
- Various 2024 surveys on KD capacity gap.

### Chain-of-Thought
- Wei, J. et al. (2022). "Chain-of-thought prompting elicits
  reasoning in large language models." arXiv:2201.11903.
  (Shows CoT helps ~100B+ models only.)

### Tool use
- Schick, T. et al. (2023). "Toolformer: Language models can teach
  themselves to use tools." (6.7B + tools > 175B without.)

### RAG abstention + cross-model
- AbstentionBench (facebookresearch 2025-2026). Holistic abstention
  benchmark across 20 datasets + 35k queries. Direct precedent
  for cross-model convergent-abstention claim.
- HALT-RAG (Tjandra et al. 2025, arXiv:2509.07475). Calibrated NLI
  ensemble + abstention. F1 0.9786 on QA.
- MKA (Multilingual cross-lingual consensus abstention,
  arXiv:2503.23687).
- LLM Cascades with Early Abstention (arXiv:2502.09054).

### RAG-as-scaffolding
- Various 2024-2025 RAG papers framing RAG as "external
  scaffolding" / "cognitive orthotic" / "cheat sheet effect".
- RGB benchmark (Chen et al. 2024 EMNLP) — the bench used here.

### JAMES internal
- `docs/handovers/v0.4-cycle-gamma-phase-c-4model-true-signal-
  2026-06-08.md` — finding that this doc positions against prior
  art.
- `memory/project_cycle_gamma_phase_b_rgb_baseline.md` — full
  Phase B+C entry.
- PR #440 (V3'.e refined Pattern S) + Robin's DOI
  10.5281/zenodo.20570701 — substitution-determinism Track 1.
