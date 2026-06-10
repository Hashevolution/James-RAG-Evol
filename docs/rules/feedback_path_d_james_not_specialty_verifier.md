<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-path-d-james-not-specialty-verifier
description: "JAMES 는 full-RAG + replayable audit 시스템. HALT-RAG 같은 verification 전문 시스템과 카테고리 다름. abstention F1 단일 axis 에서 HALT-RAG 0.978 따라가려는 시도 (NLI verifier 추가 / meta-classifier 학습 / cascade threshold) 금지. 사용자 결정 2026-06-08: 'D로하겠다' = Path D positioning = JAMES 의 unique strength 유지, 단일 axis 최적화 안 함."
metadata:
  type: feedback
  originSessionId: 2026-06-08-path-d-positioning-decision
---

## ⚠️ 2026-06-09 정정 — 9번째 catch 로 conditional 화

이 룰의 원래 framing 이 **over-protective** 였음. 9번째 catch ([[feedback_james_identity_measurement_driven]]) 가 정정:

- 이전: "JAMES = full-RAG + replayable audit 카테고리, 단일 axis 추격 절대 금지"
- 정정: "JAMES = 측정으로 정의되는 시스템. **measurement evidence 가 정당화하면 architectural pivot OK**. axis-misaligned cherry-picking 만 금지"

아래 규칙은 **measurement evidence 없는 pivot 거부** 룰로 재해석. Multi-axis Pareto 측정 결과가 net positive 면 cycle β code 변경 의무 (lock 아님).

## 규칙 (정정 후)

**JAMES 의 abstention F1 을 HALT-RAG 수준 (0.978) 으로 매칭시키려는 architectural 작업은 measurement evidence prerequisite.** Multi-axis Pareto 측정 + cross-model 확인 없이 단일 axis 추격 거부. 다음 path 들의 status:

- ⚠️ **Path A** (NLI ensemble 통합): single-axis abst_f1 chase 면 reject. Multi-axis 측정이 net positive (다른 axis regression 작거나 acceptable trade-off) 면 **고려 대상**.
- ⚠️ **Path B** (meta-classifier 학습): 라벨 데이터셋 + multi-axis 측정 + ML cycle 필요. Evidence-driven 만 진행.
- ⚠️ **Path C** (cascade threshold): single-axis chase 면 reject. multi-axis 정당화되면 OK.

이유: JAMES = **현재 production category = full-RAG with replayable audit**. HALT-RAG = **post-hoc verification specialty** 카테고리. 카테고리 pivot 은 큰 결정 — measurement evidence 가 강하게 정당화해야 진행. 단일 axis cherry-picking 만으로는 부족.

단 evidence 충분하면:

- Replayable audit (event-sourced graph reconstruction, T5 Replayable Audit Graph)
- Full RAG pipeline (retrieval + reranker + cog stages + abstention softener integrated)
- Per-query overlap measurement method (새 methodology)
- Open scripts + reproducible measurement
- Mother platform 6-dimension readiness framework

## Why (사용자 결정 2026-06-08)

Cycle γ Phase B+C+D + prior-art search + 6 honest-framing catches 누적 후 user explicit choice:

> "D로하겠다" — Path D (HALT-RAG 같은 system 안 만들기) 선택

이전 4-path 분석:
- Path A (NLI 통합) = 1-2주 엔지니어링, F1 0.387 → 0.7+ 가능. 그러나 NLI 모델 dependency + JAMES scope 침식
- Path B (meta-classifier) = 수개월 ML, 라벨된 abstention 데이터셋 필요
- Path C (cascade threshold) = 1-2 PR, F1 0.5 정도 제한적 lift
- **Path D = positioning 유지, 단일 axis 추격 안 함**

JAMES 의 진짜 contribution boundary (prior-art positioning 후 narrow 된 것):
- Empirical reproducibility + per-query overlap method (modest but real)
- PR #440 substitution determinism + Robin 26B 재현 (Track 1 joint piece)
- Mother platform v0.5 D2 evidence (별도 게이트)

이 boundary 가 정직. 단일 axis 추격 = boundary 와 다른 방향.

## How to apply

### 미래 세션이 "JAMES 가 약함" framing 시작하면 (★정정 2026-06-09)

