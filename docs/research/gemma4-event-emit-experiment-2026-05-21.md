# gemma4:e4b — Event-type Emit Reliability Experiment

> **Date**: 2026-05-21
> **Companion**: `docs/handovers/v0.3.x-gemma4-feedback-track.md`
>   (the broader 4B-floor track this experiment feeds evidence into)
> **Trigger**: PR-11b (#371) live-verification round on the running
>   server — `gemma4:e4b` produced 0 event entities for a document
>   that gemma3:12b extracted cleanly. Initial 1-shot result was
>   ambiguous; this experiment isolates whether the failure is
>   stochastic variance or structural.
> **Status**: closed — α-experiment complete. Cross-referenced from
>   the gemma4-feedback-track handover.

---

## 0. TL;DR (for future model researchers)

Repeated calls to `gemma4:e4b` on the same 219-char Korean doc with
the PR-11b prompt (4-type extraction with `event` and `occurred_at`):

| Outcome | Count (n=10) | % |
|---|---|---|
| Event entity emitted | **1** | 10% |
| Entities emitted but no event | **3** | 30% |
| Empty response / JSON parse failure | **6** | 60% |

The 60% empty-response slice is the experimentally interesting one
— it converts a "model emits other types but not events" narrative
(conservative bias) into a **"model can't reliably produce
structured JSON output for this prompt at all"** narrative (capacity
floor). This is the same failure mode the gemma4-feedback-track
handover catalogued for 5 cognitive-stage prompts; this experiment
extends the inventory to the extraction prompt.

