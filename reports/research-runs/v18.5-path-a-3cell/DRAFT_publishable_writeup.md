# DRAFT — Publishable Writeup Outline

**Status**: skeleton only. Numbers ⟨TBD⟩ filled in after 3-cell measurement completes. Do NOT publish before all 3 cells (A + B + C) land + Quality Delta Card written + operator review.

**Working title candidates**:
1. "How a UX cycle nearly poisoned our RAG benchmark — and the 4-layer guard we built"
2. "Thinking-mode gotcha: why gemma4:e4b might be returning empty strings in your RAG pipeline"
3. "A fair benchmark for thinking-mode LLMs: same-mode, same-budget, paired comparison"

---

## 1. Hook (≤ 300 words)

The Path A measurement crashed 27/27 trials in a way that looked like the model worked perfectly fine — except every response was an empty string. The judge auto-classified them as ABSTAINED. Without a sanity check, we would have published "gemma4:e4b ABSTAINS on 100% of multi-hop questions" — a headline that's both true and meaningless.

This writeup is two things:
1. A practical warning for anyone using a thinking-mode LLM (gemma4 family, qwq, o1-mini, etc.) in a RAG pipeline at default `num_predict` caps under ~450.
2. A measurement-design pattern (3-cell paired) and a guard architecture (lock-test + pre-flight) that we now run before every benchmark.

The gemma4-specific quirk has been documented internally (`d3_e4b_floor_mechanism_thinking_trace`, May 2026) but is under-discussed publicly. The measurement-design pattern is, as far as I can tell, novel.

## 2. The Bug (≤ 600 words)

`gemma4:e4b` is a Google Gemma 4 model with a Capabilities declaration of `thinking` (verifiable via `ollama show gemma4:e4b`). It generates a structured "Thinking Process" block before the user-facing answer.

**The gotcha**: ollama's `/api/generate` strips the thinking block from the `response` field. The `eval_count` (total tokens generated) still includes it. So when `num_predict` is small (we ran at 400, ollama's safety cap is `done_reason="length"` at the limit), the thinking block alone can consume 100% of the budget — and `response` arrives as an empty string.

Measured behavior on our hardware (RTX 4070 SUPER 12 GB, gemma4:e4b Q4_K_M):
- Default-mode call at `num_predict=400`: empty response, 4.6s wall-clock, `eval_count=400`, `done_reason=length`
- Same prompt with `think: false` (Ollama body field): 245-char response, 10.5s wall-clock, complete answer

The same pattern surfaces under the `complete_with_retry` budget logic (`core.reasoning.budget` in our codebase): an empty string registers as a degenerate generation, but the retry escalates `num_predict` until the cap is high enough for both the thinking block AND a real answer — which masks the cost issue for anyone who only watches latency.

## 3. The Fair-Comparison Question (≤ 500 words)

We initially planned to benchmark gemma4:e4b against Claude with `--force-think off`. An operator on our review pushed back:

> "젬마4 think 모드는 그 모델 자체 내장된 능력인데, 그것을 일부러 off 로 내리고 다른 모델과 측정 비교하는 것이 공정한 평가가 맞는가?"

The catch is real. We landed on a 3-cell paired design:

| Cell | LOCAL | think mode | num_predict | What it measures |
|---|---|---|---|---|
| A | gemma4:e4b | OFF | 400 | "production cost-conscious quality" |
| B | gemma4:e4b | ON | 2000 | "vendor-spec capability with adequate budget" |
| C | gemma3:12b | n/a (no thinking) | 400 | "non-thinking medium tier baseline" |

Δ(A − B) = the measured value of gemma4's thinking lift, at the cost of 5× larger budget + corresponding latency.
Δ(A − C) = "is the small thinking-off model competitive with the medium non-thinking model at the same budget?".
Δ(B − C) = "does gemma4's best mode beat the medium non-thinking baseline?".

Each Δ answers a different deployment question. A single cell isn't operator-decision-grade.

Hardware constraint: gemma3:27b (16.2 GB) would need CPU offload on our 12 GB GPU. Declined; gemma3:12b (7.6 GB, fully GPU-resident) is the honest medium-tier comparator.

## 4. Results — ⟨TBD after measurement⟩

### Cell A: gemma4:e4b OFF cap=400 vs Claude
- LOCAL CORRECT rate: ⟨TBD⟩
- LOCAL ABSTAINED rate: ⟨TBD⟩
- Mean LOCAL latency: ⟨TBD⟩
- Δ (cloud − local) on correct rate: ⟨TBD⟩

### Cell B: gemma4:e4b ON cap=2000 vs Claude
- LOCAL CORRECT rate: ⟨TBD⟩
- LOCAL ABSTAINED rate: ⟨TBD⟩
- Mean LOCAL latency: ⟨TBD⟩ (expected ≫ Cell A — thinking + larger budget)
- Δ (cloud − local): ⟨TBD⟩

### Cell C: gemma3:12b cap=400 vs Claude
- LOCAL CORRECT rate: ⟨TBD⟩
- LOCAL ABSTAINED rate: ⟨TBD⟩
- Mean LOCAL latency: ⟨TBD⟩
- Δ (cloud − local): ⟨TBD⟩

### Cross-cell Δs — ⟨TBD⟩

## 5. The Guard Architecture (≤ 700 words)

