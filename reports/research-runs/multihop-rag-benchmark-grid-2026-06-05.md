# MultiHop-RAG Benchmark Grid — 잣대 테스트 인벤토리

> 추후 다른 모델 / 다른 스케일 / 자메스 업그레이드 시 비교 활용용
> 잣대 테스트 baseline 인벤토리. 이번 cycle (2026-06-05) 의 모든
> 측정 셀 + 환경 + baseline 값 + 비교 활용 가이드.

## 공통 환경

- **Fixture**: `workspaces/hotpot_eval/eval/multihop_rag_queries.json`
  (MultiHop-RAG Tang & Yang 2024 EMNLP, 100Q = 25 inference + 25
  comparison + 25 temporal + 25 null)
- **Workspace**: `./workspaces/hotpot_eval` (격리 corpus)
- **Embedding**: BAAI/bge-m3 (multilingual)
- **Chroma DB**: `workspaces/hotpot_eval/chroma_db_bge_m3`
- **Oracle**: `eval/qvt/oracle.py::score_paper_aligned_accuracy` /
  `score_graded_answer` / `score_abstention_f1`
- **공통 env**:
  ```
  JAMES_WORKSPACE=./workspaces/hotpot_eval
  JAMES_GEMMA4_E4B_THINK_OFF=1  (root .env)
  JAMES_NUM_CTX=16384
  ```

## 잣대 테스트 리스트

### 1. paper-style baseline (Layer B framework comparison)

| 항목 | 값 |
|---|---|
| 목적 | JAMES corpus 위에 paper-equivalent baseline. JAMES advanced 스택의 framework-level contribution 분리 |
| Runner | `scripts/research/multihop_raw_run.py` |
| Env | `PROMPT_STYLE=paper RAW_TOP_K=10` |
| Model | 가변 (PROOF_MODEL) |
| Stack | JAMES advanced 모두 OFF (raw runner = simple chunk + LLM call) |
| Metric | primary / graded / abst_F1 |

**baseline 값** (2026-06-05):

| Model | primary | graded | abst_F1 | inf | comp | temp | null | n |
|---|---|---|---|---|---|---|---|---|
| gemma4:e4b (4B) | 0.530 | 0.223 | 0.559 | 0.76 | 0.32 | 0.28 | 0.76 | 100 |
| mixtral:8x7b (47B) | 0.500 | 0.357 | 0.431 | 0.80 | 0.40 | 0.24 | 0.56 | 100 |

**비교 활용**:
- 새 모델 도입 시 같은 환경 측정 → "JAMES corpus retrieval 위에서
  이 모델 baseline = X"
- "advanced 스택 contribution" 분리 = (JAMES Default 값) − (paper-style
  값) per axis

### 2. JAMES Default 모체 (PR-A 후 production state)

| 항목 | 값 |
|---|---|
| 목적 | PR-A 후 production-deployed JAMES 모체 baseline (terse single-answer 측정 시) |
| Runner | `scripts/research/multihop_terse_run.py` |
| Env | `JAMES_RESPONSE_STYLE=terse` (production NATURAL 측정 시 비활성) |
| Model | 가변 (PROOF_MODEL) |
| Stack | JAMES advanced 모두 ON (production state: planner+reflect+verify+graph+...) |
| Session | same-session (`JAMES_TERSE_SESSION_MODE=fixed-shared` 또는 default per-query) |
| Metric | primary / graded / abst_F1 / type cross-tab |

**baseline 값** (2026-06-05, terse fixture 한정):

| Model | primary | graded | abst_F1 | inf | comp | temp | null | n |
|---|---|---|---|---|---|---|---|---|
| gemma4:e4b (4B) PM-10 | 0.480 | 0.490 | 0.611 | 0.80 | 0.16 | 0.08 | 0.88 | 100 |
| mixtral:8x7b (47B) PM-12-final | 0.450 | 0.450 | 0.667 | 0.76 | 0.16 | 0.16 | 0.72 | 100 |

**비교 활용**:
- 자메스 업그레이드 후 같은 환경 측정 → 다축 ±N 정량
- 새 모델 추가 시 baseline 새 행 → mother-platform 가치 평가

### 3. JAMES legacy Default (PR-A 전 production)

| 항목 | 값 |
|---|---|
| 목적 | PR-A 전 production state — legacy 회귀 / regression check baseline |
| Runner | `scripts/research/multihop_terse_run.py` |
| Env | `JAMES_SYNTH_CONTEXT_CHARS=1000` (PR-A flip 회귀) |
| 비고 | PR-A 후 default 8000 이라 legacy 명시 필요 |

**baseline 값** (2026-06-05):

