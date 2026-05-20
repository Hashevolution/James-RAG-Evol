# STAGE 1B — 7 Invariant Test ↔ 청구항 한정 매핑

> 본 문서는 Hotfix PR #349 (`b89c099`, 2026-05-20) 로 `tests/test_relations_schema.py`
> 에 lock-in 된 7개 invariant 테스트를 STAGE 1B 임시명세서 청구항 한정 표현에
> 매핑한 작업 노트다.
>
> **목적**: 출원 재개 시 청구항 작성 시간을 단축. 본 매핑이 그대로 청구항 한정에
> 들어갈 수 있도록 미리 정리.
>
> **사용 대상**: `docs/patent/stage1b-cascade-spec-skeleton.md` §6 청구항.
>
> **상태**: PAUSE 중 작성 (skeleton 본문은 미수정).

---

## 0. 배경 — 왜 invariant 매핑이 중요한가

특허 청구항은 **"무엇이 발명인지"를 enumerated 방식으로 한정**해야 한다. 추상적
표현 ("적절한 신뢰도 함수") 은 신규성·진보성 거절 사유. 반면 invariant 테스트는
**수학적으로 입증 가능한 구체 한정** 이므로 청구항 본문으로 직접 변환 가능.

7 invariant lock-in 의 의미:
- 회귀 방지: 미래에 누가 clamped sum 으로 되돌리면 테스트 fail → 출원과 구현 영구
  정합 보장
- 청구항 진보성 증거: 각 invariant 가 prior art (Google US8682913B1, IBM
  US20180060733A1) 와 구분되는 한정점
- 정식 전환 시 변리사 검토 효율: 매핑 표가 있어 변리사는 "이 invariant 들이
  실제 구현됐고 테스트로 락인됐다"만 확인하면 됨

---

## 1. 7 Invariant → 청구항 한정 매핑표

| # | Invariant 테스트 | Prior Art 대비 차별 | 청구항 한정 (제안 표현) | 청구항 위치 |
|---|------------------|---------------------|------------------------|--------------|
| 1 | `test_single_source_returns_weight` | — (identity) | 단일 출처 sources = [{w}] 시 confidence = w 인 것을 특징으로 하는 방법. | 청구항 1 (a) 보조 한정 또는 종속항 |
| 2 | `test_two_sources_diverge_from_clamped_sum` | **Google US8682913B1 (clamped sum 류)**, IBM US20180060733A1 (학습 기반) | 두 출처 sources = [{w_1}, {w_2}] 에서 confidence = 1 - (1-w_1)(1-w_2) 이며, 이 값이 min(w_1+w_2, 1) 과 일반적으로 다른 것을 특징으로 하는 방법. | **청구항 1 (b) 본문** (가장 강한 차별) |
| 3 | `test_strong_corroboration_3_sources` | 디자인 메모 §3 예시 | 3 출처 w=[0.7, 0.7, 0.7] 시 confidence = 0.973 으로 도출되는 것을 특징으로 하는 방법. | **실시예 §8** 구체 수치 |
| 4 | `test_many_sources_asymptotic_not_saturated` | clamped sum, max, mean 모두 saturate | 5 출처 이상에서 confidence 가 1.0 으로 saturate 되지 않고 점근적으로 1 에 접근하되 1 미만의 값을 유지하는 것을 특징으로 하는 방법. | **청구항 6 추가 한정** (asymptotic property) |
| 5 | `test_monotone_adding_source_strictly_increases` | — (수학적 성질) | 임의의 sources 집합 S 에 새 출처 s' (weight > 0) 를 추가할 때 confidence 가 strictly 증가하는 것을 특징으로 하는 방법. | **청구항 6 (i)** strict 증가 단조성 |
| 6 | `test_monotone_removing_source_strictly_decreases` | — | sources 집합 S 에서 출처 s (weight > 0) 를 제거할 때 confidence 가 strictly 감소하는 것을 특징으로 하는 방법. | **청구항 6 (ii)** strict 감소 단조성 |
| 7 | `test_weight_clamped_to_unit_interval` | — (정의역 한정) | 각 출처의 weight 가 [0, 1] 구간으로 element-wise clamp 된 후 결합 함수에 입력되어, 잘못된 weight 값이 confidence 를 [0, 1] 밖으로 밀어내지 않는 것을 특징으로 하는 방법. | **청구항 7** weight ∈ [0, 1] |

---

## 2. 청구항 재작성 권고 (STAGE 1B skeleton §6 기준)

### 2.1 청구항 1 (방법 — 신뢰도 도출) 보강

기존 skeleton §6 청구항 1 + invariant 2 + invariant 1 결합:

