# JAMES-RAG-Evol Reproducibility Report v1 — SKELETON

> **Status: SKELETON / NOT FOR RELEASE.** This is the scaffold for a citable
> reproducibility report. It binds together the two existing preprints
> (RAB, LRB) under a single "can anyone reproduce this?" narrative. Sections
> marked _[fill]_ pull from committed artifacts; the honest-framing verdicts
> are pre-locked so a future author cannot quietly upgrade them.
>
> Zenodo DOI minting and arXiv submission are **operator actions** — this
> skeleton does not self-publish.

## 0. Framing lock (read first)

This report's claims are bounded by the project's measured reality:

- **What we claim is reproducible:** RAB (audit-log replayability) and LRB
  (temporal/lifecycle retrieval), both deterministic-scorer-only.
- **What we do NOT claim:** generic Graph-RAG reasoning gains. On open
  multi-hop (MuSiQue/MultiHop-RAG) the measured result is null/parity
  (`docs/handovers/v0.4-track-c-musique-improvement-loop-FINAL-2026-06-12.md`).
- **RAB headline = gap structure, not a JAMES-wins leaderboard** (SPEC §6.5).
- **LRB headline = scale-robust pattern + gap (strong); absolute magnitudes
  scenario-sensitive (moderate)** (preprint §5).

Any draft that strengthens these beyond the evidence violates the repository's
honest-framing rule and must be rejected in review.

## 1. Motivation

_[fill]_ Why replayable, audit-native Graph-RAG matters: EU AI Act Articles
10/12/19 (in force 2026-08-02) presuppose an audit instrument that did not
exist; RAB is that instrument. Cross-reference `papers/rab-preprint/main.pdf`
§1 and README "Why this exists".

## 2. Architecture (high level)

_[fill]_ 6-stage pipeline (security → routing → hybrid retrieval → graph →
reasoning → output filter) + Layer-4 lifecycle store + `reconstruct_graph_at(t)`.
Reuse README "Architecture" + `docs/ARCHITECTURE.md`. One paragraph + the
existing mermaid diagram; this report is about *evidence*, not design.

## 3. Experimental setup (complete reproducibility spec)

_[fill — mostly transclude]_ Pull verbatim from `benchmarks/REPRODUCIBILITY.md`:
software/model versions, hyperparameters, determinism tiers, hardware
fingerprint, dataset subsets, seeds. State the one-command path
(`bash benchmarks/run_all.sh`).

## 4. Benchmarks

### 4.1 RAB v0.1.1 — Replayable-Audit Benchmark
_[fill]_ AC / RF / PC definitions; 4-SUT design; mapping to Art. 10/12/19.
Source: `eval/rab/SPEC-v0.1.md`, `papers/rab-preprint/main.pdf`.

### 4.2 LRB v0.2.x — Lifecycle Retrieval Benchmark
_[fill]_ Temporal validity scoring; S1/S2/S3; V/N/J SUTs; 7 deterministic axes.
Source: `papers/lrb-preprint/main.pdf`.

### 4.3 RAGAS (sibling cross-check)
_[fill]_ 3-row fixture; band semantics; explicitly secondary. Source:
`eval/ragas/`, `docs/evaluation/v0.5-evaluation-coverage-mapping.md`.

### 4.4 (Out of scope) HotpotQA / LongFact / MuSiQue
_[fill]_ State plainly: not part of v1 reproducibility claims. MuSiQue measured
null/parity; HotpotQA/LongFact not integrated. Deferred to a future
measurement cycle, not packaged as wins.

## 5. Results (baseline vs JAMES)

_[fill — transclude the committed tables]_

| Benchmark | Baseline | JAMES | Reproduce |
|---|---|---|---|
| RAB S1 (AC/RF/PC) | baseline0 = 0.275/0.000/0.000 | 1.000/1.000/1.000 | `rab_run.py --sut {baseline0,james}` |
| LRB S3 R@1 | Vanilla 0.502 / Naive 0.721 | **0.845** | `lrb_run_s3.py --scale publication` |
| RAGAS answer_relevancy | band [0.649, 0.757] | band [0.649, 0.757] | `run_ragas.py --check` |

## 6. Failure cases & limitations

_[fill]_ Be generous here — it is the credibility centre of gravity:
- MuSiQue/MultiHop-RAG null/parity (no JAMES-specific reasoning lift).
- Graph build is O(N²) (lifted into RAB as the RF-cost axis).
- LLM-tier nondeterminism → bands, not points.
- RAGAS fixture is 3 rows (small).

## 7. Threats to validity

_[fill]_ Single reference machine; Ollama nondeterminism; deterministic
scorers could be gameable (invite challenge — see `benchmarks/CHALLENGE.md`);
fixtures authored by the project (mitigated by committing them + deterministic
scoring + the reproduction program).

## 8. Reproduction instructions

_[fill]_ Transclude `benchmarks/README.md` "Reproduce ... under 15 minutes".

## 9. Archival

_[operator]_ Mint Zenodo DOI for this report; cross-link to the v0.4.4 data
archive DOI `10.5281/zenodo.20652679` and the two preprints. Maintain
release-to-report traceability (Phase 6).
