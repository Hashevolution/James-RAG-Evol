# LRB v0.2.3 S3 publication-scale results (2026-06-12, FINAL with S3.1 fix)

> **Pre-reg**: `docs/research/lrb-v023-s3-publication-scale-preregistration-2026-06-12.md`
> **Honest tier**: ⭐⭐⭐ R@1 V<N<J pattern preserved at N=1000 / ⭐⭐ JAMES R@1 magnitude scenario-sensitive
> **Generator**: `scripts/research/build_lrb_scenario_s3.py` (PR #823 + S3.1 contract diversity fix this PR)
> **Runner**: `scripts/research/lrb_run_s3.py` (PR #824)
> **Mode**: token (deterministic; no LLM grounding)
> **Date**: 2026-06-12

---

## 1. Headline finding

**R@1 V<N<J inequality preserved across 4 data points spanning 12.5×
scale** (N=80 → N=1000). The PATTERN is robust; the MAGNITUDES are
scenario-sensitive (S3 synthetic R@1 ceilings differ from S2 hand-
curated by ~0.13 at publication scale).

## 2. Scale ladder table (FINAL, post-S3.1)

| Scenario | N (init/events/queries) | V R@1 | N R@1 | J R@1 | V<N<J | J − N | J − V |
|---|---|---|---|---|---|---|---|
| **S2 token** (frozen v0.2.1) | 200 / 564 / 80 | 0.225 | 0.538 | **0.713** | ✓ | +0.175 | +0.488 |
| **S3 smoke** (this PR) | 100 / 282 / 100 | 0.510 | 0.730 | **0.930** | ✓ | +0.200 | +0.420 |
| **S3 dev** (this PR) | 300 / 1206 / 300 | 0.530 | 0.737 | **0.913** | ✓ | +0.176 | +0.383 |
| **S3 publication** (this PR) | 1000 / 5620 / 1000 | 0.502 | 0.721 | **0.845** | ✓ | +0.124 | +0.343 |

## 3. Per-category R@10 (S3 publication, N=1000, post-S3.1)

| Category | Vanilla | Naive | JAMES | d(J−N) | d(J−V) |
|---|---|---|---|---|---|
| current-contract | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| current-director | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| current-policy | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| current-project-lead | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| historical-early-contract | 0.9550 | 0.0000 | 0.9550 | +0.9550 | 0 |
| historical-early-director | 1.0000 | 0.5000 | 1.0000 | +0.5000 | 0 |
| historical-mid-director | 1.0000 | 0.7576 | 1.0000 | +0.2424 | 0 |
| historical-mid-policy | 1.0000 | 0.4118 | 1.0000 | +0.5882 | 0 |
| historical-mid-project-lead | 0.8182 | 0.4545 | 1.0000 | +0.5455 | +0.1818 |
| never-stale-budget | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |

current-contract is now 1.0 across all 3 SUTs (was 0.0 in pre-S3.1 due
to retrieval cluster collapse from single-template title vocabulary).

## 4. Honest interpretation

### What this DOES show (⭐⭐⭐ pattern, ⭐⭐ magnitude)

- **Pattern robustness ⭐⭐⭐**: R@1 V<N<J inequality preserved at every
  scale point in the 4-point ladder. The fundamental claim — JAMES's
  validity-window approach beats both vanilla and naive-supersede on
  time-travel queries — is scale-robust.
- **JAMES > Naive R@1 gap robust ⭐⭐⭐**: d(J−N) = +0.175 (S2) ... +0.124
  (S3 publication). JAMES retains a >0.10 R@1 advantage over the next-
  best SUT at every scale.
- **historical-* categories** keep showing JAMES at 1.0 (or near) and
  Naive significantly below (matching the S2 differentiator finding).

### What this does NOT show (honest caveats)

- **JAMES R@1 ABSOLUTE magnitude is scenario-sensitive ⭐⭐**: J swings
  from 0.713 (S2 token, hand-curated 200 docs) to 0.930 (S3 smoke
  synthetic 100 docs). Synthetic scenarios produce HIGHER absolute R@1
  for all 3 SUTs (less vocabulary ambiguity than hand-curated cities-
  operations text). Magnitudes do NOT propagate cross-scenario; only
  the ordering does.
- **V/N magnitudes also scenario-sensitive**: V swings 0.225 → 0.502
  across scenarios. The synthetic templates make current-* queries
  easier for vanilla (templated dept/project/policy titles cluster
  predictably).
- **No LLM-grounded claim**: this is token-mode only. The published S2
  ⭐⭐⭐ V<N<J 4-model claim (claude / mxtral / gemma3:12b / gemma4:e4b)
  does NOT propagate to S3 publication without separate LLM-grounded
  runs (v0.2.3b cycle).
- **Pre-S3.1 verdict (0.040 delta vs S2 was within ±0.05 band) was
  ARTIFACT** of one broken category (current-contract = 0.0 across all
  3 SUTs from single-template retrieval cluster collapse). S3.1 fix
  restores the broken category and reveals the HONEST scenario-
  sensitivity. The previous "tight band" finding was post-hoc-fit to a
  measurement artifact.

## 5. S3.1 contract diversity fix (this PR)

**Bug**: Pre-S3.1 `make_contract` used single template `"{verb}
Services Contract"` — 20 verbs cycled across 200 contracts. All 200
contracts shared the substring "Services Contract" → BM25 / embedding
retrieval couldn't disambiguate among them.

**Symptom**: current-contract R@10 = 0.0 across all 3 SUTs at S3
publication.

**Fix**: 30 CONTRACT_DOMAINS × 7 CONTRACT_TYPES = 210 unique
(domain, type) pairs, deterministically assigned via global contract
index `dept_idx * contracts_per_dept + con_idx`. Distinguishable
titles like "Asphalt Resurfacing Contract", "Software Licensing
Agreement", "Tax Portal Statement of Work", etc.

**Verification**: 200/200 unique contract titles in publication preset
(was 60 / 200 pre-fix due to stride collisions; final iteration uses
unique enumeration). New unit test
`tests/test_lrb_s3_generator.py::ContractDiversityTests` pins this.

## 6. Verdict (per prereg §2, FINAL after S3.1)

The pre-registered verdict matrix conditions and observed values:

| Condition | Observed | Verdict |
|---|---|---|
| R@1 V<N<J pattern preserved at every scale point | ✓ (4/4) | ⭐⭐⭐ pattern scale-robust |
| JAMES R@1 magnitude within ±0.05 of S2 token-mode at every scale | ✗ (S3 publication J=0.845 vs S2 token J=0.713, delta=0.132) | ⭐⭐ magnitude scenario-sensitive |
| JAMES > Naive R@1 gap > 0.10 at every scale point | ✓ (+0.175 / +0.200 / +0.176 / +0.124) | ⭐⭐⭐ gap robust |

**Composite verdict**: ⭐⭐⭐ **Pattern + gap scale-robust** / ⭐⭐
**Absolute magnitudes scenario-sensitive**. Both findings are
publishable — the pattern is the JAMES claim, the magnitude variance
is the honest caveat for cross-scenario comparison.

## 7. What this enables (paper integration)

- arXiv preprint Discussion §6 / Limitations:
  > "Token-mode scale propagation: R@1 V<N<J pattern preserved across
  > 4 scenarios spanning 12.5× scale (S2 N=80 → S3 publication N=1000).
  > JAMES − Naive R@1 gap remains > 0.10 at every scale point. Absolute
  > magnitudes are scenario-sensitive (synthetic vocabulary produces
  > higher absolute R@1 ceilings); cross-scenario claims are limited
  > to ordering, not magnitude."
- paper v1.4 Results §5: scale ladder table (§2 above) as supplementary
  figure.
- Pre-reg verdict matrix §2: ⭐⭐⭐ pattern + gap PASSED, ⭐⭐ magnitude
  HONEST CAVEAT.

## 8. Artifacts (deterministic, re-runnable)

```
reports/external/lrb/phase-b-s3-smoke-<ts>.{vanilla,naive-supersede,james}.{result.json,bench.jsonl}
reports/external/lrb/phase-b-s3-dev-<ts>.{vanilla,naive-supersede,james}.{result.json,bench.jsonl}
reports/external/lrb/phase-b-s3-publication-<ts>.{vanilla,naive-supersede,james}.{result.json,bench.jsonl}
```

Fixture SHAs (deterministic; re-generation produces byte-identical
files; POST-S3.1):
- `scenario_S3_smoke.json`       (re-run)
- `scenario_S3_dev.json`         (re-run)
- `scenario_S3_publication.json` = `bf54b7f7dc1fccf4...`

## 9. Follow-up cycle prerequisites

| Phase | 작업 | Honest tier prereq |
|---|---|---|
| v0.2.3b | S3 publication × LLM-grounded (1 model = gemma4:e4b) | LLM call cost ~hours; operator-gated |
| v0.2.3c | S3 publication × LLM-grounded × 4 models (cross-model) | publication-tier ⭐⭐⭐ scale × model |
| S3.2 | Diversify project / policy / appointment vocabularies (current 1.0 ceiling = no resolution at small queries) | minor PR |
| v0.2.4 | S3 publication × HR cross-NLI | adapter exists; smoke pending |

## 10. 관련

- `docs/research/lrb-v023-s3-publication-scale-preregistration-2026-06-12.md` — pre-reg lock
- `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md` — S2 cross-model prereg (paired)
- `docs/handovers/v0.4-autonomous-loop-FINAL-2026-06-12.md` §2 — S2 4-model V<N<J table
- `scripts/research/build_lrb_scenario_s3.py` (PR #823 + this PR S3.1) — generator
- `scripts/research/lrb_run_s3.py` (PR #824) — runner
- `memory/feedback_finding_size_honest_framing.md` — honest tier rule applied (PRE-S3.1 ⭐⭐⭐ "within ±0.05" claim retracted as artifact)
- `memory/feedback_self_evaluation_trap.md` — self-eval trap rule (S3 uses S2 schema; scoring authority unchanged)
- `memory/feedback_oracle_phrase_artifacts.md` — measurement-side artifact rule (current-contract = 0.0 was a generator-side artifact; the right correction is generator fix, not metric reinterpretation)
