# 시나리오 A 실행 — STAGE 1 + 1A + 1B 출원

> **PAUSE 해제 2026-05-20** — 사용자 "실행" 트리거로 시나리오 A 진행.
>
> **목표**: 3건 임시 출원 (STAGE 1 + 1A + 1B), 비용 약 5.4만 원, Show HN 2026-06-16 전 우선일 확보.
>
> **Framing 원칙** (postmortem PR #352 §10): 청구 reference 는 **현재 코드 + 테스트** (skeleton X, 디자인 메모 X).

---

## 0. 출원 순서 권고

| 순서 | Stage | 사유 |
|---|---|---|
| 1 | **STAGE 1B** (Cascade) | 가장 강한 IP (점수 4/5 ⭐⭐) + 12 invariant + 핫픽스 직후 = 자연 누설 카운터 |
| 2 | **STAGE 1** (Memory Loom) | 점수 4/5 ⭐, v0.1 부터 안정, 명확한 청구 구조 |
| 3 | **STAGE 1A** (Doc-source gate) | 점수 3/5 ⭐, 단일 함수, 가장 간단 (5분 가능) |

**병행 처리 권고**: KIPO Editor 에 3건을 시퀀스로 입력. 각 건 사이 30분 ~ 1시간 휴식.

총 예상 작업 시간: **6~8시간** (KIPO Editor 입력 + 도면 + 검증 + 결제 + 제출)

---

## 1. 출원 전 사용자 사전 준비 (필수, KIPO Editor 시작 전)

### 1.1 특허로 가입 (이미 완료 가정)
- [ ] 특허로 회원가입 (patent.go.kr)
- [ ] 출원인 코드 발급 받음 (개인 자동 발급)

### 1.2 인증서 등록
- [ ] 공동인증서 또는 금융인증서 보유
- [ ] 특허로 마이페이지에 인증서 등록 완료

### 1.3 KIPO Editor (PKEAPS) 설치
- [ ] PKEAPS 다운로드 + 설치
- [ ] DPI 호환성 설정 적용 (관리자 권한 + 시스템 DPI 무시)
- [ ] 첫 실행 + 인증서 로그인 확인

### 1.4 작업 폴더
- [ ] 바탕화면에 `특허출원_2026-05-20` 폴더 생성
- [ ] 하위 폴더: `STAGE_1/`, `STAGE_1A/`, `STAGE_1B/`

### 1.5 도면 작성 도구
- [ ] **draw.io** (https://app.diagrams.net) 또는 **excalidraw** (https://excalidraw.com) 접속 가능
- [ ] Mermaid live editor (https://mermaid.live) 접속 가능

### 1.6 결제 수단
- [ ] 특허로 사이트에서 신용카드 또는 계좌이체 결제 가능
- [ ] 또는 가상계좌 입금 가능

### 1.7 공지예외 신청서 (선택, 권장)
- [ ] 특허로 → 민원서식 → "공지예외 적용 받기 위한 취지의 서류 (별지 제27호)" 다운로드
- [ ] 출원 시 함께 첨부 (GitHub 공개 12개월 grace period 적용)

---

# 📋 STAGE 1B (Cascade) — 1순위

> Hotfix 1+2 (2026-05-20) 직후 출원. 12 invariant lock + 명세 ↔ 구현 ↔ 테스트 3자 정합.

## 1B-§1. 발명의 명칭

**한국어**: `출처 추적 기반 지식 그래프 자동 정리 시스템 및 방법`
**영문**: `System and Method for Knowledge Graph Auto-Cleanup via Provenance-Tracked Cascade`

## 1B-§2. 기술분야

```
본 발명은 인공지능 기반 지식 그래프 시스템에 관한 것으로, 보다 구체적으로는
관계(relation)가 다중 출처(sources) 배열을 보유하며, 출처 문서의 추가·삭제·
수정 시 신뢰도가 단조 수학적 성질을 만족하는 폐쇄식에 의해 도출·재계산되고,
출처 추적이 불가능한 수동 편집과 출처 추적이 가능한 자동 추출이 동일 데이터
구조에서 양립하도록 정리하는 시스템 및 방법에 관한 것이다.
```

## 1B-§3. 배경기술 (간략)

```
종래 지식 그래프 시스템 (Wikidata, ConceptNet, Microsoft GraphRAG, LlamaIndex
등) 은 다음 한계를 가진다:

1. 관계가 단일 신뢰도 스칼라만 보유 — 다수 출처가 동일 관계를 강화한 경우
   출처별 기여도를 분리할 수 없다.

2. 출처 가중치 결합에 흔히 쓰이는 max(w_i) 또는 mean(w_i) 또는 clamped sum
   min(Σw_i, 1) 방식은 다음 한계를 가진다:
   - max: 최대값 출처가 아닌 출처를 제거해도 신뢰도가 변하지 않음
   - mean: 약한 출처를 제거하면 평균이 떨어지는 비직관적 동작
   - clamped sum: 두 출처가 각 weight 0.7 만 모여도 1.0 으로 saturate
     되어 추가 출처의 기여를 감지할 수 없음

3. 수동 편집과 자동 추출의 혼재 시 운영자가 보강한 관계가 출처 문서 삭제
   cascade 에서 함께 사라지는 문제.

4. 출처 문서 수정 시 변경분만 surgical 하게 식별·반영할 수 없음 — LLM 재추출
   전체를 다시 시도하거나 stale 데이터를 방치한다.

선행 특허로는 IBM US20180060733A1 (학습 기반 confidence 산출), Google
US8682913B1 (다중 출처 corroborating facts) 가 있으나, (i) 폐쇄식 noisy-OR,
(ii) role 필드 기반 수동 편집 면역, (iii) (subject, predicate, object) 트리플
단위 diff cascade, (iv) 단조성 invariant 의 결합은 어디에도 없다.
```

## 1B-§4. 해결하고자 하는 과제

```
1. 출처 문서의 추가·삭제 시 신뢰도가 단조 비감소/비증가 성질을 만족하도록
   보장하는 신뢰도 도출 공식.
2. 다중 출처가 모여도 saturate 되지 않고 점근적으로 1 에 접근하되 1 미만의
   값을 유지하는 결합 함수.
3. 출처 문서 삭제 시 다른 출처가 강화한 관계는 살아남되 그 문서의 기여만
   surgical 하게 차감되는 cascade 절차.
4. 수동 편집(role="manual", doc_id=null) 출처가 자동 cascade 에서 면역으로
   보존되는 메커니즘.
5. 출처 문서 수정 시 (subject, predicate, object) 트리플 단위 diff 로
   변경분만 source 갱신하는 부분 cascade.
6. 두 문서가 동일 (subject, predicate, object) triple 을 추출했을 때 새 source
   가 기존 관계의 sources 배열에 append 되어 cross-doc 강화가 발현되는
   ingestion 경로.
```

## 1B-§5. 과제의 해결 수단

### 5.1 sources 배열 구조

각 관계(relation) 는 단일 confidence 스칼라가 아니라 출처 가중치 집합을 유지한다:

```
relation = {
    head, tail, predicate,
    sources: [
        {doc_id, weight, role, ts},  # role ∈ {extract, inverse, manual, legacy}
        ...
    ],
    confidence  # derived from sources
}
```

`role` 필드의 4 값 (참조: `core/relations_schema.py:38-46`):
- `extract`: LLM 이 doc 본문에서 추출한 source
- `inverse`: back-reference (역방향 자동 생성)
- `manual`: admin 이 그래프 에디터로 수동 입력 (`doc_id=null`)
- `legacy`: Phase A 마이그레이션 시 출처 추적 없이 back-fill 된 사전 마이그레이션 잔류

### 5.2 신뢰도 도출 공식 (noisy-OR 폐쇄식)

confidence 는 sources 배열로부터 다음 폐쇄식에 의해 도출된다 (`core/relations_schema.py::compute_confidence_from_sources`, Hotfix PR #349):

```
confidence = 1 − Π_{i=1..n} (1 − w_i)
```

여기서 각 w_i 는 sources 배열의 i 번째 항목의 weight 이며, [0, 1] 구간으로 element-wise clamp 된 후 결합 함수에 입력된다. 학습 모델 추론은 거치지 않는다.

### 5.3 단조성 invariant (12 테스트 lock-in)

본 공식 + ingestion 경로는 다음 invariant 를 만족한다 (`tests/test_relations_schema.py` 7개 + `tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests` 5개):

| Invariant | 검증 내용 |
|---|---|
| F1 | 단일 출처 sources=[{w}] → confidence = w (identity 보존) |
| F2 | 두 출처 sources=[{w1}, {w2}] → confidence ≠ min(w1+w2, 1) 일반적으로 |
| F3 | 3 출처 w=[0.7,0.7,0.7] → confidence = 0.973 |
| F4 | 5 출처 이상에서 1 미만, 점근적 접근 (saturate 없음) |
| F5 | sources 추가 (weight > 0) 시 confidence strictly 증가 |
| F6 | sources 제거 (weight > 0) 시 confidence strictly 감소 |
| F7 | weight 가 [0,1] 구간 밖이면 element-wise clamp |
| S1 | 두 번째 doc 가 동일 triple 추출 시 기존 sources 에 append (새 row 생성 X) |
| S2 | 정방향 + 역방향 양쪽 source append |
| S3 | (joint) 두 출처 × 0.7 → confidence ≈ 0.91 |
| S4 | 동일 doc_id 멱등성 (재업로드 안전) |
| S5 | 새 target 은 새 relation 행 |

### 5.4 Cascade 절차

문서 D 삭제 시 (`core/cascade.py::cascade_remove_doc_from_sources` line 93-163):

```
Procedure cascade_remove_doc(doc_entity_id, entity_root):
  for entity in entity_root.rglob("*.md"):
    fm = read_frontmatter(entity)
    for rel in fm.get("relations", []):
      srcs = rel.get("sources")
      # Filter: keep manual (doc_id-null), keep non-matching doc_ids
      kept = [s for s in srcs
              if not (s["doc_id"] == doc_entity_id
                      and s["role"] != "manual")]
      if len(kept) == 0:
        relations.remove(rel)  # 관계 자체 사라짐
      else:
        rel["sources"]    = kept
        rel["confidence"] = compute_confidence_from_sources(kept)
    write_frontmatter(entity, fm)
```

### 5.5 수동 편집 면역

`role="manual"` 인 sources 는 cascade 의 doc_id 매칭에서 제외됨. `doc_id=null` 이므로 어떤 문서 삭제에도 영향 받지 않음.

### 5.6 Diff Cascade (수정 처리)

문서 D 수정 시 (`core/cascade.py::diff_triples` line 373, `cascade_modify_doc` line 432):

```
old_triples = load_sidecar_json(D)   # 이전 추출 결과
new_triples = llm_extract(new_content)

removed = old_triples - new_triples
added   = new_triples - old_triples
kept    = old_triples ∩ new_triples

for rel in removed: drop_source(rel, D)   # cascade only removed
for rel in added:   add_source(rel, D)    # ingest only added
# kept: source 유지 (timestamp/weight/role 그대로)
```

### 5.7 Cross-doc Source Aggregation (Hotfix PR #350)

`core/wiki_generator.py::_merge_relations_into_existing_entity` 헬퍼:

```
- 매칭: (target_name, normalized_type) — `core.ontology.normalize_relation` 사용
- 멱등성: 동일 doc_id 중복 source 는 skip
- confidence: noisy-OR 로 재 derive
- 대칭: forward + inverse 양방향
```

## 1B-§6. 발명의 효과

```
1. 신뢰도가 단조 수학 성질을 만족 — 운영자가 출처 추가/제거 시 confidence 변화
   방향을 직관적으로 예측 가능.
2. 다중 출처가 saturate 되지 않고 점근적 — 5~50 출처 강화 시나리오에서도
   신호 변별력 유지.
3. 운영자 수동 편집의 영속성 보장 — 어떤 자동 cascade 에서도 휩쓸리지 않음.
4. 문서 수정 시 surgical update — LLM 재추출 비용을 변경분만큼만 부담.
5. 약한 corroboration 의 over-promotion 차단 — 그래프 traversal 게이트가
   정확하게 작동.
6. 12 invariant 회귀 즉시 검출 — 미래 코드 변경으로 보호 약화 방지.
```

## 1B-§7. 도면의 간단한 설명

- **도 1**: noisy-OR `1−Π(1−w_i)` 와 종래 max/mean/clamped sum 의 multi-source 영역 confidence 비교 그래프
- **도 2**: 출처 문서 삭제 시 cascade flow chart — `cascade_remove_doc_from_sources` 5 단계
- **도 3**: sources schema with role field — 4 role 의 cascade 면역/대상 분리 흐름
- **도 4**: 문서 수정 시 (s, p, o) triple-level diff cascade — old/new triple set 비교

## 1B-§8. 청구범위 (최종 안 — code grounded)

### 청구항 1 (방법 — 신뢰도 도출, 독립)
```
지식 그래프 시스템에서 관계(relation)의 신뢰도를 도출하는 방법으로서,
(a) 상기 관계에 대해 출처 가중치 집합 sources = {(doc_id_i, w_i, role_i, ts_i)
    : i = 1..n} 을 유지하는 단계로서, 각 w_i 는 LLM 출력 score 또는 정책
    기반 weight 이고, role_i 는 {extract, inverse, manual, legacy} 중 하나이며,
    각 w_i 는 [0, 1] 구간으로 element-wise clamp 된 후 결합 함수에 입력되는
    것을 특징으로 하는 단계;
(b) 상기 관계의 신뢰도 confidence 를 다음 폐쇄식 (closed-form) 에 의해
    도출하는 단계:
        confidence = 1 − Π_{i=1..n} (1 − w_i)
    여기서 학습 모델 추론을 거치지 않고, 출처가 1개일 때는 confidence = w_1
    (identity), 출처가 2개 이상일 때는 일반적으로 min(Σw_i, 1) 과 다른 값을
    돌려주는 것을 특징으로 하는 단계;
(c) 상기 도출된 신뢰도를 retrieval, scoring, 또는 reasoning 단계에서 사용하는
    단계
를 포함하는 것을 특징으로 하는, 신뢰도 도출 방법.
```

### 청구항 2 (방법 — Cascade, 독립)
```
청구항 1의 방법을 사용하는 지식 그래프 시스템에서 출처 문서 삭제 시 derived
knowledge 를 정리하는 방법으로서,
(a) 삭제 대상 문서의 doc_id 를 식별하는 단계;
(b) 모든 관계의 sources 배열에서 해당 doc_id 항목을 제거하되, role 이
    "manual" 인 항목은 보존하는 단계;
(c) 청구항 1의 도출 공식에 의해 신뢰도를 재계산하는 단계;
(d) sources 가 빈 관계는 그래프에서 제거하는 단계;
(e) 해당 문서가 attributes.source_document 로 지정된 엔티티 중 다른 엔티티의
    참조가 없는 엔티티를 제거하는 단계;
(f) 위 (b)~(e) 동작을 audit log 에 before/after sources 와 함께 기록하는
    단계
를 포함하는 것을 특징으로 하는, 지식 그래프 cascade 방법.
```

### 청구항 3 (시스템, 독립)
```
지식 그래프 시스템으로서,
(1) 출처 가중치 집합과 role 필드를 유지하는 관계 저장소,
(2) 청구항 1의 도출 공식을 적용하는 신뢰도 계산기,
(3) 청구항 2의 cascade 절차를 수행하는 cascade 엔진,
(4) 동일 (subject, predicate, object) triple 이 두 번째 문서에서 추출될 때
    기존 관계의 sources 에 새 source 를 append 하는 cross-doc aggregation
    모듈,
(5) 모든 cascade 이벤트를 기록하는 audit 로거
를 포함하는 것을 특징으로 하는, 출처 추적 기반 지식 그래프 시스템.
```

### 청구항 4 (종속 — 수동 면역)
```
청구항 2에 있어서, 상기 sources 배열의 각 항목은 role 필드와 doc_id 필드를
가지며, role 값이 "manual" 이고 doc_id 값이 null 인 항목은 (b)~(e) 단계의
어떤 cascade 동작에서도 제거되지 않고 보존되는 것을 특징으로 하는 방법.
```

### 청구항 5 (종속 — Diff Cascade)
```
청구항 2에 있어서, 출처 문서가 수정될 때:
(a) 직전 추출 결과를 (subject, predicate, object) 트리플 집합으로 sidecar
    파일에 보존하는 단계;
(b) 새 내용에서 동일 트리플 집합을 LLM 으로 추출하는 단계;
(c) 두 집합의 차집합 removed = old − new, added = new − old, 교집합
    kept = old ∩ new 를 산출하는 단계;
(d) removed 에 대해서만 청구항 2의 (b)~(e) 를 수행하고, added 에 대해서만
    source 추가를 수행하며, kept 에 대해서는 source 의 timestamp, weight,
    role 필드를 유지하는 단계
를 추가로 포함하는 것을 특징으로 하는, 부분 수정 cascade 방법.
```

### 청구항 6 (종속 — 단조성)
```
청구항 1에 있어서, 상기 도출 공식은 다음 성질을 가지는 것을 특징으로 하는
방법:
(i)   sources 집합 S 에 새 출처 s' (weight > 0) 를 추가할 때 confidence 가
      strictly 증가;
(ii)  sources 집합 S 에서 출처 s (weight > 0) 를 제거할 때 confidence 가
      strictly 감소;
(iii) 0 ≤ confidence < 1 — 임의 N ≥ 1 출처에 대해 confidence 는 1 에
      asymptotic 하게 접근하되 결코 1 과 같지 않다 (saturation 없음);
(iv)  weight 값이 [0, 1] 구간 밖이면 element-wise clamp 한 후 결합한다.
```

### 청구항 7 (종속 — Cross-doc aggregation)
```
청구항 3에 있어서, 상기 cross-doc aggregation 모듈은 (target_name,
normalized_type) 매칭에 의해 동일 관계를 식별하고, 동일 doc_id 의 중복
source 추가를 멱등으로 처리하며, 추가 후 청구항 1의 공식으로 confidence 를
재 derive 하고, 정방향 (subject, predicate, object) 과 역방향 (object,
inverse_predicate, subject) 양쪽에 대칭적으로 source 를 append 하는 것을
특징으로 하는 시스템.
```

### 청구항 8 (종속 — 구체 수치)
```
청구항 1에 있어서, sources = [{weight=0.7}, {weight=0.7}] 에 대해 confidence
가 0.91 (소수 둘째자리에서 반올림) 로 도출되고, sources = [{weight=0.7},
{weight=0.7}, {weight=0.7}] 에 대해 confidence 가 0.973 (소수 셋째자리에서
반올림) 으로 도출되는 것을 특징으로 하는 방법.
```

### 청구항 9 (종속 — Audit)
```
청구항 3에 있어서, 상기 audit 로거는 cascade 이벤트마다 다음을 기록하는
것을 특징으로 하는 시스템:
- 이벤트 종류 (file_delete / file_modify / manual_edit / ingestion);
- 영향 받은 entity 수, recompute 된 relation 수, drop 된 relation 수,
  orphan entity 수;
- 각 영향 받은 관계의 before/after sources 배열;
- 이벤트 timestamp.
```

### 청구항 10 (종속 — 임계값 게이팅)
```
청구항 1에 있어서, 상기 도출된 confidence 가 시스템 임계값 (예: 0.6) 이상인
관계만 그래프 traversal 또는 답변 context 포함에 사용되어, 약한 출처 다수의
조합으로 부풀린 confidence 가 차단되는 것을 특징으로 하는 방법.
```

## 1B-§9. 실시예 (간략)

`core/relations_schema.py:52-69`:
```python
def compute_confidence_from_sources(sources: list | None) -> float:
    """Noisy-OR over per-source weights."""
    if not sources:
        return 0.0
    p = 1.0
    for s in sources:
        w = s.get("weight")
        if isinstance(w, (int, float)):
            w_clip = max(0.0, min(1.0, float(w)))
            p *= (1.0 - w_clip)
    return round(1.0 - p, 4)
```

(이외 `core/cascade.py::cascade_remove_doc_from_sources`, `core/wiki_generator.py::_merge_relations_into_existing_entity`, `tests/test_relations_schema.py` 7 invariant, `tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests` 5 invariant 인용)

## 1B-§10. 요약

```
본 발명은 지식 그래프 시스템에서 각 관계가 단일 신뢰도 스칼라가 아닌 출처
가중치 집합 (doc_id, weight, role, ts) 을 유지하고, 신뢰도를 폐쇄식 noisy-OR
1 − Π(1 − w_i) 로 도출하며, 출처 문서의 추가·삭제·수정 시 단조 비감소/비증가
성질을 보장하면서 cascade 하는 방법 및 시스템에 관한 것이다. role="manual"
출처는 cascade 면역으로 보존되고, 문서 수정 시 (s, p, o) 트리플 단위 diff
로 변경분만 처리되며, 동일 triple 의 cross-doc 추출은 기존 관계의 sources 에
멱등으로 append 되어 점근적 confidence 증가를 발현한다. 12 invariant 테스트로
회귀 차단.
```

대표도: **도 2** (cascade flow chart)

---

# 📋 STAGE 1 (Memory Loom 5-gate) — 2순위

## 1-§1. 발명의 명칭

**한국어**: `다단계 게이트 기반 메모리 저장 검증 시스템 및 방법`
**영문**: `Method and System for Multi-Gate Memory Storage Verification`

## 1-§2. 기술분야

```
본 발명은 대화형 인공지능 시스템의 장기 기억 저장 검증에 관한 것으로, 보다
구체적으로는 LLM 출력 또는 외부 추출 결과를 장기 기억에 영구 저장하기 전에
신뢰도, 온톨로지 정합, 세션 쓰기율, 중복, 충돌의 5 단계 게이트를 순차 적용
하여 검증된 결과만 저장하는 시스템 및 방법에 관한 것이다.
```

## 1-§3. 배경기술 (간략)

```
기존 대화형 AI 시스템 (OpenAI ChatGPT, Anthropic Claude, LangChain memory 등)
은 운영 단계에서 메모리에 저장할지 여부를 단일 confidence threshold 또는
사용자 명시 명령으로 결정한다. 이러한 단순 접근은:

1. 동일 사실의 중복 저장으로 메모리 saturation;
2. 동일 entity-relation 에 대한 모순 사실의 동시 저장;
3. 세션 내 무제한 쓰기로 인한 노이즈 증가;
4. 온톨로지에 정의되지 않은 관계의 무차별 저장
의 문제를 야기한다. 본 발명은 이를 단일 임계값이 아닌 5 단계의 순차 게이트로
해결한다.
```

## 1-§4. 해결하고자 하는 과제

```
1. 단일 confidence 임계값만으로는 신뢰성 있는 메모리 저장이 어려운 문제 해결.
2. 동일 entity+relation 의 모순 사실 동시 저장 (충돌) 자동 검출.
3. 동일 triple 의 단기 중복 자동 차단.
4. 세션 단위 쓰기율 제한으로 시스템 saturation 방지.
5. 거부 사유 별 독립 audit log 기록.
```

## 1-§5. 과제의 해결 수단 — 5 게이트 (참조: `core/memory/loom.py:80-149`)

```
저장 시도되는 결과 result = {entity_id, relation_type, tail_id, confidence,
ontology_valid, text} 에 대해 다음 5 게이트를 순차 적용:

Gate 1 — Confidence Threshold:
  if confidence < MEMORY_CONFIDENCE_TH (= 0.75): 거부 (gate1_fail)

Gate 2 — Ontology Validity:
  if not ontology_valid: 거부 (gate2_fail)
  (사전 정의된 관계 타입과 entity 타입 조합 검증)

Gate 3 — Session Write Rate:
  if session_write_count >= MAX_WRITES_PER_SESSION (= 3): 거부 (gate3_limit)

Gate 4 — Dedup:
  triple_key = f"{entity_id}::{relation_type}::{tail_id}"  # 또는 text hash fallback
  if triple_key in dedup_buffer (deque(maxlen=MEMORY_DEDUP_WINDOW=100)):
    거부 (gate4_dedup)

Gate 5 — Conflict Detection:
  base_key = f"{entity_id}::{relation_type}"
  if base_key in conflict_index:
    existing_tail = conflict_index[base_key]["tail_id"]
    if existing_tail != tail_id:                # 동일 entity+relation, 다른 tail
      거부 (gate5_conflict)
    if |confidence − existing_confidence| > CONFLICT_CONFIDENCE_DIFF (= 0.3):
      거부 (gate5_conf_conflict)

  전부 통과 → 저장 + dedup_buffer / conflict_index 갱신 + session_write_count 증가
```

각 거부는 audit log 에 `gate{N}_*` step 으로 기록.

## 1-§6. 발명의 효과

```
1. 5 게이트 순차 적용으로 단일 임계값 대비 false positive 저장 감소.
2. 세션 단위 쓰기율 제한으로 시스템 saturation 방지 (3회/세션).
3. 100-window dedup buffer 로 단기 중복 자동 차단.
4. 동일 entity+relation 의 모순 tail 또는 0.3 이상 confidence 차이를
   자동 충돌로 검출하여 데이터 무결성 보장.
5. 각 거부 사유 별 독립 audit log 로 메모리 거부 원인 추적 가능.
```

## 1-§7. 도면의 간단한 설명

- **도 1**: 5 게이트 순차 적용 순서도
- **도 2**: 각 게이트 임계값 표 + 거부 메시지 형식
- **도 3**: Gate 5 충돌 검출 — tail 불일치 / confidence 차이 2 케이스 흐름
- **도 4**: Audit log 구조 (gate{N}_* step + reason + timestamp)

## 1-§8. 청구범위 (최종 안)

### 청구항 1 (방법, 독립)
```
대화형 인공지능 시스템의 장기 기억 저장 검증 방법으로서,
저장 시도되는 결과 result = {entity_id, relation_type, tail_id, confidence,
ontology_valid, text} 에 대해 다음 5 게이트를 순차로 적용하는 단계를
포함하고, 어느 게이트에서라도 거부되면 저장하지 않고 audit log 에 거부 사유를
기록하는 것을 특징으로 하는 방법:
(a) Gate 1 — 상기 confidence 가 임계값 (default 0.75) 미만이면 거부;
(b) Gate 2 — 상기 ontology_valid 가 False 이면 거부;
(c) Gate 3 — 현재 세션의 저장 횟수가 최대 (default 3) 이상이면 거부;
(d) Gate 4 — 상기 (entity_id, relation_type, tail_id) 트리플 키가 최근 N
    (default 100) 개의 저장 이력에 존재하면 거부;
(e) Gate 5 — 동일 (entity_id, relation_type) 키의 기존 저장 항목이 존재하고,
    (i) 기존 tail_id 와 신규 tail_id 가 다른 경우 또는 (ii) 두 항목의
    confidence 차이가 임계값 (default 0.3) 을 초과하는 경우 거부;
(f) 전부 통과 시 저장 + dedup 인덱스 + 충돌 인덱스 갱신 + 세션 카운터 증가.
```

### 청구항 2 (시스템, 독립)
```
대화형 인공지능 시스템의 장기 기억 저장 검증 시스템으로서,
- (1) 청구항 1의 5 게이트를 순차 적용하는 게이트 엔진,
- (2) 최근 N 개의 저장 트리플 키를 보존하는 deque 기반 dedup 버퍼,
- (3) (entity_id, relation_type) 키 별 최신 저장 항목을 추적하는 충돌
  인덱스,
- (4) 세션 단위 저장 카운터,
- (5) 각 게이트의 거부 사유 별 독립 step 명 (gate1_fail / gate2_fail /
  gate3_limit / gate4_dedup / gate5_conflict / gate5_conf_conflict) 으로
  기록하는 audit 로거
를 포함하는 것을 특징으로 하는 시스템.
```

### 청구항 3 ~ 7 (종속)
```
청구항 3: 청구항 1에 있어서, Gate 1 의 임계값이 0.75, Gate 3 의 한도가 3,
   Gate 4 의 윈도우가 100, Gate 5 의 confidence 차이 임계값이 0.3 인 것을
   특징으로 하는 방법.

청구항 4: 청구항 1에 있어서, Gate 4 의 트리플 키는 (entity_id,
   relation_type, tail_id) 3-tuple 의 문자열 연결이며, 어느 필드가 결측인
   경우 result 의 text 필드의 MD5 해시로 대체되는 것을 특징으로 하는 방법.

청구항 5: 청구항 1의 Gate 5 에 있어서, 동일 (entity_id, relation_type) 키의
   기존 항목이 존재하더라도 양쪽 tail_id 가 모두 비어 있으면 충돌로 간주하지
   않는 것을 특징으로 하는 방법.

청구항 6: 청구항 2의 dedup 버퍼는 collections.deque 자료구조이며 maxlen 이
   100 인 것을 특징으로 하는 시스템.

청구항 7: 청구항 2의 audit 로거는 시스템 JSONL 로그 파일에 기록함과 동시에
   SQLite audit_log 테이블에 mirror 하는 것을 특징으로 하는 시스템.
```

### 청구항 8 ~ 10 (종속 — 운영 동작)
```
청구항 8: 청구항 1에 있어서, 5 게이트의 적용 순서가 (a) → (b) → (c) → (d)
   → (e) 로 고정되어, 비용이 낮은 게이트 (confidence 비교) 가 먼저 적용되어
   비용이 높은 게이트 (충돌 인덱스 lookup) 에 도달하지 않도록 하는 것을
   특징으로 하는 방법.

청구항 9: 청구항 2의 세션 카운터는 서버 재시작 시 0 으로 초기화되며 세션 간
   영속화되지 않는 것을 특징으로 하는 시스템.

청구항 10: 청구항 7의 audit log entry 는 {time ISO, level, step
   (gate{N}_* 또는 store_ok), detail (300자 제한)} 의 4 필드를 포함하는 것을
   특징으로 하는 시스템.
```

## 1-§9. 실시예 — `core/memory/loom.py:80-149` 인용

(코드 전체 인용 — KIPO Editor 의 §발명을 실시하기 위한 구체적인 내용 에 코드 블록으로 삽입)

## 1-§10. 요약

```
본 발명은 대화형 AI 시스템의 장기 기억 저장에 있어서 confidence 임계값,
ontology 정합, 세션 쓰기율, 트리플 dedup, 충돌 검출 의 5 단계 게이트를 순차
적용하여 검증된 결과만 저장하는 방법 및 시스템이다. 각 게이트의 거부는
독립 audit log step 으로 기록되며, 단일 임계값 대비 false positive 저장 및
모순 데이터 동시 저장을 방지한다.
```

대표도: **도 1** (5 게이트 순서도)

---

# 📋 STAGE 1A (Doc-source gate) — 3순위

## 1A-§1. 발명의 명칭

**한국어**: `출처 비대칭성 기반 지식 그래프 탐색 게이트 시스템 및 방법`
**영문**: `Asymmetric Provenance Gate for Knowledge Graph Traversal`

## 1A-§2. 기술분야

```
본 발명은 지식 그래프 탐색(graph traversal) 에 관한 것으로, 보다 구체적
으로는 문서 entity 의 외향 엣지(outgoing edge) 가 "그 문서가 target entity 의
출처(source) 인 경우에만 통과 가능" 한 비대칭 게이트를 적용하여, 문서가
mention 만 한 entity 로의 spurious cross-domain path 를 차단하는 시스템 및
방법에 관한 것이다.
```

## 1A-§3. 배경기술 (간략)

```
기존 graph traversal (Microsoft GraphRAG, RAG-Fusion, KGAT 등) 은 문서
entity 의 모든 outgoing edge 를 동일하게 처리하여, 문서가 본질적 내용을
다루는 entity 와 단순 mention 만 한 entity 를 구분하지 못한다. 결과적으로:

  query "Palantir" → Palantir → PLTR_03(doc) → Morgan Stanley → 비트코인

같은 cross-domain spurious path 가 발생한다. PLTR_03 문서는 Morgan Stanley 를
mention 만 하고 Morgan Stanley 의 source 가 아니므로 (Morgan Stanley 의
sources 는 09_MorganStanley_* 파일들), 위 traversal 은 잘못된 추론을
유발한다.

기존 metadata 필터링은 양방향 대칭적이라 본 발명의 비대칭성을 활용하지 못한다.
```

## 1A-§4. 해결하고자 하는 과제

```
1. 문서 entity 의 outgoing edge 중 "본질적 (source 관계)" 와 "비본질적
   (mention 관계)" 의 구분.
2. 위 구분을 후처리 가 아니라 traversal 시점의 hop 게이트로 적용.
3. 비문서 entity → entity 간 inferred edge 는 영향 받지 않는 비대칭 게이팅.
4. 검증된 효과 (Palantir → 비트코인 spurious path 차단, baseline 12/13 query
   보존) 의 재현.
```

## 1A-§5. 과제의 해결 수단 (참조: `core/graph_engine.py:44-105`)

```
DFS traversal 중 각 hop (source_entity → target_entity) 에 대해 다음 게이트
를 적용:

def _doc_outgoing_hop_valid(source_entity, target_entity) -> bool:
    if source_entity.entity_type != "document":
        return True   # rule only applies when source is a document

    src_name = source_entity.name.strip()  # 확장자 없는 stem
    target_sources = target_entity.sources  # 확장자 포함 filename list

    for s in target_sources:
        if src_name in s:   # stem-in-filename match
            return True

    return False  # 문서가 target entity 의 source 가 아님 → hop 차단

비대칭성: 위 규칙은 (a) source = document 인 경우에만 적용. (b) entity →
document, (c) entity → entity 는 모두 통과. 따라서 그래프 backbone 의 78% 인
entity-entity 추론 edge (conf 0.7) 는 영향 받지 않음.
```

## 1A-§6. 발명의 효과

```
1. Spurious cross-domain path 차단 — Palantir → 비트코인 같은 무관계
   경로 제거.
2. 비대칭 적용으로 over-cut 회피 — entity → entity inferred edge 는
   영향 받지 않음.
3. Baseline 12/13 query 보존 — 검증된 효과 (PR #139 회귀 테스트).
4. Source vs target asymmetry 활용으로 단순 metadata 필터링과 차별.
```

## 1A-§7. 도면의 간단한 설명

- **도 1**: Palantir → 비트코인 spurious path 의 hop 분석 (type-a vs type-b)
- **도 2**: `_doc_outgoing_hop_valid` 순서도
- **도 3**: source 와 target 의 비대칭 (entity.name stem vs entity.sources filename)
- **도 4**: 게이트 적용 전후 graph traversal 비교 (path 수, hop 수)

## 1A-§8. 청구범위 (최종 안)

### 청구항 1 (방법, 독립)
```
지식 그래프 탐색 방법으로서,
(a) 그래프 노드 N1 → N2 의 hop 을 평가하는 단계;
(b) N1 의 entity_type 이 "document" 인 경우에만, N1.name 의 stem 이 N2.sources
    배열의 어느 항목에도 부분 일치하지 않으면 해당 hop 을 차단하는 단계;
(c) N1 의 entity_type 이 "document" 아닌 경우 또는 N2.sources 가 N1.name
    stem 을 포함하는 경우 hop 을 허용하는 단계
를 포함하는 것을 특징으로 하는, 출처 비대칭 게이트 기반 지식 그래프 탐색
방법.
```

### 청구항 2 (시스템, 독립)
```
지식 그래프 탐색 시스템으로서,
(1) 각 entity 의 entity_type, name, sources 필드를 보유하는 그래프 저장소,
(2) DFS 또는 BFS 탐색 엔진,
(3) 청구항 1의 hop 게이트를 매 hop 마다 적용하는 hop validator
를 포함하는 것을 특징으로 하는 시스템.
```

### 청구항 3 ~ 7 (종속)
```
청구항 3: 청구항 1에 있어서, N1.name 의 stem 과 N2.sources 항목의 매칭이
   문자열 부분 포함 (substring) 으로 수행되는 것을 특징으로 하는 방법.

청구항 4: 청구항 1에 있어서, N2 가 결측이거나 N2.sources 가 list 가 아니거나
   N1.name 이 빈 문자열인 경우, 게이트가 permissive 로 동작하여 hop 을
   차단하지 않는 것을 특징으로 하는 방법 (다른 게이트가 처리하도록 위임).

청구항 5: 청구항 2에 있어서, hop validator 가 N1.entity_type == "document"
   인 hop 에만 적용되고, entity → entity inferred edge 에는 적용되지 않아
   비대칭 게이팅을 실현하는 것을 특징으로 하는 시스템.

청구항 6: 청구항 1에 있어서, entity 의 sources 필드는 파일명 (확장자 포함)
   의 list 이고, entity 의 name 은 파일명에서 확장자를 제거한 stem 이며,
   두 형식의 비대칭으로 인해 substring 매칭이 필요한 것을 특징으로 하는
   방법.

청구항 7: 청구항 2에 있어서, hop validator 가 audit log 에 게이트 통과/차단
   결과를 hop 별로 기록하는 것을 특징으로 하는 시스템.
```

### 청구항 8 ~ 10 (종속 — 응용)
```
청구항 8: 청구항 1의 방법이 retrieval-augmented generation (RAG) 의
   graph-RAG 단계에 적용되어, 문서 entity 가 mention 만 한 entity 로의 path
   가 답변 context 에 포함되지 않는 것을 특징으로 하는 방법.

청구항 9: 청구항 1의 방법이 confidence 임계값 게이트 (CONFIDENCE_THRESHOLD)
   및 깊이 게이트 (MAX_DEPTH) 와 함께 순차 적용되는 것을 특징으로 하는 방법.

청구항 10: 청구항 1의 방법 적용 결과 spurious path 가 차단되어도 baseline
   query 의 N/M (예: 12/13) 가 보존되는 것을 특징으로 하는 방법.
```

## 1A-§9. 실시예 — `core/graph_engine.py:44-105` 인용

## 1A-§10. 요약

```
본 발명은 지식 그래프 탐색에 있어서 문서 entity 의 outgoing hop 만 비대칭으로
게이팅하는 방법이다. 문서 N1 의 이름(확장자 제거 stem)이 target entity
N2 의 sources 배열의 어느 파일명(확장자 포함)에도 부분 일치하지 않으면 해당
hop 을 차단하여, 문서가 mention 만 한 entity 로의 spurious cross-domain
path 를 제거한다. 비문서 entity 의 outgoing hop 은 영향 받지 않아 over-cut 을
회피한다.
```

대표도: **도 2** (게이트 순서도)

---

# 🎨 도면 작성 가이드

각 stage 마다 4 매 = **총 12 매** 의 도면 필요. 권장 도구:

| 도면 유형 | 도구 | 예시 |
|---|---|---|
| 그래프 / 플로우차트 | **mermaid.live** 또는 **draw.io** | `flowchart`, `sequenceDiagram` |
| 비교 그래프 (도 1 of STAGE 1B) | matplotlib (Python) 또는 draw.io | confidence vs source count |
| 데이터 구조 | draw.io class diagram 또는 mermaid `classDiagram` | sources schema |
| 표 / 매트릭스 | draw.io 의 grid 또는 직접 HTML 캡처 | 임계값 표, 거부 사유 표 |

작업 흐름:
1. mermaid 소스 작성 (또는 draw.io 에서 직접 그리기)
2. PNG 또는 PDF 로 export
3. 저장 위치: `STAGE_{N}/figures/figure-{1-4}.{png,pdf}`
4. KIPO Editor 도면 첨부 단계에서 업로드

---

# 📋 KIPO Editor 입력 Checklist (각 stage 공통)

각 stage 마다 다음 순서로:

- [ ] 1. 새 문서 → 특허출원 선택
- [ ] 2. 식별항목 선택: 도면만 체크 (선행기술문헌 / 산업상이용가능성 / 수탁번호 / 청구범위제출유예 모두 체크 해제)
- [ ] 3. 【발명의 명칭】 입력 (한국어 + 영문)
- [ ] 4. 【기술분야】 입력
- [ ] 5. 【배경기술】 입력
- [ ] 6. 【발명의 내용】 → 【해결하고자 하는 과제】 입력
- [ ] 7. 【발명의 내용】 → 【과제의 해결 수단】 입력 (가장 분량 큰 섹션)
- [ ] 8. 【발명의 내용】 → 【발명의 효과】 입력
- [ ] 9. 【도면의 간단한 설명】 입력
- [ ] 10. 【발명을 실시하기 위한 구체적인 내용】 입력 (코드 인용 + 실시예)
- [ ] 11. 【청구범위】 → 청구항 1~10 입력 (각각 별도 박스)
- [ ] 12. 【요약서】 → 【요약】 + 【대표도】 입력
- [ ] 13. **검증** (`도구 → 검증` 또는 F7) → 오류 0개 확인
- [ ] 14. **저장** (`Ctrl + S`) → `STAGE_{N}/spec.kipo`
- [ ] 15. **통합서식 작성기** 에서 특허출원서 작성 + 명세서 첨부 + 도면 첨부 + 공지예외 신청서 첨부
- [ ] 16. **전자출원** 모듈에서 인증서 로그인 → 패키지 검증 → 수수료 확인 → 제출
- [ ] 17. **출원번호 수령** + 접수증 PDF 보관 (`STAGE_{N}/receipt.pdf`)
- [ ] 18. `docs/patent/` 디렉토리에 출원번호 + 접수증 기록 (PII 제외)

---

# 💰 비용

| 항목 | 단가 | 3건 합계 |
|---|---|---|
| 특허출원료 (개인 70% 감면) | 1.8만 원 | 5.4만 원 |
| 심사청구료 (출원과 동시 청구 권장, 청구항 10개 기준) | 약 9만 원 (개인 감면) | 27만 원 |
| 공동인증서 사용 | 0원 | 0원 |
| **즉시 비용 (출원료만)** | — | **5.4만 원** |
| 심사청구료는 1년 이내 별도 결제 가능 (옵션) | — | (별도) |

**권고**: 출원료만 즉시 결제 (5.4만 원). 심사청구료는 1년 grace 내 별도 결제 — 정식 전환 결정 시 함께.

---

# 🗓️ 예상 일정

| 일자 | 작업 |
|---|---|
| 2026-05-20 (오늘) | 본 실행 자료 commit + push. 사용자 KIPO Editor 환경 점검. |
| 2026-05-21 ~ 22 | STAGE 1B 명세서 + 도면 작성. KIPO Editor 입력. 검증 통과. |
| 2026-05-23 | STAGE 1B 출원 제출. 출원번호 수령. |
| 2026-05-24 ~ 25 | STAGE 1 명세서 + 도면. 입력. 출원 제출. |
| 2026-05-26 ~ 27 | STAGE 1A 명세서 + 도면. 입력. 출원 제출. |
| 2026-05-28 ~ 06-15 | 보강 작업 / 추가 stage 검토 / Show HN 준비 |
| 2026-06-16 | Show HN — 3건 출원 완료 후 글로벌 노출 |

---

# 📑 출원 후 후속

- [ ] 각 출원번호 + 접수증을 `docs/patent/receipts/` 에 보관
- [ ] `HANDOVER.md` §0 에 출원 결과 기록 (출원번호, 일자, 비용)
- [ ] Show HN 본문에 "한국 특허 출원 진행 중 (Stage 1, 1A, 1B)" 명시
- [ ] 모니터링: 분기별 KIPRIS 재검색 (경쟁사 추적)
- [ ] 1년 후 (2027-05) 정식 전환 결정 — 사용 수치 / 사업화 진척에 따라

---

**End of execution plan.**

본 문서는 시나리오 A 실행의 단일 truth source. 작업 진행 시 본 문서 § 별로 참조. 추가 stage (Tier 2) 출원 결정 시 동일 양식으로 별도 실행 문서 작성.
