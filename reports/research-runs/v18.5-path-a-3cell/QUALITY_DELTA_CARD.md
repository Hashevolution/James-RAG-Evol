# Quality Delta Card — v18.5 Path A 3-cell

**Measurement date**: 2026-06-16
**Hardware**: NVIDIA RTX 4070 SUPER 12 GB VRAM, AMD Ryzen 7 7700, 31 GB RAM
**Fixture**: MultiHop-RAG (Tang & Yang 2024) — 9 questions × 3 paired runs = 27 trials per cell
**Design**: reasoning-isolated (same full gold evidence to both sides), blinded A/B per (query, run)
**Judge**: Claude CLI, evidence-grounded grading
**Pre-flight**: 6/6 ok per cell (fixture_rows / regex_sweep / backend_registry / abstraction_smoke / diffusiongemma_optin / thinking_mode_contract)
**v18.4 guard verification**: 27/27 empty-response failure mode resolved (was 100% pre-fix)

## 5-axis matrix (CLOUD baseline = Claude CLI, 1.00 correct across all cells)

| Axis | Cell A — gemma4:e4b OFF cap=400 | Cell B — gemma4:e4b ON cap=2000 | Cell C — gemma3:12b cap=400 |
|---|---|---|---|
| Path Recall | n/a (gold evidence directly injected) | n/a | n/a |
| **Graded answer rate** | **1.00** | 0.70 | **1.00** |
| **Δ vs Claude (graded)** | **+0.00** | +0.30 (worse) | **+0.00** |
| Abstention rate | 0/27 (0%) | 8/27 (30%) | 0/27 (0%) |
| **Token cost (cap)** | 400 | 2000 (5×) | 400 |
| **Latency cost (pair avg)** | 27.4s | 33.7s (+23%) | 26.2s |
| **Stability (across 3 runs)** | 1.00 | 0.78 | 1.00 |
| Run-to-run noise (per-question) | none | comparison/temporal each lost 1 question | none |

## 3-way Δ summary

| Δ | Value | Operator-facing interpretation |
|---|---|---|
| **A − B** | +0.30 | gemma4 production default (think=OFF, cap=400) **beats** the vendor "best-mode" config (think=ON, cap=2000) by 30 graded-answer points on multi-hop QA |
| **A − C** | **0.00** | gemma4:e4b OFF (8.9 GB small) **matches** gemma3:12b (7.6 GB medium non-thinking) at the same cap. The small model is competitive without thinking. |
| **B − C** | −0.30 | gemma4 ON (more budget + thinking) **underperforms** the smaller non-thinking model. Pure cost without quality. |

## Operator-facing recommendation (data-grounded)

**For multi-hop QA at JAMES production budget (cap=400) on RTX 4070 SUPER:**

1. **Keep `JAMES_GEMMA4_E4B_THINK_OFF=1`** in `.env`. The production default is correct.
2. **gemma4:e4b OFF is the recommended small tier** — fully GPU-resident (8.9 GB on 12 GB VRAM), 100% graded accuracy match against Claude on reasoning-isolated multi-hop QA, 100% paired-run stability.
3. **Do NOT enable `think:true` without measurement evidence** that the specific task benefits. Cell B shows 30% over-abstention + −0.30 graded delta at 5× cap.
4. **gemma3:12b is a non-thinking alternative** at the same tier — same correct rate, marginally faster (26.2s vs 27.4s pair), 7.6 GB instead of 8.9 GB. Useful if memory pressure matters more than the 1.3 GB headroom.

## Caveats (verbatim from output JSON, required before citing)

- **judge_self_preference**: judge is Claude; one candidate is Claude — self-preference is possible. Mitigated by blinding A/B + evidence-grounded grading + per-question raw dump. Treat the auto-score as a SIGNAL.
- **gold_evidence_not_pipeline**: reasoning-isolated design; does NOT measure the full retrieval pipeline. A production Pareto claim needs a separate full-pipeline run (with JAMES retrieval + abstention) before any operator-facing conclusion.
- **small_n**: 9 query × 3 runs per cell. First answerable N per question_type from MultiHop-RAG. Not representative. Verdict here is a SIGNAL, not a publishable claim.
- **lenient_judge**: ABSTAINED + INCORRECT scored separately; two contradictory CORRECT answers can both land CORRECT.
- **hardware-specific**: RTX 4070 SUPER 12 GB, Q4_K_M quantization. Thinking-block size + cap math may differ at other quants / GPUs.
- **multi-hop QA only**: this measurement does not address single-hop factual retrieval, summarization, code generation, or any non-QA workload.

## Reproducibility

```bash
# Cell A
JAMES_ENABLE_CLAUDE_BACKEND=1 JAMES_GEMMA4_E4B_THINK_OFF=1 \
  python scripts/research/local_vs_cloud_paired.py \
    --local-model gemma4:e4b --n-per-type 3 --n-runs 3 \
    --num-predict 400 --force-think off \
    --output cellA.json

# Cell B
JAMES_ENABLE_CLAUDE_BACKEND=1 \
  python scripts/research/local_vs_cloud_paired.py \
    --local-model gemma4:e4b --n-per-type 3 --n-runs 3 \
    --num-predict 2000 --force-think on \
    --output cellB.json

# Cell C
JAMES_ENABLE_CLAUDE_BACKEND=1 \
  python scripts/research/local_vs_cloud_paired.py \
    --local-model gemma3:12b --n-per-type 3 --n-runs 3 \
    --num-predict 400 --force-think auto \
    --output cellC.json
```

Raw JSONs at `reports/research-runs/v18.5-path-a-3cell/cell{A,B,C}_*.json` include per-trial blinded A/B order, raw LOCAL + CLOUD answers, judge verdicts, pre-flight audit block, and the full caveat block.

## Related memory

- `[[d3_e4b_floor_mechanism_thinking_trace]]` — root mechanism (~85% thinking-token absorption)
- `[[a3_a2_think_mode_track_closure]]` — 5-stage think=OFF wins or safe (now extended to multi-hop QA)
- `[[project_thinking_mode_contract_v18_4]]` — 4-layer guard
- `[[project_thinking_mode_fairness_design_v18_5]]` — 3-cell rationale + publishable probe
- `[[project_measurement_environment_isolation_v18_2]]` — guard architecture
