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

## Reader contributions

> This section is append-only — never edit prior entries.
> Routing protocol: `docs/handovers/v0.3.x-gemma4-feedback-track.md`.

### 2026-05-21 — Ali Afana (dev.to Write-track follow-up)

**Reporter**: Ali Afana ([@alimafana](https://dev.to/alimafana), Provia founder, dev.to Featured)
**Permalink**: https://dev.to/alimafana/i-raised-gemma-4s-token-cap-the-dense-model-stopped-refusing-2gf3 (publication imminent; preview reviewed 2026-05-21)
**Hypothesis they support / refute**: **B (token budget) — confirming**

**Verbatim quote**:
> ... my `max_tokens: 400` cap was starving Gemma's reasoning layer before the visible reply completed. I re-ran the same six scenarios with one variable changed — budget raised from 400 to 4096. Dense recovered on every scenario, including the false-refusal headline that anchored the original article. ... The cap was doing the work. Walking it back publicly.

Twelve calls, single variable changed. Gemini 31B Dense + 26B MoE both 12/12 recovery.

**Decoded relevance to this report**:

Walk-back maps 1:1 onto JAMES's per-stage `DEFAULT_MAX_TOKENS` defaults:

| Stage (failed on `gemma4:e4b` in this report) | File:line | Default |
|---|---|---:|
| `query_rewrite` | `core/retrieval/query_rewriter.py:46` | **200** |
| `plan.decompose` | `core/reasoning/planner.py:43` | **400** |
| `reflect.critique` | `core/reasoning/reflect.py:54` | **400** |
| `verify.fact_check` | `core/reasoning/verify.py:69` | **400** |

Three of four sit at exactly Ali's failing threshold (400); query_rewriter is tighter still (200). The cognitive-stages eval's "empty response" finding (5/6 stages) is consistent with the cap being the dominant variable, not a 4B-parameter capacity floor.

**Project response**:

- **V3' (token-budget replication)** queued for 2026-05-21 week — re-run the same Korean retrieval query (`BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘`) with `max_tokens` 400 → 4096 on those 4 stages, n=10 per stage, on `gemma4:e4b`. Driver lives in `tmp/pr-11b-verify/`. Decision tree: see `docs/research/gemma4-experiment-validation-plan.md` §4.3.
- **If V3' confirms hypothesis B**: 4-line PR bumping the four `DEFAULT_MAX_TOKENS` constants (200 → 4096 / 400 → 4096 × 3). STEP 7 bench numbers in the PR description per CLAUDE.md rule #2. Operational recommendation in this report updated accordingly.
- **Cross-validation context**: Ali's article cites Robin Converse (Triava Labs, sovereign Ollama, uncapped sweep, 100% MoE success) as the original walk-back trigger. With our defaults: **three independent deployment contexts** (Robin's sovereign Ollama / Ali's managed Gemini API / JAMES's local Ollama) point at the same cap-pathology pattern, **before any cross-experiment swap runs** (Track 3 of `docs/handovers/v0.3.x-ali-collaboration-track.md`).
- **Outgoing**: 2026-05-21 LinkedIn DM acknowledged the walk-back, confirmed the two mention framings in the article preview, shared the JAMES per-stage default mapping (so Ali can incorporate it pre-publish if he chooses), and re-confirmed the Track 3 mid-June calendar.

**Notes**:

- Ali's walk-back is the **first substantive Reader contribution** since this report was published 2026-05-18. The routing matrix in the feedback-track handover (Hypothesis B → "Patch `core/gemma_client.py` to log raw Ollama response... + per-stage `num_predict` overrides per stage if a single setting fixes it") is the immediate project response shape; V3' is the falsification check on it.
- The α-experiment (2026-05-21, wiki extraction at `max_tokens=1500`) is a related but separate test — its budget (1500) is well above Ali's failing threshold (400), so a separate V3' variant (1500 → 4096) tests whether the extraction prompt's empty rate is also cap-driven or a different mechanism.

### 2026-05-22 — Hashevolution self-replication (V3'.a, query_rewrite, n=10)

**Reporter**: PROJECT JAMES maintainer (in-house V3'.a sweep)
**Driver**: `scripts/research/v3prime_query_rewriter.py` @ commit `e80ee48`
**Raw data**: `reports/research-runs/v3prime-query-rewriter-20260522T021221.json` @ commit `22a5ce2`
**Hypothesis they support / refute**: **B (token budget) — confirmed for query_rewrite at the mechanism level**

**Aggregate**:

| `num_predict` | non_empty | `done_reason` | avg `eval_count` | avg latency |
|---:|---:|---|---:|---:|
| 200 (production default) | **0 / 10** | length (10/10) | 200 (= cap) | 2.1 s |
| 4096 (lifted) | **10 / 10** | stop (10/10) | ~520 | 5.3 s |

Single variable changed: `num_predict`. Model (`gemma4:e4b`), temperature (0.2), prompt template (pinned from `core/retrieval/query_rewriter.py:53`), query (`BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘`), Ollama endpoint — all held constant.

**Mechanism (richer than "cap exhaustion")**:

`done_reason: "length"` plus `eval_count: 200` plus `response_bytes: 0` across all ten 200-cap runs means the model consumed the full 200-token budget while emitting **zero visible bytes**. The 4096-cap runs averaged ~520 `eval_count` for ~100-byte JSON output — a hidden-to-visible token ratio of roughly 5–6:1 on this prompt shape. The model needs ~500 hidden reasoning tokens *before* the first visible output token. Any cap below that threshold deterministically produces empty.

This is the toolchain-level mirror of Ali Afana's "starving Gemma's reasoning layer before the visible reply completed" framing — now quantified.

**Project response**:

- This is the in-house cross-validation of the 2026-05-21 dev.to walk-back. JAMES is now the **third deployment context** (alongside Robin Converse's sovereign Ollama uncapped sweep and Ali Afana's managed Gemini 400→4096 single-variable test) for hypothesis B.
- Remaining cognitive stages (`planner`, `reflect.critique`, `verify.fact_check`) all default to 400, looser than query_rewrite's 200 but still below the ~500 hidden-reasoning floor measured here. V3'.b/.c/.d drivers will test each stage on the same single-variable protocol.
- If V3'.b/.c/.d replicate the 0→100% recovery pattern, the 4-line PR (bumping `DEFAULT_MAX_TOKENS` in `core/retrieval/query_rewriter.py:46`, `core/reasoning/planner.py:43`, `core/reasoning/reflect.py:54`, `core/reasoning/verify.py:69`) lands with STEP 7 bench numbers per CLAUDE.md rule #2.
- Hypothesis A (4B meta-reasoning floor) is now **practically refuted for query_rewrite** — same model + same prompt + cap removed → 10/10 success.

**Updated cross-validation bundle**:

| Source | Context | Test | Result |
|---|---|---|---|
| Robin Converse | sovereign Ollama, uncapped sweep | 3 temperatures × 6 scenarios on Gemma 4 MoE | 18/18 success |
| Ali Afana (2026-05-21) | managed Gemini API, single-variable | 400 → 4096 cap on 6 scenarios × 2 architectures | 12/12 recovery |
| Hashevolution (2026-05-22, this entry) | local Ollama, single-variable | 200 → 4096 cap on query_rewrite, n=10 | 0/10 → 10/10 recovery, mechanism quantified |

Three independent deployment contexts; two architectures (Gemini 31B Dense + 26B MoE, Gemma 4 E4B Ollama); one mechanism (the reasoning layer needs hidden-token budget before visible output begins, and any cap below that floor is deterministic failure).

### 2026-05-22 — Hashevolution self-replication continued (V3'.b, planner, n=10)

**Reporter**: PROJECT JAMES maintainer (in-house V3'.b sweep)
**Driver**: `scripts/research/v3prime_planner.py` @ commit `494ef6d`
**Raw data**: `reports/research-runs/v3prime-planner-20260522T063918.json` (workstation push pending)
**Hypothesis they support / refute**: **B (token budget) — confirmed for plan.decompose, replicates V3'.a pattern at stage-independent mechanism level**

**Aggregate**:

| `num_predict` | non_empty | avg latency | JSON ok |
|---:|---:|---:|---:|
| 400 (production default) | **0 / 10** | 4.3 s | 0 / 10 |
| 4096 (lifted) | **10 / 10** | 7.1 s | 10 / 10 |

**Cross-stage consistency with V3'.a**:

| Metric | V3'.a (query_rewrite, cap 200) | V3'.b (planner, cap 400) | Pattern |
|---|---|---|---|
| Default-cap success | 0/10 | 0/10 | Identical |
| 4096-cap success | 10/10 | 10/10 | Identical |
| Default-cap latency | 2.1 s | 4.3 s | **Linear in cap** (2× cap → 2× latency) |
| 4096-cap latency | 5.3 s | 7.1 s | +1.8 s for planner's additional reasoning/output |

The linear cap-latency scaling indicates the ~500-token hidden reasoning floor is **stage-independent** — a model-level property of `gemma4:e4b` on short structured-output prompts, not a stage-specific behavior. Whatever the cap is set to, the model burns it linearly and surfaces zero visible output until the floor is cleared.

**Project response**:

- Two cognitive stages now confirm hypothesis B-budget at the mechanism level with consistent telemetry. The remaining two cognitive stages (`reflect.critique`, `verify.fact_check`, both default 400) have a strong prior to follow the same pattern.
- 4-line PR bumping all four `DEFAULT_MAX_TOKENS` constants (200 / 400 / 400 / 400 → 4096 each) now justified by 2-stage in-house mechanism evidence + Ali's external 12/12 + Robin's external 18/18.
- V3'.c / V3'.d will run as **post-merge validation** — their JSONs will land in `reports/research-runs/` alongside V3'.a/.b. If either stage does NOT replicate (low-probability scenario), single-line revert.

### 2026-05-22 — Robin Converse (LinkedIn sub-reply on the V3'.b commentary thread)

**Reporter**: Robin Converse (Triava Labs, sovereign Ollama infrastructure)
**Channel**: LinkedIn comment thread (public reply, ~1 hour after the JAMES V3'.b commentary)
**Hypothesis they support / refute**: **B (token budget) — confirmed; proposes architectural-property extension**

**Verbatim quote** (public LinkedIn comment):

> jiwon SEO — that's a meaningful upgrade to the framing. The "~500-token reasoning floor before first visible token" is more specific than the gap-widens shape I had, and it predicts something testable: there should be a discoverable threshold below which output is impossible regardless of query complexity, and above which the cap just constrains length.
>
> Worth seeing if the floor is model-specific or architecture-specific. My sweep was on gemma4:26b MoE your test is on gemma4:e4b. If the floor sits at a similar token count across both, it's an architectural property. If it scales with parameter count, that's a different story.
>
> Adding this to the Track 3 piece when it lands. Three contexts pointing at the mechanism with measurable data is the article that writes itself.

**Decoded relevance to this report**:

Two substantive operational shifts:

1. **Vocabulary convergence — the JAMES framing is now the joint anchor.** Robin explicitly names the "~500-token reasoning floor before first visible token" phrasing as a meaningful upgrade over her own "gap-widens" description. The cross-collaboration vocabulary stack:

   | Source | Vocabulary |
   |---|---|
   | Robin Converse (Triava, sovereign Ollama) | "gap widens with query difficulty" — descriptive |
   | Ali Afana (Provia, managed Gemini) | "starving the reasoning layer before the visible reply completed" — biological |
   | Hashevolution (PROJECT JAMES, local Ollama) | "~500-token reasoning floor before first visible token" — mechanistic |

   All three describe the same phenomenon. The mechanistic phrasing is the one Robin (P1) and Ali (separate DM) are now adopting forward.

2. **Testable extension: model-specific vs architectural property.** Robin's sweep was on `gemma4:26b MoE`; the V3'.a/.b results are on `gemma4:e4b`. Two readings of the hypothesis:

   | Scenario | Floor (hypothesis) | Reading |
   |---|---|---|
   | e4b and 26b MoE both ~500-token floor | **Identical** | Architectural property of the Gemma 4 family |
   | 26b MoE has a different (e.g., higher) floor | **Scales with size** | A parameter-count function — different (still publishable) finding |

   Either outcome is a clean publishable result; the disambiguation lives at the data layer, not the framing layer.

**Project response**:

- **Outgoing LinkedIn reply** sent the same day. Mirrored the "discoverable threshold" phrasing as the operating vocabulary. Reported V3'.b stage-independence as the second data point on `gemma4:e4b`. Offered the V3' driver (`scripts/research/v3prime_query_rewriter.py`) as a stdlib-only drop-in for her sovereign-Ollama 26b MoE environment, with explicit protocol: single `num_predict` variable, n=10 per cap, capturing `eval_count` + `done_reason` + raw response bytes per call. Emphasised "the capture matters more than the driver — eval_count vs visible bytes is where the floor signature shows up" (which implicitly credits Robin's original `eval_count` gap observation as the seed signal for the floor mechanism).
- **New shared vocabulary proposed**: **"cross-model floor calibration"** — covers both the architectural-property reading and the parameter-scaling reading without committing to either.
- **Deliberately not done**: did NOT speculate on which scenario will win (the "different story" reading), did NOT commit to additional family-variant sweeps (e2b / Gemma 3 etc.) on the JAMES side, did NOT claim stage-specific floor heights without V3'.c/.d data.
- **Effect on joint piece narrative**: Robin moves from cited contributor (the walk-back trigger noted in Ali's article) to **active co-contributor with a proposed second experiment**. The joint piece now potentially carries (a) three deployment contexts, (b) two architectures (Gemini Dense+MoE / Gemma 4 4B), (c) a measurable architectural property if her 26b floor aligns. If she runs the 26b sweep, the piece carries quantitative cross-model data; if she doesn't, the framing-convergence + three-context evidence already anchors it.

**Updated cross-validation bundle** (with Robin's proposed extension):

| Source | Context | Test | Result |
|---|---|---|---|
| Robin Converse (initial) | sovereign Ollama, uncapped sweep on `gemma4:26b MoE` | 3 temperatures × 6 scenarios | 18/18 success |
| Ali Afana (2026-05-21) | managed Gemini API, single-variable | 400 → 4096 cap on 6 scenarios × 2 architectures | 12/12 recovery |
| Hashevolution (V3'.a) | local Ollama, single-variable on `gemma4:e4b` | 200 → 4096 cap on query_rewrite, n=10 | 0/10 → 10/10, ~500-token hidden-reasoning floor quantified |
| Hashevolution (V3'.b) | local Ollama, single-variable on `gemma4:e4b` | 400 → 4096 cap on planner, n=10 | 0/10 → 10/10, mechanism stage-independent within model |
| Robin Converse (proposed, 2026-05-22) | sovereign Ollama, single-variable on `gemma4:26b MoE` | same protocol as V3'.a — TBD if she runs it | Pending — would disambiguate model-specific vs architectural |

**Notes**:

- This is the **second Reader contribution** since the 2026-05-21 Ali entry. Routing protocol: `docs/handovers/v0.3.x-gemma4-feedback-track.md` (unchanged — same hypothesis B classification).
- The Robin sub-reply is the first signal that the framing language is converging on the JAMES phrasing as the shared anchor (a meta-effect beyond the mechanism finding itself).

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
