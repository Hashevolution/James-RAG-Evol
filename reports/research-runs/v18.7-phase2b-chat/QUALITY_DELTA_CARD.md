# Quality Delta Card — v18.7 Phase 2b chat-mode 3-cell

**Measurement date**: 2026-06-16
**Hardware**: NVIDIA RTX 4070 SUPER 12 GB VRAM, AMD Ryzen 7 7700, 31 GB RAM
**Fixture**: `eval/chat_mode_queries.json` (v18.7 Phase 2 prereq, operator-authored, Korean primary)
**Sample**: 12 queries × 3 paired runs = 36 trials per cell
**Design**: chat-mode free-form (no evidence injection, prior_turns for multi_turn)
**Judge**: Claude CLI, evidence-free pairwise blinded A/B
**Pre-flight**: 7/7 PASS per cell

## What this measurement decides

Phase 2 Step 2c — engine.py chat-mode dispatch direction. Three candidates measured against the Cloud baseline (Claude CLI):
- **A**: gemma4:e4b OFF cap=400 (current production default per v18.6)
- **B**: gemma3:4b cap=400 (Phase 2 candidate per `DEFAULT_PREFERENCE['chat']` top)
- **C**: gemma3:12b auto cap=400 (medium-tier reference)

## 5-axis matrix

| Axis | A (gemma4:e4b OFF) | B (gemma3:4b) | C (gemma3:12b) | CLOUD (Claude) |
|---|---|---|---|---|
| **Graded — judge (Claude)** | 0.833 | 0.750 | **0.917** | 1.000 |
| **Graded — gold-grounded (factual_chat only)** | 1.000 | 1.000 | 1.000 | 1.000 |
| **Judge bias on LOCAL (factual_chat)** | 0.000 | 0.000 | 0.000 | n/a |
| **Δ judge vs Claude** | +0.167 | +0.250 | **+0.083** | 0 |
| **Abstention rate** | 6/36 (17%) | **9/36 (25%)** | 3/36 (8%) | 0/36 (0%) |
| **Token cost (cap)** | 400 | 400 | 400 | n/a |
| **Latency cost (pair avg)** | 25.5s | **24.4s** | 28.4s | included |
| **Stability (across 3 runs)** | 0.917 | 1.000 | 1.000 | 0.917 cloud |
| **VRAM** | 8.9 GB | 3.1 GB | 7.6 GB | 0 local |

## Per sub-class judge breakdown

| Sub-class | A (gemma4 OFF) | B (gemma3:4b) | C (gemma3:12b) | CLOUD |
|---|---|---|---|---|
| small_talk (3) | 3/3 ✓ | **1/3 ✗** | 2/3 | 3/3 |
| factual_chat (3) | 3/3 ✓ | 3/3 ✓ | 3/3 ✓ | 3/3 ✓ |
| open_question (3) | 2/3 | 2/3 | **3/3 ✓** | 3/3 |
| multi_turn (3) | 2/3 | **3/3 ✓** | 3/3 ✓ | 3/3 |

## Per-query catches

- **id=1001 "안녕하세요"** — Cell B (gemma3:4b) **3/3 ABSTAIN**. Cells A + C handle the greeting normally. Strong reject signal for promoting gemma3:4b to chat default.
- **id=1002 "잠깐 쉬어야겠다. 점심 뭐 먹을까?"** — Cells B + C both 3/3 ABSTAIN; A 1/3 ABSTAIN. Universal weak query — the open lunch suggestion trips local models' guardrails. Cloud handles 3/3.
- **id=1021 "주말에 가족과 시간 보낼 좋은 방법"** — Cells A + B both 3/3 ABSTAIN; **only Cell C 3/3 CORRECT**. Open-ended advice surfaces gemma3:12b's unique chat strength.
- **id=1032 multi_turn "그 중에서 어떤 게 가장 추천이야?"** — **Cell A 3/3 ABSTAIN**; Cells B + C both 3/3 CORRECT. gemma4:e4b OFF fails the anaphora resolution against `prior_turns`.

## fixture self-correction (transparency)

The first gold-grounded run showed **+0.333 bias on Cell C factual_chat** which would have looked like a judge bias artifact. Inspection revealed Cell C answered "물의 끓는점?" as **"섭씨 백도"** (한글 표기) — correct Korean, but the fixture's `gold_signals` for id=1012 lacked the "백도" alias. **fixture bug, not judge bias, not model error**. Patched `aliases` to include "백도" / "섭씨 백도" / "백 도"; rechecked → all 3 cells 1.00 gold-grounded. This is the `feedback_s31_self_correction_artifact_pattern` (broken-category artifact) chat-mode variant — caught via the v18.6 gold-grounded recheck protocol working as designed.

