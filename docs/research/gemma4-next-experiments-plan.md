# gemma4:e4b Failure-Mode Research — Next Experiments Plan

> **Status**: open queue — 5 runnable experiments in priority order.
> **Audience**: any future session (or external collaborator) that
>   wants to add an in-house data point to the gemma4-feedback track.
> **Self-contained**: read this doc + run the commands → ship a
>   data point. No need to re-derive context.

---

## 0. TL;DR

`gemma4:e4b` has 2 in-house data points (2026-05-18 cognitive-stage
eval + 2026-05-21 extraction-prompt α-experiment) and 0 external
contributions on dev.to / X / Reddit. Both in-house points show
~60% empty / broken-JSON responses on short structured-output
prompts; neither isolates which of hypotheses A / B / C / D is
dominant. **Hypothesis space remains 4-wide; root cause unknown.**

This file queues 5 single-variable experiments that each isolate
one variable so a future session can drop them in one at a time
and watch the hypothesis space narrow.

Run order (by info-per-effort):

1. **β — gemma3:12b control n=10** (highest info per minute)
2. **γ — Prompt length isolation** (3-type vs 4-type)
3. **ε — `num_predict` explicit override** (isolates hypothesis B)
4. **δ — Language isolation** (KO vs EN doc + prompt — isolates C)
5. **ζ — Model-size sweep** (2b / 4b / 9b — isolates 4B family floor)

Each takes 5–15 min once the prerequisites are installed.

---

## 1. Context — what we know already

### 1.1 Data points so far (chronological)

| Date | Prompt domain | Calls | Empty / broken | Source |
|---|---|---:|---:|---|
| 2026-05-18 | cognitive stages (query_rewriter / planner / reflect / verify / fact_check) | 6 (1 each, 5 distinct stages) | 5 / 6 | `reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md` |
| 2026-05-21 | wiki extraction (PR-11b 4-type prompt) | 10 (same doc) | 6 / 10 | `docs/research/gemma4-event-emit-experiment-2026-05-21.md` |

### 1.2 Hypotheses (defined in `v0.3.x-gemma4-feedback-track.md`)

- **A** — meta-reasoning / short-structured-output capacity floor at 4B
- **B** — early stop-token emission (model hits EOS before JSON closes)
- **C** — Korean instruction + English JSON-schema mix confusion
- **D** — JAMES-side prompt truncation artefact

The 2026-05-21 experiment **weakened D** (prompt fits well under context),
**strengthened A + B** (same failure shape on a non-cognitive task),
**left C untested** (single language). No experiment to date has
separated A from B.

### 1.3 External feedback status

- dev.to: 0 substantive replies (challenge post still open)
- X / Reddit / GitHub issues: 0
- → **All evidence in this track is currently in-house.**

---

## 2. Self-evaluation of the 2026-05-21 α-experiment

What it added:

1. **Task-shape generalization** — the failure mode applies to
   extraction tasks, not just reasoning. Reframes hypothesis A from
   "meta-reasoning floor" to "short structured-JSON floor".
2. **Failure-distribution detail** — 60% empty / 30% no-event /
   10% success (was binary previously).
3. **Bundle value** — 2 internal data points cross-cite; future
   external reports can be triangulated against them.

What it didn't settle:

1. **A vs B** — both predict the 60% empty rate. The α-experiment
   can't separate them.
2. **No control** — `gemma3:12b` success rate is `1/1` from the
   PR-11b live verification, not `10/10`. Maybe 12B also fails
   sometimes; we don't know.
3. **Multiple variables changed at once** — between 2026-05-18
   and 2026-05-21 the prompt, doc, and call count all moved. No
   single-variable isolation.
4. **Operational redundancy** — the "use gemma3:12b" recommendation
   was already there from 2026-05-18. The α-experiment didn't
   change operations.

**Lesson for the next experiments**: each one must isolate **one**
variable. The runbooks in §5 follow this rule strictly.

---

## 3. Why the next experiments matter — hypothesis-by-hypothesis

