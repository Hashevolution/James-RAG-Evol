---
title: RAB — Replayable-Audit Benchmark
emoji: 🧾
colorFrom: indigo
colorTo: gray
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: cc-by-4.0
tags:
  - rag
  - audit
  - provenance
  - eu-ai-act
  - benchmark
---

# RAB — Replayable-Audit Benchmark (interactive demo)

**Can you tell what a RAG / agent system did, replay its past state, and
trace every cited answer — from its exported audit log alone?** RAB
measures *auditability*, not answer quality, with three deterministic
(LLM-judge-free) metrics anchored on **EU AI Act Art. 10 / 12 / 19**:

- **AC — Audit Completeness**: did every decision-bearing action land in the log, correctly typed?
- **RF — Replay Fidelity**: can past state be reconstructed from the log only?
- **PC — Provenance Coverage**: does every cited answer chain back to where the content entered?

> ⚠️ RAB does **not** certify regulatory compliance — it operationalises
> Art. 10/12/19 *concepts* into measurable proxies.

## What this Space shows

Four views over a **frozen, re-verifiable scenario-S1 run** (spec
v0.1.1):

1. **Gap structure** — AC/RF/PC across four systems. The RAB headline is
   the *gap* (vanilla RAG → +tracing → audit-native), not any one score.
2. **Audit log** — JAMES's JSONL log, filterable by canonical event type.
3. **Time-travel replay** — per-checkpoint RF, reconstructed from the log only.
4. **Provenance** — trace an answer's citations back to their origin event.

## Honesty / scope

This Space **runs no model and makes no network call** — it reads
pre-computed RAB artifacts bundled under `data/`. That mirrors the
benchmark's point (and JAMES's local-first posture): the numbers fall
out of the exported audit log deterministically. To run the full
benchmark against your own system, use the driver + scorer in the
[source repo](https://github.com/Hashevolution/James-RAG-Evol)
(`eval/rab/`).

## Links

- Spec: `eval/rab/SPEC-v0.1.md` (FROZEN v0.1.1)
- Dataset (scenario fixtures): `JamesLabs/rab-replayable-audit-benchmark`
- Source: https://github.com/Hashevolution/James-RAG-Evol
- Archive DOI: https://doi.org/10.5281/zenodo.20625533
- License: CC-BY-4.0 (artifacts) · MIT (app code)
