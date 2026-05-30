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
