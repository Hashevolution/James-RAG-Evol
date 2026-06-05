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

## 12. PM-6: stage-localization — 인지 stage는 범인 아님 (negative)

e4b full + `JAMES_DISABLE_COGNITIVE_STAGES=1` (planner/reflect/verify off).

| | full(PM-1b) | cognitive-off(PM-6) | raw(PM-4) |
|---|---|---|---|
| primary | 0.45 | 0.42 | 0.52 |
| inference | 0.56 | 0.44 | 0.60 |
| temporal | 0.20 | 0.04 | 0.16 |
| null | 0.92 | **1.00** | 0.92 |
| answerable-only | 0.29 | 0.23 | 0.39 |

- **인지 stage 끄니 abstention 더 심해짐** (null 1.00, answerable 0.23↓).
  reflect/verify는 오히려 inference 도움(0.56 vs 0.44). over-abstention 원인 ✗.
- 범인 = raw와 full의 나머지 차이: query_rewrite / multi-arm retrieve /
  rerank / graph context / synth 프롬프트 조립.

### 공짜 진단 (답 나란히 비교)
- raw 맞고 full insufficient인 comparison: 전부 raw_src=5, full_src=3
  (단 count 방식 다름 — raw=chunk, full=unique file).
- over-abstention은 **multi-fact 합성형(comparison/temporal)에 집중**, 단일
  개체 inference는 거의 영향 없음.
- **메커니즘 가설**: multi-hop yes/no는 2+ chunk 합성 필요 → full의 context
  pruning이 한쪽 누락 → 합성 불가 → insufficient. raw 5 chunk는 양쪽 포함 ↑.
- nuance: e4b raw comparison 0.40엔 yes/no 추측 섞임(≈coin-flip). mixtral
  raw 0.72는 진짜 합성 → 스택이 과잉회피만 멈추면 큰 모델은 합성 함.

### 상태
- 정밀 localization은 추가 ablation(graph-off / rerank-off / query_rewrite-off)
  각 ~30-40min 필요 = multi-hour 캠페인.
- 고수준 결론은 확정: JAMES full pipeline이 multi-hop 합성형에서 과잉회피,
  원인은 인지 stage 아닌 retrieval/context 조립. 다음 = 게이트-조건부
  decoupling 설계(focused) vs 추가 ablation — 사용자 판단 대기.

## 13. 자율 개선 캠페인 (2026-06-04 저녁, 사용자 위임 ~6h)

위임: ablation 완료 → 수정사항 신중 판단·선택 실행 → 같은 조건 재측정 검증
→ e4b 추론 점수 안정 향상까지 반복 → 성공 시 mixtral 연이어 → 보고.
자율 수행하되 수정은 신중 판단, 반드시 기록.

### 가드레일 (자율 판단 기준)
1. **null abstention 보호 — 탐색 하한 0.70** (사용자 조정 2026-06-05):
   탐색 중 null을 0.70까지 내려보며 answerable↔null tradeoff 곡선의 knee와
   진짜 기전을 매핑(0.88 고정은 기전 가릴 수 있어 완화). null<0.70이면 revert.
   최종 추천 config = answerable↑ 대비 null 손실의 Pareto 균형으로 판단.
2. mother-platform: 도메인 종속 X, 일반 개선만. default 안전(불확실시 env-gate).
3. 모든 변경 = 기록(이 로그) + 커밋. 채택/기각 모두 사유 명시.
4. 최소·가역 변경, diff 자가검증.
5. 반복 상한 ~3회. 수렴 안 하면 현 상태 기록 후 보고.
6. 정직한 목표: e4b 4B 천장 인정 → 목표 = 스택이 깎은 손실 회복(full ans
   0.29 → raw ~0.39 수준, null 유지), e4b 천재화 아님.

### 기준선 (e4b, terse, num_ctx 16384)
| 구성 | primary | answerable-only | null |
|---|---|---|---|
| RAW | 0.52 | 0.39 | 0.92 |
| full | 0.45 | 0.29 | 0.92 |
| cognitive-off | 0.42 | 0.23 | 1.00 |

### ablation 결과 (채워질 예정)
| 토글 | primary | answerable | null | 판정 |
|---|---|---|---|---|
| rerank-off (PM-7) | 0.43 | 0.27 | 0.92 | ✗ 범인 아님 (answerable 회복 X) |
| graph-off (PM-8) | 0.44 | 0.28 | 0.92 | ✗ 범인 아님 |
| (cognitive-off PM-6) | 0.42 | 0.23 | 1.00 | ✗ (오히려 abstention↑) |
| → 3종 ablation 전부 ✗ = root cause는 stage 아님 → §14 context[:1000] |
| query_rewrite-off (PM-9) | … | … | … | … |

### 수정 이력 (채워질 예정)
- (수정 채택/기각 기록)

## 14. ROOT CAUSE — synth 프롬프트 context[:1000] truncation (2026-06-05)

ablation(인지/rerank/graph) 모두 answerable 회복 실패 → 코드 읽기로 진짜 원인:

`core/reasoning/engine_synth.py::generate_rag_answer` 가 evidence를
**`context[:1000]` (1000자)로 잘라** 프롬프트에 넣음. raw runner는 chunk를
`call_gemma`로 직접 넘겨 이 cap을 우회 → full evidence.

