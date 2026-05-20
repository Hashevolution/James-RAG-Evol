# Postmortem — Knowledge Cascade confidence + cross-doc aggregation defects (2026-05-20)

> **Engineering retrospective.** Two product defects discovered and corrected on 2026-05-20.
> Related patches: PR #349 (`b89c099`) · PR #350 (`1009cca`) · PR #351 (`5517743`)
> Related design memo (historical reference): `docs/design/v0.3-knowledge-cascade.md §3, §4`

---

## 0. 전제 (framing)

**제품 동작을 먼저 만들고, 그 결과를 특허로 정리한다.** 청구가 코드를 끌고 가는 방향은 안티-패턴.

본 문서는 **2건의 제품 결함 발견·정정 기록**이다:
1. confidence 공식이 확률 추론으로서 잘못 동작 (2 출처에서 saturate, 단조성 깨짐)
2. cross-doc 강화 시 ingestion 이 데이터를 silently 폐기 (Knowledge Cascade 의 핵심 가치 무효화)

정정 사유의 본질은 **수학적 정확성 + 데이터 보존 + 사용자 신뢰성**이지 특허 청구 backing 이 아니다. 디자인 메모와의 정합은 부수효과.

---

## 1. 발견 경위

프로젝트 owner 가 confidence 공식에 대해 다음 의문 제기 — 이를 트리거로 제품 동작 검증 착수:

> "Noisy-OR 관련, Clamped sum 은 출처 2~3개 모이면 saturate → confidence 의 의미 상실. 우리 시스템은 quarterly report cascade 시 한 관계가 5~20개 출처로 강화될 수 있음 → saturate 가 너무 쉬움. 디자인 메모도 처음부터 noisy-OR 을 선택한 이유가 '단조성 보장' 이었음. Clamped sum 구현은 실수 또는 단순화일 가능성. 디자인 메모와 명백히 불일치."

이 의문의 사실 여부 검증 결과:

---

## 2. 사실 검증 (4 항목 모두 ✅)

### ① "Clamped sum 은 2~3 출처면 saturate"
**TRUE — 실제로는 2 출처에서 즉시 saturate.**

구 구현 (`core/relations_schema.py` 핫픽스 이전):
```python
def compute_confidence_from_sources(sources):
    total = 0.0
    for s in sources: total += float(s.get("weight"))
    return min(total, 1.0)  # = min(Σw, 1.0)
```

수학적 비교 (LLM 추출 기본 weight ≈ 0.7):

| 시나리오 | clamped sum | noisy-OR | 차이 |
|---|---|---|---|
| 1 source × 0.7 | 0.70 | 0.70 | 0 (identity) |
| **2 sources × 0.7** | **1.00 (saturated)** | 0.91 | **-0.09 (의미 손실)** |
| 5 sources × 0.7 | 1.00 | 0.998 | -0.002 |
| 20 sources × 0.7 | 1.00 | ~1.0 (< 1, asymptotic) | < 0.01 |

→ 2 출처에서 즉시 saturate. 초기 추정 "2~3 출처" 보다 더 가혹.

### ② "5~20 출처로 강화 → saturate 너무 쉬움"
**TRUE — 디자인 메모 §9 가 직접 N=50 sources/relation 까지 처리하도록 설계 인정.**

`docs/design/v0.3-knowledge-cascade.md:362`:
> "sources array unbounded growth — **Cap per relation at N=50 sources**; on overflow, merge oldest two."

→ 시스템이 한 relation 당 **50 sources** 까지 안정 처리하도록 설계됐는데, 실제 구현은 **2 sources** 면 정보가 사라짐. **설계 전제와 구현이 정량적으로 25배 어긋남.**

### ③ "디자인 메모는 noisy-OR 을 선택한 이유가 '단조성 보장'"
**TRUE — 명시적으로 적혀 있음. 다른 후보 (max, mean) 대비 비교표까지 있음.**

`docs/design/v0.3-knowledge-cascade.md:117-148`:
```python
def derive_confidence(sources: list[dict]) -> float:
    """Probabilistic OR -- any source can confirm the relation.
    P(confirmed) = 1 - Π(1 - w_i)
    Properties:
      - many sources -> asymptotic to 1, but never exceeds 1
      - cascading delete strictly decreases confidence (monotonic)
    """
```

