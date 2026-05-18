# Gemma 4 (gemma4:e4b) on JAMES v0.3 Cognitive Stages — Field Report

> Author: PROJECT JAMES maintainer
> Date: 2026-05-18
> Status: open question — external feedback welcome (X / Reddit / dev.to comments)
> Companion to: [dev.to Gemma 4 Challenge submission](./devto-gemma4-challenge.md)
> License: MIT (same as JAMES)

## TL;DR

`gemma4:e4b` (4 B parameters, the "efficient" Gemma 4 build) **excels at the long-form natural-language synthesis stage** in JAMES's Graph-RAG pipeline, but **silently returns empty responses on five short meta-reasoning stages** (query rewrite, plan decomposition, web summary, self-critique, fact-check). Swapping the same prompts to `gemma3:12b` made all five stages succeed — so the issue is **not the prompts or wiring, it is the 4 B model's behavior on the meta-task shape**. Posting the trace data here in case other local-LLM operators have hit the same pattern or have a prompt-side fix that doesn't require jumping to a 12 B model.

This is a **fair-witness follow-up** to the project's earlier [dev.to Gemma 4 Challenge entry](./devto-gemma4-challenge.md), which highlighted Gemma 4's strengths (128 K context, RAG synthesis quality). The strengths are still real; this report documents where the smaller variant ran out of headroom for this project's cognitive layer.

---

## Setup (reproducible)

### Project

**PROJECT JAMES v0.3.x** — local-first Graph-RAG reasoning system. <https://github.com/Hashevolution/James-RAG-Evol>

Cognitive layer (relevant stages):

| Stage | Purpose | Prompt shape |
|---|---|---|
| `query_rewrite` | Rewrite the user question for retrieval | Korean/English instruction → JSON `{"rewritten": "..."}` |
| `plan.decompose` | Break a multi-aspect question into ≤ 5 subtasks | Instruction → JSON `{"subtasks": [...]}` |
| `synth.rag` | The actual long-form answer | System prompt + retrieved context (~5 KB) + Korean question → Korean prose answer |
| `synth.web_summary` | Summarize fetched web results | Instruction + web snippets → short Korean summary |
| `reflect.critique` | Critique the draft answer | Draft + instruction → Korean critique text |
| `verify.fact_check` | Audit claims against source docs | Answer + sources + instruction → JSON `{"grounded": bool, "unsupported": [...]}` |

All stages route through one Ollama backend adapter (`core/reasoning/backends/ollama_local.py`) and use the same `JAMES_LLM_MODEL` env var.

### Environment

- OS: Windows 11
- Shell: PowerShell
- Ollama: latest (mid-May 2026 build)
- Models installed locally:
  - `gemma4:e4b` (9.6 GB, ~ 4 B params)
  - `gemma3:12b` (8.1 GB, ~ 12 B params)
  - `qwen2.5-coder:7b` (4.7 GB)
  - `gemma2:2b` (1.6 GB)
- All `JAMES_ENABLE_*` cognitive flags set to `1` in the same shell session before launching the server.

### Test query

```
BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘
```

A real Korean retrieval question, routed to JAMES's retrieval pipeline (intent classifier picked `retrieval` correctly). Document corpus contains ~ 10 finance documents matching the topic.

---

## Observed behavior — `gemma4:e4b` as `JAMES_LLM_MODEL`

Direct quote of the server console (one query, all stages enabled):

| Stage | LLM call | Latency | Response size | Result |
|---|---|---|---|---|
| INTENT classify | `task=classify` | 9.1 s | **9 chars** ("retrieval") | ✅ OK |
| `query_rewrite` | `task=general` | 2.1 s | **0 chars** | ❌ empty |
| entity extract | `task=extract` | 9.5 s | **452 chars** (JSON of 9 entities) | ✅ OK |
| `synth.web_summary` | `task=general` | 4.0 s | **0 chars** | ❌ empty |
| `synth.rag` | `task=general` | 13.7 s | **2 690 chars** (Korean prose) | ✅ OK |
| `reflect.critique` | `task=general` | 4.2 s | **0 chars** | ❌ empty |
| `verify.fact_check` | `task=general` | 4.3 s | **0 chars** (prompt 4 319 → truncated to 4 000) | ❌ empty |

The empty-response path in `core/gemma_client.py` is taken when Ollama returns HTTP 200 but `response: ""` — i.e. the server replied successfully, the model just produced zero tokens. JAMES logs this as `gemma.empty_response` and surfaces it in the trace as `error="backend reported error string"`.

### What's striking

