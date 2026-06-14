# LinkedIn + X (English) — RAB + LRB launch posts

> Channel: LinkedIn (long-form) + X / Twitter (short + thread).
> Topic: the two pre-registered deterministic benchmarks shipped with
> JAMES — **RAB** (Replayable-Audit Benchmark) and **LRB** (Lifecycle
> Retrieval Benchmark).
> Facts source of truth: `reports/promo-assets/oneliner.md` (v0.4.4 base).
> Channel-separation discipline: these are *signal* posts that point to
> the repo + preprints; do not duplicate the full devto/HN body here.

---

## Core facts (backing every line below)

| Surface | Value |
|---|---|
| Version | v0.4.4 (2026-06-12) |
| DOI | 10.5281/zenodo.20652679 |
| Preprints | RAB 10pg + LRB 11pg (`papers/`) |
| RAB headline | AC/RF/PC = 1.000/1.000/1.000 (JAMES) vs 0.275/0/0 (Baseline-0, vanilla default-logging) on scenario-S1 |
| RAB metrics | Audit Completeness (AC), Replay Fidelity (RF), Provenance Coverage (PC) |
| EU AI Act anchor | RAB's 3 metrics map verbatim to Articles 10, 12, 19 (apply from 2026-08-02 per Art. 113) |
| LRB headline | R@1 ordering V<N<J preserved across 4 model families × 4 scale points (12.5× scale span) |
| LRB S3 publication | V/N/J R@1 = 0.502 / 0.721 / 0.845 |
| License | MIT · OpenSSF Best Practices passing |
| Repo | https://github.com/Hashevolution/James-RAG-Evol |

---

## LinkedIn (long-form)

Most RAG systems can't answer two questions a regulator will ask:
"show me the exact record of how this answer was produced" and
"reconstruct what your system knew at the time it answered."

So I shipped two pre-registered, deterministic benchmarks alongside
JAMES — my local-first, audit-native Graph-RAG platform — that measure
exactly those two things, instead of leaving them to a vibe check.

🔹 RAB — Replayable-Audit Benchmark
Three deterministic metrics: Audit Completeness, Replay Fidelity, and
Provenance Coverage. They map *verbatim* to EU AI Act Articles 10, 12,
and 19 — the record-keeping obligations that apply from 2026-08-02.
On scenario S1, JAMES scores 1.000 / 1.000 / 1.000. A vanilla
default-logging baseline scores 0.275 / 0 / 0. The gap is the point:
"we have logs" is not the same as "we can replay the decision."

🔹 LRB — Lifecycle Retrieval Benchmark
RAG facts go stale. LRB measures whether a system retrieves the answer
that was *valid at the queried point in time* rather than the latest
one. Across 4 model families and 4 scale points (a 12.5× span), the
R@1 ordering Vanilla < Naive-supersede < JAMES holds — time-aware
retrieval beats both naive overwrite and no time-handling at every
scale. At publication scale: 0.502 / 0.721 / 0.845.

Both are reproducible, both have a preprint (RAB 10pg, LRB 11pg), and
the whole thing runs locally on Ollama — no cloud LLM account required.
MIT-licensed, OpenSSF Best Practices passing.

The honest framing: these are benchmarks, not a victory lap. They exist
so the next person can run them, disagree, and beat the numbers.

📄 Preprints + DOI: 10.5281/zenodo.20652679
💻 Code (MIT): https://github.com/Hashevolution/James-RAG-Evol

#RAG #LLM #EUAIAct #AIGovernance #OpenSource #GraphRAG

---

## X / Twitter — single tweet (standalone)

Shipped two pre-registered, deterministic benchmarks with JAMES, my
local-first Graph-RAG:

▸ RAB — audit replayability, 3 metrics mapped verbatim to EU AI Act
Art. 10/12/19. JAMES 1.0/1.0/1.0 vs vanilla logging 0.275/0/0.
▸ LRB — time-travel retrieval. R@1 V<N<J across 4 models × 4 scales.

Local. MIT. Preprints + DOI:
https://github.com/Hashevolution/James-RAG-Evol

---

## X / Twitter — thread (5 posts)

**1/**
Two questions a regulator will ask your RAG system:
"replay how this answer was produced" and "what did you know at the
time you answered it?"

Most can't answer either. So I shipped two deterministic benchmarks
that measure exactly those — with JAMES, local-first Graph-RAG. 🧵

**2/**
RAB — Replayable-Audit Benchmark.

3 metrics: Audit Completeness, Replay Fidelity, Provenance Coverage.
They map *verbatim* to EU AI Act Articles 10/12/19 (in force
2026-08-02).

JAMES: 1.000 / 1.000 / 1.000
Vanilla default-logging: 0.275 / 0 / 0

"We have logs" ≠ "we can replay it."

**3/**
LRB — Lifecycle Retrieval Benchmark.

RAG facts go stale. LRB tests whether you retrieve the fact that was
valid *at the queried time*, not just the newest one.

R@1 ordering Vanilla < Naive-supersede < JAMES holds across 4 model
families × 4 scale points (12.5× span). Publication scale:
0.502 / 0.721 / 0.845.

**4/**
Both are pre-registered and reproducible. Both have a preprint
(RAB 10pg, LRB 11pg). It all runs locally on Ollama — no cloud LLM
account.

MIT-licensed. OpenSSF Best Practices passing.

**5/**
Honest framing: these are benchmarks, not a trophy. They exist so the
next person can run them, disagree, and beat the numbers.

📄 DOI: 10.5281/zenodo.20652679
💻 https://github.com/Hashevolution/James-RAG-Evol

---

## Posting notes

- Keep channel separation: if a Korean GeekNews/X thread runs the same
  week, these English posts stay signal-only (no body duplication).
- After posting, record the URLs in `launch-tracker.md` "Social posts".
- The single tweet and the thread are alternatives — pick one per
  account, don't run both back to back.
- V/N/J = Vanilla / Naive-supersede / JAMES (LRB system labels).
