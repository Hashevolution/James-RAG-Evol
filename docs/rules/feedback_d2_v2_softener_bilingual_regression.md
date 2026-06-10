<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-d2-v2-softener-bilingual-regression
description: "D2 V2 (JAMES_SOFTENER_BILINGUAL=1) 단순 영어 trigger 확장 측정 결과 F1 -0.111 regression. 사용자 catch 2026-06-09: 'Korean-only 정당' framing → JAMES 가 Korean-only 시스템 아님. 8번째 catch (measurement-driven + 사용자-driven 결합). 영어 softener = design 결함, V2 implementation 은 wrong fix. 다음 path: V3 directive retry / V4 selective trigger 또는 D1 retrieval pivot."
metadata:
  type: feedback
  originSessionId: 2026-06-08-d2-v2-bilingual-regression
---

## ⚠️ 2026-06-09 정정 — 9번째 catch 로 framing expand

이 룰의 결론 "Korean-only design 가 옳지 않음" 은 **under-claim 방향 too narrow** 였음. 9번째 catch ([[feedback_james_identity_measurement_driven]]) 가 정정:

**진짜 결론**:
- 영어 softener = JAMES 의 cross-lingual identity 의 **현재 design gap = fundamental defect**
- V2 = 잘못된 fix, but 영어 softener 자체 design 필요 = **cycle β code 변경 의무 candidate**
- "V3 / V4 후 D1 으로 pivot" sequence 도 over-conservative 였음 — 영어 softener 가 fundamental defect 면 D1 와 별도로 fix 의무

JAMES = cross-lingual 시스템 → 영어 softener 작동 안 함 = 그 자체로 fundamental defect (현재 production). 측정 정당화되면 cycle β code 변경 의무, 다른 작업 priority 와 별개.

## 규칙 (정정 후)

**JAMES softener bilingual 확장 시 Korean retry pattern 단순 영어로 복사 금지.** 한국어 모델 (over-confident) 과 영어 모델 (이미 abstain 잘함) 의 baseline 행동 다름. 같은 retry prompt ("respond naturally") 가 정반대 효과:
- 한국어 → over-confidence 부드러워짐 ✅
- 영어 → 이미 abstain 한 것 destabilize → hallucination ❌

**단**: V2 패턴 reject 가 "영어 softener 폐기" 아님. **영어용 design 필요** (V3 directive retry / V4 selective trigger / 또는 다른 mechanism).

**Why:**
- D2 V2 측정 = JAMES_SOFTENER_BILINGUAL=1, mxtral n=25 RGB-en negrej
- F1 -0.111 regression (set 6→4, lost {9, 18})
- Q9 retry: "Insufficient information..." → "The provided context does not list..." (semantic abstention but scorer pattern miss)
- Q18 retry: "Insufficient information" → "American students will begin taking the digital SAT..." (full hallucinate)
- Root cause: "respond naturally" cue 가 영어 모델에 "다시 시도해" 로 해석

**How to apply:**

### 영어 softener 재시도 시

- ❌ Korean retry prompt 영어 번역만 = V2 패턴 재현, regression 위험
- ✅ 영어 retry = **directive abstention reinforcement**:
  > "If the provided context does not contain the information needed to answer, respond with exactly: 'Insufficient information.' Do not try to infer or guess."
- ✅ 또는 selective trigger — 이미 abstain 형식 답변엔 retry 안 함
- 측정 의무 — V2 같은 단순 확장 측정 없이 default ON 금지

### Cross-lingual JAMES 룰 박힘

JAMES = cross-lingual 시스템 (KO + EN + 미래 다른 언어). Korean-only component 발견 시:
- "Korean-only 가 옳음" 결론 X (over-narrow)
- "현재 component 가 language-specific design, 다른 언어용 별도 design 필요" ✅
- 다른 언어 사용자 경험 = 의식적 우선순위 결정 사항

## 사례 — 2026-06-08 D2 V2 측정 + 사용자 catch

### V1 → V2 hypothesis (실패)

V1 (현재 production):
- Softener trigger = Korean strings only (`자료에 없음...` 등)
- 영어 query → trigger 안 fires → softener 작동 0
- Phase D 측정 = abst_f1 -0.054 from DISABLE_ABSTENTION (small, mostly mxtral sampling noise)

V2 hypothesis: "Bilingual trigger 추가하면 영어 softener 도 작동, lift 가능"
- Trigger 에 영어 추가 (RGB scorer _ABSTENTION_EN mirror)
- Retry prompt 도 영어 ("Follow the guide... respond naturally")

V2 측정 (mxtral n=25 negrej):
- F1 0.276 (vs R0 0.387)
- **-0.111 regression** (2 queries lost, 0 gained)

### 8번째 catch — 사용자 2026-06-09

사용자 question: "자메스를 한국어 only로 한다는 말?"

내 framing 결함:
- ❌ "V2 regression → Korean-only design 정당" (over-narrow)
- ✅ "V2 implementation 결함, 영어 softener = design gap, 다른 mechanism 필요"

JAMES 가 cross-lingual 시스템임을 명확히 — Korean-only 결론은 영어 사용자 포기 의미. 그건 결정한 적 없음.

## 8번째 catch 의 unique 성격

이전 catches:
1-7: 사용자-driven (framing over-reach 직전 catch)

8번째: **measurement-driven + 사용자-driven 결합**:
- 측정값 (-0.111) 자체가 V2 hypothesis 부정 (measurement-driven)
- "Korean-only 정당" 결론 사용자 catch (사용자-driven)
- 두 catch 종류 결합 첫 사례

## 다음 path 옵션 (이 룰 박힘 후)

| Path | 설명 | 예상 |
|---|---|---|
| V3 | Directive English retry ("Respond with exactly 'Insufficient information.'") | -0.111 사라짐 + 작은 lift |
| V4 | Selective trigger (이미 abstain 형식이면 retry 안 함) | 더 복잡, 2-3 PR |
| D1 pivot | Retrieval 강화 (Phase D 가 보여준 5/6 lever) | 모든 axis 동시 향상 |

권장 (2026-06-08 사용자 결정): **D1 pivot (Path 다)**. D2 자체가 작은 lever, D1 가 진짜 ROI. V3/V4 는 D1 결과 후 재고.

## 관련

- [[feedback_path_d_james_not_specialty_verifier]] — 7번째 catch, Path D positioning
- [[feedback_single_axis_ablation_misframing]] — 6번째 catch, axis-misalignment
- [[mechanism_layer_intent_axis_alignment]] — α-5 mother rule
- [[feedback_finding_size_honest_framing]] — 일반 over-claim 룰
- PR #746 — D2 V2 코드 + tests + measurement 영구 기록
- `docs/handovers/v0.4-cycle-gamma-phase-d-results-2026-06-08.md` — Phase D handover (D2 의 6th catch 의 후속)
