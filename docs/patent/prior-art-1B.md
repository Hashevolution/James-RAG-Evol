# STAGE 1B 선행 특허 검색 결과

> 본 문서는 `stage1b-cascade-spec-skeleton.md` 출원 전 선행 특허 검색 결과를 기록한다.
> 작성일: 2026-05-11
> 검색 대상: Provenance Cascade + Log-sum Confidence (B 후보)

---

## 1. 검색 타깃 (요소 분해)

STAGE 1B의 결합 발명:

| 요소 | 설명 |
|---|---|
| ① | Knowledge graph relation이 **여러 source**를 갖는 구조 (sources array) |
| ② | Confidence를 **확률 OR / log-sum (`1 − Π(1−w)`)** 으로 도출 |
| ③ | 출처 문서 삭제 시 **automatic cascade** (source drop → recompute → orphan sweep) |
| ④ | **Manual 편집의 cascade 면역** (role 필드, doc_id=null) |
| ⑤ | 문서 수정 시 **(s, p, o) triple 단위 diff cascade** |
| ⑥ | **audit log + monotonicity 수학 보장** |

⚠️ 개별 요소는 선행기술이 있을 수 있음. **5~6요소 결합** 발명임을 보이는 게 핵심.

---

## 2. 검색 사이트 및 키워드

### 2.1 KIPRIS (한국, https://www.kipris.or.kr/)

#### 키워드 셋 A — 핵심 결합

```
1.  지식그래프 출처 cascade
2.  지식그래프 신뢰도 다중출처
3.  관계 출처 가중치 결합
4.  knowledge graph provenance
5.  graph 출처 추적 신뢰도
```

#### 키워드 셋 B — 수학 공식

```
6.  확률 OR 신뢰도
7.  log-sum 신뢰도 그래프
8.  monotone cascade 그래프
```

#### 키워드 셋 C — 도메인

```
9.  RAG 지식그래프 출처
10. LLM 지식그래프 cascade
```

#### 추가 필터
- 출원공개일: 2010-01-01 ~ 2026-05-11
- IPC: G06F16/36, G06N5/02

### 2.2 Google Patents (전 세계, https://patents.google.com/)

#### 검색식 1 — 핵심 결합
```
("knowledge graph" OR "graph database") AND ("provenance" OR "source attribution") AND ("cascade" OR "propagation")
```

#### 검색식 2 — 수학 공식
```
"knowledge graph" AND ("probabilistic OR" OR "noisy-OR" OR "log-sum") AND "confidence"
```

#### 검색식 3 — 삭제 cascade
```
"knowledge graph" AND ("source deletion" OR "document removal") AND ("relation" OR "edge") AND "confidence"
```

#### 검색식 4 — Manual 면역
```
"knowledge graph" AND ("manual edit" OR "human curation") AND ("preserve" OR "immune" OR "protect")
```

#### 검색식 5 — Triple diff
```
"knowledge graph" AND ("triple" OR "RDF") AND ("diff" OR "delta" OR "incremental update")
```

#### 검색식 6~10 보조
```
6.  "RAG" AND "knowledge graph" AND "maintenance"
7.  "fact extraction" AND "confidence" AND "multiple sources"
8.  "ontology" AND "source weight" AND "evidence accumulation"
9.  "Wikidata" AND "confidence" AND "cascade"
10. "GraphRAG" AND "provenance"
```

#### Google Patents 필터
- After: 2010
- Status: Granted + Active
- Country: KR, US, EP, WO, CN, JP
- CPC: G06F16/36, G06F16/2455, G06N5/022, G06N5/04

---

## 3. 발견된 의심 특허

### 3.1 KIPRIS 결과

> 사용자가 직접 검색 후 의심 건 여기에 추가.

#### 후보 K-1: [특허번호, 제목]
- 출원인:
- 출원일:
- 핵심 청구항 요약:
- STAGE 1B와의 차이:
- 위험 등급: 🟢/🟡/🟠/🔴

### 3.2 Google Patents 결과 (Claude 자동 검색)

> Claude가 자동 검색한 결과를 여기에 정리. (검색 진행 중)

#### 후보 G-1: [TBD]

### 3.3 Google Patents 결과 (사용자 직접 검색)

> 사용자가 직접 검색 후 의심 건 여기에 추가.

---

## 4. 위험 등급 매핑 가이드

| 등급 | 의미 | 조치 |
|---|---|---|
| 🟢 무관 | 도메인 다름·요소 일부만 일치 | 무시. 출원 진행 |
| 🟡 일부 겹침 | 1~2개 요소 일치 | 청구항을 결합 발명으로 좁힘. 종속항 차별점 명시 |
| 🟠 상당 겹침 | 3~4개 요소 일치 | 출원 전 청구항 대폭 수정 |
| 🔴 거의 동일 | 5개 이상 + 동일 도메인 | 출원 보류 + 변리사 자문 |

---

## 5. 최종 결론

- 위험 등급 🟠 이상: __건
- 위험 등급 🔴: __건
- **출원 진행 가부**:
  - [ ] ✅ 진행 (위험 없음)
  - [ ] ⚠️ 청구항 수정 후 진행
  - [ ] ❌ 보류 (변리사 자문 필요)

**비고**:

---

**작성자**: 발명자 본인 (DIY) + Claude (자동 보조 검색)
**작업 브랜치**: claude/security-audit-LRxjo
