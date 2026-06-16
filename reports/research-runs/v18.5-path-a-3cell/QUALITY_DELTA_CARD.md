# Quality Delta Card — v18.5 Path A 3-cell

**Measurement date**: 2026-06-16
**Hardware**: NVIDIA RTX 4070 SUPER 12 GB VRAM, AMD Ryzen 7 7700, 31 GB RAM
**Fixture**: MultiHop-RAG (Tang & Yang 2024) — 9 questions × 3 paired runs = 27 trials per cell
**Design**: reasoning-isolated (same full gold evidence to both sides), blinded A/B per (query, run)
**Judge**: Claude CLI, evidence-grounded grading
**Pre-flight**: 6/6 ok per cell (fixture_rows / regex_sweep / backend_registry / abstraction_smoke / diffusiongemma_optin / thinking_mode_contract)
**v18.4 guard verification**: 27/27 empty-response failure mode resolved (was 100% pre-fix)

## 5-axis matrix (CLOUD baseline = Claude CLI)

**v18.6 update**: an operator catch — "Claude 답이 확실히 맞는가?" — forced a gold-grounded deterministic recheck (`gold_grounded_recheck.py` against the fixture's per-query `gold_signals`). The judge column below is the v18.5 published value; the gold-grounded column is the corrected reality. The judge gap is the lenient-bias correction this PR documents.

| Axis | Cell A — gemma4:e4b OFF cap=400 | Cell B — gemma4:e4b ON cap=2000 | Cell C — gemma3:12b cap=400 | CLOUD — Claude CLI |
|---|---|---|---|---|
| Path Recall | n/a (gold evidence directly injected) | n/a | n/a | n/a |
| **Graded — judge (Claude)** | 1.00 | 0.70 | 1.00 | 1.00 |
| **Graded — gold-grounded** | **0.81** | 0.78 | **0.89** | **1.00** |
| **Judge bias on LOCAL** | **+0.19 over-credit** | mixed (+2 over, −4 under) | **+0.11 over-credit** | 0.00 (perfect agreement) |
| **Δ vs Claude (gold-grounded)** | **−0.19** | −0.22 | **−0.11** | 0 |
| Abstention rate (judge) | 0/27 (0%) | 8/27 (30%) | 0/27 (0%) | 0/27 (0%) |
| **Token cost (cap)** | 400 | 2000 (5×) | 400 | n/a |
| **Latency cost (pair avg)** | 27.4s | 33.7s (+23%) | 26.2s | included above |
| **Stability (judge agreement across 3 runs)** | 1.00 | 0.78 | 1.00 | 1.00 |
| Run-to-run noise (per-question) | none | comparison/temporal each lost 1 question | none | none |

## 3-way Δ summary

| Δ | judge-based (v18.5) | **gold-grounded (v18.6 corrected)** | Operator-facing interpretation |
|---|---|---|---|
| **A − B** | +0.30 | **+0.03** | gemma4 OFF still beats ON, but the lift collapses once judge bias is removed. The difference is small — thinking ON is *not significantly worse* on this fixture, but the latency + stability costs (Cell B) make it operationally worse anyway. |
| **A − C** | 0.00 | **−0.08** | gemma3:12b actually **edges** gemma4:e4b OFF. Both are competitive, but gemma3:12b is mildly more accurate at the same cap (and faster + smaller). |
| **B − C** | −0.30 | −0.11 | gemma4 ON still underperforms gemma3:12b but the gap narrows under gold grounding. |
| **A vs Claude** | +0.00 | **−0.19** | Cloud advantage exists; v18.5's "parity" was lenient-judge artifact. |
| **C vs Claude** | +0.00 | **−0.11** | Same — small but consistent cloud advantage. |

## Operator-facing recommendation — v18.6 corrected (data-grounded)

**For multi-hop QA at JAMES production budget (cap=400) on RTX 4070 SUPER:**

1. **Keep `JAMES_GEMMA4_E4B_THINK_OFF=1`** in `.env`. Cell A vs Cell B shows thinking ON adds 23% latency + 22% stability loss + abstention spike with no graded benefit (Δ +0.03 within noise).
2. **gemma3:12b *slightly* edges gemma4:e4b OFF** under gold grounding (0.89 vs 0.81). Both compete; gemma3:12b is faster + smaller + simpler.
3. **gemma4:e4b OFF retains optionality** — it's a thinking-capable model with thinking off by env contract. Future task classes where thinking provably helps (per `a3_a2_think_mode_track_closure`'s planner / reflect / verify findings — grader-positive, judge-inconclusive) can flip the same model into thinking mode without a model swap.
4. **Claude (cloud) remains the accuracy ceiling on this fixture** (1.00 gold-grounded vs ≤ 0.89 local) — but the gap (−0.11 to −0.19) is small enough that cost/latency/privacy arguments dominate the deployment choice. Direction α's "premise unproven" framing is now more accurately "premise weakly disproven; gap exists but small enough that S6/S7 cloud-tier remains operationally deferred".

**Production model selection — operator decision:**

| Option | Score | VRAM | Latency | Notes |
|---|---|---|---|---|
| **X**: gemma4:e4b OFF cap=400 (current) | 0.81 | 8.9 GB | 27.4s pair | Thinking-mode optionality preserved |
| **Y**: gemma3:12b cap=400 | 0.89 | 7.6 GB | 26.2s pair | Simpler, slightly better on this task |
| **Z**: Cloud routing per query class | 1.00 | 0 local | network bound | Privacy / cost surface — see `core.abstraction` |

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
