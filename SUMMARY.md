# PROJECT JAMES — Summary

A one-page, external-facing summary. The internal `CHANGELOG.md` is the per-PR audit trail (long by design, internal terminology); this doc is what an external evaluator should read first.

---

## What JAMES is

**Replayable RAG.** A local-first knowledge reasoning system where every claim is sourced, every reasoning step is audited, and the system's state at any point in time can be replayed byte-identically — even after destructive deletes propagate through the graph.

Built behind a human approval gate for self-evolution. 100% on-device by default.

---

## What you get (5 bullets)

1. **Sources-aware Graph-RAG**, not just vector RAG. Every retrieved fact carries `sources` (doc_id + weight + role), every relation walks an explicit ontology graph (`core/graph_engine.py`), and every reasoning step is logged in `audit_log` so a `trace_id` reproduces the exact decision path.
2. **Deterministic memory lifecycle.** T1 temporal validity + T7 supersede chain + T2 contradiction arbitration + T6 causality cascade — all four shipped, all LLM-free (Mem0 routes via LLM-judge; JAMES routes via a deterministic 4-rule decision tree). Source code: `core/lifecycle/{schema,supersede_chain,contradiction_arbiter,causality}.py`.
3. **`reconstruct_view_at(t)` — replayable history.** When facts are corrected, the old version isn't overwritten; it's marked `superseded_by` + `superseded_at`. Querying "what did the system know at time T?" returns the byte-identical state from that moment, even after destructive deletes (CASCADE) on unrelated facts.
4. **Self-evolution behind a human gate.** Patches the system can write to itself require an `approver_username` in the audit log before they auto-apply. The gate cannot be bypassed without a code change that itself requires review (`docs/ARCHITECTURE.md §5.5`).
5. **100% local + air-gap-ready.** Default LLM is gemma4:e4b via Ollama; default embedder is bge-m3 (multilingual); default vector store is ChromaDB on disk. No network call required for the core retrieval / reasoning loop. Optional cloud backends (Claude / Gemini / OpenAI) are flag-gated.

---

## What's measured

Direct copy of the README's "What's Verified" table (numbers from current `main`, not aspirational):

| Surface | Value |
|---|---|
| Test suite | **3290 tests** across 224 files, all green on PR CI |
| Release-gating invariants | 5 (T7 separation, `tests/test_t7_release_gating_invariants.py`) + 4 (T6 causality, `tests/test_t6_release_gating_invariants.py`) |
| QVT 3-axis baseline | path_recall **1.00** / graded_answer **0.58** / abstention_f1 **0.67** (median, N=3 paired reruns) — `eval/qvt/baseline_2a31b20.json` |
| STEP 7 regression | 17-query suite (v6) with gold_signals + abstention_truth + 5 path-annotated queries |
| Module size cap | 20 KB per `core/` file (CI-enforced, CLAUDE.md rule 5) |
| Default-off invariant | Every routing layer added since v0.3 (D5 / LEO / D1 / T2.D / T6 LLM) defaults OFF — byte-identical retrieval to v0.3.3 unless flag flipped |

### What is NOT yet headline-verified

A single-page ablation card showing **Graph-RAG vs flat RAG** on the same fixture. The infrastructure exists (`scripts/qvt_capture_baseline.py` + 18-cell ablation matrix design from QVT memo §5); the operator-run capture is the late-June deliverable. Until then the graph contribution is measurable via `graph_paths_count` per query in STEP 7 bench output but not summarized in one table.

---

## Differentiators (vs neighbouring categories)

| Category | What it provides | What JAMES adds |
|---|---|---|
| **Agentic RAG** (LangGraph / LlamaIndex agents) | iterative tool use over a query | + sourced graph + deterministic memory lifecycle + replayable history |
| **Mem0 / Letta / Cognee** (memory layers) | persistent facts across sessions | + LLM-free contradiction arbitration (deterministic 4-rule tree, audit-replay-safe) + supersede-chain replay primitive |
| **Vector-only RAG** | retrieval over embeddings | + explicit ontology graph + per-source confidence + CASCADE / EVENT lifecycle separation |
| **Self-evolution agents** (AutoGPT etc.) | autonomous code rewrite | + mandatory human approval gate (operator can't be bypassed without a separate code change) |

---

## Status + provenance

- Current release: **v0.4.1** (Layer 4 lifecycle + T6 causality cascade) — DOI `10.5281/zenodo.20411354` (v0.4.0 final mint; v0.4.1 DOI lands on release publish)
- License: MIT
- Entry: `README.md` → `docs/ARCHITECTURE.md` → `docs/PLATFORM_READINESS.md`
- Per-PR audit trail: `CHANGELOG.md` (long-form, internal terminology — start with the section header you care about and skip the rest)
- Per-release narrative: `docs/release_notes_v{0.3.0,0.3.1,0.4.0,0.4.1}.md`

---

## What to read next

| If you want to … | Start here |
|---|---|
| Run JAMES locally in 5 minutes | `README.beginner.ko.md` (Korean, beginner-friendly) |
| Read the architecture | `docs/ARCHITECTURE.md` |
| See the platform-readiness gate definitions | `docs/PLATFORM_READINESS.md` |
| Reproduce a verified number from "What's measured" | the right column of the table above; commands work as-typed |
| Audit a PR's quality delta | `.github/PULL_REQUEST_TEMPLATE.md` (Quality Delta Card section) |
| Audit the contradiction arbitration logic | `core/lifecycle/contradiction_arbiter.py` (~10 KB pure function, 17 contract tests) |
