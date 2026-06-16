# v0.4.4 — LRB v0.2.3 S3 publication-scale + cycle γ 4-bench infrastructure closure

**Date**: 2026-06-12
**Predecessor**: v0.4.3 — `10.5281/zenodo.20625533` (deposited 2026-06-10)
**Concept DOI**: see Zenodo "Versions" tab of the parent record (chain-anchor across all versions)
**Tag**: `v0.4.4`
**Commit**: (this release tag)

---

## What's new (11 PRs since v0.4.3)

### LRB v0.2.3 — cross-scale reproducibility extension (6 PRs)

| PR | Type | Summary |
|---|---|---|
| #823 | feat | S3 publication-scale generator (smoke / dev / publication presets; 100 / 300 / 1000 docs; deterministic-SHA programmatic vocabulary; 25 unit tests) |
| #824 | feat | S3 token-mode 4-point ladder measurement (V<N<J preserved across smoke / dev / publication) |
| #825 | fix | S3.1 contract title diversity (30 domains × 7 types = 210 unique pairs) + honest-framing self-correction (retracts pre-S3.1 over-tight ±0.05 verdict) |
| #826 | docs | preprint §4.6 Cross-scale + §5 pattern-vs-magnitude framing + §6.1 Limitations + §7.4 Future Work updates |
| #827 | feat | v0.2.3b cross-model LLM-grounded runner (operator-gated execution; pre-reg LOCKED) |
| #829 | fix | preprint typo corrections (leg 1 deltas + line 213 narrative) + abstract S3 integration (4 fixes) |

**Headline finding**: R@1 V<N<J inequality preserved at every cell of a 4-point scale ladder spanning a **12.5× scale jump** (S2 N=80 → S3 publication N=1000). JAMES − Naive gap remains above +0.10 at every cell.

| Scenario | N (init/events/queries) | V R@1 | N R@1 | J R@1 | J−N gap |
|---|---|---|---|---|---|
| S2 token (frozen v0.2.1) | 200 / 564 / 80 | 0.225 | 0.5375 | 0.7125 | +0.175 |
| S3 smoke | 100 / 282 / 100 | 0.510 | 0.730 | 0.930 | +0.200 |
| S3 dev | 300 / 1206 / 300 | 0.530 | 0.737 | 0.913 | +0.176 |
| **S3 publication** | **1000 / 5620 / 1000** | **0.502** | **0.721** | **0.845** | **+0.124** |

Pattern + gap are scale-robust (⭐⭐⭐). Absolute magnitudes are scenario-sensitive (⭐⭐; synthetic templated vocabulary has lower retrieval ambiguity than hand-curated S2 city-operations text). Cross-scenario claims are therefore limited to ordering and gap structure, not absolute magnitude.

### Cycle γ 4-bench promise — infrastructure closure (3 PRs)

| PR | Type | Summary |
|---|---|---|
| #819 | chore | LRB v0.2.1 claude S2 vanilla audit-trail closure (canonical R@1=0.6125 + reproducibility band ⭐ finding: claude API non-determinism produces ~10pp variance between two 1.5min-apart runs) |
| #820 | feat | D-alce research-tier NLI adapter (RoBERTa-large-MNLI primary + DeBERTa-v3-large-mnli-fever-anli-ling-wanli secondary; 19 unit tests; T5-XXL TRUE NLI Mixture deferred to GPU-attended cycle) |
| #821 | feat | D-2wiki supporting-fact-aware producer (`WikiMultiCitedProducer` with `[Title #sent_id]` citation prompt + tolerant parser; 24 unit tests) |

After v0.4.4, the cycle γ 4-bench promise has **research-tier-ready infrastructure for 4 of 4 cells** (RGB + MuSiQue + ALCE + 2Wiki). v0.4.3's ⭐ infra-only caveat for ALCE / 2Wiki is closed.

### Repository health (2 PRs)

| PR | Type | Summary |
|---|---|---|
| #822 | chore | ruff F-class CI hygiene — 39 pre-existing F401/F541/F841 violations closed; 178 tests green |
| #828 | docs | Next-session entry handover doc + CLAUDE.md "Where to look next" pointer update |