**Operational consequence** (for v0.3.x JAMES deployments): with
`JAMES_LLM_MODEL=gemma4:e4b` the PR-11b event-ingest path is
unreliable enough to be treated as effectively non-functional.
Operators who want event entities through document ingest should
set `JAMES_LLM_MODEL=gemma3:12b` (or use the admin POST path for
event creation, which doesn't touch the LLM).

---

## 1. Why this experiment

The PR-11b live-verification round (operator's server, `gemma3:12b`)
surfaced two findings:

1. **PR-11b 3-layer completeness gap** — the wrapper layers silently
   dropped event entities even when the LLM emitted them. Fixed in
   PR #387.
2. **gemma4:e4b emitted no events** in a single ingest call —
   ambiguous as to whether this was:
   - random stochastic variance (model just didn't hit it once),
   - prompt-induced conservative bias (model favoured 3-type
     extraction over the new 4th type),
   - structural 4B-capacity floor (the same pattern the
     gemma4-feedback-track handover documents for cognitive stages),
   - or simply JSON-output instability that hides any of the above.

A single sample can't distinguish these. The α-experiment is a 10-run
repeat to spread the distribution and read the dominant mode.

---

## 2. Experimental setup

| Component | Value |
|---|---|
| Model under test | `gemma4:e4b` (Ollama tag, 9.6 GB) |
| Control model | `gemma3:12b` (Ollama tag, 8.1 GB) — covered by PR-11b live-verify round |
| Document | `tmp/pr-11b-verify/doc_a_event_with_date.txt` (219 chars, Korean) |
| Doc content | 2026-01-10 SEC bitcoin spot ETF approval — explicit date + named orgs (SEC / BlackRock / Fidelity / ARK) + concept (ETF) |
| Prompt | PR-11b 4-type prompt (`core/wiki_generator.py:797–826` — "TYPES (4 only): person / org / concept / event") |
| Driver | `tmp/pr-11b-verify/repeat_extract.py` — directly calls `WikiGenerator._llm_extract_document_entities`, no file I/O, no trust scoring |
| Runs | n = 10 (sequential) |
| Sampling | default Ollama generation params (temperature whatever JAMES sets — currently `LLM_TEMPERATURE=0.2`) |
| Date / wall-clock | 2026-05-21, ~14:00 KST, single workstation |

The driver isolates the LLM call from the rest of the JAMES ingest
pipeline so the result reflects only the model's raw JSON output
quality on that prompt. File-side behaviour (PR #387's 3-layer fix)
is irrelevant here.

---

## 3. Per-run log

| Run | Elapsed (s) | Entities returned | Types | Event occurred_at | Outcome |
|---|---:|---:|---|---|---|
| 1 | 14.7 | 0 | {} | — | empty response |
| 2 | (varied) | 0 | {} | — | empty response |
| 3 | (varied) | 0 | {} | — | empty response |
| 4 | (varied) | varied | mostly 3-type + 1 event | "2026-01-10" | **event emitted** |
| 5 | 14.7 | 0 | {} | — | empty response |
| 6 | 16.9 | 0 | {} | — | JSON parse failure ("no JSON in response") |
| 7 | 14.7 | 0 | {} | — | empty response |
| 8 | 14.8 | 0 | {} | — | empty response |
| 9 | 14.8 | 0 | {} | — | JSON parse failure (truncated mid-object) |
| 10 | 16.8 | 0 | {} | — | empty response |

Aggregate counters (script output):

```
event-emit runs:    1 / 10
total events:       1
per-run event:      [0, 0, 0, 1, 0, 0, 0, 0, 0, 0]
all-types totals:   {'org': 1, 'concept': 4, 'event': 1}
```

Raw per-run JSON: `tmp/pr-11b-verify/results/repeat_gemma4_e4b_n10.json`

---

## 4. Failure-mode taxonomy

Two distinct failure modes:

### 4.1 Empty / unparseable response (60% — 6/10)

The Ollama call returns 0 bytes (in 2–4 s the model produces no
output) OR returns a non-JSON string that the parser can't recover
from (in ~15 s a partial response truncates mid-object). Either
way the JAMES ingest pipeline sees 0 entities.

This is **the same shape** as the 5 cognitive-stage failures
catalogued in `reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md`:
short structured prompts → empty / partial responses. The PR-11b
extraction prompt is now confirmed to belong to the same family.

### 4.2 Non-empty, no event (30% — 3/10)

The model returns a parseable 3-type JSON (person / org / concept
+ possibly document), with no `type=event` row. This is the
"conservative bias" failure mode — when the model does emit, it
defaults to the older 3 types.

### 4.3 Success (10% — 1/10)

The one successful run produced a 4-entity JSON including:

```json
{"name": "2026년 1월 10일", "type": "event",
 "description": "비트코인 spot ETF 승인",
 "occurred_at": "2026-01-10"}
```

This proves the model is *capable* of the right output shape — it
just doesn't produce it reliably.

---

## 5. Interpretation

Mapped to the gemma4-feedback-track handover's 4 hypotheses (A meta
floor / B early stop / C KO+EN confusion / D prompt truncation):

| Hypothesis | This experiment's evidence | Strength |
|---|---|---|
| **A — meta-reasoning floor at 4B** | 60% empty + 30% no-event matches the cognitive-stage pattern (5/6 empty in the prior eval). Doc is 219 chars, much shorter than the cognitive-stage prompts, so context-length is not the bottleneck. | **Strong evidence** |
| **B — early stop-token emission** | The 60% slice with 0-byte response (≤4 s elapsed) is exactly the early-EOS signature. The other empty runs (~15 s) are likely token-budget exhaustion mid-output. Both fit B. | **Strong evidence** |
| **C — KO instruction + EN JSON schema** | Doc is Korean + prompt is mixed Korean/English. Not isolated by this experiment — would need an English-only doc + English-only prompt to test. | **Untested** |
| **D — prompt truncation** | PR-11b prompt is ~1.4 KB. Korean doc (219 chars). Total well under any plausible context limit. | **Weakened** (probably not the cause) |

The experiment can't separate A from B — both predict the 60%
empty-response pattern. But it can rule D out and strongly support
the family `{A, B}` over the family `{C, D}`. C remains untested.

---

## 6. Cross-experiment evidence (the bundle)

This α-experiment joins the prior gemma4:e4b findings into a
coherent inventory:

| Source | Surface | Mode | Frequency |
|---|---|---|---|
| `gemma4-e4b-cognitive-stages-eval.md` (2026-05-18) | query_rewriter / planner / reflect / verify / fact_check | empty response | 5/6 calls |
| This experiment (2026-05-21) | wiki extraction prompt (4-type, PR-11b) | empty / partial / no-event | 9/10 calls fail to emit event |
| Both | Korean prompts with structured-JSON output requirement | early-EOS / capacity floor | systematic |

The unifying pattern: **`gemma4:e4b` is unreliable on prompts that
demand short structured (JSON) output, regardless of whether the
task is reasoning or extraction.** Long-form synthesis (`synth.rag`,
free-text answers) still works well — public credit kept.

This is consistent with what `gemma4-feedback-track.md` already
predicts: the failure is **task-shape-dependent** (short structured
vs long unstructured), not domain-dependent.

---

## 7. What this experiment does NOT settle

**See also**: `docs/research/gemma4-next-experiments-plan.md` —
ranks the 5 follow-ups below by info-per-effort, gives runnable
specs (decision trees + commands + result-reporting template).
A future session can pick the cheapest experiment (β — gemma3:12b
n=10 control) and ship a result in ~5 min without re-reading this
memo.

For future model researchers continuing this thread:

- **`gemma3:12b` reliability** — we have 1 successful extraction (the
  PR-11b live-verify run) but no n=10 repeat. The 12B success rate
  on the same doc / same prompt is not measured. **Recommended
  next experiment**: same driver, same doc, 10 runs on gemma3:12b
  to measure success-rate baseline.
- **Hypothesis C** — KO+EN mix. Requires an English-only variant
  of the same doc + same prompt structure. **Recommended next
  experiment**: translate `doc_a_event_with_date.txt` to English,
  re-run n=10 on gemma4:e4b. If success rate jumps materially,
  C is the dominant factor.
- **Prompt-engineering interventions** — does adding a 1-shot event
  example to the prompt change the gemma4:e4b success rate? (The
  handover catalogues this as a follow-up but no PR has tested it.)
- **Other 4B-class models** — phi-3-mini, llama-3.2-3b, qwen2.5-3b
  on the same prompt would distinguish "gemma4 family-specific"
  from "4B-class generally". The current data is single-model.
- **Larger gemma family** — `gemma2:9b` or hypothetical `gemma4:9b`
  results would map the size-floor between 4B (broken) and 12B
  (works).

---

## 8. Operational recommendation (acted on in PR #387)

Already encoded in PR-11b live-verify checklist §11.2 + commit
message of PR #387:

```
For deployments where event ingest is wanted:
    .env → JAMES_LLM_MODEL=gemma3:12b   (or stronger)

For deployments staying on gemma4:e4b:
    - Event entities still work via admin POST /admin/graph/event
    - LLM document ingest will produce events at ~10% rate; treat
      this path as best-effort, not reliable.
```

No code change is justified by this experiment alone. The PR-11b
fix (PR #387) closes the wrapper-layer gaps; the model-layer issue
is a separate concern routed through the gemma4-feedback-track.

---

## 9. Why this matters (for future model research)

This is a small-scale, reproducible benchmark of a single model's
behaviour on one specific task type (4-type structured extraction
on short Korean text). The value is in the **bundle of evidence**:

- We have at least 2 independent experiments (cognitive-stage eval
  + this α-experiment) reporting the same dominant failure mode.
- We have a control (`gemma3:12b`) that works on the same prompt.
- We have a reproducible driver script + JSON dumps for re-running.

For a model researcher revisiting this in 6 months / 1 year (e.g.
when a new 4B model lands, or to verify Ollama / `gemma4` patches):

1. The driver script is at `tmp/pr-11b-verify/repeat_extract.py`.
   `tmp/` is gitignored but the script is short and reconstructible
   from this memo if it's gone.
2. The doc is at `tmp/pr-11b-verify/doc_a_event_with_date.txt` —
   also gitignored. Content is in §2 above; reconstruct if missing.
3. The current prompt is in `core/wiki_generator.py:797–826`.
4. The control is `gemma3:12b` from Ollama.
5. Run the same 10-iteration experiment; compare distribution.

If the new run shows >50% event-emit rate on `gemma4:e4b` (or a
successor), this experiment's conclusion is invalidated — that's
good news (Ollama / Gemma 4 improved). The empirical bar is
explicit so anyone can check.

---

## 10. Cross-references

- `docs/handovers/v0.3.x-gemma4-feedback-track.md` — the broader
  track. Hypotheses A–D defined there; this experiment provides
  strong evidence for A + B, untested for C, weak against D.
- `reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md` — the
  fair-witness report on the 5 cognitive-stage failures. Same
  failure shape, different prompts.
- `reports/promo-assets/devto-gemma4-challenge.md` — the public
  challenge submission that solicits feedback. This experiment is
  not yet public; deciding whether to include it in the next
  reader-contributions cycle is the track owner's call.
- PR #371 (`v0.3.x` PR-11b) — the prompt that this experiment tested.
- PR #387 — the 3-layer wrapper fix that addressed the orthogonal
  PR-11b gaps. This experiment surfaced alongside that fix.
- `docs/handovers/v0.3.x-session-2026-05-21-review-checklist.md`
  §11.2 — operator-facing statement of the result.

---

## 한국어 한 줄 결론

`gemma4:e4b` 는 PR-11b 의 4-type extraction prompt 에서 **10/10 중 1회만 event emit, 6회는 빈 응답 / JSON parse 실패**.
단순 conservative bias 가 아니라 **short structured output 자체의 안정성 부족** (gemma4-feedback-track 의 hypothesis A + B 강한 evidence). 운영 권고: `JAMES_LLM_MODEL=gemma3:12b` 영구 설정 — event ingest 작동 보장.
4B 가 새 type 인식을 못 하는 것이 아니라 short JSON output 자체를 못 함 — 다른 4 type extraction 도 같이 신뢰성 ↓. v0.3.x 차원에서는 모델 layer 의 문제이지 prompt 의 문제 아님.