| Experiment | A (4B floor) | B (early EOS) | C (KO/EN mix) | D (prompt trunc) |
|---|---|---|---|---|
| β — 12B n=10 control | ✅ pivotal — if 12B is 10/10, A's "4B floor" gap is real and quantified | indirect | indirect | indirect |
| γ — 3-type prompt n=10 | indirect | indirect | indirect | ✅ direct test (shorter prompt = less truncation pressure) |
| ε — num_predict override | indirect | ✅ direct test (B predicts "more tokens → fewer empties") | unaffected | indirect |
| δ — EN doc + EN prompt | indirect | unaffected | ✅ direct test (C predicts "remove KO → fewer empties") | unaffected |
| ζ — 2b / 4b / 9b sweep | ✅ direct test (A predicts monotone improvement with size) | confounded with A | unaffected | unaffected |

**Decision rule for stopping**: when 2 of A/B/C/D have direct
falsification evidence, the remaining 2 become the publishable
result.

---

## 4. Prerequisites (run-once for any experiment)

1. **JAMES checked out at main or later** (any commit ≥ `42a89ae`
   has the patched ingest path that lets event emit actually land
   on disk; earlier commits suffer the 2026-05-21 3-layer bug).
2. **Ollama running** on `127.0.0.1:11434`.
3. **Models pulled** for the experiment(s) you plan to run:
   ```powershell
   ollama pull gemma3:12b      # β, γ, ε, δ, ζ
   ollama pull gemma4:e4b      # all (already there)
   ollama pull gemma2:2b       # ζ only
   ollama pull gemma2:9b       # ζ only — note: gemma2, not gemma3/4
   ```
4. **Test wiki cleared** (the experiments use `source_type="test"`
   so prod wiki is untouched, but stale test entities can leak
   into trust-conflict noise — clean each round):
   ```powershell
   Remove-Item -Recurse -Force wiki/entity/test -ErrorAction SilentlyContinue
   ```
5. **`tmp/pr-11b-verify/` driver** still present (gitignored, but
   the scripts are reproducible from §5 of the
   `gemma4-event-emit-experiment-2026-05-21.md` memo if gone).

---

## 5. Experiment queue (runbooks)

Each experiment runs in ~5–15 min and writes its results JSON
under `tmp/pr-11b-verify/results/`. The result-reporting template
in §6 says exactly which fields to copy into this doc when done.

### 5.1 β — gemma3:12b control (n=10)

**Why first**: cheapest, biggest information increment, plugs the
biggest hole in the α-experiment.

**Hypothesis tested**: A (does 12B actually emit reliably?)

**Decision tree from the result**:
- 12B = 10/10 emit → A confirmed (4B floor is real & quantified)
- 12B = 7–9 / 10 → both 4B and 12B are unstable, just at different
  rates → reframe A as "size makes it better but doesn't fix it"
- 12B = 0–6 / 10 → A in doubt; the prompt itself might be the
  problem; γ / ε become more urgent

**Run**:
```powershell
cd C:\Project\James-RAG-Evol-v010
# Driver already exists at tmp/pr-11b-verify/repeat_extract.py
python tmp\pr-11b-verify\repeat_extract.py gemma3:12b 10
```

