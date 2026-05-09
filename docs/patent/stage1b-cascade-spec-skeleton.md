# [임시명세서 초안] Provenance Cascade + Log-sum Confidence

> 본 문서는 STAGE 1B (신규 2026-05-10 추가, 점수 4/5 ⭐⭐) 임시명세서 작성을 위한 skeleton입니다.
> 특허로(patent.go.kr) 전자출원 시 본 문서를 기반으로 PDF·hwp로 전환하여 첨부하십시오.
> 작성 시 [TODO] 마커를 모두 제거·채워주세요.
>
> **참고 자료**: `docs/design/v0.3-knowledge-cascade.md` (~430줄 설계 명세) — 본 임시명세서의 도면 + 실시예 원본.

---

## 발명의 명칭
**출처 추적 기반 지식 그래프 자동 정리 시스템 및 방법**
(영문: System for Knowledge Graph Auto-Cleanup via Provenance-Tracked Cascade)

## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]

## 공지예외 주장
- 공개일자: 2026-05-09 (`docs/design/v0.3-knowledge-cascade.md` 첫 commit)
- 공개매체: GitHub public repository (https://github.com/Hashevolution/James-RAG-Evol)
- 공개주체: 발명자 본인
- 공지예외 만료일: **2027-05-08**
- 증빙: `docs/patent/disclosure_log.txt` (B 후보 항목)

---

## 1. 기술 분야

본 발명은 인공지능 기반 지식 그래프 시스템에 관한 것으로, 보다 구체적으로는 출처 문서가 추가·삭제·수정될 때 그로부터 추출된 엔티티와 관계의 신뢰도 및 존재 여부를 자동으로 정리하는 시스템 및 방법에 관한 것이다.

## 2. 배경 기술

### 2.1 기존 지식 그래프 cascade의 한계

기존 지식 그래프 시스템 (Wikidata, ConceptNet, Microsoft GraphRAG, LlamaIndex 등) 은 다음 한계를 가진다:

1. **단일 confidence 값**: 각 관계(relation)는 하나의 신뢰도 스칼라만 가지며, 여러 출처가 같은 관계를 강화한 경우 그 출처별 기여도를 분리할 수 없다.

2. **출처 삭제 시 부정확한 cascade**:
   - `max(weights)` 방식: 최대값 출처가 아닌 출처를 제거해도 신뢰도가 변하지 않음 (false stability)
   - `mean(weights)` 방식: 임의 변화 — 약한 출처를 제거해도 평균이 떨어짐 (false weakening)
   - 단일 confidence 방식: 그 자체로 출처 추적 불가

3. **수동 편집과 자동 추출의 혼재**: 운영자가 수동으로 추가한 관계가 출처 문서 삭제 cascade에 휩쓸려 사라지는 문제. 인간 개입의 영속성 보장 메커니즘 부재.

4. **수정 cascade 부재**: 문서 내용이 수정됐을 때, 그 문서로부터 추출된 관계 중 어떤 것이 변했는지 surgical하게 식별하지 못해 통째로 재추출하거나 stale 데이터를 방치한다.

### 2.2 본 발명이 다루는 구체 시나리오

운영자가 분기 보고서 PDF (예: `report_2026Q1.pdf`)를 업로드한다. 시스템은 LLM으로 엔티티와 관계를 추출해 wiki에 저장한다. 같은 관계가 분기마다 다른 보고서에서 강화되며 신뢰도가 누적된다.

- (i) `report_2026Q1.pdf`를 삭제하면 그 문서가 기여한 신뢰도만큼만 정확히 차감되어야 한다.
- (ii) 다른 분기 보고서에서도 동일 관계를 지지한 경우, 관계 자체는 살아남되 신뢰도만 감소해야 한다.
- (iii) 운영자가 수동 편집으로 추가한 관계는 어떤 출처 문서가 삭제되어도 영향을 받지 않아야 한다.
- (iv) 같은 파일명으로 수정된 PDF가 재업로드되면, 변경된 부분에 대응되는 관계만 재처리되어야 한다.

기존 시스템은 (i)~(iv) 어느 것도 정확히 보장하지 못한다.

## 3. 해결하고자 하는 과제

1. 출처 문서 삭제 시 신뢰도가 정확히 단조 감소하도록 보장하는 신뢰도 도출 공식
2. 출처 문서 삭제 시 derived knowledge (추출된 엔티티 + 관계)를 surgical하게 정리하는 cascade 방법
3. 수동 편집 source가 자동 cascade에서 면역 (immune) 으로 보존되는 메커니즘
4. 출처 문서 수정 시 변경분만 surgical하게 반영하는 diff cascade

## 4. 과제의 해결 수단

### 4.1 신뢰도 도출 공식 (Log-sum)

본 발명은 각 관계(relation)가 단일 신뢰도 스칼라가 아닌, **출처 가중치 집합 (provenance weight set)** 을 가지도록 한다:

```
relation = {
    head, tail, predicate,
    sources: [{doc_id, weight, role, ts}, ...]
}
```

신뢰도는 출처 가중치 집합으로부터 다음 공식에 의해 도출된다:

```
confidence = 1 - Π(1 - w_i)        for i in sources
```

이는 확률론적 OR (probabilistic OR) 또는 log-sum 결합으로, 다음 성질을 가진다:

- **단조 증가 (출처 추가 시)**: 새로운 출처를 추가하면 신뢰도가 항상 증가하거나 같다 (1 - (1-c) × (1-w) ≥ 1 - (1-c))
- **단조 감소 (출처 제거 시)**: 어떤 출처를 제거해도 신뢰도가 항상 감소하거나 같다
- **경계**: 0 ≤ confidence ≤ 1
- **수렴**: 출처가 무한히 많아도 1을 초과하지 않음

기존 `max`, `mean` 공식은 단조성을 보장하지 못한다 (도면 1: 비교 그래프 참조).

### 4.2 출처 추적 Cascade 방법 (도면 2 참조)

문서 D를 삭제하는 경우의 처리 흐름:

```
Procedure delete_doc(doc_filename):
  doc_entity_id = find_doc_entity_by_source(doc_filename)

  // Step 1: scan all entities for source mentioning doc D.
  affected_entities = scan_all_entities_for_source(doc_entity_id)

  // Step 2: for each affected relation, drop D from sources.
  for entity in affected_entities:
    for relation in entity.relations:
      relation.sources = [s for s in relation.sources
                          if s.doc_id != doc_entity_id]
      relation.confidence = log_sum(relation.sources)
      if not relation.sources:
        entity.relations.remove(relation)

  // Step 3: orphan entity sweep — entities only referenced by D.
  for entity in entities_with_source_document(doc_filename):
    if not has_incoming_references(entity.id):
      delete_entity(entity)

  // Step 4: vector chunks + doc entity + disk file
  vector_store.delete_by_source(doc_filename)
  delete_entity(doc_entity_id)
  os.remove(uploads_path / doc_filename)

  // Step 5: audit log
  audit("/admin/files/delete", details={
    "filename": doc_filename,
    "doc_entity": doc_entity_id,
    "affected_relations": <count>,
    "orphaned_entities": <count>,
  })
```

핵심 특징:
- (a) confidence 재계산은 도출 공식에 의해 자동
- (b) sources가 비면 관계 자체 삭제 (orphan relation 방지)
- (c) 다른 entity에서만 참조되는 entity는 보존 (orphan entity sweep 통과)
- (d) audit log로 모든 cascade 이벤트 기록

### 4.3 수동 편집 면역 (도면 3 참조)

각 출처 항목은 `role` 필드를 가진다:

```
sources: [
    {doc_id: "...", weight: 0.7, role: "extract", ts: "..."},  // LLM 추출
    {doc_id: "...", weight: 0.7, role: "inverse", ts: "..."},  // 역방향 backfill
    {doc_id: null,  weight: 0.85, role: "manual",
     author: "admin", ts: "..."},                              // 수동 편집
]
```

`delete_doc` cascade는 `s.doc_id == doc_entity_id` 조건으로만 source를 제거하므로:
- `role: extract` source: 해당 문서 삭제 시 제거됨
- `role: inverse` source: 동일
- `role: manual` source: `doc_id is null`이므로 어떤 문서 삭제에도 영향 없음

이로써 운영자의 수동 편집은 자동 cascade에서 면역으로 보존된다.

### 4.4 수정 Cascade (Diff Cascade) (도면 4 참조)

문서 D가 수정된 경우 (예: 같은 파일명으로 새 내용 재업로드):

```
Procedure modify_doc(doc_filename, new_content):
  old_extraction = load_cached_extraction(doc_filename)   // sidecar JSON
  new_extraction = llm_extract(new_content)

  removed = old_extraction - new_extraction               // (subject, predicate, object) tuples only in old
  added   = new_extraction - old_extraction
  kept    = old_extraction & new_extraction

  for rel in removed:
    drop_source(rel, doc_filename)                        // cascade only the removed
  for rel in added:
    add_source(rel, doc_filename, weight, role="extract") // ingestion only the added
  // `kept` — leave alone (no sources mutation)
```

핵심 특징:
- (subject, predicate, object) 트리플 단위 diff (LLM 출력 JSON blob 전체 대조 X)
- 변경되지 않은 관계의 source 항목은 timestamp 등 메타데이터 그대로 유지
- 사이드카 JSON으로 직전 추출 결과 보존 (롤백 가능, 디스크 비용 ~20KB/문서)

## 5. 효과

본 발명에 의한 효과:

1. **운영자가 잘못 업로드한 문서를 안심하고 삭제 가능** — 다른 출처가 강화한 derived knowledge는 살아남으면서 신뢰도만 정확히 차감.

2. **인간 개입의 영속성 보장** — 운영자가 수동으로 보강한 관계는 어떤 자동 cascade에도 휩쓸리지 않음.

3. **문서 수정 시 surgical update** — LLM 재추출 비용을 변경 분량만큼만 부담.

4. **단조성 수학 보장** — 시스템 전체가 출처 출입에 따라 일관된 방향으로 신뢰도 변화 → 운영자가 직관적으로 예측 가능.

5. **Audit 가능성** — 모든 cascade 이벤트가 audit log에 before/after 신뢰도와 함께 기록.

## 6. 청구범위

### 청구항 1 (방법 — 신뢰도 도출)

지식 그래프 시스템에서 관계의 신뢰도를 도출하는 방법으로서,
(a) 상기 관계에 대해 출처 가중치 집합 sources = {(doc_id_i, w_i, role_i, ts_i) : i = 1..n} 을 유지하는 단계;
(b) 상기 관계의 신뢰도 confidence를 다음 공식에 의해 도출하는 단계:
   confidence = 1 - Π(1 - w_i) for i in sources;
(c) 상기 도출된 신뢰도를 retrieval, scoring, 또는 reasoning 단계에서 사용하는 단계
를 포함하는 것을 특징으로 하는, 신뢰도 도출 방법.

### 청구항 2 (방법 — Cascade)

청구항 1의 방법을 사용하는 지식 그래프 시스템에서 출처 문서 삭제 시 derived knowledge를 정리하는 방법으로서,
(a) 삭제 대상 문서의 doc_id를 식별하는 단계;
(b) 모든 관계의 sources 배열에서 해당 doc_id 항목을 제거하는 단계;
(c) 청구항 1의 도출 공식에 의해 신뢰도를 재계산하는 단계;
(d) sources가 빈 관계는 그래프에서 제거하는 단계;
(e) 해당 문서가 attributes.source_document로 지정된 엔티티 중 다른 엔티티의 참조가 없는 엔티티를 제거하는 단계;
(f) 위 (b)~(e) 동작을 audit log에 before/after 메트릭과 함께 기록하는 단계
를 포함하는 것을 특징으로 하는, 지식 그래프 cascade 방법.

### 청구항 3 (시스템)

지식 그래프 시스템으로서,
- (1) 출처 가중치 집합을 유지하는 관계 저장소,
- (2) 청구항 1의 도출 공식을 적용하는 신뢰도 계산기,
- (3) 청구항 2의 cascade 절차를 수행하는 cascade 엔진,
- (4) 모든 cascade 이벤트를 기록하는 audit 로거
를 포함하는 것을 특징으로 하는, 출처 추적 기반 지식 그래프 시스템.

### 청구항 4 (종속 — 수동 편집 면역)

청구항 2에 있어서, 상기 sources 배열의 각 항목은 role 필드를 가지며, role이 "manual"이고 doc_id가 null인 항목은 (b)~(e) 단계에서 보존되는 것을 특징으로 하는 방법.

### 청구항 5 (종속 — Diff Cascade)

청구항 2에 있어서, 출처 문서가 수정될 때:
(a) 직전 추출 결과를 (subject, predicate, object) 트리플 집합으로 보존하는 단계;
(b) 새 내용에서 동일 트리플 집합을 추출하는 단계;
(c) 두 집합의 차집합 removed = old - new, added = new - old, 교집합 kept = old ∩ new를 산출하는 단계;
(d) removed에 대해서만 청구항 2의 (b)~(e)를 수행하고, added에 대해서만 source 추가를 수행하며, kept에 대해서는 source를 유지하는 단계
를 추가로 포함하는 것을 특징으로 하는, 부분 수정 cascade 방법.

### 청구항 6 (종속 — 단조성)

청구항 1에 있어서, 상기 도출 공식은:
- (i) sources에 새 항목이 추가될 때 confidence가 단조 증가하고,
- (ii) sources에서 항목이 제거될 때 confidence가 단조 감소하며,
- (iii) 0 ≤ confidence ≤ 1
의 성질을 가지는 것을 특징으로 하는 방법.

### 청구항 7~10 (종속 — 추가 한정)

7. 청구항 1에 있어서, 가중치 w_i ∈ [0, 1] 이고 LLM 추출 시 LLM 출력 score를 그대로 사용하는 방법.
8. 청구항 2에 있어서, 청구항 1의 도출 공식에 의해 cascade 후 confidence가 strictly 감소하는 (단조 감소 invariant) 것을 특징으로 하는 방법.
9. 청구항 3에 있어서, audit 로거가 cascade 전후 sources 배열을 그대로 기록하여 cascade 결정의 검증·재현이 가능한 것을 특징으로 하는 시스템.
10. 청구항 5에 있어서, 직전 추출 결과를 sidecar JSON 파일 형태로 업로드 디렉토리에 저장하는 것을 특징으로 하는 방법.

## 7. 도면 (작성 필요)

- **도면 1**: log-sum vs max vs mean 비교 그래프 — 출처 추가/제거 시 confidence 변화 곡선
- **도면 2**: cascade flow chart — delete_doc procedure 5 step
- **도면 3**: sources schema with role field — manual immunity 흐름
- **도면 4**: modify_doc diff cascade — old/new triple set 비교

## 8. 실시예 (Working Example)

`docs/design/v0.3-knowledge-cascade.md` §3 (Data Model Change), §5 (Delete Cascade), §6 (Modify Cascade), §14 (Reference Implementation Sketches) 참조. 본 임시명세서의 §4와 §6 청구항은 위 설계 문서를 기반으로 작성됐으며, 실제 구현은 본 출원 후 v0.3 사이클에 진행될 예정.

코드 인용 예 (도출 공식 — Python):

```python
def derive_confidence(sources: list[dict]) -> float:
    """1 - Π(1 - w_i) — log-sum / probabilistic OR."""
    if not sources:
        return 0.0
    p = 1.0
    for s in sources:
        w = max(0.0, min(1.0, float(s.get("weight", 0))))
        p *= (1.0 - w)
    return round(1.0 - p, 4)
```

cascade 헬퍼 코드 인용 예:

```python
def cascade_remove_doc_from_sources(doc_entity_id: str) -> dict:
    counts = {"entities_touched": 0, "relations_recomputed": 0,
              "relations_dropped": 0}
    for entity_path in iter_all_entity_paths():
        fm = read_frontmatter(entity_path)
        relations = fm.get("relations", [])
        new_rels = []; touched = False
        for rel in relations:
            old_n = len(rel.get("sources", []))
            rel["sources"] = [s for s in rel.get("sources", [])
                              if s.get("doc_id") != doc_entity_id]
            if len(rel["sources"]) == old_n:
                new_rels.append(rel); continue
            touched = True
            if not rel["sources"]:
                counts["relations_dropped"] += 1; continue
            rel["confidence"] = derive_confidence(rel["sources"])
            new_rels.append(rel)
            counts["relations_recomputed"] += 1
        if touched:
            counts["entities_touched"] += 1
            fm["relations"] = new_rels
            write_frontmatter(entity_path, fm)
    return counts
```

## 9. 출원 시 체크리스트

- [ ] 발명자/출원인 정보 기재
- [ ] 도면 1~4 작성 (`assets/patent/stage1b-figs/` 디렉토리 권장)
- [ ] §6 청구항 표현 한국어 법률 용어 검수 ("를 포함하는 것을 특징으로 하는" 어순 등)
- [ ] §8 실시예 코드 인용 — `core/llm_catalog.py` 등 향후 구현 파일 추가
- [ ] 공지예외 적용 신청서 별도 첨부 (특허로 → 민원서식)
- [ ] 출원료 6만원 (개인 감면 시 1.8만원) 납부

---

**End of skeleton.**

본 skeleton은 임시명세서 작성 시 발명자가 [TODO] 항목을 채우고 도면을 첨부해 사용. 정식 변환 시 변리사 검수 권장.