### 왜 이게 모든 걸 설명하나
- multi-hop(comparison/temporal)은 2+ fact 필요. 두 번째 fact가 char 1000
  뒤에 있으면 잘림 → 합성 불가 → "insufficient" 과잉회피.
- inference(단일 fact, 보통 앞쪽 chunk)는 덜 영향 → 관측된 type 패턴 일치.
- **num_ctx=16384가 안 먹힌 이유**: 잘림이 모델 context window가 아니라
  프롬프트 조립 단계(`[:1000]`)에서 발생 → 모델은 1000자만 봄.
- stage 토글로 안 잡힌 이유: 어느 stage도 이 truncation을 안 건드림.

### 수정 (env-gated, 최소·가역)
`JAMES_SYNTH_CONTEXT_CHARS` env (default 1000 = production byte-identical).
측정/multi-hop은 상향(테스트 8000). 채택 시 default 변경은 측정 결과로 정당화.

### 검증 계획
- PM-10: e4b full + JAMES_SYNTH_CONTEXT_CHARS=8000 재측정. answerable이
  raw(0.39)쪽으로 가면 root cause 확정 + 수정 유효. null 변화 추적(탐색
  하한 0.70).
- PM-9(query_rewrite-off)는 불필요 → PM-10으로 대체.

## 15. PM-10: fix 검증 (context cap 1000→8000, e4b) — 성공

| | full(PM-1b) | PM-10 cap8000 | raw |
|---|---|---|---|
| primary | 0.45 | **0.48** | 0.52 |
| inference | 0.56 | **0.80** | 0.60 |
| comparison | 0.12 | 0.16 | 0.40 |
| temporal | 0.20 | 0.08 | 0.16 |
| null | 0.92 | **0.88** | 0.92 |
| answerable-only | 0.29 | **0.347** | 0.39 |

- **root cause 확정 + fix 유효.** context cap만 1000→8000 했는데 answerable
  0.29→0.347, inference 0.56→0.80(raw 0.60 초과), null 0.88(>0.70 floor 유지).
  **가드레일 충족(answerable↑ AND null≥0.70) → 채택.**
- 남은 gap(0.347 vs raw 0.39) = comparison/temporal e4b yes/no 합성 한계(context 무관).
- **temporal 0.20→0.08 하락** (n=25 노이즈 가능 / over-stuffing 의심) →
  PM-11 cap=4000으로 Pareto knee 탐색.

### 수정 이력
- [채택] `engine_synth.py` context[:1000] → context[:JAMES_SYNTH_CONTEXT_CHARS]
  (default 1000 byte-identical). 근거: PM-10 answerable +0.057, inference
  +0.24, null −0.04(floor 내). 기존 unit test 28 pass.
- default 변경 여부 = PM-11 Pareto 결과로 판단(현재 default 1000 유지).

## 16. PM-11: cap Pareto sweep (e4b) — 8000이 최적

| cap | answerable | inference | comparison | temporal | null |
|---|---|---|---|---|---|
| 1000(full) | 0.29 | 0.56 | 0.12 | 0.20 | 0.92 |
| 4000 | 0.32 | 0.76 | 0.12 | 0.08 | 0.88 |
| 8000 | **0.347** | **0.80** | 0.16 | 0.08 | 0.88 |

- **8000이 4000 지배** (answerable·inference↑, null·temporal 동일). knee 이득
  없음 — answerable은 cap에 단조 증가.
- temporal 0.20→0.08은 4000에서 이미 발생(over-stuffing 아님) = e4b temporal
  약점 + n=25 노이즈(raw도 0.16).
- **e4b cap 8000에서 안정화**: answerable 0.29→0.347(raw 0.39 근접). 남은
  gap = e4b yes/no 능력 천장(context 무관). 추가 조정 중단(과적합 방지).
- default 변경 권고: 1000은 명백히 과소(multi-hop 불구). 권고값은 보고서에서
  latency/abstention 균형으로 제시. 측정은 8000 계속.

## 17. ★ 핵심 발견 요약 (2026-06-05) — 통합

### 한 문장
**JAMES synth 프롬프트의 하드코딩 `context[:1000]` 한 줄이 evidence를 1000자로
잘라, 플랫폼 전체의 multi-hop 추론을 장기간 조용히 불구로 만들고 있었다.**
이를 풀자 (env-gate) e4b inference 0.56→0.80, answerable 0.29→0.347.

### 발견의 사슬 (방법론)
1. raw(vanilla RAG) > JAMES-full 역전 발견 (mixtral answerable 0.65 vs 0.29).
2. "스택이 abstention과 answerable을 맞바꾼다" 가설 (사용자 직감).
3. stage ablation 캠페인(인지/rerank/graph) 전부 negative → stage 아님.
4. 코드 read → `context[:1000]`. raw가 이 cap을 우회했던 게 차이.
5. num_ctx는 red herring (cut이 프롬프트 조립단계, 모델 window 아님).
6. fix(env-gate) + cap sweep(4000<8000) 검증 → root cause 확정.

### 왜 큰 발견인가
- **장기 platform 품질 버그**: 1000자 cap이 모든 multi-hop RAG 답변 품질을
  깎아옴 (과거 graded 측정도 이 위에서 이뤄짐).
