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

---

## Findings

<!-- Add entries below this line, newest at the bottom. -->

(none yet — populated as cells run)

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
