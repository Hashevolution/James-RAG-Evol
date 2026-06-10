<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-single-axis-ablation-misframing
description: "Component ablation 결과를 단일 axis (예: abst_f1) 만 측정한 후 'structural defect' / 'JAMES default 변경' framing 하는 것은 α-5 cycle wrong-fix-averted #7 (axis-misalignment) 의 직접 재현. layer-intent-axis 정합 규칙 [[mechanism_layer_intent_axis_alignment]] 에 위반. 사용자 catch 2026-06-08: '자메스 설계 구조상 잘못된것이 있다는 근거가 있는건가 분석해봐'. 6번째 honest-framing 정정."
metadata:
  type: feedback
  originSessionId: 2026-06-08-phase-d-axis-misalignment
---

## 규칙

**Component ablation 결과는 그 component 의 primary axis 위에서만 verdict 가능.** 다른 axis 만 측정해서 "이 component 가 해로움 / structural defect" framing = α-5 cycle wrong-fix-averted #7 직접 재현.

ablation knob X disable 시 측정 axis Y 에서 ΔY 신호 보였을 때:
- **X 의 primary axis = Y** → 정합 측정, ΔY 가 verdict 근거
- **X 의 primary axis ≠ Y** → 부정합 측정, ΔY 만으로 verdict 불가. X 의 primary axis 도 동시 측정 + axis-weighted Pareto 후 verdict

**Why:**
- 각 RAG component 는 design 시 명시 intent + primary axis 가짐 ([[mechanism_layer_intent_axis_alignment]] 의 표)
- 단일-axis 측정 후 "defect" framing 은 trade-off 측정 못함
- α-5 cycle 에서 ADAPTIVE_BUDGET 을 quality axes 로 채점해 "도움 안 됨" 잘못 판단한 사건 #7 과 정확히 동일 패턴 (그건 cycle 안에서 사용자 catch 로 막힘)
- n=25 같은 작은 sample 의 +0.050 magnitude 는 axis-misalignment 위에서 가짜 발견으로 굳기 쉬움

**How to apply:**

### Ablation matrix 설계 시 의무

각 ablation knob 의 primary axis 와 측정 axis 가 정합하는지 PR description 에 박음.

| Ablation knob | Component design intent | Primary axis | 측정 axis 정합 |
|---|---|---|---|
| `JAMES_DISABLE_ABSTENTION` | 거절 grounding | abst_f1 | abst_f1 측정 ✅ |
| `JAMES_DISABLE_RAG_RETRIEVAL` | 기본 grounding | 모든 axis (fundamental) | 모든 axis 측정 (특히 abst_f1 ✅) |
| `JAMES_DISABLE_GRAPH` | concept multi-hop | path + graded | abst_f1 만 측정 ⚠️ misaligned |
| `JAMES_DISABLE_VERIFY` | grounding 검증 | graded | abst_f1 만 측정 ⚠️ misaligned |
| `JAMES_DISABLE_RERANK` | retrieval 품질 | noise_robustness + graded | abst_f1 만 측정 ❌ misaligned |
| `JAMES_DISABLE_TYPED_FILTER` (α-8) | evidence-of-absence | abst_f1 + path | abst_f1 측정 부분 정합 (path 빠짐) |
| `JAMES_DISABLE_COGNITIVE_STAGES` | multi-step reasoning | graded | abst_f1 만 측정 ❌ misaligned |

### Verdict 규칙

- **정합 측정 + significant Δ** → component-level finding 가능 (e.g. DISABLE_ABSTENTION → abst_f1 -0.054 = 정합 valid)
- **정합 측정 + within noise band** → "no measurable effect on primary axis"
- **부정합 측정 + 어떤 Δ 든** → verdict 불가, **multi-axis 측정 후 재평가** 의무. 단일 finding 으로 "harmful" / "defect" framing 금지.

### Multi-axis Pareto 측정 prerequisite

각 component 의 primary axis + abst_f1 + path + graded + latency + noise_robustness 모두 동시 측정 후:
- Net axis-weighted delta per layer-intent matrix
- 그 후 verdict (Pareto-dominant adopt / dominated reject / mixed = trade-off)

cycle β `_classify_five_axis_delta` 룰 적용.

### Cross-model prerequisite

