# MultiHop-RAG Paper Baseline — Comparison Plan (EEE)

> **Goal**: cross-reference α-5's JAMES numbers against published
> MultiHop-RAG baselines (Tang & Yang, EMNLP 2024, arXiv:2401.15391)
> so the publishable narrative §6 can quote *"JAMES vs vanilla
> LangChain + bge-large + GPT-4"* with both sides on the same axes
> rather than separate metric universes.
>
> **작성일**: 2026-05-31 PM (α-5 T1 background-running)
> **Companion**: α-5 publishable narrative §6.1 (corrected baseline
> numbers); α-6 design memo §"External baseline comparison"

---

## 0. TL;DR

MultiHop-RAG paper evaluates RAG systems on two separate planes:
- **Retrieval**: Hits@k, MAP@10, MRR@10 against **fact substrings**
  in retrieved documents
- **QA**: Precision / Recall / F1 / Accuracy at **word-intersection**
  level (NOT exact match) on extracted answers

JAMES α-5 measures **5 axes** including 2 the paper doesn't measure
at all (`abstention_f1`, `latency_cost`) and uses different
underlying matching for the path axis (slug + sources field, not
fact substring).

**Direct comparison is partially possible** on graded_answer
(roughly maps to their QA word-F1) and approximately on
path_coverage (their Hits@k semantics differ). **Abstention F1 is
JAMES-unique** — no paper baseline exists; this is a publishable
differentiator.

---

## 1. The paper's evaluation methodology (extracted from
`qa_evaluate.py` + `retrieval_evaluate.py` on
`github.com/yixuantt/MultiHop-RAG`)

### 1.1 Retrieval (`retrieval_evaluate.py`)

- **Metrics**: Hits@10, Hits@4, MAP@10, MRR@10. NDCG NOT computed.
- **Ground truth**: `gold_list[*].fact` — plain text fact strings,
  not document IDs.
- **Match**: substring (`gold_item in retrieved_item`) after
  whitespace normalisation. **Permissive matching** — text
  containing the fact anywhere counts as hit.

### 1.2 QA (`qa_evaluate.py`)

- **Metrics**: Precision / Recall / F1 / Accuracy across all
  queries.
- **Extraction regex**: answers are extracted via
  `r'The answer to the question is "(.*?)"'` — requires the
  system to format answers in this specific shape, or the
  extraction misses.
- **Match**: word-intersection (`has_intersection` = at least one
  shared word, case-insensitive). **Very permissive**.
- **No null_query special handling**: the script treats
  `comparison / inference / temporal / null_query` identically.
  Refusals don't get a separate axis.

### 1.3 Implication for direct comparison

The paper's QA metric is essentially **"did your answer mention
any keyword from the gold answer?"** This is much more permissive
than JAMES's graded_answer (atomic `gold_signals` recall) and
abstention_f1 (explicit refusal correctness). A JAMES `graded_answer`
of 0.327 likely maps to a higher paper-style accuracy (because their
metric only needs one-word overlap to count).

---

## 2. Paper's reported baselines (from the published tables; numbers
to be confirmed against the PDF when accessible — preliminary
mapping below)

The paper benchmarks several embedding models + several LLMs:

**Embedding models** (retrieval axis):
- voyage-2
- text-embedding-ada-002
- text-embedding-3-large / small
- bge-large-en-v1.5
- llm-embedder

**LLMs** (QA axis):
- GPT-4 (gpt-4-1106-preview)
- GPT-3.5-turbo
- Llama-2-70B
- Mixtral-8x7B
- Claude 2 (one version)
- Mistral-7B

**Caveat**: exact numbers require reading the PDF tables, which
is blocked by the WebFetch binary-PDF limitation in this session.
The plan below is structured so the operator can fill them in
later without rework.

| Configuration | Reported metric | JAMES α-5 equivalent | Mappable? |
|---|---|---|---|
| (paper) bge-large + GPT-4, Hits@4 | TBD% | path_coverage 0.419 | partial — semantics differ |
| (paper) GPT-4 QA Accuracy | TBD% | graded_answer 0.327 | yes — closest shape |
| (paper) Llama2-70B QA Accuracy | TBD% | (would need T2 measurement at M_L) | partial — JAMES uses local 12b not 70b |
| (paper) null_query handling | absent | abstention_f1 0.591 | NO — JAMES-unique axis |
| (paper) Latency reporting | absent | latency_cost 64s/query | NO — JAMES-unique axis |
| (paper) Token cost reporting | absent | token_cost 1150 chars | NO — JAMES-unique axis |

---

## 3. Mapping JAMES axes → paper axes

| JAMES axis | Paper closest | Comparability |
|---|---|---|
| `path_coverage` | Hits@k (with fact-substring matching) | LOW. JAMES matches on document-slug + sources field after normalisation; paper matches fact-string substring in retrieved text. Different ground truths. |
| `graded_answer` | QA word-intersection F1 / Accuracy | MEDIUM. Both are "did the answer touch the gold material?" Permissiveness differs (paper accepts 1 word, JAMES counts atomic claim hits / total). JAMES is stricter; expect JAMES number < paper number on same data. |
| `abstention_f1` | (none) | NONE. JAMES has explicit refusal-correctness axis; paper has no equivalent. This is JAMES's publishable differentiator. |
| `token_cost` | (none) | NONE. JAMES tracks answer chars + p95; paper doesn't surface this. |
| `latency_cost` | (none) | NONE. JAMES tracks per-query seconds; paper doesn't surface this. |

