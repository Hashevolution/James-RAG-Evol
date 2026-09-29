# Multi-hop over-abstention: the model is right to refuse — it cannot see where or when anything was said (2026-09-29)

> **Question**: why do ~47% of answerable multi-hop questions end in a
> refusal (`plan-multihop-n3-20260929.md` §4), about half of them while
> naming the answer?
>
> **Data**: the plan-off arm of that run — the current production
> configuration (reflect off, plan off, verify on) — 3 runs × 100
> questions = 300 answers, **full** answers from `audit_log` rather than
> the oracle's 300-character preview, joined by question text. No new
> server run; read-only throughout.

## 1. What the refusals look like

| type | answerable | falsely refused |
|---|---:|---:|
| comparison | 75 | **58 (77%)** |
| temporal | 75 | **50 (67%)** |
| inference | 75 | 33 (44%) |
| null | (truth = absent) | — |

**125 of 141 refusals (89%) are the same line**:
`ANSWER: insufficient information`.

A strict version of "found it but refused" — the **exact dataset
answer**, whole-word, inside the refusal — can only be applied to
inference questions (comparison and temporal answers are "Yes"/"No",
which appear inside any text). There, **10 of 33** refusals name the
gold answer. The refusals say why:

> *"ANSWER: insufficient information — While the provided context
> describes **Sam Bankman-Fried** as the individual who oversaw the
> crypto exchange…, the context does not contain information confirming
> that this specific narrat[ive]…"* — Q5
>
> *"ANSWER: insufficient information — While the context confirms that
> **Google** spent billions ($26.3 billion) to become the default search
> engine, **it does not contain information from TechCrunch or The
> Verge** stating that…"* — Q11

MultiHop-RAG questions condition on the **outlet** ("as reported by both
The Verge and TechCrunch") and on **publication time**. The model finds
the entity and refuses because it cannot confirm the outlet.

## 2. Cause 1 — provenance does not reach the chunks

Each raw document carries its provenance in a header:

```
# In the end, the FTX trial was about the friends screwed along the way

Source: The Verge
URL: https://www.theverge.com/2023/10/26/…
Author: Elizabeth Lopatto
Published: 2023-10-26 12:00:00
```

Measured in `workspaces/hotpot_eval/chroma_db_bge_m3`:

- 185 documents → **5,464 chunks** (median 23 per document)
- chunks carrying the `Source:` line: **184 (3%)** — exactly one per
  document, the first; `Published:` identical
- chunk metadata keys: `category, owner, sensitivity, source,
  source_type` — `source` is the **filename**
  (`multihop_0121_In-the-end-the-FTX-trial…`), which holds neither outlet
  nor date

And the synth context (`pipeline_context.py`) lists those filenames
under `[관련 자료 목록]` and concatenates chunk text under
`[자료 내용]`. **For 97% of the evidence the model is shown, it has no
way to know which outlet wrote it or when.**

That also explains the type ordering: comparison questions contrast
what named outlets said, temporal questions compare publication dates —
both live only in the header. Inference questions condition on outlets
too, but less often decisively.

**Fixture fitness checked**: all **183 of 183** evidence articles for
the 100 questions are in the ingested corpus
(`feedback_fixture_fitness_before_verdict`). The evidence *text* is
available; the provenance is what is missing.

## 3. Cause 2 — a binary answer contract, applied by default

The refusal line is instructed, not invented. `TERSE_PRESET`
(`core/response_style_presets.py`):

> *\<answer\> = entity name, 'Yes', 'No', or 'insufficient information'* …
> *If the context lacks the answer: output only the first line
> 'ANSWER: insufficient information'.*

There is no slot for *"Google — though I could not confirm TechCrunch
reported it."* One unverifiable condition turns into a full refusal.

And terse is **not a benchmark setting**. `AnswerStyleClassifier`
(`core/answer_style_classifier.py`) auto-mounts it for short-answer
questions — who / what / when / yes-no — under `JAMES_AUTO_STYLE`,
default on. Neither `.env` nor the capture env names a style; the
classifier chose terse for these questions exactly as it would for a
user.

## 4. The diagnosis

Not synth being over-cautious. **The model is being appropriately
cautious about evidence it cannot see**, and the answer contract gives
it no way to be partially sure.

- Cause 1 manufactures the unverifiable condition.
- Cause 2 converts it into a refusal, often while the next line names
  the answer.

## 5. Two levers — and which to pull first

| | lever | what it changes | risk |
|---|---|---|---|
| **A** | carry provenance to the model — label each retrieved chunk with its document's source and date (context-time, flag-gated, no re-ingest), or write a header into every chunk at ingest | gives the model the information it is missing; its caution is untouched | low: adds true information, not a looser rule |
| **B** | let terse answer with a caveat instead of all-or-nothing | changes how uncertainty is expressed | high: this is an abstention dial (`feedback_abstention_dial_vs_pareto`) — plan's regression on null questions (#1165) is what loosening refusal looks like |

**A first**, context-time: smallest blast radius, no re-ingest, and it
tests the causal claim directly — if false refusals do not fall when the
model can see the outlet and date, this diagnosis is wrong. It must be
judged on **both** sides: false refusals on answerable questions **and**
abstention on the 25 null questions, where a helpful-looking change can
hide a hallucination increase.

## 6. What this licenses — and what it does not

**Licensed**

- On this corpus, 97% of chunks lack their document's outlet and date,
  and the synth context shows filenames, not provenance.
- 89% of multi-hop refusals are the terse refusal line, which the
  production-default style classifier selects for short-answer
  questions.
- The refusals state the unverifiable-outlet reason themselves (§1).

**Not licensed**

- ❌ "Fixing provenance will cut false refusals by N%." Untested — §5 A
  is the test.
- ❌ "Every refusal here is wrong." Some conditions may be genuinely
  unsupported; the strict count (10 of 33 inference refusals) is the
  firm number, the ~half from #1165 is loose.
- ❌ Any claim about the production corpus. Its documents are not built
  with `Source:` / `Published:` headers; whether provenance is lost there
  the same way was not measured. **Cause 2 does apply to production**;
  cause 1 is shown here for header-style documents.
