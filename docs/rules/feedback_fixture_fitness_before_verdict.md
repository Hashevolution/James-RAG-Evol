<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-fixture-fitness-before-verdict
description: "2026-06-04 Stage 3 step7 smoke 결과 over-read 패턴 catch. n=1 measurement 결과를 verdict로 해석하기 전 \"fixture가 verdict-grade인가 vs regression-check-grade인가\" 먼저 확인 의무."
metadata:
  node_type: memory
  type: feedback
  originSessionId: bc92b2b9-7664-4935-ae35-9d050e1b974a
---

# Fixture Fitness Check Before Verdict (2026-06-04 catch)

## 사건

Stage 3 smoke로 M_CLOUD × step7 (n=1, 20Q) 측정 → graded 0.38 vs baseline_2a31b20.json (step7 α-3 baseline) 0.58 → Δ = -0.20 OUTSIDE noise band → **내가 "cloud underperforms production"로 framing**.

**사용자 catch**: "이전 모델별 평가시 step7 평가를 한게 아니라, 외부 벤치 테스트로 하지않았나, 그게 맞나"

→ 맞음. `memory/alpha_5_multihop_rag_reset` 명시:
- α-5 reset (2026-05-30): 외부 벤치마크 부재 catch + MultiHop-RAG (Tang & Yang 2024) 도입
- step7 = internal regression check (강등)
- multihop_rag = primary verdict fixture

`memory/project_alpha_8_closure_state` 직접 인용:
- "Step7 (n=3 paired, n=20 queries) — **null effect, regression-free**"
- "Multihop_rag n=3 paired — **THE ACTUAL VERDICT**"

즉 step7 결과 자체로 "model X가 model Y보다 못함" verdict 내면 안 됨. step7는 "regression 들어왔나" 체크용.

## Why this trap is dangerous

1. Noise-grade fixture에서 over-read하면 잘못된 결정 trigger (이번엔 "Direction α premise 반증" framing 직전)
2. fixture-language bias가 confound로 작동 (step7 한국어 + JAMES-specific → Claude에 unfair)
3. Stage 4 더 큰 측정으로 escalate하면 같은 confound로 24-100x 비용 burn

## How to apply

**룰 — measurement 결과 보기 전:**
1. **fixture role 확인**: 이 fixture가 verdict-grade인가? regression-check-grade인가?
2. **fixture-language match 확인**: tested model의 강점 언어와 fixture 언어가 맞나?
3. **fixture-construct 확인**: tested model의 학습 분포에 fixture 케이스가 포함되나?
4. **n=1 결과는 verdict 아님**: 단일 측정 + 부적합 fixture = verdict trigger 금지

**fixture-grade 확인 source:**
- `memory/alpha_5_multihop_rag_reset` — primary verdict fixture = multihop_rag
- `memory/project_alpha_8_closure_state` — "ACTUAL VERDICT" 라벨 위치
- design memo § 측정 설계 부분 — fixture role 명시

**룰 violation 신호:**
- "n=1 결과로 OUTSIDE noise band이라 cloud가 못함" 같은 framing
- baseline 파일 = `baseline_<sha>.json` (step7 baseline only)로 multihop-grade fixture 비교
- fixture-language confound 확인 안 함

## 운영 체크리스트

1. measurement 시작 전:
   - [ ] 이 fixture가 verdict-grade인가 (메모리 확인)
   - [ ] tested model의 강점-fixture 일치 확인
   - [ ] baseline data가 이 fixture에서 측정된 값인가
2. measurement 결과 분석 전:
   - [ ] fixture role 다시 한 번
   - [ ] caveat 모든 항목 (특히 fixture bias, language match) 검토
   - [ ] n=1 시점에서 "verdict" 단어 금지

## 관련 룰

- [[feedback_finding_size_honest_framing]] — 발견 크기 honest framing (over-read 일반 룰)
- [[feedback_n1_verdict_inflation_n3_caught]] — n=1 inflation (measurement-side hygiene)
- [[feedback_alpha_cycle_discovery_loop_end]] — forced discovery hunt 종료 (over-read 트리거 패턴)
- [[alpha_5_multihop_rag_reset]] — primary verdict fixture가 multihop_rag로 이동
- [[project_alpha_8_closure_state]] — "ACTUAL VERDICT" 라벨 = multihop, step7는 regression-check
- [[feedback_measurement_smoke_caught_wiring_bugs]] — smoke가 wiring bug 잡는 룰 (이번 사건은 wiring 정상, fixture 선택 잘못)

## 이번 cycle 적용

- Stage 3 step7 smoke 결과 (Δ graded -0.20): **regression check 통과** (cloud가 step7에 unfair한 건 알려진 confound), verdict 아님
- Stage 3b multihop_rag smoke 결과 (in flight): **actual verdict 후보** — baseline = α-8 closure M_M multihop graded ≈ 0.30
- Stage 5 보고서: step7 표는 caveat 표시 (불공정 fixture), multihop 표가 메인
- Direction α premise 평가는 multihop 결과 위에서만