- **The 5 empty responses cluster at ~ 2–4 seconds**. Not a timeout (the per-stage budget is 10–30 s). The model decided it was done.
- **The two successful `task=general` calls** (entity extract: JSON, synth.rag: long Korean prose) **took 9.5 s and 13.7 s**. Same backend, same model, same `task` parameter — only the prompt shape differs.
- **The pattern is consistent across multiple trials**. Run the same query three times back-to-back and the same stages are empty each time.

---

## Control — `gemma3:12b` as `JAMES_LLM_MODEL`

Same query, same flags, no other changes. Re-ran the same trace probe:

| Stage | Latency | Response | Result |
|---|---|---|---|
| `query_rewrite` | 0.91 s | "BlackRock 및 Vanguard의 ETF 투자 전략과 포트폴리오 구성 방식의 차이점을 비교 분석해줘" — meaning-preserved keyword expansion | ✅ OK |
| `plan.decompose` | 1.33 s | 3 subtasks: "BlackRock ETF 전략 조사 / Vanguard ETF 전략 조사 / 두 ETF 전략 비교 분석" | ✅ OK |
| `synth.rag` | 9.6 s | 2 690-char Korean answer | ✅ OK |
| `reflect.critique` | 7.98 s | "## 답변 초안 비판적 검토 — 모순 / 사실 오류 …" — coherent meta-critique | ✅ OK |
| `reflect.revised` | 9.19 s | revised answer based on critique | ✅ OK |
| `verify.security` | 0 s | heuristic only — `no flags` | ✅ OK |
| `verify.fact_check` | 1.17 s | `{"grounded": true, "unsupported": []}` — valid JSON | ✅ OK |
| `verify.final` | 0 s | `rec=accept flags=0 unsupp=0` | ✅ OK |

Full 9-step trace renders end-to-end. Total wall-clock: ~ 39 s.

---

## Where Gemma 4 e4b succeeds in this project

To stay fair to the model:

- **Long-form synthesis from a 5 KB retrieved context** is the project's most-frequent stage, and gemma4:e4b handles it well (the 13.7 s, 2 690-char answer above is genuinely useful Korean prose).
- **JSON entity extraction with a 9-entity schema** (the `task=extract` step) returned 452 chars of clean JSON at 9.5 s.
- **Single-token classification** (`task=classify` → emit exactly one of seven mode strings) was fine.

So the model is not "broken" — it ships real Graph-RAG answers. The narrow failure mode is the second class of prompts: **short, structured, meta-instructional**.

---

## Failure pattern

```
✅ succeeds    long context + free-form Korean prose
✅ succeeds    short instruction + emit 1 token from a finite vocab
✅ succeeds    rich context + emit one JSON object describing the input
❌ empty       short context + emit JSON that critiques / restructures / audits the input
```

The five empty responses share these traits:

1. **The model is asked to act on a model output** (rewrite the user query, critique a draft, audit claims).
2. **The expected output is short and structured** — a few sentences, or a tight JSON object.
3. **The prompt mixes Korean instructions with English JSON schema keys** (`{"rewritten": "..."}`, `{"grounded": true, "unsupported": []}`).

A natural-language paraphrase (synth.rag) avoids all three. A JSON entity extraction has trait 3 only, and that one passes.

---

## Working hypotheses (open for discussion)

We have data but not a root cause. Candidate explanations:

### Hypothesis A — meta-reasoning capacity at 4 B is the floor

Critique / verify / decomposition prompts ask the model to reason **about** another reasoning artifact. The empirical literature on small open-weights models (Qwen 2.5-3B, Phi-3-mini, Gemma-2-2B, …) consistently shows the meta-reasoning gap is the first capability to drop below ~ 7 B params, while paraphrase-from-context survives much smaller. If this is right, no prompt-side fix exists for e4b on these stages.

### Hypothesis B — early stop-token emission on short structured prompts

Ollama returning `response: ""` on a 2 – 4 s call (well below the timeout) suggests the model emitted EOS / `<end_of_turn>` immediately. Possibly the chat template's wrapping of the user prompt resembles a completed conversation when the user prompt itself looks like an instruction-only frame (no input data attached).

### Hypothesis C — Korean instruction + English JSON schema confusion

The five failing prompts all mix Korean directive language with English-key JSON output. The two succeeding `task=general` calls don't (entity extract uses Korean prompt → Korean-content JSON; synth.rag is all Korean). Worth testing whether an all-Korean schema would change anything.

### Hypothesis D — JAMES side prompt-truncation artifact

The `verify.fact_check` log shows `prompt 4319자 → 4000자 축약` — JAMES capped the prompt at 4 000 chars, which likely chopped the closing brace of an embedded JSON example in the system prompt. If true, this is a JAMES bug, not a Gemma 4 bug, but it would only explain `verify.fact_check`, not the other four empty responses.

---

## What I'd love feedback on

