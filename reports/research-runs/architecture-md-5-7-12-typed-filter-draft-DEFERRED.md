# ARCHITECTURE.md §5.7.12 draft — α-8 ontology typed filter [**DEFERRED 2026-06-03**]

> **STATUS: DEFERRED** — Phase C n=3 paired confirm (2026-06-03 04:00)
> returned ⭐ operational only per §4.1 tree (graded Δ +0.007 < +0.010,
> abst_f1 Δ inside 0.418 noise band). Code stays in main (PR #688/#689
> already landed), default ON, no regression — but **no formal §5.7.12
> entry in ARCHITECTURE.md until stronger evidence**. See
> `reports/research-runs/alpha-8-phase-d-closure-analysis-20260602.md`
> for verdict basis + `memory/feedback_n1_verdict_inflation_n3_caught`
> for process lesson.
>
> **Paths to revival**: (a) 5-tier remeasurement showing scale-
> dependent magnitude, (b) R1-targeted null-only fixture where
> mechanism should saturate, (c) larger N (n=5+) at M_M. If any
> produces ⭐⭐ verdict, this draft is the base — Δ table fill from
> new measurement, verbiage tone-up, then insert.
>
> The original draft below preserved verbatim for context.

---

## ⚠️ Original draft (pre-n=3) — preserved for revival reference

---

### 5.7.12 Ontology typed-filter layer (α-8, v0.4, 2026-06-02)

Groups graph-DFS entity results by ontology entity_type before assembling
the LLM prompt context, and emits an explicit `(none found in graph for
this query)` row for query-relevant types that have zero entities. The
empty-type rows are the structural evidence-of-absence signal — they let
the LLM recognise "the corpus contains no person of this name" instead
of receiving a bare entity list whose absence is implicit.

Triggered by the α-7 cycle's REJECT verdict (2026-06-02, PR #680, 10th
wrong-fix-averted): α-7's top-K=10 graph filter removed entities the LLM
needed to detect null-query absence, causing universal regression
(e4b/12b/27b CRASH amplify→disrupt at multiple tiers). The α-7 closure
analysis (`reports/research-runs/alpha-7-closure-analysis-20260602.md`)
identified that the right fix is NOT filtering harder but **making the
absence explicit** — which is what α-8 ships.

Implementation:

