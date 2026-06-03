# JAMES Retrieval Pipeline Audit (2026-06-03)

> Conducted after α-8 ⭐ operational verdict to identify the actual
> bottleneck on answer quality. Audit conclusion: typed filter (α-8)
> is a small operational helper; the bigger ROI sits in **retrieval
> stage** improvements (reranker, chunk size, top_k) which were never
> properly measurement-audited. This doc seeds the β / γ / δ cycle
> sequence.

---

## 0. Why this audit

α-8 Phase C n=3 paired confirm + null_v1 saturating measurement both
returned **⭐ operational only** (graded Δ +0.000–+0.007, abst_f1 Δ
+0.03–+0.06, all inside noise). Direction-correct but small. The
diagnostic surfaced a deeper question: **where is the actual ceiling
on JAMES answer quality?**

The α-cycle series (α-5 through α-8) measured *layer ablation*
(JAMES_DISABLE_* flags) but never audited the underlying retrieval
pipeline. Typed filter operates on retrieval output — if retrieval
itself is the bottleneck, no upstream layer can save it.

This doc maps the retrieval architecture, identifies 6 specific
issues, and proposes a measurement-driven cycle sequence.

---

## 1. Current architecture

```
User Query
    ↓
STEP 0.5a: Entity Anchor Expander (F9.3, opt-in)
    │     core/retrieval/entity_anchor_expander.py
    │     "MCP 설계자 David Soria Parra" pattern — corpus-aware anchor
STEP 0.5b: Query Rewriter (LLM-based, opt-in)
    │     core/retrieval/query_rewriter.py
    ↓
Loop 0: Hybrid Search (top_k=8)
    │     core/retrieval_engine.py:hybrid_search
    │     - Vector(0.6) + BM25(0.2) + Keyword(0.1) + Name(0.1)
    │     - VectorStore = ChromaDB cosine, BAAI/bge-m3 (1024-dim)
    ↓
Cross-Encoder Reranker (top-8 → top-5)
    │     core/retrieval/rerank.py
    │     - DEFAULT: cross-encoder/ms-marco-MiniLM-L-6-v2  (English-only)
    │     - JAMES_RERANKER_MODEL=BAAI/bge-reranker-base    (multilingual)
    │     - JAMES_DISABLE_RERANK=1 to skip
    ↓
GraphEngine.expand_dynamic — DFS graph expansion
    ↓
typed_filter (α-8) — entity grouping by 9 ontology types
    ↓
LLM answer generation
```

### Chunking

`utils/tokenizer.py:split_chunks`:
- chunk_size=**500 chars**, overlap=**50 chars** (~10%)
- hierarchical: heading (`# / ## / ###`) → paragraph (blank line) → sentence (.!?。) → fixed-size fallback
- 359 chunks in ChromaDB

### Embedding

`config.EMBEDDING_MODEL = BAAI/bge-m3` (multilingual, 1024-dim, BL-9 swap landed 2026-05-27).
- Per-model chroma dir: `chroma_db_bge_m3/`
- Legacy `paraphrase-multilingual-MiniLM-L12-v2` (384-dim) still mappable.

### Hybrid scoring weights

```python
# core/retrieval_engine.py:hybrid_search final scoring
score = 0.6 * vector_score + 0.2 * bm25 + 0.1 * keyword + 0.1 * name
```

NO measurement of weight optimality. Magic constants since refactor.

### Reranker

`core/retrieval/rerank.py`:
- One CrossEncoder per process (lazy load, thread-safe)
- Default model = ms-marco-MiniLM (~80 MB, **English-optimized**)
- Operator comment: "Korean-heavy corpora can swap to BAAI/bge-reranker-base"
- Reranks top-8 candidates → returns top-5

### Query expansion

`core/retrieval/entity_anchor_expander.py` (F9.2/F9.3):
- For bare proper-noun queries ("David Soria Parra가 누구야?")
- Scans wiki entity index + frontmatter aliases
- Adds corpus-verified concept anchors
- Opt-in via env

---

## 2. 6 findings — Priority ranked

