# JAMES Benchmarks — Reproducibility Package

This directory is the **single entry point** for independently reproducing
PROJECT JAMES's published benchmark numbers. It does not introduce new
measurements; it wraps the committed, pre-registered runners
(`scripts/research/rab_run.py`, `scripts/research/lrb_run_phase_b.py`,
`eval/ragas/run_ragas.py`) behind one command and discloses the exact
environment they were captured in.

> **What is reproducible here, stated honestly.**
> The headline reproducible numbers are **RAB** (audit-log replayability)
> and **LRB** (temporal/lifecycle retrieval). Both are scored by
> **deterministic scorers with no LLM in the path**, so they are
> byte-identical across machines. They are *not* a generic "Graph-RAG
> beats vector RAG on reasoning" claim — on open multi-hop reasoning
> (MuSiQue/MultiHop-RAG) the project's own measured result is a
> **null/parity** finding, documented in
> `docs/handovers/v0.4-track-c-musique-improvement-loop-FINAL-2026-06-12.md`.
> RAB's SPEC §6.5 explicitly disclaims a "JAMES-wins" framing; the
> contribution is the *benchmark and the gap structure*, not a leaderboard win.

---

## Reproduce the benchmark results in under 15 minutes

**Prerequisites:** Python ≥ 3.11, `git`, and a bash shell. No GPU, no
Ollama, and no network are needed for the deterministic core tier.

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol.git
cd James-RAG-Evol
python -m pip install -r requirements.txt

bash benchmarks/run_all.sh
```

That's the whole core path. It runs:

1. **RAB v0.1.1** — 3 systems-under-test (reference / baseline0 / james) on
   scenario S1. Deterministic, no LLM, ~5 s each.
2. **LRB Phase B** — S1 + S2 time-travel retrieval, token-mode. Deterministic,
   no LLM, ~30 s.

Total wall time for the core tier is **1–2 minutes** on a laptop.

### Optional tiers

```bash
bash benchmarks/run_all.sh --full       # + LRB S3 publication-scale (1000 docs), ~3-6 min, still no LLM
bash benchmarks/run_all.sh --with-llm   # + RAGAS suite — needs Ollama (gemma4:e4b) + server, ~90 min, band-checked
```

---

## Expected output

The core tier must print these numbers (deterministic — any deviation is a
real finding worth an issue):

### RAB v0.1.1 — scenario S1 (AC / RF / PC)

| SUT | Audit Completeness | Replay Fidelity | Provenance Coverage |
|---|---|---|---|
| `reference` | 1.000 | 1.000 | 1.000 |
| `baseline0` (vanilla default logging) | **0.275** | **0.000** | **0.000** |
| `james` (audit-native) | 1.000 | 1.000 | 1.000 |

The point is the **gap** between an audit-native runtime and a default-logging
one — the three metrics operationalise EU AI Act Articles 10 / 12 / 19
(in force 2026-08-02).

### LRB Phase B — S2 time-travel (R@1, V / N / J)

The S2 gap table must show `R@1` strictly ordered **Vanilla < Naive < JAMES**,
with the JAMES − Naive gap above +0.10. Publication-scale (`--full`) R@1
reference values:

| SUT | R@1 (S3 publication, 1000 docs) |
|---|---|
| Vanilla (append-only) | 0.502 |
| Naive-supersede | 0.721 |
| **JAMES (validity-window)** | **0.845** |

Honest framing (locked in the preprint): the **pattern + gap are
scale-robust**; the **absolute magnitudes are scenario-sensitive**.

### RAGAS (`--with-llm` only)

Band-checked, not point-identical. A run landing inside the committed
tolerance bands (`eval/ragas/baseline.json`: judge ±0.15, embedding ±0.10) is
a confirmed reproduction. `context_precision`/`context_recall` should be
≈ 1.0; `answer_relevancy` should land in **[0.649, 0.757]**.

---

## Files in this package

| File | Purpose |
|---|---|
| `run_all.sh` | One-command orchestrator (core / `--full` / `--with-llm`) |
| `config.yaml` | Disclosure: what is scored, reference numbers, environment fingerprint |
| `seeds.txt` | Random-seed / determinism posture |
| `REPRODUCIBILITY.md` | Full deterministic-evaluation disclosure (Phase 2) |
| `REPRODUCTION_PROGRAM.md` | How to submit an independent reproduction (Phase 3) |
| `CHALLENGE.md` | Benchmark challenge — beat JAMES under identical constraints (Phase 7) |

## What this package deliberately does NOT claim

- It does **not** ship HotpotQA / LongFact subsets. The project does not
  currently have validated, JAMES-specific gains on those, and inventing a
  "James wins" table for them would violate the project's honest-framing rule.
  Adding new external benchmarks is scoped as a **separate future measurement
  cycle**, not a packaging task.
- It does **not** claim RAGAS as a headline. RAGAS here is a 3-row sibling
  cross-check with judge-variance bands; see
  `docs/evaluation/v0.5-evaluation-coverage-mapping.md` for the full mapping
  of standard RAG metrics to what the project measures (and deliberately
  doesn't).