1. **`core/ontology.py`** (Phase A, PR #688) — 5 new horizontal entity
   types (`event`, `date`, `location`, `quantity`, `project`) + 6 new
   relations (`OCCURRED_AT`, `HAPPENED_ON`, `LOCATED_IN`, `INVOLVES`,
   `MEASURED_AS`, `WORKED_ON`). All horizontal per design memo §2.3
   boundary test (✅ "any pack benefits", ❌ "pack-specific only" filter
   applied). New `ENTITY_TYPES` dict carries `since:` field for v0.5
   domain-pack extension hook. Module 14.9 KB (under 20 KB gate).
2. **`core/graph_typed_filter.py`** (Phase A, PR #688) — new module
   (10.7 KB) implementing the R1-R5 rules from design memo §2.4:
   - **R1**: never silently drop a query-relevant type slot
   - **R2**: empty-type rows are first-class context (the explicit
     "(none found)" line)
   - **R3**: don't conflate "empty" with "type not in query"
   - **R4**: order types by query relevance, not alphabetic
   - **R5**: cap total type slots at 10 (loose)
   Public API: `is_typed_filter_disabled`, `classify_query_intent`,
   `group_entities_by_type`, `format_typed_context`, `apply_typed_filter`.
3. **`core/pipeline_context.build_unified_context`** (Phase B, PR #689)
   — prepends typed entity summary BEFORE graph context. Byte-additive
   when filter active; falls back to pre-α-8 path when disabled.
4. **`scripts/qvt_ablation_matrix.py`** (Phase B, PR #689) — adds
   `C_rag-ontology` sector cell between `C_rag-graph` (α-7 baseline,
   `JAMES_DISABLE_TYPED_FILTER=1` forced) and `C_rag-full` (full
   layered stack). Lets future cycles measure typed filter effect
   incrementally via Δ vs `C_rag-graph`.

Default behaviour: filter **ACTIVE** in production (`/query/`). Disable
flag `JAMES_DISABLE_TYPED_FILTER=1` reverts to pre-α-8 byte-identical
path for A/B measurement.

Query intent classification (per design memo §2.1 step 5): cheap
deterministic keyword bag (`_INTENT_KEYWORDS` in `graph_typed_filter.py`).
LLM-judge upgrade is a v0.5+ candidate. The bag-of-keywords design is
intentional — if a heuristic classifier-based filter beats heuristic
top-K, the LLM classifier upgrade has a *floor* not a ceiling
(design memo §1.3 honest framing).

**Verdict** (Phase C closure, 2026-06-02):

| Axis | C_rag-graph (filter OFF) | C_rag-ontology (filter ON) | Δ |
|---|---:|---:|---:|
| path_coverage (multihop, M_M) | 0.4011 | 0.3967 | −0.004 (flat) |
| graded_answer (multihop, M_M, n=1) | 0.2900 | 0.3267 | **+0.0367** |
| abstention_f1 (multihop, M_M, n=1) | 0.4865 | 0.6222 | **+0.1357** |
| graded_answer (multihop, M_M, n=3) | *(n=3 TBD)* | *(n=3 TBD)* | *(n=3 TBD)* |
| abstention_f1 (multihop, M_M, n=3) | *(n=3 TBD)* | *(n=3 TBD)* | *(n=3 TBD)* |

Confusion matrix change at M_M n=1:
- TP (correct refusal): 9 → 14 (+5)
- FN (hallucination when should refuse): 16 → **11** (−5, **31% reduction**)
- FP (over-refusal): 3 → 6 (+3, minor cost)
- TN (correct answer): 72 → 69 (−3)

R1 mechanism direct evidence (`scripts/research/audit_12b_null_query_refusal_shape.py`):
5 α-8 refusal answers contain explicit absence-language ("because the
provided context does not contain any details regarding X") tied to
typed filter's empty-slot output — the exact §2.4 R1 design intent.

⭐⭐ adopt verdict per design memo §4.1 tree (`graded Δ ≥ +0.030`),
contingent on n=3 paired confirm holding the threshold.

Trust zone: typed filter is a context-formatting layer. No new write
paths, no new auth surfaces, no new sensitivity classes. Sensitive
relations (`HAS_SECRET`, `KNOWS_PASSWORD`, `HAS_CREDENTIAL`,
`OWNS_PRIVATE`) keep `compute_graph_score = 0` weighting unchanged.

**Scope discipline**:

- **Mother-platform horizontal only** — 5 new types passed §2.3
  boundary test. `regulation` (legal-leaning), `transaction`
  (finance/retail-leaning), `recipe` (food-only) were explicitly
  deferred/rejected per CLAUDE.md rule #1.
- **No domain-vertical drift** — `since:` extension hook in
  `ENTITY_TYPES` is the v0.5 domain-pack integration point. Mother
  schema does **not** absorb pack-defined types.
- **No retroactive reclassification** — existing 931 wiki entities'
  `entity_type` field untouched. New types only assigned at next
  ingest. Operators may run a one-off retro-classification script if
  desired; α-8 does not autonomously reclassify (parallels event-
  promotion rule from §5.7.6).
- **No auto-evolution of the schema itself** — adding a new entity
  type or relation type requires a code-level PR + reviewer approval
  (CLAUDE.md rule #1+#3). The Change Request primitive
  (`core/change_request.py`, §5.6) supports `self_evo_patch` target
  types in principle, but ontology schema patches are out of scope
  for v0.4. Defer mechanism to post-v1.0.
- **`feedback_finding_size_honest_framing` ceiling** — even at
  ⭐⭐ verdict, the finding is **partial**, not new mechanism.
  Type-aware context filtering is decades-old (MS GraphRAG, LlamaIndex,
  every commercial RAG with type hints). JAMES contribution = (a)
  multihop_rag Δ numbers, (b) explicit R1-R5 design rule, (c)
  operational empirical position. **No "ontology fixes RAG"
  headline framing.**

Module sizes:

- `core/ontology.py` ≈ **14.9 KB** (under 20 KB gate; further additions
  need split-first)
- `core/graph_typed_filter.py` ≈ **10.7 KB**
- `core/pipeline_context.py` change ≈ +1.2 KB (typed-prefix overlay only)
- `scripts/qvt_ablation_matrix.py` change ≈ +0.6 KB (sector cell entry)

Pointers:

- Design memo: `docs/design/v0.4-alpha-8-ontology-typed-filter.md` (§2.4 R1-R5, §3 integration, §4 verdict tree, §1.3 honest framing)
- α-8 Phase A PR: `#688` (`fcf343d`) — ontology + module + flag
- α-8 Phase B PR: `#689` (`6d6698e`) — matrix cell + pipeline overlay
- α-8 closure PR: *(TBD post-n=3, conditional on verdict)*
- Closure analysis: `reports/research-runs/alpha-8-phase-d-closure-analysis-20260602.md`
- Closure memory: `memory/project_alpha_8_closure_state.md`
- α-7 predecessor (REJECT context): `reports/research-runs/alpha-7-closure-analysis-20260602.md`
- Audit script: `scripts/research/audit_12b_null_query_refusal_shape.py`

---

## Insertion notes for the closure PR

- Bump main TOC if exists
- Update `## 8. Versioning of this document` with new section entry
- Update `## 9. 한국어 요약` to include one-line mention of α-8 typed
  filter as v0.4 lifecycle addition
- Cross-reference from §5.7.10 (QVT) to mention new C_rag-ontology cell
  as the canonical α-8 measurement vehicle
- Cross-reference from §5.7.7 (deployment) — no change needed,
  workspace isolation pattern unaffected by ontology layer
