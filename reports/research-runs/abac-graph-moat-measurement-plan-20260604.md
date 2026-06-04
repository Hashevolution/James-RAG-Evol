# Access-Controlled Graph-RAG — Moat Measurement Plan (Tier 1)

> **Status**: PLAN / decision note (2026-06-04)
> **Branch**: `claude/graph-rag-abac-benchmark-qRBnr`
> **Frame**: Direction-(b) — *platform moat empirical proof first, paper is a
> by-product*. Applies the Direction α lesson (`feedback_evidence_grounded_
> validity_check`): **prove the moat claim, don't assume it.**
> **Mode**: mother-platform hardening. Access control is a *horizontal* moat
> (aligned with the v0.5 "enterprise internal knowledge ontology" candidate),
> NOT a vertical domain fork. No domain features added.

---

## 0. Why this note exists

We evaluated a candidate research direction — *"access-control-aware
Graph-RAG security–utility tradeoff benchmark"* — through a 5-angle academic
+ industry literature sweep and a full read of the two closest prior works.
This note records (a) the novelty verdict, (b) the GO decision under the
(b) framing, and (c) a grounded Tier-1 measurement plan against JAMES's
*actual, current* code.

---

## 1. Novelty verdict (cold)

**Grade: ★★★☆☆ — real but moderate, empirical-measurement novelty, NOT a
conceptual breakthrough.** The *phenomena* are all known; the *measurement
in this system + a released benchmark + the differential/recovery axes* are
what is open.

What is **dead** (do not claim):
- "Access-control ↔ utility tradeoff" observation — owned by **SNU
  Permission-Aware RAG** (IEEE Access 2025, doc 11224764): measures
  Permission-Coverage × EM/F1 on HotpotQA, incl. an AWS-ABAC bucket.
- "Strict access → lower utility" — near-tautological.
- "Inference can defeat access control" — the **inference problem**
  (Denning 1980s; Farkas & Jajodia, *SIGKDD Explor.* 2002) — relational/
  logical, decades old.
- "Graph-RAG vs plain-RAG ablation is missing" — false as of 2026
  (GraphRAG-Bench / ICLR'26; "Unbiased Eval" 2506.06331 shows gains were
  *overstated*).
- "Super-linear collapse from critical-node removal" — **Albert/Jeong/
  Barabási, *Nature* 2000** (percolation; targeted-vs-random attack
  tolerance). Concede the mechanism.

What **survives** (the only defensible unit):
- The **empirical instantiation of the inference problem in LLM Graph-RAG**:
  even when access filtering is *correctly enforced*, multi-hop reasoning
  over the *permitted* subgraph reconstructs the content/existence of
  *forbidden* nodes — measured, with a leak-controlled fixture, plus the
  **differential** (graph vs flat) and **recovery** (graceful degradation
  under partial permissions) axes.

### Named foils (must cite + differentiate)
| Work | What it does | Why it does NOT close our gap |
|---|---|---|
| **VAULT** (Stäbler et al., eKNOW 2025) | GraphRAG (MS-GraphRAG/Leiden) + RBAC (2 roles), 4 access tiers, 16 LLMs, quality-by-tier (Table I) | RBAC only; **post-traversal node filter, not per-hop**; **never measures inference leakage** — asserts "security boundary prevents unauthorized disclosure" via one USER1-can't-see-CFO example; tiny eval (20 Q, 2 docs, Apple SEC = LLM-memorized → invalid fixture); no recovery; low-tier venue |
| **SNU Permission-Aware RAG** (IEEE Access 2025) | IAM filtering, PermCov×F1, multi-hop QA | No graph (FAISS only); doc-level post-filter; no leakage; no recovery; in-paper eval, not released benchmark |
| **GRASP** (arXiv 2602.06495) | Subgraph **reconstruction** attack on GraphRAG | Reconstructs the **retrieved** subgraph (whole-KG-private threat); we reconstruct the **excluded** subgraph from the **retained** one under correct ACL. One-sentence differentiator — must be crisp |

### Residual novelty risks (honest)
1. Outcome of "it leaks" is semi-predictable → **the spine must be the
   differential (graph vs flat) + recovery, not the bare leak.**
2. Scoop window ~6–12 mo (GRASP / robust-GraphRAG authors are adjacent).
3. Validity: requires a **leak-controlled synthetic fixture** or the result
   is a parametric-knowledge artifact (the exact VAULT/Apple-SEC mistake;
   cf. SNU user-1 scoring F1 0.31 at PermCov 0%).

---

## 2. GO decision

**GO**, under framing (b). The deliverable is **proof (or refutation) of
JAMES's existing moat claim**, with a reusable benchmark as the artifact.
Academic publishability is a secondary, opportunistic output.

---

## 3. Grounded reality — what JAMES *actually* has (code audit, 2026-06-04)