- **2개 착시를 설명**: (a) "모델 무관성"(e4b≈mixtral) — 둘 다 1000자만 받아
  능력차 안 드러남. (b) "abstention 강점" 일부 — evidence starvation 부작용
  (진짜 abstention 규율은 별개로 건강, null 0.88 유지).
- **측정 방법론 가치**: ablation 전부 negative가 "stage 아님"의 강한 증거가
  되어 코드 read를 강제 → root cause 도달. honest negative의 힘.

### 정직한 경계 (over-claim 금지)
- fix는 inference(개체 추출)에 큰 효과. comparison/temporal(yes/no 합성)은
  e4b 모델 능력 천장이라 context로 안 풀림 (raw에서도 약함).
- temporal 0.20→0.08 하락은 미해결(노이즈 가능). 추적 필요.
- default 변경(1000→?)은 latency/abstention 균형 결정 — 보고서에서 권고.
- mixtral+fix(PM-12) 결과가 "raw 답변력+full 회피력 동시 달성" 확정/반증.

### 채택된 코드 변경
- `core/reasoning/engine_synth.py`: `context[:1000]` → `context[:JAMES_SYNTH_CONTEXT_CHARS]`
  (default 1000 byte-identical). commit `fix(synth): env-gate evidence char budget`.

## 18. temporal 0.20→0.08 하락 origin — answer-format drift (2026-06-05)

cap=1000→8000 변경 시 temporal 5/25 → 2/25. 같은 25 query 매핑하면 flipped 5
(1 win + 4 loss). 4 loss 모두 동일 패턴:

- e4b가 cap↑로 풀린 evidence를 **self-critique/revision 메타 모드**로 활용 ("This
  revision focuses on improving the professional tone...", "## Revised Answer",
  "Hello, I am JAMES. I will follow your plan..."). 답이 분석적 서술이 되어
  yes/no 결론이 lead 60자 밖으로 밀림 → matcher (P3 yes/no word-boundary,
  `_YESNO_LEAD_CHARS=60`) 미스.

| qid | cap1k correct | cap8k correct | cap8k 답 lead 양상 |
|---|---|---|---|
| 77 | False | True | "Direct Answer: No, ..." (lead에 명시 — win) |
| 78 | True | False | "### Step 1: Search Sporting News..." (계획 서술, yes/no 없음) |
| 83 | True | False | "This revision assumes the review critique was..." (메타) |
| 84 | True | False | "This revision addresses the review by..." (메타) |
| 96 | True | False | "### 1. CBSSports.com Report..." (구조 서술) |

- **noise가 아니라 systemic**: 5/25에서 4 동일 양식 변화. e4b는 짧은 context는
  결론 우선("Yes,..." / "No,..."), 긴 context는 분석/메타 모드.
- **실제 품질 변화는 모호**: 사람이 본문 끝까지 읽으면 4개 중 일부는 yes/no
  결론이 본문 안에 있을 수 있음 (사람 채점 필요). metric 기준엔 진짜 미스.
- **matcher 약점**: lead 60자 yes/no 강제는 단답 fixture를 가정. long-context
  분석 서술에 불리. (수정 후보 = whole-answer + 위치 가중, 단 substring noise
  재유입 위험 — 별도 cycle.)
- **함의**: temporal score는 cap↑ 후 줄어들지만 **inference 0.56→0.80 효과는
  실재**(open-ended entity, format-drift 영향 적음). default 결정 시 temporal
  loss는 metric artifact로 해석, 핵심 평가는 inference + answerable-only.

## 20. 두 번째 ROOT CAUSE — session episodic context drift (2026-06-05)

§18 temporal drift 추적이 두 번째 platform-wide hidden defect 후보 발굴.

### 진단

`engine_memory.py:153-200` (Cognitive Phase 3 PR-9b)이 같은 세션 prior turn
의 plan/reflect/verify summaries를 `system_prompt`에 inject:

```python
events = get_episodic_memory().recent_events(
    session_id_ep, limit=12, stages=("plan","reflect","verify"))
# 최근 3 turns × 3 stages × summary[:120]
lines = ["[이전 추론 흔적 (이 세션)]"]
for slot in recent_turns:
    for stage in ("plan","reflect","verify"):
        lines.append(f"- [{stage}] {ev.summary[:120]}")
system_prompt = f"{system_prompt}\n\n{episodic_block}".strip()
```

### Smoking gun (DB inspection)

`./james_episodic.db` SQL 조회:
- `pm1-terse` session **4,947 events 누적** (711 plan + 1319 reflect + 2100
  verify + 817 synth). 100 query × 평균 ~50 events.
- reflect summary가 **본질적으로 메타-critique 톤**으로 생성됨:
  - `**1. Contradiction / factual error:** The answer is structurally sound,
    but it relies on the phrase...`
  - `**Contradiction / factual error:** The answer is overly procedural and
    academic, detailing the steps taken rather than providing a direct...`
- 이게 system_prompt에 inject되면 모델 입장에서 "이 세션 = 답 만들고 →
  contradiction 찾기 → revise" 라는 강력한 framing.

### 왜 §15 cap[:1000] fix 후에야 드러났나

cap=1000일 땐 evidence가 짧아 모델이 발산 못 함 → 메타 cue 본문 반영 X.
cap=8000으로 풀자 모델이 답을 길게 발산할 여유 생김 → episodic critique
framing을 그대로 따라가 답 본문이 "## Revised Answer" / "This revision
focuses on improving..." / "review critique" 모드 진입. cap[:1000]과
정확히 동일한 두-결함-상호-mask 패턴.

