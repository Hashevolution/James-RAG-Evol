# LRB v0.2.4 — HR (Hallucination Resistance) NLI Axis 사전 등록 (2026-06-11)

> **Status**: LOCKED. 이 doc commit 후 NLI verifier choice / claim
> extraction / scoring spec 변경 금지.
>
> **Bench under test**: LRB v0.2 의 6th axis 추가 (R@k / P@k / Latency /
> Token cost / temporal_accuracy 외 **HR** 신규). + Track C 의 answer
> faithfulness scoring infrastructure dependency.

**Why pre-register**: HR NLI axis 가 LRB v0.2 publication tier 의
의도적 deferred scope 였음 (LRB design memo §3.2, Phase A/B prereg
§1.5). 측정-evidenced LRB ⭐⭐⭐ 가 R@k / R@1 / temporal_accuracy
만으로 진행되었기에 — answer-side hallucination 자체 측정 안 됨.
**Track C Phase C3 의 scoring infrastructure dependency** 인 동시
LRB v0.2 publication tier 의 마지막 piece. 양 track 의 공통 dependency.

**Predecessors**:
- LRB design memo (PR #782) §3.2 "HR axis = LRB v0.2 candidate"
- Track C plan (PR #792) §1 "Answer faithfulness"
- Track C C0 (이번 세션) §3.2 "NLI-grounded axis"
- v0.2.4 task #14 (이번 세션 추가)

---

## 1. Scope — v0.2.4 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK)

| 항목 | 값 |
|---|---|
| Axis name | **HR (Hallucination Resistance)** |
| Scope | answer 의 atomic claim 들이 retrieved context 에 의해 entail 되는 비율 |
| Bench coverage | LRB-S1 + LRB-S2 (답변 생성 추가) + TimeQA + TempReason + MuSiQue (Track C 와 공통) |
| NLI verifier | **RoBERTa-large-MNLI** (HuggingFace `roberta-large-mnli`) — primary |
| Secondary verifier | **DeBERTa-v3-large-mnli-fever-anli** (HF `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`) — robustness check |
| Mode | deterministic (argmax classification; 모델 weights pinned; temperature N/A for classification) |
| n_runs | 1 per (SUT, model, bench) — deterministic single run |
| Honest tier | **⭐⭐ infra validated + axis emit per cell** → **⭐⭐⭐ cross-bench cross-SUT reproduction** |

### 1.2 NLI verifier 선택 사유 — RoBERTa-large-MNLI (primary)

| Verifier | Size | Determinism | Speed | LRB H1 정합 | 선택 |
|---|---|---|---|---|---|
| **RoBERTa-large-MNLI** | ~355M | ✓ argmax classification | CPU 가능 (1-2s/claim) | ✓ (scoring step 만 LLM) | **★ Primary** |
| DeBERTa-v3-large MNLI+FEVER+ANLI | ~435M | ✓ | CPU 가능 (2-3s/claim) | ✓ | Secondary (robustness check) |
| T5-XXL TRUE NLI Mixture | ~11B | ✓ | GPU 필수 | ✓ | ALCE official 정합 candidate (deferred) |
| GPT-4 / Claude as judge | n/a | ✗ LLM judge | n/a | ✗ RAB H1 위반 | reject |

**Primary = RoBERTa-large-MNLI 사유**:
- 학계 표준 baseline (MNLI 정합, transformers default checkpoint)
- CPU 가능 (operator hardware constraint 최소)
- Deterministic argmax (RAB H1 정합)
- Reproducible by external evaluator (HF checkpoint hash pinned)
- Speed: 10K claim × 1.5s = 4시간 CPU; GPU 시 ~10분

**Secondary = DeBERTa MNLI+FEVER+ANLI 사유**:
- Cross-NLI robustness (RoBERTa-MNLI 결과가 single-verifier artifact 아닌지 검증)
- FEVER + ANLI adversarial 추가로 더 strict
- 같은 hardware 에서 가능

**T5-XXL deferred**: ALCE 의 official scoring 이지만 GPU + 11B 모델
loading 비용 — operator 측정 cost vs benefit. Phase C5 가 RoBERTa+DeBERTa
agree 시 T5-XXL 측정 안 함; disagree 시 T5-XXL deferred separate
cycle.

### 1.3 측정하지 **않음** (v0.2.4 — LOCK)

| 항목 | 사유 |
|---|---|
| LLM judge (GPT-4 / Claude) | RAB H1 강제 위반 |
| Per-step CoT entailment | Bench fixture 가 CoT label 미제공 |
| Causal / counterfactual entailment | NLI 가 적합 axis 아님 |
| Cross-lingual NLI | 영어 fixture only (한국어 NLI = LRB v0.3 candidate) |
| Soft entailment scores | argmax classification 만 (deterministic 우선) |

### 1.4 honest-tier ladder (LOCK)

```
LADDER:
  ⭐⭐⭐ = HR axis emit per cell + JAMES > Vanilla on HR on temporal
        bench (TimeQA) AND cross-NLI agreement (RoBERTa + DeBERTa)
  ⭐⭐   = HR axis emit per cell + JAMES > Vanilla on >= 1 bench
  ⭐    = HR axis emit per cell + JAMES ≈ Vanilla on all bench
  ⭐    = HR axis fail to emit (NLI verifier bug / claim extraction fail)
        → fix-PR separate cycle
```

**Magnitude framing 금지**: smoke 결과로 publication-tier claim 금지.
cross-NLI verifier agreement 가 ⭐⭐⭐ 의 핵심 condition.

## 2. Claim extraction (LOCK)

### 2.1 Atomic claim 정의

**Atomic claim** = 답변 안의 1 개 simple proposition (subject-predicate
-object 또는 등가).

예시 (답변 → atomic claims):
```
답변: "Marcus Chen is the director of the Department of Public Works,
       having replaced Lena Ortiz on week 2."
↓ atomic claims:
1. "Marcus Chen is the director of the Department of Public Works."
2. "Marcus Chen replaced Lena Ortiz."
3. "Lena Ortiz was previously the director of the Department of Public Works."
4. "The replacement occurred on week 2."
```

### 2.2 Claim extraction method (LOCK)

**선택**: **rule-based + LLM augmentation hybrid**

1. **Rule-based extraction** (deterministic primary):
   - Sentence-split (NLTK / spaCy)
   - 각 sentence = atomic claim if simple (no compound conjunction)
   - Compound sentences → split on "and" / "but" / "having" / "while"

2. **LLM augmentation** (deterministic secondary, temperature=0):
   - Rule-based 가 split 못 한 sentence → LLM 으로 atomic claim 분해
   - LLM prompt: "Decompose into atomic claims, JSON output, no prose"
   - Same LLM family as bench measurement (cross-LLM contamination 방지)

3. **Cap**: per-answer max 10 atomic claims (over-extraction 방지)

### 2.3 Extraction failure modes

| Failure | Handling |
|---|---|
| Empty answer | HR = 1.0 (no claim → no hallucination) — 사용자 catch: abstention 정합 |
| Claim too long (>200 chars) | Skip with `notes` flag |
| LLM augmentation fail | Fallback to rule-based only |
| > 10 claims after extraction | Truncate to top 10 by token count desc |

## 3. NLI scoring (LOCK)

### 3.1 Pipeline

```
For each (query, retrieved_context, answer):
  claims = extract_atomic_claims(answer)
  for claim in claims:
    nli_result = nli_verifier(premise=retrieved_context, hypothesis=claim)
    # → entailment / neutral / contradiction (argmax)
  hr_score = (# entailment claims) / (total claims)
HR = mean over all queries
```

### 3.2 Per-claim scoring

| NLI result | Score 기여 |
|---|---|
| entailment | +1 (claim 정확) |
| neutral | 0 (NOT counted as positive — strict) |
| contradiction | 0 (claim 잘못) |

**Strict**: neutral 도 entailment 가 아니므로 HR 분모에 포함.

### 3.3 Context too long

NLI 입력 max length (RoBERTa = 512 tokens; DeBERTa-v3 = 512). retrieved
context 가 더 길면:
- Truncate to first 512 tokens (deterministic; reproducible)
- Per-cell flag `context_truncated_count` 기록

## 4. 보고 프로토콜 (LOCK)

### 4.1 산출물

per (SUT, model, bench, NLI verifier):
- `reports/external/lrb/v024-hr-<bench>-<sut>-<model>-<nli>-<ts>.result.json`
- `reports/external/lrb/v024-hr-<bench>-<sut>-<model>-<nli>-<ts>.bench.jsonl`
  (per-query: query / answer / claims / per-claim NLI / HR)

### 4.2 보고 시 의무

1. ⭐⭐⭐ / ⭐⭐ / ⭐ tier 명시 per prereg §1.4
2. RoBERTa-MNLI + DeBERTa-v3 양 verifier 동시 보고 (cross-verifier
   agreement)
3. Cross-bench + cross-SUT gap structure
4. NLI verifier license + checkpoint hash 명시 (replication 가능)
5. NOT publication framing
6. Track C 정합 — answer faithfulness 의 dependency 성공/실패 report

### 4.3 금지 사항

1. RoBERTa-MNLI / DeBERTa disagreement 시 결과 cherry-pick
2. Claim extraction tuning after measurement (post-hoc fit)
3. NLI verifier checkpoint pin 없이 측정
4. Single-bench 결과로 publication-tier HR claim
5. LLM judge 도입 (RAB H1 위반)

## 5. 인프라

| 위치 | 역할 |
|---|---|
| `eval/external/lrb/nli_verifier.py` | RoBERTa-MNLI + DeBERTa-v3 dispatch (HuggingFace transformers) |
| `eval/external/lrb/claim_extractor.py` | Rule-based + LLM augmentation hybrid |
| `eval/external/lrb/hr_scorer.py` | HR score 계산 + cross-verifier agreement |
| `scripts/research/lrb_run_v024_hr.py` | CLI runner (per bench × SUT × model × NLI) |
| `tests/test_lrb_v024_hr.py` | infra tests |

신규 코드 surface ≈ 800 줄.

## 6. Dependency

본 v0.2.4 의 prerequisite (없으면 측정 불가):

| Dependency | 상태 | LOCK 시점 |
|---|---|---|
| HuggingFace `transformers` package | ✓ 이미 project 에 가용 | already |
| RoBERTa-large-MNLI checkpoint | operator action (download) | C2 진입 시 |
| DeBERTa-v3-large checkpoint | operator action (download) | C2 진입 시 |
| LRB answer generation pipeline | ✗ 미구현 (Track C C2) | C2 완료 시 |

본 v0.2.4 는 **Track C C2 (answer generation pipeline) 완료 후 진입**.
C0-C3 까지의 의존성 chain:
```
Track C C0 (bench select) → Track C C1 (prereg) → Track C C2 (answer gen)
  → [v0.2.4 본 prereg 측정 가능] + Track C C3 (scoring 통합)
  → Track C C4 (smoke) → Track C C5 (full sweep)
```

## 7. 외부 객관화 기여

v0.2.4 의 ⭐⭐⭐ 진입 = 외부 인정 7-요건 중:
- ✓ 외부 표준 fixture (LRB + Track C bench)
- ✓ 외부 표준 scoring (NLI = MNLI 학계 표준)
- ✓ 사전 등록 (이 doc)
- ✓ deterministic (NLI argmax, checkpoint pin)
- ✓ multi-NLI verifier (cross-verifier agreement)
- ✓ multi-SUT + multi-model (LRB v0.2.1 producer reuse)
- ✓ 공개 artifacts (result.json + bench.jsonl)

LRB v0.2 publication tier 의 마지막 piece + Track C scoring 의
deterministic foundation.

## 8. 실행 순서

```
0. 이 사전 등록 commit                              ← P0 (이 단계)
1. nli_verifier.py 모듈 + checkpoint download
2. claim_extractor.py 모듈
3. hr_scorer.py 모듈
4. CLI runner + tests (cross-NLI verifier sanity)
5. LRB-S1 / S2 위에서 답변 생성 producer 통합 (Track C C2 와 공통)
6. Smoke 측정 (LRB-S1 × 3 SUT × gemma3:12b × RoBERTa-MNLI)
7. Full sweep (LRB+Track C 통합)
8. Handover + memory + PR
```

예상 비용:
- nli_verifier + claim_extractor + hr_scorer: 4-6h
- CLI runner + tests: 2h
- Smoke 측정: 1-2h
- Full sweep: operator-attended (NLI CPU = 4시간 / GPU = 10분 per cell)
- Handover: 2h
- 총 ~12-15h + Full sweep operator time

## 9. 관련

- LRB design memo: `docs/design/v0.4-lrb-lifecycle-retrieval-benchmark-design.md`
- Track C plan: `docs/strategy/track-c-reasoning-measurement-plan-2026-06-11.md`
- Track C C0 lock: `docs/research/track-c-c0-bench-selection-2026-06-11.md`
- LRB Phase A/B prereg + handover (retrieval axes)
- ALCE smoke handover (StringContainment fallback, T5-XXL deferred):
  `reports/external/alce/asqa-smoke-20260611T051847Z.result.json`
- RAB SPEC v0.1.1 (H1 strict rule)
- self-eval trap rule: memory `feedback_self_evaluation_trap`
- single-axis ablation 금지: memory `feedback_single_axis_ablation_misframing`

## 10. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록 timestamped evidence.
NLI verifier module + claim extractor + 측정 실행 **전** PR 머지.

---

*v0.2.4 = LRB v0.2 publication tier 의 6번째 axis + Track C 의 scoring
infrastructure. 양 track 의 공통 dependency.*