단일 모델 ablation = cross-model 변동성 ignored. Phase B+C 가 보여줬듯 모델별 abstention pattern 다름 (gemma4 4/6, gemma3:12b 3/6, mxtral 6/6, llama 6/6). 단일 모델 ablation 결과는 generalizable 아님.

## 사례 — Phase D 2026-06-08 (6번째 catch)

### 측정
mxtral n=25, 7 ablation knobs, all measured on abst_f1 only.

### 결과 + 내 (Claude) over-claim framing
| Ablation | abst_f1 Δ | 내 framing |
|---|---|---|
| `DISABLE_RERANK` | +0.050 | "rerank = abstention 에 net harmful" ❌ |
| `DISABLE_TYPED_FILTER` | +0.050 | "typed_filter = abstention 에 net harmful" ❌ |
| `DISABLE_COGNITIVE_STAGES` | +0.050 | "cog_stages = abstention 에 net harmful" ❌ |
| 합산 | "potential +0.15 lift" | "structural defect / default 변경 후보" ❌ |

### 사용자 catch (2026-06-08)
> "자메스 설계 구조상 잘못된것이 있다는 근거가 있는건가 분석해봐"

→ 단일 abst_f1 axis cherry-picking 으로 "structural defect" 주장하는 것은 α-5 wrong-fix #7 패턴 직접 재현임을 catch.

### 정정된 framing

**✅ Valid (axis-aligned):**
- `DISABLE_ABSTENTION` → abst_f1 -0.054 (1 query lost)
  → softener 가 1/6 of abstention set 에 design-intent contribute 확인. magnitude 작지만 valid.
- `DISABLE_RAG_RETRIEVAL` → abst_f1 -0.173, set 완전 변경
  → retrieval = 기본 grounding, abstention 의존성 expected, 정합 측정.

**⚠️ Speculative (axis-misaligned) — defect evidence 아님:**
- Rerank / cog_stages / typed_filter 의 abst_f1 +0.050 = valid measurement, but defect framing 위해 primary axis (noise / graded / path) 동시 측정 + Pareto verdict 필요.

**Expected behavior (axis-misaligned):**
- Graph / verify 의 ΔF1 = 0 → primary axis 가 abst_f1 아니므로 regression-check pass. defect 아님.

## 일반화 패턴

이 룰은 RAG component ablation 한정 아님. 모든 시스템에서:

1. **각 component 가 무엇을 위해 존재하는지** design intent 명시
2. **그 intent 의 primary metric 이 무엇인지** axis 매핑
3. **그 axis 로만 측정** 후 verdict (또는 multi-axis Pareto)
4. **단일 cherry-picked axis 로 "defect" framing 금지**

cycle β 의 `_classify_five_axis_delta` Pareto 규칙 + α-5 의 layer-intent matrix 가 같은 원칙의 cycle-별 표현.

## 누적 catch 패턴 (2026-06-08 세션)

이번 catch = 6번째 honest-framing 정정:
1. post-hoc fit framed as prediction → `[[feedback_finding_size_honest_framing]]`
2. 0.000 negrej audit → real measurement 확인
3. family vs size 분리 → mxtral 측정 동기
4. prior art 권장 → `[[docs/research/cycle-gamma-prior-art-positioning]]` ⭐⭐⭐ REJECT
5. cycle γ ↔ joint piece scope 분리 → `[[feedback_eval_cycle_vs_collab_arc_separation]]`
6. **Phase D 단일-axis → "structural defect" framing 위반** → 이 룰

각 catch 가 measurement 자체는 valid 로 보존하면서 framing 만 narrowing/honest 방향으로 정정. JAMES 측정 데이터 손상 없음, framing 만 정직화.

## 관련

- [[mechanism_layer_intent_axis_alignment]] — α-5 cycle 에서 박힌 mother rule
- [[feedback_finding_size_honest_framing]] — over-claim 일반 방지 룰
- [[feedback_oracle_phrase_artifacts]] §"확장 3" — 4-step 룰의 layer-intent 일반화
- [[feedback_eval_cycle_vs_collab_arc_separation]] — 5번째 catch, scope conflation 룰
- `docs/handovers/v0.4-cycle-gamma-phase-d-results-2026-06-08.md` — Phase D 정직 handover