### 영향 범위

- **측정**: PM-1~PM-12 모두 same-session ("pm1-terse") → episodic 누적
  conditioning 노출. e4b·mixtral·cap 무관 전부 영향.
- **production**: 사용자가 같은 세션에서 여러 query → episodic trail 누적
  → 답이 점진적 "revision draft" 메타 모드로 drift. 대화 길어질수록 심함.
  (단 production은 보통 query 다양성 + 일반 chat 흐름이라 측정만큼
  amplify되진 않음 — 정량은 후속 cycle.)

### 채택 fix (측정-side, production byte-identical)

`scripts/research/multihop_terse_run.py` 1줄: `session_id="pm1-terse"` →
`session_id=f"pm-terse-q{q['id']}"`. 매 query가 세션 첫 turn이 되어
`engine_memory.py:164` gate (`if hist_ctx and ...`)가 자동으로 episodic
inject skip. **코드 변경 없이 측정 환경만 정정.**

### 검증 (PM-13/PM-14)

| 측정 | 환경 | 기대 |
|---|---|---|
| PM-13 | e4b + cap=8000 + per-query session | qid 78/83/84/96 4 flip 풀림 → temporal 회복 0.08→? + comparison/inference 추가 회복 가능 |
| PM-14 | mixtral + cap=8000 + per-query session | answerable 0.29 → raw 0.65 방향 회복 + null 유지 → §11 "스택 = abstention 다이얼" 가설 재검증 |

### Platform-side fix 후보 (검증 후 사용자 결정)

| 옵션 | 범위 | 위험 |
|---|---|---|
| (A) reflect/verify summary tone 정화 | summary 생성 단계에서 critique 헤더 제거/중립화 | reflect/verify 본질 design 영향 |
| (B) episodic inject 양식 paraphrase | 입력 시 critique-tone 원문 X, 중립 fact-only 변환 | 추가 cost + 정보 손실 |
| (C) synth stage는 episodic 비주입 | `engine_memory.py:162` stage 조건 추가 | conversational follow-up 약화 가능 |
| (D) JAMES_EPISODIC_CONTEXT default 1→0 | 이미 env-gate 존재, default 뒤집기 | conversational session에서 PR-9b 의도 손실 |

권고 = PM-13/PM-14 결과 + production session 누적 정량 측정 후 결정.

## 21. PM-13 결과 — §20 진단 부분 기각, honest 정정 (2026-06-05)

§20 "두 번째 ROOT CAUSE = episodic context drift" framing은 over-claim.
PM-13 (e4b cap=8000 + per-query session, episodic 자동 skip) 결과로 일부
기각.

### 결과 비교

| metric | PM-1b cap1k same-sess | PM-10 cap8k same-sess | **PM-13 cap8k per-query** |
|---|---|---|---|
| primary | 0.45 | 0.48 | **0.41** ↓ |
| answerable-only | 0.293 | 0.347 | **0.280** ↓ |
| inference | 0.56 | 0.80 | **0.68** ↓ |
| comparison | 0.12 | 0.16 | **0.12** = |
| temporal | 0.20 | 0.08 | **0.04** ↓↓ |
| null | 0.92 | 0.88 | **0.80** ↓↓ |
| meta-mode marker (lead 300) | — | 37/100 | **29/100** (−22%) |

### 진단 정정

1. **메타 모드 풀리지 않음.** per-query session_id로 episodic을 끊었는데도
   29/100 답이 여전히 "## Revised Answer" / "This revision focuses on..."
   양식. 예: qid 77 PM-13 답 lead = "This revision focuses on adopting a
   more formal, academic, and polished tone..." — episodic 끊어도 동일
   메타 양식. **episodic은 main driver 아니라 partial contributor (8/100
   메타 모드 감소만)**.

2. **episodic의 net positive 효과.** 끄니 inference 0.80→0.68, null 0.88→
   0.80, primary 0.48→0.41 모두 하락. episodic의 cross-turn reasoning +
   critique-tone abstention 강화가 multi-hop fixture에서 일정 가치 있었음.
   단순 "결함 제거" 아니라 **양면 효과** (drift 8% 감소 vs primary 0.07
   regression — net 손해).

3. **진짜 root cause 후보 (미규명, 잠정 4)**:
   - (a) e4b 모델 자체 long-context 답변 양식 (Gemma4 prior, training data
     영향)
   - (b) `rule_text_en` NATURAL 잔재가 측정 어딘가 inject
   - (c) synth prompt가 long-context에서 분석/report 양식 자체-유도
   - (d) `system_prompt` 다른 layer (persona / character / preference)
     잔재

### 사용자 박은 룰 모두 trigger됨

- `feedback_finding_size_honest_framing`: §20 "ROOT CAUSE" framing이
  over-claim. 진단 가설 부분 기각.
- `feedback_fixture_fitness_before_verdict`: multi-hop fixture가
  episodic의 양쪽 효과를 정확히 측정 못 함 (cross-turn reasoning이 단발
  multi-hop에선 정의상 의미 약함).
- `feedback_evidence_grounded_validity_check`: fix가 가설을 약하게 지지
  (-8 메타) + 다른 축에서 명확히 해침 (-0.07 primary). 가설 부분 기각이
  정확한 결론.
