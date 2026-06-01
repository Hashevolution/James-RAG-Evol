# QVT α-5 Ablation — Incidental Findings Log

> **Purpose** — Capture observations during the α-5 ablation matrix run
> that don't fit a verdict cell but might be **mechanism candidates**
> or **universal laws** worth re-running / writing up later.
>
> **Plan reference**: `~/.claude/plans/quiet-hugging-iverson.md` Step 10.
> **User requirement #5**: "모델별 특성 / 보편적 법칙 발견 시 반드시 보고 후 추후
> 연구될 수 있도록 메모."
>
> **Style** — Each entry is short (3-5 lines). Date, cell context, what
> was observed, why it's surprising, recommended follow-up. **Do not**
> debug here — flag the surprise, capture the data pointer, move on.

---

## How to add a finding

1. Add a `### YYYY-MM-DD — <slug>` entry at the bottom of the
   "Findings" section below.
2. Fill the 5 fields (cell / observation / surprise / data pointer /
   follow-up).
3. If the finding crosses cells (e.g. consistent pattern across all
   M_S cells), tag it `pattern:` instead of `cell:`.
4. After the matrix run completes, scan this file and propose memo
   draft entries for findings tagged `mechanism-candidate` or
   `universal-law`. Memo lands under `memory/finding_<slug>.md` after
   user confirmation (see Step 10 of the plan for the trigger
   workflow).

## Categories (pick the strongest)