**Expected runtime**: ~2–3 min (12B is ~6–14 s per call vs 4B's ~15 s).

**Output to capture**:
- `event-emit runs: X / 10`
- `total events: Y`
- `per-run event count: [...]`
- JSON: `tmp/pr-11b-verify/results/repeat_gemma3_12b_n10.json`

---

### 5.2 γ — Prompt length isolation (3-type vs 4-type)

**Why second**: directly tests D (truncation) and rules out
"PR-11b made the prompt too long".

**Hypothesis tested**: D (prompt length / truncation) + indirectly A
(if 3-type also fails, A is more solid).

**Decision tree**:
- 3-type also 60%+ empty on gemma4:e4b → D ruled out; A or B
  dominant; the failure is **not** about the 4th type
- 3-type works (≥80%) on gemma4:e4b but 4-type fails → D confirmed;
  prompt length / new-type addition is the trigger
- Both fail at different rates → mixed; report rate delta

**Run** — requires a 1-line code variant. Easiest is a separate
script that constructs the 3-type prompt manually:

```python
# tmp/pr-11b-verify/repeat_extract_3type.py — sketch
# Use the OLD prompt (pre-PR-11b) by importing from a tag/commit:
#   git show 3a7aa33:core/wiki_generator.py > /tmp/wg_3type.py
# Or simply construct the 3-type prompt inline (copy from the
# pre-PR-11b version in git history) and call RouterWrapper("extract")
# directly with that prompt, skipping process_document_for_entities.
```

Run shape:
```powershell
python tmp\pr-11b-verify\repeat_extract_3type.py gemma4:e4b 10
```

**Output to capture**: same fields as β.

**Note**: this script does not exist yet — see §6 task list.

---

### 5.3 ε — `num_predict` explicit override

**Why third**: directly tests B (early stop-token emission).

**Hypothesis tested**: B (does forcing more output tokens reduce
the empty rate?)

**Decision tree**:
- num_predict=1024 → empty rate drops materially (e.g. 60% → 20%)
  → B confirmed; file Ollama issue / patch JAMES per-stage
  num_predict overrides
- num_predict=1024 → empty rate unchanged → B ruled out; A
  more likely; the model isn't running out of tokens, it's not
  starting

**Run** — requires modifying `llm/providers/ollama_client.py`
or the RouterWrapper to plumb `num_predict` through, OR calling
Ollama HTTP directly:

```powershell
# Direct Ollama call, bypassing JAMES wrapper:
# (sketch — script does not exist; see §6)
python tmp\pr-11b-verify\direct_ollama_num_predict.py gemma4:e4b 10 1024
```

The script should POST to `http://127.0.0.1:11434/api/generate`
with the PR-11b prompt body and `{"options": {"num_predict": 1024}}`.

**Output to capture**: same fields as β, plus the raw response
length per call (to verify the longer budget actually helped).

---

### 5.4 δ — Language isolation (KO vs EN)

**Why fourth**: directly tests C (Korean/English mix confusion).

**Hypothesis tested**: C (does an English-only prompt + doc cure
the failure?)

**Decision tree**:
- EN doc + EN prompt → empty rate drops materially → C
  confirmed; a Korean-aware prompt rewrite could help
- EN doc + EN prompt → same empty rate → C ruled out

**Run** — need EN versions of the doc and prompt:

```powershell
# Create tmp/pr-11b-verify/doc_a_event_with_date_EN.txt — translate
#   the existing doc_a content into English.
# Create tmp/pr-11b-verify/repeat_extract_EN_prompt.py — variant of
#   the driver that constructs an English-only prompt (translate
#   the TYPES block in core/wiki_generator.py:797 to English).
python tmp\pr-11b-verify\repeat_extract_EN_prompt.py gemma4:e4b 10
```

**Output to capture**: same fields as β, plus a side-by-side
comparison against the 2026-05-21 KO baseline.

---

### 5.5 ζ — Model-size sweep (gemma2:2b / gemma4:e4b / gemma2:9b)

**Why fifth**: tests A (size as the variable) cleanly.

**Hypothesis tested**: A (monotone improvement with size?)

**Decision tree** (after running 10 calls on each model):
- 2B << 4B << 9B (e.g. 0% / 10% / 70%) → A confirmed and quantified
  ("4B is the floor"; 7B+ recommended)
- 2B ≈ 4B << 9B → A confirmed but the floor is at 4B not 2B
  (Gemma's small models are equally limited)
- All three roughly equal → A in serious doubt; the family is the
  issue, not the size

**Run**:
```powershell
python tmp\pr-11b-verify\repeat_extract.py gemma2:2b   10
python tmp\pr-11b-verify\repeat_extract.py gemma4:e4b  10  # rerun for fresh sample
python tmp\pr-11b-verify\repeat_extract.py gemma2:9b   10
```

**Note**: `gemma2:9b` ≠ `gemma3:9b`. There's no `gemma3:9b` tag;
gemma3 family jumps from "12b" downward. The 9B comparison point
is from gemma2, which is an older family — confounds size with
family generation. Disclaim this in the result write-up.

**Expected runtime**: ~10 min total.

**Output to capture**: 3 JSON files + a comparison table.

---

## 6. Result-reporting template

When an experiment is done, append a section to **this file**:

```markdown
### Result — <experiment letter> (run on YYYY-MM-DD by <session ID>)

**Driver**: <path to script>
**Model(s)**: <list>
**Calls per model**: <N>

**Aggregate**:
| Metric | Value |
|---|---|
| event-emit runs (or relevant outcome) | X / N |
| empty / parse-fail runs | Y / N |
| other outcomes | ... |

**Per-run event count**: `[..., ..., ...]`

**Hypothesis verdict** (from §5's decision tree):
- A: confirmed / weakened / ruled out / no change
- B: ...
- C: ...
- D: ...

**Notes / surprises**: <2–5 lines max>

**Raw JSON**: `tmp/pr-11b-verify/results/<filename>`
```

Append to **§8** below as the results land. The chronology in §8
is the data — keep entries strictly append-only.

Also: append a 1-line entry to the "Internal evidence pile" table
in `docs/handovers/v0.3.x-gemma4-feedback-track.md` so the
handover stays in sync.

---

## 7. Task list — preflight needed before each experiment

| Task | Status | Owner | Notes |
|---|---|---|---|
| β driver — reuse existing `repeat_extract.py` | ready | any session | runs as-is |
| γ driver — `repeat_extract_3type.py` | NOT WRITTEN | next session | grab pre-PR-11b prompt from `git show 3a7aa33:core/wiki_generator.py` |
| ε driver — `direct_ollama_num_predict.py` | NOT WRITTEN | next session | bypass JAMES wrapper, post to Ollama directly |
| δ driver — `repeat_extract_EN_prompt.py` | NOT WRITTEN | next session | English-only prompt + English doc |
| ζ driver — reuse existing `repeat_extract.py` with different model args | ready | any session | needs `ollama pull gemma2:2b` + `gemma2:9b` first |

The next session can start with **β** (zero new code), capture a
result, and decide whether to invest the 10–20 min to write the
γ / ε / δ drivers.

---

## 8. Results log (append-only)

*Empty — no further experiments run as of 2026-05-21. The next
session should add results here in the order they land.*

---

## 9. When to stop / publish

The track gracefully exits when **any** of the following holds:

- Two of A / B / C / D are confidently falsified or confirmed by
  the table in §3.
- An external contributor on dev.to / X / GitHub independently
  reports a result that resolves one hypothesis.
- Upstream Gemma 4 / Ollama publishes a fix or version bump that
  changes the failure rate materially (re-run §5.1 and update).

At that point the eval report
(`reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md`) gets
a "Reader contributions" entry + the conclusion paragraph in this
doc gets a final form.

---

## 10. Cross-references

- `docs/research/gemma4-event-emit-experiment-2026-05-21.md` —
  the α-experiment that motivated this plan
- `docs/handovers/v0.3.x-gemma4-feedback-track.md` — the broader
  track + hypothesis A/B/C/D definitions + external-feedback
  routing
- `reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md` —
  the public fair-witness report (2026-05-18 baseline)
- `reports/promo-assets/devto-gemma4-challenge.md` — the public
  challenge that requested external feedback
- PR #371 (PR-11b) + PR #387 (3-layer wrapper fix) — the code
  context that surfaced the α-experiment

---

## 한국어 한 줄 결론

`gemma4:e4b` 가설 4개 (A 4B floor / B early EOS / C KO+EN mix /
D prompt 절단) 중 어떤 게 dominant 인지 단정 못 함 (2026-05-21
시점). 본 doc 은 **다음 세션이 그대로 돌릴 수 있는 5 실험**
(β 12B control / γ prompt 길이 / ε num_predict / δ 언어 / ζ
모델 크기) 의 runbook + 결정 트리 + 결과 기록 템플릿. 가장 cheap
+ 가장 큰 정보 = **β 가 first**. 결과는 §8 에 append-only 누적.
가설 2개가 falsify / confirm 되면 (`§9` 종료 조건) 트랙 마감.
