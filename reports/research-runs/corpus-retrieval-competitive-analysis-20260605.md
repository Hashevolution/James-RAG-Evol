# JAMES Corpus Retrieval — External Competitive Analysis (2026-06-05)

> **Trigger**: A local test showed JAMES corpus retrieval
> (bge-m3 + Chroma + hybrid indexing) clearly above a paper's
> LlamaIndex (voyage-02 / ada-002) retrieval baseline. Question:
> *where does JAMES's development value actually sit in the recent
> (2025–2026) RAG landscape?*
>
> **Method**: external web survey (MTEB / RAG-eval / GraphRAG /
> security-RAG literature, June 2026) + internal codebase
> verification against actual design. **Honest-framing rule applied**
> (`memory/feedback_finding_size_honest_framing.md`): this is an
> analysis report, not a publishable superiority claim.
>
> **Label**: `docs` (no `core/` change → Quality Delta Card exempt).

---

## 0. TL;DR

1. **"Beating the paper's LlamaIndex + voyage-02/ada-002 baseline" is a
   pass/check, not a competitive advantage.** ada-002 (deprecated
   2025-10-03) and voyage-02 are 2022–2023 vintage; bge-m3 is a 2024
   off-the-shelf open model JAMES did **not** train. The win mostly
   reflects "current commodity stack > 2–3 year-old commodity stack"
   plus JAMES's system-layer additions.
2. **The embedding/vector substrate is commoditised.** 2025–2026 MTEB
   SOTA rotates quarterly (Gemini 68.3 > Cohere 65.2 > OpenAI-3-large
   64.6 > **bge-m3 63.0** > ada-002 ~61.0). JAMES sits at the *current
   commodity frontier*, not at SOTA.
3. **The field's value frontier has moved to the system layer** —
   agentic RAG, GraphRAG, context engineering, provenance/governance,
   and quality gates — which is **exactly where JAMES's real
   development value lives** and is design-verified below.
4. **Of JAMES's 7 system-layer capabilities, 4 have strong external
   benchmarks (crowded red-ocean), 1 is framework-comparable only, and
   the 2 most differentiated (ABAC, replay/audit) have essentially no
   public benchmark** — simultaneously a moat and a "cannot prove with
   a number" risk.

---

## 1. What the measurement actually beat

The codebase has **no** direct LlamaIndex/voyage-02/ada-002 comparison
file. The relevant artifact is the **MultiHop-RAG paper (Tang & Yang,
EMNLP 2024)** alignment in
`reports/research-runs/alpha-8-paper-aligned-comparison-20260604.md`;
that paper's retrieval experiments are LlamaIndex + ada-002 / voyage-02
(± reranker). So the observed win is **JAMES (bge-m3 + Chroma + hybrid)
vs the MultiHop-RAG retrieval table**.

Honest decomposition of the win:

| Source of the win | Attribution |
|---|---|
| Newer commodity embedding (bge-m3 vs ada-002/voyage-02) | **expected / table-stakes** — off-the-shelf, not JAMES IP |
| bge-m3 structural traits (dense+sparse+ColBERT, 8192 ctx, 100+ lang) | commodity, but materially helps multi-hop |
| Hybrid fusion `0.6·vec + 0.2·BM25 + 0.1·kw + 0.1·name` + cross-encoder rerank | **JAMES-built** |
| Entity-anchor expansion, graph-RAG DFS, abstention, citation | **JAMES-built (the real value)** |

`JAMES + gemma4:e4b` reaches **0.44–0.47** on the paper-aligned primary
metric = ChatGPT-3.5 parity, **below GPT-4 (0.56)**. The retrieval
substrate is *competitive, not SOTA* — consistent with the internal
honest framing in `retrieval-pipeline-audit-20260603.md` (graded-answer
ceiling = ⭐⭐ partial; retrieval-side headroom ≈ +0.05–0.10).

---

## 2. External landscape: embeddings are commoditised

