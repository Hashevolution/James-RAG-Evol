# gemma4:e4b Experiment Validation Plan

> **Date**: 2026-05-21
> **Companion artefacts** (read these first):
>   1. `docs/research/gemma4-event-emit-experiment-2026-05-21.md` —
>      α-experiment (what we did, n=10)
>   2. `docs/research/gemma4-next-experiments-plan.md` —
>      original 5-experiment runbook (β / γ / δ / ε / ζ)
>   3. `reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md` —
>      first internal data point (2026-05-18)
>   4. `reports/promo-assets/devto-gemma4-write-track.md` —
>      public dev.to article (`/5-empty-responses…-1ggd`)
> **Status**: open — methodology critique + refined design
> **Audience**: the next session running gemma4:e4b hypothesis experiments
> **Naming convention**: Greek letters (α/β/…) = original runbook
>   experiments; V-prefix (V1/V2/…) = refined experiments in this doc.
>   Greek-to-V mapping in §4.

---

## 0. TL;DR

The existing 5-experiment runbook is structurally sound (each
experiment maps to one hypothesis, each has a decision tree), but
joint reading of the 4 artefacts above surfaces **6 methodology
gaps + 1 missing hypothesis** that would let the conclusions be
challenged on review:

1. **Statistical power**: n=10 with observed ~60% empty rate has a
   95% CI of roughly [0.31, 0.83]. Two experiments at n=10 can
   return results whose CIs overlap fully — every hypothesis stays
   alive.
2. **Confounded variables**: γ mixes prompt length with the 4th
   entity type itself; δ mixes prompt language with JSON-key
   language; ζ mixes parameter size with model-family generation
   (gemma2 vs gemma4).
3. **"Empty" is two distinct failure modes**: α-experiment §4.1
   distinguishes 0-byte-at-<5s (early EOS) from ~15s-partial-truncate
   (token budget). These have different root causes; the runbook
   collapses them and loses the resolution.
4. **No temperature / determinism control**: α used temp=0.2 only.
   A temp=0 multi-seed run separates "structural refusal" from
   "sampling variance."
5. **Experiment dependencies not encoded**: 5 experiments are
   listed by info-per-effort but run as if independent. In fact β
   should gate ζ (no point sweeping sizes if 12B itself is shaky),
   and ε should gate γ (if num_predict fixes it, prompt-length is
   moot).
6. **External-feedback gating absent**: dev.to article asks 5
   questions; runbook doesn't say which inbound replies re-prioritise
   which experiments.
7. **Missing hypothesis E** — `<think>`-tag post-processing: see §3.

This document does **not** replace the runbook. It adds methodology
guardrails, 2 new experiments (V6 sub-mode taxonomy, V7 temperature
sweep), 1 cross-experiment decision tree, and pre-registered
stopping criteria.

**Recommended first action**: run V1 + V6 + V7 in parallel
(~30 min total wall-clock on a single workstation). Everything
else branches off their results.

---

## 1. Joint reading of the 4 artefacts

| Artefact | Domain | Sample | Empty rate | Hypothesis support |
|---|---|---|---|---|
| 2026-05-18 cognitive-stages eval | 5 meta-stages (rewrite / plan / web-summary / critique / fact-check) | 6 calls, 5 distinct stages | 5/6 | A + B (strong); C plausible; D possible-for-1 |
| 2026-05-21 α-experiment | wiki extraction (PR-11b 4-type prompt) | 10 (same doc) | 6/10 + 3/10 no-event | A + B (strong); D weakened (prompt fits) |
| dev.to article (public, 2026-05-18) | same as cognitive-stages eval | (publishes the above) | — | requests external data on all 5 Qs |
| External replies | — | 0 as of 2026-05-21 | — | — |

**Triangulation**: two internal data points across distinct prompt
domains (cognitive vs extraction) show the **same ~60% empty rate
on short structured-JSON outputs**. This makes the failure
task-shape-dependent, not domain-dependent — i.e. hypothesis A
generalises beyond "meta-reasoning" to "short structured JSON in
general." The dev.to article documents this honestly and explicitly
defers root-cause identification.

