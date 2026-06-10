<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-methodological-chain-before-plan
description: 2026-06-04 사용자 catch — measurement plan 짜기 전 verdict / diagnostic / regression-check / baseline 등 각 fixture / metric의 logical role을 라벨링하고 logical 의존 순서를 박지 않으면 같은 종류 catch (인수인계 fact 무시)가 반복된다. read order rule만으로 부족.
metadata:
  node_type: memory
  type: feedback
  originSessionId: bc92b2b9-7664-4935-ae35-9d050e1b974a
---

# Methodological Chain Reasoning Before Plan (2026-06-04, 핵심 룰)

## 사건

2026-06-04 한 세션 안에서 같은 종류 catch 4건:

1. "같은 9Q paired 또 돌리자" — 이전 측정 결과를 logical input으로 못 잡음
2. fixture upgrade 옵션 a/b/c — superset infra (qvt_ablation_matrix) vs ad-hoc script의 logical 우선순위 못 잡음
3. step7 → multihop 거꾸로 측정 순서 — verdict-grade vs check-grade fixture의 logical role 못 잡음
4. step7 결과 over-read — fixture role 따라 verdict 권한 다르다는 logic 못 잡음

사용자 정정: *"이전 모델별 평가시 step7 평가를 한게 아니라, 외부 벤치 테스트로 하지 않았나"* + *"꺼꾸로된게 벤치한 테스트를 먼저 돌리고 결과가 이상하다하면 스텝7 돌려서 결과가 왜 이상했다 밝히는 것"* + *"이런 실수들이 왜 계속 반복되는지 진짜 이전 과정들을 논리적으로 파악하고있어야 앞으로 개발과정이 잘되겠다"*.

## 근본 원인

단순히 "memory를 안 본 것"이 아님. 인수인계 (memory + handover + design memo)를 **fact list**로 읽지 measurement method의 **logical structure**로 안 읽음.

- fact list 읽기 = "step7 fixture가 있다 / multihop_rag fixture가 있다 / α-5에서 multihop 도입됐다"
- logical structure 읽기 = "primary verdict = multihop, regression check = step7, 따라서 verdict 측정은 multihop 먼저, 결과 이상하면 step7로 원인 분석"

후자가 빠지면 plan 짤 때 step1→step2 단순 시퀀스만 늘어놓고 각 step의 role + 의존성을 안 함. read order rule 추가만으로 안 고쳐짐.

## How to apply — 4질문 의무 (plan 짜기 전)

매 measurement / build plan 작성 전:

1. **Verdict question 무엇?** — 무엇을 결정하는 측정인가?
2. **Diagnostic question 무엇?** — verdict가 이상할 때 원인 찾는 측정인가?
3. **각 fixture / metric / data의 role 라벨링** — verdict-grade / diagnostic / regression-check / baseline / ground truth / smoke wiring check
4. **Logical 순서** — verdict 먼저, diagnostic은 verdict 결과 따라 conditional. baseline은 verdict 측정 전에 존재 의무.

답을 plan 본문 안에 명시 (한 줄씩):
```
- Verdict Q: M_CLOUD가 production M_M보다 multihop_rag (영어 multi-hop, primary verdict fixture) 에서 더 잘 푸는가?
- Diagnostic Q: verdict가 이상하면 (예: cloud underperforms 또는 over-performs 비현실적) step7 (regression check, 한국어 + JAMES-specific) 결과 보고 fixture-language confound인지 pipeline 망가짐인지 분리
- Fixture roles:
  - multihop_rag = verdict-grade (α-5 reset 이후 primary, memory `alpha_5_multihop_rag_reset`)
  - step7 = regression-check + diagnostic (α-5 reset 이후 강등, memory `project_alpha_8_closure_state`)
  - baseline_2a31b20.json = step7 baseline (verdict 비교에 부적합)
  - 비교 baseline for multihop = `qvt-ablation-cell-C_rag-{graph,ontology}-M_M.json` (α-8 n=3 paired)
- Logical 순서:
  1. multihop wiring smoke (verdict-grade fixture에서 wiring 작동 확인)
  2. multihop verdict 측정 (n=3 paired)
  3. verdict 이상하면 → step7 diagnostic (원인 분리)
  4. step7 결과로 fixture-confound 확인되면 → multihop만 verdict로 사용
```

위 명시 안 한 plan은 incomplete — push 전 반려.

## 운영 체크리스트 (매 plan 작성 시)

1. [ ] verdict question 한 줄 명시
2. [ ] diagnostic question 한 줄 명시 (없으면 명시)
3. [ ] 각 fixture / metric / baseline role 라벨링 (5 종 중 하나)
4. [ ] logical 순서 박힘 + 각 step의 의존성 명시
5. [ ] 이전 측정 결과 (memory)와의 logical 연결 명시
6. [ ] superset infra 있나 확인 (ad-hoc script 만들기 전)

체크리스트 통과 안 하면 plan 자체가 아직 미완성 — 코드 시작 금지.

## fixture / metric role 5종 정의

| Role | 정의 | 예시 |
|---|---|---|
| verdict-grade | 무엇을 결정하는 측정 | multihop_rag (α-5 이후 primary), MultiHop-RAG external benchmark |
| diagnostic | verdict 이상할 때 원인 분리 | step7 (한국어 / cross-lingual / dedup / negative 카테고리), 특정 question_type cross-tab |
| regression-check | 코드 변경이 깨뜨림 잡기 | step7, smoke run |
| baseline | verdict 비교 ground | 동일 fixture × 이전 N=3 paired cell, eval/qvt/baseline_*.json |
| smoke | wiring 살아있나 확인 | n=1 × 5Q, 1 cell × 1 tier × 1 run |

같은 fixture가 여러 role 가질 수 있음 (step7 = regression-check + diagnostic). 단 verdict-grade 라벨은 명시적 (인수인계에서 박혀있어야).

## 즉시 적용 — 이번 cycle 정정

- Stage 3 step7 smoke = 사실은 **smoke (wiring check)** + **diagnostic data 수집** 으로 재라벨 (verdict 아님)
- Stage 3b multihop_rag smoke (in flight) = **smoke (wiring check on verdict-grade fixture)**
- Stage 4 = multihop_rag × N=3 paired (verdict 측정) — step7 4a/4b 아님
- Stage 4 후 만약 multihop verdict 이상하면 → step7 + question_type cross-tab으로 diagnostic
- Stage 5 보고서 = multihop verdict 메인 표 + step7는 caveat 라벨로 부록

design memo Stage 0.2 "step7 first" 추천 = 본 룰 위반. design memo 다음 update 시 정정 의무 (verdict-grade fixture 우선 명시).

## 관련 룰

- [[feedback_finding_size_honest_framing]] — 발견 크기 framing (이번 룰은 verdict 권한 라벨링의 측면)
- [[feedback_n1_verdict_inflation_n3_caught]] — n=1 inflation (verdict 권한 + n 모두 확인 의무)
- [[feedback_fixture_fitness_before_verdict]] — fixture role 확인 룰 (본 룰의 하위 항목)
- [[feedback_alpha_cycle_discovery_loop_end]] — forced discovery hunt 종료 (logical 순서 무시하면 trigger)
- [[alpha_5_multihop_rag_reset]] — multihop_rag = primary verdict (역사적 origin)
- [[project_alpha_8_closure_state]] — "THE ACTUAL VERDICT" 라벨 (multihop)
