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

## 7. Post-platform-fix verdict run (PM-1, 2026-06-04 PM)

전제: 이전 Exp 1-7은 platform 결함(response_style hardcode→NATURAL) 상태라
terse fixture suffix가 NATURAL 3-layer 강제와 싸웠음. PR #711이 결함 수정
(response_style="terse" → L1/L2/L3 collapse) → 비로소 깨끗한 terse 측정 가능.

- **경로**: direct-engine (HTTP 서버 우회), `response_style="terse"` 직접 전달.
  `scripts/research/multihop_terse_run.py`. 워크스페이스=hotpot_eval,
  `JAMES_NUM_CTX=16384`, mode_override=retrieval.
- **PM-0 smoke (gate)**: 근거회수 질문 4/4 ANSWER: 파싱 → terse 경로 viable.
  워크스페이스 미설정 시 prod 코퍼스 조회되는 wiring 함정도 발견·수정.
- **PM-1 본 측정** (gemma4:e4b × terse × 100Q):

| 지표 | 값 |
|---|---|
| accuracy_primary | **0.300** (30/100) |
| accuracy_strict | 0.240 |
| null_query (abstention) | **0.96** (24/25) |
| comparison / inference / temporal | 각 **0.08** |
| evidence-retrieved (answerable) | ~50/75 (33% recall miss) |

### 정직한 해석 (honest framing — 헤드라인 금지)

- **"0.30이 Llama-2-70b 0.28 초과" framing 금지.** 0.30의 24/30이 null
  abstention에서 나옴. paper 0.28-0.56은 주로 answerable 정확도 →
  composition이 달라 직접 비교 부당. JAMES answerable = 0.08 (paper 한참 아래).
- **진짜 강점 = abstention 0.96** — 답 없는 질문에 환각 안 함. paper 모델
  약점이자 JAMES 실제 moat (§5 0.84와 일관, n=25로 확인).
- **e4b floor 확인** — answerable은 근거 있어도 0.08. 작은 모델 multi-hop
  추론 천장 (smoke "근거 있어도 insufficient" 재현). JAMES 결함 아님.
- **retrieval recall 갭** — answerable 75 중 ~25 근거회수 실패. 모델과 별개
  JAMES retrieval 이슈로 분리 (별도 follow-up).

### PM-2: recall 갭 = 측정 아티팩트 (suffix → 500자 가드)

PM-1 answerable 32/75 sources=0 원인 추적:
- **suffix 임베딩 희석 가설 → 기각.** search-레벨 비교 base 30/32 ≈ terse
  31/32 (둘 다 gold chunk top-8 회수). `_recall_suffix_diag.py`.
- **진짜 원인**: terse fixture가 ~250자 ANSWER 지시를 query TEXT에 붙임 →
  50/100 질문이 **500자 보안 가드** (`core/security_layer/_detection.py:33`,
  `len(query)>500 → blocked "입력 길이 초과"`) 초과 → retrieval 전 차단
  (`blocked=True, loop_count=0`). 누락 32개 **전부** terse>500 & base≤500.
  base 질문은 0/100이 500 초과 (전부 통과).
- **함의**: format 지시는 query text가 아니라 `response_style="terse"`로
  (platform fix가 이걸 가능케 함). query text는 깨끗한 base 질문 유지.

### PM-1b: 올바른 재측정 (base fixture + response_style=terse)

| 지표 | PM-1 (artifact) | **PM-1b (corrected)** |
|---|---|---|
| accuracy_primary | 0.30 | **0.45** (45/100) |
| accuracy_strict | 0.24 | 0.26 |
| evidence-retrieved | 50/100 | **100/100** |
| inference_query | 0.08 | **0.56** |
| temporal_query | 0.08 | 0.20 |
| comparison_query | 0.08 | 0.12 |
| null_query | 0.96 | 0.92 |