### 🔴 P1: Reranker is English-only (CrossEncoder)

**Finding**: Default reranker `cross-encoder/ms-marco-MiniLM-L-6-v2`
is trained on MS MARCO (English passage retrieval). JAMES corpus is
Korean+English mixed; F7 audit already showed Korean proper-noun
retrieval has multilingual encoder weaknesses (`memory/feedback_q15_chroma_embedding_root_pinned`).

The operator escape hatch (`JAMES_RERANKER_MODEL=BAAI/bge-reranker-base`)
exists but defaults to English-optimized. No measurement comparing the
two has been run.

**Hypothesis**: bge-reranker-base (multilingual, 278 MB) materially
improves graded_answer on Korean queries.

**Fix cost**: env var change (1 line) or default model swap (1 line).
First-time model download ~278 MB.

**Cycle**: β-1 (this session, in flight as `bp9ckr0ge`).

### 🔴 P2: Chunk size = 500 chars (very small)

**Finding**: Modern RAG systems use 256–1024 tokens per chunk. JAMES
uses 500 chars which translates to:
- Korean: ~150–200 tokens
- English: ~80–120 tokens

Mid-document entity relations (e.g., "Tesla founded by Elon Musk and
JB Straubel and Marc Tarpenning, in 2003 in San Carlos") often span
multiple chunks at 500 chars. Each chunk loses surrounding context.

**Hypothesis**: chunk_size 500→1024 improves multi-hop graded_answer
materially.

**Fix cost**: 1 line `split_chunks(text, chunk_size=1024)` + **full
wiki re-ingest** (~30 min for 316 source docs). Risk: chunk-ID
mismatch with existing relations.

**Cycle**: γ-1 (after β-1).

### 🟡 P3: Retrieval top_k=8 narrow

**Finding**: With 359 total chunks, top_k=8 = 2.2% recall by document.
For multi-hop questions needing 3+ supporting docs, this is tight.
Cross-encoder reranks 8 → 5; the rerank's value is limited if only 8
candidates exist.

Modern RAG: retrieve 20–50 candidates → rerank → top 5–10.

**Hypothesis**: top_k 8→20 improves graded_answer at +500ms latency.

**Fix cost**: 1 line. Latency cost ~500ms-1s (rerank scales linearly
with input count).

**Cycle**: β-2 (after β-1 if reranker swap helps).

### 🟡 P4: Hybrid weights never measured

**Finding**: `0.6 vector + 0.2 BM25 + 0.1 keyword + 0.1 name` is a
magic-number formula from the v0.1 refactor. No grid-search, no
A/B test, no ablation. With BL-9 (bge-m3 swap), vector quality
changed but weights didn't.

**Hypothesis**: Different weight mix (e.g., 0.7/0.15/0.10/0.05) helps.

**Fix cost**: weight grid-search measurement (~10h compute for
representative grid).

**Cycle**: δ-2 (after β + γ, lower priority).

### 🟡 P5: No retrieval-side quality metric

**Finding**: Bench measures graded_answer / abstention_f1 / token /
latency. None measure retrieval@k quality directly (NDCG, MRR,
Recall@k). When typed filter Δ is tiny, can't disambiguate "filter
broken" vs "retrieval is the upstream ceiling".

**Hypothesis**: NDCG@5 measurement infra lets future cycles factor
out retrieval contribution from layer-specific contribution.

**Fix cost**: ~2h infra build (need labeled gold-doc-per-query).

**Cycle**: δ-1 (measurement infra; supports δ-2 + future).

### 🟢 P6: No metadata-aware retrieval routing

**Finding**: Hybrid search uses only `source_type` and `sensitivity`
filters. The typed filter intent classifier (α-8) routes queries to
9 type buckets but this signal is NOT used at retrieval — it only
affects the LLM context post-DFS.

**Hypothesis**: "date question → chunks containing date entities"
priority improves both retrieval and typed-filter effect.

**Fix cost**: medium (intent → chunk-metadata mapping). Requires
chunk-time metadata extraction extension.

**Cycle**: ε-1 (synergy with α-8 + γ chunking).

---

## 3. Proposed cycle sequence

### β cycle (fast wins, this session + next)
| ID | Action | Compute | Decision |
|---|---|---:|---|
| β-1 | Reranker swap ms-marco → bge-reranker-base | ~1h × 2 (n=3) | Δ ≥ +0.030 graded → adopt |
| β-2 | top_k 8→20 (conditional on β-1 win) | ~1h × 2 | Δ ≥ +0.020 graded → adopt |
| β-3 | Combined β-1+β-2 cell vs default | ~1h × 2 | confirm cumulative |

### γ cycle (chunk size, heavier)
| ID | Action | Compute |
|---|---|---:|
| γ-1 | chunk_size 500→1024 + re-ingest 316 docs | ~30 min ingest |
| γ-2 | n=3 paired measurement on β-best stack | ~5h |

### δ cycle (measurement infra + weight tuning)
| ID | Action | Compute |
|---|---|---:|
| δ-1 | NDCG@5 / MRR measurement infrastructure | code only |
| δ-2 | Hybrid weight grid search ablation | ~10h |

### ε cycle (synergy, post-γ)
| ID | Action | Compute |
|---|---|---:|
| ε-1 | Intent-aware retrieval routing | medium build |

---

## 4. Mother platform fit

All 6 issues are **horizontal** (mother-platform improvements). No
vertical drift. CLAUDE.md rule #1 ✓.

The β / γ / δ / ε cycles all close BEFORE v0.5 domain pilot — they
strengthen the platform foundation that v0.5 will stress-test in
production. Per `memory/feedback_jameses_positioning_replayable_rag`:
v0.5 ≠ silver bullet on answer quality; it's the domain
contextualization layer ON TOP of the mother platform's retrieval
strength.

---

## 5. Honest framing reminders

- **Reranker swap (β-1) ceiling = ⭐⭐ partial** even at best case.
  Cross-encoder retrieval is decades-old; multilingual variant is
  standard practice. JAMES contribution = empirical Δ on this corpus +
  operational position.
- **Chunk size (γ-1) ceiling = ⭐⭐ partial**. Larger chunks help
  multi-hop is well-known. JAMES contribution = empirical optimal
  for bge-m3 + this corpus shape.
- **NDCG infra (δ-1) = ⭐ operational** (measurement quality). Not a
  finding by itself.
- **Cumulative β+γ effect on graded_answer**: if it lands +0.05–
  +0.10, that's the realistic answer-quality lever JAMES has at
  v0.4.x. v0.5 then tests THIS strength under domain stress.

---

## 6. Pointers

- α-8 closure: `memory/project_alpha_8_closure_state.md` (⭐ verdict)
- Honest framing: `memory/feedback_finding_size_honest_framing.md`
- BL-9 embedding swap: `memory/feedback_bl9_partial_q15_query_expansion_root.md`
- Q15 retrieval debug: `memory/feedback_q15_chroma_embedding_root_pinned.md`
- Reranker code: `core/retrieval/rerank.py`
- Hybrid search code: `core/retrieval_engine.py:hybrid_search`
- Chunking code: `utils/tokenizer.py:split_chunks`
- Vector store: `core/vector_store.py:VectorStore`
- Compare tool: `scripts/research/compare_paired_cells.py` (this session)

---

## 7. Korean handover snippet

α-8 ⭐ closure 후 retrieval pipeline audit 진행. 6개 발견:
- (P1) reranker 영문전용 → bge-reranker-base swap = β-1 cycle 진행 중
- (P2) chunk size 500 chars 너무 작음 → 1024 + 재 ingest = γ
- (P3) top_k=8 좁음 → 20 = β-2
- (P4) hybrid weights 측정 안 됨 = δ-2
- (P5) NDCG/MRR infra 없음 = δ-1
- (P6) metadata-aware routing 없음 = ε-1

답변 품질 실 lever 는 retrieval stage. v0.5 silver bullet 아님 —
mother platform 의 β/γ/δ cycle 들이 v0.5 진입 전 답변 품질 토대
구축. ε 는 α-8 typed filter 와 synergy.
