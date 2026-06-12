# v0.4.4 — LRB v0.2.3 S3 publication-scale + cycle γ 4-bench infrastructure closure

**Released**: 2026-06-12 (PR sequence #819 → #836; ~6h autonomous loop predecessor PRs #797 → #818 from 2026-06-11/12 lap).

**DOI**: [`10.5281/zenodo.20652679`](https://doi.org/10.5281/zenodo.20652679)
**Predecessor DOI**: [`10.5281/zenodo.20625533`](https://doi.org/10.5281/zenodo.20625533) (v0.4.3)
**Concept DOI**: see Zenodo "Versions" tab of the parent record.

**Theme**: v0.4.4 extends v0.4.3 with **LRB v0.2.3** — the *Lifecycle Retrieval Benchmark*'s cross-scale reproducibility extension and a sibling axis to RAB v0.1.1. The v0.2.1 cross-model leg-clear (gemma4:e4b 4B / gemma3:12b 12B / mixtral:8x7b 47B / claude-haiku-4-5 cloud) established that **R@1 V<N<J on Phase B (S2 time-travel)** is not a single-model artefact; **v0.2.3 adds the scale axis**: a 4-point ladder spanning a **12.5× scale jump** (S2 N=80 → S3 publication N=1000) preserves the V<N<J inequality at every cell with JAMES − Naive gap above +0.10 throughout. **Pattern + gap are scale-robust ⭐⭐⭐; absolute magnitudes are scenario-sensitive ⭐⭐** (honest framing locked in preprint §5).

Same cycle ships the **cycle γ 4-bench measurement infrastructure closure**: D-alce research-tier NLI adapter + D-2wiki supporting-fact-aware producer promote ALCE and 2Wiki cells from ⭐ infra-only (v0.4.3) to research-tier-ready infrastructure for 4-of-4 cycle γ benches.

**No JAMES production runtime change** — v0.4.4 ships generators, scorers, runners, NLI adapters, 8 pre-registration LOCK documents, and 2 arXiv preprints (`papers/rab-preprint`, `papers/lrb-preprint`). The arXiv preprints cite Zenodo DOI 10.5281/zenodo.20652679 for data availability.

---

## What's new

### LRB v0.2.3 — cross-scale reproducibility extension

| PR | Type | Summary |
|---|---|---|
| #823 | feat | S3 publication-scale generator (smoke / dev / publication presets; 100 / 300 / 1000 docs; SHA-deterministic programmatic vocabulary; 25 unit tests) |
| #824 | feat | S3 token-mode 4-point ladder measurement (initial verdict) |
| #825 | fix | **S3.1 contract title diversity + honest-framing self-correction** (broken `current-contract` category R@10=0 caught via per-category audit; generator fix → honest J magnitude 0.845; re-graded verdict ⭐⭐⭐ pattern + gap / ⭐⭐ magnitude scenario-sensitive). **First self-catch in 12 wrong-fix-averted history** |
| #826 | docs | preprint §4.6 Cross-scale + §5 pattern-vs-magnitude framing + §6.1 Limitations + §7.4 Future Work |
| #827 | feat | v0.2.3b cross-model LLM-grounded runner (pure-reuse wrapper of v0.2.1 `run_cell`; operator-gated; pre-registration LOCKED) |
| #829 | fix | preprint typo corrections (leg 1 deltas, line 213 narrative) + abstract S3 integration (4 fixes) |

**Headline finding** (R@1 V<N<J 4-point scale ladder):

| Scenario | N (init/events/queries) | V R@1 | N R@1 | J R@1 | J−N gap |
|---|---|---|---|---|---|
| S2 token (frozen v0.2.1) | 200 / 564 / 80 | 0.225 | 0.5375 | 0.7125 | +0.175 |
| S3 smoke | 100 / 282 / 100 | 0.510 | 0.730 | 0.930 | +0.200 |
| S3 dev | 300 / 1206 / 300 | 0.530 | 0.737 | 0.913 | +0.176 |
| **S3 publication** | **1000 / 5620 / 1000** | **0.502** | **0.721** | **0.845** | **+0.124** |

### Cycle γ 4-bench infrastructure closure

| PR | Type | Summary |
|---|---|---|
| #819 | chore | LRB v0.2.1 claude S2 vanilla audit-trail closure (canonical R@1=0.6125 + ⭐ reproducibility band: claude API non-determinism produces ~10pp variance between two ~1.5min-apart runs) |
| #820 | feat | **D-alce research-tier NLI adapter** (`eval/external/alce_nli_adapter.py`; RoBERTa-large-MNLI primary + DeBERTa-v3-large-mnli-fever-anli-ling-wanli secondary; T5-XXL deferred; 19 unit tests) |
| #821 | feat | **D-2wiki supporting-fact-aware producer** (`eval/external/wikimulti_cited_producer.py` with `[Title #sent_id]` citation prompt + tolerant parser; 24 unit tests) |

After v0.4.4 the cycle γ 4-bench promise has **research-tier-ready infrastructure for 4 of 4 cells** (RGB + MuSiQue + ALCE + 2Wiki).

### Repository health + papers pre-flight

| PR | Type | Summary |
|---|---|---|
| #822 | chore | ruff F-class CI hygiene (39 violations → 0; 178 tests green) |
| #828 | docs | next-session entry handover |
| #830 | chore | Zenodo v0.4.4 mint prep (`.zenodo.json` + `RELEASE_NOTES_v0.4.4.md`); GitHub Release publish → webhook → DOI 10.5281/zenodo.20652679 minted |
| #831 | docs | preprint Data Availability + Acknowledgements (v0.4.4 DOI inserted) |
| #832 | fix | refs.bib citation corrections (6 LLM-fabricated citation patterns caught: 4 wrong-author-at-correct-arXiv-ID + 2 fabricated-URL entries) + LRB `\thanks{}` commit-hash insertion |
| #833 | fix | Stage-2 deep audit cleanup (EU AI Act precision, "JAMES T5" → "JAMES", LRB Acknowledgements over-attribution fix) |
| #834 | chore | README + CHANGELOG v0.4.4 sync (Phase 1 enterprise polish) |
| #835 | chore | README Phase 2 + Phase 3 (Papers section + "Why JAMES?" hero, EN + KO) |
| #836 | chore | SUMMARY.md + SECURITY.md + awesome-list-entry v0.4.4 sync |

---

## Self-correction narrative (12th wrong-fix-averted, **first self-catch**)

PR #824 originally claimed ⭐⭐⭐ "JAMES R@1 within ±0.05 of S2 token reference" (J = 0.673 at S3 publication vs J = 0.713 at S2 token, delta = 0.040). A per-category audit revealed `current-contract R@10 = 0.0` across all 3 SUTs from single-template title cluster collapse. PR #825 fixed the generator vocabulary (30 contract domains × 7 contract types = 210 unique title pairs), restored the broken category (R@10 = 1.0), revealed the honest J magnitude (0.845, delta +0.132 vs S2 token), and re-graded the verdict.

This is the **12th wrong-fix-averted in the JAMES cycle history** and the **first self-catch** (the prior 11 were all user-catches). The S3.1 fix → preprint §5 honest framing → arXiv abstract update self-correction loop is the strongest applied evidence of the project's `feedback_oracle_phrase_artifacts` measurement-side-artefact rule.

---

## What v0.4.4 does NOT include (separate cycles)

- LLM-grounded S3 publication run (v0.2.3b operator-gated; ~4-6h wall for 12 cells × 4 models)
- D-alce / D-2wiki research-tier measurement (operator-gated; HF cache ~1.5GB; CPU ~3-5min each)
- T5-XXL TRUE NLI Mixture integration (ALCE-official-grade; GPU-attended cycle)
- HR full sweep n=100 (operator-attended)
- TimeQA / TempReason / Microsoft GraphRAG SUT (operator data-download + license gated)
- arXiv preprint submission (pre-flight complete; endorsement is the operator-gated last step)
- v0.5 customer pilot LOI / pilot kickoff (separate trajectory)

---

## Verification

After v0.4.4: **~200+ tests pass**. New: `test_alce_nli_adapter.py` (19), `test_wikimulti_cited_producer.py` (24), `test_lrb_s3_generator.py` (27). Existing: 0 regressions. ruff F-class: 0 violations (down from 39).

## Reproduce

See `README.md` → "📑 Papers & Reproducibility" → "Reproduce in 60 seconds" code block.
