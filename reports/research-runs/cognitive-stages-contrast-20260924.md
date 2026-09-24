# Cognitive stages on / off — paired arms, and the two answers they broke (2026-09-24)

> **Design**: two arms, **same session, back-to-back**, on `main`
> `65d25e4`, via `scripts/qvt_capture_baseline.py --n-runs 1 --output <arm>`
> so every integrity guard applies (model pinned to `gemma4:e4b`, routing
> disabled, generation-failure abort, provenance, host state).
>
> | arm | `JAMES_DISABLE_COGNITIVE_STAGES` | window (KST) | artifact |
> |---|---|---|---|
> | A | unset (`env -u`) — production path | 15:00:34 → 15:25:34 | `qvt-arm-A-default-cogcontrast-20260924.json` |
> | C | `1` — plan / verify / reflect skipped | 15:25:34 → 15:34:42 | `qvt-arm-C-nocognitive-20260924.json` |
>
> `JAMES_QUERY_REWRITE_TIMEOUT_S` unset in both (10 s default).
> Written outside `eval/qvt/` on purpose (#1139: the newest file there
> becomes the canonical baseline).
>
> **n = 1 per arm. This is screening, not a verdict** (§5).

## 1. The flag actually applied

The flag is not in the capture banner, so it was checked in `audit_log`
with `scripts/research/latency_decomposition.py` over each window:

| stage events | arm A | arm C |
|---|---:|---:|
| `reason:plan` | 8 | **0** |
| `reason:verify` | 54 | **0** |
| `reason:reflect` | 33 | **0** |
| `reason:retry` | 7 | **0** |
| `gemma.timeout` | 7 | **0** |
| `reason:synth` | 18 | 18 |

Both arms: 18/18 answers healthy (no infrastructure failures), effective
model `gemma4:e4b` at `gpu_fraction` 1.0.

## 2. Five axes

| axis | arm A (on) | arm C (off) | Δ C−A | `baseline_6deca66` band |
|---|---:|---:|---:|---:|
| path_coverage | 0.9091 (10/11) | 0.8182 (9/11) | −0.0909 | 0.0455 |
| graded_answer | 0.6667 | 0.7333 | +0.0667 | 0.0667 |
| abstention_f1 | 0.5000 (FP 1) | 0.5714 (FP 0) | +0.0714 | 0.0714 |
| token_cost (chars) | 1628.5 | 1550.6 | −77.9 | 343.45 |
| latency_cost (s/query) | **74.06** | **26.37** | **−47.7 (−64%)** | 3.40 |

Bench wall clock: 1482 s → 528 s.

**Host state was equal** — mean SM clock 2716 vs 2740 MHz, mean power
186 vs 188 W, GPU utilisation 89 vs 83 %. So, unlike the 2026-09-22
baseline (§8.6 of the handover), the latency gap is not the host.

⚠️ `reason:synth` is **not** a clean internal control here (18.2 →
12.6 s mean). With the host equal, the shift belongs to the arm; the
mechanism was not isolated. It does not change the headline — synth is
5.6 s of a 47.7 s gap.

## 3. Where the quality differences come from — per query

Every changed query was traced in `audit_log`.

| Q | axis | A → C | cause | attributable to cognitive stages? |
|---|---|---|---|---|
| **14** | abstention | FP → TN | **reflect overwrote a correct grounded answer** (§4.1) | **yes — traced** |
| **17** | graded | 0.0 → 1.0 | **verify blocked a correct answer** as injection echo (§4.2) | **yes — traced** |
| 9 | path | 1.0 → 0.0 | graph paths come from LLM entity extraction (`pipeline_loops.py:282`), upstream of all three stages; retrieval was identical in both arms | no — run variance |
| 1, 13 | graded | +0.33 each | wording of the synth answer | no — generation variance |
| 4 | graded | −0.33 | wording of the synth answer | no — generation variance |

Graph-path counts move in both directions between the arms (Q13 0 → 46,
Q15 71 → 6), which is what variance looks like, not a direction.

## 4. The two defects

### 4.1 Reflect judges facts without the evidence — Q14 "GPT-6 모델은 언제 공식 발표됐어?"

