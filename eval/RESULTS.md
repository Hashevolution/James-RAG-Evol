# JAMES — Evaluation Results

This page tracks regression metrics across the v0.2 → v1.0 hardening cycle. Numbers are committed only when they reflect a representative-hardware run on a tagged release branch — drift between commits is expected (LLM nondeterminism); committing every nightly run would bury signal under noise.

## Hardware fingerprint (committed alongside numbers)

| Field | Value |
|---|---|
| OS | tbd |
| RAM | tbd |
| GPU | tbd |
| Ollama LLM model | tbd (`config.GEMMA_MODEL`, default `gemma4:e4b`) |
| Embedding model | `models/miniLM` (paraphrase-multilingual-MiniLM-L12-v2) |

## STEP 7 — internal regression baseline

12 hand-crafted queries on the project's own wiki entities. Locked in PR #TBD (Issue #45).

| Metric | v0.2 baseline | Current | Δ |
|---|---|---|---|
| Total elapsed (12 queries) | tbd | — | — |
| q11 security block bytes | tbd | — | — |
| Median graph_paths | tbd | — | — |

Re-run: `python scripts/step7_query_test.py` (after `python server_llmwiki.py`).

## RAGAS — third-party retrieval / generation metrics

Public-knowledge fixture (`eval/ragas/fixture_v0.2.json`, 3 rows). Harness landed in PR #TBD (Issue #46). The first run on representative hardware after merge becomes the v0.2 baseline.

| Metric | v0.2 baseline | Description |
|---|---|---|
| `context_precision` | tbd | Of the retrieved contexts, what fraction are relevant to the question? |
| `context_recall` | tbd | Of the information needed to answer, what fraction is present in retrieved contexts? |
| `faithfulness` | tbd | Of the claims in the response, what fraction are grounded in retrieved contexts? |
| `answer_relevancy` | tbd | How directly does the response address the user's question? |

Re-run: `python eval/ragas/run_ragas.py` (Ollama must be running at `127.0.0.1:11434`).

## Reproducibility note

RAGAS uses an LLM as judge (faithfulness, answer_relevancy especially) and embeddings (context_precision, context_recall). Both are nondeterministic — expect ±10% drift across machines and runs. The baseline is a band, not a point. PRs that drift > 15% on any metric should investigate.

## Out of scope (deferred)

- LegalBench subset — separate issue, after #46
- BEIR / MS MARCO — too large for laptop, defer to v0.3
- KLUE-RC (Korean public benchmark) — no clean public option yet, watch for v0.4
- Domain-specific eval suites (legal, food, etc.) — those arrive with their respective domain packs in v0.3+