honest framing:
- recall 아티팩트 제거로 primary 0.30→0.45, **inference 0.08→0.56** 극적 회복
  (차단됐던 게 대부분 inference). 이전 0.30은 artifact-suppressed.
- **"0.45 > ChatGPT 0.44 / Mixtral 0.32 / Llama-70b 0.28" 일부만 valid**:
  0.45의 ~23/45가 여전히 null abstention. answerable-only ≈ 0.29 (22/75).
- **inference 0.56 = 4B 모델치곤 진짜 강점** (JAMES 파이프라인이 작은 모델로
  multi-hop inference 가능케 함). yes/no형(comparison/temporal)은 e4b 추론 약점.
- 비교는 근사 (paper matching logic 미공개) — band 신호로만.
- raw: `reports/multihop_terse_gemma4-e4b_20260604_185857.json`

### 결론 + 다음

- e4b는 **abstention moat 입증 O + inference multi-hop 경쟁력 시사 / yes/no
  reasoning 약점**. 0.45는 4B 모델로 paper 중급 모델 범위 (composition caveat).
- answerable 우수성 **"확정"**엔 **mixtral:8x7b (paper 동일모델)** 필요 —
  JAMES+Mixtral vs paper-Mixtral 0.32 = 모델 통제로 파이프라인 순수 기여 분리.
  e4b가 이미 시사적(4B가 paper Mixtral 0.32 상회)이나 model-control이 nail.
  (26GB CPU-offload, 100Q 수 시간.)
- 재현: `scripts/research/multihop_terse_run.py`
  (`PROOF_MODEL`/`FIXTURE` 환경변수, default = base fixture)

## 8. 과잉 abstention 감소 가능성 조사 (2026-06-04, 사용자 발의)

질문: 과잉 abstention(comparison/temporal said_insufficient)을 줄여 추론을
늘릴 수 있나? abstention 강점(null 0.92)은 유지하면서.

### JAMES abstention 4층
| 층 | 위치 | 동작 |
|---|---|---|
| ① 관련성 게이트 | `pipeline_context.py` `_RELEVANCE_GATE=0.45` | avg_vec<0.45 → 근거없음 |
| ② unified 라우팅 | `pipeline_synth.py` | context 없으면 web-fallback |
| ③ 모델 자기-회피 | `response_style.py` terse rule | "근거없으면 insufficient" 출구 |
| ④ retry 소프트너 | `pipeline_synth.py:244` | "자료에 없음" → persona 재시도 (abstention 줄임) |

### 진단
- e4b said_insufficient는 **sources>0(①② 통과)** 상태에서 발생 → 원인은 ③
  (모델이 프롬프트 출구 택함), 게이트 아님.
- ④ 소프트너는 한국어 "자료에 없음" 접두사만 잡음 → 영어 "insufficient
  information" 통과 (측정모드 사각지대).

### 결론 — 감소 가능 (decoupling), 단 모델 능력이 상한
- JAMES가 이미 answerable vs null을 가르는 신호(게이트 0.45) 보유 →
  **게이트 통과 시 abstention 출구 제거(best-effort 강제), 실패 시 허용**으로
  분리 가능. null 강점 보존하며 answerable 회복 = tradeoff-최소 경로.
- 레버(surgical 순): (1) 게이트-조건부 프롬프트 (2) synth think=ON 조건부
  (3) 소프트너 ④ 영어 마커 확장.
- **상한**: 4B는 출구 막아도 합성 불가 시 said_insufficient→wrong로 바뀔 뿐.
  실익은 모델 추론력 비례 → mixtral(PM-3)이 정량 검증 (said_insufficient가
  correct로 바뀌면 = 레버 유효 + 병목=모델 확정).
- 기존 env `JAMES_DISABLE_ABSTENTION=1`은 ④를 끄는(=abstention 늘리는) 측정용,
  방향 반대. "줄이는" 전용 knob 부재.