---

## Self-correction example (12th wrong-fix-averted, **first self-catch**)

PR #824 originally claimed ⭐⭐⭐ "JAMES R@1 within ±0.05 of S2 token reference" (J = 0.673 at S3 publication vs J = 0.713 at S2 token, delta = 0.040). A per-category audit revealed `current-contract R@10 = 0.0 across all 3 SUTs` from single-template contract-title cluster collapse — the broken category coincidentally pulled J magnitude down to match S2.

PR #825 fixed the generator vocabulary, restored the broken category (R@10 = 1.0), revealed the honest J magnitude (0.845, delta +0.132 vs S2 token), and re-graded the verdict (⭐⭐⭐ pattern preserved + ⭐⭐ magnitude scenario-sensitive). PR #826 propagated the honest framing into preprint §5; PR #829 corrected residual abstract / leg 1 typos.

This is the **12th wrong-fix-averted** in the JAMES cycle history and the **first self-catch** (the prior 11 were all user-catches). The S3.1 → preprint §5 → arXiv abstract self-correction loop is the strongest applied evidence of the `feedback_oracle_phrase_artifacts` measurement-side artefact rule: when overall magnitude looks like a coincidence, audit per-category before declaring ⭐⭐⭐.

---

## What's NOT included (separate cycles)

- **LLM-grounded S3 publication run** (v0.2.3b operator-gated; ~4-6h wall for 12 cells × 4 models)
- **D-alce research-tier measurement** (operator-gated; HF cache ~1.5GB × 2, CPU ~3-5min × 2)
- **D-2wiki research-tier measurement** (operator-gated; ~3-5min on local gemma4:e4b)
- **T5-XXL TRUE NLI Mixture integration** (ALCE-official-grade verifier; GPU-attended)
- **HR full sweep n=100** (operator-attended)
- **TimeQA / TempReason / Microsoft GraphRAG SUT** (operator data-download + license gated)
- **arXiv preprint LRB v0.2.5 submission** (pre-flight in progress; this DOI will be cited in Acknowledgements)
- **Joint-piece collab arc with Robin Converse / Ali Afana** (separate trajectory, not auto-linked per the eval-cycle-vs-collab-arc-separation rule)

---

## Reproducing the results

```bash
# 1. Generate scenario fixtures (deterministic; no LLM; SHA-pinned)
python scripts/research/build_lrb_scenario_s1.py
python scripts/research/build_lrb_scenario_s2.py
python scripts/research/build_lrb_scenario_s3.py --scale smoke
python scripts/research/build_lrb_scenario_s3.py --scale dev
python scripts/research/build_lrb_scenario_s3.py --scale publication

# 2. Phase A (S1 current-only) + Phase B (S2 time-travel) token-mode
python scripts/research/lrb_run_phase_b.py --scenarios S1,S2 --k 10

# 3. v0.2.1 cross-model (S1+S2 × 4 models × token + llm-grounded)
PYTHONPATH=. python scripts/research/lrb_run_v021_cross_model.py \
  --scenarios S1,S2 \
  --modes token,llm-grounded \
  --models gemma4:e4b,gemma3:12b,mixtral:8x7b,claude-haiku-4-5

# 4. v0.2.3 S3 token-mode ladder (this release; deterministic; no LLM)
python scripts/research/lrb_run_s3.py --scale smoke
python scripts/research/lrb_run_s3.py --scale dev
python scripts/research/lrb_run_s3.py --scale publication

# 5. v0.2.3b S3 cross-model LLM-grounded (this release infrastructure;
#    operator-gated; expensive)
PYTHONPATH=. python scripts/research/lrb_run_v023b_s3_cross_model.py \
  --scale publication \
  --modes llm-grounded \
  --models gemma4:e4b,gemma3:12b,mixtral:8x7b,claude-haiku-4-5

# 6. v0.2.4 HR axis (RoBERTa primary + DeBERTa rescore)
PYTHONPATH=. python scripts/research/lrb_v024_hr_smoke.py
PYTHONPATH=. python scripts/research/lrb_v024_hr_rescore.py

# 7. Cycle γ 4-bench (RGB + MuSiQue + ALCE + 2Wiki)
python scripts/research/alce_smoke_run.py --verifier roberta-mnli --n 20
python scripts/research/alce_smoke_run.py --verifier deberta-v3-anli --n 20
python scripts/research/wiki2_smoke_run.py --cited --n 20
```

