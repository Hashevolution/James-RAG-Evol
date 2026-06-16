# DRAFT — Publishable Writeup (v18.5 pivot)

**Status**: data complete (3 cells measured). Pivot applied after prior-art scan.

**Working title**: "How a UX cycle nearly poisoned our RAG benchmark — the 4-layer guard we built (and one measurement that paid for it)"

**Honest framing** (prior-art adjusted, [[feedback_finding_size_honest_framing]]):
- **NOT a thinking-mode discovery** — Ollama issues #15428 / #16456 / #16584 / #14793 + Google AI docs + webscraft/markaicode blogs all document the gemma4 thinking-token tax. We replicate; we don't discover.
- **NOT a fair-comparison framework** — HRBench / OptimalThinkingBench / arxiv 2605.04488 already publish the same-budget, same-mode paired design we use.
- **POSSIBLY novel** — pre-flight regex sweep + lock-test source-pin + "harness-as-last-bypass-site" pattern. Industry has RAG CI gates (Patronus / Braintrust / Confident AI), and LLM Readiness Harness covers the general space, but no public artifact I found describes catching intent-classifier substring drift (`News` → meta-mode) via fixture sweep BEFORE the paired run.
- **One narrow data point** — gemma4:e4b OFF cap=400 matches gemma3:12b on multi-hop QA. Production-budget validation for "small + thinking-off" tier. Not a benchmark; an operator-grade signal.

---

## 1. Hook (~250 words)

We were about to publish "gemma4:e4b ABSTAINS on 100% of multi-hop QA when paired against Claude". The headline was technically true — 27/27 trials returned ABSTAINED in our v18.3 Path A baseline. It was also meaningless.

The model was producing empty strings. Our judge classified empty strings as ABSTAINED. The reason was documented inside Google's Gemma 4 docs and inside multiple Ollama issues (#15428 / #16456 / #14793), and we'd even cited it as a memory note in our codebase: gemma4 is a thinking model, ~85% of `num_predict` is hidden reasoning tokens that `/api/generate` strips from `response`. cap < ~450 = empty answer.

What surprised us wasn't the bug. What surprised us was that we'd built five UX cycles' worth of guards specifically to catch measurement-environment drift, and they didn't catch this one. The harness was the LAST call site bypassing our `think_policy` plumbing. Production code paths consult it; the measurement tool didn't.

This writeup is two narrow contributions:
1. A guard pattern — pre-flight regex sweep + lock-test source-pin + harness-as-last-bypass-site — that catches this class of "production-aligned, tooling-misaligned" failures.
2. One operator-grade data point: at production budgets (cap=400, RTX 4070 SUPER 12 GB), gemma4:e4b with thinking OFF matches gemma3:12b on multi-hop QA. Smaller-mode-off can match medium-mode-off.

Neither claim is novel against well-curated prior art. Both have specific reproduction value.

## 2. The bug (~400 words)

Skip if you've already chased a thinking-model `num_predict` issue. Cited prior art covers this comprehensively; we add nothing.

**Quick mechanics for context**:
- `ollama show gemma4:e4b` → Capabilities includes `thinking`
- model emits structured reasoning before user-facing answer
- `/api/generate` strips the reasoning block from `response`; `eval_count` includes it
- at cap=400, eval_count hits 400, done_reason="length", response="" (empty string)

**Direct repro on our hardware**:
```
Default-mode call at num_predict=400: response='', eval_count=400, done_reason=length, 4.6s
Same prompt with think:false in body: response=245 chars, complete answer, 10.5s
```

This is on RTX 4070 SUPER 12 GB Q4_K_M. Numbers may differ at other quants.

**Why a JAMES `complete_with_retry` wouldn't have caught it**: empty string registers as a degenerate generation, but our retry escalates `num_predict` until BOTH thinking + answer fit. The mask hides the cost from anyone who only watches latency in production. We caught it during measurement design, not during deployment.