- 영역 겹침: 보류 S6 난이도 라우터 + memory `feedback_abstention_dial_vs_pareto`.
- **구현은 미정** (mixtral 결과 보고 가치 판단). 본 절은 조사 기록.

## 9. 과거 e4b vs 현재 e4b 비교 (2026-06-04, 사용자 요청)

주의: 메트릭 다름 — 과거 graded(부분점수)+verbose, 현재 exact-match+terse.
직접 숫자 비교 아니라 "구성 설명"으로 읽을 것.

### 축 비교
| 축 | 과거 (α-5/6) | 현재 (PM-1b) |
|---|---|---|
| 모델/fixture | e4b / MultiHop-RAG | 동일 |
| 답변 형식 | 서술형 (NATURAL, 결함) | 단답 (terse, 수정 후) |
| 정답 메트릭 | graded substring 부분점수 | paper-aligned exact-match |

### JAMES+e4b 수치
| 지표 | 과거 | 현재 | 비고 |
|---|---|---|---|
| 정답 | graded 0.343 | primary 0.45 / answerable 0.29 | 메트릭 달라 직접비교 불가 |
| abstention | abst_f1 0.609 | null-acc 0.92 | 둘 다 강함 일관 |
| path(인용) | +0.404 (S4 universal) | PM 미측정 | 과거 고유 |

(출처: α-6 27b baseline `M_M e4b path 0.404/graded 0.343/abst_f1 0.609`,
recovery-curve `M_M e4b pure graded 0.347/abst_f1 0.558`.)

### 통찰 3
1. **사용자 가설 확증 — 과거 graded noisy.** 서술형 답에 gold 조각 우연
   포함 = substring 부분점수 noise ("점수 들쭉날쭉"). terse exact-match
   answerable 0.29 = 깨끗한 진짜 값. 0.343→0.29는 하락 아니라 noise 제거.
2. **과거 abst_f1 0.609 분해됨.** 단일 F1로 뭉쳐 있던 게 → null 0.92(탁월)
   + answerable 과잉회피(F1 끌어내린 숨은 페널티)로 분리. 즉 과거 0.609의
   원인 = 방금 발견한 과잉 abstention. 새 측정이 과거 숫자를 설명.
3. **JAMES 기여 패턴 일관.** 과거: graded 거의 안 바꾸고 path +0.40 더함
   (S4). 현재: inference 0.56로 끌어올림(4B 단독 불가). 둘 다 "모델 능력
   변경보다 retrieval/구조로 작은 모델 떠받침" 동일 메커니즘.

### 한 줄
과거 숫자가 틀린 게 아니라, 현재 측정(platform 수정 + terse exact-match)이
그 숫자의 **구성을 설명**한다. 다음: mixtral 행 추가 시 "모델 통제" 완성.

## 10. PM-3: 모델 통제 (paper 동일 Mixtral-8x7B) — 모델 무관성 확정

base fixture + response_style=terse + num_ctx 16384, mixtral:8x7b 100Q.
(smoke 60s/q, 본run ~73min, evidence-retrieved 100/100.)

| type | e4b (4B) | mixtral (47B) |
|---|---|---|
| primary | 0.45 | **0.46** |
| strict | 0.26 | 0.26 |
| inference | 0.56 | **0.56** (동일) |
| comparison | 0.12 | 0.20 |
| temporal | 0.20 | 0.12 |
| null | 0.92 | 0.96 |
| answerable-only | 0.29 | **0.29** (동일) |

### 핵심 — 모델 12배 키워도 거의 불변
- 4B→47B (12× params)인데 primary 0.45→0.46, answerable 0.29=0.29, inference
  0.56=0.56. **JAMES 위에서 모델 무관성 확정** (§3 가설을 paper 모델 +
  exact-match로 입증).
- 제 이전 가설(큰 모델이면 yes/no 과잉회피 풀림) **반증**: comparison/temporal
  mixtral에서도 낮음 (0.20/0.12). → answerable 천장(~0.29)은 **모델 추론력이
  아니라 retrieval 완전성 or JAMES 추론 스택**이 원인.