| Model | Released | MTEB (Eng) | Note |
|---|---|---|---|
| ada-002 | 2022 | ~61.0 | **deprecated 2025-10-03** |
| voyage-02 family | 2023→2024 | — | superseded by voyage-3/3.5/4 |
| **bge-m3** | 2024-01 | ~63.0 | dense+sparse+ColBERT, 8192 ctx, 100+ lang |
| OpenAI text-3-large | 2024 | 64.6 | MIRACL 31.4 → 54.9 vs ada |
| Cohere embed-v4 | 2025 | 65.2 | |
| Gemini Embedding 001 | 2025 | 68.32 | English MTEB #1 |
| NVIDIA Llama-Embed-Nemotron-8B | 2025 | — | multilingual MTEB #1, open-weight |

**Implication**: "which embedding model" is no longer a RAG
differentiator. The 2025–2026 reviews (RAGFlow year-end review; Agentic
RAG survey 2501.09136) place value in: **(1)** agentic RAG, **(2)**
GraphRAG, **(3)** context engineering, **(4)**
provenance/auditability/governance, **(5)** quality gates/eval.

---

## 3. JAMES position — 3-layer map (design-verified)

| Layer | JAMES position | Honest grade |
|---|---|---|
| Embedding/vector **substrate** | at current commodity frontier, **not SOTA** | beats old paper baseline = pass |
| **End-to-end answer quality** | mid-pack, limits acknowledged | 0.44–0.47 paper-aligned; comparison_query 0.24 weak |
| **System / governance moat** | **upper tier — the differentiator** | aligned with field's stated 2026–2030 enterprise moat |

---

## 4. System-layer ↔ external-benchmark mapping (core of this analysis)

Each capability was verified against the actual codebase (file refs in
§6) and matched to whether an external benchmark exists to evaluate it.

| JAMES system layer | External bench? | Representative bench | Metric |
|---|---|---|---|
| Hybrid (BM25+dense+rerank) | ✅ strong | BEIR, MTEB-retrieval, MultiHop-RAG | nDCG@10, Recall@k, MRR, MAP |
| Graph-RAG (DFS + ACT halting) | ✅ strong | HotpotQA, MuSiQue, 2WikiMultiHopQA, GraphRAG-Bench | EM / F1, supporting-fact acc |
| Citation (source grounding) | ✅ strong | **ALCE** (ASQA/QAMPARI/ELI5), GaRAGe, RAGTruth | citation precision/recall, correctness |
| Abstention (hallucination refusal) | ✅ exists | **RGB** (negative rejection), RAGTruth, FaithBench | hallucination rate, rejection acc, F1 |
| Entity-anchor (query expansion) | △ indirect | no dedicated bench; measured via Recall@k uplift | Recall@k delta |
| QVT 5-axis quality gate | △ framework only | RAGAS / ARES / TruLens / RAGBench / RAGChecker | (eval framework, **not** a leaderboard) |
| **ABAC access control** | ✗ no standard bench | SNU *Permission-Aware RAG* (2026), *Secure RAG* survey — prototypes only | — |
| **Replay / audit reproducibility** | ✗ no bench exists | (no public task scores trace reconstructability) | — |

### Reading

- **The 4 well-benchmarked axes are red-ocean.** Multi-hop SOTA is
  re-set quarterly (HopRAG, GraphRAG-R1, StepChain GraphRAG, LinearRAG).
  Placing JAMES there yields a *measurable but not #1* result. Best
  near-term external numbers: **abstention** (Abstention F1 ↔ RGB
  negative-rejection, near 1:1) and **citation** (ALCE precision/recall).
- **QVT is a framework, not a contest.** Externally it is the RAGAS/ARES
  family **internalised as a merge gate** (PR-level Quality Delta Card).
  Position it as *engineering discipline / process rigor*, not a score
  to win.
- **The two most differentiated capabilities have no external bench.**
  - ABAC: only nascent 2026 research (SNU Permission-Aware RAG; Secure
    RAG review) — no leaderboard. JAMES's design is in fact *stronger*
    than the generic doc-level pattern: `cross_stage_abac_verify`
    enforces 3-stage **Vector → Graph → Output** policy consistency
    (`core/security_layer/_abac.py`).
  - Replay/audit: no public task scores this at all. JAMES pins it as a
    hard invariant — ARCHITECTURE.md §5.7.2: *the full reasoning trace
    must be reconstructable from `audit_log` rows alone*
    (`tests/test_replay_trace.py`).
  - **Double edge**: (+) competitors cannot comparison-shop or leapfrog
    you on a number here = genuine moat, and it matches the field's
    stated enterprise governance frontier; (−) you cannot *prove*
    superiority with a number → it stays "unproven" under honest-framing
    and leans on "trust us" for sales/publication.

