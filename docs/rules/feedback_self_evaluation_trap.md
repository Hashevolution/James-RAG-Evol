<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-self-evaluation-trap
description: "2026-06-06 PM 사용자 catch — JAMES 가 자기 fixture + 자기 oracle 로 자기 답 채점하면 'self-eval 함정'. 학계 / publication / v0.5 D2 게이트 evidence 가치 ⭐ trivial. 진짜 evidence path = 외부 표준 벤치 (RGB / ALCE / MuSiQue / 2Wiki). cycle β #3 NATURAL-grade oracle skip 결정 evidence."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 10f0ecbb-1aa0-473e-8a59-a77d7786695f
---

# Self-evaluation 함정 (2026-06-06 PM 사용자 catch)

cycle β #3 (NATURAL-grade oracle) 진입 직전 사용자 catch:

> "이 도구를 만들어서 채점하더라도 외부에 객관적으로 평가받을 수
>  있는 테스트 셋이 되어야 제대로 어필되지 않나? 자메스 자체 기준
>  도구면 인정받기 힘들것 같은데"

## 사건

cycle β #3 의 원래 design = JAMES NATURAL 답 양식의 multi-axis quality
oracle (LLM-judge 또는 graded extension). 자기 fixture (내부 multihop
or NATURAL fixture) + 자기 oracle (LLM-judge) 로 자기 답 채점.

사용자 catch = **self-evaluation 함정**:
- 자기 fixture + 자기 채점 = "엄마 100점이야!" 패턴
- 학계 / publication / D2 게이트 evidence 가치 ⭐ trivial
- 외부 인정 어려움

## Why

### Test set + scoring authority 가 evidence 의 진짜 source

| Test 유형 | Authority | 학계 인정 |
|---|---|---|
| 외부 표준 벤치 (MultiHop-RAG / RGB / ALCE / MuSiQue / 2Wiki) | 학자 fixture + 표준 채점 (NLI / official scorer) | ⭐⭐⭐ 인정 |
| **JAMES self-oracle** (cycle β #3) | JAMES fixture + JAMES LLM-judge | **⭐ 인정 어려움** |

→ JAMES 가 자체 manuwell 한 oracle 로 자기 답 채점 = framing 으로
어떤 점수든 가능. publication / D2 evidence 무관.

### Cycle γ 가 진짜 publication-grade evidence path

| 외부 벤치 | 표준 채점 | 출처 |
|---|---|---|
| MultiHop-RAG (이미 사용) | `score_paper_aligned_accuracy` (paper 표준) | Tang & Yang 2024 EMNLP |
| RGB | Negative rejection F1 자동 채점 | Chen et al. 2024 EMNLP |
| ALCE | **NLI-based** citation precision/recall (Roberta-NLI) | Gao et al. 2023 |
| MuSiQue | EM / F1 / support fact 표준 | Trivedi et al. 2022 |
| 2WikiMultiHopQA | EM / F1 / support fact 표준 | Ho et al. 2020 |

→ cycle γ = JAMES 가 외부 표준 위에서 정량 점수. publication-grade +
v0.5 D2 게이트 + mid-June joint piece 모두 충족.

### Cycle β #3 의 ALCE prerequisite 차원 무관

원래 cycle γ design memo §7 = "cycle β #3 = ALCE long-form citation
채점 prerequisite". 단 사용자 catch 후 정정:
- ALCE 표준 채점 = **NLI-based 자동** (Roberta-NLI), JAMES self-oracle
  과 다른 stack
- cycle γ ALCE = official ALCE evaluation library 사용 (HuggingFace
  NLI model)
- JAMES 자체 LLM-judge 무관

→ cycle β #3 = cycle γ prerequisite 아님 ✅ (정정).

## How to apply

### 새 측정 / oracle 작업 진입 시 의무 4 질문

1. **Test set authority**: 학자 (외부 벤치) 또는 JAMES (self-fixture)?
2. **Scoring authority**: 표준 채점 (NLI / official scorer) 또는
   JAMES (self-LLM-judge)?
3. **Authority 둘 다 self?** → ⭐ trivial publication / D2 evidence
   가치
4. **외부 인정 필요?** → 외부 벤치 + 표준 채점 path 우선

### Self-eval 작업의 진짜 가치 명시

| 차원 | self-eval 가치 |
|---|---|
| Publication evidence | ⭐ trivial |
| v0.5 D2 게이트 evidence | ⭐ trivial |
| Production UX internal validation | ⭐⭐ partial |
| Cycle γ prerequisite | ❌ 무관 (외부 표준 채점 사용 시) |

→ self-eval 작업은 **internal validation 만** 가치. publication /
학계 / D2 evidence 는 외부 벤치만.

### Cycle β #3 skip 결정 (2026-06-06 PM)

Path 1 sequence 재정정:
- ~~4. cycle β #3 (NATURAL-grade oracle)~~ skip
- 4. v0.4.2 T5 (Replayable Audit Graph full) 직행
- 5. Cycle γ (4 외부 벤치)
- 6. v0.5 진입 게이트 평가

cost 절감 4-8h + sequence 단순화 + publication evidence path 직접.

## Mother-platform philosophy 정합

| 원칙 | self-eval 함정 catch 의 정합 |
|---|---|
| 원칙 1 (옵션형 거둬내기 + 다이얼 조정) | self-eval = JAMES 가 다이얼 직접 조정 가능 = 측정 의도 위반 |
| 원칙 5 (NATURAL 지장 없는 개선) | self-eval framework 없이도 cycle γ 외부 벤치 위 NATURAL 양식 답 평가 가능 |
| **honest framing rule** ([[feedback-finding-size-honest-framing]]) | self-eval = self-fitting 직접 가능, honest framing rule 위반 risk |
| **Layer B framework comparison** ([[feedback-layer-b-framework-comparison-value]]) | 외부 framework comparison 가치 = self-eval 와 정반대 dimension |

## 관련 메모

- [[feedback-finding-size-honest-framing]] — self-eval = self-fitting
  의 직접 가능, honest framing rule 의 직접 적용
- [[feedback-layer-b-framework-comparison-value]] — Layer B/C/D/E
  framework comparison = 외부 evidence path 의 일관
- [[feedback-design-planned-infra-before-cycle-gamma]] — cycle γ 진입
  전 audit. self-eval 함정 = cycle β #3 skip 결정의 evidence
- [[feedback-mother-platform-6-principles]] — 6 원칙 의 외부 framework
  차원 = self-eval 와 정반대
- [[feedback-james-vanilla-definition]] — 좁은/넓은 정의 = JAMES self-
  fixture 측정. 단 paper baseline + 표준 채점 (Tang & Yang 2024 EMNLP)
  = 외부 표준 정합
- [[feedback-fixture-fitness-before-verdict]] — fixture role 명시
  의무. self-eval fixture 의 fitness 약함

## Cycle β #3 의 대안 path (사용자 catch 후 결정)

| 작업 | 가치 path |
|---|---|
| Production NATURAL UX evidence | cycle γ ALCE / RGB / MuSiQue / 2Wiki 의 NATURAL 양식 답 측정 |
| v0.5 D2 게이트 evidence | cycle γ 4 벤치 cross-bench validation |
| Mid-June joint piece evidence | cycle γ cross-bench + Robin/Ali 외부 평가 |
| Real production 사용자 feedback | v0.5 도메인 pilot 시 실 사용자 평가 |

→ cycle β #3 의 의도 모두 외부 path 로 충족. self-eval 함정 회피.