- vs paper: JAMES+Mixtral 0.46 > paper-Mixtral 0.32 (+0.14). 단 차이는 주로
  abstention/null 구성 + 우리 retrieval이지 answerable 추론 아님 (answerable
  양쪽 0.29). composition + 근사 caveat 유지.

### 다음 — raw(vanilla RAG)가 천장 원인 가른다
PM-4(e4b raw) / PM-5(mixtral raw): JAMES 추론 스택 제거, 같은 retrieval chunk.
- raw ≈ full → 스택이 이 벤치에서 무의미 (가치=retrieval).
- raw < full → 스택이 가치 더함.
- raw > full (특히 answerable) → 스택이 과잉회피로 **해침** (tradeoff 위치 확정).
raw: `reports/multihop_terse_mixtral-8x7b_20260604_204351.json`.

## 11. PM-4/PM-5: raw(vanilla RAG) vs JAMES-full — abstention이 지배

raw = retrieval(top-5) + 단일 LLM 호출, JAMES 추론 스택 제거. terse 동일,
num_ctx 16384. validity guard: 양쪽 75/75 answerable evidence (leak 없음).

### 3×2 (primary / answerable-only / null)
| 구성 | primary | answerable-only | null |
|---|---|---|---|
| paper-Mixtral | 0.32 | — | — |
| RAW e4b | 0.52 | 0.39 | 0.92 |
| JAMES-full e4b | 0.45 | 0.29 | 0.92 |
| RAW mixtral | 0.55 | **0.65** | **0.24** |
| JAMES-full mixtral | 0.46 | 0.29 | **0.96** |

### type별 (mixtral)
| type | RAW | full | Δ(full-raw) |
|---|---|---|---|
| inference | 0.92 | 0.56 | −0.36 |
| comparison | 0.72 | 0.20 | −0.52 |
| temporal | 0.32 | 0.12 | −0.20 |
| null | 0.24 | 0.96 | +0.72 |

### 결론 (사용자 직감 "abstention 과잉" 확정)
1. **JAMES 스택 = abstention 다이얼.** answerable↔null 맞바꿈. mixtral
   answerable 0.65→0.29, null 0.24→0.96. 스택이 답을 죽이고 회피를 살림.
2. **"모델 무관성"은 스택 착시.** 스택이 answerable을 ~0.29 천장에 가둠.
   제거 시 모델 능력 드러남: raw mixtral 0.65 ≫ raw e4b 0.39.
3. **모델 성격**: e4b 천성 소심(raw null 0.92, ans 0.39); mixtral 천성
   자신만만(raw ans 0.65, null 0.24 환각) → JAMES 회피 규율 필수(0.24→0.96).
4. **JAMES 진짜 가치 = 자신만만 모델의 환각 억제** (mixtral null 0.24→0.96).
   단 현재 과잉 교정 → answerable 동반 사망.
5. **이상 = raw 답변력(0.65) + full 회피력(0.96).** 현재 어느 설정도 둘 다
   못 가짐. §8 게이트-조건부 decoupling이 타깃.
6. **paper 대비**: 같은 모델 raw mixtral answerable 0.65 ≫ paper 0.32 →
   **우리 retrieval 강함.** "+0.14 우위(full 0.46 vs paper 0.32)"의 정체 =
   abstention 구성, 추론 스택은 answerable에 음의 기여.
raw: `reports/multihop_raw_{gemma4-e4b,mixtral-8x7b}_20260604_*.json`

### 후속 (필요 확정)
- 천장 원인 = 추론 스택의 과잉 abstention. **다음 = 스택 stage-localization**
  (reflect/verify/relevance-gate/graph 중 어디가 answerable 죽이나) →
  게이트-조건부 decoupling 설계 → null≥0.9 유지하며 answerable 회복 측정.
