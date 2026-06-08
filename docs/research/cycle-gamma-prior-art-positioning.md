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

## 5. What this means for the mid-June joint piece

### Safe claims (publishable)

1. "JAMES Track 1 (substitution determinism, PR #440 + Robin's
   26B extension) is a measurement contribution — reproducible
   substitution-vs-synthesis mode gradient with cap-invariance."
2. "On RGB-en, JAMES exhibits the published RAG-as-scaffolding
   pattern (weak-base lifter, ceiling convergence) — adds 4-model
   paired data + per-query overlap evidence to the existing
   literature."
3. "Per-query identical JAMES abstention set across mixtral and
   llama on RGB-en suggests the AbstentionBench convergent-
   abstention finding holds at the per-query level on this stack."

### Claims to AVOID

1. ❌ "JAMES discovered cross-model abstention convergence" —
   AbstentionBench precedes this with much larger evidence.
2. ❌ "JAMES discovered inverse-lift / scaffold helps weak models
   more" — Schapire 1990, KD literature, RAG cheat-sheet effect
   all precede.
3. ❌ "JAMES emits a model-independent abstention signal" — basic
   claim covered under "scaffold provides external signal" framings.
4. ❌ "⭐⭐⭐ universal-law candidate" — mechanism is published;
   JAMES is reproduction-grade empirical, not theory-grade.

### Joint piece angle that could work

**"Reproducibility + per-query method": JAMES Track 1 (PR #440 +
Robin's 26B) provides byte-identical cross-model reproduction with
public artifacts (DOI, scripts, data). JAMES cycle γ Phase B+C
provides 4-model paired RGB-en data with per-query overlap analysis
that adds granularity to the AbstentionBench aggregate finding.
Neither is mechanism discovery; both are measurement infrastructure
contributions.**

This framing:
- Honestly bounds the contribution
- Highlights what's unique (reproducibility + per-query method)
- Cites the actual prior art (AbstentionBench, RAG-scaffolding)
- Sets up future cycle γ work (cross-bench, mechanistic ablation)
  as the path to genuine novelty

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
