# Axis-2 — Graph-vs-Flat Utility Differential (reachability proxy, LLM-free)

> **Status**: EXECUTED result (2026-06-04). Deterministic, no LLM, no core/
> edits (pure `check_access` only). Parallel-safe with a running test suite.
> **Branch**: `claude/graph-rag-abac-benchmark-qRBnr`
> **Artifact**: `eval/abac_bench/probe_differential.py` +
> `eval/abac_bench/fixtures/axis2_graph.py`
> **Run**: `python -m eval.abac_bench.probe_differential`

---

## Result

### Strictness sweep (JAMES real roles)
| role | graph answerable | flat answerable | differential (flat−graph) |
|---|---|---|---|
| external | 0/7 | 1/7 | **1** |
| employee | 3/7 | 6/7 | **3** |
| manager | 6/7 | 6/7 | 0 |
| admin | 7/7 | 7/7 | 0 |

### Per-question @ employee (sees public+internal; hub = confidential)
- **Q1, Q2, Q3 — flat answers, graph cannot** (path routes through the
  confidential hub). **Q3 is the sharpest: the answer node is *public*, yet
  graph-RAG cannot reach it** because the only path crosses a confidential
  hub. Flat retrieves the public endpoint directly.
- Q4, Q7 — no-hub routes, both answer.
- Q5 — secret answer: both fail (control, no differential).
- Q6 — **redundant** (hub path OR internal bypass): graph answers via the
  bypass → redundancy rescues it.

### Centrality concentration (k=1 node removal, admin baseline)
| removal | graph loss | flat loss |
|---|---|---|
| targeted = highest-betweenness (Cobalt Hub) | **4/7** | **0/7** |
| mean over gated nodes | 2.00/7 | — |

Removing one high-betweenness *intermediate* breaks 4 graph multi-hop
answers (2.0× the mean gated node) while flat loses 0.

---

## What this establishes

1. **A graph-specific utility cost of access control exists and is
   measurable.** It appears precisely when a reasoning path routes through an
   intermediate node *more sensitive than the answer node* — graph traversal
   is path-dependent, flat retrieval is not. This is the mechanism SNU
   (no graph) and VAULT (post-filter, no flat comparison) never isolate.
2. **The chokepoint↔redundancy duality is demonstrated both ways**: gating a
   high-betweenness hub collapses many answers (chokepoint); an alternative
   path rescues the question (redundancy, Q6).
3. **The differential is conditional, not universal** (honest): under uniform
   level-gating where the hub is ≤ the answer's sensitivity, graph and flat
   degrade together (manager/admin rows, differential 0). The graph-specific
   penalty is concentrated in the "sensitive-intermediate, less-sensitive-
   answer" regime.

## Honest scope / caveats
- This is an **answerability *reachability* proxy**, not measured answer
  quality. It isolates the structural mechanism; the LLM probe must confirm
  that JAMES's actual answers track these reachability verdicts.
- **Mechanism is conceded**: targeted-vs-random super-linearity is
  Albert/Jeong/Barabási (*Nature* 2000). The novel unit is the *access-
  control framing* + the *graph-vs-flat paired comparison* + the *answer-
  accessible-but-path-gated* case — not the percolation insight.
- Concentration ratio here is 2.0× (small hand-built graph). A scaled
  synthetic graph with realistic degree distribution would sharpen the
  magnitude; this fixture proves direction + existence, not magnitude.

## Hooks into the rest of Tier-1
- **Recovery (Axis-4)** has a concrete definition now: the Q6-style rescue
  rate — fraction of path-gated questions recoverable via an alternative
  *permitted* path. (graph re-routing.)
- **LLM probe** should report, per role, whether actual answer correctness
  matches graph-answerable here (validates the proxy) and feed the parametric
  baseline.

## Next (parallel-safe vs not)
- Parallel-safe (no LLM / no core edits): scale the fixture; add Axis-4
  recovery-rate computation (also reachability-based).
- NOT parallel-safe (hold for after the test run): LLM-echo probe; Tier-2
  must-fixes.
