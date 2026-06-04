# Measurement 0 — Enforcement-Point Audit (code audit)

> **Status**: code-audit finding (2026-06-04). **NOT yet empirically
> executed** — these are claim-vs-reality observations from reading the live
> `ReasoningEngine.query` path. Empirical confirmation is the fixture+probe
> step (Axis 3). Framed per `feedback_finding_size_honest_framing`.
> **Branch**: `claude/graph-rag-abac-benchmark-qRBnr`
> **Prereq for**: Axis 1 (enforcement) + Axis 3 (leakage). See the Tier-1
> plan (`abac-graph-moat-measurement-plan-20260604.md`).

---

## Self-correction vs the plan note

The plan note stated the graph-stage gate had "no caller in `core/reasoning`."
**That was a grep artifact** — the call is a *method* invocation
(`engine.security.filter_graph(...)`), not a direct `filter_graph_by_abac(`.
**The graph-stage gate IS wired in the live loop.** Corrected below.

---

## Live enforcement path (`ReasoningEngine.query` → Loop 1 → Output)

Traced through `core/reasoning/pipeline_loops.py::run_loop_1_expand` and
`core/reasoning/pipeline.py` (output stage).

```
Vector stage   retrieval_engine.py:103   can_retrieve(role, meta)      ✅ pre-filter (docs)
                                          └ ROLE_LEVEL ≥ SENSITIVITY_LEVEL

Graph stage    pipeline_loops.py:192     expand_dynamic(valid_ids)     ⚠️ DFS — NO clearance check
               graph_engine.py:341         dfs(...)                       (visits confidential nodes;
                                                                           blocks only sensitive *relation
                                                                           types* + ontology, not node
                                                                           clearance)
               pipeline_loops.py:195     rank_nodes(graph_ctx)         — no access
               pipeline_loops.py:196     security.filter_graph(...)    ✅ POST-traversal node filter
                                          └→ filter_graph_by_abac → can_walk   (entity LIST only)
               pipeline_loops.py:197     verify_reasoning(graph_paths) ❗ paths NOT access-filtered

Loop-2 ABAC    pipeline_loops.py:231     abac_consistency_check(...,"") logs violations; answer="" so
                                          (= cross_stage_abac_verify)    output stage not checked here; non-blocking

Output stage   pipeline.py:289           can_emit (phase-1: always allow)
               pipeline.py:290           filter_answer_by_role(answer, role,
                                            graph_context=<FILTERED list>, wiki_person_names=…)
                                          └ masks names of sensitive-type entities **present in the
                                            filtered graph_context**, + wiki persons (external only),
                                            + PII/keyword regex (mask_sensitive)
```

---

## Claim vs reality

| Public claim (`devto-data-exfiltration.md:164`) | Code reality |
|---|---|
| "every hop applies `can_walk`" | Gate is **post-traversal** (L196), not per-hop. DFS (L341) visits all nodes regardless of clearance. |
| "a confidential entity can't be a hop destination" | It **can** be a hop destination during DFS; it is removed from the *node list* afterward. |
| "the reasoning path is access-controlled by construction" | **`graph_paths` are NOT access-filtered** (only the node list is). Path strings embed confidential entity names (graph_engine.py:408-412). |

**Verdict:** the enforcement is *post-filter*, not *by-construction*. The
phrase "access-controlled by construction" overstates the actual mechanism.

---

## Hypothesised leak channel (Axis-3 target — UNCONFIRMED)

Code reading suggests a concrete path for inference/Direct leakage that
survives JAMES's defense-in-depth:

1. DFS visits a confidential entity `C` and builds a path string
   `"… -[rel]→ C"` (graph_engine.py:408-412).
2. `filter_graph` (L196) removes `C` from `graph_context` (the node list).
3. `verify_reasoning` (L197) does **not** access-filter `graph_paths`, so the
   string containing `C`'s name remains and flows into the answer context
   (via `build_graph_context_str(graph_entities, graph_paths)`).
4. `filter_answer_by_role` (L290) masks names of sensitive entities **that
   are in the (now-filtered) `graph_context`** — but `C` was *removed* at
   step 2, so `C`'s name is **not in the mask set** (unless `C` is a person
   and role is external, or `C` matches a PII/keyword regex).
5. ⇒ `C`'s name can reach the final answer via the unfiltered path string,
   escaping the very masker meant to catch it.

This is a **"filtered from the list, surviving in the path"** channel —
distinct from inference reconstruction, and arguably a *direct* leak. Both
the direct-leak (this) and the inference-leak (reconstruct `C`'s facts from
permitted neighbors) variants are Axis-3 measurements.

### Honesty caveats
- This is a **static-reading hypothesis**, not an executed result. Several
  guards may intervene in practice: `is_sensitive_relation` may block the
  edge to `C`; `mask_sensitive` keyword/PII rules may catch `C`; the path
  may be pruned by ACT-halting / confidence / ontology gates. **Must be
  confirmed by the fixture+probe**, not asserted.
- "ABAC" here is ordinal MLS (`ROLE_LEVEL ≥ SENSITIVITY_LEVEL`), not
  multi-attribute ABAC. Name it level-based.

---

## Implications for the build
- **Axis 1** (enforcement) must distinguish *node-list* enforcement (wired,
  L196) from *path* enforcement (absent) and *traversal* enforcement
  (absent). The moat claim is true for the node list, false for paths.
- **Axis 3** (headline) has a concrete first target: the path-survival
  channel above, with parametric-baseline subtraction on a leak-controlled
  synthetic fixture.
- A likely **Tier-2 must-fix** (if confirmed): access-filter `graph_paths`
  at L197 and/or feed the *pre-filter* entity set to `filter_answer_by_role`
  so removed entities are still masked. (Would require a Quality Delta Card —
  touches `core/reasoning`.)

## Next
Build `eval/abac_bench/fixtures/` (synthetic, leak-controlled) + the Axis-3
probe to empirically confirm/refute the path-survival channel.