If you've used `gemma4:e4b` (or `gemma4:e2b`) and have data points either way, I'd like to know:

1. **Have you seen the same "empty response on short structured prompts" pattern?** Especially: critique-of-a-draft, JSON schema audit, query rewrite.
2. **Did a prompt-engineering change rescue it on your setup?** (Different chat template, different `num_predict`, different temperature, all-one-language prompts, etc.)
3. **Does `gemma4:e2b` show the same pattern, or is it specific to e4b?**
4. **Does the same prompt set behave on `gemma4:31b-dense` / `gemma4:26b-moe` if you have one of those provisioned?**
5. **Is there a known issue with Ollama + Gemma 4 + JSON-output prompts** in your experience?

Project's stance on next steps:

- Default model swap to `gemma3:12b` is already done locally (we keep `gemma4:e4b` available — its long-context synthesis is the project's bread-and-butter stage).
- A follow-up Phase 0 / A2 PR will let operators wire individual cognitive stages to different backends, so e4b can keep the `synth.rag` stage while a heavier model takes the meta stages — best of both.
- We will **not** patch JAMES's prompt-shapes specifically to coax e4b into responding on these stages until we understand whether the empty-response is the model declining, the chat template misfiring, or a JAMES-side truncation bug.

---

## Reproduction

```powershell
# 1. Install JAMES (one-liner, MIT, no cloud)
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol-v010
python -m pip install -r requirements.txt

# 2. Make sure the two models are local
ollama pull gemma4:e4b
ollama pull gemma3:12b

# 3. Enable the five cognitive stages
$env:JAMES_ENABLE_QUERY_REWRITE = "1"
$env:JAMES_ENABLE_PLANNER       = "1"
$env:JAMES_ENABLE_REFLECT       = "1"
$env:JAMES_ENABLE_VERIFY        = "1"
$env:JAMES_ENABLE_FACT_CHECK    = "1"

# 4. Test with Gemma 4
$env:JAMES_LLM_MODEL = "gemma4:e4b"
python server_llmwiki.py
# In another shell, send a retrieval query (mode picker = retrieval),
# e.g. "BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘"
python scripts/replay_trace.py --recent
python scripts/replay_trace.py <trace_id>
# Observe: 5 stages return empty response strings

# 5. Test with Gemma 3 (control)
# Stop the server, set the env var, restart in the same shell:
$env:JAMES_LLM_MODEL = "gemma3:12b"
python server_llmwiki.py
# Same query, same trace command — all 9 stages succeed
```

If you publish your own numbers (X / GitHub issue / Reddit), please tag `#JAMES` or open an issue on the repo — we'll link it back here.

---

## 한국어 요약 (Korean summary)

자메스 v0.3 의 Cognitive Layer 5 stage 검증 중 `gemma4:e4b` (4 B) 가 메타-task 5 개에서 빈 응답:

- `query_rewrite` / `plan.decompose` / `synth.web_summary` / `reflect.critique` / `verify.fact_check` 모두 0자 응답, 2–4 초 latency (timeout 아닌 self-stop).
- 같은 모델이 `synth.rag` (긴 자연어 답변, 2 690 자) 와 entity 추출 (JSON 452 자) 은 정상.

**같은 PowerShell session 에서 `JAMES_LLM_MODEL=gemma3:12b` 로 변경 후 9-step trace 전부 정상.** Prompt / wiring 회귀 아님 — 모델 변경만으로 해결.

**가설** (정답 미상, 외부 데이터 환영):

A. 4 B 의 메타-추론 한계 — 다른 답변을 비판/검증/재구조화 요구는 7 B+ 부터 안정
B. 짧고 구조화된 prompt 에 모델이 즉시 EOS 토큰 emit
C. 한국어 지시 + 영어 JSON schema 키 혼합이 모델을 confuse
D. JAMES 측 prompt 4 000 자 truncation 버그 (verify.fact_check 만 해당 가능성)

같은 패턴 보신 분 / prompt-side fix 가 있는 분 — X 멘션, GitHub issue, 또는 dev.to 코멘트로 알려주세요. `#JAMES` 태그 사용 시 본 보고서에 역참조 추가합니다.

본 보고서는 [dev.to Gemma 4 Challenge 응모 글](./devto-gemma4-challenge.md) 의 후속 — 같은 모델의 강점(긴 context Graph-RAG 합성)은 유지하면서, 작은 변형(e4b)이 본 프로젝트의 메타-stage 에서 부족한 점을 정직하게 기록한 fair-witness 보고서.

---

*Companion materials: [dev.to challenge submission](./devto-gemma4-challenge.md), [launch tracker](./launch-tracker.md). Project repo: <https://github.com/Hashevolution/James-RAG-Evol>.*