- `feedback_n1_verdict_inflation_n3_caught`: §20을 n=1 SQL 검사 +
  진단으로 "확정 수준" 표현. n=100 measurement에서 약화.

### 진단의 정직한 잔존 가치

- pm1-terse session 4,947 events 누적은 사실. cross-turn episodic inject
  가 시스템에 있다는 점도 사실. 영향이 메타 모드 8/100 + abstention
  강화 ~+0.08 / inference 강화 +0.12 로 quantified됨 — 이건 가치 있는
  observation (production 사용 패턴 영향 측정 자료).
- platform-side fix 옵션 (A/B/C/D)은 더 이상 권고 안 함. episodic의
  net positive 효과 때문에 끄는 fix는 손해. 다른 fix (예: critique-tone
  summary 자체를 중립화 = option A) 만 유효 후보.

### 다음

- PM-14 (mixtral cap=8000 + per-query session) → 메타 모드 패턴이 모델
  무관인지 (e4b만의 특질인지) 확인. 진행 중 (task baz0a36u2).
- mixtral에서도 같은 양식이면 → (c)/(d) layer-side 또는 prompt-side
  잔재 후보 강화. e4b만이면 → (a) 모델 양식 천장.
- 진짜 root cause는 별도 cycle 또는 후속 코드 read 필요 (이번 cycle
  scope 외, honest framing).

## 22. 진단 (c) — reflect engine의 critique→revise + stripper 패턴 부족 (2026-06-05)

§21 honest 정정 후 (a)/(b)/(d) 다 약화 또는 기각. (c) reflect engine
이 진짜 source 라는 evidence chain.

### Evidence chain (4 단계)

1. **(a) 기각 — raw e4b 0/100**: `multihop_raw_*.json` (JAMES 스택 우회,
   직접 call_gemma) 답 100/100 중 메타 marker 0. e4b pure model 은
   long-context evidence 받아도 "## Revised Answer" 양식 절대 안 만듦.
   **JAMES 스택이 유도** 하는 것.

2. **(b)/(d) 약화**: `response_style="terse"` 정상 동작 (resolve_style
   확인). system_prompt 87자 ("Always respond in English. JAMES")
   메타 cue 없음. memory_context 438자 "[사용자 설정] / [반복 패턴]"
   단순 preference. persona.style 은 deprecated (memory dump 확인).
   per-query session 이라 episodic 도 skip.

3. **(c) 확정 — reflect engine 코드 자체 명명**: `reflect.py` line 73-88
   주석:
   > "Even with the REVISE_PROMPT directives explicitly forbidding
   > meta-text, Gemma 4 occasionally opens the revision with the model
   > commenting on the critique it just received..."
   이미 2026-05-26 A3.1 NVIDIA 사건 때 같은 현상 발견 + stripper
   추가. 영어 6 패턴 (Korean 7 vs EN 6 빈약). PM-13 29/100 메타 답
   전부 (29/29) 기존 6개 EN 패턴에 미스.

4. **`.env` 확인**: 루트 `.env` 에 `JAMES_ENABLE_REFLECT=1` 박혀있어
   측정 시 reflect 활성. PM-13 log 에 `[reason:reflect] reasoning.
   reflect.critique` + `.revised` 매 query 마다 호출 확인.

### Type 분포 일치 (causal coherence)

| type | meta-marker | 가설 |
|---|---|---|
| temporal | 14/25 (56%) | yes/no 합성형 → critique "Missing core" 빈발 → revise → 메타 양식 |
| comparison | 9/25 (36%) | 동일 |
| inference | 5/25 (20%) | single fact → critique 깔끔 → revise 적음 |
| null | 1/25 (4%) | abstention 답 → critique "NO_ISSUES" → revise skip |

### Band-aid fix (즉시 적용, commit `2d96192`)

- `_META_NARRATIVE_PATTERNS` 영어 5 패턴 추가:
  - `^\s*\*?\*?##?\s*Revised\s+(Answer|Draft|Version)\*?\*?:?`
  - `^\s*\*\*\s*Revised\s+(Answer|Draft|Version)\s*\*?\*?:?`
  - `^\s*This\s+revision\s+(focuses|addresses|maintains|assumes|...)`
  - `^\s*This\s+revised\s+(answer|draft|version|response)`
  - `^\s*Hello,?\s+I\s+am\s+JAMES\.\s*I\s+will\s+follow`
- `REVISE_PROMPT_EN` forbidden openings list 확장 + heading 금지 명시
- Tests 50/50 pass (39 기존 + 11 신규)
- PM-13 retrofit: 14/29 추가 caught (heading 양식 15/29 는 prompt 만)

### PM-15 검증 (e4b cap=8000 + per-query + band-aid 활성)

| metric | PM-10 no-fix | PM-13 ep-fix | **PM-15 +stripper** |
|---|---|---|---|
| primary | 0.480 | 0.410 | **0.460** (+0.05) |
| answerable | 0.347 | 0.280 | **0.333** (+0.05) |
| inference | 0.800 | 0.680 | **0.760** (+0.08) |
| comparison | 0.160 | 0.120 | **0.160** (+0.04) |
| temporal | 0.080 | 0.040 | **0.080** (+0.04) |
| null | 0.880 | 0.800 | **0.840** (+0.04) |
| meta-marker | 38/100 | 30/100 | **28/100** (-2) |

