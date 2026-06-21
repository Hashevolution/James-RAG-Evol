# LRB v0.2.4 HR — full sweep N=100, cross-NLI (2026-06-21)

Runner: `scripts/research/lrb_v024_hr_smoke.py --n 100 --sut all
--model gemma4:e4b --verifiers roberta,deberta`
Scenario: S1 quarterly (~60 answerable queries). Generator: gemma4:e4b.
Verifiers: RoBERTa-large-MNLI (primary) + DeBERTa-v3-anli (cross-check).

HR = **hallucination rate** = fraction of answer claims NOT entailed by
the retrieved evidence (per-claim NLI).

## Results

| SUT | HR (roberta) | HR (deberta) | claims | entailed (rob/deb) | empty |
|---|---|---|---|---|---|
| vanilla | **0.492** | **0.400** | 75 | 35 / 24 | 8 |
| naive-supersede | 0.425 | 0.364 | 86 | 39 / 30 | 0 |
| **james** | 0.436 | **0.358** | 85 | 40 / 29 | 0 |

## Findings

1. **Both NLI verifiers agree: vanilla is the worst (most hallucination)**
   — 0.49 / 0.40, highest under both. And vanilla *abstained* on 8
   queries yet still hallucinated most on the answers it gave →
   keeping un-superseded stale facts inflates hallucination. Robust.

2. **james ≈ naive-supersede, indistinguishable on HR** — the ~0.01 gap
   FLIPS between verifiers (roberta: naive lower; deberta: james lower).
   On the plain hallucination-rate axis, *having a supersede mechanism*
   is what matters; the *validity-window vs delete* distinction does not
   show up here.

3. **Cross-NLI robustness**: the qualitative ordering (vanilla worst,
   james ≈ naive) holds across both verifiers; only the absolute level
   differs (DeBERTa is more lenient — 3-class, counts only contradiction
   not neutral as hallucination). The conclusion is not verifier-specific.

## Connection to the other 2026-06-21 measurements

This is the axis where JAMES does **not** uniquely win — consistent with:
- **v0.2.3b** (reports/research-runs/lrb-v023b-3model-llm-grounded-smoke-
  20260621.md): JAMES's unique advantage is on the *time-travel* axis
  (temporal_acc 0.99–1.00 vs naive-supersede ~0.79), NOT current-fact
  answer quality. HR confirms current-fact hallucination is ≈ between
  james and naive.
- **D-alce** (research-tier NLI citation 0.62/0.73): citation precision
  is a JAMES improvement target, not a strength.

Net: JAMES's moat is replayable-audit / validity-window (time-travel),
not hallucination rate or citation precision. The three measurements
triangulate this honestly.

## Caveats
- Smoke scale (~60 queries, S1), single generator (gemma4:e4b), n not
  paired across runs. NOT a verdict — a cross-NLI smoke signal.
- `is_alce_grade`-equivalent: research-tier NLI, not an official
  hallucination benchmark. Per-cell `result.json` committed;
  `bench.jsonl` gitignored.
