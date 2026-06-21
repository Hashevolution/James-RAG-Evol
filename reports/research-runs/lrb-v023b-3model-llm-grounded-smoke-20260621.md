# LRB v0.2.3b — 3-model LLM-grounded smoke results (2026-06-21)

Runner: `scripts/research/lrb_run_v023b_s3_cross_model.py
--scale smoke --modes llm-grounded --models gemma4:e4b,gemma3:12b,mixtral:8x7b`
Prereg: `docs/research/lrb-v023b-s3-cross-model-preregistration-2026-06-12.md`

Scale: S3 **smoke** (scenario_S3_smoke.json — 100 queries / 282 events).
3 SUTs × 3 local reranker models × 1 mode (llm-grounded). The 4th prereg
leg (`claude-haiku-4-5`) is excluded here — it needs the cloud backend
(`JAMES_ENABLE_CLAUDE_BACKEND` + Max-plan CLI). Wall-clock ≈ 2 h
(mixtral cells ≈ 28 min each; gemma4 ≈ 5.5 min).

## Gap-table (R@1 = correct *current* fact retrieved at rank 1)

| reranker model | vanilla | naive-supersede | **james** | V<N<J | **J−N gap** |
|---|---|---|---|---|---|
| gemma4:e4b   | 0.51 | 0.74 | **0.95** | ✅ | **+0.21** |
| gemma3:12b   | 0.62 | 0.76 | **0.98** | ✅ | **+0.22** |
| mixtral:8x7b | 0.53 | 0.71 | **0.85** | ✅ | **+0.14** |
| *(ref) token-mode* | *0.51* | *0.73* | *0.93* | *✅* | *+0.20* |

Temporal accuracy (time-travel correctness): james 0.99–1.00 across all
3 models; naive-supersede **0.78–0.80**; vanilla 0.97–0.99.

## Findings

1. **V<N<J holds 3/3 under LLM reranking.** The +0.20 J−N gap seen in
   the deterministic token-mode reproduces at +0.14–+0.22 with a real
   LLM reranker. → JAMES's advantage lives in the SUT's retrieval /
   supersede mechanism, **not** the reranker — rebuts the "token-overlap
   scoring artifact" objection.

2. **Bigger backbone does NOT widen the gap** (mixtral 47B has the
   *smallest* gap +0.14 and lowest james R@1 0.85; gemma3:12b the
   largest +0.22 / 0.98). → JAMES's lift is structural
   (validity-window), not a function of model capability — consistent
   with it being a mother-platform layer contribution.

3. **The two-axis story.** vanilla keeps all history → stale facts win
   rank-1 (low R@1, high temp_acc); naive-supersede deletes superseded
   facts → current fact rank-1 improves but **time-travel breaks**
   (temp_acc drops to ~0.79); **james marks a validity-window (no
   delete)** → wins BOTH axes (R@1 0.85–0.98 AND temp_acc 0.99–1.00).
   This is the replayable-audit differentiator.

## Honest caveats

- **smoke scale (100 q)**, not publication (1000). The v0.2.3 token-mode
  publication run already showed R@1 V<N<J preserved 4/4 scale points;
  the LLM-grounded *publication* run is the strong claim and is NOT done
  here (≈ 10× wall-clock, ~1 day with mixtral).
- 3-local-model only; the `claude-haiku-4-5` cross-leg is pending the
  cloud backend.
- Per-cell `result.json` committed; per-row `bench.jsonl` is gitignored.

## One-line
JAMES's validity-window advantage (J−N ≈ +0.20) reproduces across **3
distinct LLM rerankers** AND across **token-mode ↔ LLM-grounded**, and is
**independent of backbone size** — strengthening that it is a structural
mechanism, not a model or scorer artifact.