| Model | primary | graded | abst_F1 | n |
|---|---|---|---|---|
| gemma4:e4b (4B) PM-1b | 0.450 | 0.413 | 0.523 | 100 |
| mixtral:8x7b (47B) PM-3 | 0.460 | 0.423 | 0.545 | 100 |

**비교 활용**:
- PR-A 결정 정당화 evidence (cap=1000 → cap=8000 회복 정량)
- 회귀 발생 시 측정값 ↓ → 결함 의심

### 4. raw vanilla RAG (모델 자체 능력 baseline)

| 항목 | 값 |
|---|---|
| 목적 | JAMES 스택 우회 직접 retrieval + LLM call. 모델 자체 능력 baseline |
| Runner | `scripts/research/multihop_raw_run.py` |
| Env | `PROMPT_STYLE=james_terse` (default) `RAW_TOP_K=5` (default) |
| Stack | 0 (vanilla RAG, JAMES 스택 우회) |
| Note | JAMES corpus + JAMES embedding 사용 — paper-style 과 다름 (corpus 변수 통제, prompt 변수만 다름) |

**baseline 값** (2026-06-04):

| Model | primary | graded | abst_F1 | inf | comp | temp | null | n |
|---|---|---|---|---|---|---|---|---|
| gemma4:e4b (4B) PM-4 | 0.520 | 0.403 | 0.561 | 0.60 | 0.40 | 0.16 | 0.92 | 100 |
| mixtral:8x7b (47B) PM-5 | 0.55 | — | — | — | — | — | — | 100 (partial scoring) |

**비교 활용**:
- 새 모델 자체 능력 측정 (스택 contribution 분리)
- JAMES 스택 contribution = (JAMES Default) − (raw) per axis

### 5. terse opt-in 옵션 (V2 활성)

| 항목 | 값 |
|---|---|
| 목적 | V2 critique 비노출 redesign 효과 — 단답 use case 최적화 옵션 |
| Runner | `scripts/research/multihop_terse_run.py` |
| Env | `JAMES_REVISE_PROMPT_V2=1` |
| Stack | JAMES advanced ON + V2 옵션 활성 |

**baseline 값** (2026-06-05):

| Model | primary | graded | abst_F1 | meta marker | n |
|---|---|---|---|---|---|
| gemma4:e4b (4B) PM-16 | 0.580 | 0.373 ↓ | 0.621 | 3/100 | 100 |

**비교 활용**:
- 단답 use case 옵션의 효과 정량
- 단축 +0.10 vs 다축 −0.12 trade-off 패턴 측정
- cycle β AnswerStyleClassifier 후 자동 활성 시 baseline

### 6. 모든 단답 옵션 활성 (V2 + P-1)

| 항목 | 값 |
|---|---|
| 목적 | meta-deterministic 답 (양식 leak 0) — 단답 보장 옵션 |
| Runner | `scripts/research/multihop_terse_run.py` |
| Env | `JAMES_REVISE_PROMPT_V2=1` + terse 모드 (P-1 자동 conditional) |

**baseline 값** (2026-06-05):

| Model | primary | graded | abst_F1 | meta marker | n |
|---|---|---|---|---|---|
| gemma4:e4b (4B) PM-17 | 0.560 | 0.360 | 0.509 ↓ | 0/100 | 100 |

**비교 활용**:
- V2 단독 vs +P-1 marginal contribution 측정
- meta-marker 0 보장 use case (예: API consumer, deterministic output)

### 7. 컴포넌트 ablation (advanced 스택 분리)

| 항목 | 값 |
|---|---|
| 목적 | 각 컴포넌트의 marginal contribution |
| Runner | `scripts/research/multihop_terse_run.py` |
| Env | `JAMES_DISABLE_COGNITIVE_STAGES=1` / `JAMES_DISABLE_GRAPH=1` / 기타 |

**baseline 값** (2026-06-05, e4b 4B):

| Cell | env | primary | graded | abst_F1 | n |
|---|---|---|---|---|---|
| cognitive-off PM-6 | JAMES_DISABLE_COGNITIVE_STAGES=1 | 0.42 | — | — | 100 |
| rerank-off PM-7 | (별도 env) | 0.43 | — | — | 100 |
| graph-off PM-8 | JAMES_DISABLE_GRAPH=1 | 0.44 | — | — | 100 |

**비교 활용**:
- cycle β per-layer ablation cycle 의 baseline
- 양 모델 −0.05 단축 손해의 어느 컴포넌트 기여 정량

### 8. Paper external baseline (Tang & Yang 2024 EMNLP)

| 항목 | 값 |
|---|---|
| 목적 | 외부 SOTA baseline. JAMES vs paper 비교의 기준점 |
| Source | arXiv:2401.15391, Table 6 (retrieved chunks accuracy) |
| Framework | LlamaIndex vanilla (chunk 256 / top-10 / no reranker / paper prompt) |