The bug surfaced AFTER we had a UI/UX cycle running in parallel — 21 PRs touching frontend + intent_classifier + meta inventory mode. Most were measurement-irrelevant. One PR (#962) introduced a regex that matched the literal English substring `News` and silently routed retrieval queries to the meta-inventory handler in the live chat path. A separate PR (#960) added a new intent regex pattern that also matched English `class ` substrings (a long-running bug, not the v0.6.1 cycle's fault). Neither broke the paired harness directly because the harness bypasses the intent classifier — but BOTH would have polluted live-user behavior.

We landed three layers of guard to catch these classes of drift before they reach a measurement run:

**Layer 1 — Lock test** (`tests/test_measurement_critical_surfaces.py`):
- Asserts the exact `(module, symbol, value)` tuples the paired harness consumes
- 11 tests covering constants (`NUM_CTX`, `OLLAMA_URL`, `FIXTURE`, ...), top-level functions (`call_local`, `judge`, `aggregate`, ...), downstream surface (`core.abstraction`, `core.reasoning.backends.{claude_code_cli, diffusiongemma_local}`, `core.reasoning.think_policy`)
- Source-level pin: lock-test greps `local_vs_cloud_paired.py` for the `think_policy` import + `is_thinking_capable(model)` call + the `"think"` field — a refactor that strips the integration trips this test red.

**Layer 2 — Pre-flight check** (`scripts/research/pre_flight_check.py`):
- 6 checks run at the start of every paired launch
- `fixture_rows` (≥9 rows per answerable type)
- `regex_sweep` (no fast-path regex matches the fixture's retrieval queries — caught the v17 "News" bug AND the long-running `class ` bug)
- `backend_registry` (exactly the expected backends — extras = `JAMES_PLUGINS` leak)
- `abstraction_smoke` (core.abstraction symbols importable + callable)
- `diffusiongemma_optin` (env flag + registry presence consistent)
- `thinking_mode_contract` (think_policy surface intact, `JAMES_GEMMA4_E4B_THINK_OFF=1` set)
- Output JSON records every result + the `--skip-pre-flight` flag so an operator cannot bypass invisibly.

**Layer 3 — Production code already aligned**:
- 5 cognitive stages (planner / reflect / verify / engine_synth / query_rewriter) + the base `gemma_client.client.py` all consult `think_policy` before issuing Ollama requests
- The paired harness was the last bypass site. v18.4 closed it.

## 6. Caveats (≤ 400 words)

- **Small n**. 9 query × 3 runs per cell = 27 trials per cell. First N answerable per question_type from MultiHop-RAG (Tang & Yang 2024) — not a representative random sample.
- **Reasoning-isolated, not full pipeline**. Both LOCAL and CLOUD get the same full gold evidence. Doesn't measure retrieval contribution. A separate full-pipeline run is required before any production Pareto claim.
- **Judge = Claude**. Self-preference is possible. Mitigated by blinded A/B + evidence-grounded grading + per-question raw dump. Treat the auto-score as a signal; confirm against raw answers.
- **Hardware-specific**. RTX 4070 SUPER 12 GB. gemma3:27b would need CPU offload here — not measured. gemma4:e4b's thinking-block size at other quant levels (we ran Q4_K_M) may differ.
- **Multi-hop QA only**. The gotcha may not surface the same way in single-hop factual retrieval, summarization, or coding-mode prompts.
- **Lenient judge**. ABSTAINED + INCORRECT are scored separately, but two contradictory CORRECT answers can both land CORRECT.

## 7. Reproducible Code

- Repo: `<JAMES-RAG-Evol>` (link)
- Paired harness: `scripts/research/local_vs_cloud_paired.py`
- Pre-flight: `scripts/research/pre_flight_check.py`
- Lock-test: `tests/test_measurement_critical_surfaces.py`
- think_policy: `core/reasoning/think_policy.py`
- Exact reproduction (3-cell):

```bash
JAMES_ENABLE_CLAUDE_BACKEND=1 JAMES_GEMMA4_E4B_THINK_OFF=1 \
  python scripts/research/local_vs_cloud_paired.py \
    --local-model gemma4:e4b --n-per-type 3 --n-runs 3 \
    --num-predict 400 --force-think off \
    --output cellA.json

JAMES_ENABLE_CLAUDE_BACKEND=1 \
  python scripts/research/local_vs_cloud_paired.py \
    --local-model gemma4:e4b --n-per-type 3 --n-runs 3 \
    --num-predict 2000 --force-think on \
    --output cellB.json

JAMES_ENABLE_CLAUDE_BACKEND=1 \
  python scripts/research/local_vs_cloud_paired.py \
    --local-model gemma3:12b --n-per-type 3 --n-runs 3 \
    --num-predict 400 --force-think off \
    --output cellC.json
```

Raw JSONs include the full `caveat` block, the `pre_flight.results` audit, and per-trial blinded A/B order.

## 8. Recommendation for gemma4 users (≤ 300 words)

1. **Don't run gemma4:e4b at `num_predict < ~450`** unless you set `think: false` on the Ollama call. If you use ollama's `/api/generate` or any wrapper that doesn't expose the `think` field, switch to a wrapper that does (or set the model's default via `Modelfile`).
2. **Audit your `complete_with_retry` / budget code**. Empty-string returns from gemma4 at low cap are NOT timeouts or errors — they are silent budget exhaustion on hidden thinking tokens.
3. **Build a sanity check**. Print `eval_count` + `done_reason` + `len(response)` for every gemma4 call during development. If `len(response)==0` and `done_reason==length`, you have this bug.
4. **For benchmarks**: present BOTH (think=OFF, low cap) AND (think=ON, high cap) cells. Single-cell results don't support deployment decisions.

---

**FINAL PRE-PUBLISH CHECKLIST** (do not skip):
- [ ] All 3 cells measured + raw JSONs committed
- [ ] Quality Delta Card written per cell
- [ ] Memory entry `project_thinking_mode_fairness_design_v18_5.md` referenced
- [ ] Operator review of headline framing
- [ ] Confirm no over-claim re: "first to document" — scan HF discussions, r/LocalLLaMA, ollama issues for prior posts
- [ ] Repo link works
- [ ] CAVEATS section verbatim from harness output JSON
