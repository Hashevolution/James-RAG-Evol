# JAMES vs MultiHop-RAG Paper — Experiment Log (2026-06-04)

> 목적: 자메스 retrieval/reasoning 품질을 외부 benchmark (MultiHop-RAG,
> Tang & Yang 2024, COLM) Table 6과 **fair 비교**해 우수성 확정 논리 구축.
> 사용자 framing 요구: ① 모델 통제 (같은 모델) ② metric 정밀.
>
> 이 문서는 시간순 실험 로그 — 각 시도의 방법 / 결과 / confound / 다음
> 결정. confound chain이 핵심 발견.

## 0. 외부 baseline (MultiHop-RAG 논문 Table 6, retrieved chunks)

| Model | retrieved | ground-truth |
|---|---:|---:|
| GPT-4 | 0.56 | 0.89 |
| Claude-2.1 | 0.52 | 0.56 |
| Google-PaLM | 0.47 | 0.74 |
| ChatGPT/3.5 | 0.44 | 0.57 |
| Mixtral-8x7B | 0.32 | 0.36 |
| Llama-2-70b | 0.28 | 0.32 |

- Metric: exact match on simple responses (entity / yes-no / before-after).
  null query = "insufficient information" 류면 correct. **정확한 matching
  logic은 논문 미공개.**
- 논문 결론: "existing RAG methods perform unsatisfactorily" — GPT-4 0.56
  조차 unsatisfactory. multi-hop RAG는 field-wide 어려운 문제.

## 1. 실험 시간순 로그

### Exp 1 — P1: paper-aligned binary (substring) [PR #709]

- 방법: `eval/qvt/oracle.py::score_paper_aligned_accuracy`. 기존 multihop
  bench JSON 재채점 (새 측정 없음). answerable=gold_signals match
  (primary=signal[0] substring), null=abstain. [strict, primary] band.
- 결과: JAMES+gemma4:e4b **primary 0.44** / strict 0.11-0.17.
  JAMES+Claude(Opus) 0.47. Claude RAW 0.72.
- 해석 (당시): e4b 0.44 = ChatGPT(0.44) 동급, Mixtral(0.32)/Llama-70b(0.28) 초과.
- **confound 발견**: yes/no를 substring 매칭 → 거짓 hit ("no" in "not"/
  "nothing", "yes" 답 중간 등장) → **과대평가 의심**.

### Exp 2 — P3: yes/no word-boundary precision [PR #710]

- 방법: primary 매칭을 question-type-aware로. yes/no는 word-boundary +
  answer-lead(60자) (`_primary_answer_match`). entity는 substring 유지.
- 결과: JAMES+gemma4:e4b **0.29-0.35** (P1 0.44에서 하락). Opus 0.26.
- **핵심 confound 발견 — answer-format mismatch**: 자메스 답 = 서술형
  (1400-2000자, "Source files:" 시작, yes/no 명시 안 함). 논문 = 단답.
  P1 substring 0.44 = 과대, P3 word-boundary 0.29 = 과소 (자메스 yes/no
  앞에 안 둠). **진실 = answer-format 통제 후.**

### Exp 3 — 순수 단답 smoke (fixture suffix)

- 방법: comparison 3Q에 "Answer with ONLY Yes/No" suffix. gemma4:e4b.
- 결과: 자메스 "No"/"No"/"No." 단답 produce (서술형 아님, 코드 0 변경).
  단 **3개 다 틀림** (gold Yes).
- confound: 단답 강제 → e4b **reasoning 생략** → comparison 틀림. 작은
  모델 불리 변수.
- cell overwrite 발견: cell 이름 = `<cell>-<tier>` (suite 미포함). terse
  측정이 기존 α-8 cell 덮어씀 → 이후 백업/복구 의무화.

### Exp 4 — 모델 통제 시도: Mixtral-8x7B

- 동기: framing 엄밀 — 논문 같은 모델로 통제. 논문 open 모델 중 최소 =
  Mixtral-8x7B (47B, 26GB). Llama-70b는 39GB.
- pull: `ollama pull mixtral:8x7b` (26GB, ~12분).
- 속도 smoke: 직접 ollama "Paris" 정답, **33초** (cold load + 짧은 답).
  RTX 4070 SUPER 12GB VRAM → CPU offload. multihop (긴 context + CoT) =
  **per query 1-3분 추정, 100Q = 1.5-5시간.** matrix runner는 cell마다
  server boot → Mixtral 로드 느려 boot timeout ("bench output 실패").
- 부작용: Mixtral 26GB 다운로드 후 **numba DLL quarantine** (Windows
  Defender 추정) → pytest conftest 차단 + server import 실패. `pip
  install --force-reinstall numba`로 복구.