`audit_log`, arm A:

1. `reason:synth` — *"ANSWER: 2026년 4월 15일 — 내부 자료에 따르면 … OpenAI가
   GPT-6 모델을 공식 발표했으며 …"* — **correct and grounded**.
2. `reason:reflect` (critique) — *"이 답변 초안은 **치명적인 사실 오류
   (Hallucination)**를 포함하고 있습니다"*.
3. `reason:reflect` (revise) — *"현재까지 OpenAI 측에서 GPT-6 … 공개된 바가
   없습니다"* — the fact is gone.
4. `reason:verify` — `grounded: false`, 2 unsupported claims →
   `rec=annotate`. **Verify caught the damage correctly** but only
   annotated it, so the wrong answer shipped with a note appended.

**Mechanism (code)**: `CRITIQUE_PROMPT_*` and `REVISE_PROMPT_*`
(`core/reasoning/reflect/prompts.py`) are formatted with `{query}` and
`{draft}` only (`reflect/loop.py:213`, `:243`). The critique is told to
flag *"명백히 틀린 사실"* but is never shown the retrieved context, so it
can only judge against the model's training data. Any fact newer than
the model — the normal case for an internal knowledge base — reads as a
hallucination, and revise deletes it.

This is the evidence-vs-learned-knowledge leak that
`feedback_evidence_grounded_validity_check` names, inside the product.

### 4.2 Verify's echo check reuses an input-injection pattern — Q17 "Anthropic의 CEO는 누구야?"

1. `reason:synth` — *"ANSWER: Dario Amodei — The title of the article
   provided in the context is "The Making Of Anthropic CEO Dario Amodei""*.
2. `reason:reflect` — `NO_ISSUES`.
3. `reason:verify` — `security.injection_echo:(context|system|previous)\s*(i…`
   → `rec=block`. LLM grounding check on the same answer: `grounded: true`.
4. User receives *"(Security verification: … blocked. Please rephrase
   the question.)"*

**Mechanism (code)**: the pattern is
`core/security_layer/_policies.py:106`,
`(context|system|previous)\s*(is|was|=|:)\s*["']` — an **input**
injection signature. Verify applies it to the **output**, where
*"the context is "<quoted title>""* is an ordinary way to cite a source.
Arm C's synth happened to phrase it *"The context includes a title, …"*;
with verify off it would have shipped either way.

## 5. What this licenses — and what it does not

**Licensed**

- Two product defects with traced mechanisms (§4.1, §4.2). Each is a
  code-structure fact plus one observed instance; neither depends on n.
- Latency: on this suite, host equal, the three stages cost **~48 s of
  a 74 s query** and all 7 timeouts.

**Not licensed**

- ❌ "Turn the cognitive stages off." n = 1, 18 answerable queries, one
  suite. Removing a layer on a single-axis ablation is exactly what
  `feedback_single_axis_ablation_misframing` forbids; the stages may
  earn their cost on suites this one does not exercise (multi-hop,
  contradiction-heavy corpora). Their own design-intent axes were not
  measured here.
- ❌ "Quality improved with the stages off." Every axis Δ sits at or
  inside the baseline band except path_coverage, whose one flip is
  upstream variance (§3). Net of the two traced defects, the arms are
  indistinguishable on quality at this n.

**Oracle note**: graded_answer scored arm A's wrong Q14 denial **1.0** —
the signals `GPT-6 / 발표 / OpenAI` all appear in a sentence saying there
was no announcement. abstention_f1 is what caught it. Known weakness of
substring signals (`feedback_graded_substring_vs_terse_exact_match`).

## 6. Next

1. **Fix §4.1** — give critique / revise the evidence the draft was
   written from, or restrict critique to internal consistency when no
   evidence is passed. Touches `core/reasoning` → rule #2 bench + Quality
   Delta Card, scored on reflect's design-intent axes.
2. **Fix §4.2** — separate output echo signatures from input injection
   signatures. Trust-boundary code: its own PR, no auto-merge.
3. **n = 3 same-session contrast** after 1–2 land, before any default
   change to the stages or their budgets (roadmap step 2).