- 모든 axis 회복, 단 메타 marker 감소 약함 (30→28). band-aid 효과는
  체감 작음. 핵심 metric (answerable / inference) 회복은 의미 있음.

### (c) 의 정밀화 — (c1) reflect / (c2) synth draft

PM-15 메타 답 28/100 분해:
- **(c1) 5/28 = stripper 패턴 매치** (revise pass 산물). separator
  뒤 body 추출 또는 draft fallback 작동.
- **(c2) 23/28 = stripper 미스** = **synth draft 자체가 메타 양식**.
  예:
  - qid 7: "### Step 1: Search TechCrunch and The Verge..." (planner
    sub-task 양식)
  - qid 30: "**[Revised Answer]** / Thank you for the detailed..."
    (bracket 변형 + thank you)
  - qid 35: "Hello, I am JAMES. Based on the provided internal data,
    here is the step-by-step analysis..."

→ (c) 가 두 층:
  - (c1) reflect revise pass — stripper + Option B (V2) 로 fix 가능
  - (c2) synth draft 자체 — **planner sub-task leak** 또는 **NATURAL
    rule_text "report format with ## section headers" cue 가 모델
    prior 활성화** 가능성. stripper 무관. **별도 cycle β scope**.

## 23. Option B systemic fix (PM-16 검증 진행 중, 2026-06-05)

(c1) 의 진짜 systemic fix — critique 본문 비노출.

### Design

`REVISE_PROMPT_V2_{EN,KO}` 추가 (commit `9ed1af7`):
- v1: `revise_prompt = "Revise the draft to address the review.\n[Review]\n{critique}\n..."` → 모델이 critique 본문 봄 → 메타 양식 자연 유도
- **v2**: `revise_prompt = "Write the best possible answer. An earlier attempt had a quality flag (type: {issue_type}). [Question] [Earlier attempt]..."` → critique 본문 비노출, "answer-write" task 로 framing
- `_extract_issue_flag(critique_text)` regex 가 critique → 4-tag 압축
  (factual_error / missing_core / ambiguity / general)
- v2 prompt 본문에 `critique` / `review` 단어 자체 미등장 (test 로 enforce)
- env-gate `JAMES_REVISE_PROMPT_V2=1` 활성. default OFF = production
  byte-identical. 검증 후 default flip = 후속 PR.

### 왜 systemic 인가

band-aid (stripper + forbidden list 확장) 는 무한 패치 게임. v2 는
**메타-format 공간 자체를 닫음** — 모델이 critique 본문을 안 보면
revision-speak 양식 자체가 응답 후보로 활성화 안 됨. critique pass
는 그대로 (audit trail 보존), 오직 revise-side framing 만 변경.

### PM-16 검증 (진행 중, task bb77a7kmv)

- e4b cap=8000 + per-query + stripper + V2 활성 100Q
- 기대: 메타 marker 28 → ?(target <10/100, redesign 효과)
- answerable / inference 추가 회복 (V2 가 답을 단순화 시키면 yes/no
  lead matcher 더 작동)
- 결과 양호 시 V2 default flip 후속 PR + mixtral PM-14 retry

### Scope 외 (cycle β)

- (c2) synth draft 메타 cue (planner sub-task leak / NATURAL rule_text
  cue) 는 별도 cycle. 이번 cycle 은 reflect 차원 까지만.
- mother-platform 의 self-healing pattern: hidden defect 발견 →
  진단 → patch (band-aid) → systemic redesign → measurement 검증 →
  default flip. cap[:1000] / episodic / reflect 모두 같은 패턴.

## 24. (c2) 정밀 진단 — planner plan-prepend leak + P-1 fix (2026-06-05)

§23 V2 redesign 후에도 PM-15 28/100 메타 답 중 23/28 이 stripper
미스. 추적 결과 `pipeline_synth.generate_answer:73-84`:

```python
_plan = get_planner().plan(safe_query, user_role=user_role)
if _plan and not _plan.is_trivial():
    _steps = "\n".join(
        f"{i + 1}. {s}" for i, s in enumerate(_plan.subtasks)
    )
    system_prompt = (
        f"[추론 계획]\n{_steps}\n\n위 계획에 따라 단계별로 답변하라.\n\n"
        + system_prompt
    )
```

`JAMES_ENABLE_PLANNER=1` (루트 `.env`) 활성 → 매 query 마다 planner
가 sub-tasks 분해 → numbered list 로 `[추론 계획]` 헤더와 함께
system_prompt 앞에 prepend → **"위 계획에 따라 단계별로 답변하라"**
한국어 directive 가 모델에 step-by-step report 양식 강제. PM-13
reflect summary dump 와 정확히 일치 (`[plan] 3 subtasks: Identify
companies reported by TechCrunc / Filter the list...`).

raw e4b (no JAMES stack) PM-4 0/100 메타 vs JAMES-full 28-30/100 →
JAMES 측 prompt 결함 확정 → planner prepend 추적 → (c2) systemic
fix scope 안에 들어옴.

### P-1 fix (commit `bc2ddae`)

terse 모드에서 plan prepend skip. response_style 이 `terse` 일 때만
차단, 나머지 (NATURAL chat / 보고서) 는 byte-identical 보존:

