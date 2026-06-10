<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-evidence-grounded-validity-check
description: 2026-06-04 Stage 4b 측정 invalidation catch (5번째 본질 catch). evidence-grounded measurement 비교 전 (1) evidence 실제 전달됐는지 (2) LLM 학습-지식-leak 가능성 분리 의무. fixture가 LLM 학습 분포에 포함됐을 가능성 항상 check.
metadata:
  node_type: memory
  type: feedback
  originSessionId: bc92b2b9-7664-4935-ae35-9d050e1b974a
---

# Evidence-Grounded Measurement Validity Check (2026-06-04)

## 사건 — 5번째 본질 catch

Stage 4b (C_minus × M_CLOUD × N=1) 결과를 "사용자 가설 입증" framing 직전. 사용자 catch:
1. "그 내부자료들이 클로드한테도 제시됬나"
2. "클로드가 작은모델을 불러온거아닌지 의심"

확인 결과:
- **Stage 4 (cloud + JAMES)**: sources=3, graph_paths=18-46, evidence 정상 전달
- **Stage 4b (cloud raw, C_minus)**: sources=0, graph_paths=0 → evidence 없음 + Cloud는 **자체 학습 지식**으로 답 ("Sam Bankman-Fried", "Trump", "Sam Altman" 등 실명 직답)
- multihop_rag fixture = 2023년 뉴스 (FTX trial, Trump apartment, Altman ouster 등) → **Claude 학습 데이터 포함 거의 확실**
- Cloud model = Opus 4.7 1M context (메인) + Haiku 4.5 (보조 router/classifier)

→ Stage 4b의 graded 0.347은 "cloud raw reasoning power"가 아니라 **"Cloud의 학습 지식 recall"** 측정. JAMES evidence-grounded design과 apple-to-orange. 비교 invalid.

## 근본 원인

evidence-grounded measurement (RAG quality)를 비교할 때 두 confound 분리 안 했음:

| Confound | 정의 | 영향 |
|---|---|---|
| Evidence 전달 누락 | 한 모드는 evidence 받음, 다른 모드는 못 받음 → 비교 unfair | "JAMES 부담" framing 오류 trigger |
| LLM 학습-지식-leak | fixture가 LLM 학습 분포에 포함된 정답 → no-evidence 모드도 답 가능 → fair-RAG 측정 invalid | "cloud raw가 reasoning 잘함" 오류 framing |

Stage 4b는 둘 다 발현 — sources=0 (evidence 없음) + multihop_rag = 2023 뉴스 (학습 분포 안). 그래서 "cloud raw 0.347 > cloud+JAMES 0.29" framing이 fair 가설 검증 아니었음.

## How to apply

**룰 — evidence-grounded measurement 비교 전 의무 체크:**

1. **Evidence 전달 확인**: 비교하는 모든 모드가 같은 evidence를 받았나? 받지 않은 모드가 있다면 = comparable 차원 아님.
   ```python
   # bench JSON에서 sources / graph_paths_count로 검증
   for r in bench['results'][:3]:
       print(r['sources'], r['graph_paths_count'])
   ```

2. **LLM 학습-지식-leak 가능성 분리**: fixture의 정답이 LLM 학습 분포에 포함될 가능성 있나?
   - 영어 + 2023년 이전 well-known event (FTX, Trump, Altman 등) = 거의 확실 leak
   - 한국어 + 도메인-specific + 후속 사건 = leak 가능성 낮음
   - synthetic fixture / 미공개 corpus = leak 없음 (gold standard)
   - leak 있는 fixture로 no-evidence 모드 측정하면 = "model knowledge recall" 측정이지 "reasoning capability" 측정 아님

3. **두 confound 분리 design**:
   - "model reasoning capability" 측정 = leak-free fixture + evidence 동등 전달
   - "RAG layer 효과" 측정 = same model + evidence with/without
   - "model + RAG 통합 효과" 측정 = leak-controlled fixture + 모든 모드 evidence 동등 전달

**룰 violation 신호 (이번 case):**
- 비교 모드 중 하나는 sources=0, 다른 하나는 sources>0
- fixture가 well-known event / known data 포함
- LLM이 evidence 없이도 specific 실명/숫자 직답
- "가설 입증" framing이 너무 깨끗하게 떨어짐 (학습 지식 confound 의심)

## 운영 체크리스트 (evidence-grounded 비교 시)

1. [ ] 비교하는 모든 mode의 evidence 전달 같은지 sources/graph_paths_count 확인
2. [ ] fixture가 LLM 학습 분포 leak 가능성 평가 (event date, language, specificity)
3. [ ] no-evidence 모드 답이 specific 실명/숫자/날짜 포함 → 학습 지식 confound 의심
4. [ ] verdict 결론 전 "fair 비교 차원인가" 자문
5. [ ] leak 있는 fixture로 raw mode 측정 = invalid 결과 박음 (이번 Stage 4b)

## 측정-side rule 체계 (이번 catch 박힌 후)

| 룰 | 적용 단계 | catch # |
|---|---|---|
| [[feedback_methodological_chain_before_plan]] | plan 짜기 전 (4질문) | catch 1-3 |
| [[feedback_fixture_fitness_before_verdict]] | 측정 결과 verdict 해석 전 | catch 4 |
| **본 룰 — evidence-grounded validity check** | **비교 분석 전 (evidence 전달 + 학습-지식-leak 분리)** | **catch 5** |
| [[feedback_n1_verdict_inflation_n3_caught]] | n=1 → n=3 paired 전 | 일반 |
| [[feedback_finding_size_honest_framing]] | verdict / closure framing | 일반 |

## 이번 cycle 적용

- **Stage 4b 결과 (graded 0.347, 사용자 가설 입증 framing) = invalid**. cloud 학습 지식 confound로 fair 비교 아님.
- **valid 비교 = Stage 4 Run 1만**: cloud + JAMES + Opus 4.7 (0.29) vs local + JAMES + gemma4:e4b (0.327) → Δ -0.037, evidence-grounded comparison. n=1 caveat.
- 사용자 가설 (JAMES가 cloud에 부담)의 **fair 검증은 leak-controlled fixture + evidence 동등 전달**로 별도 측정 필요. 이번 cycle 안에서 안 됨.

## 관련

- [[feedback_methodological_chain_before_plan]] — 본 룰은 그 4질문의 measurement-validity 측면 확장
- [[project_direction_alpha_local_vs_cloud_quality_thread]] — 측정 결과 박힌 곳 (정정 의무)
- [[feedback_alpha6_findings_mostly_known_to_literature]] — "RAG hurts capable LLM" 학계 기지 패턴 (Stage 4b 결과 우연한 합치였을 수도)