**baseline 값** (paper original):

| Model | params | primary |
|---|---|---|
| GPT-4 | ~1.7T | 0.56 |
| Claude-2.1 | ? | 0.52 |
| PaLM | 540B | 0.47 |
| ChatGPT/3.5 | ~175B | 0.44 |
| Mixtral-8x7B | 47B | 0.32 |
| Llama-2-70b | 70B | 0.28 |

**비교 활용**:
- 외부 baseline 으로 JAMES 위치 정량
- "4B JAMES Default 가 paper Mixtral 47B (+0.16) / Llama 70b (+0.20) /
  ChatGPT 175B (+0.04) 초과" 같은 framing
- 단 framework 다름 caveat 의무 (Layer B 측정으로 보강)

## 결합 활용 패턴

### 새 모델 도입 시 standard 측정 sequence

새 모델 X 도입 시 다음 순서로 잣대 측정:

1. **raw e4b baseline** (모델 자체 능력) — `multihop_raw_run.py` default
   환경 + 새 모델
2. **JAMES Default** (스택 추가 후) — `multihop_terse_run.py` default 환경
   + 새 모델 + same-session
3. **paper-style baseline** (Layer B) — `multihop_raw_run.py PROMPT_STYLE=
   paper RAW_TOP_K=10` + 새 모델
4. **(선택) V2 옵션** — `JAMES_REVISE_PROMPT_V2=1` 활성 측정

→ 새 모델의 "스택 contribution" + "framework contribution" + "옵션 효과"
3 차원 정량.

### 자메스 업그레이드 시 standard 측정 sequence

새 fix / 컴포넌트 추가 시:

1. **JAMES Default** 측정 (다축) — fix 전후 비교
2. **paper-style baseline** 측정 — corpus retrieval 영향 분리
3. **(필요 시) ablation cell** — 새 fix 의 marginal contribution 정량

→ Mother-platform 6 원칙 (Default vs Option 분리 + NATURAL 지장 없는
개선 Default 인정) 기준 의사결정.

### 다른 fixture 추가 시

새 fixture (한국어 / NATURAL / 도메인-specific) 도입 시:

1. fixture 메타데이터 정리 (`source_dataset / source_citation / version`)
2. oracle 호환 확인 (gold_signals / abstention_truth / expected_path)
3. baseline 4 cell 측정 (raw / JAMES Default / paper-style / V2 opt-in)
   per model
4. 양 모델 측정으로 모델-무관 pattern 확인

## 통제 변수 vs 측정 변수 매트릭스

| 측정 | corpus | model | framework | retrieval | prompt | top-K | rerank |
|---|---|---|---|---|---|---|---|
| **vs paper (Tier C)** | 다름 | 같음 | 다름 | 다름 | 다름 | 같음 | 다름 |
| **Layer B (vs PM-LL)** | 같음 | 같음 | 다름 (advanced vs vanilla) | 같음 | 다름 (paper vs JAMES) | 같음 | 다름 |
| **per-component ablation (vs JAMES Default)** | 같음 | 같음 | 거의 같음 | 같음 | 같음 | 같음 | 같음 (또는 토글) |
| **vs raw (스택 contribution)** | 같음 | 같음 | 다름 (스택 X) | 같음 | 다름 (JAMES vs JAMES-terse) | 다름 (top-5 vs top-8) | 다름 |

→ 비교 목적에 맞는 측정 layer 선택.

## 마감 시점 정량 (2026-06-05 cycle)

### Mother-platform 가치 정량 (4 차원)

| 차원 | 정량 | 출처 |
|---|---|---|
| Corpus retrieval 우위 | +0.18 (mixtral) / +0.21 (e4b vs paper Mixtral) | PM-LL vs paper |
| Advanced 스택 단축 contribution | −0.050 (양 모델 동일) | PM-Default vs PM-LL |
| Advanced 스택 다축 contribution | graded +0.093-0.267 / abst_F1 +0.052-0.236 | PM-Default vs PM-LL |
| 모델 size 흡수 | 4B Default 0.480 ≈ 47B Default 0.450 | PM-10 vs PM-12-final |
| cap fix Default 회복 | primary +0.030 / graded +0.077 / abst_F1 +0.088 | PM-1b vs PM-10 |

## 관련 docs

- `cycle-2026-06-05-easy-explainer.md` — 초등생 버전 설명
- `alpha-8-paper-comparison-experiment-log-20260604.md` — 전체 cycle
  실험 기록 (§11-§34)
- `../../docs/handovers/v0.4-mother-platform-6-principles-cycle-2026-06-05.md`
  — handover doc (cycle β scope)
- memory `feedback_mother_platform_6_principles.md` — 6 원칙 entry
- memory `feedback_layer_b_framework_comparison_value.md` — Layer B
  가치 평가