```python
_style_is_terse = _resolve_style(response_style).name == "terse"
if not _style_is_terse:
    _plan = get_planner().plan(...)
    # ... legacy prepend
```

resolve_style 실패 시 `_style_is_terse=False` fallback (안전). Tests:
6 new (resolve_style 호출 / non-terse 가드 / 호출 순서 / fallback /
non-terse byte-identical / design rationale source anchor) — 73 + 6 =
79/79 pass.

더 systemic 한 redesign (plan 을 retrieval routing 에만 사용, model
prompt 비노출, planner.py MVP 다음 design intent) 은 cycle β scope.

## 25. PM-16 측정 + validity check — V2 효과 강력 (2026-06-05)

### 5-way 측정 매트릭스 (e4b cap=8000, 100Q)

| metric | PM-10 no-fix | PM-13 +ep-fix | PM-15 +stripper | **PM-16 +V2** | PM-17 +V2+P-1 |
|---|---|---|---|---|---|
| primary | 0.480 | 0.410 | 0.460 | **0.580** | 진행 중 |
| answerable-only | 0.347 | 0.280 | 0.333 | **0.533** | 진행 중 |
| inference | 0.800 | 0.680 | 0.760 | **0.840** | 진행 중 |
| comparison | 0.160 | 0.120 | 0.160 | **0.480** | 진행 중 |
| temporal | 0.080 | 0.040 | 0.080 | **0.280** | 진행 중 |
| null | 0.880 | 0.800 | 0.840 | 0.720 | 진행 중 |
| **meta-marker** | 38 | 30 | 28 | **3/100** | 진행 중 |

### 신뢰성 검증 (PM-16 결과의 합리성)

사용자 박은 룰들 다 trigger 후 검증:
- `feedback_n1_verdict_inflation_n3_caught` — n=100 single-shot 이라
  paired confirmation 없음. 단 axis 별 변화량 정확히 산술 일치
  (comparison Δ +0.32 = 8/25; +8 cases identifiable by qid).
- `feedback_evidence_grounded_validity_check` — 답 sample inspection
  으로 진짜 신호인지 확인.

**comparison axis 11 WIN / 3 LOSS 답 sample 확인**:

| qid | gold | PM-15 답 lead | PM-16 답 lead | 평가 |
|---|---|---|---|---|
| 27 | Yes | `### 1. Identify the monetization...` (메타) | `Yes, the two articles indicate fundamentally different monetization strategies.` | WIN 진짜 |
| 32 | Yes | `### 1. Determine if the TechCrunch...` (메타) | `Yes, the TechCrunch article suggests that Amazon's LLM is not trained on children's responses.` | WIN 진짜 |
| 33 | no | `Based on the analysis... **No**.` (lead 깊은 곳) | `No. The CNBC report on Nike's Latin America...` (lead 직접) | WIN matcher 회복 |
| 47 | Yes | (lead 깊은 곳 Yes) | `No, only the article from The Verge...` | LOSS — 실제 잘못 답 |
| 49 | Yes | `Yes, the Yardbarker...` (정답) | `No.` (단답 잘못) | LOSS — V2 가 hallucination 유도 |
| 50 | Yes | (lead "explicitly states") | `**Step 1: Determine from the CBSSports.com...**` | LOSS — 1/100 잔존 메타 |

**verdict**: **결과 진짜.** measurement artifact 아님. V2 가 답 lead 에
yes/no 를 두는 양식 활성화 → matcher 정확히 작동. LOSS 3개 = 예측
가능한 tradeoff (1 hallucination + 1 노이즈 + 1 잔존 메타).

### V2 가 (c2) planner-leak 까지 흡수한 이유

PM-16 은 P-1 미적용 (planner 여전히 활성, plan prepend 됨). 그런데도
meta marker 28→3. 원인 가설:

- PM-15: synth draft 가 `### Step 1:` 양식 → critique pass 가 "Missing
  core" 지적 → revise pass 가 critique 본문 봄 → critique 안에 있는
  `### Step 1:` 양식을 critic 하면서 revise 가 다시 `### Step 1:`
  양식으로 답을 *강화* (양식 echo loop)
- PM-16 V2: critique 비노출 → revise 가 "fresh answer 작성" framing →
  synth draft 양식 안 따라가고 깨끗한 새 답 작성 → planner-leak 양식
  까지 흡수

즉 V2 가 reflect-revise leak 뿐 아니라 **synth draft → critique echo
→ revise 강화** 의 incident chain 까지 차단. P-1 (PM-17) 은 추가 마진
만 줄 가능성.

### answerable 0.533 의 의미

raw e4b answerable-only = 0.39 (PM-4 vanilla RAG). PM-16 = 0.533. **JAMES
스택이 raw 초과 — V2 활성 시 처음.** §11 결론 (스택이 답 죽이고 회피
살림) 의 정밀한 정정: **스택의 reflect engine 만 답을 죽이고 있었음**.
V2 가 그 사망 메커니즘 차단 → 스택의 진짜 가치 (retrieval rerank +
graph) 드러남.

### Honest framing (cycle 마감 톤 정렬)

- **claim**: V2 가 reflect-revise 메타 양식 + synth draft echo 강화
  을 한 번에 차단해 answerable 0.347→0.533 (n=100 single-shot)
- **caveat 1**: n=1 single-shot 이라 paired n=3 confirm 필요 (over-claim
  방지). 단 axis 별 산술 일치 + 답 inspection 신뢰성 ↑.
