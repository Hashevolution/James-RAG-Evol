# Deterministic Evaluation Disclosure (Phase 2)

> Purpose: eliminate ambiguity about how the published numbers were produced,
> so different evaluators obtain substantially identical results. This is the
> full disclosure that `benchmarks/config.yaml` summarises.

## 1. Exact software / model versions

| Component | Value | Source of truth |
|---|---|---|
| Python | ≥ 3.11 | `pyproject.toml` |
| Dependencies | `requirements.txt` (loose) / `requirements_pinned.txt` (frozen v0.4.3) | repo root |
| Reasoning LLM | `gemma4:e4b` (Ollama) | `config.py`, `eval/ragas/baseline.json` fingerprint |
| Coding-mode LLM | `qwen2.5-coder:32b` | `config.py` |
| Embedding model | `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers) | `config.py` |
| Ollama endpoint | `http://localhost:11434` | `core/gemma_client/config.py` |
| Vector store | ChromaDB (embedded, persistent) | `core/vector_store.py` |
| Sparse retriever | `rank-bm25 ≥ 0.2.2` | `requirements.txt` |
| LLM decode temperature | `0.0` (greedy) | inference call sites |

**Important:** the LLM/embedding models above are **only** needed for the
LLM tier (`--with-llm`, and `--full` if you opt into the JAMES-engine RAB
mode). The **deterministic core tier needs none of them.**

## 2. Prompt templates, hyperparameters

Core retrieval/graph hyperparameters (HANDOVER.md §2 "핵심 LLM 설정"):

```
MAX_DEPTH=4              # Graph DFS depth cap
DFS_SCORE_THRESHOLD=0.05
DEPTH_DECAY=0.7
num_ctx=2048
temperature=0
Hybrid weights: Vector 0.60 / BM25 0.20 / keyword 0.20
```

Prompt templates live with the engine (`core/reasoning/`) and are exercised
only in the LLM tier. The deterministic benches do not call them.

## 3. Determinism tiers (read this before filing a variance report)

| Tier | Benchmarks | LLM? | Reproducibility |
|---|---|---|---|
| **Core** | RAB (all SUTs, no `--engine`); LRB Phase B + S3 token-mode | No | **Byte-identical** across machines. Pure functions over committed JSON fixtures. Runners print `fixture_sha` / `log_sha` so you can confirm you scored identical bytes. |
| **LLM** | RAGAS; LRB-S3 with `--engine james`; RAB `--engine` | Yes (Ollama) | **Band-based.** Local inference is not fully deterministic even at temp 0. Judge metrics reported as bands, not points. |

A result that differs in the **core tier** is a genuine finding — please open
an issue (it likely means a fixture or scorer changed). A result that differs
in the **LLM tier** but lands inside the documented band is a normal,
**confirmed** reproduction.

## 4. LLM-tier prerequisites (`--with-llm` / `--full james`)

```bash
# 1. Install + start Ollama (https://ollama.com), then:
ollama pull gemma4:e4b
ollama serve            # must be listening on :11434

# 2. (RAGAS path) start the JAMES server in another shell:
python server_llmwiki.py    # serves :8000

# 3. Run the LLM tier:
bash benchmarks/run_all.sh --with-llm
```

## 5. Random seeds

See `benchmarks/seeds.txt`. Summary: the core tier has **no RNG** (nothing to
seed); the LLM tier uses `temperature=0` plus numpy/sklearn seed 42 in test
fixtures, and reports bands for judge metrics.

## 6. Hardware specification (reference capture)

The committed reference numbers were captured on:

```
OS:        Windows 11 Home 10.0.26200
CPU:       AMD Ryzen 7 7700 (8-core)
RAM:       32 GB
GPU:       NVIDIA GeForce RTX 4070 SUPER (12 GB VRAM)
```

Hardware affects **wall-clock time only**, never the core-tier metric values.
RAGAS `elapsed_*` fields are informational and explicitly **not** gated by
`--check`.

## 7. Dataset subsets used

| Benchmark | Fixture (committed) | Size |
|---|---|---|
| RAB | `eval/rab/scenarios/s1_lifecycle_small.json`, `s2_lifecycle_large.json` | frozen v0.1.1 |
| LRB | `eval/external/lrb/` scenarios S1/S2/S3 (S3 built by `build_lrb_scenario_s3.py`) | S3 publication = 1000 docs / ~5.6k events / 1000 queries |
| RAGAS | `eval/ragas/fixture_v0.2.json` | 3 rows (small by design — sibling cross-check, not headline) |

All scored fixtures are committed to git. There is **no hidden
preprocessing**: the core-tier runners read the committed JSON directly.
Datasets that require a download (MuSiQue / 2Wiki / RGB / ALCE for the
*separate* external-benchmark cycle) are **out of scope** for this package and
are not part of the reproduction core.

## 8. Success criterion

> Different users obtain substantially identical results.

- **Core tier:** identical to the digit shown in `benchmarks/README.md`
  "Expected output". Any deviation → issue.
- **LLM tier:** inside the bands in `eval/ragas/baseline.json`.