- **mechanism-candidate** — "I think X explains Y in this cell."
  Triggers a follow-up probe (next session) to confirm or refute.
  Example pattern: A3 thinking trace (#608 §16) — initially flagged
  here as "gemma4:e4b spends 85% of budget on hidden tokens",
  promoted to a mechanism via `v3prime_e4b_mechanism_probe.py`.
- **universal-law** — "This holds across all tiers / all layers / all
  query types." Worth a separate cross-axis confirmation run. Example:
  D3 §16.7 "reasoning cost is model-invariant" (#603) started as a
  cross-family observation, promoted to a paper-ready statement.
- **anti-pattern** — Surprising in the wrong direction (a layer that
  *hurt* quality on a tier we expected it to help). Document so we
  don't re-recommend it.
- **data-quality** — Suspicious result that suggests fixture / oracle
  bias rather than a real signal (e.g., constant abstention F1 across
  cells suggests the abstention phrase matcher is the bottleneck, not
  the layers).
- **operational** — Runtime / setup issue worth surfacing (e.g., ingest
  pipeline crashed on a specific article; budget caps interacting with
  routing).

## Diagnostic bucket (MANDATORY field, per user guidance 2026-05-31 PM-2)

Before this finding becomes a code change, classify which solution
bucket it belongs to. Getting the bucket wrong → wrong fix.

| Bucket | Symptom | Solution shape | Examples in repo |
|---|---|---|---|
| **(a) Architecture** | layer's designed boundary / shape is wrong | redesign / split / merge | (none yet this cycle) |
| **(b) LLM model** | model capability ceiling | tier change / model swap | A3 #608 — gemma4:e4b thinking trace; D3 #602/#603 — model-invariant cost |
| **(c) Feature gap** | no layer covers this need | new layer design | D6 LLM-judge (deferred); abstention nuance beyond phrase matcher |
| **(d) Measurement artifact** | oracle / fixture / bench misses real JAMES output | matcher fix (zero JAMES code change) | #618 source-recall; #619 abstention phrases |

Diagnosis order (priority): **(d) first** — cheapest to rule out;
**(b)** — same layer fails on multiple tiers?; **(a)** — design vs
observed behaviour mismatch; **(c)** — only after the above are ruled
out (otherwise you build a layer that didn't need to exist).

The 4-step verification rule for ruling out (d) is documented in memory
`feedback_oracle_phrase_artifacts.md` — apply it BEFORE proposing a
fix in any of the other three buckets.

Every entry below MUST include a `bucket:` line tagging (a)/(b)/(c)/(d).
"unclassified — needs more sampling" is fine while waiting on data.

---

## Findings

<!-- Add entries below this line, newest at the bottom. -->

### 2026-05-31 — multihop-rag-path-axis-dead → RESOLVED (bucket-d) (#618)

- **bucket**: (d) measurement artifact — bench.py was dropping
  `response.sources`; JAMES citation design was correct all along.
  Diagnosis: applied the 4-step rule (axis 0 → sample answers manually →
  check `response` keys → reconcile design vs matcher) and found
  `core/reasoning/pipeline.py:343` emits `sources: [d["source"] for d
  in docs[:3]]` while bench only inspected `graph_paths`.
- **pattern**: 100/100 queries with `expected_path` → `path_recall = 0.000`
- **cell context**: baseline L1/M_M (`baseline_f7762a3.json`), workspace
  ingested 183 articles (931 entities)
- **observation**: graph_paths actually returned 18-179 nodes per query
  (mean 60) but **none of them are MultiHop-RAG evidence article titles**.
  Sample q1 expected = `['The FTX trial is bigger than Sam Bankman-Fried',
  'SBF's trial starts soon, but how did he — and FTX — get here?', …]`;
  actual document entity name = `multihop_0010_SBF-s-trial-starts-soon-but-
  how-did-he-and-FTX-get-here` (prefix + slugified, max 80 chars).
- **surprise**: this is not just a slug formatting issue. graph_paths
  surfaces **concept / org / person entities** (the entities *extracted
  from* the article), not the **document entity** (the article itself).
  MultiHop-RAG's `evidence_list[].title` measures "did the system cite the
  right *source*" — that semantic doesn't map onto JAMES's concept-centric
  graph traversal.
- **data pointer**: `reports/bench_f7762a3_multihop_rag_20260531_063800.json`
  + `workspaces/hotpot_eval/eval/qvt/baseline_f7762a3.json` aggregate
- **follow-up tag**: `data-quality` + `mechanism-candidate`
- **probe ideas**:
  1. Modify `scripts/hotpot/build_fixture.py` to map each evidence title
     to the *concept/org entities extracted from that article*
     (post-ingest fixture rebuild). Requires loading wiki to find which
     concepts came from `source_document=multihop_<id>_<slug>.txt`.
  2. Modify `eval/qvt/oracle.py:score_path_coverage` to also credit
     document-via-`doc_id` matches when bench output includes the
     traversed document IDs.
  3. Accept path axis as fixture-incompatible for MultiHop-RAG; rely on
     graded + abstention + token + latency for matrix verdicts. Mark
     path Δ as "n/a — fixture limitation" in report.
  - Option 3 is cheapest; options 1 / 2 are methodologically cleaner.
- **immediate impact on α-5**: matrix loses 1/5 axes for verdict
  discrimination. With 4 remaining axes (3 quality + 2 cost; path frozen
  at 0), Pareto verdict still works but on a smaller surface. Sanity cell
  (think=ON vs OFF) still measurable on all 4 active axes.

### 2026-06-01 — multihop-rag-lost-in-middle-at-gemma4-e4b

- **bucket**: (b) — model-context interaction (well-documented in
  Lost-in-the-Middle / Power-of-Noise literature)
- **cell context**: α-6 Phase 1, C_minus → C_rag-basic transition at
  gemma4:e4b production tier (M_M), MultiHop-RAG balanced-100
- **observation**: adding S1 RAG retrieval to pure gemma4:e4b
  degrades abst_f1 by 0.137 (0.558 → 0.421). Null-query refusal
  count drops from 12/25 (pure LLM) to 8/25 (with RAG context).
  Specifically, the LLM hallucinates ON 4 MORE null queries when
  given irrelevant retrieved context vs no context at all.
- **surprise**: this matches the published Lost-in-the-Middle
  (Liu et al. 2023) + Power-of-Noise (Cuconasu et al. 2024)
  findings. Worth documenting that gemma4:e4b reproduces the
  pattern at production scale on MultiHop-RAG balanced-100. NOT
  JAMES-specific.
- **data pointer**: `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/qvt-ablation-cell-C_minus-M_M.json` +
  `qvt-ablation-cell-C_rag-basic-M_M.json` + analysis at
  `reports/research-runs/alpha-6-phase-1-analysis-20260601.md`
- **follow-up tag**: `mechanism-candidate`
- **probe ideas**: tier-gated check (Phase 2 in flight); does smaller
  gemma3:4b see larger relative degradation?
- **immediate impact on α-6**: framing change — α-6's "does each
  sector help vs vanilla LLM" question reframes: "does each sector
  help vs the LLM-alone-with-no-context baseline?" RAG and graph
  are no longer assumed-positive contributors.

### 2026-06-01 — jameses-s5-s6-recover-rag-damage

- **bucket**: (a) — architecture-as-designed; mechanism candidate
- **cell context**: α-6 Phase 1, C_rag-graph → C_rag-full transition
  at gemma4:e4b production tier (M_M)
- **observation**: enabling S5 abstention + S6 cognitive stages
  on top of S1+S2+S3+S4 recovers graded_answer by +0.054 (0.273 →
  0.327) AND abst_f1 by +0.129 (0.462 → 0.591). The recovery
  brings abst_f1 ABOVE the pure-LLM baseline (0.591 vs 0.558).
- **surprise**: this is the measurable JAMES contribution at
  production tier. S5+S6 are doing the heaviest semantic work in
  the stack — exactly the "abstention softener" mechanism the
  layer was designed for. Latency tax: +37s/query (~5.5× total
  over pure LLM).
- **data pointer**: same as above + α-5 L1 cell as C_rag-full
- **follow-up tag**: `mechanism-candidate` + `universal-law`
  (preliminary — Phase 2/3 confirms or restricts to gemma4)
- **probe ideas**:
  1. Phase 2 (M_S = gemma3:4b) tier-gated check
  2. Phase 3a (gemma3 scale ladder) — does recovery magnitude
     scale with model size?
  3. Phase 3b (cross-family qwen/llama/deepseek) — is the recovery
     JAMES-architecture-specific or universal RAG mitigation?
- **immediate impact on α-6**: this is the publishable JAMES
  contribution at production tier on MultiHop-RAG. Phase 2 tests
  whether the pattern is model-invariant.

### 2026-06-01 — jameses-graph-too-many-entities-surfaced

- **bucket**: (a) — architecture, optimizable (engineering, not
  fundamental)
- **cell context**: α-6 Phase 1, C_rag-graph cell, gemma4:e4b
- **pattern**: per-query graph_paths counts in trace JSONL range
  41-161 entities (sample queries 96-100 show counts of 90, 41,
  137, 161). LLM context window flooded with potentially-irrelevant
  graph entities.
- **observation**: adding S2 graph traversal + S3 preproc + S4
  citation as a bundle on top of S1 RAG degrades graded_answer by
  -0.054 (0.327 → 0.273). The aggregate Power-of-Noise pattern
  (semantically-similar irrelevant entities hurt more than random
  noise) reproduces on the graph axis.
- **surprise**: the graph layer is providing MORE noise than the
  document layer alone. Aggressive top-K filtering on graph
  results (by query embedding similarity, threshold ~0.3) is the
  cheapest engineering improvement candidate.
- **data pointer**: `workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/qvt-ablation-cell-C_rag-graph-M_M.json`;
  trace files in `workspaces/hotpot_eval/reports/trace/2026-06-01/`
- **follow-up tag**: `mechanism-candidate` + `anti-pattern`
- **probe ideas**:
  1. Implement top-K graph filtering (~1 day code) — expected
     graded +0.03-0.05
  2. Per-question-type routing — graph for multi-hop queries
     only, skip for comparison/temporal/null
  3. Query embedding similarity threshold in
     `engine.graph.rank_nodes`
- **immediate impact on α-6**: an engineering candidate that could
  shift the C_rag-graph cell verdict from "neutral" to "adopt"
  with one focused PR. Tagged for after Phase 2/3 completes (so
  the fix is informed by the cross-model data).

### 2026-06-01 — multihop-rag-citation-axis-jameses-only

- **bucket**: (a) — structural; JAMES's unique measurable contribution
- **cell context**: α-6 Phase 1, C_rag-graph → path 0 → 0.411 step
- **observation**: enabling S4 citation (bundled with S2+S3 in this
  batch, but isolated by C_rag-cited cell when next phase runs)
  drives path_coverage from 0.0 (no JAMES → no citation surface)
  to 0.411 (JAMES emits top-3 source documents per query). No
  regression on other axes from this layer.
- **surprise**: NO surprise — confirms JAMES's design. Worth
  promoting because *this is the one axis where vanilla LLM
  cannot compete by construction.* All other JAMES contributions
  are recoveries from RAG damage; the citation axis is JAMES's
  one-axis structural lead.
- **data pointer**: cell L1 carryover (C_rag-full) at path 0.419
  vs C_minus at 0.0
- **follow-up tag**: `mechanism-candidate` + `universal-law`
- **probe ideas**: Phase 2/3 confirms path axis is model-invariant
  (should be — it's a structural output, not a quality measure)
- **immediate impact on α-6**: publishable framing —
  *"JAMES's measurable structural contribution on MultiHop-RAG is
  path coverage +0.42 vs zero for the bare LLM. Quality axes are
  roughly LLM-equivalent at production tier."*

### 2026-06-01 — jameses-s5-s6-capability-floor-not-crutch

- **bucket**: (a) architecture + universal-law candidate
- **cell context**: α-6 Phase 2, M_M vs M_S comparison
- **observation**: at gemma4:e4b (M_M production), JAMES S5+S6
  layers recover +0.129 abst_f1 + +0.054 graded from RAG damage.
  At gemma3:4b (M_S small), the same layers produce **0.000**
  abst_f1 recovery and **degrade** graded by 0.070. The layers are
  mechanically engaged in both cells but produce measurable
  improvement only above a model-capacity floor.
- **surprise**: this REVERSES the original tier-gated routing
  hypothesis (small models gain more). The smaller model gains
  *less* — or actively loses ground.
- **data pointer**: Phase 2 analysis
  `reports/research-runs/alpha-6-phase-2-analysis-20260601.md`
- **follow-up tag**: `mechanism-candidate` + `universal-law`
- **probe ideas**: Phase 3a gemma3 scale ladder (1b / 4b / 12b /
  27b) to localize the capability floor; cross-family at qwen / llama / deepseek
- **immediate impact on α-6**: publishable framing — JAMES
  abstention layers are a *capability amplifier*, NOT a
  *small-model crutch*. The routing policy at M_S becomes "S4
  citation only; skip S5+S6 to save the 8.4× latency tax."

### 2026-06-01 — tier-conditional-rag-helps-small-hurts-large

- **bucket**: (b) model-context interaction
- **cell context**: α-6 Phase 1 + 2, C_minus → C_rag-basic transition
  at both M_M and M_S tiers
- **observation**: adding RAG retrieval to pure LLM yields **opposite**
  Δ on graded by tier:
  - M_M (gemma4:e4b): graded **-0.020** (Lost in the Middle)
  - M_S (gemma3:4b): graded **+0.043** (RAG compensates for
    weaker parametric knowledge)
- **surprise**: Lost-in-the-Middle is conditional on model capacity.
  Below the capability threshold, RAG context is genuinely
  informative; above it, RAG context becomes a distractor.
- **data pointer**: Phase 1 analysis (M_M) + Phase 2 analysis (M_S)
- **follow-up tag**: `mechanism-candidate`
- **probe ideas**: Phase 3a scale ladder to find the inversion
  point; Phase 3b cross-family to test family-specific inversion
- **immediate impact on α-6**: routing policy must be tier-aware.
  M_S → keep RAG on; M_M → RAG ON only with abstention layer to
  recover damage.

### 2026-06-01 — s4-citation-tier-invariant

- **bucket**: (a) architecture + universal-law candidate
- **cell context**: α-6 Phase 1 + 2 path_coverage comparison
- **observation**: S4 citation contributes +0.42 path at M_M and
  +0.397 path at M_S — nearly identical structural contribution
  across model scales.
- **surprise**: NOT a surprise. Citation is a structural output, not
  a quality measure — it should be model-invariant. Worth promoting
  because *this is the one axis where JAMES's contribution is
  measurable AND universal*.
- **data pointer**: Phase 1 + Phase 2 analyses
- **follow-up tag**: `universal-law`
- **probe ideas**: Phase 3b at qwen/llama/deepseek to confirm
  family-invariance
- **immediate impact on α-6**: S4 citation = JAMES's one
  unconditional contribution. Always-on at any tier.

### 2026-06-01 — jameses-rate-limit-corruption-arithmetic-step

- **bucket**: (a) measurement-side wiring + mechanism-candidate
- **cell context**: α-6 Phase 2 C_minus/M_S first run (corrupted)
- **observation**: server's per-IP rate limiter (30 req / 60 s)
  silently corrupted a cell whose model responded in sub-2s/query.
  70/100 queries got 429s; bench treated empty answers as
  abstentions; oracle computed apparent abst_f1 = 0.521 from what
  was actually rate-limit errors.
- **surprise**: the corrupted scores looked plausible. They
  fabricated "valid" abstention behavior. The catch was the
  **arithmetic step** of the 4-step rule: cell wall-clock 53s vs
  latency 1.71s × 100 = 171s expected. The math didn't add up.
- **data pointer**: post-mortem at
  `reports/research-runs/alpha-6-phase-2-rate-limit-corruption-postmortem-2026-06-01.md` (#671);
  fix at #672
- **follow-up tag**: `mechanism-candidate` (the lesson is the
  arithmetic step itself, not the specific bug)
- **probe ideas**: extend the 4-step rule's memory entry with the
  arithmetic step as a worked example
- **immediate impact on α-6**: cycle wrong-fix-averted count went
  from 7 to 8; the arithmetic step is the new fast catch for
  silent corruption. Future bench runs at sub-1s/query (Phase 3a
  gemma3:1b) would have corrupted entirely without this catch.

---

## Promoted to memory

When a finding is promoted to a memory entry (Step 10 trigger), record
the promotion here so the trail stays auditable:

| Date | Finding slug | Memory file | Confirmed by |
|---|---|---|---|

(none yet)

---

## Carry-over from prior tracks (for context — not new findings)

The following mechanism findings already landed in memory before α-5
runs. Listed here so a reviewer scanning this log understands what
"counts as a mechanism" in this project's history:

- `d3_e4b_floor_mechanism_thinking_trace` — gemma4:e4b's hidden
  thinking trace consumes ~85% of `num_predict` (#608 §16, PR #602).
  Promoted from an A3 observation to a cross-family law in #603/#604.
- `feedback_q15_chroma_embedding_root_pinned` — MiniLM struggles with
  proper-noun-mediated retrieval (F7/F9 cycle). Promoted to BL-9
  embedding swap.
- `feedback_bench_step7_chat_mode_passthrough` — IntentClassifier
  routes retrieval-mode bench queries to chat mode without the
  bearer token. Caused a measurement-bias correction.

These are the kinds of entries this log aims to seed.