- **caveat 2**: null −0.12 tradeoff. 적용 시 design 결정 필요 (cap
  default 결정 패턴).
- **caveat 3**: mixtral 모델 무관성 미확인. PM-14 redo 필요.
- **이번 cycle 의 가장 큰 finding**: cap[:1000] discovery 만큼 큰
  systemic platform defect. 단 cycle β 진입 정당화 보다는 **이번 cycle
  안에서 P-1 + V2 둘 다 land + design 결정** 까지 마무리.

### 진행 매트릭스 (작업 과정 기록)

| Phase | 발견 | Fix | 효과 | commit |
|---|---|---|---|---|
| 0 (어제) | cap[:1000] truncation | env-gate JAMES_SYNTH_CONTEXT_CHARS | answerable +0.057, inference +0.24 | eb871c3 |
| 1 (오전) | episodic critique drift 가설 | per-query session (runner-side) | -0.07 primary (가설 부분 기각) | af1b529 + ba938bc |
| 2a | temporal drift origin 추적 | — (진단만) | (c)/(c1)/(c2) 분기 발견 | (uncommitted, §22) |
| 2b | reflect critique→revise + stripper 부족 (c1) | stripper 5 패턴 + REVISE_PROMPT_EN 확장 | +0.05 axis, meta 30→28 | 2d96192 |
| 2c | reflect critique-노출 자체 결함 (systemic c1) | Option B V2 prompt + env-gate | meta 28→3 (-92%), answerable 0.333→0.533 | 9ed1af7 |
| 2d | planner plan-prepend leak (c2) | terse-mode skip + tests | 측정 PM-17 진행 중 | bc2ddae |
| 3 (대기) | PM-17 결과 + mixtral PM-14 retry + 종합 verdict + design 결정 | — | — | — |

## 19. 최종 verdict matrix (PM-12 완료 후 마감)

PM-12 (mixtral + fix cap=8000, 100Q) 결과로 6칸 매트릭스 완성. 핵심 verdict:

| 구성 | primary | answerable-only | inference | comparison | temporal | null |
|---|---|---|---|---|---|---|
| paper-Mixtral | 0.32 | — | — | — | — | — |
| RAW e4b | 0.52 | 0.39 | 0.60 | 0.40 | 0.16 | 0.92 |
| full e4b cap1000 | 0.45 | 0.293 | 0.56 | 0.12 | 0.20 | 0.92 |
| **full+fix e4b cap8000** | **0.48** | **0.347** | **0.80** | 0.16 | 0.08 | 0.88 |
| RAW mixtral | 0.55 | **0.65** | 0.92 | 0.72 | 0.32 | 0.24 |
| full mixtral cap1000 | 0.46 | 0.29 | 0.56 | 0.20 | 0.12 | 0.96 |
| **full+fix mixtral cap8000 (PM-12)** | _대기_ | _대기_ | _대기_ | _대기_ | _대기_ | _대기_ |

(PM-12 partial 40Q 부분 결과: primary 0.525, inference 0.80, comparison 0.067
— inference에서 e4b+fix와 동일하면 "fix 후 모델 무관성 유지" 추가 확증.
comparison/temporal/null 미측정 → 재실행 진행 중, 결과 대기.)

### verdict 후보 (PM-12로 분기)

- **case A — mixtral+fix가 raw mixtral answerable(0.65)에 근접 + null 유지(≥0.88)**:
  "raw 답변력 + full 회피력 동시 달성" 확정. JAMES 스택의 진짜 가치 입증
  (자신만만 모델 환각 억제 + 답변력 보존). default 변경 적극 권고 (8000).
- **case B — mixtral+fix가 e4b+fix와 비슷 (answerable ~0.30대 천장)**:
  cap-fix는 inference 풀어주지만 yes/no 합성에선 스택이 여전히 답을 죽임.
  추가 stage 진단 필요(synth 프롬프트 추가 cut 또는 reflect/verify의 yes/no
  특이성). default 변경은 e4b 근거로만 정당화 (보수적).
- **case C — partial 40Q comparison 0.067이 100Q에서도 유지**:
  cap8000이 mixtral comparison을 해침 (e4b temporal과 동일 양식 drift 패턴
  mixtral comparison에도). default 권고 = 4000 (knee 보수치).

### default 권고 (예비, PM-12 후 확정)

권고 = **`JAMES_SYNTH_CONTEXT_CHARS` default 1000 → 4000 또는 8000으로 상향**.

| 후보 | 근거 | 위험 |
|---|---|---|
| 8000 | e4b answerable +0.057, inference +0.24, null −0.04 (floor 유지) | latency 증가 (프롬프트 7k자 더), e4b temporal drift |
| 4000 | answerable +0.027, inference +0.20, null −0.04 (knee 직전) | 8000 대비 answerable 0.027 손실 |
| 1000 유지 | byte-identical, 위험 0 | **장기 platform 버그 그대로 — production 답변 품질 ↓** |

- production 변경은 사용자 확정 필수 (mother-platform 영향).
- 적용 시 별도 PR + Quality Delta Card (intent axis = "multi-hop reasoning
  unlock" + regression axis = latency/null) + ROADMAP 등재.
- 측정 워크플로우는 env-gate로 이미 가능 — default 변경은 production 사용자
  편익 결정.