```
청구항 1 (수정안):
지식 그래프 시스템에서 관계의 신뢰도를 도출하는 방법으로서,
(a) 상기 관계에 대해 출처 가중치 집합 sources = {(doc_id_i, w_i, role_i, ts_i)
    : i = 1..n} 을 유지하는 단계 — 여기서 각 w_i 는 LLM 출력 score 또는 정책
    기반 weight 로서, 각 element 가 [0, 1] 구간으로 clamp 된 후 결합 함수에
    입력됨;
(b) 상기 관계의 신뢰도 confidence 를 다음 폐쇄식 (closed-form) 에 의해
    도출하는 단계:
        confidence = 1 - Π_{i=1..n} (1 - w_i)
    이 공식은 학습 모델 추론을 거치지 않고, 출처가 1개일 때는 confidence = w_1
    (identity), 출처가 2개 이상일 때는 일반적으로 min(Σw_i, 1) 과 다른 값을
    돌려준다;
(c) 상기 도출된 신뢰도를 retrieval, scoring, 또는 reasoning 단계에서 사용
    하는 단계
를 포함하는, 신뢰도 도출 방법.
```

### 2.2 청구항 6 (종속 — 단조성) 보강

기존 청구항 6 + invariant 4/5/6 결합:

```
청구항 6 (수정안):
청구항 1 또는 청구항 2 에 있어서, 상기 도출 공식은 다음 성질을 가지는 것을
특징으로 하는 방법:
(i)   sources 집합 S 에 새 출처 s' (weight > 0) 를 추가할 때 confidence 가
      strictly 증가한다;
(ii)  sources 집합 S 에서 출처 s (weight > 0) 를 제거할 때 confidence 가
      strictly 감소한다;
(iii) 0 ≤ confidence < 1 — 임의 N >= 1 출처에 대해 confidence 는 1 에
      asymptotic 하게 접근하되 결코 1 과 같지 않다 (saturation 없음);
(iv)  weight 값이 [0, 1] 구간 밖이면 element-wise clamp 한 후 결합한다.
```

### 2.3 청구항 7 (종속 — 구체 수치) 신규

invariant 3 기반:

```
청구항 7 (신규):
청구항 1 에 있어서, sources = [{weight=0.7}, {weight=0.7}, {weight=0.7}] 에
대해 confidence 가 0.973 (소수 셋째자리에서 반올림) 으로 도출되는 것을
특징으로 하는 방법.
```

> 구체 수치 청구항은 진보성을 한정시키지만 거절 회피에 강함. 정식 전환 시 변리사
> 와 협의해 broad ↔ narrow 균형 결정.

---

## 3. 청구 제외 (false novelty 회피)

다음은 invariant 가 입증해도 청구하지 말 것:

- ❌ "단조 결합 함수" 만으로 broad 청구 — IBM US20180060733A1 의 학습 기반
  단조 함수도 단조라서 침범 가능
- ❌ "출처 다중 보유" 만으로 broad 청구 — Google US8682913B1 의 "corroborating
  facts" 와 충돌
- ❌ 0.6 임계값 자체 — magic number 라서 정식 전환 시 거절 가능. 대신 "임계값
  이상 통과" 의 범용 표현 권장

---

## 4. 청구 강조 (true novelty 강조)

다음은 invariant 가 직접 입증하는 강한 신규성:

- ✅ **폐쇄식 `1 - Π(1 - w_i)`** + **identity preservation** 결합 — 학습 기반
  fusion 과 명확 구분
- ✅ **strict 단조성** (증가·감소 모두) — Google clamped sum 은 saturate 후
  단조성 lose
- ✅ **asymptotic non-saturating** — clamped sum / max 와 명확 구분
- ✅ **`role='manual' & doc_id=null` cascade 면역** — 선행기술 0건 (skeleton
  청구항 4)
- ✅ **(s, p, o) triple-level diff cascade** — 선행기술 0건 (skeleton 청구항 5)

---

## 5. 출원 재개 시 작업 순서 (5분 가이드)

1. 본 매핑표 §2 의 청구항 1/6/7 재작성안을 skeleton §6 의 해당 청구항에 교체
2. skeleton §8 실시예에 invariant 3 (3 sources × 0.7 = 0.973) 추가
3. `tests/test_relations_schema.py:62-118` 의 7 invariant 를 명세서 §8 부록으로
   인용 (코드 블록째)
4. `core/relations_schema.py` 의 `compute_confidence_from_sources` 도크스트링
   인용 (Properties 부분)
5. 청구항 4 (manual 면역) + 청구항 5 (triple diff) 는 별도 검토 — `prior-art-1B.md`
   §5 의 mitigation 수정안 그대로 사용 가능

---

## 6. 검증 미완 항목 (Tier 2/3) — 정식 전환 전 보완 필요

- ⏳ Tier 2 (synthetic A/B): noisy-OR ↔ clamped sum 의 retrieval 차이 측정
- ⏳ Tier 3 (실 multi-source): production wiki 에 multi-source 누적 후 STEP 7
  bench 재캡처. 현재 production wiki = 278 files, 0 multi-source relations.

임시 출원에는 영향 없음. 정식 전환 (D+330일 ~ D+360일) 전에 보완.

---

**End of mapping.**

본 문서는 PAUSE 기간 중에도 cost 없이 (skeleton 본문 미수정) 청구항 작성
준비를 진행해두기 위한 sidecar 작업물. 재개 시 본 매핑을 skeleton 에 적용.