All result.json + bench.jsonl files land in `reports/external/lrb/` and `reports/external/{alce,2wiki,musique}/` deterministically (SHA-pinned per fixture; LLM-grounded mode inherits the ~10pp claude-API reproducibility band documented in PR #819).

---

## Citation

```bibtex
@software{seo2026james044,
  author    = {Seo, Jiwon},
  title     = {PROJECT JAMES — v0.4.4 (LRB v0.2.3 S3 publication-scale +
               cycle γ 4-bench infrastructure closure)},
  year      = {2026},
  month     = {6},
  doi       = {10.5281/zenodo.XXXXXXXX},
  url       = {https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.4.4},
  version   = {v0.4.4},
  publisher = {Zenodo}
}
```

(DOI populated by Zenodo after release publish.)

---

## Pre-registrations (LOCKED before measurement, R5 rule)

| Cycle | Pre-reg doc |
|---|---|
| LRB Phase A (S1 current-only) | `docs/research/lrb-phase-a-smoke-preregistration-2026-06-11.md` |
| LRB Phase B (S2 time-travel) | `docs/research/lrb-phase-b-time-travel-preregistration-2026-06-11.md` |
| LRB v0.2.1 cross-model | `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md` |
| LRB v0.2.4 HR axis | `docs/research/v024-hr-nli-axis-preregistration-2026-06-11.md` |
| **LRB v0.2.3 S3 scale** (new) | `docs/research/lrb-v023-s3-publication-scale-preregistration-2026-06-12.md` |
| **LRB v0.2.3b S3 cross-model** (new) | `docs/research/lrb-v023b-s3-cross-model-preregistration-2026-06-12.md` |
| **D-alce research-tier NLI** (new) | `docs/research/cycle-gamma-d-alce-research-tier-nli-preregistration-2026-06-12.md` |
| **D-2wiki supporting-fact** (new) | `docs/research/cycle-gamma-d-2wiki-supporting-fact-preregistration-2026-06-12.md` |

Each pre-reg is a Markdown LOCK doc committed before any measurement code or result.json artefact. All eight pre-regs (including the four inherited from v0.4.3) are committed in this repository and accessible at the v0.4.4 tag commit.

---

## Test suite

After this release: **~200+ tests pass**. Touched in v0.4.4:
- `tests/test_alce_nli_adapter.py` — 19 tests (D-alce contract)
- `tests/test_wikimulti_cited_producer.py` — 24 tests (D-2wiki parser + scorer round-trip)
- `tests/test_lrb_s3_generator.py` — 27 tests (S3 vocabulary primitives + determinism + scale invariants)
- Existing tests: 0 regression from any of the 11 PRs

---

## Honest framing summary

The headline of v0.4.4 is the **SCALE-axis extension of the V<N<J finding** (LRB), not a JAMES win. Gap structure is the headline per LRB SPEC §4.6.

- ✓ Pattern + gap scale-robust (publication-tier evidence)
- ⚠ Absolute magnitudes scenario-sensitive (honest caveat; not a JAMES claim)
- ✗ ActiveGraph (arXiv 2605.21997) is independent co-invention of the audit-native validity-window architecture; LRB does NOT claim novelty of the architecture, only of the benchmark and the cross-scale measurement
- = Multi-hop reasoning is **measured parity** — V=N=JAMES produce 4-decimal-identical EM/F1 on MuSiQue, so JAMES adds **no reasoning degradation**. The lifecycle/validity-window axes are retrieval-side and orthogonal to closed-book reasoning; this is equivalence, not a failed win.
- ✗ EU AI Act references are anchor / framing, not compliance certification

This release is the data-availability anchor for the LRB v0.2.5 arXiv preprint. The preprint's Acknowledgements section will cite the v0.4.4 DOI assigned at Zenodo mint.
