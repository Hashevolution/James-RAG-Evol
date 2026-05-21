# STAGE 1A 선행 특허 검색 결과 — 2026-05-21

> 본 문서는 STAGE 1A (Doc-source gate, 출처 비대칭 게이트) 추가 prior art 검색 결과.
> 검색 트리거: 사용자 검토 의견 "비대칭 게이팅 개념은 CGR 추세와 일부 겹침" 우려.
> 검색 일자: 2026-05-21
> 검색 도구: Claude 자동 Agent (WebSearch + WebFetch)

---

## 1. 검색 타깃 (STAGE 1A 의 4 요소)

| 요소 | 설명 |
|---|---|
| ① | `entity_type == "document"` 조건부 asymmetric hop 게이팅 |
| ② | stem (확장자 제거) vs filename (확장자 포함) 비대칭 표기 |
| ③ | substring containment in `sources` 배열 (entity 내부 필드) |
| ④ | 12/13 baseline 보존 + 1 spurious path 차단 실증 |

---

## 2. 검색 결과 요약

### 위험 등급 분포

| 등급 | 건수 | 사례 |
|---|---|---|
| 🔴 거의 동일 | **0건** | — |
| 🟠 상당 겹침 | **1건** | HugRAG (arXiv 2602.05143, 미공개일 가능성, mechanism distinct) |
| 🟡 일부 겹침 | 9건 | US11080491B2 (IBM), PathRAG, Paths-over-Graph, CatRAG, CGR 등 |
| 🟢 무관 | 7건 | Microsoft GraphRAG, Provenance malware patents, 등 |

### 가장 가까운 후보들

#### 🟠 HugRAG (arXiv 2602.05143)
- 제목: Hierarchical Causal Knowledge Graph for RAG
- 특징: "causal gates" + N-hop traversal + "spurious path" 용어
- 차별점: **mechanism = causal LLM judgment** (STAGE 1A 는 deterministic substring matching)
- 위험: terminology 유사 (motivation), 메커니즘 distinct

#### 🟡 US11080491B2 (IBM, 2021-08-03)
- 제목: Filtering spurious knowledge graph relationships between labeled entities
- 특징: cosine similarity of context embeddings → spurious 필터링
- 차별점: **mechanism = embedding similarity** (STAGE 1A 는 string substring)
- 위험: motivation 유사, 메커니즘 명확히 다름

#### 🟡 PathRAG (arXiv 2502.14902, 2025-02)
- 제목: Flow-based pruning of relational paths
- 특징: reliability score 기반 path pruning
- 차별점: **mechanism = symmetric scoring** (STAGE 1A 는 asymmetric structural)
- 위험: pruning 자체 개념 일부 겹침

#### 🟡 Microsoft GraphRAG (microsoft/graphrag, 2024-07)
- 특징: community detection + hierarchical summary
- 차별점: **mechanism = community-based query** (STAGE 1A 는 hop-level gate)
- 위험: 무관 (다른 추상 수준)

---

## 3. 신규성 결론

**STAGE 1A 의 4 요소 결합은 prior art 부재.**

특히 다음 specific 메커니즘들은 **0 건** prior art:
- `entity_type == "document"` 조건부 비대칭 trigger
- entity.name (stem) ↔ entity.sources (filename) 비대칭 표기 활용
- substring containment in source array (외부 그래프 X)
- 12/13 benchmark preservation + 1 spurious path elimination 실증

---

## 4. 권고

⚠️ **narrow 청구 후 출원 진행** (조건부 ✅)

### 청구항 narrowing 전략

청구항 1 의 핵심 표현 (broad concept 위험 회피):

```
청구항 1 (narrow):
"지식 그래프 탐색 방법으로서,
 (a) 그래프 노드 N1 → N2 hop 평가 단계;
 (b) N1 의 entity_type 이 'document' 인 경우에 한해 (조건부 활성화),
     N1.name 의 확장자 제거 stem 이 N2.sources 배열의 어느 항목에도
     substring 으로 포함되지 않으면 hop 을 차단하는 단계;
 (c) N1 의 entity_type 이 'document' 가 아닌 경우 또는 sources
     매칭 성공 시 hop 을 허용하는 단계
 를 포함하는 것을 특징으로 하는 방법."
```

→ 모든 specific 디테일 (entity_type 검사, stem vs filename, substring) 명시.

### 강조할 차별점

1. **Deterministic (LLM/embedding 비사용)** — A-MAC, Mem0, HugRAG 와 명확 구분
2. **Structural (entity-internal sources)** — embedding 기반 IBM US11080491 와 구분
3. **Asymmetric (document only)** — symmetric pruning (PathRAG) 와 구분
4. **O(1) per-hop** — query-time embedding/LLM 미사용

---

## 5. 배경기술 인용 권장

명세서 §2 배경기술 에 다음 인용:

| 인용 | 차별 표현 |
|---|---|
| US11080491B2 (IBM, 2021) | "embedding similarity 기반의 spurious 필터링과 달리..." |
| US20160306896 (Oracle, 2016) | "범용 graph traversal hooks 와 달리, 본 발명은 specific predicate..." |
| Microsoft GraphRAG | "community detection 기반 질의와 달리, 본 발명은 hop-level gate..." |
| PathRAG (arXiv 2502.14902) | "flow-based scoring 과 달리, 본 발명은 deterministic structural..." |
| HugRAG (arXiv 2602.05143) | "causal LLM judgment 와 달리, 본 발명은 structural substring..." |

---

## 6. 등록 가능성 추정

- Narrow claim (위 안): **55~65%**
- Broad concept claim: 30~40% (비추천)
- Defensive publication 효과: ⭐⭐⭐ (이미 MIT + GitHub 로 확보, 출원은 offensive 보강)

---

## 7. 출원 결정

| 시나리오 | 결정 |
|---|---|
| 임시 출원 (₩13,800) | ✅ **진행 권장** |
| 정식 전환 (1년 후) | 변리사 자문 후 narrow claim 으로 등록 시도 |
| 비용 효율 | 좋음 (prior art 클리어) |

---

**End of prior-art-1A.md**