| Capability | File / symbol | Reality |
|---|---|---|
| Policy primitive | `core/policy_engine.py` `can_retrieve` / `can_walk` | ✅ exists, wired into retrieval |
| ABAC check | `core/security_layer/_abac.py` `check_access` | ⚠️ **ordinal MLS**, not multi-attribute ABAC: `ROLE_LEVEL[role] >= SENSITIVITY_LEVEL[sensitivity]` |
| Graph-stage gate | `_abac.py` `filter_graph_by_abac` → `can_walk` | ⚠️ **post-traversal list filter**, and **no caller found in `core/reasoning`** (only `SecurityLayer.filter_graph` wrapper + tests) |
| Graph traversal | `core/graph_engine.py` `expand_dynamic` / inner `dfs` | ⚠️ **no inline access check** — DFS visits all nodes; gating (if any) is downstream |
| Output defense | `pipeline.py:290` `filter_answer_by_role` + `mask_sensitive` | ✅ wired in live pipeline (entity-name + keyword/PII masking) |
| Cross-stage invariant | `_abac.py` `cross_stage_abac_verify` (Vector→Graph→Output) | exists; wiring into live loop TBD |
| Public claim | `reports/promo-assets/devto-data-exfiltration.md:164` | *"every hop applies can_walk … a confidential entity can't be a hop destination … the reasoning path is access-controlled by construction"* |

**Key tension to resolve first:** the public claim says *per-hop, by
construction*; the code suggests *post-traversal filter (possibly not wired
in the live loop), with output masking as the primary live defense.* This
gap is itself a mother-hardening finding.

### Honest scope split
| | State | Handling |
|---|---|---|
| Per-hop / post-traversal **gating** (`can_walk`) | exists (wiring TBD) | **Tier 1: measure** |
| "ABAC" = ordinal sensitivity level | exists | name it **level-based**, not multi-attribute |
| Multi-attribute ABAC (subject/resource/env) | ❌ absent | Tier 2 (gated on Tier-1 value) |
| Permission **propagation** along edges (relational/inherited) | ❌ absent (per-node independent) | Tier 2 (gated) |

---

## 4. Tier-1 measurement design

### Measurement 0 — Enforcement-point audit (prerequisite)
Pin down *where* graph access control actually happens in the live
`ReasoningEngine.query` path: per-hop in DFS, post-traversal filter, or
output masking only. Output: a precise enforcement diagram + the
claim-vs-reality delta. **Without this, axes 1/3 are uninterpretable.**

### Axis 1 — Enforcement correctness (security)
Does the gate (wherever it is) actually exclude unauthorized
nodes/docs? FP/FN against ground-truth permissions, swept over access
strictness (≥3 ordered clearance levels). Reuses `cross_stage_abac_verify`
semantics.

### Axis 2 — Utility cost + the differential (SPINE)
Quality drop as strictness increases. **Headline comparison:** same
removed node-set applied to (a) graph traversal vs (b) flat/vector
retrieval — is the degradation slope steeper for graph (chokepoint) or
flatter (redundant paths)? Is loss concentrated at high-betweenness nodes?
Metrics via existing `eval/qvt` (Graded Answer / Path Recall) + bench
(`scripts/bench.py --suite=step7`).

### Axis 3 — Leakage despite the gate (HEADLINE)
Even when a confidential entity is correctly gated/masked, can the LLM
**reconstruct its content or existence** from permitted neighbors via
multi-hop reasoning? This tests JAMES's full **defense-in-depth**
(`can_walk` gate + `cross_stage_abac_verify` + `filter_answer_by_role`
masking) — a strictly stronger test than VAULT's single gate. A leak that
survives all three layers **refutes "access-controlled by construction"**
→ platform must-fix *and* the novel contribution.
- Metric: *Forbidden-Entity Reconstruction Rate* (FERR) — fraction of
  gated entities whose key facts are recoverable from the answer/permitted
  context, scored against fixture ground truth, with a parametric-baseline
  subtraction (see §5).

### Axis 4 — Recovery (graceful degradation)
Under partial permissions, how much answer quality is recoverable by
re-routing through *alternative permitted* evidence paths? Defines a
*Recovery Rate* the prior art (VAULT/SNU) leaves as future work.

---

## 5. Validity — leak-controlled fixture (non-negotiable)
- **Synthetic knowledge graph** with fabricated entities/relations **outside
  any LLM training distribution** (no Apple-SEC-style memorized facts).
- Known ground-truth multi-hop paths; explicit sensitivity labels per node.
- **Parametric baseline subtraction:** run every probe with the graph
  *absent* to measure what the bare LLM guesses; FERR counts only
  reconstruction *above* that baseline. (Directly fixes the VAULT Apple-SEC
  and SNU user-1 artifacts. Per `feedback_fixture_fitness_before_verdict`.)
- Both outcomes are valuable: gate holds → moat *proven*; gate leaks →
  must-fix *found*. (The Direction-α anti-pattern, inverted.)

---

## 6. Compliance (CLAUDE.md)
- **No domain fork**: access control is horizontal. ✅
- **PR gate**: measurement harness / fixture / benchmark = measurement-side
  → `Quality delta: exempt (label: code/fix)` (the PR is the oracle/baseline
  itself). A Quality Delta Card is required only if `core/graph` /
  `core/retrieval` / `core/reasoning` *logic* changes (e.g., wiring the
  per-hop gate as a Tier-2 fix).
- **20 KB module gate**: new code under `eval/abac_bench/` +
  `scripts/research/`; keep `core/` files split.
- **Artifacts**: decision notes in `reports/research-runs/`; reproducible
  regression in `eval/`.

## 7. Next steps
1. **Measurement 0** — enforcement-point audit (read `ReasoningEngine.query`
   path end-to-end; produce the enforcement diagram + claim-vs-reality
   delta).
2. Build the **leak-controlled synthetic graph fixture** (`eval/abac_bench/
   fixtures/`).
3. Implement the **Axis-3 FERR probe** (headline) with parametric-baseline
   subtraction; then Axis-2 differential, Axis-4 recovery.
4. Report to `reports/research-runs/`; fold reusable checks into `eval/`.
