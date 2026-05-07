# JAMES — Evaluation Results

This page tracks regression metrics across the v0.2 → v1.0 hardening cycle. Numbers are committed only when they reflect a representative-hardware run on a tagged release branch — drift between commits is expected (LLM nondeterminism); committing every nightly run would bury signal under noise.

Both suites are gated by `--check` mode of their runner. PRs touching `core/retrieval`, `core/graph`, or `core/reasoning` paste the relevant suite numbers in the description (CLAUDE.md rule 2).

## Hardware fingerprint (committed alongside numbers)

| Field | Value |
|---|---|
| OS | Windows 11 Home 10.0.26200 |
| CPU | AMD Ryzen 7 7700 8-Core |
| RAM | 32 GB |
| GPU | NVIDIA GeForce RTX 4070 SUPER (12 GB VRAM) |
| Ollama LLM model | `gemma4:e4b` (`config.GEMMA_MODEL` default) |
| Embedding model | `models/miniLM` (paraphrase-multilingual-MiniLM-L12-v2) |

## STEP 7 — internal regression baseline

12 hand-crafted queries on the project's own wiki entities. Locked by `scripts/bench.py --suite=step7 --check` against `eval/regression/step7_baseline.json` (PR #52 / Issue #45). Baseline derived from 5 runs spanning the v0.2 reasoning split (PRs #35 / #37 / #38 / #39).

| Metric | v0.2 baseline | Tolerance | Source |
|---|---|---|---|
| Total elapsed (12 queries) | 298.9 s — 413.7 s (mean 377.7 s) | ± 30 % | `step7_baseline.json::totals` |
| q11 security block answer bytes | 26 (byte-identical) | exact | `step7_baseline.json::q11.answer_len_exact` |
| q3 graph_paths | 0 (no Anthropic↔Claude edge yet) | ± 2 | `step7_baseline.json::q3` |
| q11 graph_paths | 0 (security block before graph) | exact | `step7_baseline.json::q11` |
| q1 / q4 / q6 / q8 / q10 graph_paths bands | 8 — 52 (per-query), see baseline | ± 2 | `step7_baseline.json::queries` |

Re-run: `python scripts/bench.py --suite=step7` (live JAMES server at `127.0.0.1:8000`, then `--check` to gate against baseline).

q12 is marked `flaky` in the baseline (5-run history: 1 OK / 4 timeout) and excluded from `--check`. Investigation tracked outside this page.

## RAGAS — third-party retrieval / generation metrics

Public-knowledge fixture (`eval/ragas/fixture_v0.2.json`, 3 rows). Harness landed in PR #51 (Issue #46 phase 1); baseline + `--check` drift detection in PR #64 (Issue #46 phase 2). Baseline derived from 2 representative-hardware runs on the fingerprint above.

| Metric | v0.2 baseline | Tolerance | Description |
|---|---|---|---|
| `context_precision` | 1.000 (min) — 1.000 (max) | ± 0.10 | Of the retrieved contexts, what fraction are relevant to the question? (embedding-based) |
| `context_recall` | 1.000 — 1.000 | ± 0.10 | Of the information needed to answer, what fraction is present in retrieved contexts? (embedding-based) |
| `faithfulness` | 1.000 — 1.000 | ± 0.15 | Of the claims in the response, what fraction are grounded in retrieved contexts? (LLM-judge) |
| `answer_relevancy` | 0.649 — 0.757 | ± 0.15 | How directly does the response address the user's question? (LLM-judge) |

Total run elapsed: 93.5 s — 95.5 s (mean 94.5 s).

Re-run: `python eval/ragas/run_ragas.py` (Ollama must be running at `127.0.0.1:11434`); `--check` to gate, `--update-baseline` to widen the band on intentional scope changes.

## Reproducibility note

RAGAS uses an LLM as judge (faithfulness, answer_relevancy especially) and embeddings (context_precision, context_recall). Judge metrics are nondeterministic — the `answer_relevancy` band already spans 0.649 → 0.757 across 2 same-machine runs, and the dev-machine reference number from PR #51 (0.678) sits inside that band. The baseline is therefore a band, not a point. Embedding metrics tighten quickly: both `context_*` are 1.000 across all runs because the fixture is small and unambiguous. PRs that drift `answer_relevancy` past `[0.649, 0.757] ± 0.15` (i.e. outside [0.499, 0.907]) should investigate before merging.

## Out of scope (deferred)

- Live `/query/` integration for the RAGAS harness — Issue #46 phase 3, depends on a runner reusing the `bench.py` shape.
- LegalBench subset — separate issue, after phase 3.
- BEIR / MS MARCO — too large for laptop, defer to v0.3.
- KLUE-RC (Korean public benchmark) — no clean public option yet, watch for v0.4.
- Domain-specific eval suites (legal, food, etc.) — those arrive with their respective domain packs in v0.3+.
- CI enforcement of the PR-contract rule — separate Axis 2-C issue (CLAUDE.md rule 2 is human-enforced today).