## 3. The guard pattern (~700 words)

Three layers, in order of discovery during our v0.6.1 chrome cycle.

### Layer 1 — Lock test

`tests/test_measurement_critical_surfaces.py` (~360 lines, 11 tests).

The paired harness imports concrete symbols from concrete modules at specific names. A refactor that renames `core.abstraction.run_cloud_egress` → `core.abstraction.cloud_egress` would silently break the harness AND every paired result produced after that PR. We lock the names:

```python
_HARNESS_TOP_LEVEL_REQUIRED = {"FIXTURE", "NUM_CTX", "OLLAMA_URL",
                               "call_local", "call_cloud_via_abstraction",
                               "judge", "aggregate", "main", ...}
_DOWNSTREAM_SURFACE = {
    ("core.abstraction", "default_decider", "callable"),
    ("core.abstraction", "run_cloud_egress", "callable"),
    ("core.reasoning.backends.claude_code_cli", "ClaudeCodeCliBackend", "class"),
    ("core.reasoning.think_policy", "is_thinking_capable", "callable"),
    ...
}
```

Plus source-level pins for behavioral integrations:

```python
def test_call_local_honors_thinking_contract(self):
    src = harness_path.read_text(encoding="utf-8")
    self.assertIn("from core.reasoning.think_policy", src)
    self.assertIn("is_thinking_capable(model)", src)
    self.assertIn('"think"', src)
```

Brittle by design. A refactor that strips `think_policy` from the harness trips this test red before measurement.

### Layer 2 — Pre-flight check

`scripts/research/pre_flight_check.py` (~390 lines, 6 checks). Runs at the start of every paired launch:

```
✓ [ok  ] fixture_rows             — 75 answerable queries available
✓ [ok  ] regex_sweep              — 0/75 false positives across 4 fast-path modes
✓ [ok  ] backend_registry         — registered=['claude_code_cli', 'ollama_local']
✓ [ok  ] abstraction_smoke        — default_decider=function; run_cloud_egress callable
✓ [ok  ] diffusiongemma_optin     — flag=None registered=False
✓ [ok  ] thinking_mode_contract   — think_policy intact; JAMES_GEMMA4_E4B_THINK_OFF=1
```

The `regex_sweep` is the load-bearing check. It sweeps every fast-path regex bucket (meta / wiki_edit / coding / self_evolve, excluding the chat fallback) against the fixture's retrieval queries. A pattern that matches an answerable query is a "live chat path will misroute" bug. We caught two during the cycle:
- v17: `(...|new)` matched English `New York` / `Hacker News` substrings → routed to meta
- v0.1.0-alpha: `\b(class )` matched `class-action lawsuit` / `first-class flights` → routed to coding

Both were live-chat regressions. The paired harness bypasses intent_classifier, so the math survives; the operator's chat surface doesn't. Catching it at measurement-launch time is the honest move.

### Layer 3 — Production code already aligned

Five cognitive stages (`planner / reflect / verify / engine_synth / query_rewriter`) + base `gemma_client.client.py` honor `think_policy`. We verified by ripgrep. The paired harness was the only call site outside production stages; v18.4 closed it.

### The pattern

> Measurement tools tend to be the LAST call site to honor production contracts. They were the FIRST call site to be written, predate the contract, and rarely show up on "find all callers" grep when the contract lands.

The guard architecture is three-layered for a reason: lock-test catches structural drift (renames), pre-flight catches data drift (regex / fixture changes), production-alignment is the asymptote (every caller honors the contract). Each layer fails differently. Treating them as one would have missed the cases at the seams.

## 4. The one data point (~400 words)

After all four layers landed, we re-ran Path A as a 3-cell paired comparison.

| Cell | Model | think | cap | LOCAL correct | Latency/pair | Stability |
|---|---|---|---|---|---|---|
| A | gemma4:e4b | OFF | 400 | **1.00** | 27.4s | 1.00 |
| B | gemma4:e4b | ON | 2000 | 0.70 | 33.7s | 0.78 |
| C | gemma3:12b | n/a | 400 | **1.00** | 26.2s | 1.00 |