---

## 2. Six methodology gaps (with concrete fixes)

### 2.1 Statistical power

n=10 at observed p=0.6 → Wilson 95% CI ≈ [0.31, 0.83].
If β returns "12B = 7/10" (rate 0.7, CI [0.40, 0.89]) and α was
"4B = 1/10" (rate 0.1, CI [0.02, 0.40]), the CIs are non-overlapping
and A is confirmed. But "12B = 9/10" vs "4B = 4/10" → CIs overlap;
conclusion ambiguous.

**Fix**: n=30 for headline experiments (V1, V6); n=20 for
secondary (V2, V3, V7); n=15 per cell for factorial (V4, V5).
At n=30 + p=0.9 the CI is [0.74, 0.97] — clean separation.

### 2.2 Confounded variables

| Original | What it confounds | Fix |
|---|---|---|
| γ (3-type vs 4-type) | prompt length × addition of new type label × addition of new exemplar | V4 = 3 sub-variants (γ'.a / γ'.b / γ'.c) — see §4.4 |
| δ (KO vs EN) | language of instruction × language of JSON keys × language of doc content | V5 = 2×2 design — see §4.5 |
| ζ (size sweep) | parameter count × model-family generation (gemma2 vs gemma4) | V2 = stay inside gemma3 family (1b / 4b / 12b); add gemma2 as separate comparison |

### 2.3 "Empty" is two distinct failure modes

α-experiment §4.1 distinguishes but doesn't isolate:

| Sub-mode | Signature | Likely cause |
|---|---|---|
| **Empty-Immediate** | 0-byte response, elapsed 2–4 s | Hypothesis B (early EOS) OR new E (`<think>`-only output stripped to 0) |
| **Empty-Truncated** | partial JSON, elapsed ~15 s, `done_reason=length` | Hypothesis B-budget (token budget exhausted) OR A (capacity) |
| **Parseable-no-event** | full JSON, no `type=event` row | Hypothesis A-flavor (conservative bias / new-type unfamiliarity) |
| **Success** | full JSON, includes event | — |

**Fix**: V6 taxonomy run instruments the driver to record per-call
`(elapsed_s, response_bytes, ollama_done_reason, parse_ok,
entity_count, event_emitted, raw_response_sha256)`. The
`done_reason` field is already in the Ollama HTTP response payload
— one-line code change in the driver.

### 2.4 No temperature / determinism control

α used `LLM_TEMPERATURE=0.2`. Without a temp=0 run we can't tell
if the 60% empty rate is **stochastic** (sampling sometimes lands
on EOS) or **structural** (model deterministically refuses on this
prompt). At temp=0:

- 0/N events → deterministic refusal (model has a fixed forbidden
  path for this prompt)
- ~1/N events (matches the 0.2 baseline) → temp isn't the variable
- Higher rate than 0.2 → unusual but possible (Ollama temp=0 is a
  hint, not a guarantee)

At temp=0.7 (V7) we test the inverse: does sampling diversity
unblock rare success modes?

**Fix**: V7 = (0.0 / 0.2 / 0.7) × n=20 each.

### 2.5 Experiment dependencies

The runbook orders 5 experiments by info-per-effort, but each is
run "independently." In practice, V1's result changes what V2
means (no point in size sweep if 12B itself is unreliable). §5
encodes this as a decision tree.

### 2.6 External feedback gating

dev.to article asks 5 specific questions. The runbook has no
"if reply Q matches, re-prioritise to experiment X" mapping. §6
provides one.

---

## 3. Missing hypothesis: E — `<think>`-tag post-processing

`core/gemma_client.py:283–309` strips `<think>...</think>` blocks
from every Ollama response, then attempts 3 fallback recovery
stages if the strip leaves the output empty. The recovery is robust
**when the response has a proper `</think>` closing tag**, but:

- If gemma4:e4b emits an unbalanced `<think>` (open with no close),
  the regex `r'<think>.*?</think>'` is non-greedy and matches
  nothing — but the `</think>` fallback (line 290) also fails.
  Final result: stage 3 tries `<think>(.*?)</think>` (greedy
  internal), also fails, → `[Gemma 응답 없음]`.
- If gemma4:e4b emits **only** `<think>some-reasoning</think>`
  with no after-tag content, recovery stage 2 returns empty;
  stage 3 picks the last 2 sentences of the `<think>` body — but
  if the body itself is just CoT prose, the "recovery" is
  semantically wrong (the model never actually produced a JSON
  answer; we're feeding the CoT as if it were the answer).

The α-experiment driver calls `_llm_extract_document_entities`
→ `call_router(task_type="extract")` → `gemma_client.py` (the
think-stripping path). So **hypothesis E is in scope for the
α-experiment**.

**E is not currently in the 4-hypothesis space**. It needs its own
isolation experiment:

- **V8 (deferred)**: run the α-experiment driver with the
  think-stripping path bypassed (raw Ollama response captured
  verbatim). If raw response is non-empty for the 60% "empty"
  runs, E is the cause; if raw response is also 0 bytes, B-
  immediate still dominant.

V8 is deferred because the 1-line driver patch isn't blocking
V1/V6/V7. It is the first thing to run **after** the headline
batch lands.

---

## 4. Refined experiment queue (7 experiments)

Naming: V1 ← refines β; V2 ← refines ζ; V3 ← refines ε; V4 ←
refines γ; V5 ← refines δ; V6/V7 are new. V8 is the E-hypothesis
follow-up from §3.

### 4.1 V1 — 12B control (n=30)

**Refines**: β.
**Hypothesis**: A (does 12B emit reliably at scale?).
**Run**: `python tmp/pr-11b-verify/repeat_extract.py gemma3:12b 30`
(same driver, n bumped from 10 to 30).
**Instrumentation**: ensure the per-call JSON includes elapsed_s,
response_bytes, ollama_done_reason.
**Decision** (see §5 tree):
- ≥27/30 events → A quantitatively confirmed; run V2 for size floor
- 18–26/30 → 12B also unstable, different rate; run V3
- ≤17/30 → A in doubt; V4 (prompt isolation) becomes urgent

**Expected runtime**: ~5 min.

### 4.2 V2 — Same-family size sweep (gemma3:1b / 4b / 12b, n=20 each)

**Refines**: ζ. Eliminates the gemma2/gemma4 family confound.
**Hypothesis**: A (monotone size → success rate?).
**Prerequisite**: `ollama pull gemma3:1b gemma3:4b`. (gemma3:12b
already pulled per V1.)
**Note**: there is no gemma3:e4b — gemma3 family doesn't have the
"efficient" variants. So the sweep is *parameter-count, same
family generation*. Gemma4 family separately compared via the
existing α data + ζ's gemma2 numbers as additional disclosed
comparison points.
**Decision tree**:
- Monotone (1b ≪ 4b ≪ 12b) → A confirmed, floor quantified
- 1b ≈ 4b ≪ 12b → floor is between 4b and 12b
- Flat → A in serious doubt; the issue is per-family or
  per-prompt-shape, not size

**Expected runtime**: ~12 min total.

### 4.3 V3 — num_predict + temperature combo (3 sub-runs, n=20 each)

**Refines**: ε + adds temperature axis.
**Hypothesis**: B (does forcing budget / determinism move the
needle?).
**Sub-runs**:
- V3.a: num_predict=1024, temp=0.2 (original ε)
- V3.b: num_predict=512, temp=0.0 (low-budget + deterministic)
- V3.c: num_predict=2048, temp=0.2 (max-out budget)

**Note**: `gemma_client.py:253` already defaults to 8192 num_predict
— so the "empty" responses **cannot** be num_predict-limited at
the JAMES layer. V3 should call Ollama HTTP directly (bypassing
the JAMES wrapper) to test whether *Ollama's own* budget
interpretation matters for empty-immediate vs empty-truncated
sub-modes. Sketch:

```python
# tmp/pr-11b-verify/direct_ollama.py — bypasses gemma_client.py
import requests, json
resp = requests.post(
    "http://127.0.0.1:11434/api/generate",
    json={"model": "gemma4:e4b", "prompt": PROMPT, "stream": False,
          "options": {"num_predict": 1024, "temperature": 0.0}},
)
print(resp.json())   # captures done_reason verbatim
```

**Decision tree splits by sub-mode** (from V6):
- empty-immediate rate unchanged across all 3 → B-immediate ruled out
- empty-truncated rate drops at V3.c → B-budget confirmed
- success rate jumps at V3.b (temp=0) → determinism helps; sampling
  was hurting

### 4.4 V4 — Length / type isolation (3 variants, n=15 each)

**Refines**: γ. Decomposes the "3-type vs 4-type" confound.

| Variant | Prompt | What it tests |
|---|---|---|
| V4.a | original pre-PR-11b 3-type prompt (from `git show 3a7aa33:core/wiki_generator.py`) | Baseline — does old prompt work? |
| V4.b | 3-type prompt **padded** to match 4-type total length | Pure length effect |
| V4.c | 4-type prompt with the `event` exemplar line removed (still mentions "event" as a type) | Knowledge of the type vs the exemplar |

**Decision tree**:
- a passes, b passes, c fails → 4th-type exemplar is the issue
- a passes, b fails, c fails → length is the issue (D-flavor)
- a fails too → not a γ-track problem; back to V1/V2

### 4.5 V5 — Language 2×2 (4 cells, n=15 each)

**Refines**: δ. Decomposes the "KO + EN" confound.

| Cell | Doc | Instruction | Keys | What it tests |
|---|---|---|---|---|
| V5.a | KO | KO | EN | Baseline (current α-experiment) |
| V5.b | KO | KO | KO (`{"이름", "유형"}`) | Key-language effect |
| V5.c | EN | EN | EN | Full-EN baseline |
| V5.d | KO | EN | EN | Instruction-language effect |

**Decision tree**:
- V5.a fails, V5.b passes → JSON-key language is the issue
- V5.a fails, V5.c passes, V5.b fails → both instruction and keys
  contribute
- All four fail at the same rate → C ruled out

### 4.6 V6 — Sub-mode taxonomy (n=50 on baseline) — NEW

**Why new**: α-experiment had n=10, 6 "empty" responses lumped
together. At n=50 we expect ~30 failures, large enough to estimate
the proportion of empty-immediate vs empty-truncated vs
parseable-no-event with ≤±10% CI.

**Driver change** (1 line): record `ollama_done_reason`. Outcome
is a fixed-form failure-mode histogram used by all other
experiments' decision trees.

**Cost**: ~15 min sequential on gemma4:e4b.

### 4.7 V7 — Temperature sweep (n=20 × 3 temps) — NEW

**Temps**: 0.0 / 0.2 / 0.7.
**Hypothesis**: distinguishes structural refusal from sampling
variance (see §2.4).

**Decision tree**:
- All three temps show similar failure rate → A (capacity)
  confirmed, sampling is not the variable
- temp=0 has higher failure rate than 0.2 → 0.2's variance was
  what occasionally rescued the model; A confirmed with
  sampling-flavor
- temp=0.7 has materially lower failure rate → high-temp sampling
  recovers rare success modes; suggests the model has the
  capability but the default decoding misses it

---

## 5. Cross-experiment decision tree

```
                     ┌─────────────────────┐
                     │ V1 + V6 + V7        │
                     │ (parallel, ~30 min) │
                     └──────────┬──────────┘
                                │
       ┌────────────────────────┼─────────────────────────┐
       ▼                        ▼                         ▼
   V1: 12B reliable?      V6: sub-modes?              V7: temp?
       │                        │                         │
   ┌───┴───┐            ┌───────┼─────────┐         ┌─────┼─────┐
   │       │            │       │         │         │     │     │
  ≥27/30  ≤26/30   empty-imm  trunc   no-event   flat   t=0 worse  t=0.7 better
   ↓       ↓        dominant  dominant  dominant  ↓        ↓          ↓
   A       A in     E or B-   B-budget  A (cons.) A      A+sampling  capability
   conf.   doubt    immediate    ↓      bias)     conf.  flavor      latent
   ↓       ↓        ↓ run V8  run V3.c  ↓                            ↓
  run V2   run V4   first     first   run V4                       run V3.b
                                              (does 1-shot help?)

Optional / follow-up:
   V8 — bypass <think>-strip → tests hypothesis E
   V5 — language 2×2 — only if V4 also passes (i.e. prompt content
        not the variable but baseline still fails)
   V3.a/V3.b/V3.c remaining — run for completeness once dominant
        sub-mode known
```

---

## 6. Pre-registered stopping criteria

Stop and publish the result when **any one** of:

1. **Confirmation**: 2 of {A, B, C, D, E} have direct supporting
   evidence:
   - V1 ≥27/30 + V2 monotone → A confirmed
   - V6 ≥70% empty-immediate + V8 raw-response-non-empty → E confirmed
   - V6 ≥70% empty-truncated + V3.c rate-drop → B-budget confirmed
   - V4 length-effect significant → D confirmed
   - V5 cell-difference significant → C confirmed

2. **Falsification**: 2 of {A, B, C, D, E} ruled out (Cl 95% non-
   overlap with the failing baseline):
   - V1 ≤17/30 → A weakened (12B also unstable)
   - V3 all sub-runs flat → B ruled out
   - V5 all cells fail equally → C ruled out
   - V4 all variants fail equally → D ruled out
   - V8 raw response also 0-byte → E ruled out

3. **Resource exhaustion**: V1 + V6 + V7 + V8 (the 4 cheapest)
   all run with no signal → escalate by filing an Ollama / Gemma
   upstream issue with the full data bundle.

4. **External resolution**: a dev.to / X / GitHub reply provides
   falsifying data on any single hypothesis → re-run only the
   affected experiment to verify, then update the report.

The chronology in `gemma4-next-experiments-plan.md §8` (append-only
results log) is the data; do not edit prior entries.

---

## 7. External feedback integration (dev.to / X / GitHub)

The dev.to article (`5-empty-responses-from-gemma4e4b-4-hypotheses-0-root-cause-1ggd`)
asks 5 questions. Each maps to an experiment re-prioritisation:

| dev.to Q | Maps to | Re-prioritise if reply says |
|---|---|---|
| Q1: Have you seen the same pattern? | (confirmation only) | ≥3 confirmations → V6 lower priority (failure is well-attested); focus on V1 + V4 |
| Q2: Did a prompt change rescue it? | V4 | A specific change named → add as V4.d variant |
| Q3: Does e2b show the same? | V2 | e2b also fails → expand V2 to include gemma4:e2b |
| Q4: Does 31b / 26b-moe behave? | V2 | 31b passes → A confirmed; skip V2 lower-end |
| Q5: Known Ollama + Gemma 4 issue? | (escalation) | Yes → cite + re-run V1 only |

All replies append to:
- `reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md` "Reader
  contributions" section (template in `docs/handovers/v0.3.x-gemma4-feedback-track.md`)
- `gemma4-next-experiments-plan.md §8` (with hypothesis tag)

---

## 8. Driver instrumentation upgrade

The current `tmp/pr-11b-verify/repeat_extract.py` (per α-experiment
§9) needs **one schema extension** for every experiment below to
produce comparable data. Per-call JSON record:

```json
{
  "run_idx": 4,
  "model": "gemma4:e4b",
  "elapsed_s": 15.2,
  "response_bytes": 0,
  "ollama_done_reason": "stop",
  "parse_ok": false,
  "entity_count": 0,
  "event_emitted": false,
  "failure_mode": "zero_byte_early",
  "raw_response_sha256": "<hex>",
  "temperature": 0.2,
  "num_predict": 8192
}
```

`failure_mode` ∈ {`success`, `zero_byte_early` (<5s, 0 bytes),
`partial_truncate` (>10s, parse fails), `no_event_parseable`
(parse ok, no event row), `other`}.

The 1-line code change reads `done_reason` from the Ollama
`/api/generate` response. Backwards compatible with existing JSON
dumps (additional fields ignored by old readers).

---

## 9. CLAUDE.md alignment

| Rule | This plan |
|---|---|
| #1 — no domain features before v1.0 | Pure model-behaviour research; no domain code |
| #2 — bench numbers on `core/retrieval`/`core/graph`/`core/reasoning` PRs | No code-PR justified by this doc alone. If V3 leads to a per-stage num_predict patch in `core/reasoning`, that PR pastes STEP 7 numbers per rule #2 |
| #3 — self-evolution opt-in only | Unrelated |
| #4 — architecture changes via `architecture`-label PR | None |
| #5 — `core/` file ≤ 20 KB | Driver lives in `tmp/` (gitignored); not subject to gate |

---

## 10. Cross-references

- `docs/research/gemma4-event-emit-experiment-2026-05-21.md` — α data
- `docs/research/gemma4-next-experiments-plan.md` — original runbook (Greek series)
- `docs/handovers/v0.3.x-gemma4-feedback-track.md` — A/B/C/D definitions + feedback routing
- `reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md` — first internal data point
- `reports/promo-assets/devto-gemma4-write-track.md` — public dev.to article archive
- `core/gemma_client.py:253` — `num_predict` default 8192 (rules out JAMES-side budget cap)
- `core/gemma_client.py:283–309` — `<think>`-stripping (hypothesis E source)
- `core/wiki_generator.py:860–944` — α-experiment LLM call site
- PR #371 (PR-11b) + PR #387 (3-layer wrapper fix) — code context

---

## 11. 한국어 요약

기존 5-실험 runbook (`gemma4-next-experiments-plan.md`) 의 구조는
건전 (가설 1개당 실험 1개, 결정 트리 존재) — 그러나 4 개 문서를
함께 읽으면 **6개 방법론적 갭 + 1개 누락 가설** 발견:

1. **검증력 부족** — n=10, 60% 비율 95% CI [0.31, 0.83]
2. **변수 혼선** — γ (길이 × 새 타입), δ (지시 언어 × 키 언어),
   ζ (크기 × 패밀리 세대)
3. **"empty" 가 두 가지 모드** — 0-byte at <5s vs ~15s partial-truncate
4. **온도/결정성 통제 없음** — temp=0 미실행
5. **실험 간 의존성 미인코딩** — V1 결과가 V2 의미를 바꿈
6. **외부 피드백 게이팅 없음** — dev.to 5개 질문이 실험 우선순위를
   바꿔야 함

추가로 **가설 E** (`<think>` 후처리에 의한 합법 응답 stripping)
가 4-가설 공간에 누락 — `core/gemma_client.py:283–309` 의
`<think>` 제거 로직이 비정상 종료 응답을 빈 응답으로 변환할 수
있음.

본 문서는 runbook 을 대체하지 않음 — 방법론 보강 + V6 (n=50
sub-mode taxonomy) + V7 (온도 sweep) + V8 (E 가설 isolation)
추가 + 7개 실험 통합 결정 트리 + pre-registered 종료 조건.

**추천 첫 액션**: V1 (n=30) + V6 (n=50) + V7 (3 temps × n=20)
병렬 실행, ~30분 내 완료. 나머지는 결과 분기에 따라.