**The honest publishable claim**:

> JAMES on MultiHop-RAG balanced-100 produces `graded_answer 0.327`
> and `path_coverage 0.419` (corrected oracle). The paper's
> word-intersection accuracy and Hits@k metrics aren't byte-identical,
> so head-to-head comparison requires either (a) reproducing one of
> their baselines locally with their evaluation harness, or (b)
> running our 5-axis oracle on their baselines' raw outputs.
> Path (a) is cheaper (~1-2 days engineering) and is the next-cycle
> deliverable.

---

## 4. Reproduction plan (the "C" of α-5 prior recommendation)

### 4.1 Goal

Reproduce **one** paper baseline locally — the cheapest is
**bge-large + GPT-3.5-turbo** or **bge-large + Mistral-7B** — and
run BOTH evaluation suites:
- Their `qa_evaluate.py` on our output → number directly comparable
  to their reported baseline
- Our 5-axis oracle on the same output → number directly comparable
  to JAMES α-5 numbers

Cross-table tells whether the gap between JAMES and the paper's
baseline is **methodology** (different metric definitions) or
**system** (different RAG architecture).

### 4.2 Steps

1. **Set up paper's harness locally** (~2-3 h):
   - Clone `github.com/yixuantt/MultiHop-RAG`
   - Install their dependencies (likely LangChain + bge-large + LLM
     SDK)
   - Run their `retrieval_evaluate.py` on a sample to confirm we
     reproduce their published Hits@k numbers (within noise)

2. **Run a baseline configuration on MultiHop-RAG balanced-100**
   (the same 100 queries our α-5 baseline used) (~30 min compute):
   - Configuration: paper's vanilla LangChain + bge-large +
     **gemma4:e4b** (substitute for their LLM choices to keep model
     constant with JAMES)
   - Output: the answers + retrieved docs in a format both
     evaluators can consume

3. **Score the output** twice (~5 min):
   - `qa_evaluate.py` → paper-style F1 number
   - Our `qvt_rescore_baseline.py` adapted to read the paper's
     output format → 5-axis number

4. **Compare** (~15 min):
   - Same input, same LLM, different RAG stack
   - JAMES α-5 numbers vs reproduced-paper numbers
   - Establishes the **architectural delta**

### 4.3 Expected outcome shapes

**Outcome A (JAMES wins on its own axes, paper baseline wins on
their metric)**: methodology gap — both systems are doing what
they're designed for; comparison is direction-dependent. This is
the most likely outcome and is publishable: *"JAMES's
strict-grading + abstention metrics show 0.X precision where
permissive-grading baseline shows 0.Y; the metric pair tells two
sides of the same RAG."*

**Outcome B (JAMES wins on both axis families)**: strong claim —
the JAMES architecture is genuinely better, even when judged by
the paper's permissive metric. Direct evidence for the
"reasoning stack helps" claim.

**Outcome C (JAMES loses on the paper's metric too)**: honest
read — the JAMES architecture trades some metric performance for
audit-grade properties (the 0 lines of code change cycle the
publishable narrative emphasises). Still publishable, framing
shifts to "JAMES sacrifices N% raw accuracy for X% audit
property."

All three outcomes are publishable. The cycle's discipline is
that we **measure first, frame second**.

---

## 5. Effort vs leverage

| Step | Effort | Yield |
|---|---|---|
| 4.1 paper harness setup | 2-3 h | unblocks all comparisons |
| 4.2 one-baseline reproduction | 30 min compute + 30 min setup | the direct comparison data point |
| 4.3 cross-scoring | 5 min | numbers in both metric universes |
| 4.4 publish comparison memo | 1 h | reviewer-facing artifact |
| **Total** | **~5 hours** | **full cross-reference** |

This is significantly cheaper than re-running JAMES at multiple
configurations (~5.5h × N) and answers the *external credibility*
question (user req #4) cleanly.

---

## 6. Sequencing relative to α-6

This work is **independent of α-6 engineering pre**. It can run
in parallel while sector flags are landing or while T1 / T2 cells
are computing. The reproduction baseline becomes the **anchor
column** of the α-6 matrix render.

Recommended slot: between T1 completion and α-6 Phase 1 launch.

---

## 7. Position guard reminder

Per `memory/feedback_jameses_positioning_replayable_rag.md` §"정정
2026-05-31": **don't frame this comparison as "Replayable RAG
beats X."** Frame as: *"JAMES's 5-axis oracle (including the
abstention axis the paper doesn't measure) shows N on metric M;
reproducing the paper's baseline at the same LLM gives X on the
paper's word-intersection F1, Y on JAMES's strict graded_answer."*
Mother-platform identity stays primary in any externally-shared
comparison.

---

## 8. References

- Paper: Tang, Y., & Yang, Y. (2024). MultiHop-RAG: Benchmarking
  Retrieval-Augmented Generation for Multi-Hop Queries. *EMNLP
  2024 (also at COLM 2024)*. arXiv:2401.15391.
- Code: `github.com/yixuantt/MultiHop-RAG`
- Dataset: `huggingface.co/datasets/yixuantt/MultiHopRAG`
- Our equivalent: `eval/qvt/oracle.py` (5-axis), workspace at
  `workspaces/hotpot_eval/`
- α-5 corrected baseline: `baseline_3a961a3_rescored.json`
  (path 0.404 / graded 0.343 / abst_f1 0.704)
- α-6 design memo: `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md`
