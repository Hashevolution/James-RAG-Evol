# dev.to — Gemma 4 Challenge submission (Write track)

> Drafted: 2026-05-18
> Track: **Write about Gemma 4** ($100 × 5 winners)
> Source material: [`gemma4-e4b-cognitive-stages-eval.md`](./gemma4-e4b-cognitive-stages-eval.md) — internal fair-witness report (PR #307)
> Companion submission: [Build track piece on E4B model choice](./devto-gemma4-challenge.md)
> Submission deadline: 2026-05-24 23:59 PDT
> Winners announced: 2026-06-04
> Tags: `devchallenge`, `gemmachallenge`, `gemma`, `ollama`

## Why a Write-track submission in addition to the Build-track one

The Build-track submission ([`Building a Mini Palantir on gemma4:e4b — 128K Context Lets the Graph Actually Be Graph-RAG`](https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk)) made an *intentional model choice* argument: 128K context window > parameter count, so E4B was right for the Graph-RAG retrieval-conditioning stage.

That argument held — and it is still the strongest single thing E4B does in this project.

But once the v0.3 Cognitive Middleware Layer started shipping Phase 2 stages (verification, planner, tool router, query rewriter, fact-check), a second pattern showed up that the Build-track piece could not honestly absorb: E4B silently returns empty responses on five of the nine cognitive stages, while the same prompts on Gemma 3 12B succeed end-to-end.

This is the Write-track piece that documents that pattern honestly, without retreating from the Build-track claim. Same author, two articles, two facets of the same model.

The challenge judging rubric for the Write track is:

- Clarity and depth of explanation
- Originality of perspective or insight
- Practical value to the community
- Quality of writing

A fair-witness field report meets all four at once: it shares reproducible numbers, an explicit "I don't know yet" stance on root cause, and a set of open questions that other operators can act on.

---

## Suggested title (pick one)

| # | Title | Why |
|---|---|---|
| **A** | **5 empty responses from `gemma4:e4b`. 4 hypotheses. 0 root cause.** A fair-witness field report from a Graph-RAG production. | ⭐ Strongest hook — number-led, names a tension (no resolution), promises honesty. |
| B | Where Gemma 4 e4b runs out of room: empty responses on meta-reasoning stages | Clearer technical framing, slightly less click-worthy |
| C | Gemma 4 e4b: brilliant at synthesis, silent on meta-reasoning. A field report. | Bridges the strengths and weaknesses in the title itself |

Recommended: **A**. Numbers-led titles outperform on the dev.to feed; the "0 root cause" half signals the writing is honest rather than gloating.

## Cover image

Use [`reports/promo-assets/screenshots/03-chat-graph-paths.jpg`](./screenshots/03-chat-graph-paths.jpg) — the chat-UI screenshot with "그래프 경로 47개 보기" surfaced. It primes the reader for "this writer ships a real Graph-RAG pipeline" before the article gets into the failure mode.

Download URL: `https://github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/screenshots/03-chat-graph-paths.jpg?raw=true`

## Tags

```
devchallenge, gemmachallenge, gemma, ollama
```

`ollama` is the 4th tag (instead of `rag`) — the failure mode plausibly involves the Ollama chat template or stop-token handling, so the Ollama tag's audience is more likely to recognize the pattern.

---

# Submission body (copy-paste into dev.to editor)

````markdown
*This is a submission for the [Gemma 4 Challenge: Write about Gemma 4](https://dev.to/challenges/google-gemma-2026-05-06)*

## TL;DR

`gemma4:e4b` (4 B parameters, the "efficient" Gemma 4 build) **excels at long-form natural-language synthesis from a 5 KB retrieved context** in my Graph-RAG project. It also **silently returns empty responses on five short meta-reasoning stages** — query rewrite, plan decomposition, web summary, self-critique, fact-check. Same model, same backend, same `task` parameter. Swapping to `gemma3:12b` made all five succeed without touching a single prompt.

I have data. I do not yet have a root cause. Posting this as a fair-witness field report in case other local-LLM operators have seen the same pattern (or have a prompt-side fix that doesn't require jumping to a 12 B model).

This is a companion to my earlier [Build-track submission](https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk), which argued for E4B on the basis of its 128 K context window. That argument is still right — for the synthesis stage. The five meta stages are where the 4 B variant runs out of room.

## Setup (reproducible)

### Project

[**PROJECT JAMES v0.3.x**](https://github.com/Hashevolution/James-RAG-Evol) — a local-first Graph-RAG reasoning engine. MIT-licensed, Ollama-only, no cloud LLM dependency. v0.3.0 shipped the Cognitive Middleware Layer architecture; v0.3.x is landing its phases incrementally — verification engine, planner, tool router, query rewriter, fact-check.

Relevant stages of the cognitive layer:

| Stage | Purpose | Prompt shape |
|---|---|---|
| `query_rewrite` | Rewrite the user question for retrieval | Korean/English instruction → JSON `{"rewritten": "..."}` |
| `plan.decompose` | Break a multi-aspect question into ≤ 5 subtasks | Instruction → JSON `{"subtasks": [...]}` |
| `synth.rag` | The actual long-form answer | System prompt + retrieved context (~5 KB) + Korean question → Korean prose answer |
| `synth.web_summary` | Summarize fetched web results | Instruction + web snippets → short Korean summary |
| `reflect.critique` | Critique the draft answer | Draft + instruction → Korean critique text |
| `verify.fact_check` | Audit claims against source docs | Answer + sources + instruction → JSON `{"grounded": bool, "unsupported": [...]}` |

All stages route through one Ollama backend adapter and use the same `JAMES_LLM_MODEL` env var. Whatever model is named, every stage talks to it the same way.

### Environment

- OS: Windows 11, PowerShell
- Ollama: latest mid-May 2026 build
- Models installed locally: `gemma4:e4b` (9.6 GB, ~4 B params), `gemma3:12b` (8.1 GB, ~12 B), plus a few others irrelevant to this report
- All `JAMES_ENABLE_*` cognitive flags set to `1` in the same shell before launching the server

### Test query

```
BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘
```

A real Korean retrieval question. Intent classifier picked `retrieval` correctly. Document corpus contains ~10 finance documents matching the topic.

## What I observed with `gemma4:e4b`

Direct quote of the server console (one query, all stages enabled):

| Stage | LLM call type | Latency | Response size | Result |
|---|---|---|---|---|
| INTENT classify | `task=classify` | 9.1 s | **9 chars** ("retrieval") | ✅ OK |
| `query_rewrite` | `task=general` | 2.1 s | **0 chars** | ❌ empty |
| entity extract | `task=extract` | 9.5 s | **452 chars** (JSON of 9 entities) | ✅ OK |
| `synth.web_summary` | `task=general` | 4.0 s | **0 chars** | ❌ empty |
| `synth.rag` | `task=general` | 13.7 s | **2 690 chars** (Korean prose) | ✅ OK |
| `reflect.critique` | `task=general` | 4.2 s | **0 chars** | ❌ empty |
| `verify.fact_check` | `task=general` | 4.3 s | **0 chars** (prompt 4 319 → truncated to 4 000) | ❌ empty |

The empty-response path is taken when Ollama returns HTTP 200 but `response: ""` — the server replied successfully, the model just produced zero tokens. JAMES logs it as `gemma.empty_response`.

### What's striking

- **The 5 empty responses cluster at ~2–4 seconds.** Not a timeout. The per-stage budget is 10–30 s; the model decided it was done.
- **The two successful `task=general` calls** (entity extract: JSON; synth.rag: long Korean prose) **took 9.5 s and 13.7 s.** Same backend, same model, same `task` parameter — only the prompt shape differs.
- **The pattern is consistent across multiple trials.** Run the same query three times back-to-back and the same five stages are empty each time.

## Control — same prompts on `gemma3:12b`

Same query, same flags, no other changes. Single env-var swap, restart server:

| Stage | Latency | Response | Result |
|---|---|---|---|
| `query_rewrite` | 0.91 s | "BlackRock 및 Vanguard의 ETF 투자 전략과 포트폴리오 구성 방식의 차이점을 비교 분석해줘" — meaning-preserved keyword expansion | ✅ |
| `plan.decompose` | 1.33 s | 3 subtasks (BlackRock 조사 / Vanguard 조사 / 비교 분석) | ✅ |
| `synth.rag` | 9.6 s | 2 690-char Korean answer | ✅ |
| `reflect.critique` | 7.98 s | "## 답변 초안 비판적 검토 — 모순 / 사실 오류 …" — coherent meta-critique | ✅ |
| `reflect.revised` | 9.19 s | revised answer based on critique | ✅ |
| `verify.fact_check` | 1.17 s | `{"grounded": true, "unsupported": []}` — valid JSON | ✅ |

Full 9-step trace renders end-to-end. Wall-clock ~39 s. Same prompts. Same wiring. Same backend.

**This is the punchline: nothing changed except the model name.**

## Where Gemma 4 e4b still wins

Staying fair to the model:

- Long-form synthesis from a 5 KB retrieved context — the project's most-frequent stage — handled well at 13.7 s for 2 690 chars of genuinely useful Korean prose.
- JSON entity extraction with a 9-entity schema returned 452 chars of clean JSON at 9.5 s.
- Single-token classification — emit exactly one of seven mode strings — was fine.

The model is not "broken." It ships real Graph-RAG answers. The narrow failure mode is a second class of prompts: **short, structured, meta-instructional**.

## The failure pattern

```
✅ succeeds    long context + free-form Korean prose
✅ succeeds    short instruction + emit 1 token from a finite vocab
✅ succeeds    rich context + emit one JSON object describing the input
❌ empty       short context + emit JSON that critiques / restructures / audits the input
```

The five empty responses share three traits:

1. **The model is asked to act on a model output** — rewrite the user query, critique a draft, audit claims.
2. **The expected output is short and structured** — a few sentences, or a tight JSON object.
3. **The prompt mixes Korean instructions with English JSON schema keys** — e.g. `{"rewritten": "..."}` or `{"grounded": true, "unsupported": []}`.

A natural-language paraphrase (synth.rag) avoids all three. A JSON entity extraction has trait 3 only, and that one passes. The cluster of all three is what seems to silence the model.

## Four working hypotheses

I have data but not a root cause. Four candidate explanations, listed by my own subjective likelihood:

### A. Meta-reasoning capacity at 4 B is the floor

Critique / verify / decomposition prompts ask the model to reason *about* another reasoning artifact. The empirical literature on small open-weights models (Qwen 2.5-3B, Phi-3-mini, Gemma-2-2B, …) consistently shows the meta-reasoning gap is the first capability to drop below ~7 B params, while paraphrase-from-context survives much smaller. If this is right, no prompt-side fix exists for E4B on these stages.

### B. Early stop-token emission on short structured prompts

Ollama returning `response: ""` on a 2–4 s call (well below the timeout) is consistent with the model emitting EOS / `<end_of_turn>` immediately. Possibly the chat template wrapping resembles a completed conversation when the user prompt itself looks like an instruction-only frame with no input data attached.

### C. Korean instruction + English JSON schema confusion

The five failing prompts all mix Korean directive language with English-key JSON output. The two succeeding `task=general` calls don't (entity extract uses Korean prompt → Korean-content JSON; synth.rag is all Korean). Worth testing whether an all-Korean schema (e.g. `{"재작성된_질의": "..."}`) would change anything.

### D. JAMES-side prompt-truncation artifact

The `verify.fact_check` log shows `prompt 4 319자 → 4 000자 축약` — JAMES capped the prompt at 4 000 chars, which likely chopped the closing brace of an embedded JSON example in the system prompt. If true, this is a JAMES bug, not a Gemma 4 bug — but it would only explain `verify.fact_check`, not the other four empty responses.

The report explicitly **does not** advocate for a single hypothesis — that is the work this feedback round is asking the community to fund.

## What I'd love feedback on

If you've used `gemma4:e4b` (or `gemma4:e2b`) and have data points either way, I'd like to know:

1. Have you seen the same "empty response on short structured prompts" pattern? Especially critique-of-a-draft, JSON schema audit, query rewrite.
2. Did a prompt-engineering change rescue it on your setup? Different chat template, different `num_predict`, different temperature, all-one-language prompts, anything else.
3. Does `gemma4:e2b` show the same pattern, or is it specific to E4B?
4. Does the same prompt set behave on `gemma4:31b-dense` / `gemma4:26b-moe` if you have one of those provisioned?
5. Is there a known issue with Ollama + Gemma 4 + JSON-output prompts in your experience?

Project's stance on next steps:

- Default model swap to `gemma3:12b` is already done locally. `gemma4:e4b` stays available — its long-context synthesis is the project's bread-and-butter stage.
- A follow-up PR (option A2) will let operators wire individual cognitive stages to different backends, so E4B can keep `synth.rag` while a heavier model takes the meta stages.
- We will **not** patch JAMES's prompt shapes specifically to coax E4B into responding on these stages until we understand whether the empty response is the model declining, the chat template misfiring, or a JAMES-side truncation bug.

## Reproduction

If you want to reproduce — or, more usefully, to falsify — the report on your own corpus:

```powershell
# 1. Install JAMES (one-liner, MIT, no cloud)
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol
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
# In another shell, send a retrieval query, e.g. the same BlackRock vs Vanguard line above.
python scripts/replay_trace.py --recent

# 5. Control: Gemma 3
$env:JAMES_LLM_MODEL = "gemma3:12b"
python server_llmwiki.py
# Same query, same trace command — all 9 stages succeed
```

If you publish your own numbers — X / GitHub issue / Reddit / dev.to comment — please tag `#JAMES` or open an issue on the [repo](https://github.com/Hashevolution/James-RAG-Evol). I'll link it back to this report.

## A note on the companion piece

This Write-track submission and the [Build-track submission](https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk) are deliberately contradictory in tone — one defends the model choice, the other documents where the same model falls short on a different class of prompts. Both are honest readings of the same model under different conditions. I think the contradiction is the point: writing about Gemma 4 useful for the community has to include both halves, not just the half that fits the marketing arc.

If you've read [Ali Afana's parallel piece on MoE vs Dense](https://dev.to/alimafana/i-added-three-rules-to-gemma-4-the-moe-searched-the-dense-model-refused-1j18), you'll recognize the framing: same prompt, opposite behavior, architecture under the model is the variable I wasn't controlling. He came at it from MoE vs Dense; I came at it from 4 B vs 12 B and meta-task vs synthesis-task. The two reports compose.

---

🤖 *Honest disclosure: this submission was drafted with AI assistance and edited by the author. The trace numbers, environment specs, and reproduction commands are real and verifiable in the linked repository. The hypotheses are the author's; the fair-witness framing — data without root cause — is deliberate.*
````

---

## Where to publish

dev.to → New Post → Editor v1 (markdown) → paste the body above → set title, tags, cover image → **Publish**.

After publish:

1. Add the URL to `reports/promo-assets/launch-tracker.md` "Social posts" table (or trigger a small docs PR — happy to handle this from a future session).
2. Add a self-reply comment on the article pointing at:
   - The internal eval report ([`gemma4-e4b-cognitive-stages-eval.md`](./gemma4-e4b-cognitive-stages-eval.md)) — the source of truth.
   - The Build-track submission — completes the "two halves, same author" arc.
   - Ali Afana's parallel piece — extends the conversation across two writers.
3. Quote-reply from the existing X English thread + LinkedIn post linking the new article. Image: `06-3d-graph.jpg` again (the hero), or `03-chat-graph-paths.jpg` if the post wants to lead with the chat UI.

## Why this submission can win the Write track

| Rubric criterion | This piece |
|---|---|
| **Clarity and depth of explanation** | One controlled experiment, six tabulated trace rows, four named hypotheses, explicit reproduction script |
| **Originality of perspective or insight** | Fair-witness framing — "I have data, not a conclusion" — is rare in dev.to LLM writing. Most pieces commit to a hypothesis early |
| **Practical value to the community** | The five open questions are answerable by anyone running Gemma 4 + Ollama. Any single reply with falsifying data is useful project-wide |
| **Quality of writing** | Inherited from the eval report's voice — short paragraphs, tight tables, no flourish |

Combined with the Build-track piece, the same author appears twice on the challenge with two non-overlapping perspectives on the same model. That itself is a signal of seriousness — defending a model in one piece and documenting its limits in the other is the opposite of a marketing arc.

## Risk-management notes

- The piece is honest about a failure mode of Gemma 4. It is *not* a hit piece — it explicitly preserves credit for what the model does well, and frames the failure as "rich call for community data" rather than "model is bad." This tone is the actual differentiator.
- The mention of Korean text in failed prompts could be misread as a language-equity issue. The body explicitly frames Hypothesis C as one of four possibilities and proposes the test (Korean-key JSON) — that is the right shape for the claim, not bigger.
- Title A leads with five numbers. If dev.to's automatic linting flags it, B or C are safe fallbacks.

## Companion artifacts

- Source eval report (definitive numbers): [`gemma4-e4b-cognitive-stages-eval.md`](./gemma4-e4b-cognitive-stages-eval.md)
- Feedback-routing handover (what to do when replies arrive): [`docs/handovers/v0.3.x-gemma4-feedback-track.md`](../../docs/handovers/v0.3.x-gemma4-feedback-track.md)
- Build-track Companion: [`devto-gemma4-challenge.md`](./devto-gemma4-challenge.md)
- Visual library for cover / inline images: [`screenshots/README.md`](./screenshots/README.md)
- Launch tracker (running log): [`launch-tracker.md`](./launch-tracker.md)
