# V3'.e cross-family / cross-generation — Step 1 partial (4 models)

**Date**: 2026-05-29
**Status**: 🔒 **Internal partial only** — DO NOT share externally yet
**Trigger**: handover §11.10 M11 (arxiv:2605.09104 prior art → Direction 3 timing pressure)
**Driver**: `scripts/research/v3prime_e_mode_split.py` (existing `--model` flag, no driver extension required)
**Step 2 status**: pending operator-side Ollama pulls (`llama3.1:8b` / `qwen2.5:7b` / `deepseek-v2:16b`)

## 1. Why "internal partial only"

Phase 1 Robin DM (Option B, 2026-05-29) committed to the framework verbatim *"Whatever shape comes back, you see first."* That commitment is what gets the first comprehensive cross-family + cross-generation dataset, not the first 4-model batch in hand. Sharing partial results would (a) fragment Robin's read into multiple DMs in a 24-hour window — already 2 DMs sent today — and (b) tilt against the [[feedback_collaborator_consent_default]] + [[feedback_high_stakes_endorsement_posture]] discipline that's held since 2026-05-19.

Rule captured (see also: handover §11.10 follow-up): **Cumulative measurement still in progress → no partial first-share. Single consolidated DM after the full measurement set lands.**

## 2. Capture conditions (same for all 4 cells)

