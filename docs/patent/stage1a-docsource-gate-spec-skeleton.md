# [임시명세서 초안] STAGE 1A — Doc-source 출처 게이트 그래프 탐색

> 본 문서는 STAGE 1A (점수 3/5 ⭐, 신규 후보 A) 임시명세서 작성을 위한 skeleton입니다.
> 특허로(patent.go.kr) 전자출원 시 본 문서를 기반으로 PDF·hwp로 전환하여 첨부하십시오.
> 작성 시 [TODO] 마커를 모두 제거·채워주세요.
>
> **참고 자료**: PR #139 (`core/graph_engine.py:_doc_outgoing_hop_valid`), `tests/test_a5d_doc_source_gate.py` (14 unit tests).

---

## 발명의 명칭
**출처 메타데이터 비대칭성을 이용한 지식 그래프 traversal 게이팅 시스템 및 방법**
(영문: System and Method for Knowledge Graph Traversal Gating via Source Metadata Asymmetry)

## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]

## 공지예외 주장
- 공개일자: 2026-05-09 (PR #139 첫 commit)
- 공개매체: GitHub public repository (https://github.com/Hashevolution/James-RAG-Evol)
- 공개주체: 발명자 본인
- 공지예외 만료일: **2027-05-08**
- 증빙: `docs/patent/disclosure_log.txt` (A 후보 항목)

---

## 1. 기술 분야

본 발명은 인공지능 기반 지식 그래프 검색 시스템에 관한 것으로, 보다 구체적으로는 문서 노드와 엔티티 노드 사이의 그래프 traversal 시 출처(source) 메타데이터의 비대칭성을 이용해 가짜 추론 경로(spurious path)를 차단하는 시스템 및 방법에 관한 것이다.

## 2. 배경 기술

### 2.1 기존 그래프 RAG 시스템의 한계

Microsoft GraphRAG, RAG-Fusion, KGAT 등 기존 지식 그래프 기반 검색 시스템은 문서가 엔티티를 단순히 언급한 경우와 그 문서가 엔티티의 진짜 출처인 경우를 구별하지 못한다.

구체적으로, 다음과 같은 비대칭성이 시스템에 누적된다:
- **상황 A (정상)**: 문서 D가 엔티티 E의 출처 → E의 sources 메타데이터에 D가 포함됨
- **상황 B (오염원)**: 문서 D가 엔티티 E를 그저 언급만 함 → E의 sources에 D가 포함되지 않으나 entity-relation 그래프상 D–E 연결은 형성됨

기존 시스템은 두 경우를 동등하게 취급해 그래프 traversal 시 D→E hop을 모두 허용한다. 그 결과, 무관한 도메인의 엔티티가 cross-context에서 가짜 추론 경로를 생성한다.

### 2.2 본 발명이 다루는 구체 시나리오

운영자가 "Palantir 회사 분석 보고서"와 "비트코인 백서"를 차례로 업로드한다. 보고서 문서에 비트코인이 단순 비교 목적으로 언급된 경우, 기존 시스템은 다음과 같은 가짜 path를 생성한다:

```
"Palantir → (보고서 문서) → 비트코인 → (관련 산업) → 채굴"
```

운영자가 "Palantir의 채굴 활동" 같은 query를 던질 때, 위 spurious path가 그래프 traversal로 검색되어 무관한 답변이 생성된다.

## 3. 해결하고자 하는 과제

1. 문서 노드에서 엔티티 노드로의 hop 유효성을 출처 메타데이터로 게이팅하는 방법
2. "언급"과 "출처"의 비대칭성을 traversal 정책에 반영하는 시스템 구조
3. 다른 문서가 진짜 출처인 엔티티는 보존하면서 cross-context 가짜 path만 surgical하게 차단하는 방법
4. 게이팅으로 인한 부수 피해(legitimate path 손상)를 최소화하는 평가 기준

## 4. 과제의 해결 수단

### 4.1 출처 비대칭성 통찰

지식 그래프 ingestion 단계에서 다음 비대칭이 자연 발생한다:
- 엔티티 E가 문서 D에서 추출되면 E.sources에 D가 추가됨 (정방향, asymmetric)
- 문서 D는 엔티티 E를 언급한 모든 경우 D-E 그래프 edge를 생성함 (대칭, including spurious)

본 발명은 이 비대칭을 traversal gate로 활용한다.

### 4.2 Doc-source Hop Validation 알고리즘

```python
def _doc_outgoing_hop_valid(doc_entity_id: str, target_entity: dict) -> bool:
    """
    문서 노드 → 엔티티 노드 hop 유효성 검사.

    True iff target_entity.sources contains doc_entity_id.
    """
    target_sources = target_entity.get("sources", [])
    for src in target_sources:
        if isinstance(src, dict) and src.get("doc_id") == doc_entity_id:
            return True
        if isinstance(src, str) and src == doc_entity_id:
            return True
    return False
```

기존 DFS traversal에 다음 게이트를 삽입:

```python
# 기존 graph_engine.py:266-301 DFS loop 확장
for rel in relations:
    target_id = rel.get("target_id", "")
    target_entity = self.load_entity(target_id) or {}

    # [신규 게이트] doc → entity hop 유효성 검사
    if entity.get("entity_type") == "document":
        if not _doc_outgoing_hop_valid(eid, target_entity):
            continue   # 가짜 path 차단

    # 기존 logic 계속
    if rel.confidence < CONFIDENCE_THRESHOLD: continue
    if is_sensitive_relation(rel.type): continue
    dfs(target_id, d+1, ...)
```

### 4.3 비대칭 게이팅의 효과

- **정방향 정상 path**: D가 E의 진짜 출처 → E.sources에 D 포함 → hop 통과
- **역방향 정상 path**: E → D (역방향) → entity가 doc을 향한 hop은 본 게이트 적용 안 함 (asymmetric)
- **Cross-context 가짜 path**: D가 E를 단순 언급 → E.sources에 D 미포함 → hop 차단

### 4.4 평가 결과

baseline 13개 query에 대한 측정:
- 본 발명 적용 전: Palantir → 비트코인 spurious path가 4개 query에서 발생
- 본 발명 적용 후: 위 spurious path 0건, baseline 12/13 query 결과 보존 (낮은 부수 피해)
- 옵션 1 (blanket inferred-confidence threshold) 폐기 사유: 9/13 회귀 발생

## 5. 효과

1. **Cross-context 가짜 path 차단** — 문서가 단순 언급한 엔티티로의 spurious traversal 제거
2. **부수 피해 최소화** — 정방향 정상 출처 관계는 그대로 보존
3. **비대칭 통찰 활용** — 데이터 ingestion 시 자연 발생하는 비대칭을 게이트로 전환
4. **추가 LLM 호출 불필요** — 메타데이터 룩업만으로 게이팅, 비용 0
5. **Audit 가능** — 차단된 hop 횟수를 logging해 효과 측정 가능

## 6. 청구범위

### 청구항 1 (방법)

지식 그래프 시스템의 그래프 traversal 방법으로서,
(a) 문서 노드 D로부터 엔티티 노드 E로의 hop 후보를 식별하는 단계;
(b) 엔티티 노드 E의 출처 메타데이터(sources) 배열을 조회하는 단계;
(c) 상기 sources 배열에 문서 D의 식별자가 포함된 경우만 hop을 유효하다고 판정하는 단계;
(d) 유효 판정된 hop만 traversal 결과에 포함시키고 그렇지 않은 hop은 차단하는 단계
를 포함하는 것을 특징으로 하는, 출처 메타데이터 기반 그래프 traversal 게이팅 방법.

### 청구항 2 (시스템)

지식 그래프 검색 시스템으로서,
- (1) 엔티티 노드별 sources 메타데이터를 유지하는 그래프 저장소,
- (2) 청구항 1의 방법을 적용하는 traversal 엔진,
- (3) 차단된 hop 정보를 audit log에 기록하는 logger
를 포함하는 것을 특징으로 하는, 출처 추적 기반 지식 그래프 검색 시스템.

### 청구항 3 (종속 — 비대칭 적용)

청구항 1에 있어서, 상기 게이트는 문서 노드 → 엔티티 노드 방향에만 적용되고, 엔티티 노드 → 문서 노드 방향에는 적용되지 않는 것을 특징으로 하는 방법.

### 청구항 4 (종속 — sources 구조)

청구항 1에 있어서, 상기 sources 배열의 각 항목은 doc_id 필드를 가지며, 게이트는 `target_entity.sources[i].doc_id == doc_id_of_source_node` 조건으로 판정하는 것을 특징으로 하는 방법.

### 청구항 5 (종속 — DFS 통합)

청구항 1에 있어서, 상기 게이팅은 DFS 그래프 traversal의 인접 노드 확장 단계에 삽입되어, 게이트 통과 hop만 재귀 호출되는 것을 특징으로 하는 방법.

### 청구항 6~10 (종속)

6. 청구항 1에 있어서, 차단된 hop 횟수를 측정하여 시스템의 효과 메트릭으로 사용하는 방법.
7. 청구항 1에 있어서, 본 게이트의 적용 결과 baseline query의 의미적 정답률이 보존되는지 회귀 테스트로 검증하는 방법.
8. 청구항 2에 있어서, 상기 audit logger가 차단 hop의 source/target 식별자를 기록하여 운영자가 차단 사유를 검토 가능한 시스템.
9. 청구항 1에 있어서, 게이트는 LLM 호출 없이 메타데이터 룩업만으로 수행되는 방법.
10. 청구항 1에 있어서, 게이트 통과 여부와 무관하게 sensitive relation 차단, confidence threshold 등 기존 게이트는 직교적으로 적용되는 방법.

## 7. 도면 (작성 필요)

- **도면 1**: 비대칭 ingestion 흐름 — 같은 문서 D가 sources(asymmetric)와 graph edges(symmetric)에 다르게 기록됨
- **도면 2**: 가짜 path 발생 시나리오 — Palantir 문서 + 비트코인 언급 → spurious "Palantir → 비트코인 → 채굴" path
- **도면 3**: 게이트 적용 후 — 가짜 hop 차단, 정상 path 보존
- **도면 4**: DFS 알고리즘 흐름도 — 게이트 삽입 위치 명시

## 8. 실시예 (Working Example)

`core/graph_engine.py:220-307` 의 `expand_dynamic` DFS에 게이트가 삽입된 형태:

```python
def expand_dynamic(self, entity_ids, source_type_filter=None):
    visited, entities, paths = set(), [], []

    def dfs(eid, d, path_so_far, parent_score):
        if d > MAX_DEPTH or eid in visited: return
        visited.add(eid)
        entity = self.load_entity(eid)
        if not entity: return

        relations = entity.get("relations", [])
        for rel in relations:
            target_id = rel.get("target_id", "")
            target_entity = self.load_entity(target_id) or {}

            # [PR #139 신규 게이트]
            if entity.get("entity_type") == "document":
                if not _doc_outgoing_hop_valid(eid, target_entity):
                    continue

            # 기존 게이트
            if rel.get("confidence", 0) < CONFIDENCE_THRESHOLD: continue
            if is_sensitive_relation(rel.type): continue
            ...
            dfs(target_id, d+1, ...)
```

회귀 검증: `tests/test_a5d_doc_source_gate.py` 14개 unit test로 정방향/역방향/cross-context 시나리오 검증.

## 9. 산업상 이용 가능성

본 발명은 GraphRAG 기반 챗봇, 다중 문서 KG QA, 기업 내부 지식관리 시스템에서 cross-context 오염을 방지하는 데에 산업상 이용 가능하다. 특히 운영자가 다양한 도메인의 문서를 업로드하는 환경에서 검색 품질을 유지하는 데에 유용하다.

---

## 10. 출원 시 체크리스트

- [ ] 발명자/출원인 정보 기재
- [ ] 도면 1~4 작성 (`assets/patent/stage1a-figs/` 권장)
- [ ] §6 청구항 한국어 법률 용어 검수
- [ ] §8 실시예에 PR #139 머지 시 실제 코드로 보강
- [ ] 공지예외 적용 신청서 별도 첨부
- [ ] 출원료 6만원 (개인 감면 시 1.8만원) 납부

---

**End of skeleton.**