Claude (CLI) was the cloud baseline; 1.00 across all cells (n=9 query × 3 paired runs each, reasoning-isolated against gold MultiHop-RAG evidence).

**Δ(A − B) = +0.30**. gemma4:e4b's production default (think OFF, cap 400) outperforms its vendor-spec "thinking on, larger budget" config on this fixture by 30 graded-answer points. The thinking trace adds 5× cap budget, 23% wall-clock latency, run-to-run instability (1.00 → 0.78), and the model abstains 30% of the time instead of 0%.

**Δ(A − C) = 0.00**. gemma4:e4b OFF (8.9 GB small tier) matches gemma3:12b (7.6 GB medium non-thinking) at the same cap. The small thinking-off model is competitive with the medium non-thinking model at the same budget.

**Δ(B − C) = −0.30**. gemma4 with thinking on underperforms gemma3:12b at the smaller model's cap. Pure cost.

Operator-facing: if you have an `JAMES_GEMMA4_E4B_THINK_OFF=1`-equivalent in your stack, keep it. The default is correct for this task class.

**Caveats** (verbatim from the JSON output's `caveat` block):
- judge_self_preference (judge = Claude; mitigated but nonzero)
- gold_evidence_not_pipeline (reasoning-isolated; doesn't measure retrieval)
- small_n (9 questions × 3 paired runs; first answerable N per question_type; not representative)
- lenient_judge (ABSTAINED + INCORRECT separate; two contradictory CORRECT both land CORRECT)
- hardware-specific (RTX 4070 SUPER, Q4_K_M)
- multi-hop QA only (no single-hop / summarization / code claim)

**Prior art for "thinking ON often hurts at small-task budgets"**:
- OptimalThinkingBench (arxiv 2508.13141): "current thinking models overthink even on simple queries without improving performance"
- AlphaOne (arxiv 2505.24863): test-time thinking-mode switching
- arxiv 2605.04488: "Controlled Instant-vs-Thinking Comparison Across Five Frontier Models"

We extend the same finding to gemma4:e4b at production budgets on multi-hop QA. Narrow specific data point; not a category contribution.

## 5. What we DON'T claim

- We did NOT discover the gemma4 thinking-token tax. It's in Google AI docs.
- We did NOT invent same-mode, same-budget paired comparison. HRBench did.
- We did NOT pioneer RAG CI gates. Patronus / Braintrust / Confident AI sell that.
- We DID build a guard pattern that catches a class of measurement-environment drift faster than the post-hoc "compare two JSON outputs" workflow most RAG benchmarks rely on. We use it. You might find it useful.

## 6. Reproducible code

- Repo: `<JAMES-RAG-Evol>` (link goes here)
- Paired harness + 3-cell CLI: `scripts/research/local_vs_cloud_paired.py`
- Pre-flight: `scripts/research/pre_flight_check.py`
- Lock-test: `tests/test_measurement_critical_surfaces.py`
- `think_policy`: `core/reasoning/think_policy.py`
- Raw 3-cell JSONs: `reports/research-runs/v18.5-path-a-3cell/`

```bash
# Reproduces the table above on your own ollama + claude CLI install
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
    --num-predict 400 --force-think auto \
    --output cellC.json
```

---

## Pre-publish checklist

- [x] All 3 cells measured + raw JSONs committed
- [x] Quality Delta Card written (`QUALITY_DELTA_CARD.md`)
- [x] Memory entries referenced (`project_thinking_mode_*_v18_*.md`)
- [x] Prior art scan complete; honest-framing pivot applied
- [ ] Operator review of headline framing
- [ ] Repo public link works
- [ ] CAVEATS section pasted verbatim from harness output JSON
- [ ] Final HF / r/LocalLLaMA scan ≤ 24h before publish for any new prior art