- Driver: `scripts/research/v3prime_e_mode_split.py`
- Protocol: 4 cells per model = (substitution / synthesis) × (cap 400 / cap 4096) × n=10
- Temperature: 0.2 (V3' standard)
- Server: local Ollama (`http://127.0.0.1:11434/api/generate`)
- Context fixture: e-commerce policy (English, matches Robin's domain — see driver §CONTEXT_FIXTURE)
- Substitution prompt: verbatim retrieval of "Refund Policy" section
- Synthesis prompt: 2-3 sentence policy-justified recommendation for linen-shirt return case

## 3. Step 1 result files

| Model | File | sub @400 | sub @4096 | syn @400 | syn @4096 | avg lat (syn @400) |
|---|---|---|---|---|---|---|
| `gemma4:e4b` | `v3prime-e-mode-split-20260529T124145.json` | 10/10 | 10/10 | **8/10** ⚠️ | 10/10 | 4.1s |
| `gemma3:12b` | `v3prime-e-mode-split-20260529T124336.json` | 10/10 | 10/10 | 10/10 | 10/10 | 1.6s |
| `gemma2:2b` | `v3prime-e-mode-split-20260529T124439.json` | 10/10 | 10/10 | 10/10 | 10/10 | 0.4s |
| `qwen2.5-coder:7b` | `v3prime-e-mode-split-20260529T124459.json` | 10/10 | 10/10 | 10/10 | 10/10 | 1.1s |

All four cells × four models = 160 trials, all completed cleanly (no Ollama errors, no timeouts).

## 4. Patterns

### 4.1 Substitution mode → universal byte-identical retrieval

All 4 models, both caps: **10/10 success, 1/10 unique** (every call returned the byte-identical canonical text). Robin Converse's 2026-05-23 issue #448 Finding 1 ("40/40 → 1 unique on 26b substitution") replicates at the JAMES end across:

- Gemma 4 (4B, default e4b)
- Gemma 3 (12B)
- Gemma 2 (2B)
- Qwen 2.5 (7B, coder variant)

Substitution mode = canonical retrieval, no internal reasoning. **Cross-family universal at the JAMES end.**

### 4.2 Synthesis mode floor → narrows to gemma4:e4b at the n=10 sample

- `gemma4:e4b`: synthesis @ cap=400 yields **8/10 success** (2 empty / floor-bounded). @ cap=4096 yields 10/10.
- `gemma3:12b` / `gemma2:2b` / `qwen2.5-coder:7b`: synthesis @ cap=400 yields **10/10 success**. No visible floor in this fixture at this n.

**Pre-Step 1 hypothesis** (V3'.a~d 4-stage uniformity on e4b extrapolated): "~500-token reasoning floor is a Gemma 4 family architectural property."

**Post-Step 1 partial revision**: the floor's *visible magnitude in this fixture* is model-specific, not family-wide. gemma3:12b shows no floor at cap=400 (same family generation gap); gemma2:2b (smaller still) shows no floor either; qwen2.5-coder:7b (cross-family) shows no floor.

This is a one-fixture, n=10 observation. It does **not** yet license the stronger claim "the e4b floor is not a Gemma-family property at all" — that requires (a) more fixtures across synthesis complexity, (b) larger n per cell for tail estimation, and (c) Llama 3.1 / Qwen 2.5 general / DeepSeek-v2 measurements (Step 2) to rule out architecture-class confounds.

### 4.3 Synthesis unique-response diversity

| Model | syn @400 unique | syn @4096 unique |
|---|---|---|
| `gemma4:e4b` | 8/10 | 10/10 |
| `gemma3:12b` | 2/10 | 6/10 |
| `gemma2:2b` | 7/10 | 7/10 |
| `qwen2.5-coder:7b` | 7/10 | 7/10 |

`gemma3:12b` produces noticeably less diverse synthesis outputs than the other three at both caps — possibly a deterministic-decoding bias of that specific checkpoint at temperature 0.2. Worth a brief note but not a load-bearing finding.

### 4.4 Latency

`gemma4:e4b` synthesis latency (~4-5s) is 3-10× the other three. `gemma3:12b` (12B params) is faster (1.5-1.6s) than `gemma4:e4b` (4B params) on synthesis — consistent with Robin's "scale isn't lifting the ceiling; it's shortening the path to the same answer" framing (Ali → Robin, 2026-05-24).

## 5. Narrative impact (pre-Step 2)

The cross-family / cross-generation evidence at Step 1 strengthens Robin's substitution/synthesis split (cross-family universal) **and weakens** the original V3'.a~d framing of "Gemma 4 family-wide reasoning floor" toward something more specific:

- **Substitution-vs-synthesis split** = cross-family universal (locked vocabulary)
- **Synthesis-mode entry cost** = real (Robin + Ali + V3'.a~d agree)
- **Cap-floor magnitude per model** = model-specific, not family-wide (revised)

In Yang et al. 2026 (arxiv:2605.09104) framework terms: the CES production function's M_int (internal reasoning) is approximately zero in substitution mode (universal) but has a model-specific budget threshold in synthesis mode. The threshold sits above cap=400 for gemma4:e4b in this fixture and below cap=400 for the other three measured here.

## 6. Step 2 plan

Pending operator-side Ollama pulls:

```powershell
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
ollama pull deepseek-v2:16b
```

Then re-run the driver against each:

```powershell
$env:PYTHONIOENCODING = "utf-8"
python scripts/research/v3prime_e_mode_split.py --model llama3.1:8b
python scripts/research/v3prime_e_mode_split.py --model qwen2.5:7b
python scripts/research/v3prime_e_mode_split.py --model deepseek-v2:16b
```

Consolidation:
- All 7 result JSONs into a single comprehensive analysis doc
- Re-validation pass (e.g., n=20 per cell for the boundary models, or 2-3 reruns of `gemma4:e4b` synthesis @ cap=400 to estimate the 8/10 tail)
- Cross-family / cross-generation / cross-architecture table
- Yang et al. framework citation + the M_int-per-model finding

## 7. Re-validation candidates

Before single Robin DM, consider:

1. **Reproducibility check**: rerun `gemma4:e4b` synthesis @ cap=400 with n=20 or 3-rerun of n=10 to estimate the 8/10 statistic's confidence interval. The 8/10 from a single run could be the floor or could be sampling noise.
2. **Additional fixtures**: 1-2 more synthesis fixtures of different complexity to test fixture-dependence vs model-dependence of the floor.
3. **Temperature sweep**: optional 1-cell check at temp 0.7 to confirm temperature-independence on the substitution side (Robin's original "no effect" observation).

These are scope-bounded; pick at most 1-2 before the Robin DM to keep total cycle time reasonable.

## 8. Out of scope (this doc)

- Robin first-share DM (gated on Step 2 + re-validation completion)
- Ali side mention (gated on Ali 6/7 resume per handover §11.9)
- Joint piece Related Work draft (gated on full cross-family dataset + analysis)
- Production code changes (V3' is pure research; cap defaults already adjusted in PR #399)

## 9. Related

- handover `docs/handovers/v0.4.x-session-2026-05-29-collaboration-checkpoint.md` §5 M3 / M11 / §11.10
- memory `feedback_arxiv_2605_09104_prior_art_finding.md`
- memory `direction_3_cross_family_review.md` (timing decision history)
- driver `scripts/research/v3prime_e_mode_split.py` (used as-is, no extension)
- prior V3'.a~d archives: `reports/research-runs/v3prime-{query_rewriter,planner,reflect,verify}-*.json`
- Robin Phase R4 / R5 / R6 DM record: handover §3
- Ali Phase 1-11 DM record + Phase 12 (resume notice): memory `feedback_ali_resume_notice_june6.md`