- ⚠️ "abstention F1 개선 PR" → **multi-axis Pareto 측정 prerequisite**. evidence 면 진행, single-axis chase 면 reject.
- ⚠️ "NLI 채점기 추가" → 카테고리 pivot, **multi-axis + cross-model 측정 후** 결정. evidence 면 고려.
- ⚠️ "HALT-RAG mechanism 일부 차용" → measurement evidence 정당화 시 OK, 단 framing careful.
- ✅ "JAMES 의 unique strength 강화 (replayable audit / measurement method / cross-model evidence)" → OK
- ✅ "abstention 측정 방식 자체를 정직하게 표현" → OK
- ✅ **"measurement-driven discovery로 JAMES 정체성 evolve" → OK + 권장** (9번째 catch core)

### Trigger 발생 시 응답 template

만약 협업자 / publication / 측정 결과가 "JAMES abst_f1 약함" 지적하면:

```
JAMES는 full-RAG + replayable audit 카테고리 시스템입니다.
HALT-RAG 같은 verification specialty 시스템과 axis-by-axis 비교
는 카테고리-aware하지 않습니다.

abstention F1 0.387 (RGB-en mxtral) = full RAG pipeline 의 abstention
contribution 측정. verification specialty 와 다른 axis 묶음.

JAMES 의 unique strength = replayable audit + per-query overlap
method + open reproducibility. 이쪽이 contribution boundary.
```

### "더 측정 필요?" 질문에 응답

Step 1 (NLI 재채점 ~30분) **도 안 함**. 그 측정은 Path A/B/C 결정 위한 측정. Path D 선택 후에는 측정 자체 불필요.

대신:
- Cross-bench (ALCE/MuSiQue/2Wiki) = Path D 와 정합 — JAMES 의 unique strength (per-query overlap method) 를 다른 벤치에 적용
- Phase E multi-axis ablation = Path D 와 정합 — full-RAG axis 묶음 보여줌 (single-axis 아님)
- M9 joint deposit prep = 별도 collab arc
- Mechanistic ablation 깊이 분석 = JAMES architecture 이해 강화

## 비-Path-D 측정과의 구분

Path D 가 거부하는 것 = "abst_f1 단일 axis 최적화 위한 measurement / architectural change"

Path D 가 허용하는 것 = 다른 motivation 으로 같은 component 측정:
- noise robustness 최적화 → rerank 측정 OK
- multi-hop reasoning 강화 → cog_stages 측정 OK
- replayable audit 강화 → verify 측정 OK
- 등

핵심 distinction: **motivation 이 단일 abst_f1 추격이면 reject, 다른 axis primary motivation 이면 OK**.

## 누적 catch (이번 세션 7 catches)

이번 결정 = 7번째 정직 framing 정정:
1. post-hoc fit framed as prediction
2. 0.000 negrej audit
3. family vs size separation
4. prior art 권장 (⭐⭐⭐ REJECT)
5. cycle γ ↔ joint piece scope 분리
6. 단일-axis ablation → "defect" framing 위반
7. **HALT-RAG axis 추격 안 함 (Path D positioning)**

각 catch 가 "JAMES 가 부족하다" / "더 잘 만들자" 방향에서 "JAMES 가 무엇인가 정직하게 정의" 방향으로 framing 견인.

## 관련

- [[feedback_single_axis_ablation_misframing]] — 6번째 catch, 같은 axis-misalignment 패턴의 ablation 버전
- [[feedback_eval_cycle_vs_collab_arc_separation]] — 5번째 catch, scope separation
- [[mechanism_layer_intent_axis_alignment]] — α-5 mother rule, 같은 카테고리 정합 원칙
- [[feedback_jameses_positioning_replayable_rag]] — "Replayable RAG 는 하나의 특성, 전체 정체성 아님" 룰
- `docs/research/cycle-gamma-prior-art-positioning.md` — prior art 분석 (HALT-RAG 0.978 등 reference)
- `docs/handovers/v0.4-cycle-gamma-phase-d-results-2026-06-08.md` — Phase D 정직 handover
- `docs/PLATFORM_READINESS.md` — Mother platform 6-dimension framework (JAMES 의 진짜 axis 묶음)
