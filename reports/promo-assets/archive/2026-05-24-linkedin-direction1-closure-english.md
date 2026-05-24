# LinkedIn English — Direction 1 closure (draft)

> 2026-05-24 draft. Sibling to Direction 4 English LinkedIn post
> (activity-7463978849412857856). Operator publishes when ready;
> Korean follow-up + X thread queued after.

---

🔬 **Direction 1 closure on JAMES — when the hypothesis fails but the data turns out more valuable.**

Two weeks ago I shipped `core/reasoning/budget.py` to test whether per-call dynamic token budgets could cut JAMES's reasoning cost by 60-80% on `gemma4:e4b`. The mechanism: classify each prompt as substitution / light / heavy, request a matched `num_predict` cap (200 / 800 / 4096) instead of the fixed 4096 floor.

I built it as an experiment, not a runtime change — A/B sweep, raw JSON, pre-registered decision tree, env-flag gated default-OFF.

The data came back. The hypothesis flipped.

🎯 **Finding 1 — the cap was a ceiling, not the floor.**

`gemma4:e4b` naturally stops well below 4096 on every workload tier. Cutting cap from 4096 to 200 / 800 produced **+0% / +8% / -2% eval_count change**, `done_reason=stop` on every cell, zero quality regression. PR #399's lifted cap was *permission to finish*, not waste.

The token-reduction win the heuristic was designed to deliver doesn't exist on this model. What does exist:

• -17.5% / -7.3% latency on substitution / light tiers (Ollama KV-cache buffer sizing)
• ~20x smaller per-call memory allocation on substitution
• Bounded emergency-exit (cap=200 is a hard safety floor)

The implementation ships in tree, gated behind `JAMES_ADAPTIVE_BUDGET=1` env flag (default OFF). Operators can opt in for the latency / memory / safety benefits.

🎯 **Finding 2 — a 7-tier monotonic natural-stop gradient.**

The first sweep covered substitution / light / heavy free-form prompts. A follow-up extension measured the 4 cognitive middleware stages (query_rewriter / planner / reflect / verify) on the same fixture. Combined, the data spans 7 monotonic natural-stop tiers:

```
substitution verbatim    62 tokens
light synth e-commerce  235
query_rewriter          ~370
planner                 ~690
reflect                 ~910
verify                  ~970
heavy synth 4-step     1681
```

**27x dynamic range, cross-sweep noise <5% on every tier.** This is the quantitative form of the joint-paper sub-clause Robin Converse and I have been circling: *"the workload gradient is multi-tier monotonic on a single model."* Natural-stop length *is* the workload measurement.

🎯 **Finding 3 — `verify` is a high-clustering cognitive stage. Mechanism 2 needs a second axis.**

At T=0.2, verify produces only **2-3 unique responses across 20 baseline calls (~12.5%)** — and this is stable across two independent sweeps. Other cognitive stages at the same workload tier produce 20/20 unique. The difference: verify emits structured JSON (`{"grounded": ..., "unsupported": [...]}`), and the answer space is a small finite set.

So Direction 4's Mechanism 2 (answer convergence) has **two axes**, not one:
• workload weight (substitution 1/20 → heavy 20/20)
• **task type** (structured-JSON outputs cluster tightly independent of workload)

The "ceiling vs path" framing Ali Afana proposed for the 26b cross-stack data extends here: structured-output prompts route through a shorter path even at heavy workload, because the destination set is smaller.

🎯 **And one process finding — falsification → revision → confirmation.**

The cognitive-stages sweep first ran with CAP_LIGHT=800. It exposed a calibration error: 800 was below reflect (926) and verify (984) natural-stop lengths, so 19/20 calls truncated and quality dropped 40-75%. The data drove a heuristic bump (CAP_LIGHT 800 → 1200), and the re-sweep passed cleanly: 0/20 truncation, quality 20/20 restored.

Same empirical discipline I've watched Robin run on the 26b mode-split sweeps. Builds joint-paper trust in the protocol.

🤝 **Three-author joint-piece status:**

Headline (3-author locked, unchanged): *"Substitution is free. Synthesis costs in proportion to what it has to invent."*

Sub-clauses now drafted:
• *"…and inversely to parameter count."* (Robin axis-3, 2 evidence layers)
• *"…and the gradient is multi-tier monotonic — 7 measured tiers spanning 27x dynamic range."* (JAMES Direction 1)
• *"…and answer convergence has a task-type axis: structured-JSON outputs cluster independent of workload."* (JAMES Direction 1, cross-sweep validated)

The joint piece outline trigger Robin endorsed on 2026-05-24 is now load-bearing on three independent stacks: hers (26b MoE), mine (e4b cognitive stack), and Ali's mid-June Gemini backend.

🔗 PR #461 (D1.A module + D1.B wiring + 3-prompt experiment + 4-stage extension): https://github.com/Hashevolution/James-RAG-Evol/pull/461
🔗 PR #463 (heuristic v2 + closure result docs + 7-tier gradient): https://github.com/Hashevolution/James-RAG-Evol/pull/463
🔗 Cognitive-stages result doc: https://github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/v3prime-direction1-cognitive-stages-result.md

@Robin Converse @Ali Afana — three axes locked, three independent stacks, one architectural property. The cognitive-stages 7-tier gradient + verify task-type clustering land as joint-paper §axis-2 input.

#SovereignAI #LLM #Gemma4 #LocalLLM #AgenticArchitecture #GraphRAG #Ollama #LLMResearch

---

## Operator publish checklist

- [ ] Verify the activity URL format (`activity-<id>`) — record on publish for `launch-tracker.md`
- [ ] Tag @Robin Converse + @Ali Afana when typing the names (LinkedIn @ autocomplete)
- [ ] Same 3 link slots as Direction 4 post — let LinkedIn collapse to `lnkd.in/*`
- [ ] Hashtags identical to Direction 4 post (8 total)
- [ ] After publish: append URL to `reports/promo-assets/launch-tracker.md` as a new row + add the URL to PR #461 + PR #463 description (4-way cross-link)
- [ ] Korean follow-up post + X thread queued after (6-12h later for KO LinkedIn, KO LinkedIn publish + KST 19-22 for X)

## Tone notes

- Stays in Direction 4 voice — same sentence lengths, same emoji discipline (🔬 lead, 🎯 finding bullets, 🤝 collaborator section, 🔗 link list)
- "When the hypothesis fails but the data turns out more valuable" is the durable headline — sets the empirical-discipline frame Robin and Ali both rewarded on the 2026-05-22~24 thread
- No "ask" — the joint-piece status paragraph just states the lock + new sub-clauses. No request for endorsement. Tag-and-publish is the inform path.
- Numbers carry the weight — three explicit findings, 7-tier table, 12.5% verify metric, 27x dynamic range. Avoid "hype" adjectives.

## What this post deliberately does NOT do

- Claim D1 was a success on its original hypothesis — it wasn't, and that's stated
- Ask Robin or Ali to weigh in publicly — Robin's mid-June Gemini backend timing + Ali's structured-output extension would be natural responses, but unprompted
- Promote env-flag flip (`JAMES_ADAPTIVE_BUDGET` default ON) — the data doesn't justify it; stays OFF
- Pre-publish a Korean version or X thread — those are separate posts after this one lands
