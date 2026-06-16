# Quality Delta Card — v18.7 Phase 3b local tier ladder

**Date**: 2026-06-16
**Hardware**: RTX 4070 SUPER 12 GB, Ryzen 7 7700, 31 GB RAM
**Fixture**: MultiHop-RAG (reasoning-isolated — gold evidence injected)
**Sample**: 9 queries × 3 paired runs = 27 trials per cell
**Question**: does complexity-tier escalation (4b → 12b → 27b) justify wiring D5 to route by query complexity among local models?

## The reversal (why gold-grounded matters)

A judge-only read concluded "escalation is pointless" (4b=12b=gemma4=1.0 > 27b=0.704) and was briefly asserted to the operator. The deterministic `gold_signals` recheck **reversed** it:

| Model | Rung | Judge | **Gold-grounded** | Judge bias | Pair latency |
|---|---|---|---|---|---|
| **gemma3:27b** | deep | 0.704 | **1.000** | **−0.296 (under-credit)** | 60.2s |
| gemma3:12b | standard | 1.000 | 0.889 | +0.111 | 27.5s |
| gemma3:4b | light | 1.000 | 0.852 | +0.148 | 26.4s |
| gemma4:e4b | (current default) | 1.000 | 0.815 | +0.185 | 23.2s |

**27b is the only cell at gold-grounded 1.000.** The judge under-credited it by −0.296 because 27b answers verbosely ("Yes, both statements are true according to the provided texts. The New York Times article states...") and the judge tripped on the elaboration — the gold term was present in every case. Same judge-trip class as v18.6.

## Findings

1. **Complexity escalation has a basis** — bigger model = more gold-accurate. The judge-only "pointless" conclusion was an artifact. Not "meaningless".
2. **But not dramatic** — 27b vs 12b = **+0.111** (modest), and 27b costs **2.3× latency + verbose answers** that confuse the judge (and likely downstream consumers / users).
3. **Side finding**: the current production default `gemma4:e4b` is the **lowest** of the four on evidence-rich retrieval (gold 0.815) — below even gemma3:4b (0.852). Yet on chat (Phase 2b) gemma4:e4b 0.833 > gemma3:4b 0.750. **Task type flips the model ranking** (open-ended chat vs evidence-rich retrieval) — this is exactly why mode routing (chat≠retrieval) is meaningful.

## Phase 3c decision (operator)

Not "shelve as meaningless" but **"+0.111 accuracy vs (2.3× latency + verbose answers) trade-off"**:
- Wire D5 complexity escalation only if the modest gold-accuracy gain justifies the latency + verbosity cost.
- If wired, pair 27b with a response_style that curbs verbosity (also helps downstream + judge agreement).
- Phase 3a ladder infra (`LOCAL_TIER_LADDER`, `resolve_local_tier`) stays valid regardless.

## Caveats

- **n=9 queries (27 trials)**, single fixture, reasoning-isolated (gold injected = easier than production retrieval). Directional signal, not a publishable claim.
- **judge-only is unreliable here** — the headline reversal is the lesson: any fixture with `gold_signals` must get a gold-grounded recheck BEFORE concluding (negative OR positive).
- gold-grounded single-hit threshold (term OR alias present). Does not measure full answer correctness, only gold-term presence.
- 27b on 12 GB GPU runs with partial offload (60s/pair) — latency is hardware-specific.

## Reproducibility

```bash
# per cell (multihop, reasoning-isolated)
JAMES_ENABLE_CLAUDE_BACKEND=1 [JAMES_GEMMA4_E4B_THINK_OFF=1 for gemma4] \
  python scripts/research/local_vs_cloud_paired.py \
    --fixture multihop --local-model <model> \
    --n-per-type 3 --n-runs 3 --num-predict 400 --force-think off \
    --output reports/research-runs/v18.7-phase3b-tier-ladder/cell_<name>.json

python reports/research-runs/v18.7-phase3b-tier-ladder/gold_grounded_recheck.py
```

Raw: `cell_{light_4b,gemma4_e4b,standard_12b,deep_27b}.json` + `gold_grounded_summary.json`.

## Related memory

- `[[project_d5_complexity_routing_negative]]` — the self-corrected conclusion (judge→gold reversal)
- `[[project_judge_reliability_gold_grounded_v18_6]]` — the rule this measurement re-validated
- `[[project_graph_rag_reasoning_boundary]]` — companion (reasoning ≈ evidence quality + backbone)
- `[[project_routing_buildout_5phase_v18_7]]` — 5-phase parent