**비교표** (L141-148, 디자인 메모 §3 발췌):

| Formula | Adding source | Removing source |
|---|---|---|
| `max(weights)` | 동일 (새 값이 더 크지 않으면) | max 였던 게 빠질 때만 떨어짐 |
| `mean(weights)` | 항상 변함 — 약한 source 도 평균 희석 | 항상 변함 |
| `log-sum (noisy-OR)` | **항상 증가 (단조)** | **항상 감소 (단조)** |

디자인 메모 §3 인용:
> "Log-sum is **the only one with monotone cascade semantics**: deleting a doc strictly drops confidence, never leaves it stale."

→ 선택 사유가 명시적·문서화·근거 비교 포함.

### ④ "구현은 디자인 메모와 명백히 불일치"
**TRUE — 그리고 함수 이름조차 다름.**

| 측면 | 디자인 메모 | 구 구현 |
|---|---|---|
| 함수 이름 | `derive_confidence` | `compute_confidence_from_sources` |
| 공식 | `1 - Π(1 - w_i)` | `min(Σw_i, 1.0)` |
| 2-source 케이스 | 0.91 | 1.00 |
| 단조성 (삭제) | 엄격 감소 | saturated 면 잔류 |
| 단조성 (추가) | 엄격 증가 | saturated 면 변화 0 |
| Many-source | asymptotic | flat at 1.0 |

→ 5개 측면 중 5개 모두 불일치.

---

## 3. 왜 이 결함이 9 일 동안 발견되지 않았는가

**4 단계 사일런트 정렬 (silent alignment)** — 디자인 / 구현 / 테스트 / 검증 invariant 가 일관되게 잘못된 방향으로 정합:

### 단계 1 — 구현 단순화 (시점 불명)
누군가가 `compute_confidence_from_sources` 를 작성하면서 noisy-OR 대신 clamped sum 채택. 디자인 메모 §3 의 `derive_confidence` 가 있음에도 함수 이름을 바꿔서 새로 작성. **디자인 메모 업데이트 없이** 묵시적으로 contract 변경.

### 단계 2 — 테스트 락인 (같은 PR)
`tests/test_relations_schema.py:62-81` 가 clamped-sum 결과를 명시적으로 assert:
```python
def test_multiple_sources_sum(self):
    sources = [{"weight": 0.4}, {"weight": 0.3}]
    self.assertAlmostEqual(compute_confidence_from_sources(sources), 0.7)
    # noisy-OR 이면 0.58. 0.7 을 박아두면서 clamped sum 을 "정상" 으로 격상.

def test_caps_at_1_0(self):
    sources = [{"weight":0.7}, {"weight":0.6}, {"weight":0.3}]
    self.assertEqual(compute_confidence_from_sources(sources), 1.0)
    # noisy-OR 이면 0.916. CAP 도달이 의도임을 명시.
```
→ 누군가 noisy-OR 을 시도해도 테스트가 거부. **공식 변경이 회귀로 보임.**

### 단계 3 — Closure-doc invariant 가 검출 못 함
`docs/handovers/v0.3.x-session-2026-05-17-closure.md:234` (v0.3.0 릴리스 invariant):
> `compute_confidence_from_sources([{weight:0.7}]) == 0.7`

→ 단일 source 만 검사. clamped-sum 과 noisy-OR **모두 단일 source 에서 동일값** (`min(0.7,1)` = `1-(1-0.7)` = 0.7). **두 공식을 구분할 수 없는 invariant 가 invariant 로 인정됨.**

### 단계 4 — Phase A 마이그레이션 byte-identical 검증의 함정
PR #266 (Phase A) 의 검증 "1-A bench step7 byte-identical PASS":
- Phase A 는 **모든 relation 에 단일 legacy source** 만 back-fill
- → 두 공식 동일값 → bench 무변동
- → "byte-identical" 이 형식적으로 통과
- 실제 multi-source 케이스에서의 회귀는 **측정 자체가 안 됨**