- 결정: **모델 통제 포기.** 논문에 작은 모델 baseline 없어 동일-모델
  통제는 Mixtral 26GB 외 불가. 대안 = **handicap framing** ("더 작은
  모델 e4b로 논문 큰 모델 47B league 도전" — 동일-모델보다 강한 주장).

### Exp 5 — CoT+ANSWER 단답 (변수 통제 design)

- 동기: 순수 단답(Exp 3)이 e4b reasoning 생략시킴. 논문 큰 모델은 단답
  강제해도 내부 reasoning; 작은 모델은 reasoning 막힘. **CoT 허용 +
  마지막 ANSWER 줄 추출**로 reasoning 유지 + 단답 추출.
- 방법: fixture suffix = "Reason ... THEN last line 'ANSWER:' + 단답".
  oracle `_extract_terse_answer` ("ANSWER:" 줄 추출, last-wins, 없으면
  전체). gemma4:e4b, terse fixture 100Q, num_ctx=8192.
- 결과 (paper-aligned): primary **0.25**.
  - null_query **0.84** (abstention 강함, 신뢰 가능)
  - inference 0.16, comparison **0.00**, temporal **0.00**
- **confound 발견 — CoT 잘림**: e4b가 ANSWER 줄 안 만듦. 답 1308자에서
  잘림 ("...FTX and the"). comparison/temporal 0.00 = yes/no 결론 도달
  전 잘림 (gold no 케이스도 miss → 자메스 답이 yes/no 아예 안 냄).

### Exp 6 — 잘림 원인 진단

- num_predict = 8192 (max, 충분). think = OFF (workspace .env, thinking
  trace 흔적 없음). 둘 다 잘림 원인 아님.
- **진짜 원인 = num_ctx 8192 포화**: retrieval evidence (multihop 3개
  기사 ~6000자) + 질문이 context window 채움 → 답 토큰 부족 → 잘림.
- gemma4:e4b context length = **131072 (128K)** — 자메스 num_ctx 8192는
  1/16. 늘릴 여유 충분.

### Exp 7 — 측정 전용 환경: num_ctx=16384 [진행 중]

- 방법: `core/gemma_client.py`에 `JAMES_NUM_CTX` env override 추가
  (production default 8192 유지, 측정 시 16384). evidence + CoT 답 둘 다
  수용 → 잘림 해소 기대. terse fixture, gemma4:e4b.
- 상태: **background 측정 진행 중** (task bqtd1pqca, ~25-40min).
- 기대: comparison/temporal 0.00이 회복되면 잘림이 원인이었음 → fair
  측정. 여전히 0이면 자메스 comparison 진짜 약점.

## 2. confound chain (핵심 발견)

측정 시도마다 새 confound 등장:
```
P1 substring (과대)
  → P3 word-boundary (과소, answer-format mismatch)
    → 순수 단답 (reasoning 생략)
      → CoT 단답 (잘림)
        → think (이미 OFF)
        → num_predict (이미 8192 max)
        → num_ctx (포화 — 8192→16384 시도 중)
          → evidence size (?)
```

**근본**: 자메스 production pipeline (서술형 grounded RAG, 8192 context,
자체 retrieval, 큰 evidence) ≠ benchmark 단답 exact-match 설계. 깔끔한
점수 비교 = 자메스를 benchmark 형식으로 변환 (측정 전용 설정) + confound
하나씩 제거.

## 3. 신뢰 가능한 발견 (confound 영향 적음)

| 발견 | 근거 |
|---|---|
| **abstention 강점** | null_query 0.84 (모든 측정에서 일관) — hallucination 회피 |
| **모델 무관** | JAMES+e4b ≈ JAMES+Opus (paper-aligned 둘 다 ~0.25-0.47) — JAMES 위에서 모델 차이 작음 |
| **학습-지식 leak** | Claude RAW (no JAMES) 0.72 > GPT-4 retrieved 0.56 = multihop(2023 뉴스) Claude 학습 분포 포함 |
| **품질 lever = 도메인** | 모델 scaling (1b~27b~cloud) general에서 평탄 → lever는 데이터/온톨로지 |

## 4. 측정-side 룰 (이번 cycle 박힘)

- `feedback_methodological_chain_before_plan` — plan 전 verdict/diagnostic/role/순서 4질문
- `feedback_fixture_fitness_before_verdict` — fixture가 verdict-grade인지
- `feedback_evidence_grounded_validity_check` — evidence 전달 + 학습-leak 분리
- (신규 후보) **answer-format mismatch + confound chain** — production
  pipeline vs benchmark format은 confound 연쇄. 하나 제거하면 다음 등장.
- (신규 후보) **작은 모델 + 작은 토큰 예산은 단답 benchmark 부적합** —
  순수 단답이면 reasoning 생략, CoT면 토큰 소진/잘림.

## 5. 잠정 결론 (Exp 7 pending)

- 자메스 general-multihop 경쟁력은 **abstention(0.84)에서 명확**, 단답
  정답률은 confound chain으로 깔끔한 "확정" 미완.
- handicap framing (작은 e4b로 논문 큰 모델 league)이 측정 가능하면
  강한 입증. Exp 7 (num_ctx 16384)이 잘림 해소하면 fair 측정.
- Exp 7도 안 되면 → Mixtral 동일-모델 측정 (PC 부담 1.5-5h 감수).
- 어느 경우든 핵심 차별화 lever = **도메인 데이터 + 온톨로지** (general
  benchmark는 모든 시스템 retrieval bottleneck — 자메스 v0.5 도메인 pilot 방향).

## 6. 재현

- oracle: `eval/qvt/oracle.py::score_paper_aligned_accuracy` + `_extract_terse_answer`
- 재채점: `scripts/research/paper_aligned_rescore.py`
- terse fixture 생성: `scripts/research/build_terse_fixture.py` (CoT+ANSWER suffix)
- num_ctx override: `JAMES_NUM_CTX=16384`
- Mixtral tier: `--tiers M_MIXTRAL` (opt-in, 26GB CPU-offload 느림)
- tests: `tests/test_qvt_oracle.py::PaperAlignedAccuracyTests` (CoT 추출 + yes/no precision)
