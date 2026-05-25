# v0.3.1 — Direction 1 (Adaptive Budgeting) cycle closure

**Theme**: ship the dynamic-token-budget mechanism as a **data-bearing experiment artifact**, not a runtime change. Default OFF; opt-in via `JAMES_ADAPTIVE_BUDGET=1`. Three publishable findings + one process finding on `gemma4:e4b` at T=0.2, validated by two A/B sweeps × N=20/cell × 7 task-weight tiers.

## Why this is a citable release

Direction 1 was designed as a runtime change to cut JAMES's reasoning cost by 60-80% on `gemma4:e4b`. The data **flipped the hypothesis**, and the data turned out to be more valuable than the hypothesis. The release ships:

- the **TaskBudget module** (`core/reasoning/budget.py`),
- **two A/B experiment drivers** (`scripts/research/v3prime_direction1_*.py`),
- **three raw JSON sweeps** (`reports/research-runs/v3prime-direction1-*.json`) totaling 280 calls across 7 task-weight tiers,
- **two result documents** that close the cycle (`reports/promo-assets/v3prime-direction1-*-result.md`),
- a **7-tier monotonic natural-stop gradient** (62 → 1681 tokens, 27× dynamic range) measured cross-sweep stable within 5% per tier.

The release is the JAMES-side validation artifact for the V3' Protocol v1 methodology spec (released as v0.3.0 → spec at `docs/research/v3prime-protocol-v1.md`), and the input data for the three-author joint piece in trajectory with Robin Converse (Triava Labs, 26b MoE cross-stack) and Ali Afana (Provia, mid-June managed-Gemini cross-stack).

## Three publishable findings

### 1. Cap is a ceiling, not the floor

`gemma4:e4b` naturally stops well below 4096 on every measured tier. Cutting cap from 4096 to 200 / 800 produced **+0% / +8% / -2% `eval_count` change**, `done_reason=stop` on every cell, zero quality regression. PR #399's lifted cap was *permission to finish*, not waste.

The token-reduction win the heuristic was designed to deliver doesn't exist on this model. What does exist:

- **Latency -17.5% / -7.3%** on substitution / light tiers (Ollama KV-cache buffer sizing)
- **~20× smaller** per-call memory allocation on substitution
- **Bounded emergency-exit** (cap=200 is a hard safety floor)

The implementation ships in tree, gated behind `JAMES_ADAPTIVE_BUDGET=1` env flag (default OFF). Operators can opt in for the latency / memory / safety benefits.

### 2. 7-tier monotonic natural-stop gradient (the quantitative workload gradient)