**결과**: 9일간 7 production wiring (`core/cascade.py`, `core/graph_editor.py × 4`, `core/wiki_generator.py`) + 50+ 테스트가 잘못된 공식 위에 정합. 자가-수정 메커니즘이 모두 무력화.

---

## 4. 발견의 의의 (제품 측면)

### 4.1 잘못된 동작이 제품에 끼치던 영향

핫픽스 이전 코드의 결함은 다음 4가지 제품 동작 문제로 직접 드러남:

- **확률 추론 정확성 위반** — `min(Σw, 1.0)` 는 독립적 증거 결합 의미론을 모방하지 않음. 2 출처에서 평탄화되어 "얼마나 강하게 corroborated 되었는가" 신호 손실.
- **단조성 깨짐** — doc 삭제 cascade 시 confidence 가 안 떨어지는 케이스 발생 (다른 source 가 cap 을 유지). stale 1.0 잔류 → 신뢰할 수 없는 graph traversal.
- **약한 신호 over-promotion** — weight 0.3 × 2 면 1.0 까지 부풀림. 실제 confidence 는 0.51 수준. graph DFS 의 0.6 임계값 통과 여부가 잘못 결정됨.
- **Knowledge Cascade 가치 무효화** — cross-doc 강화 자체가 작동 안 함 (PR #350). doc 5개가 같은 사실 확인해도 confidence 안 올라감.

→ 본질은 **사용자 데이터의 신뢰성 + 추론 정확성** 의 문제. 디자인 메모와 무관하게 정정 정당.

### 4.2 정정 후 작동 확정 (테스트 락인)

`tests/test_relations_schema.py` + `tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests` 의 12개 테스트가 다음 제품 동작을 contract 로 잠금:

1. 단일 source: confidence = weight (정보 보존)
2. 다중 source: noisy-OR, asymptotic to 1.0 but < 1
3. source 추가/삭제 시 strictly 단조
4. weight per-element [0,1] clamp (외부 plugin/손편집 방어)
5. cross-doc 동일 triple → sources append
6. cross-doc inverse direction 대칭
7. same doc_id 멱등성 (재업로드 안전)
8. 새 target 은 새 relation 행

→ 제품 동작이 측정 가능한 invariant 로 정의됨. 회귀 시 즉시 검출.

### 4.3 발견 패턴이 시사하는 것 — silent alignment failure

본 사건의 가치 있는 부산물: **"디자인 메모 / 구현 / 테스트 / 검증 invariant 가 같은 방향으로 잘못 정합" 패턴**.

자가-수정 메커니즘이 모두 무력화된 사례:
- 디자인 메모는 명세 (제품 의도 기록)
- 구현이 단순화 결정으로 메모와 어긋남
- 테스트가 단순화된 구현을 정상으로 락인
- 검증 invariant 가 두 동작을 구분 못 함 (단일 source 케이스만 검사)
- 4-layer 모두 정합 → 외부 검토 트리거 없이는 드러나지 않음

이 패턴 자체가 학습 자료. 향후 작업에서 "테스트가 정상이라 했지만 의심" 시점이 오면 layer 4개 모두 독립 검증해야 함.

### 4.4 특허 관점 (사후)

핫픽스 이후 제품이 작동하는 방식 (noisy-OR + cross-doc aggregation) 자체가 출원 시점에 청구 후보가 될 수 있음. 다만 framing 은:

- ❌ "디자인 메모가 청구한 것을 코드로 backing"
- ✅ "제품이 이렇게 동작하므로 그 동작을 청구"

방향은 **코드 → 청구**. 출원 시점에 그때까지 작동하는 동작을 그대로 정리한다. 디자인 메모는 historical artifact (개발 트리거의 일부) 이며 청구의 ground truth 아님. 청구 reference 는 **현재 코드 + 테스트**.

---

## 5. 영향 분석 — 자메스 성능 / 추론 체계

### 5.1 추론 체계에서 confidence 가 결정을 좌우하는 곳
전체 `core/` grep 결과: **단 1개 게이트**.

`core/graph_engine.py:38` — `CONFIDENCE_THRESHOLD = 0.6`

| 위치 | 사용 | 영향 |
|---|---|---|
| L335 (DFS traversal) | `if confidence < 0.6: continue` | 다음 hop 건너뜀 — graph path 좁아짐 |
| L450 (entity context) | `confidence >= 0.6 만 포함` | 약한 relation 이 답변에 안 들어감 |

그 외 confidence 사용처 (`wiki_generator`, `cascade`, `graph_editor` × 4, `graph_snapshot`, `memory/{store,loom,extractor}`, `ontology`, `reasoning/pipeline`, `retrieval/*`) 는 **표시·저장·로깅·메타데이터** 만. 결정 게이트 아님.

### 5.2 즉시 영향 (현재)
**거의 0.** Production wiki audit (PR #349 의 dry-run):
- 278 entity files scanned
- **0 multi-source relations**
- max_delta = 0.0

→ 모든 confidence 값 byte-identical. STEP 7 bench 무회귀.

### 5.3 미래 영향 (첫 multi-source 누적 시)
**약한 corroboration 케이스의 임계값 통과율 변화.**

| 상황 | 구 (clamped) | 신 (noisy-OR) | 0.6 임계값 |
|---|---|---|---|
| 2 sources × 0.3 (약함) | 0.60 | 0.51 | **통과 → 차단** ⚠ |
| 2 sources × 0.5 (중간) | 1.00 | 0.75 | 통과 (양쪽) |
| 2 sources × 0.7 (강함) | 1.00 | 0.91 | 통과 (양쪽) |
| 5 sources × 0.7 | 1.00 | 0.998 | 통과 (양쪽) |

**판정**:
- 강한 corroboration (≥ 0.5 weight) — 동작 차이 없음
- 약한 corroboration (≤ 0.35 weight) — graph path 에서 제외됨
- **방향성**: 확률 추론으로서 옳음 — "약한 신호 2개 = 강한 신호 1개" 의 거짓 등가를 거부 (디자인 메모도 같은 결론이었음)

### 5.4 부수 효과
- **UI confidence 막대바**: 2-doc 강화 시 100% → 91% 표시. 사용자가 "약해 보임" 으로 오인할 가능성.
- **0.6 임계값의 적절성**: 구 공식에 맞춰 튜닝된 magic number. 신 공식의 연속 분포에서는 0.5 또는 0.55 가 더 적절할 수 있음. **데이터 누적 후 재튜닝 권장**.
- **자가-진화 patch 평가**: confidence-기반 점수가 있다면 변별력 향상 (구 공식은 모두 1.0 cluster).
- **RAGAS faithfulness**: 답변 context 포함 relation 수 변동 → 측정 필요.

---

## 6. 검증 방법 (Tier 1/2/3)

### Tier 1 — 수학적 검증 (완료)
`tests/test_relations_schema.py` 의 7개 invariant 테스트 — 락인됨, 매 push 시 자동 검증.

| 테스트 | 검증 내용 |
|---|---|
| `test_single_source_returns_weight` | identity contract (Phase A 마이그레이션 byte-identical) |
| `test_two_sources_diverge_from_clamped_sum` | 2-source 분기 (smoking gun) |
| `test_many_sources_asymptotic_not_saturated` | 5×0.7 → 0.9976 (< 1) |
| `test_strong_corroboration_3_sources` | 디자인 메모 §3 예시 |
| `test_monotone_adding_source_strictly_increases` | 추가 단조성 |
| `test_monotone_removing_source_strictly_decreases` | 삭제 단조성 (cascade 의 근거) |
| `test_weight_clamped_to_unit_interval` | per-element robustness |

### Tier 2 — Synthetic multi-source A/B (가능, 30분)
**목적**: 실제 retrieval 체인에서 noisy-OR 적용 확인.

```bash
# 동일 triple 추출하는 두 doc 업로드
echo "조비는 NVIDIA 와 협력한다." > /tmp/doc1.txt
echo "조비-NVIDIA 협업이 발표되었다." > /tmp/doc2.txt
curl -X POST /admin/files -F file=@/tmp/doc1.txt
curl -X POST /admin/files -F file=@/tmp/doc2.txt

# /admin/graph/relation 확인 — sources 2개 / confidence ≈ 0.91 기대
curl /admin/graph/relation?src=e_org_joby&tgt=e_org_nvidia&type=RELATED_TO
```

**판정**:
- confidence = 0.91 → noisy-OR 정확히 wiring ✅
- confidence = 1.0 → clamped sum 잔류 또는 ingestion 의 별 경로 (재점검 필요) ❌
- sources 1개로만 표시 → cross-doc aggregation 자체가 동작 안 함 (별도 버그) ⚠

### Tier 3 — STEP 7 baseline 재캡처 (1~2 사이클 후)
**목적**: 실 사용 환경에서 graph_paths / answer faithfulness 변동 측정.

```bash
# 1~2주 정상 사용 → multi-source 자연 누적
python scripts/bench.py --suite=step7  # graph_paths delta
# ±2 변동 이내 → 정상. 초과 → 0.6 임계값 재튜닝
```

---

## 7. 미해결 의문 — **CLOSED 2026-05-20** ✅

**Production wiki 의 multi-source 0건이 정상인가?**

→ **사일런트 버그 확인됨.** 즉시 정정 (PR #350).

### 발견

`core/wiki_generator.py:640-645` 의 분기:
```python
existing_id = self._find_existing_entity_id(name, etype)
if existing_id:
    print(f"... already exists -> skip")
    name_to_id[name] = existing_id
    continue   # _build_entity_relations + create_entity_file 둘 다 skip
```

→ 두 번째 doc 가 같은 (subject, predicate, object) triple 을 추출해도 entity 가 이미 존재하면 **entire processing 을 skip**. 결과적으로 cross-doc 강화 자체가 작동 안 함 — Knowledge Cascade 의 핵심 동작(다중 출처 누적) 이 사용자 데이터에서 발현 안 됨. 디자인 메모 §4 도 같은 패턴을 명세했으나, 정정 사유는 청구 backing 이 아니라 **사용자 데이터 손실** 임.

### 영향 (PR #349 단독 vs 양 PR 결합)

| 시나리오 | PR #349 이전 | PR #349 만 | PR #349 + PR #350 |
|---|---|---|---|
| doc1 (Joby, NVIDIA) | sources=[d1], conf=0.7 | 동일 | 동일 |
| doc2 같은 triple | sources=[d1], conf=0.7 (변화 0) | **동일** — 공식 fix 됐지만 data 없음 | **sources=[d1,d2], conf=0.91** |
| 5 docs 누적 | sources=[d1], conf=0.7 | 동일 | sources=[5 entries], conf=0.998 |
| doc 삭제 cascade | confidence 불변 | 동일 | proportional drop (단조성) |

→ **PR #349 만으로는 불충분**. 두 PR 함께 들어가야 제품이 실제 monotone-asymptotic 동작을 함 — confidence 공식과 ingestion 경로 양쪽이 정합돼야 사용자 데이터가 올바르게 누적됨.

### 정정 (PR #350, merge commit `1009cca`)

- 신규 helper `_merge_relations_into_existing_entity(entity_id, new_relations, doc_id, ts)`
- L640 의 `continue` → helper 호출로 교체
- 매칭: `(target_name, normalized_type)` via `core.ontology.normalize_relation`
- 멱등성: 같은 `doc_id` 중복 source 는 skip
- confidence: noisy-OR 로 재 derive (PR #349 와 정합)
- 대칭: forward + inverse 양방향 동일 메커니즘

### 신규 invariant 5건 (`tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests`)

| 테스트 | 검증 |
|---|---|
| `test_second_doc_appends_sources_to_existing_entity` | cross-doc append 정상 |
| `test_second_doc_inverse_also_aggregates` | inverse 도 양방향 정합 |
| `test_confidence_uses_noisy_or_after_two_sources` | **0.91 assertion** (clamped sum 회귀 시 1.0) — 두 PR 의 결합 contract |
| `test_same_doc_reupload_is_idempotent` | doc_id 멱등성 |
| `test_second_doc_new_target_appends_new_relation` | 새 target 은 새 row 로 |

### 제품 동작 정정 결과

이 결함의 핵심은 **doc 5개로 같은 사실을 누적 강화해도 confidence 가 첫 doc 의 weight 에서 멈춰 있었다는 것**. Knowledge Cascade 가 약속한 "다중 출처 누적 강화" 가 사용자 데이터에서 발현되지 않았음.

**현재 상태** (PR #349 + #350 머지 후):
- 새 doc 가 기존 (subject, predicate, object) 을 다시 추출하면 source append → confidence 단조 증가
- doc 삭제 cascade 시 해당 source 만 제거 → confidence 단조 감소
- 약한 신호의 over-promotion 차단 → graph DFS 의 0.6 임계값이 의미 있게 작동
- 12개 invariant 테스트로 회귀 차단

특허 측면은 사후 정리 대상 — 출원 시점에 그때까지 작동하는 동작을 청구 후보로 정리. 본 정정은 출원과 무관하게 사용자 데이터 신뢰성을 위해 필요했음.

### Production wiki 의 retroactive recovery (불가)

기존 656 single-source relation 들이 실제로 다른 doc 에서도 같은 사실을 가졌는지는 **복원 불가** — LLM extraction 의 원본 기록이 doc entity 의 outgoing relations 외에는 없음. 미래 ingestion 부터 정상.

### 잔여 점검

- 다른 design memo ↔ implementation 정합성의 일제 audit 는 **수행 안 함** (사용자 우선순위 = 추론 강화·안정화 → 특허는 사후). 향후 사용자가 동일 위험 패턴 발견 시에만 spot 정정.

---

## 8. 권장 후속 행동 (제품 우선순위)

본 문서는 발견·정정 기록일 뿐 향후 작업 가이드 아님. 제품 우선순위는 별도 트랙:

| 우선 | 항목 | 비고 |
|---|---|---|
| 🔴 | **Phase 2 PR-7 Planner** — multi-step task decomposition + Tool Router wiring | 추론 강화 직접 기여, Phase 2 마감 |
| 🟠 | Phase 3 PR-9 Episodic Memory | 세션 간 일관성 (안정화 + 추론) |
| 🟠 | Phase 2 Default ON 검토 (Reflection / Verification) | 측정 기반 |
| 🟡 | PR-O6b Graph Node Editor frontend | 사용자 가시성 |
| 🟡 | 0.6 confidence 임계값 데이터 기반 재튜닝 | multi-source 누적 후 (자연 발생) |

본 결함이 다른 모듈에도 isolated 인지 systematic 인지는 **실제 사용 중 의심 시점에만 spot 점검**. 일제 audit 는 사용자 우선순위와 어긋남 (특허 청구를 코드 ground truth 로 격상하는 안티-패턴).

---

## 9. 첨부 — 정정 산출물 위치 (참고용)

- PR #349 noisy-OR (`b89c099`)
  - `core/relations_schema.py::compute_confidence_from_sources`
  - `tests/test_relations_schema.py` (7 invariant)
  - `scripts/migrate_recompute_confidence.py` (드라이런 / apply / snapshot+rollback)
- PR #350 cross-doc aggregation (`1009cca`)
  - `core/wiki_generator.py::_merge_relations_into_existing_entity` (신규 helper)
  - `core/wiki_generator.py::process_document_for_entities` (L640 분기 교체)
  - `tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests` (5 invariant)
- PR #351 CHANGELOG framing 정정 (`5517743`) — 두 entry lead 를 제품 결함으로 reframe
- 디자인 메모 (변경 없음, historical reference): `docs/design/v0.3-knowledge-cascade.md §3 / §4`

---

## 10. Ground truth 명시

본 문서는 **2026-05-20 시점의 발견·정정 기록**일 뿐 청구의 ground truth 아님. 특허 출원 시 reference 는 항상 **현재 코드 + 테스트**:

- `core/relations_schema.py` (현재 commit) — 공식 정의
- `tests/test_relations_schema.py` (현재 commit) — 7 invariant
- `core/wiki_generator.py` (현재 commit) — ingestion 경로
- `tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests` (현재 commit) — 5 invariant
- `CHANGELOG.md` (현재 commit) — publishable summary

본 문서는 historical reference 로 보존.

---

**End of postmortem.**
