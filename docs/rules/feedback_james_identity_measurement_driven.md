<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-james-identity-measurement-driven
description: "JAMES 정체성 = ongoing measurement-driven discovery process. Cycle β code snapshot 은 '지금까지의 발견' 표현, 영구 invariant 아님. 사이클 γ 가 fundamental defect 발견 시 cycle β code 도 변경 의무. Path D / cycle β / mother platform 모두 measurement evidence conditional. 사용자 catch 2026-06-09: '사이클 베타 이후를 정체성으로 삼는것이 맞는가? ... 아직은 자메스의 정체성과 성능을 측정을 통해 찾아가는중'. 9번째 catch = framing under-claim 정정 (1-8 catches over-claim narrowing 의 mirror)."
metadata:
  type: feedback
  originSessionId: 2026-06-09-james-identity-measurement-driven
---

## 규칙

**JAMES 정체성은 measurement-driven discovery process 결과, snapshot lock 아님.** Cycle β / cycle γ / mother platform / Path D 등 모든 framing 은 **measurement evidence conditional**:

- ✅ "지금까지 측정으로 발견된 JAMES 의 모습"
- ❌ "JAMES 의 영구 정체성"

**Why:**

이 룰은 1-8번째 catches 의 mirror correction:

- **1-8 catches** = framing **over-claim** narrowing (publication 직전 over-reach 막기)
- **9번째 catch** = framing **under-claim** 정정 (over-conservative lock-in 막기)

1-8 catches 가 "JAMES 가 무엇인지 너무 broad 하게 주장 X" 룰 박았다면:
9번째 catch = "JAMES 가 무엇인지 너무 narrow 하게 가둠도 X" 룰

정확한 framing 위치:
- 너무 broad (e.g. "JAMES universal abstention oracle") → 1-8 narrow 방향
- 너무 narrow (e.g. "Cycle β code = 영구 invariant") → 9th expand 방향
- **정확한 위치 = ongoing measurement-driven discovery, equilibrium dynamic**

## 사용자 catch 원문 (2026-06-09)

> "사이클 베타 이후를 정체성으로 삼는것이 맞는가? 사이클 감마에서 자메스의 본질적 잘못이 나오면 고치긴해야지. 아직은 자메스의 정체성과 성능을 측정을 통해 찾아가는중"

→ Path D + cycle β invariance framing 이 over-protective. 사이클 γ 가 발견하는 fundamental defects = JAMES 변경 의무 source, lock 대상 아님.

## How to apply

### Path D (7번째 rule) 정정

이전 framing:
- "JAMES = full-RAG + replayable audit 카테고리, HALT-RAG 안 따라감"
- "abst_f1 단일 axis 추격 금지"
- "Cycle β code = 영구 invariant"

정정 framing:
- "JAMES = 측정으로 정의되는 시스템, **measurement evidence 가 정당화하면 architectural pivot OK**"
- "axis-misaligned cherry-picking 금지, multi-axis Pareto 후 evidence-driven 변경은 OK"
- "Cycle β code = 현재 production snapshot, 측정 결과 defect 가리키면 변경 가능 + 의무"

### Phase D speculative finding 재해석

이전 (over-protective):
> "rerank/typed_filter/cog_stages +0.050 = axis-misaligned, defect evidence 아님. multi-axis 측정 필요 (별도 cycle)"

정정 (measurement-driven):
> "rerank/typed_filter/cog_stages +0.050 = **multi-axis 측정 prerequisite**. Phase E 가 사실상 **의무 작업**. 측정 결과 net positive 면 fundamental defect → 변경 의무. measurement 회피 X."

### D2 V2 finding 재해석

이전:
> "Korean-only design 가 옳지 않음. V3/V4 가능하지만 D1 lever 큼"

정정:
> "영어 softener = JAMES 의 cross-lingual identity 의 **현재 design gap = fundamental defect**. V3/V4 측정 + 정당화되면 cycle β code 변경 의무. JAMES 가 cross-lingual 이라면 영어 softener 도 제대로 되어야 = 평등 부분"

### D1 변경 시 cycle β regression check

이전 (over-protective gate):
> "D1 변경 후 cycle β 효과 사라지면 D1 변경 reject"

정정:
> "D1 변경 후 cycle β 효과 재측정 의무. **변화 자체 = 정보**. 효과 사라지는 게 D1 의 정당화 reject 가 아님, 새 발견. evidence-driven 판단."