## Step 2c operator decision

**gemma3:4b promotion → REJECTED.**

The `DEFAULT_PREFERENCE['chat']` top (gemma3:4b) was the Phase 2 candidate based on size + speed reasoning. The measurement shows it is **the worst of three on chat-mode**:
- small_talk lowest (1/3 vs 3/3 / 2/3) — the most basic chat sub-class
- highest abstention rate (25% vs 17% / 8%)
- ties or loses on every other sub-class

**Recommended Step 2c action — `DEFAULT_PREFERENCE['chat']` reorder**

```python
# OLD (pre-measurement, size-favored ordering)
"chat": ["gemma3:4b", "gemma3:1b", "gemma2:2b", "gemma3:12b",
         "gemma3:27b", "gemma4:e4b", "qwen2.5:14b", "llama3.2:3b",
         "mistral:7b"]

# NEW (v18.7 Phase 2b measured ordering)
"chat": ["gemma3:12b", "gemma4:e4b", "gemma3:27b",
         "gemma3:4b", "gemma3:1b", "gemma2:2b", "qwen2.5:14b",
         "llama3.2:3b", "mistral:7b"]
```

Rationale:
- **gemma3:12b first** — best graded, lowest abstention, only model that handles open_question id=1021.
- **gemma4:e4b second** — competitive on small_talk + factual + open, only weak on multi_turn anaphora (id=1032). Production current default preserved as fallback.
- **gemma3:27b third** — not measured here, but consistent with chat preference shape (large-medium tier).
- **gemma3:4b demoted** — measurement says it actively abstains on basic greeting. Sub-3B family kept in list for fallback when nothing larger is installed, but no longer the top pick.

## Caveats (required reading before citing)

- **small_n**: 12 query × 3 runs per cell = 36 trials. Single fixture, operator-authored. Not publishable — operator-decision-grade signal only.
- **chat_mode_lenient_judge**: 3 of 4 sub-classes (small_talk / open_question / multi_turn) are intrinsically judge-only. The v18.6 +0.11-0.19 judge bias caveat applies to those rows; only factual_chat got gold-grounded confirmation (and saturated at 1.00 across all cells → no model differentiation from this sub-class).
- **single_fixture**: chat-mode fixture is Korean-primary, operator-authored. Generalization to Japanese / Chinese / wider English chat is not measured. v0.6.2+ cross-language extension is operator-pending.
- **judge_self_preference**: judge is Claude; one candidate is Claude. The verdict-CORRECT rate above is the published number; the abstention-side analysis (where the catch lives) is not subject to this bias.
- **think_policy alignment**: Cell C used `--force-think auto` because gemma3:12b is NOT in the thinking-capable family; Cells A + B used `--force-think off` for fair comparison against the thinking-OFF production contract. think_policy contract honored end-to-end (per `project_thinking_mode_contract_v18_4`).
- **production retrieval not exercised**: this measurement bypasses JAMES retrieval / abstention / cognitive stages. Chat-mode in production may behave differently if those layers interact with the local model — measurement axis is reasoning isolation, not pipeline e2e.

## Reproducibility

Raw artifacts at `reports/research-runs/v18.7-phase2b-chat/`:
- `cellA.json` / `cellB.json` / `cellC.json` — full per-trial rows including blinded A/B order, raw answers, judge verdicts, pre-flight audit, caveat block
- `cellA.log` / `cellB.log` / `cellC.log` — stdout logs (~7 KB each)
- `gold_grounded_recheck.py` — deterministic gold-signal substring check
- `gold_grounded_summary.json` — per-cell judge vs gold table (machine-readable)
- `_chain.log` — chain timing record (Cell A: 20:36-20:51 / Cell B: 20:51-21:06 / Cell C: 21:06-21:23, ~14-15 min per cell)

Launch command equivalents in `project_phase2a_chat_mode_fixture_v18_7.md`.

## Related memory

- `[[project_phase2a_chat_mode_fixture_v18_7]]` — fixture + harness Step 2a
- `[[project_routing_buildout_5phase_v18_7]]` — 5-phase plan, Phase 1 + Phase 2b context
- `[[project_judge_reliability_gold_grounded_v18_6]]` — gold-grounded recheck protocol applied here
- `[[project_thinking_mode_contract_v18_4]]` — think_policy honored across all 3 cells
- `[[feedback_s31_self_correction_artifact_pattern]]` — fixture self-correction precedent (chat-mode variant caught this run)
