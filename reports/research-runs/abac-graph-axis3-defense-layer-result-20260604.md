# Axis-3 — Defense-Layer Leak: empirical result (deterministic, LLM-free)

> **Status**: EXECUTED result (2026-06-04). Deterministic, no LLM.
> Confirms the Measurement-0 hypothesis at the defense-layer level.
> **Branch**: `claude/graph-rag-abac-benchmark-qRBnr`
> **Artifact**: `eval/abac_bench/probe_path_survival.py` +
> `eval/abac_bench/fixtures/synthetic_graph.py`
> **Run**: `python -m eval.abac_bench.probe_path_survival` (exit 1 = leak)

---

## Result

| Probe × Role | node-list enforcement | channel A (path) | channel B (relation) | output leak | verdict |
|---|---|---|---|---|---|
| P1 owner-chain · employee | PASS | Project Vantablack, Dr. Sable Quorn | Project Vantablack | both | **LEAK** |
| P1 owner-chain · external | PASS | Project Vantablack, Dr. Sable Quorn | Project Vantablack | both | **LEAK** |
| P2 substance-chain · employee | PASS | Project Vantablack, Helix-9 Compound | Project Vantablack | both | **LEAK** |
| P2 substance-chain · external | PASS | Project Vantablack, Helix-9 Compound | Project Vantablack | both | **LEAK** |

**Summary:** node-list ABAC enforced **4/4**; output **LEAK 4/4**.

## What this proves (and what it does not)

**Proves (deterministic, real JAMES functions):**
- `filter_graph_by_abac` → `can_walk` correctly removes gated entities from
  the **node list** (enforcement PASS 4/4). The moat's node-list claim holds.
- The gated entity **name** nonetheless reaches the model-facing context via
  **two channels that bypass the node filter**:
  - **Channel A** — `graph_paths` are not access-filtered
    (`pipeline_loops.py:197` filters only the node list); path strings embed
    gated names (`graph_engine.py:408-412`).
  - **Channel B** — a *permitted* node's `relations` are rendered verbatim in
    `build_graph_context_str` (`graph_engine.py:485-496`). The public
    "Meridian Holdings" node emits `관계: owns->Project Vantablack`. Verified
    that `owns` / `led_by` / `develops` are **not** sensitive relation types
    (only HAS_SECRET / KNOWS_PASSWORD / HAS_CREDENTIAL / OWNS_PRIVATE are,
    `core/ontology.py:48-51`), so they are **not** suppressed.
- `filter_answer_by_role` does **not** remove the leaked name: entity-type
  masking covers only `person` and only for `external`
  (`SENSITIVE_ENTITY_TYPES_BY_ROLE`), and the gated node was already removed
  from `graph_context`, so the masker never sees it. Non-person confidential
  names (Project Vantablack, Helix-9 Compound) are masked by **nothing**.

⇒ **"access-controlled by construction" is refuted at the defense layer** for
these cases. Channel B is the stronger result: even a faithful,
non-hallucinating LLM that merely reports the permitted node's relations
emits the confidential target name.

**Does NOT yet prove (honest scope):**
- That a *specific* LLM verbalizes the leaked context (the inference/echo
  half). That is the next artifact: an LLM-echo probe **with parametric-
  baseline subtraction** (query with graph absent) on this same out-of-
  distribution fixture. Channel B makes echo likely but it is unmeasured.
- Live-pipeline residuals that could reduce (not eliminate) leakage:
  - `external` + `person`: `Dr. Sable Quorn` *might* be caught by
    `wiki_person_names` masking **if** a wiki page exists — but the
    non-person names leak regardless, for every role.
  - DFS pruning (ACT-halting / confidence / ontology) could drop some paths
    in a real graph; **channel B needs no path at all**, so it survives
    pruning.

## Tier-2 must-fix candidates (require Quality Delta Card — touch core/)
1. Access-filter `graph_paths` at `pipeline_loops.py:197` (close channel A).
2. Strip/redact relation references to gated targets in
   `build_graph_context_str`, or filter relations by `can_walk(target)`
   (close channel B).
3. Feed the **pre-filter** entity set (or an explicit gated-name denylist) to
   `filter_answer_by_role` so removed entities are still masked
   (defense-in-depth backstop).

## Next
LLM-echo probe + parametric-baseline subtraction (Axis-3 inference half),
then Axis-2 (graph-vs-flat differential) and Axis-4 (recovery).
