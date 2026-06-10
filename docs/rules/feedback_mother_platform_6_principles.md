<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-mother-platform-6-principles
description: "JAMES 평가 design 의 6 원칙 (Default vs Option 분리, NATURAL 지장 없는 개선 Default 인정, IntentClassifier 단답 auto-selection). 단답 metric over-claim 거부 + multi-axis Default 평가 + auto-adaptive default 의 framework. cycle β 이후 모든 fix 의 평가 기준."
metadata:
  node_type: memory
  type: feedback
  originSessionId: a886e7a2-391e-45b4-a087-3c2e232a5837
---

JAMES 평가 design 의 핵심 원칙 6 개 — 2026-06-05 cycle (cap[:1000] +
reflect critique-노출 + planner plan-prepend) 마감 시 사용자 통찰로
정립.

## 6 원칙

1. **코드 끼워 맞춘 옵션형 거둬내기 + 추론 다이얼 조정 = 올바른 방향**
   적용: cap[:1000] 같은 hardcoded 결함 → env-gate + default flip.
   stripper 같은 결함 사후 정화도 Default.

2. **평가 metric 맞춘 단답 specific 구조 추가 = 틀린 방향**
   NATURAL 답을 차단하는 극단 다이얼도 NO. V2 같이 critique 비노출로
   답을 단답에 강제하면 graded (multi-fact) 약화 = 원칙 2 위반.

3. **단답 needed 시 specific 옵션 layer 로 setting**
   V2 = env-gate OFF default. P-1 = terse 가드 conditional. 사용자가
   명시 활성 시만.

4. **기존 옵션형 코드 → 사용자 답변 방식 옵션으로 setting**
   NATURAL rule_text 보고서 양식 강제 / planner directive / persona
   directives 등도 사용자 선택 옵션 layer 로 이동 (cycle β scope).

5. **NATURAL 답에 지장 없는 개선 = Default 인정**
   multi-axis (primary + graded + abst_F1) 모두 ↑ 또는 NATURAL noise
   band 안이면 Default 통합. cap fix 와 stripper 가 정확히 이것.

6. **JAMES 가 단답 query 자동 파악 → 단답 specific 자동 장착 = Default 인정**
   IntentClassifier 가 query intent 분류 (단답 / 분석 / 사실 / 대화) →
   response_style auto-selection. 단답 query 면 V2 + P-1 자동 활성,
   분석 query 면 NATURAL 유지. V2 의 graded tradeoff 해결의 진짜 길.
   mother-platform 의 진짜 지능 = query-aware auto-adaptive default.

## 큰 그림

```
JAMES 풀스택 (지능형 Default)
├── Default 본체 = 순수 추론 + auto-adaptive 양식 선택
│   ├── 추론 layer + 다이얼 (cap, num_ctx, think mode)
│   ├── IntentClassifier (단답 / 분석 / 사실 / 대화)
│   ├── 답 양식 auto-selection ← 원칙 6
│   └── 모체 향상 = Default 점수 ↑ + NATURAL 지장 없는 개선 통합 ← 원칙 5
│
└── 옵션 layer (사용자 explicit override)
    ├── response_style="terse" / "natural" / 등
    ├── 자동 선택 무시
    └── advanced / 측정 / 특수 use case
```

## 단일 axis over-claim 거부

이번 cycle 의 가장 큰 lesson — V2 가 primary 0.580 (paper GPT-4 league)
이라고 framing 하면 거짓. multi-axis (graded -0.11) 까지 보면 단답
specific 옵션 layer 옵션이지 mother-platform 향상 아님.

평가 의미는 단일 metric 변화가 아니라 **Default 자체의 다축 점수
변화**. 단축 over-claim 은 평가-fitting (원칙 2 위반).

## Why: 평가 design 의 mother-platform philosophy

JAMES 가 "v1.0 까지 mother-hardening" 인데 평가 방식이 use-case-specific
optimization 으로 가면 mother-platform 의미 사라짐. Default 가 모든
use case 에서 합리적 성능 = 진짜 모체 강함. Option layer = use case
tuning. 두 layer 분리가 평가 정합성의 핵심.

원칙 6 (auto-selection) 이 그 분리의 진화형 — 사용자가 옵션 명시 안
해도 query intent 인식 → 적절한 옵션 자동 mount → UX 자연 + Default
의미 보존.

## How to apply

새 fix 평가 시 5 질문:
1. NATURAL 답에 지장 있나? (graded / 다축 검증)
2. 단축 metric 만 ↑ 인 평가-fitting 아닌가?
3. 다축 모두 ↑ 또는 NATURAL noise band 안이면 → Default
4. 단답 specific 효과면 → 옵션 layer
5. 자동 인식 가능하면 → cycle β IntentClassifier 통합

연결 메모:
- [[feedback-finding-size-honest-framing]] — 단일 metric over-claim 거부
  rule. 6 원칙 의 원칙 2 와 정합.
- [[feedback-fixture-fitness-before-verdict]] — fixture 가 verdict-grade
  인지 확인. 단답 fixture 는 단축 만 측정.
- [[feedback-evidence-grounded-validity-check]] — 답 sample inspection
  으로 신뢰성. 원칙 5 (NATURAL 영향) 검증에도 적용.

## 적용 사례 (2026-06-05 cycle)

| Fix | 원칙 매핑 | Default? |
|---|---|---|
| cap[:1000] → 8000 (PR-A) | 1 + 5 (다이얼 + 다축 ↑) | ✅ Default flip |
| stripper 확장 | 1 + 5 (결함 정화 + NATURAL noise band) | ✅ Default |
| V2 critique 비노출 | 3 (단답 specific) | ❌ env-gate OFF, cycle β 6 통합 후보 |
| P-1 planner skip | 3 (단답 specific) | ❌ terse conditional |
| per-query session | 측정 isolation | ❌ runner-only |

## Cycle β scope (6 원칙 후속, 의무)

1. **NATURAL-grade oracle 신설** — 원칙 5 검증 인프라 (이후 self-eval trap catch 로 skip 결정)
2. **IntentClassifier → response_style auto-selection** — 원칙 6 구현
3. **기존 옵션형 코드 옵션화** — 원칙 4 확장
4. **Hidden defect audit (cap[:1000] 패턴 N개)** — 원칙 1 확장

cycle β 진입 결정 시 이 메모 + 6 원칙 의무 reading.