### 새 작업 priority (1-8 narrow direction + 9th expand direction 결합)

| 작업 | 정정 priority |
|---|---|
| **D5 Phase E multi-axis ablation** | **의무** — Phase D speculative finding 검증 (별도 cycle 미루기 X) |
| **D2 V3 directive English retry** | 측정 정당화되면 cycle β code 변경 의무 |
| **D1 retrieval 강화** | 권장, cycle β 재측정 의무 |
| **D3 NLI partial integration** | 측정 정당화되면 OK (lock 아님) |
| **HALT-RAG mechanism 일부 차용** | 측정 정당화되면 고려 대상 (단 framing careful) |

## 균형 — over-claim 과 under-claim 둘 다 위험

이번 catch 의 의미 = **framing discipline 은 양방향 균형**:

- **Over-claim 방향 risk** (1-8 catches 가 막은 것):
  - publication 직전 broad 주장
  - axis-misalignment cherry-picking
  - scope creep (cycle γ → joint piece)
  - prior art ignorance
  - single-axis defect framing

- **Under-claim 방향 risk** (9번째 catch 가 막은 것):
  - 정체성 over-protective lock-in
  - "Cycle β code = 영구" framing
  - measurement evidence 가 가리키는 defect 회피
  - "Path D protects status quo" 해석
  - evolutionary discovery process 차단

**정확한 framing** = 그 사이의 dynamic equilibrium:
- broad → narrow 방향 (over-claim 막기)
- narrow → broad 방향 (over-conservative lock 막기)
- 둘 다 measurement evidence 기준

## Cycle β code 의 새 status

영구 invariant 아님:
- Persona 옵션화 = 그 당시 측정 evidence 위에 정당화
- AnswerStyleClassifier = 그 당시 측정 evidence 위에 정당화
- TERSE rule_text v4 = 그 당시 측정 evidence 위에 정당화

새 측정 evidence (cycle γ Phase D / Phase E / D1 / D2 V3 etc.) 가 이 design 들의 위치를 변경하면:
- 사라질 수도 있음 (defect 확인 시)
- 강화될 수도 있음 (다중 evidence 누적 시)
- 변형될 수도 있음 (better design 발견 시)

**Cycle β = JAMES 의 진화 중 한 layer, 영원한 base 아님**.

## Mother platform 6 원칙 status

mother platform 6 원칙 (Default vs Option 분리 등) = framework rule, content 아님:
- Rule = 영구 valid (framework 자체)
- Content (어떤 게 Default, 어떤 게 Option) = measurement-driven 변경 가능

즉 framework 보존 + content evolution = 정확한 framing.

## 누적 9 catches 의 framing geometry

```
                    Over-claim
                   (broad direction)
                          ↑
                          |
                      1, 2, 3, 4, 5, 6, 7, 8 (narrow 방향 catches)
                          |
                  정확한  |  framing
                  equilibrium ←—— 9th catch (expand 방향)
                          |
                          ↓
                  Under-claim
                 (narrow direction)
```

각 catch 가 framing 을 정확한 위치로 push:
- 1-8 = 너무 위 (broad) 에서 아래 (narrow) 로 push
- 9th = 너무 아래 (narrow) 에서 위 (broad) 로 push
- 둘 다 measurement evidence equilibrium 으로 수렴

## 관련

- [[feedback_path_d_james_not_specialty_verifier]] — 7번째 rule, 정정 대상 (over-protective framing)
- [[feedback_d2_v2_softener_bilingual_regression]] — 8번째 rule, 정정 대상 ("Korean-only 정당" framing 도 over-narrow)
- [[feedback_single_axis_ablation_misframing]] — 6번째 rule, multi-axis Pareto **의무** (별도 cycle 미루기 X)
- [[mechanism_layer_intent_axis_alignment]] — α-5 mother rule, axis 정합 (변경 reject 아님, 측정 prerequisite)
- [[feedback_finding_size_honest_framing]] — 일반 honest framing (양방향)
- [[feedback_jameses_positioning_replayable_rag]] — "Replayable RAG 는 하나의 특성, 전체 정체성 아님" 룰 정합
- PR #745, #746, #747 — 7th-8th catches 의 docs, 9th catch 가 conditional 로 만듦