---

## 5. Recommendation — two-track

**Track A — buy external trust with numbers (low cost, do first):**
1. Wire JAMES abstention to **RGB / RAGTruth** (Abstention F1 ↔ negative
   rejection). JAMES-unique strength → strongest first external number.
2. Run citation on **ALCE (ASQA)** for citation precision/recall;
   RAGAS as harness.
3. Extend the existing MultiHop-RAG alignment to **MuSiQue /
   2WikiMultiHopQA** for graph-RAG — pre-state "not #1" honestly.

**Track B — prove the moat by demonstration, not benchmark:**
4. ABAC + replay have no public bench → ship a **reproducible demo +
   sample audit-log/trace** as the evidence artifact; cite SNU
   Permission-Aware RAG's PEP as the reference design JAMES already
   embeds in production (3-stage cross-layer).

This is consistent with CLAUDE.md direction: mother-platform hardening +
v0.5 enterprise-internal-knowledge pilot (audit/ownership/correction
moat). The right next bet is **graph reasoning depth + provenance**, not
embedding tuning.

---

## 6. Design-consistency verification (claims ↔ code)

Re-verified 2026-06-05 against the actual tree before commit:

| Claim | Verified at | Verdict |
|---|---|---|
| bge-m3 active embedding (baseline) | `eval/qvt/baseline_2a31b20.json` env `JAMES_EMBEDDING_MODEL=BAAI/bge-m3`; `config.py:207` legacy default = MiniLM | ✓ (active via baseline env; legacy default noted) |
| Hybrid fusion weights | `core/retrieval_engine.py:68–152` (`0.6/0.2/0.1/0.1`) | ✓ |
| Cross-encoder rerank | `core/retrieval/rerank.py` (ms-marco-MiniLM / bge-reranker-base) | ✓ |
| Entity-anchor expansion | `core/retrieval/entity_anchor_expander.py` | ✓ |
| Graph-RAG DFS + ACT halt | `core/graph_engine.py:323–433` | ✓ |
| Citation / sources | `core/reasoning/pipeline.py:343` (`sources: docs[:3]`) | ✓ |
| Abstention F1 | `eval/qvt/oracle.py:758` `score_abstention_f1` | ✓ |
| QVT 5-axis | `eval/qvt/oracle.py` `score_path_coverage/graded_answer/abstention_f1/token_cost/latency_cost`, `score_five_axis` | ✓ |
| Paper-aligned metric | `eval/qvt/oracle.py:629` `score_paper_aligned_accuracy` | ✓ |
| **ABAC (3-stage)** | `core/security_layer/_abac.py` `cross_stage_abac_verify` (Vector→Graph→Output) via `PolicyEngine` | ✓ **stronger than stated** |
| **Replay invariant** | ARCHITECTURE.md §5.7.2; `tests/test_replay_trace.py` (reconstruct trace from `audit_log` alone) | ✓ |

No inconsistency found. Two claims (ABAC, replay) were **understated**
in the original analysis and are corrected upward here.

---

## 7. Sources

- MTEB / embeddings: Modal MTEB leaderboard; Ailog 2025 guide;
  VentureBeat leaderboard shakeup; OpenAI embedding update; ada-002
  deprecation; BAAI/bge-m3 (HuggingFace).
- RAG landscape: RAGFlow 2025 year-end review; Agentic RAG survey
  (arXiv 2501.09136); Morphik enterprise RAG; NStarX RAG 2026–2030.
- Eval/benchmarks: ALCE (arXiv 2305.14627); GaRAGe (ACL Findings 2025);
  Vectara/FaithJudge faithfulness leaderboard (arXiv 2505.04847);
  RAGTruth abstention study; RAGBench (arXiv 2407.11005);
  Awesome-RAG-Evaluation survey (YHPeter); GraphRAG-Bench / HopRAG /
  LinearRAG.
- Security-RAG: SNU *Permission-Aware RAG* (IAM-based filtering, 2026);
  *Towards Secure RAG* review (arXiv 2603.21654).