Combined Direction 1 (3-prompt + cognitive-stages) + Direction 4 (V3'.e) measurements on `gemma4:e4b` at T=0.2:

| Tier | Prompt | natural-stop (tokens) |
|---|---|---|
| 1 | substitution verbatim | 62 |
| 2 | light synth e-commerce | 235 |
| 3 | query_rewriter | ~370 |
| 4 | planner | ~690 |
| 5 | reflect | ~910 |
| 6 | verify | ~970 |
| 7 | heavy synth 4-step | 1681 |

**27× dynamic range**, cross-sweep noise within 5% per tier. This is the quantitative form of the joint-paper sub-clause *"the workload gradient is multi-tier monotonic on a single model."* Natural-stop length **is** the workload measurement.

### 3. `verify` is a high-clustering cognitive stage (new task-type axis on Mechanism 2)

At T=0.2, verify produces only **2-3 unique responses across 20 baseline calls (~12.5%)** — stable across two independent sweeps. Other cognitive stages at the same workload tier produce 20/20 unique. The difference: verify emits structured JSON (`{"grounded": ..., "unsupported": [...]}`), and the answer space is a small finite set.

Direction 4's Mechanism 2 (answer convergence) now has **two axes**:

- workload weight (substitution 1/20 → heavy 20/20)
- **task type** (structured-JSON outputs cluster tightly independent of workload)

This is Ali Afana's *"shortening the path"* framing made measurable for structured-output prompts.

## Process finding — falsification → revision → confirmation

The cognitive-stages sweep first ran with `CAP_LIGHT=800`. It exposed a calibration error: 800 was below reflect (926) and verify (984) natural-stop lengths, so 19/20 calls truncated and quality dropped 40-75%. The data drove a heuristic bump (`CAP_LIGHT 800 → 1200`), and the re-sweep passed cleanly: 0/20 truncation on every cell, quality 20/20 restored.

Same empirical discipline pattern as Robin Converse's 26b mode-split sweeps. Builds joint-paper trust in the protocol.

## Three-author joint piece status

3-author headline (Ali Afana + Robin Converse + Jiwon Seo) holds verbatim:

> *"Substitution is free. Synthesis costs in proportion to what it has to invent."*

Direction 1 closure adds three sub-clauses:

- *"…and inversely to parameter count."* (Robin axis-3, 2 evidence layers)
- *"…and the gradient is multi-tier monotonic — 7 measured tiers spanning 27× dynamic range."* (JAMES Direction 1)
- *"…and answer convergence has a task-type axis: structured-JSON outputs cluster independent of workload."* (JAMES Direction 1, cross-sweep validated)

The joint piece outline trigger Robin endorsed on 2026-05-24 is now load-bearing on three independent stacks: hers (26b MoE), mine (e4b cognitive stack), and Ali's mid-June Gemini backend.

## What's in this release

### Code

- `core/reasoning/budget.py` — TaskBudget module (7.2 KB)
- `core/retrieval/query_rewriter.py` — adaptive-budget wiring (default OFF, env-flag gated)
- 71 unit tests (40 `tests/test_adaptive_budget.py` + 31 `tests/test_query_rewriter.py`)
- 2 experiment drivers under `scripts/research/`

### Data

- `reports/research-runs/v3prime-direction1-adaptive-budget-20260524T050347.json` (3-prompt sweep, 120 calls)
- `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T054634.json` (cognitive v1 — falsification data)
- `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T061858.json` (cognitive v2 — PASS data)

### Documentation

- `reports/promo-assets/v3prime-direction1-adaptive-budget-result.md`
- `reports/promo-assets/v3prime-direction1-cognitive-stages-result.md` (NEW — Direction 1 final closure)
- `reports/promo-assets/v3prime-e-substitution-synthesis-result.md` (extended with 7-tier sub-finding + task-type axis)
- `CHANGELOG.md` v0.3.1 entry

## How to cite

If you use the data, drivers, or methodology, please cite the Zenodo DOI minted with this release plus the GitHub repository URL:

```
Seo, Jiwon (2026). PROJECT JAMES — Local-First Graph-RAG with
Adaptive Reasoning Budget (v0.3.1). Zenodo.
https://doi.org/10.5281/zenodo.XXXXXXX
```

(The DOI URL completes after Zenodo automatic minting; the badge will appear on the repository README.)

## Reproducibility

```powershell
git checkout v0.3.1
git pull
# Local Ollama with gemma4:e4b warm-loaded
ollama run gemma4:e4b "ping"
# 3-prompt sweep (120 calls, ~12 min)
python scripts/research/v3prime_direction1_adaptive_budget.py --n 20
# 4-stage cognitive sweep (160 calls, ~13 min)
python scripts/research/v3prime_direction1_cognitive_stages.py --n 20
```

Raw JSON outputs land under `reports/research-runs/`. The result docs interpret them; the drivers are the protocol.

## Out of scope for v0.3.1

- Flipping `JAMES_ADAPTIVE_BUDGET` default to ON — hypothesis target unmet on `gemma4:e4b`; stays OFF. Operator opt-in remains available.
- Production wiring of the 4 cognitive stages (planner / reflect / verify / synth) — cap-invariance removes urgency.
- Direction 2 (task-weight metric formalization), Direction 3 (cross-family generalization), Direction 5 (auto-routing) — separate cycles per `docs/handovers/v0.3.x-measurement-framework-track.md`.
- arXiv preprint — separate trajectory; Joint paper Direction 6(I) Stage 4 cycle (3-author byline) is the natural trigger after Ali's mid-June Gemini backend completes the third stack.

## Acknowledgements

- **Robin Converse** (Triava Labs) — 2026-05-22~24 LinkedIn endorsement of the *"parameter count buys reasoning routing precision"* framing that anchored Direction 1's design and serves as the module's vocabulary anchor. 26b MoE cross-stack data (companion repo: `triavalabs/gemma4-26b-mode-split`) is the Mechanism 1+2 cross-validation source.
- **Ali Afana** (Provia) — 2026-05-23 LinkedIn *"ceiling vs path"* / *"shortening the path"* framing that maps cleanly onto the verify task-type clustering finding. Mid-June Gemini backend is the third-stack trigger for the joint piece.

🤖 Notable assist: this release's code, drivers, result docs, and CHANGELOG were drafted with Claude Code (Anthropic) over a 2026-05-24 session; the operator approved each PR and ran each Ollama sweep manually.
